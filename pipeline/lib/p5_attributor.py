# -*- coding: utf-8 -*-
"""
Vendored from the private production pipeline (syllabus2anki, stage 05b).
Logic UNCHANGED except configuration: all personal paths / credential file
reads replaced by S2A_* environment variables (see docs/pipeline.md):
  S2A_DATA_DIR, S2A_CARDS, S2A_AUDIT,
  S2A_LLM_API_KEY, S2A_LLM_URL, S2A_LLM_MODELS, S2A_NO_LLM

p5 sense-bold attribution (v5 card spec):
1) parse 常用义项 into numbered sense lines (pos + clean tokens)
2) 真题例句 -> (en, zh) pairs; drop exam directions / stem-less sentences
3) valid examples present -> LLM final judgement; rule hits are candidates only
4) no examples + frequency-tier word -> bold first clean token of sense 1;
   exam-tier word without valid examples -> leave blank (honest > forced)
5) append one audit record per word to AUDIT jsonl (resume = skip words present)

Usage: python -m p5_attributor --limit N --workers K [--all]
"""
import json, re, os, sys, time, argparse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

WS = os.environ.get("S2A_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
CARDS = os.environ.get("S2A_CARDS") or os.path.join(WS, "cards.json")
AUDIT = os.environ.get("S2A_AUDIT") or os.path.join(WS, "attributor_audit.jsonl")

API_KEY = os.environ.get("S2A_LLM_API_KEY", "")
API_URL = os.environ.get("S2A_LLM_URL",
                         "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
MODELS = [m.strip() for m in os.environ.get(
    "S2A_LLM_MODELS", "qwen3.8-flash,qwen-flash,qwen-turbo,qwen-plus").split(",") if m.strip()]
NO_LLM = os.environ.get("S2A_NO_LLM", "") not in ("", "0")
_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

STOP = set("的了是在和与或等把被将从对以之其有没这那要就都还很更最被给让做作")
INSTR = re.compile(r"本部分|你将听到|听下面|回答问题|Directions|Section\s+[A-D]|^\s*[A-D]\)", re.I)

def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "")

def parse_senses(html):
    """-> [(pos, raw_line_without_pos, [clean_tokens])]"""
    out = []
    for ln in (html or "").split("<br>"):
        m = re.search(r'class="pos">([^<]+)</span>(.*)', ln)
        pos, body = (m.group(1), m.group(2)) if m else ("", ln)
        body = strip_html(body).strip()
        toks = []
        for t in re.split(r"[；，,、]", body):
            t = re.sub(r"[（(][^）)]*[)）]", "", t)
            t = re.sub(r"〔[^〕]*〕", "", t).strip()
            if len(re.findall(r"[\u4e00-\u9fff]{2,}", t)) and not re.fullmatch(r"[\u4e00-\u9fff]*", t.replace("……", "")) == "":
                pass
            if re.search(r"[\u4e00-\u9fff]{2,}", t):
                toks.append(t)
        if body:
            out.append((pos, body, toks))
    return out

def ex_pairs(html):
    """真题例句 -> [(en, zh)]，剔除 en 不含词干或 zh 为指令行的"""
    if not html:
        return []
    items = []
    for it in re.split(r'<div class="ex-item">', html)[1:]:
        en = re.search(r'class="en">([^<]+)<', it)
        zh = re.search(r'class="zh">([^<]+)<', it)
        if en and zh:
            items.append((en.group(1).strip(), zh.group(1).strip()))
    return items

def valid_examples(word, items):
    stem = re.escape(word[:max(3, len(word) - 2)])
    keep = []
    for en, zh in items:
        if not re.search(r"(?i)\b\w*" + stem + r"\w*\b", en):
            continue
        if INSTR.search(zh) or len(zh) < 6:
            continue
        keep.append((en, zh))
    return keep[:2]

def llm(word, senses, exs, model):
    lines = "\n".join("%d. [%s] %s" % (i + 1, p or "?", b) for i, (p, b, _) in enumerate(senses))
    ex = "\n".join("- EN: %s\n  ZH: %s" % (e, z) for e, z in exs)
    sysm = ("你是CET-6词汇真题义项归因器。给定单词、它在真题中的英中例句、编号义项列表。"
            "判断例句中该词表达哪条（些）义项。只输出JSON："
            '{"senses":[编号],"tokens":["要加粗的最小中文词",...],"confidence":"high|low",'
            '"reason":"不超过25字"}。规则：译文意译时按语义就近归因；tokens必须是所编号义项文本中出现的原词'
            "（不含括号修饰与词性），最多2个，与senses对应；例句语义明显不属于任何义项、或无法确定时，"
            'senses=[]且confidence=low。不要硬凑。')
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 300,
                       "enable_thinking": False,
                       "messages": [{"role": "system", "content": sysm},
                                    {"role": "user", "content": "word: %s\n义项:\n%s\n例句:\n%s" % (word, lines, ex)}]},
                      ensure_ascii=False).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"})
    r = json.loads(_proxy_opener.open(req, timeout=60).read().decode())
    txt = r["choices"][0]["message"]["content"].strip().strip("`")
    txt = re.sub(r"^json\s*", "", txt)
    out = json.loads(txt)
    if not isinstance(out, dict):
        raise ValueError("非对象返回: %s" % str(out)[:60])
    return out

