# Vendored from the private production pipeline (syllabus2anki).
# Logic UNCHANGED except: (1) WS data-dir override via S2A_DATA_DIR,
# (2) tolerant/overridable data-file loads (S2A_ENTRIES / S2A_AUDIO_MAP_OUT).
# Regression-verified byte-identical against production outputs. See docs/pipeline.md.
# -*- coding: utf-8 -*-
"""
词义频次模块：用红宝书的 COCA 分布决定「哪条义项最常用」

数据形态（6047 词有，百分比总和=100）：
    constitute → 构成(70%)，组成(19%)，制定(4%)，建立(4%)，任命(3%)

核心规则（用户定死）：核心义必须 = 最常用义。

排序键 = (-频次, -精度, 原顺序)
  · 频次：该义项对应到的 COCA 百分比
  · 精度：COCA 义与义项文本的贴合度（越短越干净的包含关系精度越高）
    这条用来避免「遗憾」匹配上「（用于正式书面语）对…感到抱歉，对…感到遗憾」这种长尾巴，
    从而让「遗憾，惋惜」这种干净短义项胜出。

匹配策略（从严到宽）：完全相同 100 > 包含 90 > 连续两字以上 70+ > 字集过半 40
"""
import json, os, re

WS = os.environ.get("S2A_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
_HBS = None

NOISE = {"名词", "动词", "形容词", "副词", "介词", "连词", "代词",
         "数词", "感叹词", "短语", "形式", "分词", "复数", "过去式",
         "不定式", "比较级", "最高级"}


def _load():
    global _HBS
    if _HBS is None:
        p = os.path.join(WS, "hbs_index.json")
        _HBS = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    return _HBS


def parse_coca(coca):
    out = []
    for m in re.finditer(r"([^，,；;（(]+?)[（(](\d+)%[）)]", coca or ""):
        z = m.group(1).strip()
        if not z or z in NOISE:
            continue
        if re.search(r"形式|分词|复数$|^动词|^名词", z):
            continue
        out.append((z, int(m.group(2))))
    return out


def dist(word):
    h = _load().get((word or "").lower()) or {}
    d = parse_coca(h.get("coca"))
    d.sort(key=lambda x: -x[1])
    return d


def _clean(s):
    s = re.sub(r"^[a-z]+\.", "", s or "")
    s = re.sub(r"（[^）]*）|\([^)]*\)", "", s)
    s = re.sub(r"〔[^〕]*〕", "", s)
    return s.strip(" ，,。；;、／/.")


def match(zh, sense):
    """COCA 义 zh 与词典义项 sense 的匹配度，0 = 不匹配"""
    a, b = _clean(zh), _clean(sense)
    if not a or not b:
        return 0
    if a == b:
        return 100
    if a in b or b in a:
        return 90
    best = 0
    for i in range(len(a)):
        for j in range(i + 2, len(a) + 1):
            if a[i:j] in b:
                best = max(best, j - i)
    if best >= 2:
        return 70 + min(best, 6)
    sa, sb = set(a), set(b)
    if len(a) <= 4 and sa and len(sa & sb) / len(sa) >= 0.5:
        return 40
    return 0


def _precision(zh, sense):
    """贴合精度：义项越接近 COCA 原词，精度越高（0-30）

    只在「包含式匹配」时按多余字数扣分；义项本身是同义并列（"部，司，系，处，科"）
    不该因为长就被判低分 —— 那会把完整义项挤到后面。
    """
    a, b = _clean(zh), _clean(sense)
    if not a or not b:
        return 0
    if a == b:
        return 30
    if a in b:
        # 义项是 COCA 义 + 其它并列片段：只要开头就是该义，视为高精度
        if b.startswith(a):
            return 28
        extra = max(0, len(b) - len(a))
        return max(0, 30 - extra)
    if b in a:
        return 26
    return 20


def sense_key(word, sense, idx, d=None):
    """义项排序键：(-频次, -匹配度, -精度, 原顺序)"""
    d = dist(word) if d is None else d
    best_pct, best_sc, best_prec = -1, 0, 0
    for zh, pct in d:
        sc = match(zh, sense)
        if sc < 40:
            continue
        prec = _precision(zh, sense)
        if pct > best_pct:
            best_pct, best_sc, best_prec = pct, sc, prec
        elif pct == best_pct:
            if (sc, prec) > (best_sc, best_prec):
                best_sc, best_prec = sc, prec
    return (-best_pct, -best_sc, -best_prec, idx)


def has_freq(word):
    return bool(dist(word))


def top_sense(word):
    d = dist(word)
    return d[0] if d else (None, 0)


def top_ties(word, tol=1):
    """并列最高频的一组义（容差 tol 个百分点）"""
    d = dist(word)
    if not d:
        return []
    top = d[0][1]
    return [zh for zh, p in d if p >= top - tol]


def _core_of(s):
    """义项去掉括注后的主体（"（商场里的）部" → "部"）"""
    return re.sub(r"[（(][^）)]*[）)]", "", s or "").strip(" ，,。；;、")


def rank_senses(word, senses):
    """按频次重排义项；若 COCA 首位义在词典里对不上，则补在最前"""
    if not senses:
        return list(senses), False, None
    # 同义重复收缩：若 A 的括注主体被 B 完全包含且 B 信息更全，丢掉 A
    # （"（商场里的）部" 和 "（组织或机构中的）部，司，系，处，科" 二选一，留后者）
    if len(senses) > 1:
        keep = []
        for s in senses:
            cs = _core_of(s)
            redundant = False
            for t in senses:
                if t == s:
                    continue
                ct = _core_of(t)
                if cs and ct and cs in ct and len(ct) > len(cs):
                    redundant = True
                    break
            if not redundant:
                keep.append(s)
        if keep:
            senses = keep
    d = dist(word)
    if not d:
        return list(senses), False, None
    zh0, pct0 = d[0]
    senses = list(senses)
    injected = False
    if not any(match(zh0, s) >= 40 for s in senses):
        senses = [zh0] + senses
        injected = True
    keyed = [(sense_key(word, s, i, d), s) for i, s in enumerate(senses)]
    keyed.sort(key=lambda x: x[0])
    return [s for _, s in keyed], injected, zh0


if __name__ == "__main__":
    cases = {
        "regret": ["懊悔，惋惜", "（用于正式书面语）对......感到抱歉，对......感到遗憾", "〔古〕对（损失或缺乏）感到痛惜"],
        "perceptive": ["感知力强的，有洞察力的，思维敏捷的", "视觉的，听觉的，感觉的"],
        "susceptible": ["易得病的，易受影响的", "（人）易受感动的，易动感情的", "可能有······的，容许······的"],
        "icon": ["图标", "偶像，代表", "画像，雕像"],
        "wardrobe": ["衣柜，衣橱", "全部服装"],
        "default": ["不履行，违约", "默认，系统设定值"],
        "constitute": ["组成，构成", "是，被视为", "成立，设立"],
    }
    for w, senses in cases.items():
        ranked, inj, top = rank_senses(w, senses)
        print(f"{w:13s} COCA首位:{top}  → {ranked[0]!r}  补位={inj}")
    print("\nregret 各义项排序键：")
    d = dist("regret")
    for s in cases["regret"]:
        print(f"  {s[:34]:36s} {sense_key('regret', s, 0, d)}")
