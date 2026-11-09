#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
07_audit.py — QA gates + layered report (stage 07).

Two modes:
  file  audit a card-records JSON (stage 05 or 05c output) — offline
  anki  audit the LIVE deck through AnkiConnect (read-only) + media
        reference/reality two-way diff against the collection.media folder

Gates (file mode):
  G1 residue      HTML entities, control chars, template junk in any field
  G2 structure    example numbering leftovers, phrase-pair sanity (count,
                  pseudo-phrase, over-long zh, domain tags), memory-block and
                  syllable-split shape, required fields present
  G3 coverage     non-empty rate per field, official-star count, duplicates
  G4 semantic     (only when 核心义 exists and a COCA-frequency index is
                  available) core-sense vs COCA top sense agreement, exam
                  examples supporting the core sense, example length stats,
                  mnemonic provenance

anki mode runs G1/G3 on live note fields, extracts [sound:] refs and diffs
them against the media folder (missing = broken playback, orphans = wasted
space).

Exit codes: 0 pass, 1 hard failure (residues / duplicates / missing media
refs), 2 warnings only.

Usage:
  python 07_audit.py --config config.local.yaml file --cards work/cards_final.json
  python 07_audit.py --config config.local.yaml anki --media-dir "C:/.../collection.media"
"""
import argparse
import collections
import json
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import p0_clean as P0  # noqa: E402  (pure module, no data deps)

COVERAGE_FIELDS = ["核心义", "常用义项", "英英释义", "真题例句", "高质量例句", "搭配", "同根词",
                   "助记", "词根", "词源", "辨析", "柯林斯", "考频", "音节", "音标美", "音标英",
                   "发音美", "发音英"]
SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")


def _resolve(base, p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def plain(h):
    return re.sub(r"<[^>]+>", "", h or "").strip()


class Report:
    def __init__(self):
        self.stat = collections.Counter()
        self.samples = collections.defaultdict(list)
        self.hard = False
        self.warn = False

    def bad(self, key, w, detail="", hard=False, warn=True):
        self.stat[key] += 1
        if hard:
            self.hard = True
        if warn:
            self.warn = True
        if len(self.samples[key]) < 6:
            self.samples[key].append(f"{w} {detail}".strip())

    def dump(self, title, n):
        print(f"\n=== {title} (n={n}) ===")
        if not self.stat:
            print("  clean — no findings")
        for k, v in sorted(self.stat.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v} ({v * 100 / max(n, 1):.2f}%)")
            for s in self.samples[k][:3]:
                print(f"      · {s[:100]}")


def gate_fields(rep, rec, word, hard_residue=True):
    """G1 + G2 on one record (dict of field->html str)."""
    for k, v in rec.items():
        if isinstance(v, str) and P0.has_residue(v):
            rep.bad("G1 实体残留:" + k, word, hard=hard_residue)
    for k in ("真题例句", "高质量例句"):
        if 'class="num"' in (rec.get(k) or ""):
            rep.bad("G2 例句数字编号", word)
    pairs = re.findall(r'<span class="ph-en">(.*?)</span><span class="ph-zh">(.*?)</span>',
                       rec.get("搭配") or "", re.S)
    if "搭配" in rec and not pairs:
        rep.bad("G2 无搭配", word)
    if len(pairs) > 5:
        rep.bad("G2 搭配>5条", word, str(len(pairs)))
    for en, zh in pairs:
        t = en.lower().split()
        if len(t) == 2 and t[1] in P0.VIRT:
            rep.bad("G2 伪搭配", word, en)
        if len(zh) > 12:
            rep.bad("G2 搭配中文>12字", word, zh)
        if P0.DOMAIN.search(zh):
            rep.bad("G2 搭配含领域标记", word, zh)
    mem = rec.get("助记") or ""
    mks = re.findall(r'<span class="mk">(.*?)</span>', mem)
    if mem.strip() and mks and "助记" not in mks:
        rep.bad("G2 记忆块无真助记", word)
    m = re.search(r'<span class="mv syll">(.*?)</span>', mem)
    if m and len([x for x in re.split(r"[·\-]", m.group(1)) if x.strip()]) < 2:
        rep.bad("G2 音节未切分", word)
    if "核心义" in rec and not (rec.get("核心义") or "").strip():
        rep.bad("G2 缺核心义", word, hard=True)
    if "常用义项" in rec and not (rec.get("常用义项") or "").strip():
        rep.bad("G2 缺常用义项", word, hard=True)
    if "音标美" in rec and not (rec.get("音标美") or rec.get("音标英") or "").strip():
        rep.bad("G2 缺音标", word)
    if "核心义" in rec and len(plain(rec.get("核心义"))) > 40:
        rep.bad("G2 核心义过长", word, plain(rec.get("核心义"))[:40])
    for blk in re.findall(r'<div class="ex-item">(.*?)</div>(?=<div class="ex-item">|$)',
                          rec.get("真题例句") or "", re.S):
        if "真题" in blk and 'class="zh"' not in blk:
            rep.bad("G2 真题例句缺译文", word)
            break


def gate_coverage(rep, records):
    n = len(records)
    print("\n=== G3 覆盖率 ===")
    for k in COVERAGE_FIELDS:
        if not any(k in c for c in records[:50]):
            continue
        cnt = sum(1 for c in records if str(c.get(k) or "").strip())
        print(f"  {k}: {cnt}/{n} ({cnt * 100 // max(n, 1)}%)")
    star = sum(1 for c in records if str(c.get("官方★") or "").strip())
    print(f"  官方★: {star}   变体标注: {sum(1 for c in records if str(c.get('变体') or '').strip())}")
    words = [plain(c.get("单词", "")).lower() for c in records]
    dup = {w: v for w, v in collections.Counter(words).items() if v > 1}
    if dup:
        rep.bad("G3 重复单词", ",".join(list(dup)[:5]), str(len(dup)), hard=True)
    else:
        print("  重复单词: 0")


def gate_semantic(records, data_dir):
    """G4: needs 核心义 (v4 records) + hbs COCA index. Skipped otherwise."""
    hbs_p = os.path.join(data_dir, "hbs_index.json") if data_dir else None
    if not any("核心义" in c for c in records[:50]) or not hbs_p or not os.path.exists(hbs_p):
        print("\n=== G4 语义闸：跳过（无核心义字段或无 COCA 索引）===")
        return
    hbs = json.load(open(hbs_p, encoding="utf-8"))
    print("\n=== G4 语义闸 ===")
    have = [c for c in records if (hbs.get(plain(c.get("单词", "")).lower()) or {}).get("coca")]
    ok = part = bad = 0
    for c in have:
        w = plain(c.get("单词", "")).lower()
        coca = hbs[w]["coca"]
        m = re.match(r"([^，(（]+)\((\d+)%?\)", coca)
        if not m:
            continue
        top = m.group(1).strip()
        core_body = re.sub(r"^[a-z]+\.", "", plain(c.get("核心义"))).strip()
        if not core_body:
            continue
        if top and top in core_body:
            ok += 1
        elif any(t and t in core_body for t in re.findall(r"([^，(（]+)\(", coca)):
            part += 1
        else:
            bad += 1
    tot = ok + part + bad
    print(f"  A 核心义=COCA最常用义: 一致 {ok} 部分 {part} 不一致 {bad} (n={tot})")
    L = []
    for c in records:
        for k in ("真题例句", "高质量例句"):
            for b in re.findall(r'<div class="ex-item">(.*?)</div>', c.get(k) or "", re.S):
                en = re.search(r'<span class="en">(.*?)</span>', b, re.S)
                if en:
                    L.append(len(plain(en.group(1)).split()))
    if L:
        L.sort()
        print(f"  C 例句长度: n={len(L)} min={L[0]} med={L[len(L) // 2]} max={L[-1]} "
              f">45词={sum(1 for x in L if x > 45)} <5词={sum(1 for x in L if x < 5)}")
    n_mem = sum(1 for c in records if (c.get("助记") or "").strip())
    n_ai = sum(1 for c in records if "AI 助记" in (c.get("助记") or ""))
    n_eng = sum(1 for c in records if "engra" in (c.get("助记") or ""))
    print(f"  D 助记: 有记忆块 {n_mem} (AI {n_ai} / engra {n_eng} / 其他 {n_mem - n_ai - n_eng})")


def cmd_file(a, args):
    base = a.base
    cfg = a.cfg.get("audit") or {}
    cards_p = _resolve(base, args.cards or cfg.get("cards", "work/cards_final.json"))
    records = json.load(open(cards_p, encoding="utf-8"))
    print(f"audit file: {cards_p}  records: {len(records)}")
    rep = Report()
    for c in records:
        gate_fields(rep, c, plain(c.get("单词", "?")))
    gate_coverage(rep, records)
    data_dir = _resolve(base, cfg["data_dir"]) if cfg.get("data_dir") else None
    gate_semantic(records, data_dir)
    rep.dump("G1+G2 缺陷", len(records))
    if args.json:
        json.dump({"stat": dict(rep.stat), "hard": rep.hard,
                   "samples": {k: v for k, v in rep.samples.items()}},
                  open(_resolve(base, args.json), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("json report:", args.json)
    sys.exit(1 if rep.hard else (2 if rep.warn else 0))


def cmd_anki(a, args):
    import urllib.request
    cfg = a.cfg["anki"]
    url = "http://%s:%d" % (cfg.get("host", "127.0.0.1"), int(cfg.get("port", 27701)))
    key = ""
    if cfg.get("api_key_file"):
        p = _resolve(a.base, cfg["api_key_file"])
        if os.path.exists(p):
            key = open(p, encoding="utf-8").read().strip()
    if not key and cfg.get("api_key_env"):
        key = os.environ.get(cfg["api_key_env"], "")
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def ask(action, tmo=120, **params):
        pl = {"action": action, "version": 6, "params": params}
        if key:
            pl["key"] = key
        req = urllib.request.Request(url, data=json.dumps(pl).encode(),
                                     headers={"Content-Type": "application/json"})
        r = json.loads(op.open(req, timeout=tmo).read().decode())
        if r.get("error"):
            raise RuntimeError(f"{action}: {r['error']}")
        return r["result"]

    deck = args.deck or cfg["deck"]
    nids = ask("findNotes", query=f'deck:"{deck}"')
    print(f"deck {deck!r}: {len(nids)} notes (read-only scan)")
    rep = Report()
    refs = set()
    cover = collections.Counter()
    for i in range(0, len(nids), 200):
        infos = ask("notesInfo", notes=nids[i:i + 200])
        for ni in infos:
            fields = {k: v.get("value", "") for k, v in ni.get("fields", {}).items()}
            word = plain(fields.get("单词", str(ni.get("noteId"))))
            gate_fields(rep, fields, word)
            for v in fields.values():
                refs.update(SOUND_RE.findall(v or ""))
            for k in COVERAGE_FIELDS:
                if str(fields.get(k) or "").strip():
                    cover[k] += 1
        print(f"  scanned {min(i + 200, len(nids))}/{len(nids)}", flush=True)
    n = len(nids)
    print("\n=== G3(anki) 覆盖率 ===")
    for k in COVERAGE_FIELDS:
        if cover[k] or k in ("核心义",):
            print(f"  {k}: {cover[k]}/{n} ({cover[k] * 100 // max(n, 1)}%)")
    rep.dump("G1+G2(anki live)", n)

    media_dir = args.media_dir or (a.cfg.get("audit") or {}).get("media_dir")
    if media_dir:
        media_dir = _resolve(a.base, media_dir)
        files = {f for f in os.listdir(media_dir) if f.lower().endswith(".mp3")}
        missing = refs - files
        orphans = files - refs
        print(f"\n=== 媒体对账 ===\n  卡面引用: {len(refs)}  目录文件: {len(files)}")
        print(f"  引用缺失(播放坏): {len(missing)} {sorted(missing)[:5]}")
        print(f"  孤儿文件(占空间): {len(orphans)}")
        if missing:
            rep.hard = True
    else:
        print("\n(media-dir not configured — skipped 媒体对账)")
    sys.exit(1 if rep.hard else (2 if rep.warn else 0))


def main():
    ap = argparse.ArgumentParser(description="Stage 07: audit")
    ap.add_argument("--config", required=True)
    ap.add_argument("mode", choices=["file", "anki"])
    ap.add_argument("--cards", default=None)
    ap.add_argument("--deck", default=None)
    ap.add_argument("--media-dir", default=None)
    ap.add_argument("--json", default=None, help="write machine report to this path")
    args = ap.parse_args()
    args.base = os.path.dirname(os.path.abspath(args.config))
    args.cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    {"file": cmd_file, "anki": cmd_anki}[args.mode](args, args)


if __name__ == "__main__":
    main()
