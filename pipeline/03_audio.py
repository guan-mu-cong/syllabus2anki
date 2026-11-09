#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_audio.py — pronunciation audio: download + transcode + audio map (stage 03).

Thin wrapper around the vendored production module lib/p2_audio.py (logic
byte-identical; only paths are configurable). For every entry word it ensures
UK + US pronunciation mp3s exist under <data_dir>/audio32/ (32kbps mono,
~5KB each) and writes the word -> filename map consumed by stage 05.

Requirements: `requests`; ffmpeg on PATH (only invoked for NEW downloads).
Audio source: public dictionary TTS endpoint via speech URLs cached in
stage 02 data. Personal study use only — see docs/compliance.md.

Modes:
  check — offline coverage report (no network, no ffmpeg)
  run   — download missing + transcode + write map
          (S2A_AUDIO_MAP_OUT or <data_dir>/audio_map2.json)

Usage:
  python 03_audio.py --config config.local.yaml check
  python 03_audio.py --config config.local.yaml run
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


def prepare(cfg_path):
    base = os.path.dirname(os.path.abspath(cfg_path))
    cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))["audio"]
    data_dir = _resolve(base, cfg["data_dir"])
    # env BEFORE importing the vendored module (module-level constants)
    os.environ["S2A_DATA_DIR"] = data_dir
    if cfg.get("entries"):
        os.environ["S2A_ENTRIES"] = cfg["entries"]
    if cfg.get("map_out"):
        os.environ["S2A_AUDIO_MAP_OUT"] = _resolve(base, cfg["map_out"])
    sys.path.insert(0, os.path.join(HERE, "lib"))
    import p2_audio as P2  # noqa: E402
    return base, cfg, data_dir, P2


def cmd_check(cfg_path, args):
    base, cfg, data_dir, P2 = prepare(cfg_path)
    ents = P2._s2a_entries()
    out_dir = P2.OUT
    full, partial, none = [], [], []
    for e in ents:
        w = e["word"]
        uk = os.path.join(out_dir, P2.fname(w, "uk"))
        us = os.path.join(out_dir, P2.fname(w, "us"))
        hu = os.path.exists(uk) and os.path.getsize(uk) > 800
        hs = os.path.exists(us) and os.path.getsize(us) > 800
        (full if (hu and hs) else partial if (hu or hs) else none).append(w)
    n = len(ents)
    print(f"entries: {n}")
    print(f"uk+us both: {len(full)} ({len(full) * 100 // max(n, 1)}%)")
    print(f"one side:   {len(partial)} {partial[:10]}")
    print(f"no audio:   {len(none)} {none[:10]}")
    sys.exit(0 if not none else 2)


def cmd_run(cfg_path, args):
    base, cfg, data_dir, P2 = prepare(cfg_path)
    P2.main()  # production loop: skip existing, download missing, transcode, write map


def main():
    ap = argparse.ArgumentParser(description="Stage 03: pronunciation audio")
    ap.add_argument("--config", required=True)
    ap.add_argument("mode", choices=["check", "run"])
    a = ap.parse_args()
    {"check": cmd_check, "run": cmd_run}[a.mode](a.config, a)


if __name__ == "__main__":
    main()