def call_llm(word, senses, exs):
    if NO_LLM or not API_KEY:
        return {"senses": [], "tokens": [], "confidence": "low",
                "reason": "LLM disabled (S2A_NO_LLM=1)" if NO_LLM else "S2A_LLM_API_KEY not set"}
    last = None
    for attempt in range(3):
        for model in MODELS:
            try:
                return llm(word, senses, exs, model)
            except Exception as e:
                last = e
                time.sleep(1 + attempt)
    return {"senses": [], "tokens": [], "confidence": "low", "reason": "LLM失败:%s" % str(last)[:40]}

def apply_bold(senses_html, picks):
    """picks: [(sense_idx, token)]；在对应 <br> 行内替换首个 token，返回新 html"""
    lines = senses_html.split("<br>")
    done = 0
    for idx, tok in picks:
        if idx >= len(lines) or tok not in lines[idx] or done >= 2:
            continue
        # 行内已有同词加粗则跳过
        if '<b class="xt">%s</b>' % tok in lines[idx]:
            continue
        lines[idx] = lines[idx].replace(tok, '<b class="xt">%s</b>' % tok, 1)
        done += 1
    return "<br>".join(lines)

def process(word, c):
    try:
        return _process(word, c)
    except Exception as e:
        return {"w": word, "strategy": "error-blank", "picks": [], "conf": "low", "note": str(e)[:60]}

def _process(word, c):
    senses = parse_senses(c.get("常用义项", ""))
    items = valid_examples(word, ex_pairs(c.get("真题例句", "")))
    rec = {"w": word, "strategy": "", "picks": [], "conf": "", "note": ""}
    if senses:
        if items:
            r = call_llm(word, senses, items)
            conf = r.get("confidence", "low")
            picks = []
            for s, t in zip(r.get("senses", []), r.get("tokens", [])):
                try:
                    i = int(s) - 1
                except Exception:
                    continue
                if 0 <= i < len(senses) and t and t in senses[i][1]:
                    picks.append((i, t))
            if conf == "high" and picks:
                rec.update(strategy="llm", picks=picks, conf=conf, note=r.get("reason", ""))
            else:
                rec.update(strategy="llm-blank", picks=[], conf=conf, note=r.get("reason", ""))
        else:
            if "词频" in (c.get("考频", "") or ""):
                toks = senses[0][2]
                rec.update(strategy="freq-default", picks=[(0, toks[0])] if toks else [], conf="rule",
                           note="★词频层无有效例句,默认粗首条")
            else:
                rec.update(strategy="blank-novalidex", picks=[], conf="rule", note="真题层但例句均无效(指令/不含词干)")
    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    data = json.load(open(CARDS, encoding="utf-8"))
    cards = [(strip_html(c["单词"]).strip().lower(), c) for c in data]
    done = set()
    if os.path.exists(AUDIT):
        for ln in open(AUDIT, encoding="utf-8"):
            try:
                done.add(json.loads(ln)["w"])
            except Exception:
                pass
    todo = [(w, c) for w, c in cards if w not in done]
    todo = todo[: (None if a.all else a.limit)]
    print("总:%d 已归因:%d 本轮:%d" % (len(cards), len(done), len(todo)))
    t0 = time.time()
    n = 0
    with open(AUDIT, "a", encoding="utf-8") as fo, ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(process, w, c): w for w, c in todo}
        for f in as_completed(futs):
            rec = f.result()
            rec["picks"] = [[i, t] for i, t in rec["picks"]]
            fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush()
            n += 1
            if n <= a.limit or n % 200 == 0:
                print(n, rec["w"], rec["strategy"], rec["picks"], rec["conf"], rec["note"][:30])
    print("done %s in %.1fs" % (n, time.time() - t0))

if __name__ == "__main__":
    main()
