# -*- coding: utf-8 -*-
"""
Vendored from the private production pipeline (syllabus2anki, stage 05c).
Logic UNCHANGED except configuration via S2A_* env vars:
  S2A_DATA_DIR, S2A_CARDS, S2A_AUDIT, S2A_CARDS_FINAL_OUT

p6 finalizer: bake the attribution audit (05b) into the final card records —
bold the attributed sense tokens (<b class="xt">) inside 常用义项 and drop the
核心义 field (v5 card spec: core sense lives in the bolded sense list).
Deterministic and offline: same inputs -> byte-identical output.
"""
import json, os, re, sys

WS = os.environ.get("S2A_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
CARDS = os.environ.get("S2A_CARDS") or os.path.join(WS, "cards.json")
AUDIT = os.environ.get("S2A_AUDIT") or os.path.join(WS, "attributor_audit.jsonl")
OUT = os.environ.get("S2A_CARDS_FINAL_OUT") or os.path.join(WS, "cards_final.json")


def main():
    audit = {}
    for ln in open(AUDIT, encoding="utf-8"):
        r = json.loads(ln)
        audit[r["w"].lower()] = r

    data = json.load(open(CARDS, encoding="utf-8"))
    strip = lambda s: re.sub(r"<[^>]+>", "", s or "").strip()

    stats = {"llm": 0, "llm-blank": 0, "freq-default": 0, "blank-novalidex": 0, "missing": 0}
    bold_total = 0
    out = []
    for c in data:
        w = strip(c["单词"]).lower()
        c = dict(c)
        c.pop("核心义", None)
        a = audit.get(w)
        if not a:
            stats["missing"] += 1
        else:
            stats[a["strategy"]] = stats.get(a["strategy"], 0) + 1
            lines = c["常用义项"].split("<br>")
            used = 0
            for idx, tok in (a["picks"] or []):
                if used >= 2 or idx >= len(lines):
                    continue
                if tok in lines[idx] and '<b class="xt">%s</b>' % tok not in lines[idx]:
                    lines[idx] = lines[idx].replace(tok, '<b class="xt">%s</b>' % tok, 1)
                    used += 1
            c["常用义项"] = "<br>".join(lines)
            bold_total += used
        out.append(c)

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    n = len(out)
    print("卡数:", n)
    print("策略分布:", json.dumps(stats, ensure_ascii=False))
    print("加粗处数:", bold_total, "| 平均每卡:", round(bold_total / n, 2))
    print("无任何加粗占比:", round((n - bold_total) / n * 100, 1), "%")
    print("输出:", OUT)


if __name__ == "__main__":
    main()
