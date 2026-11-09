# Vendored from the private production pipeline (syllabus2anki).
# Logic UNCHANGED except: (1) WS data-dir override via S2A_DATA_DIR,
# (2) tolerant/overridable data-file loads (S2A_ENTRIES / S2A_AUDIO_MAP_OUT).
# Regression-verified byte-identical against production outputs. See docs/pipeline.md.
import os
import json, os, re, html

WS = os.environ.get("S2A_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(WS, "yd_cache")


def safe(w):
    return w.replace("/", "_").replace("\\", "_").replace(":", "_")


def load(w):
    p = os.path.join(CACHE, safe(w) + ".json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return None
    # 官方词表里斜杠/括号合并后的词条可能去掉了空格（accordingto、oughtto、babyboom）
    for cand in (re.sub(r"\s+", " ", w), re.sub(r"\s+", "", w)):
        p2 = os.path.join(CACHE, safe(cand) + ".json")
        if os.path.exists(p2):
            try:
                return json.load(open(p2, encoding="utf-8"))
            except Exception:
                return None
    return None


def _txt(x):
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return "".join(_txt(i) for i in x)
    if isinstance(x, dict):
        if "i" in x:
            return _txt(x["i"])
        for k in ("l", "tr", "headword", "word"):
            if k in x:
                return _txt(x[k])
        return ""
    return ""


def _pos_span(s):
    m = re.match(r"^([a-zA-Z/\.\s]{1,12}?)\s+(.+)$", s)
    if m and re.search(r"[a-zA-Z]", m.group(1)):
        return f'<span class="pos">{html.escape(m.group(1).strip())}</span>{html.escape(m.group(2))}'
    return html.escape(s)


def ipa(d):
    ec = d.get("ec") or {}
    w = ec.get("word") or []
    w = w[0] if isinstance(w, list) and w else (w if isinstance(w, dict) else {})
    uk = (w.get("ukphone") or "").strip()
    us = (w.get("usphone") or "").strip()
    if not uk and not us:
        for k in ("simple", "phrs"):
            o = d.get(k) or {}
            if isinstance(o, dict):
                uk = uk or (o.get("ukphone") or "")
                us = us or (o.get("usphone") or "")
    return uk, us


def speech(d):
    ec = d.get("ec") or {}
    w = ec.get("word") or []
    w = w[0] if isinstance(w, list) and w else (w if isinstance(w, dict) else {})
    return (w.get("ukspeech") or "").strip(), (w.get("usspeech") or "").strip()


def senses(d):
    ec = d.get("ec") or {}
    w = ec.get("word") or []
    w = w[0] if isinstance(w, list) and w else (w if isinstance(w, dict) else {})
    out = []
    for grp in w.get("trs") or []:
        for tr in grp.get("tr") or []:
            lv = tr.get("l", {})
            iv = lv.get("i", "") if isinstance(lv, dict) else ""
            # 有道新版把释义放在 list 里（i: ["n. 六月；琼（人名）"]），旧版是带 \n 的字符串
            chunks = iv if isinstance(iv, list) else [iv]
            for chunk in chunks:
                for s in _txt(chunk).split("\n"):
                    s = s.strip()
                    if not s or s.startswith("【名】"):
                        continue
                    out.append(_pos_span(s))
    # dedupe
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s); uniq.append(s)
    return "<br>".join(uniq)


def collins(d):
    c = d.get("collins") or {}
    ents = c.get("collins_entries") or []
    if not ents:
        return "", ""
    e0 = ents[0]
    try:
        star = int(e0.get("star") or 0)
    except Exception:
        star = 0
    blocks = []
    for e in ents:
        for ent in (e.get("entries") or {}).get("entry", []) or []:
            for te in ent.get("tran_entry") or []:
                pe = te.get("pos_entry") or {}
                pos = (pe.get("pos") or "").strip()
                tip = (pe.get("pos_tips") or "").strip()
                tran = (te.get("tran") or "").strip()
                if not tran:
                    continue
                h = '<div class="ce">'
                if pos:
                    h += f'<div class="ce-pos">{html.escape(pos)}<span class="ce-tip">{html.escape(tip)}</span></div>'
                h += f'<div class="ce-def">{tran}</div>'
                sents = ((te.get("exam_sents") or {}).get("sent") or [])[:1]
                for s in sents:
                    en = (s.get("eng_sent") or "").strip()
                    zh = (s.get("chn_sent") or "").strip()
                    if en:
                        h += f'<div class="ce-ex">{en}<br><span class="zh">{zh}</span></div>'
                h += "</div>"
                blocks.append(h)
    return ("★" * star + "☆" * max(0, 5 - star)) if star else "", "".join(blocks[:6])


def en_def(d):
    ee = d.get("ee") or {}
    w = ee.get("word") or {}
    trs = w.get("trs") or []
    out = []
    for g in trs:
        pos = (g.get("pos") or "").strip()
        items = [html.escape(_txt(t.get("l", {})).strip()) for t in (g.get("tr") or [])[:4]]
        items = [i for i in items if i]
        if items:
            pre = f'<span class="pos">{html.escape(pos)}</span>' if pos else ""
            out.append(pre + "；".join(items))
    if not out:
        # fallback: first collins english definition, stripped
        c = d.get("collins") or {}
        for e in (c.get("collins_entries") or [])[:1]:
            for ent in (e.get("entries") or {}).get("entry", []) or []:
                for te in (ent.get("tran_entry") or [])[:1]:
                    t = re.sub(r"<[^>]+>", "", te.get("tran") or "").strip()
                    if t:
                        out.append(html.escape(t))
    return "<br>".join(out)


def examples(d, word, limit=3):
    pairs = ((d.get("blng_sents_part") or {}).get("sentence-pair") or [])
    cands = []
    wl = word.lower()
    for p in pairs:
        en = re.sub(r"<[^>]+>", "", p.get("sentence-eng") or p.get("sentence") or "").strip()
        zh = (p.get("sentence-translation") or "").strip()
        if not en or not zh:
            continue
        n = len(en.split())
        if n < 5 or n > 32:
            continue
        score = (2 if wl in en.lower() else 0) + (1 if n <= 22 else 0)
        cands.append((score, en, zh))
    cands.sort(key=lambda x: -x[0])
    out = []
    for sc, en, zh in cands:
        if sc < 1:
            continue
        out.append((html.escape(en), html.escape(zh)))
        if len(out) >= limit:
            break
    return out


def phrases(d, limit=6):
    ph = ((d.get("phrs") or {}).get("phrs") or [])
    out = []
    for p in ph:
        o = p.get("phr") or {}
        head = _txt(o.get("headword", {})).strip()
        zh = "；".join(_txt(t.get("tr", {})).strip() for t in (o.get("trs") or [])).strip("；")
        if head and zh and head.lower() != "":
            out.append(f'<div class="ph"><span class="ph-en">{html.escape(head)}</span><span class="ph-zh">{html.escape(zh)}</span></div>')
        if len(out) >= limit:
            break
    return "".join(out)


def rels(d, limit=6):
    r = d.get("rel_word") or {}
    out = []
    for g in (r.get("rels") or []):
        o = g.get("rel") or {}
        for wd in (o.get("words") or [])[:limit]:
            word = (wd.get("word") or "").strip()
            tr = (wd.get("tran") or "").strip()
            if word:
                out.append(f'<div class="ph"><span class="ph-en">{html.escape(word)}</span><span class="ph-zh">{html.escape(tr)}</span></div>')
    return "".join(out[:limit])
