#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
06_write_anki.py — write cards into Anki via AnkiConnect (stage 06).

Subcommands:
  init          create note model (+ deck) with the configured field order and
                card template/CSS from assets
  sync-template push template/CSS updates to an existing model
  push-media    store pronunciation mp3s into the Anki collection (threaded,
                resumable via a done-log)
  push-notes    addNotes in batches (resumable via written-log; on duplicate
                errors falls back to note-by-note so existing cards are skipped)
  forget        reset scheduling for the whole deck (findCards -> forgetCards)
  stats         deck/model status report

Global flags: --dry-run (print the plan + a sample payload, touch nothing),
--limit N (first N records only).

Connection: AnkiConnect HTTP endpoint (host/port from config). The API key is
read from anki.api_key_file (a path OUTSIDE the repo, e.g. a gitignored local
file) or from the environment variable named by anki.api_key_env. Never commit
a key.

Field payloads mirror the production convention: for each record take
{k: rec[k] for k in configured_fields if k in rec} (or the sub-dict at
anki.fields_from when set). [sound:...] references must already be baked into
the records (stage 05 does this via the audio map).

Usage:
  python 06_write_anki.py --config config.local.yaml init
  python 06_write_anki.py --config config.local.yaml push-media
  python 06_write_anki.py --config config.local.yaml push-notes --dry-run
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

HERE = os.path.dirname(os.path.abspath(__file__))


