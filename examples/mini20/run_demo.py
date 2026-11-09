#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_demo.py — end-to-end offline demo on 20 SYNTHETIC words.

Stages exercised (no network, no Anki, no dictionary content):
  02 check  -> cache coverage must be 100%
  05 build  -> 20 cards, 0 errors (wordfreq used for ordering; install it)
  05b       -> rules-only attribution for all 20
  05c       -> bold bake, 核心义 dropped
  06 dry    -> offline push-notes payload preview
  07 file   -> audit gates; hard gates must pass (0 residues, 0 duplicates)

Usage:  python run_demo.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CFG = os.path.join(HERE, "config.mini20.yaml")
PY = sys.executable


def stage(name, argv, expect=(0,)):
    print(f"\n{'=' * 60}\n▶ {name}\n{'=' * 60}")
    r = subprocess.run([PY] + argv, cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip()[-1500:])
    if r.returncode not in expect:
        sys.exit(f"!! stage {name} failed: exit {r.returncode}")
    return out


def main():
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    if not os.path.exists(os.path.join(HERE, "data", "entries_7619.json")):
        stage("gen data", [os.path.join(HERE, "gen_data.py")])

    P = lambda s: os.path.join(REPO, "pipeline", s)
    stage("02 fetch-dict cache check", [P("02_fetch_dict.py"), "--config", CFG, "check"])
    stage("05 build cards", [P("05_build_cards.py"), "--config", CFG])
    stage("05b attribution (rules-only)", [P("05b_attribute.py"), "--config", CFG, "--all"])
    stage("05c finalize (bold bake)", [P("05c_finalize.py"), "--config", CFG])
    stage("06 write-anki DRY RUN (offline)",
          [P("06_write_anki.py"), "--config", CFG, "push-notes", "--dry-run", "--limit", "2"])
    out = stage("07 audit (file mode)",
                [P("07_audit.py"), "--config", CFG, "file",
                 "--json", os.path.join(HERE, "out", "audit_report.json")],
                expect=(0, 2))  # 2 = warnings only (e.g. synthetic cards lack 搭配)

    # ---- invariants ----
    cards = json.load(open(os.path.join(HERE, "out", "cards_final_mini.json"), encoding="utf-8"))
    assert len(cards) == 20, f"expected 20 cards, got {len(cards)}"
    assert all("核心义" not in c for c in cards), "05c must drop 核心义"
    star_words = {c["单词"] for c in cards if str(c.get("官方★") or "").strip()}
    assert len(star_words) == 9, f"expected 9 starred, got {len(star_words)}"
    # starred words sort before non-starred (tier 0)
    assert cards[0]["排序键"].startswith("0"), "first card must be ★ tier"
    report = json.load(open(os.path.join(HERE, "out", "audit_report.json"), encoding="utf-8"))
    assert not report["hard"], f"hard gate failures: {report['stat']}"
    residue = [k for k in report["stat"] if "实体残留" in k]
    assert not residue, f"residues found: {residue}"
    # audio refs baked
    n_sound = sum(1 for c in cards if "[sound:" in (c.get("发音美") or ""))
    assert n_sound == 20, f"expected 20 cards with us audio ref, got {n_sound}"

    print(f"\n{'=' * 60}\n✅ mini20 demo PASSED all invariants")
    print(f"   cards: {len(cards)} (starred {len(star_words)}) | hard gates: clean")
    print(f"   sample: {cards[0]['单词']} | 常用义项: {cards[0].get('常用义项', '')[:60]}")
    print(f"   柯林斯星级: {cards[0].get('柯林斯星级')} | 排序键: {cards[0]['排序键']}")


if __name__ == "__main__":
    main()
