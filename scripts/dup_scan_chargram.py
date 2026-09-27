# scripts/dup_scan_chargram.py
# Pending 97 step 1-b, third pass: character n-gram comparison.
# READ-ONLY. Opens files for reading only. Writes nothing, deletes nothing.
# Prints identifiers, counts and ratios only -- never document text
# ([COMMON] Third-Party Information Handling [4]).
#
# WHY THIS EXISTS. dup_scan_full.py and dup_scan_containment.py both compare
# sequences or sets of LINES. Three documents of record carry no usable line
# structure -- vol01 holds its whole body on one line (PDF extraction), web141 has
# four lines, sn233 has two -- so both earlier passes silently compared nothing for
# them. They were reported as excluded, not as checked. This pass removes the
# dependence on line breaks by comparing sets of character n-grams.
#
# Measure: containment = |NA intersect NB| / min(|NA|, |NB|), where N is the set of
# distinct character n-grams of the whitespace-stripped text.
#
# The script runs a CALIBRATION block first, over pairs whose status is already
# settled by measurement, and refuses to report TARGET results if calibration does
# not reproduce. A measure that cannot separate known duplicates from known
# non-duplicates says nothing about unknown pairs.

import argparse
import csv
import os
import sys

HEADER_PREFIXES = ("[CATEGORY]", "[SOURCE]", "[DATE]")
HEADER_EXACT = ("[TEXT]",)

NGRAM = 12
REPORT_MIN = 0.30   # TARGET pairs at or above this are printed
TOP_N = 20

# Settled by character-weighted line comparison, S285-J. DUP are the six pairs
# that share 96.5% or more of the shorter document; NOT_DUP are the three that
# share 76.0% or less. The 20-point gap between the two groups is what
# calibration must reproduce.
CAL_DUP = [("AD_034", "AD_065"), ("AD_037", "AD_071"), ("AD_038", "AD_072"),
           ("AD_040", "AD_074"), ("AD_035", "AD_067"), ("AD_039", "AD_073")]
CAL_NOT = [("AD_042", "AD_079"), ("web132", "web133"), ("web145", "web146")]

TARGETS = ["vol01", "web141", "sn233"]


def flatten(text):
    """Drop archive header lines, then remove every whitespace character.
    Returns one string. Line breaks carry no information here by design."""
    keep = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith(HEADER_PREFIXES) or s in HEADER_EXACT:
            continue
        keep.append(s)
    return "".join("".join(x.split()) for x in keep)


