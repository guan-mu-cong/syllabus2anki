#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05c_finalize.py — bake attribution into final card records (stage 05c).

Wrapper around vendored lib/p6_finalizer.py: applies the 05b audit jsonl to
the stage-05 card records — bolds attributed sense tokens inside 常用义项 and
drops the now-redundant 核心义 field (v5 card spec). Deterministic, offline,
same inputs -> byte-identical output.

Usage:
  python 05c_finalize.py --config config.local.yaml
"""
import argparse
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
    ap = argparse.ArgumentParser(description="Stage 05c: finalize (bold bake)")
    ap.add_argument("--config", required=True)
    a = ap.parse_args()

    base = os.path.dirname(os.path.abspath(a.config))
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))["finalize"]
    os.environ["S2A_DATA_DIR"] = _resolve(base, cfg["data_dir"])
    os.environ["S2A_CARDS"] = _resolve(base, cfg.get("cards", "work/cards.json"))
    os.environ["S2A_AUDIT"] = _resolve(base, cfg.get("audit", "work/attributor_audit.jsonl"))
    os.environ["S2A_CARDS_FINAL_OUT"] = _resolve(base, cfg.get("out_path", "work/cards_final.json"))

    sys.path.insert(0, os.path.join(HERE, "lib"))
    import p6_finalizer as P6  # noqa: E402
    P6.main()


if __name__ == "__main__":
    main()
