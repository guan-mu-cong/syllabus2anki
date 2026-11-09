# Vendored from the private production pipeline (syllabus2anki M2).
# Logic is UNCHANGED except the WS data-dir override via S2A_DATA_DIR,
# so regression output is byte-identical to production. See docs/pipeline.md.
# -*- coding: utf-8 -*-
"""
全量建卡引擎（v4）

与 build_v3.build() 的区别：
  · 以 entries_7619.json 为词表驱动（官方 7809 条目，一卡一条）
  · 复用 build_v3 的所有字段生成与 P0 清洗
  · 新增：变体拼写标注（center（英 centre））、官方 ★ 星级
  · 新增：缺数据时的优雅降级（新词可能没有 hbs/engra 记录）
  · 数据源：plan.json（旧词）/ yd_cache（新词，走 ydparse 现场解析）

输出：cards.json（每张卡的 21 字段 + 排序键）
"""
import json, os, re, sys, html

WS = os.environ.get("S2A_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, WS)
import p0_clean as P0
import ydparse
import build_v3 as B

ENTRIES = json.load(open(os.path.join(WS, "entries_7619.json"), encoding="utf-8"))["entries"]

# 音频映射：audio_map2.json 按单词索引（p2_audio.py 产出，覆盖全量 7809 词）
# 旧的 audio_map.json 只按 plan.json 的 id 索引且仅 5278 项，不足以覆盖全量
_AUDIO2_PATH = os.path.join(WS, "audio_map2.json")
AUDIO2 = json.load(open(_AUDIO2_PATH, encoding="utf-8")) if os.path.exists(_AUDIO2_PATH) else {}


def canon(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def find_plan(word, variants):
    """在旧 plan.json 里找这张卡的数据源"""
    for cand in [word] + list(variants):
        p = B.plan.get((cand or "").lower())
        if p:
            return p
        k = canon(cand)
        for pw, pp in B.plan.items():
            if canon(pw) == k:
                return pp
    return None


def synthetic_plan(word):
    """新词：从 yd_cache 现解析出与 plan.json 同构的记录"""
    d = ydparse.load(word)
    if d is None:
        # 变体拼写试一次
        return None
    uk, us = ydparse.ipa(d)
    star, col = ydparse.collins(d)
    return {
        "id": "yd:" + word,
        "word": word,
        "音标": uk,
        "音标美": us,
        "释义": "",
        "释义详": ydparse.senses(d),
        "柯林斯星级": star,
        "柯林斯解释": col,
        "英文释义": ydparse.en_def(d),
        "例句": "",
        "例句翻译": "",
        "词组": ydparse.phrases(d, limit=6),
        "同根词": ydparse.rels(d, limit=6),
        "audio_old": "",
        "uk_speech": ydparse.speech(d)[0],
        "us_speech": ydparse.speech(d)[1],
        "_from": "yd",
    }


def variant_note(word, variants):
    """center（英 centre）这样的标注；只在有变体时出现"""
    if not variants:
        return ""
    vs = [v for v in variants if v.lower() != word.lower()]
    if not vs:
        return ""
    return "／".join(vs[:3])


def build_card(e):
    word = e["word"]
    variants = e.get("variants") or []
    p = find_plan(word, variants)
    # plan.json 里有些词的释义被旧解析器清空了（june/river/camera…）→ 回落到 yd_cache 现解析
    if p is not None and not (p.get("释义详") or "").strip():
        syn = synthetic_plan(p["word"])
        if syn and (syn.get("释义详") or "").strip():
            syn["id"] = p["id"]
            syn["word"] = p["word"]
            p = syn
    if p is None:
        p = synthetic_plan(word)
    # 错拼变体（jewelery/instalation）自己查不到释义 → 借官方正确拼写那份
    if p is not None and not (p.get("释义详") or "").strip():
        for v in variants:
            sp = synthetic_plan(v)
            if sp and (sp.get("释义详") or "").strip():
                sp["word"] = word
                sp["id"] = p.get("id") or ("yd:" + word)
                p = sp
                break
    if p is None:
        return {"word": word, "error": "无数据源"}

    w = p["word"].lower()
    f = B.build(w) if not p.get("_from") else _build_from_synthetic(p, w)

    # 官方星级覆盖（方案 §1：以官方 ★ 为准）
    f["柯林斯星级"] = "★★★" if e["star"] else ""
    f["官方★"] = "1" if e["star"] else ""
    f["变体"] = variant_note(word, variants)
    f["官方拼写"] = e["official"]
    f["排序键"] = sort_key(e)
    # 音频：统一以 audio_map2.json（按单词索引，7809 项）为准
    # 旧 amap 是按 plan.json 的 id 索引且只有 5278 项，
    # 全量新增的 2532 个词拿不到音频，会让 cards.json 与 Anki 实卡不一致。
    # 注意：audio_map2 的键保留原始大小写（Catholic / January / X-ray），
    # 只按小写查会漏掉全部专有名词（48 个词）→ 三种写法都试。
    a = {}
    for cand in (word, word.lower(), word.capitalize(), *variants):
        a = AUDIO2.get(cand) or {}
        if a.get("us") or a.get("uk"):
            break
    f["发音英"] = f'[sound:{a["uk"]}]' if a.get("uk") else ""
    f["发音美"] = f'[sound:{a["us"]}]' if a.get("us") else ""
    return f


def _build_from_synthetic(p, w):
    """新词走一遍与 build_v3.build 相同的渲染管线（monkeypatch plan）"""
    old = B.plan.get(w)
    B.plan[w] = p
    try:
        return B.build(w)
    finally:
        if old is None:
            B.plan.pop(w, None)
        else:
            B.plan[w] = old


def sort_key(e):
    """新卡顺序（方案 §3）：★ → 真题高频非★ → 四级基础高频 → 派生词"""
    w = e["word"].lower()
    if e["star"]:
        tier = 0
    elif B.corpus.get(w):
        tier = 1
    elif len(w) <= 7:
        tier = 2
    else:
        tier = 3
    # 派生词（高频后缀且去掉后缀仍有 4 字以上）只在前两档内再往后压一档
    DERIV = ("tion", "sion", "ness", "ment", "ity", "ally", "ous", "ive", "ly", "al")
    if tier in (2, 3) and any(w.endswith(s) and len(w) - len(s) >= 4 for s in DERIV):
        tier = min(tier + 1, 4)
    try:
        from wordfreq import zipf_frequency
        z = zipf_frequency(w, "en")
    except Exception:
        z = 0.0
    return f"{tier}{round(9 - z, 1):04.1f}"


def main():
    cards, errs = [], []
    for i, e in enumerate(ENTRIES):
        c = build_card(e)
        if c.get("error"):
            errs.append((e["word"], c["error"]))
        else:
            c["_idx"] = i
            cards.append(c)
        if (i + 1) % 500 == 0:
            print(f"{i+1}/{len(ENTRIES)} 卡片={len(cards)} 错误={len(errs)}", flush=True)
    cards.sort(key=lambda c: (c["排序键"], c["单词"].lower()))
    json.dump(cards, open(os.path.join(WS, "cards.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("建卡完成:", len(cards), "错误:", len(errs))
    print("错误样例:", errs[:15])
    json.dump(errs, open(os.path.join(WS, "build_errors.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
