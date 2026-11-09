#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04_translate.py — translate example sentences lacking Chinese (stage 04).

Scans every sentence the card builder could render (exam examples + quality
examples per entry), collects the ones without a zh translation and not yet in
the cache, and translates them through any OpenAI-compatible chat completions
endpoint. Cache = <data_dir>/translations.json keyed by the cleaned English
sentence (same key the builder looks up), so reruns are free and resumable.

The API key is read from the ENVIRONMENT VARIABLE named by
translate.api_key_env — never stored in config or code.

Modes:
  dry-run — collect + report the todo list (no key needed, no network)
  run     — translate (needs the key env var)

Usage:
  python 04_translate.py --config config.local.yaml dry-run
  python 04_translate.py --config config.local.yaml run --workers 16
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

HERE = os.path.dirname(os.path.abspath(__file__))
SYS_DEFAULT = ("你是英语词典译者。把英文句子译成自然、准确、简洁的中文，保留原文语气；"
               "只输出译文，不要引号、不要解释。")
AUTH_SCHEME = "Bearer "


def _resolve(base, p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def prepare(cfg_path):
    base = os.path.dirname(os.path.abspath(cfg_path))
    cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))["translate"]
    data_dir = _resolve(base, cfg["data_dir"])
    os.environ["S2A_DATA_DIR"] = data_dir
    if cfg.get("entries"):
        os.environ["S2A_ENTRIES"] = cfg["entries"]
    sys.path.insert(0, os.path.join(HERE, "lib"))
    import build_v3 as B  # noqa: E402  (heavy module-level loads; env first)
    import build_all as BA  # noqa: E402
    import p0_clean as P0  # noqa: E402
    return base, cfg, data_dir, B, BA, P0


def cache_path(base, cfg, data_dir):
    return _resolve(data_dir, cfg.get("cache", "translations.json"))


def collect_todo(cfg, B, BA, P0):
    """Sentences the builder may render that still lack a Chinese translation."""
    cache_p = cfg["_cache_path"]
    cache = json.load(open(cache_p, encoding="utf-8")) if os.path.exists(cache_p) else {}
    todo = {}
    for i, e in enumerate(BA.ENTRIES):
        w = e["word"].lower()
        try:
            items = B.pick_exam(w, 2) + B.pick_quality(w, 1)
        except Exception:
            continue
        for it in items:
            if it.get("zh"):
                continue
            en = P0.clean_sentence(it["en"])
            if en and en not in cache:
                todo[en] = True
        if (i + 1) % 1000 == 0:
            print(f"  scanned {i + 1}/{len(BA.ENTRIES)} todo={len(todo)}", flush=True)
    return cache, list(todo)


def translate_one(cfg, key, text):
    body = {"model": cfg.get("model", "qwen-flash"),
            "messages": [{"role": "system", "content": cfg.get("system_prompt", SYS_DEFAULT)},
                         {"role": "user", "content": text}],
            "temperature": float(cfg.get("temperature", 0.2))}
    req = urllib.request.Request(cfg["api_url"], data=json.dumps(body).encode(),
                                 headers={"Authorization": AUTH_SCHEME + key,
                                          "Content-Type": "application/json"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    r = json.loads(op.open(req, timeout=60).read())
    return r["choices"][0]["message"]["content"].strip().strip('"\u201c\u201d')


def cmd_dry(cfg, args):
    B, BA, P0 = cfg["_B"], cfg["_BA"], cfg["_P0"]
    cache, todo = collect_todo(cfg, B, BA, P0)
    print(f"translation cache: {len(cache)} sentences")
    print(f"todo (uncached, no zh): {len(todo)}")
    for s in todo[:10]:
        print("  ·", s[:80])
    sys.exit(0 if not todo else 2)


def cmd_run(cfg, args):
    B, BA, P0 = cfg["_B"], cfg["_BA"], cfg["_P0"]
    key = os.environ.get(cfg.get("api_key_env", "S2A_TRANSLATE_API_KEY"), "")
    if not key:
        sys.exit(f"env var {cfg.get('api_key_env', 'S2A_TRANSLATE_API_KEY')} is empty — set your API key")
    cache_p = cfg["_cache_path"]
    cache, todo = collect_todo(cfg, B, BA, P0)
    print(f"cache: {len(cache)} | todo: {len(todo)}")
    if not todo:
        return
    lock = threading.Lock()
    fail = []

    def job(en):
        if en in cache:
            return
        for a in range(3):
            try:
                zh = translate_one(cfg, key, en)
                with lock:
                    cache[en] = zh
                return
            except Exception:
                time.sleep(1 + a * 2)
        with lock:
            fail.append(en)

    t0 = time.time()
    workers = args.workers or int(cfg.get("workers", 16))
    with ThreadPoolExecutor(workers) as ex:
        for i, _ in enumerate(ex.map(job, todo), 1):
            if i % 300 == 0:
                print(f"{i}/{len(todo)} fail={len(fail)} {time.time() - t0:.0f}s", flush=True)
                with lock:
                    json.dump(cache, open(cache_p, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(cache, open(cache_p, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"done: cache={len(cache)} fail={len(fail)} {fail[:10]}")
    sys.exit(1 if fail else 0)


def main():
    ap = argparse.ArgumentParser(description="Stage 04: sentence translation")
    ap.add_argument("--config", required=True)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("mode", choices=["dry-run", "run"])
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.config))
    cfgraw = yaml.safe_load(open(a.config, encoding="utf-8"))["translate"]
    data_dir = _resolve(base, cfgraw["data_dir"])
    os.environ["S2A_DATA_DIR"] = data_dir
    if cfgraw.get("entries"):
        os.environ["S2A_ENTRIES"] = cfgraw["entries"]
    sys.path.insert(0, os.path.join(HERE, "lib"))
    import build_v3 as B  # noqa: E402
    import build_all as BA  # noqa: E402
    import p0_clean as P0  # noqa: E402
    cfg = dict(cfgraw)
    cfg.update(_B=B, _BA=BA, _P0=P0, _cache_path=_resolve(data_dir, cfgraw.get("cache", "translations.json")))
    {"dry-run": cmd_dry, "run": cmd_run}[a.mode](cfg, a)


if __name__ == "__main__":
    main()
