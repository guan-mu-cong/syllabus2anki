#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_extract_wordlist.py — extract the vocabulary list from an official syllabus PDF.

Stage 1 of the syllabus2anki pipeline. Reads the word-list pages of an exam
syllabus PDF (e.g. the China CET 2016 revised syllabus), repairs known
text-layer corruptions, and writes a clean entry list:

    [{"w": "center", "star": false, "variants": ["centre"], "pages": [39]}, ...]

Repairs performed (background and war stories: docs/pitfalls.md):
  * Oxford repeated-prefix marker "Ｇ" (U+FF27): center/Ｇtre -> centre.
    Must be swapped for a placeholder BEFORE NFKC normalization, which would
    otherwise flatten it into a plain 'G' and corrupt the reconstruction.
  * Entries wrapped across lines: 'marvel(' + 'l)ous' -> marvel(l)ous,
    'mo(u)' + 'ld' -> mo(u)ld. Balanced-paren merges are accepted only when
    the result is a real dictionary word (guards against ax(e)+axis -> axaxis).
  * Swallowed spaces: 'accordingto' -> 'according to'. Accepted only when
    EXACTLY ONE space insertion hits the dictionary cache.
  * Parenthesized / slashed spelling variants: mom(my), center/Ｇtre,
    airＧconditioning -> one card head + variants list.
  * Fullwidth sense-number lines, sample-paper headers, option letters.

Dictionary probe: repair decisions need an "is this a real word?" oracle,
served by a cache directory of per-word JSON files (produced by stage 02).
With no cache available the probe answers False everywhere and repairs are
conservatively skipped — run 02 between two passes of this script for full
repair coverage (two-pass bootstrap).

Usage:
    python 01_extract_wordlist.py --config config.local.yaml [--pdf P] [--out O]
