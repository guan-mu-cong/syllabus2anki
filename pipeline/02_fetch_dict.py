#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_fetch_dict.py — populate the per-word dictionary cache (stage 02).

Default provider: the public Youdao dictionary endpoint (jsonapi), the same
source the production deck was built from. Fetched content is cached locally
for PERSONAL study use only — read docs/compliance.md before redistributing
anything you fetch. Swapping in another provider = write one function
`fetch_<name>(word, cfg) -> raw text` and register it in PROVIDERS.

Cache layout: <data_dir>/yd_cache/<safe(word)>.json — raw provider response,
parsed later by lib/ydparse.py. safe() replaces / \\ : with _ (parser-compatible).

Modes:
  check  offline cache-coverage report for the entries file (no network)
  fetch  download missing words (thread pool; natural resume — cached files
         are skipped; politeness delay between requests per worker)

Usage:
  python 02_fetch_dict.py --config config.local.yaml check
  python 02_fetch_dict.py --config config.local.yaml fetch --workers 8
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

HERE = os.path.dirname(os.path.abspath(__file__))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
DICTS_DEFAULT = '{"count":99,"dicts":[["ec","collins","ee","blng_sents_part","web_trans","phrs","rel_word"]]}'


def _resolve(base, p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def safe(w):
    """Filename-safe word — MUST stay in sync with lib/ydparse.safe()."""
    return w.replace("/", "_").replace("\\", "_").replace(":", "_")


def load_cfg(path):
    base = os.path.dirname(os.path.abspath(path))
    cfg = yaml.safe_load(open(path, encoding="utf-8"))["fetch"]
    cfg["_base"] = base
    cfg["_data_dir"] = _resolve(base, cfg["data_dir"])
    cfg["_cache"] = _resolve(cfg["_data_dir"], cfg.get("cache_dir", "yd_cache"))
    return cfg


def load_entries(cfg):
    ep = _resolve(cfg["_data_dir"], cfg.get("entries", "entries_7619.json"))
    if not os.path.exists(ep):
        ep2 = _resolve(cfg["_base"], cfg.get("entries", ""))
        if cfg.get("entries") and os.path.exists(ep2):
            ep = ep2
    d = json.load(open(ep, encoding="utf-8"))
    ents = d.get("entries") or d.get("words") or (d if isinstance(d, list) else [])
    return ep, ents


def fetch_youdao(word, cfg):
    """Provider: Youdao public dictionary endpoint. Returns raw response text."""
    q = urllib.parse.quote(word)
    dicts = urllib.parse.quote(cfg.get("dicts", DICTS_DEFAULT))
    url = f"https://dict.youdao.com/jsonapi?q={q}&dicts={dicts}"
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://dict.youdao.com/"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    tmo = int(cfg.get("timeout", 25))
    return op.open(req, timeout=tmo).read().decode("utf-8", "replace")


PROVIDERS = {"youdao": fetch_youdao}


def cache_path(cfg, word):
    return os.path.join(cfg["_cache"], safe(word) + ".json")


def cmd_check(cfg, args):
    ep, ents = load_entries(cfg)
    have = [e for e in ents if os.path.exists(cache_path(cfg, e["word"]))]
    miss = [e["word"] for e in ents if not os.path.exists(cache_path(cfg, e["word"]))]
    print(f"entries: {len(ents)} (from {ep})")
    print(f"cached:  {len(have)} ({len(have) * 100 // max(len(ents), 1)}%)")
    print(f"missing: {len(miss)}")
    if miss:
        print("missing sample:", miss[:20])
    sys.exit(0 if not miss else 2)


def cmd_fetch(cfg, args):
    ep, ents = load_entries(cfg)
    provider = PROVIDERS[cfg.get("provider", "youdao")]
    todo = [e["word"] for e in ents if not os.path.exists(cache_path(cfg, e["word"]))]
    print(f"entries: {len(ents)} | to fetch: {len(todo)}")
    if not todo:
        return
    os.makedirs(cfg["_cache"], exist_ok=True)
    workers = args.workers or int(cfg.get("workers", 6))
    delay = float(cfg.get("delay_s", 0.3))
    fails = []

    def job(w):
        for attempt in range(3):
            try:
                txt = provider(w, cfg)
                if txt and txt.strip().startswith("{"):
                    json.loads(txt)  # validate JSON before caching
                    open(cache_path(cfg, w), "w", encoding="utf-8").write(txt)
                    return w
            except Exception:
                pass
            time.sleep(0.5 * (attempt + 1))
        fails.append(w)
        return None

    t0 = time.time()
    n = 0
    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(job, todo):
            n += 1
            if r:
                time.sleep(delay)
            if n % 200 == 0:
                print(f"  {n}/{len(todo)} fail={len(fails)} {time.time() - t0:.0f}s", flush=True)
    print(f"fetched ok: {n - len(fails)} | failed: {len(fails)} {fails[:15]}")
    sys.exit(1 if fails else 0)


def main():
    ap = argparse.ArgumentParser(description="Stage 02: dictionary cache fetcher")
    ap.add_argument("--config", required=True)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("mode", choices=["check", "fetch"])
    a = ap.parse_args()
    cfg = load_cfg(a.config)
    {"check": cmd_check, "fetch": cmd_fetch}[a.mode](cfg, a)


if __name__ == "__main__":
    main()
