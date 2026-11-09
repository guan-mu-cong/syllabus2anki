# Vendored from the private production pipeline (syllabus2anki M2).
# Logic is UNCHANGED except the WS data-dir override via S2A_DATA_DIR,
# so regression output is byte-identical to production. See docs/pipeline.md.
import json, os, re, sys, html, random

WS = os.environ.get("S2A_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))  # 2026-11-08: 旧路径指向 scratch，已被 24h 清理，改用工程目录
sys.path.insert(0, WS)
import ydparse
import p0_clean as P0
import freq


plan = {p["word"].strip().lower(): p for p in json.load(open(os.path.join(WS, "plan.json"), encoding="utf-8"))}
corpus = json.load(open(os.path.join(WS, "corpus.json"), encoding="utf-8"))


def _cet_papers(c):
    """六级语料里出现过的套卷集合（如 2013.06），用于把「套数」标准化"""
    ps = set()
    for lst in c.values():
        for e in lst:
            if e.get("kind") != "cet6":
                continue
            m = re.search(r"(\d{4})[.-](\d{2})", e.get("src", ""))
            if m:
                ps.add(m.group(1) + "." + m.group(2))
    return ps


CET_PAPERS = _cet_papers(corpus)

hbs = json.load(open(os.path.join(WS, "hbs_index.json"), encoding="utf-8"))
engra = json.load(open(os.path.join(WS, "engra_index.json"), encoding="utf-8"))
amap = json.load(open(os.path.join(WS, "audio_map.json"), encoding="utf-8"))
from wordfreq import zipf_frequency

_TRANS = {}
_tp = os.path.join(WS, "translations.json")
if os.path.exists(_tp):
    _TRANS = json.load(open(_tp, encoding="utf-8"))


def _strip_num(s):
    return P0.strip_lead_num(s)


def _zh_for(en, zh):
    if zh and zh.strip():
        return zh
    return _TRANS.get(_strip_num(en), "")

JUNK = re.compile(
    r"〔[^〕]{0,12}?(?:古|旧|非正式|口语|方言|俚|律|医|化|生物|数|计|军|航海|印刷|纹章|天主教|基督教|语法|音乐|体育|牌戏)[^〕]{0,12}?〕"
)
NAME = re.compile(r"人名|地名|（[美英德法巴俄印日]）|【名】")


def trim_name(s):
    """去掉义项里的人名/地名括注，保留真实词义。
    "六月；琼（人名）" → "六月"
    "（Spaghetti，首字母大写）意大利语人名或姓氏…" → ""
    """
    if not s or not NAME.search(s):
        return s
    parts = [p for p in re.split(r"[；;]", s) if p.strip()]
    keep = [p.strip() for p in parts if not NAME.search(p) and not re.search(r"[（(][^）)]*[）)]$", p.strip())]
    keep = keep or [p.strip() for p in parts if not NAME.search(p)]
    out = "；".join(keep).strip("；;，, ")
    # 剩下如果只是"人名/名字"之类，视为无有效义项
    if not out or re.fullmatch(r"[（(]?[^）)]*[）)]?人名[^，。；]*", out):
        return ""
    return out


# 旧版按单字模糊匹配（古|化|生|物|数|计），会误杀「文化，文明」「生态系统」「使加重」这类正常义项。
# P0 只清洗实体，语域过滤维持原状；把该项设为 True 才启用精确版本（仅匹配〔古〕〔非正式〕这类标记）。
JUNK_STRICT = True   # 2026-11-08：精确匹配〔古〕〔非正式〕这类标记；单字模糊版会误杀「文化，文明」「妈妈，母亲」
JUNK_OLD = re.compile(r"古|旧|非正式|口语|方言|俚|律|医|化|生|物|数|计|军|航海|印刷|纹章|天主教|基督教|语法|音乐|体育|牌戏")


def strip_tags(s):
    return P0.text(s)


def pos_and_body(line):
    m = re.match(r'<span class="pos">([^<]*)</span>(.*)', line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", line.strip()


def split_items(body):
    return [x.strip() for x in re.split(r"[；;]", body) if x.strip()]


def simplify(p, limit_pos=3, limit_total=4, per_pos=3, word=None):
    """把 释义详 收敛成 ≤limit_total 条常用义项，返回 (html, 全义项html, 首义)

    word 给出时用 COCA 使用频率排序：核心义强制取最常用义（用户定死的规则）。
    """
    raw = P0.marks_to_brackets(P0.unescape_all(p.get("释义详") or ""))
    lines = [l for l in raw.split("<br>") if l.strip()]
    out, full = [], []
    for line in lines:
        pos, body = pos_and_body(line)
        items = split_items(body)
        if not pos:
            items = [re.split(r"[：:]/", x)[0].strip() for x in items]
        keep = []
        for x in items:
            jm = (JUNK if JUNK_STRICT else JUNK_OLD).search(x)
            if jm:
                # 语域标记（〔旧〕〔古〕〔非正式〕）只是修饰，剥掉标记保留词义，
                # 不能整条丢（"〔旧〕少女，未婚女子，处女" 仍要保留"少女…"）
                stripped = re.sub(r"^[〔\[\[][^〕\]\]]{1,16}[〕\]\]]\s*", "", x).strip()
                if not stripped or (JUNK if JUNK_STRICT else JUNK_OLD).search(stripped):
                    continue
                x = stripped
            keep.append(x)
        # 人名/地名：只摘掉那一段，别把整条义项判死（"n. 六月；琼（人名）" 仍有"六月"）
        keep = [trim_name(x) for x in keep]
        keep = [x for x in keep if x]
        keep = keep or items[:1]
        # 去重（包含关系）
        uniq = []
        for x in keep:
            if not any(x in y or y in x for y in uniq):
                uniq.append(x)
        full.append((pos, uniq))
        if len(out) < limit_pos and uniq:
            sel = uniq[:per_pos]
            out.append((pos, sel))

    # ---- 按 COCA 使用频率重排（核心义 = 最常用义）----
    # 关键约束：COCA 分布不给词性，中文「膝盖」既能匹配 n. 膝盖 也能匹配 v. 用膝盖顶。
    # 所以先定「主词性」= 原词典第一条义项所属的组（词典正文顺序天然反映常用性，
    # 如 knee 首义就是 n. 膝盖），再在主词性组内按频次挑最常用义。
    # 只有当别的组存在「频次严格更高、且传统用度也更高」的义项时才整体换组（regret 的 n. 遗憾）。
    if word:
        freq_ranked = []
        for pos, items in out:
            ranked, injected, top_zh = freq.rank_senses(word, items)
            freq_ranked.append((pos, ranked))
        if len(freq_ranked) > 1 and freq.dist(word):
            d = freq.dist(word)
            first_pct = -freq.sense_key(word, freq_ranked[0][1][0], 0, d)[0]

            def group_pct(g):
                pos, items = g
                if not items:
                    return -1
                return max(freq.sense_key(word, s, i, d)[0] * -1 for i, s in enumerate(items))

            def group_key(g):
                pos, items = g
                if not items:
                    return (0, 9, 9, 9)
                return min(freq.sense_key(word, s, i, d) for i, s in enumerate(items))

            best_alt = max((group_pct(g) for g in freq_ranked[1:]), default=-1)
            # 换组条件从严：只有替代组频次严格高出 20 个百分点才换（抑制跨词性误匹配）
            # 同频不换（knee 的 v. 用膝盖顶 也能匹配"膝盖"，不能让它篡位）
            if best_alt > first_pct + 20:
                scored = [((-group_pct(g), group_key(g)), gi, g)
                          for gi, g in enumerate(freq_ranked)]
                scored.sort(key=lambda x: (x[0], x[1]))
                freq_ranked = [g for _, _, g in scored]
        out = freq_ranked

    # 总量截断
    budget = limit_total
    trimmed = []
    for pos, items in out:
        take = items[:budget]
        if take:
            trimmed.append((pos, take))
            budget -= len(take)
        if budget <= 0:
            break
    first_pos, first_items = (trimmed[0] if trimmed else ("", [""]))
    core_txt = clean_core(first_items[0] if first_items else "", word=word)
    core = f'<span class="pos">{P0.esc(first_pos)}</span>{P0.esc(core_txt)}' if first_pos else P0.esc(core_txt)

    def render(pairs):
        return "<br>".join(
            f'<span class="pos">{P0.esc(pos)}</span>{ "；".join(P0.esc(x) for x in items) }' if pos
            else "；".join(P0.esc(x) for x in items)
            for pos, items in pairs if items)
    full_html = "<br>".join(
        f'<span class="pos">{P0.esc(pos)}</span>{ "；".join(P0.esc(x) for x in items) }' if pos
        else "；".join(P0.esc(x) for x in items)
        for pos, items in full if items)
    return render(trimmed), full_html, core


def ipa_clean(s):
    s = (s or "").strip()
    s = s.split(";")[0].strip()
    s = re.sub(r"^\[|\]$", "", s)
    return s


def clean_core(s, word=None):
    s = P0.unescape_all(s or "")
    s = re.sub(r"^[〔\[（(][^〕\]）)]{0,12}[〕\]）)][\s　]{0,3}", "", s)  # 去掉开头的语域标记
    s = s.replace("〔", "").replace("〕", "")
    s = re.split(r"[：:]", s)[0]
    # 开头的括注通常是限定语（"（组织或机构中的）部，司，系"），
    # 直接丢掉会把后面的并列片段一起切没 → 先摘掉括注内容本身，保留其后的正文
    s = re.sub(r"^[（(][^）)]*[）)]\s*", "", s)
    # 再摘掉其余的成对括注
    s = re.sub(r"（[^）]*）|\([^)]*\)", "", s)
    # 括号不配对的残句：从第一个孤立的 （ 或 ( 起截掉
    s = re.split(r"[（(]", s)[0]
    s = re.sub(r"^[，,。、；;\s]+", "", s)
    s = s.strip("，,。 ")

    # 一条义项里用逗号并列了多个近义片段、且整体过长时（感知力强的，有洞察力的，思维敏捷的），
    # 挑与 COCA 首位义最贴近的那一段；否则保留完整义项
    # （"部，司，系，处，科" 不该被拆成 "部"，"膝盖，膝关节" 不该被裁成 "膝盖"）
    if word and len(s) > 16:
        d = freq.dist(word)
        if d:
            segs = [x.strip() for x in re.split(r"[，,、]", s) if x.strip()]
            if len(segs) > 1:
                # 只有当某片段明显更贴合（比第一名高出 20 分以上）才拆，否则保留整条
                scored = []
                for sg in segs:
                    sc = max(freq.match(zh, sg) for zh, _ in d)
                    prec = max((freq._precision(zh, sg) for zh, _ in d), default=0)
                    scored.append((sc, prec, len(sg), sg))
                scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
                best_sc = scored[0][0]
                if len(scored) > 1 and best_sc >= 40 and best_sc - scored[1][0] >= 20 and len(scored[0][3]) <= 16:
                    return scored[0][3].strip("，,。 ")
    # 超长时不再"砍在第一个逗号"，而是按片段累加，尽量多保留同义片段
    # （"部，司，系，处，科" 不该只剩 "部"）
    if len(s) > 16:
        segs = [x.strip() for x in re.split(r"[；;]", s) if x.strip()]
        s = segs[0] if segs else s
        if len(s) > 16:
            parts = [x.strip() for x in re.split(r"[，,、]", s) if x.strip()]
            acc = parts[0] if parts else s
            for p in parts[1:]:
                cand = acc + "，" + p
                if len(cand) <= 16:
                    acc = cand
                else:
                    break
            s = acc if len(acc) >= 2 else s[:16]
        return s.strip("，,。 ")
    return s


def syll_of(w, h):
    raw = (h or {}).get("syll") or ""
    raw = raw.strip()
    if raw:
        segs = [x for x in raw.split("·") if x]
        if segs and min(len(x) for x in segs) >= 2 and len(segs) <= max(2, len(w) // 3):
            return raw
    try:
        import pyphen
        if len(w) >= 6 and " " not in w and "-" not in w:
            return pyphen.Pyphen(lang="en_US").inserted(w).replace("-", "·")
    except Exception:
        pass
    return ""


def badge(w, p, h):
    """考频牌：六级部分统一写成「X/N套 · Y处」，没有六级记录就明写「六级未考」。

    旧写法 `六级真题 27 次` 会让人误以为考了 27 次，其实那是「27 套卷里出现了 27 套」
    （语料共 27 套，属封顶值）；而 4022 张没有六级记录的写 `词频 4.7`，
    两种单位混在同一字段里，无法比较也无法检索。
    """
    parts = []
    # ---- 六级真题：统一以「套数/总套数 · 实际出现处数」表达 ----
    papers = set()
    occ = 0
    for c in corpus.get(w, []):
        if c.get("kind") != "cet6":
            continue
        occ += 1
        m = re.search(r"(\d{4})[.-](\d{2})", c.get("src", ""))
        if m:
            papers.add(m.group(1) + "." + m.group(2))
    total_papers = len(CET_PAPERS)
    if papers:
        parts.append(f"六级真题 {len(papers)}/{total_papers}套 · {occ}处")
    else:
        parts.append(f"六级未考 · 词频 {zipf_frequency(w, 'en'):.1f}")
    # ---- 考研真题：真实次数，保留 ----
    if h:
        freq = re.search(r"近<a>(\d+)</a>年<a>(\d+)</a>次", h.get("exam_freq") or "")
        if freq and int(freq.group(2)) > 0:
            parts.append(f"考研真题 {freq.group(2)} 次")
    return " · ".join(parts)


def _junk_example(en):
    """例句质量闸门：拦掉 OCR 乱码、残留实体、控制字符

    hi 的真题例句原文是 "•*ffiApp f.Hi!l'ti!l'lli-1< Directions:"，
    quote 的真题例句里有未还原的 "& quote;" —— 这类句子不能上卡。
    """
    if not en:
        return True
    if re.search(r"&\s*(?:[a-zA-Z][a-zA-Z0-9]{1,10}|#\d{1,6});", en):  # 残留实体（含 "& quote;" 这种带空格的）
        return True
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", en):      # 控制字符
        return True
    # 乱码特征：连续非常规符号、单词里夹 1 等
    if re.search(r"[!]{2,}|[•*]{2,}|\b\w*[!]{2,}\w*\b", en):
        return True
    letters = len(re.findall(r"[A-Za-z]", en))
    if letters == 0 or letters / max(len(en), 1) < 0.55:              # 字母占比过低
        return True
    return False


def pick_exam(w, limit=2):
    cands = []
    h = hbs.get(w)
    if h:
        for e in h.get("exams") or []:
            en = e.get("en", "").strip()
            if not en:
                continue
            n = len(en.split())
            if 5 <= n <= 45 and not _junk_example(en):
                cands.append({"en": en, "zh": e.get("zh", ""), "src": "考研 " + re.sub(r"\s+", " ", e.get("from", "")), "score": 3 if 10 <= n <= 30 else 1})
    for c in corpus.get(w, []):
        if c.get("kind") != "cet6":
            continue
        en = c["en"]
        n = len(en.split())
        if 5 <= n <= 45 and not _junk_example(en):
            cands.append({"en": en, "zh": c.get("zh", ""), "src": c["src"], "score": 4 if 8 <= n <= 26 else 2})
    cands.sort(key=lambda x: -x["score"])
    seen, out = set(), []
    for c in cands:
        k = c["en"][:60].lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
        if len(out) >= limit:
            break
    return out


def pick_quality(w, limit=1):
    out = []
    d = ydparse.load(w) or {}
    for en, zh in ydparse.examples(d, w, limit=4):
        n = len(en.split())
        if 6 <= n <= 26 and "真题" not in en:
            out.append({"en": en, "zh": zh, "src": "词典例句"})
        if len(out) >= limit:
            break
    if not out:
        for c in corpus.get(w, []):
            if c.get("kind") == "tat":
                out.append({"en": c["en"], "zh": c.get("zh", ""), "src": "Tatoeba"})
                break
    return out


def ex_html(items, cls, numbered=False):
    """例句渲染：圆点列表（P0-2：不再用 1/2 数字编号）"""
    parts = []
    for i, e in enumerate(items, 1):
        raw = P0.clean_sentence(e["en"])
        en = P0.esc(raw)
        zh_txt = P0.text(e["zh"]) if e.get("zh") else ""
        zh = f'<div class="zh">{P0.esc(zh_txt)}</div>' if zh_txt else ""
        src = f'<span class="src">{P0.esc(e["src"])}</span>' if e.get("src") else ""
        num = f'<span class="num">{i}</span>' if numbered else '<span class="bullet">·</span>'
        parts.append(f'<div class="ex-item">{num}<span class="en">{en}</span>{src}{zh}</div>')
    return "".join(parts)


def root_html(w, h):
    if h and h.get("root"):
        t = P0.unescape_all(h["root"]).replace("\r", " ")
        return f'<div class="rx">{P0.esc(t).replace(chr(10), "<br>")}</div>'
    e = engra.get(w)
    if e and e.get("root"):
        rm = f'（{P0.esc(e["root_meaning"])}）' if e.get("root_meaning") else ""
        return f'<div class="rt"><span class="rt-root">{P0.esc(e["root"])}</span>{rm}</div>'
    return ""


def mnemonic_html(w, h):
    """P0-4：只输出真正讲了词义的助记；纯词根分解（空壳）不输出"""
    e = engra.get(w)
    mn = (e or {}).get("mnemonic") or ""
    if mn and not P0.mnemonic_shell(mn):
        return f'<div class="mn">{P0.esc(mn)}<span class="src">engra</span></div>'
    ai = AI_MNEMONIC.get(w, "")
    if ai and not P0.mnemonic_shell(re.sub(r"<[^>]+>", "", ai)):
        return ai
    return ""


def etym_html(w, h):
    """P0-1：词源里含 &#13; 等实体，先解码再转义，否则卡面会露出 &#13;"""
    if h and h.get("etym"):
        t = P0.unescape_all(h["etym"]).replace("\r", " ")
        t = fix_unclosed(t)
        return f'<div class="et">{P0.esc(t[:600]).replace(chr(10), "<br>")}</div>'
    return ""


def fix_unclosed(t):
    """修源数据里括号不闭合的残句：impact冲击，碰撞；(  → 去掉孤立括号"""
    t = re.sub(r"[；;，,]?\s*[（(]\s*(?=<br>|\n|$)", "", t)
    t = re.sub(r"^\s*[（(]\s*", "", t)
    return t


def discrim_html(w, h):
    if h and h.get("discrim"):
        t = P0.unescape_all(h["discrim"]).replace("\r", " ")
        return f'<div class="dc">{P0.esc(t[:800]).replace(chr(10), "<br>")}</div>'
    return ""


_AI_PATH = os.path.join(WS, "ai_mnemonic.json")
AI_MNEMONIC = json.load(open(_AI_PATH, encoding="utf-8")) if os.path.exists(_AI_PATH) else {}
_OLD_AI = {
    "parliament": '<div class="mn">parlia（说，parley）+ ment（名词后缀）→ 大家坐在一起说话的地方 → 议会<span class="src">AI 助记</span></div>',
    "résumé": '<div class="mn">re（再）+ sum（拿，取）→ 把经历再取出来交给人看 → 简历<span class="src">AI 助记</span></div>',
    "according to": '<div class="mn">accord（一致）+ ing → 与某人说法一致 → 根据<span class="src">AI 助记</span></div>',
    "up": '<div class="mn">古英语 uppan“在上面”，与 over、open 同源 → 向上<span class="src">AI 助记</span></div>',
}


GOOD_POS = ("n.", "v.", "vt.", "vi.", "adj.", "adv.", "prep.", "pron.", "conj.", "num.", "art.", "aux.")


def en_ok(t):
    plain = strip_tags(t or "")
    if not plain.strip():
        return False
    if len(plain) > 420:
        return False
    m = re.match(r"^\s*([A-Za-z]{1,12}[.:])", plain)
    if m and m.group(1).rstrip(".:").lower() not in [x.rstrip(".") for x in GOOD_POS]:
        return False
    if "[[" in plain or "]]" in plain or "(the colon" in plain:
        return False
    return True


def collins_en(w, p):
    h = p.get("柯林斯解释") or ""
    m = re.search(r'<div class="ce-def">(.*?)</div>', h, re.S)
    if not m:
        return ""
    t = re.sub(r"<[^>]+>", "", m.group(1))
    t = re.sub(r"^If .*?, ", "", t)  # 柯林斯常以 If 从句开头
    t = re.sub(r"[\u4e00-\u9fff，。；：、]+$", "", t).strip()
    return P0.esc(t[:220])


def trim_en(t, prefer_pos=""):
    t = P0.unescape_all(t or "")
    lines = [l for l in t.split("<br>") if l.strip()]
    parsed = []
    for l in lines:
        m = re.match(r"^\s*([a-z]+\.)\s*(.*)$", strip_tags(l))
        pos = m.group(1) if m else ""
        body = m.group(2) if m else strip_tags(l)
        body = re.split(r"[；;]", body)[0].strip()
        parsed.append((pos, body))
    m0 = re.search(r'<span class="pos">([^<]*)</span>', prefer_pos or "")
    pref = m0.group(1).strip() if m0 else ""
    parsed.sort(key=lambda x: 0 if (pref and x[0] == pref) else 1)
    out = []
    for pos, body in parsed[:2]:
        if not body:
            continue
        out.append(P0.esc(f"{pos} {body}"[:110]))
    return "<br>".join(out)


def _pairs(h):
    return re.findall(r'<span class="ph-en">(.*?)</span><span class="ph-zh">(.*?)</span>', h or "", re.S)


def _clean_zh(z):
    z = re.sub(r"^\s*(n|v|vt|vi|adj|adv|prep|pron|conj|num|art)\.\s*", "", z or "")
    return re.sub(r"\s{2,}", " ", z).strip()


def trim_phr(h, w, limit=5):
    scored = []
    for en, zh in _pairs(h):
        en_p, zh_p = strip_tags(en).strip(), _clean_zh(strip_tags(zh))
        if not en_p or not zh_p:
            continue
        ok, zh_cut = P0.colloc_ok(en_p, zh_p)   # P0-3：伪搭配/领域长串/释义截12字
        if not ok:
            continue
        zh_p = zh_cut
        if re.search(r"\[口\]|\[俚\]|\[古\]|\[方\]|\[军\]|\[律\]", zh_p):
            continue
        toks = en_p.lower().split()
        if len(toks) > 1 and toks[1] in ("some", "any", "other", "such", "more", "less", "this", "that", "these", "those"):
            continue
        sc = 0
        if toks and toks[0] == w.lower():
            sc += 2
        if 2 <= len(toks) <= 3:
            sc += 2
        elif len(toks) > 4:
            sc -= 2
        if len(zh_p) <= 12:
            sc += 1
        elif len(zh_p) > 25:
            sc -= 2
        scored.append((sc, en_p, zh_p))
    scored.sort(key=lambda x: -x[0])
    seen, out = set(), []
    kept = []
    for sc, en, zh in scored:
        k = en.lower()
        if k in seen:
            continue
        if any(k.startswith(x) or x.startswith(k) for x in kept):
            continue
        seen.add(k)
        kept.append(k)
        out.append((en, zh))
        if len(out) >= limit:
            break
    return "".join(f'<div class="ph"><span class="ph-en">{P0.esc(e)}</span>'
                   f'<span class="ph-zh">{P0.esc(z)}</span></div>' for e, z in out)


def trim_rel(h, limit=5):
    order, mm = [], {}
    for en, zh in _pairs(h):
        k = strip_tags(en).strip()
        if not k:
            continue
        if k not in mm:
            mm[k] = []
            order.append(k)
        z = _clean_zh(strip_tags(zh))
        if z and z not in mm[k]:
            mm[k].append(z)
    return "".join(f'<div class="ph"><span class="ph-en">{P0.esc(k)}</span>'
                   f'<span class="ph-zh">{P0.esc("；".join(mm[k]))}</span></div>' for k in order[:limit])


def memory_html(w, h):
    rows = []
    syl = syll_of(w, h)
    if syl and P0.syll_ok(syl, w):          # P0-4：音节切分 == 单词本身 → 无信息，不渲染
        rows.append(f'<div class="mrow"><span class="mk">音节</span><span class="mv syll">{P0.esc(syl)}</span></div>')
    mn = mnemonic_html(w, h)
    if mn:
        inner = re.sub(r'^<div class="mn">|</div>$', '', mn)
        rows.append(f'<div class="mrow"><span class="mk">助记</span><span class="mv">{inner}</span></div>')
    rt = root_html(w, h)
    rt_plain = strip_tags(rt or "").strip()
    if rt and len(rt_plain) >= 4 and P0.root_ok(rt_plain, w):
        inner = re.sub(r'^<div class="(rx|rt)">|</div>(<div class="rt">.*)?$', '', rt, flags=re.S)
        rows.append(f'<div class="mrow"><span class="mk">词根</span><span class="mv">{inner}</span></div>')
    return "".join(rows)


CORE_OVERRIDE = {
    # COCA 首位义 = 遗憾(49%)，词典 n. 遗憾，惋惜 与之完全对应；
    # v. 的「对…感到抱歉」只是同义长表述，机器匹配分不清，这里人工定死。
    "regret": ("n.", "遗憾，惋惜"),
}


def build(word):
    w = word.lower()
    p = plan[w]
    h = hbs.get(w)
    common, full, core = simplify(p, word=w)
    if w in CORE_OVERRIDE:
        ov_pos, ov_txt = CORE_OVERRIDE[w]
        core = f'<span class="pos">{P0.esc(ov_pos)}</span>{P0.esc(ov_txt)}'
    exam = pick_exam(w, 2 if (len(w) >= 9 or common.count("<br>") >= 3) else 1)
    qual = pick_quality(w, 1)
    for lst in (exam, qual):
        for e in lst:
            e["zh"] = _zh_for(e["en"], e.get("zh", ""))
    a = amap.get(str(p["id"]), {})
    return {
        "单词": p["word"],
        "音节": syll_of(w, h),
        "音标英": ipa_clean(p["音标"]), "音标美": ipa_clean(p["音标美"]),
        "发音英": f'[sound:{a["uk"]}]' if a.get("uk") else "",
        "发音美": f'[sound:{a["us"]}]' if a.get("us") else "",
        "核心义": core,
        "考频": badge(w, p, h),
        "常用义项": common,
        "英英释义": trim_en(p["英文释义"], core) if en_ok(p["英文释义"]) else collins_en(w, p),
        "真题例句": ex_html(exam, "exam"),
        "高质量例句": ex_html(qual, "qual"),
        "词根": root_html(w, h),
        "词源": etym_html(w, h),
        "助记": memory_html(w, h),
        "辨析": discrim_html(w, h),
        "柯林斯": p["柯林斯解释"],
        "搭配": trim_phr(p.get("词组", ""), w, 5),
        "同根词": trim_rel(p.get("同根词", ""), 5),
        "全义项": (full[:450] + " …" if len(full) > 450 else full),
    }


if __name__ == "__main__":
    for w in sys.argv[1:]:
        f = build(w)
        print("=" * 30, w)
        for k, v in f.items():
            if k in ("柯林斯", "全义项"):
                v = (v or "")[:150]
            print(f"  {k}: {v}")
