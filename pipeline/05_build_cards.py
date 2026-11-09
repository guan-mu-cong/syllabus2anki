#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05_build_cards.py — render the full card-field records for every wordlist entry.

Stage 5 of the syllabus2anki pipeline. Consumes:
  * entries json        (stage 01 output, enriched with plan/source metadata)
  * dictionary cache    (stage 02 output, per-word JSON)
  * corpus / frequency / audio-map / translation caches (stages 02-04)
and produces one JSON record per card with all render fields (senses, examples,
etymology, collocations, value-tier sort key, ...).

The heavy lifting lives in the vendored production library (lib/build_v3.py,
lib/build_all.py, lib/freq.py, lib/ydparse.py, lib/p0_clean.py). This wrapper
only: (a) injects the data directory via S2A_DATA_DIR before import, and
(b) replicates the production main loop with a configurable output path so a
regression run never overwrites production data.

Card field pipeline highlights (details in docs/pipeline.md):
  * sense cleaning: register tags kept as bracketed prefixes, junk senses
    dropped only on exact 〔古〕/〔非正式〕-style tags (fuzzy single-char
    matching once killed 15.7% of legitimate senses)
  * core sense == most common sense, calibrated on COCA distributions where
    available (100% enforced, documented one-off overrides allowed)
  * value-tier sort key: starred > exam-attested > short common > derived,
    each tier ordered by general frequency (wordfreq zipf) descending
  * audio references taken from the word-indexed audio map (stage 03)

Usage:
    python 05_build_cards.py --config config.local.yaml
"""
import argparse
import json
import os
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

HERE = os.path.dirname(os.path.abspath(__file__))


def _resolve(base, p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def main():
    ap = argparse.ArgumentParser(description="Build card records for all entries (stage 05).")
    ap.add_argument("--config", required=True, help="YAML config (see config.example.yaml)")
    args = ap.parse_args()

    base = os.path.dirname(os.path.abspath(args.config))
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))["build"]
    data_dir = _resolve(base, cfg["data_dir"])
    out_path = _resolve(base, cfg["out_path"])

    # Inject data dir BEFORE importing the vendored lib (module-level loads).
    os.environ["S2A_DATA_DIR"] = data_dir
    if cfg.get("entries"):
        os.environ["S2A_ENTRIES"] = cfg["entries"]  # file name, relative to data_dir
    sys.path.insert(0, os.path.join(HERE, "lib"))
    import build_all as BA  # noqa: E402  (import order matters here)

    entries = BA.ENTRIES
    if not entries:
        sys.exit(f"no entries found (looked for {os.environ.get('S2A_ENTRIES', 'entries_7619.json')} in {data_dir})")
    print(f"entries: {len(entries)} (from {data_dir})")
    cards, errs = [], []
    for i, e in enumerate(entries):
        c = BA.build_card(e)
        if c.get("error"):
            errs.append((e["word"], c["error"]))
        else:
            c["_idx"] = i
            cards.append(c)
        if (i + 1) % 1000 == 0:
            print(f"  {i + 1}/{len(entries)} cards={len(cards)} errors={len(errs)}", flush=True)

    # Production ordering: value tier + frequency, alphabetical tie-break.
    cards.sort(key=lambda c: (c["排序键"], c["单词"].lower()))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    json.dump(cards, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
    err_path = os.path.join(os.path.dirname(out_path), "build_errors.json")
    json.dump(errs, open(err_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"built: {len(cards)} cards | errors: {len(errs)}")
    if errs:
        print("error samples:", errs[:15])
    print("written:", out_path)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