"""
import argparse
import json
import os
import re
import sys
import unicodedata

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

try:
    import pymupdf
except ImportError:  # pragma: no cover
    sys.exit("PyMuPDF is required: pip install pymupdf")

GS = "\x01"  # placeholder for U+FF27 during normalization

# --------------------------------------------------------------------------
# Line-level filters
# --------------------------------------------------------------------------

# A plausible word-list line: starts with a letter (or ★-stripped letter),
# allows the typography the syllabus uses (hyphen, apostrophe, slash, dot,
# comma, parens, space) plus the GS placeholder. Deliberately permissive;
# BAD and shape checks below do the real filtering.
ENTRY_OK = re.compile("^[^\\W\\d_][\\w\\-'/\\.,() \x01]{0,44}$")
ENTRY_OK_LIGHT = re.compile("^[a-z][A-Za-z\\-'/()]{1,44}$")

# Sample-paper / section headers leaking into the text layer.
BAD = re.compile(r"^(全国大学|Part|Section|Passage|News|Conversation|Recording|"
                 r"Translation|Writing|Reading|Listening|Comprehension|Directions|"
                 r"Unit|Model|Test|词|表|[IVX]+$)")

NUMBER_ONLY = re.compile(r"^[０-９0-9]{1,2}$")  # fullwidth sense-number lines
CONT = re.compile(r"^[a-z]{1,4}$")              # short wrap continuation: ld/ous/s


def canon(s):
    """Comparison key: lowercase ASCII letters only."""
    return re.sub(r"[^a-z]", "", (s or "").lower())


def norm(s):
    """Normalize one raw PDF line.

    ORDER MATTERS: U+FF27 (Ｇ) must be replaced by the GS placeholder BEFORE
    unicodedata NFKC, because NFKC maps it to a plain 'G' and destroys the
    repeated-prefix information (center/Ｇtre must rebuild into 'centre').
    """
    s = s.replace("\uff27", GS)
    s = unicodedata.normalize("NFKC", s).replace("\u3000", " ").strip()
    s = (s.replace("\U001001b3", "'")   # apostrophe variant (coup d'état, o'clock)
          .replace("\U00100a8b", "-")   # hyphen variant
          .replace("\u2015", "-"))
    return s


class DictProbe:
    """'Is this a real word?' oracle backed by a dictionary cache directory.

    Backend convention (matches stage 02): one JSON file per headword.
    Single tokens are looked up under a sanitized filename (characters outside
    [A-Za-z-' ] replaced with '_'); multi-word phrase candidates are looked up
    under their RAW name with spaces, matching how the fetch stage stores
    phrases. Files <= min_size bytes count as misses (error stubs).
    """

    def __init__(self, cache_dir, min_size=200):
        self.dir = cache_dir
        self.min_size = min_size
        self.enabled = bool(cache_dir) and os.path.isdir(cache_dir)
        self._memo = {}

    def _hit(self, filename):
        p = os.path.join(self.dir, filename)
        return os.path.exists(p) and os.path.getsize(p) > self.min_size

    def is_word(self, s):
        """Single-token lookup, sanitized filename."""
        s = (s or "").strip().lower()
        if not self.enabled:
            return False
        if s in self._memo:
            return self._memo[s]
        ok = self._hit(re.sub(r"[^A-Za-z\-' ]", "_", s) + ".json")
        self._memo[s] = ok
        return ok

    def has_phrase(self, cand):
        """Phrase lookup under the raw candidate name (spaces/apostrophes kept)."""
        if not self.enabled:
            return False
        return self._hit(cand + ".json")


# --------------------------------------------------------------------------
# Line repair
# --------------------------------------------------------------------------

def unbalanced(s):
    return s.count("(") != s.count(")")


def real_word_forms(joined, probe):
    """joined looks like mo(u)ld / marvel(l)ous: derive parenthesis-free
    candidates and confirm at least one exists in the dictionary."""
    base = re.sub(r"\([^()]*\)", "", joined).lower()   # mold
    alt = re.sub(r"[()]", "", joined).lower()          # mould
    return probe.is_word(base) or probe.is_word(alt)


def merge_wrapped(lines, probe):
    """Re-join entries the PDF split across lines; drop sense-number lines."""
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if NUMBER_ONLY.match(line):
            i += 1
            continue
        # Case 1: unbalanced parens -> entry definitely continues on next line.
        if unbalanced(line) and i + 1 < len(lines):
            nxt = lines[i + 1]
            if not NUMBER_ONLY.match(nxt):
                joined = line + nxt
                if not unbalanced(joined) and len(canon(joined)) >= 3:
                    out.append(joined)
                    i += 2
                    continue
        # Case 2: parens balanced but the entry was cut right after ')':
        # 'mo(u)' + 'ld'. Accept only if the merged form is a real dictionary
        # word, otherwise ax(e)+axis would fuse into 'axaxis'.
        if (re.search(r"\)$", line) and i + 1 < len(lines)
                and CONT.match(lines[i + 1])
                and len(canon(line)) >= 3):
            joined = line + lines[i + 1]
            if ENTRY_OK_LIGHT.match(joined) and real_word_forms(joined, probe):
                out.append(joined)
                i += 2
                continue
        out.append(line)
        i += 1
    return out


def recover_space(word, probe):
    """'accordingto' -> 'according to'.

    Try every split point; accept only when EXACTLY ONE candidate phrase hits
    the dictionary cache. Ambiguous or cache-less words are left untouched.
    """
    if " " in word or "-" in word or len(word) < 5:
        return None
    hits = []
    for k in range(2, len(word) - 1):
        cand = word[:k] + " " + word[k:]
        a, b = cand.split(" ")
        if len(a) < 2 or len(b) < 2:
            continue
        if probe.has_phrase(cand):
            hits.append(cand)
    return hits[0] if len(hits) == 1 else None


def recover_apostrophe(word, probe):
    """coupd'état -> coup d'état (split before d' when the phrase is real)."""
    m = re.match(r"^([a-z]{3,})(d'[a-zéèêàç]{2,})$", word)
    if not m:
        return None
    cand = m.group(1) + " " + m.group(2)
    return cand if probe.has_phrase(cand) else None


# --------------------------------------------------------------------------
# Form expansion
# --------------------------------------------------------------------------

def expand_g(form1, form2):
    """Resolve the Oxford repeated-prefix marker.

    'center/Ｇtre': the second spelling reuses the first len(form1)-len(rest)
    characters of form1 -> 'cen' + 'tre' = 'centre'. Mid-word (no slash) the
    marker is a hyphen: airＧconditioning -> air-conditioning. Replacing it
    with 'e' (a common first guess) yields garbage like 'center/etre'.
    """
    if GS not in form2:
        return form2
    if form2.startswith(GS):
        rest = form2[len(GS):]
        n = len(form1) - len(rest)
        if 0 < n <= len(form1):
            return form1[:n] + rest
        return rest
    return form2.replace(GS, "-")


def _paren(w):
    """mo(u)ld -> [mold, mould]; mom(my) -> [mom, mommy]; coup(d'état) -> [coup, coup d'état]"""
    if "(" not in w:
        return [w]
    m = re.match(r"^([A-Za-z\-' ]*)\(([^()]*)\)([A-Za-z\-' ]*)$", w)
    if not m:
        return [re.sub(r"[()]", "", w)]
    pre, mid, suf = m.groups()
    base = (pre + suf).strip()
    forms = [base]
    with_mid = (pre + mid + suf).strip()
    if with_mid and with_mid != base:
        forms.append(with_mid)
    return forms


def paren_split(w):
    """One raw line -> (head_form, [variant_forms]).

    Handles slashed double spellings (center/Ｇtre), parenthesized variants
    (mom(my)), and two side-by-side entries on one line
    ('standardize/Ｇise standardization/Ｇsation' -> head of the first,
    everything else becomes variants; one line never yields two cards).
    """
    w = w.strip()
    out_heads = []
    groups = [p for p in re.split(r"\s+", w) if p]
    if not (len(groups) > 1 and "/" in groups[0] and "/" in groups[1]):
        groups = [w]
    for g in groups:
        if "/" not in g:
            forms = _paren(g)
            out_heads.append((forms[0], forms[1:]))
            continue
        f1, f2 = g.split("/", 1)
        f1 = f1.strip()
        f2 = expand_g(f1, f2.strip())
        forms = _paren(f1)
        if f2 and f2 != f1:
            forms.append(_paren(f2)[0])
        out_heads.append((forms[0], forms[1:]))
    head, variants = out_heads[0]
    for h, v in out_heads[1:]:
        variants.extend([h] + v)
    head = head.replace(GS, "-")
    variants = [v.replace(GS, "-") for v in variants if v and v != head]
    seen, uniq = set(), []
    for v in variants:
        if v.lower() not in seen:
            seen.add(v.lower())
            uniq.append(v)
    return head, uniq


# --------------------------------------------------------------------------
# Extraction driver
# --------------------------------------------------------------------------

def extract(pdf_path, page_start, page_end, min_good_per_page, probe, fixups=None):
    fixups = fixups or {}
    dropped = []
    doc = pymupdf.open(pdf_path)
    entries, seen, pages = [], {}, []
    for i in range(page_start, page_end + 1):
        raw = [norm(x) for x in doc[i].get_text().splitlines()]
        lines = merge_wrapped([x for x in raw if x], probe)
        good = []
        for line in lines:
            if BAD.match(line):
                continue
            if not ENTRY_OK.match(line.lstrip("★").strip()):
                continue
            if len(canon(line)) < 2:
                continue
            star = line.startswith("★")
            w = line.lstrip("★").strip()
            if len(canon(w)) < 2:
                continue
            # option letters (A) B. ...) and question numbers from sample papers
            if re.match(r"^[A-D][\)\.]", w) or re.match(r"^Questions?[\d１-９]", w):
                continue
            good.append((star, w))
        # The configured page_end is a human-verified list boundary: the LAST
        # page may legitimately hold a single trailing entry (the CET 2016 PDF
        # prints "★zoom" alone on p148 before the printed totals). Interior
        # pages keep the sparse-page guard against TOC/blank intruders.
        threshold = min_good_per_page if i < page_end else 1
        if len(good) < threshold:
            continue
        pages.append((i, len(good)))
        for star, w in good:
            fixed = recover_space(w, probe) or recover_apostrophe(w, probe)
            if fixed:
                w = fixed
            head, variants = paren_split(w)
            # Variants produced by paren/slash expansion can themselves carry
            # PDF artifacts (coup(d'état) -> "coupd'état"); run the same
            # space/apostrophe recovery on them.
            variants = [recover_space(v, probe) or recover_apostrophe(v, probe) or v
                        for v in variants]
            # Documented one-off corrections for artifacts no general rule can
            # decide safely (see head_fixups in config).
            fx = fixups.get(head.lower())
            if fx == "drop":
                dropped.append(head)
                continue
            if isinstance(fx, str):
                head = fx
            k = canon(head)
            if not k:
                continue
            if k in seen:
                # Same headword printed twice (e.g. homographs merged by the
                # digitized list): keep first record, OR in the star, append variants.
                if star:
                    seen[k]["star"] = True
                for v in variants:
                    if v not in seen[k]["variants"]:
                        seen[k]["variants"].append(v)
                continue
            rec = {"w": head, "star": star, "variants": variants, "pages": [i]}
            seen[k] = rec
            entries.append(rec)
    return entries, pages, dropped


def report(entries, pages, dropped, probe, self_check):
    ok = True
    if pages:
        print(f"word-list pages: {pages[0][0]}..{pages[-1][0]} ({len(pages)} pages)")
    print(f"entries: {len(entries)}  starred: {sum(1 for e in entries if e['star'])}")
    print(f"with variants: {sum(1 for e in entries if e['variants'])}")
    if dropped:
        print(f"dropped via head_fixups: {dropped}")
    print("probe: " + (f"enabled ({probe.dir})" if probe.enabled else
                       "DISABLED — no dictionary cache; wrap/space repair limited (two-pass bootstrap)"))
    for w in self_check:
        hit = [e for e in entries if canon(e["w"]) == canon(w)
               or any(canon(v) == canon(w) for v in e["variants"])]
        if hit:
            where = "head" if canon(hit[0]["w"]) == canon(w) else f"variant of {hit[0]['w']}"
            print(f"  check {w:16s} -> {where}")
        else:
            ok = False
            print(f"  check {w:16s} -> MISSING")
    bad = [e["w"] for e in entries if re.search(r"[()]|\x01", e["w"])]
    print(f"residual anomalies (paren/placeholder left in headword): {len(bad)} {bad[:10]}")
    if bad:
        ok = False
    return ok


def _resolve(base, p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def main():
    ap = argparse.ArgumentParser(description="Extract syllabus word list from PDF (stage 01).")
    ap.add_argument("--config", required=True, help="YAML config (see config.example.yaml)")
    ap.add_argument("--pdf", help="override extract.pdf_path")
    ap.add_argument("--out", help="override extract.out_path")
    args = ap.parse_args()

    base = os.path.dirname(os.path.abspath(args.config))
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))["extract"]
    pdf = _resolve(base, args.pdf or cfg["pdf_path"])
    out = _resolve(base, args.out or cfg["out_path"])
    probe = DictProbe(_resolve(base, cfg.get("probe_cache_dir") or ""),
                      int(cfg.get("probe_min_file_size", 200)))

    entries, pages, dropped = extract(pdf, int(cfg["page_start"]), int(cfg["page_end"]),
                                      int(cfg.get("min_good_per_page", 3)), probe,
                                      cfg.get("head_fixups") or {})
    ok = report(entries, pages, dropped, probe, cfg.get("self_check_words") or [])
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(entries, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("written:", out)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