def grams(s, n=NGRAM):
    if len(s) < n:
        return set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def containment(ga, gb):
    if not ga or not gb:
        return None
    return len(ga & gb) / min(len(ga), len(gb))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--clean_dir", required=True)
    args = ap.parse_args()

    print("=== dup_scan_chargram.py  (READ-ONLY) ===")
    print("master    :", args.master)
    print("clean_dir :", args.clean_dir)
    print(f"measure   : containment over distinct character {NGRAM}-grams")
    print(f"targets   : {TARGETS}")

    with open(args.master, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    targets = [r["target"] for r in rows]
    print("master rows        :", len(rows))
    print("master targets uniq:", len(set(targets)))
    if len(set(targets)) != len(targets):
        print("[FAIL] duplicate target identifiers in master")
        return 2

    on_disk = sorted(x for x in os.listdir(args.clean_dir) if x.endswith(".txt"))
    stem_exact = {x[:-4]: x for x in on_disk}
    stem_lower = {}
    for x in on_disk:
        stem_lower.setdefault(x[:-4].lower(), []).append(x)

    mapping = {}
    missing = []
    for t in targets:
        if t in stem_exact:
            mapping[t] = stem_exact[t]
        else:
            cands = stem_lower.get(t.lower(), [])
            if len(cands) == 1:
                mapping[t] = cands[0]
            else:
                missing.append(t)
    print("mapped             :", len(mapping))
    print("targets w/o file   :", len(missing), missing if missing else "")
    if missing:
        print("[FAIL] every master target must map to a file; nothing was compared")
        return 2

    def load(t):
        """Build one document's gram set on demand. Sets are not retained for
        the whole corpus: at 211 documents that is an unmeasured memory cost,
        and only the targets and the calibration members are needed at once."""
        with open(os.path.join(args.clean_dir, mapping[t]),
                  encoding="utf-8-sig", errors="replace") as f:
            raw = f.read()
        s = flatten(raw)
        return s, grams(s)

    held = {}
    for t in set(TARGETS) | {x for p in CAL_DUP + CAL_NOT for x in p}:
        if t in mapping:
            held[t] = load(t)
    print("gram sets held in memory:", len(held),
          "(targets and calibration members only)")

    # --- calibration ---------------------------------------------------
    print()
    print("=== CALIBRATION  known pairs, measured before any target is reported ===")
    missing_cal = [p for p in CAL_DUP + CAL_NOT
                   if p[0] not in held or p[1] not in held]
    if missing_cal:
        print("[FAIL] calibration pair absent from the corpus:", missing_cal)
        return 2

    dup_vals, not_vals = [], []
    for a, b in CAL_DUP:
        c = containment(held[a][1], held[b][1])
        dup_vals.append(c)
        print(f"  DUP      {a} .. {b:8s} containment={c:.4f}")
    for a, b in CAL_NOT:
        c = containment(held[a][1], held[b][1])
        not_vals.append(c)
        print(f"  NOT_DUP  {a} .. {b:8s} containment={c:.4f}")

    lo_dup, hi_not = min(dup_vals), max(not_vals)
    print(f"  lowest DUP={lo_dup:.4f}  highest NOT_DUP={hi_not:.4f}  "
          f"gap={lo_dup - hi_not:+.4f}")
    if lo_dup <= hi_not:
        print("[FAIL] calibration did not separate the two groups; "
              "TARGET results are not reported")
        return 3
    print("  separation holds; TARGET results follow")

    # --- targets -------------------------------------------------------
    print()
    print(f"=== TARGETS  each of {TARGETS} against all other documents of record ===")
    live = [t for t in TARGETS if t in mapping and held.get(t, (None, set()))[1]]
    absent = [t for t in TARGETS if t not in mapping]
    tiny = [t for t in TARGETS if t in mapping and not held[t][1]]
    if absent:
        print("  [SKIP] not documents of record in this master:", absent)
    if tiny:
        print(f"  [SKIP] shorter than {NGRAM} characters, not comparable:", tiny)

    scored = {t: [] for t in live}
    skipped_short = []
    compared = 0
    for o in sorted(mapping):
        if o in live:
            continue
        text_o, go = held[o] if o in held else load(o)
        if not go:
            skipped_short.append(o)
            continue
        compared += 1
        for t in live:
            c = containment(held[t][1], go)
            scored[t].append((c, o, len(go)))
        del go

    print(f"  documents compared against each target: {compared}")
    print(f"  documents skipped as shorter than {NGRAM} chars:",
          len(skipped_short), skipped_short if skipped_short else "")

    for t in live:
        rows_t = sorted(scored[t], reverse=True)
        hits = [r for r in rows_t if r[0] >= REPORT_MIN]
        print(f"\n  --- {t}  chars={len(held[t][0])}  grams={len(held[t][1])} ---")
        print(f"      at or above {REPORT_MIN}: {len(hits)}")
        for c, o, go in rows_t[:TOP_N]:
            mark = "  <== at/above report threshold" if c >= REPORT_MIN else ""
            print(f"      {c:.4f}  {t} .. {o}  (grams {len(held[t][1])}/{go}){mark}")

    print()
    print("=== SUMMARY ===")
    print("calibration lowest DUP     :", f"{lo_dup:.4f}")
    print("calibration highest NOT_DUP:", f"{hi_not:.4f}")
    print("targets examined           :", len(live))
    print("NOTE: a high containment here is a CANDIDATE. Confirmation is a read of")
    print("      the shared span and is outside this script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