def _resolve(base, p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


class Anki:
    def __init__(self, cfg, base):
        self.base = base
        self.cfg = cfg
        self.url = "http://%s:%d" % (cfg.get("host", "127.0.0.1"), int(cfg.get("port", 27701)))
        key = ""
        if cfg.get("api_key_file"):
            p = _resolve(base, cfg["api_key_file"])
            if os.path.exists(p):
                key = open(p, encoding="utf-8").read().strip()
        if not key and cfg.get("api_key_env"):
            key = os.environ.get(cfg["api_key_env"], "")
        self.key = key
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def ask(self, action, tmo=600, **params):
        pl = {"action": action, "version": 6, "params": params}
        if self.key:
            pl["key"] = self.key
        req = urllib.request.Request(self.url, data=json.dumps(pl).encode(),
                                     headers={"Content-Type": "application/json"})
        r = json.loads(self.opener.open(req, timeout=tmo).read().decode())
        if r.get("error"):
            raise RuntimeError(f"{action}: {r['error']}")
        return r["result"]


def load_records(cfg, base, args):
    p = _resolve(base, args.cards or cfg.get("cards", "work/cards_final.json"))
    data = json.load(open(p, encoding="utf-8"))
    if args.limit:
        data = data[: args.limit]
    return p, data


def fields_of(rec, cfg):
    src = rec.get(cfg["fields_from"]) if cfg.get("fields_from") else rec
    if not isinstance(src, dict):
        src = rec
    fields = cfg.get("fields") or list(src.keys())
    return {k: src[k] for k in fields if k in src}


def tags_of(rec, cfg):
    tags = list(cfg.get("tags") or [])
    st = cfg.get("star_tag") or {}
    if st and str(rec.get(st.get("field", ""), "")).strip():
        tags.append(st["tag"])
    return tags


def cmd_init(a, args):
    cfg, ank = a.cfg, a.ank
    tpl = cfg.get("template") or {}
    if not (tpl.get("front") and tpl.get("back")):
        sys.exit("anki.template.front/back required for init")
    front = open(_resolve(a.base, tpl["front"]), encoding="utf-8").read()
    back = open(_resolve(a.base, tpl["back"]), encoding="utf-8").read()
    css = open(_resolve(a.base, tpl["css"]), encoding="utf-8").read() if tpl.get("css") else ""
    names = ank.ask("modelNames")
    if cfg["model"] in names:
        print("model exists:", cfg["model"])
    else:
        if args.dry_run:
            print("[dry-run] createModel", cfg["model"], f"fields={len(cfg['fields'])}")
        else:
            ank.ask("createModel", modelName=cfg["model"], inOrderFields=cfg["fields"],
                    cardTemplates=[{"Name": cfg.get("template_name", "Card 1"),
                                    "Front": front, "Back": back}],
                    css=css, isStd=True)
            print("model created:", cfg["model"])
    decks = ank.ask("deckNames")
    if cfg["deck"] not in decks:
        if args.dry_run:
            print("[dry-run] createDeck", cfg["deck"])
        else:
            ank.ask("createDeck", deck=cfg["deck"])
            print("deck created:", cfg["deck"])
    else:
        print("deck exists:", cfg["deck"])


def cmd_sync_template(a, args):
    cfg, ank = a.cfg, a.ank
    tpl = cfg["template"]
    front = open(_resolve(a.base, tpl["front"]), encoding="utf-8").read()
    back = open(_resolve(a.base, tpl["back"]), encoding="utf-8").read()
    css = open(_resolve(a.base, tpl["css"]), encoding="utf-8").read() if tpl.get("css") else None
    tname = cfg.get("template_name", "Card 1")
    if args.dry_run:
        print(f"[dry-run] update template {tname!r} of {cfg['model']} "
              f"(front {len(front)}B back {len(back)}B css {len(css or '')}B)")
        return
    ank.ask("updateModelTemplates", model={"name": cfg["model"],
                                           "templates": {tname: {"Front": front, "Back": back}}})
    if css is not None:
        ank.ask("updateModelStyling", model={"name": cfg["model"], "css": css})
    print("template/CSS synced")


def cmd_push_media(a, args):
    cfg, ank = a.cfg, a.ank
    m = cfg.get("media") or {}
    mdir = _resolve(a.base, m.get("dir", "work/audio32"))
    done_log = _resolve(a.base, m.get("done_log", "work/media_done.json"))
    done = set(json.load(open(done_log, encoding="utf-8"))) if os.path.exists(done_log) else set()
    files = sorted(f for f in os.listdir(mdir) if f.endswith(".mp3") and f not in done)
    if args.limit:
        files = files[: args.limit]
    print(f"media dir: {mdir}\nto push: {len(files)} | already done: {len(done)}")
    if args.dry_run or not files:
        return

    def job(f):
        for attempt in range(3):
            try:
                ank.ask("storeMediaFile", tmo=60, filename=f, path=os.path.join(mdir, f))
                return f
            except Exception:
                time.sleep(0.3 * (attempt + 1))
        return None

    ok = err = 0
    t0 = time.time()
    with ThreadPoolExecutor(int(m.get("workers", 6))) as ex:
        for i, f in enumerate(ex.map(job, files), 1):
            if f:
                ok += 1
                done.add(f)
            else:
                err += 1
            if i % 1000 == 0:
                print(f"  {i}/{len(files)} ok={ok} err={err} {time.time() - t0:.0f}s", flush=True)
                json.dump(sorted(done), open(done_log, "w", encoding="utf-8"))
    json.dump(sorted(done), open(done_log, "w", encoding="utf-8"))
    print(f"media done: ok={ok} err={err} total={len(done)} {time.time() - t0:.0f}s")


def cmd_push_notes(a, args):
    cfg, ank = a.cfg, a.ank
    p, records = load_records(cfg, a.base, args)
    log = _resolve(a.base, cfg.get("written_log", "work/written.json"))
    done = set(json.load(open(log, encoding="utf-8")).get("words", [])) if os.path.exists(log) else set()
    wf = cfg.get("word_field", "单词")
    todo = [r for r in records if r.get(wf, "") not in done]
    print(f"records: {len(records)} (from {p}) | already written: {len(done)} | todo: {len(todo)}")
    if args.dry_run:
        if todo:
            sample = {"deckName": cfg["deck"], "modelName": cfg["model"],
                      "tags": tags_of(todo[0], cfg),
                      "options": {"allowDuplicate": bool(cfg.get("allow_duplicate", False)),
                                  "duplicateScope": "deck"},
                      "fields": fields_of(todo[0], cfg)}
            print("[dry-run] sample payload (fields truncated to 60 chars):")
            s = dict(sample)
            s["fields"] = {k: (v[:60] + "…" if isinstance(v, str) and len(v) > 60 else v)
                           for k, v in sample["fields"].items()}
            print(json.dumps(s, ensure_ascii=False, indent=1)[:2000])
        return
    if not todo:
        return
    batch = int(cfg.get("batch", 300))
    total = 0
    for bi in range(0, len(todo), batch):
        chunk = todo[bi:bi + batch]
        notes = [{"deckName": cfg["deck"], "modelName": cfg["model"],
                  "tags": tags_of(r, cfg),
                  "options": {"allowDuplicate": bool(cfg.get("allow_duplicate", False)),
                              "duplicateScope": "deck"},
                  "fields": fields_of(r, cfg)} for r in chunk]
        try:
            res = ank.ask("addNotes", notes=notes)
        except Exception as e:
            msg = str(e)[:200]
            print(f"  batch {bi} failed ({msg}) — retrying note-by-note")
            if "duplicate" not in msg:
                time.sleep(3)
            res = []
            for n in notes:
                try:
                    r = ank.ask("addNotes", notes=[n])
                    res.append(r[0] if r else None)
                except Exception:
                    res.append(None)
        ok = sum(1 for r in res if r)
        total += ok
        done.update(r.get(wf, "") for r, res_ in zip(chunk, res) if res_)
        json.dump({"words": sorted(done)}, open(log, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"  batch {bi // batch + 1}: wrote {ok}/{len(chunk)} total {total}", flush=True)
    ids = ank.ask("findCards", query=f'deck:"{cfg["deck"]}"')
    print(f"push-notes done: wrote {total}; deck now has {len(ids)} cards")


def cmd_forget(a, args):
    cfg, ank = a.cfg, a.ank
    ids = ank.ask("findCards", query=f'deck:"{cfg["deck"]}"')
    print(f"cards to reset: {len(ids)}")
    if args.dry_run or not ids:
        return
    ank.ask("forgetCards", cards=ids)
    print("scheduling reset (all cards are new again)")


def cmd_stats(a, args):
    cfg, ank = a.cfg, a.ank
    st = ank.ask("getDeckStats", decks=[cfg["deck"]])
    for did, s in st.items():
        print(f"deck {cfg['deck']}: total={s['total_in_deck']} new={s['new_count']} learn={s['learn_count']} review={s['review_count']}")
    fields = ank.ask("modelFieldNames", modelName=cfg["model"])
    print(f"model {cfg['model']}: {len(fields)} fields")
    missing = [f for f in cfg.get("fields", []) if f not in fields]
    if missing:
        print("!! config fields missing on model:", missing)


def main():
    ap = argparse.ArgumentParser(description="Stage 06: Anki writer")
    ap.add_argument("--config", required=True)
    ap.add_argument("--cards", default=None, help="override anki.cards record file")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("command", choices=["init", "sync-template", "push-media",
                                        "push-notes", "forget", "stats"])
    args = ap.parse_args()

    base = os.path.dirname(os.path.abspath(args.config))
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))["anki"]
    args.base, args.cfg = base, cfg
    if args.dry_run and args.command in ("init", "push-media", "push-notes", "sync-template", "forget"):
        # still connect for stats-free dry runs? No: dry-run must work offline.
        args.ank = Anki(cfg, base)
    else:
        args.ank = Anki(cfg, base)
        try:
            args.ank.ask("version", tmo=5)
        except Exception as e:
            sys.exit(f"AnkiConnect not reachable at {args.ank.url}: {e}")
    {"init": cmd_init, "sync-template": cmd_sync_template, "push-media": cmd_push_media,
     "push-notes": cmd_push_notes, "forget": cmd_forget, "stats": cmd_stats}[args.command](args, args)


if __name__ == "__main__":
    main()
