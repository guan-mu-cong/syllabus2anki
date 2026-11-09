#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05b_attribute.py — sense-bold attribution (stage 05b, v5 card extension).

Wrapper around vendored lib/p5_attributor.py: decides, for every card, WHICH
sense token(s) deserve the <b class="xt"> bold — using real exam sentences +
an LLM final judgement where available, deterministic rules elsewhere
(frequency-tier default / honest blank). Output is an append-only audit jsonl
(resumable), consumed by stage 05c.

LLM config comes from the config file; the API KEY comes only from the
environment variable named by attribute.llm.api_key_env. Set
attribute.llm.enabled: false for a fully offline rules-only run.

Usage:
  python 05b_attribute.py --config config.local.yaml --all --workers 10
  python 05b_attribute.py --config config.local.yaml --limit 50
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
    ap = argparse.ArgumentParser(description="Stage 05b: attribution")
    ap.add_argument("--config", required=True)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    base = os.path.dirname(os.path.abspath(a.config))
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))["attribute"]
    data_dir = _resolve(base, cfg["data_dir"])

    os.environ["S2A_DATA_DIR"] = data_dir
    os.environ["S2A_CARDS"] = _resolve(base, cfg.get("cards", "work/cards.json"))
    os.environ["S2A_AUDIT"] = _resolve(base, cfg.get("audit_out", "work/attributor_audit.jsonl"))
    llm = cfg.get("llm") or {}
    if not llm.get("enabled", False):
        os.environ["S2A_NO_LLM"] = "1"
    else:
        os.environ.pop("S2A_NO_LLM", None)
        key = os.environ.get(llm.get("api_key_env", "S2A_LLM_API_KEY"), "")
        if key:
            os.environ["S2A_LLM_API_KEY"] = key
        if llm.get("api_url"):
            os.environ["S2A_LLM_URL"] = llm["api_url"]
        if llm.get("models"):
            os.environ["S2A_LLM_MODELS"] = ",".join(llm["models"])

    sys.path.insert(0, os.path.join(HERE, "lib"))
    import p5_attributor as P5  # noqa: E402

    # forward CLI to the vendored main()
    fwd = ["p5", "--limit", str(a.limit), "--workers", str(a.workers)]
    if a.all:
        fwd.append("--all")
    sys.argv = fwd
    P5.main()


if __name__ == "__main__":
    main()
