#!/usr/bin/env python3
"""
Table 4, Human column: gated recount.

WHAT THIS OWNS
    Manuscript Table 4's Human column, three printed cells:
        HIGH 57.3% (121) / MEDIUM 36.0% (76) / LOW 6.6% (14)
    and the column header denominator, Human (n=211).

WHY IT EXISTS
    The printed percentages are derived values that no claim row carries.
    Pending 113 sub-item (7) settles the rule as A-by-default, C where a value
    will move. These three cells MOVE at DEC-072 (denominator 211 -> 205), so
    they are the C case: a producer recomputes them from counts and asserts
    them against the strings the manuscript actually prints.

DENOMINATOR, AND WHY IT IS NOT 196 OR 202
    The Human column counts the WHOLE corpus, CMI = 0.0 documents included,
    because human_label was assigned to all of them. The manuscript states this
    at Table 4's note: the Human column and the two model columns are computed
    over different populations and are not directly comparable as proportions.
    DEC-072 removes six documents from the corpus, so the denominator moves
    211 -> 205. The DEFINITION is unchanged. Section 4.5's kappa populations
    (202 / 198, and now 196 / 192) are a different quantity and are not touched
    here.

GATE DESIGN
    The n=211 gate runs FIRST and must pass before any n=205 value is emitted.
    A gate that only checks the new values proves nothing: it would agree with
    whatever the code happens to compute.

USAGE
    python3 table4_human_recount.py --old <v1_9/corpus_master.csv>
                                    --new <v1_9r/corpus_master.csv>
                                    [--manuscript <R8_preprint_draft_v1_9.md>]
                                    [--out <audit log path>]

READER MODE, the only mode that runs on the released data
    python3 table4_human_recount.py --public_master corpus_master.csv

EXIT
    0 = every gate passed. Non-zero = at least one FAIL; no log is written.
"""

import argparse
import csv
import hashlib
import sys

# ---- recorded values, from the evidence ledger. Not recomputed here. --------
# EV-cmi0-recall-001: full-211 human_label distribution HIGH=121, MEDIUM=76, LOW=14
LEDGER_OLD_COUNTS = {"HIGH": 121, "MEDIUM": 76, "LOW": 14}
LEDGER_OLD_N = 211
# EV-r196-029: full-population distribution at n=205 HIGH=118, MEDIUM=73, LOW=14
LEDGER_NEW_COUNTS = {"HIGH": 118, "MEDIUM": 73, "LOW": 14}
LEDGER_NEW_N = 205
# What the manuscript prints today, Table 4 Human column.
PRINTED_OLD = {"HIGH": "57.3", "MEDIUM": "36.0", "LOW": "6.6"}
# DEC-072 removed identifiers.
DEC072_REMOVED = {"AD_065", "AD_067", "AD_071", "AD_072", "AD_073", "AD_074"}

# PUBLIC MODE expectations, transcribed BEFORE any public-mode run existed so
# that the check is not fitted to its own output. Counts and n: EV-r196-029
# (the LEDGER_NEW_* values above). Printed strings: EV-table4-derivation-001,
# which records the Human column at n=205 as 57.6 (118), 35.6 (73), 6.8 (14).
PUBLIC_PRINTED = {"HIGH": "57.6", "MEDIUM": "35.6", "LOW": "6.8"}


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def read_labels(path):
    """Return {target: human_label} over every row, CMI = 0.0 included."""
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            target = (row.get("target") or "").strip()
            label = (row.get("human_label") or "").strip()
            if target:
                out[target] = label
    return out


def distribution(labels):
    d = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    other = 0
    for v in labels.values():
        if v in d:
            d[v] += 1
        else:
            other += 1
    return d, other


def pct(n, d):
    """One decimal place, the manuscript's printed form."""
    return f"{round(n / d * 100, 1):.1f}"


def public_mode(path):
    """Reader mode. Recompute the Table 4 Human column from the released
    corpus_master.csv and compare counts and printed percentages with the
    recorded values. Writes nothing. Exit 0 only when every check passes."""
    print("Table 4 Human column -- public mode")
    print(f"  input  {path}")
    print(f"  sha256 {sha256(path)}")
    labels = read_labels(path)
    d, other = distribution(labels)
    fails = 0

    def check(name, got, want):
        nonlocal fails
        ok = got == want
        fails += (not ok)
        print(f"  [{'OK  ' if ok else 'FAIL'}] {name}: got {got!r} want {want!r}")

    check("row count", len(labels), LEDGER_NEW_N)
    check("labels outside HIGH/MEDIUM/LOW", other, 0)
    for k in ("HIGH", "MEDIUM", "LOW"):
        check(f"{k} count", d[k], LEDGER_NEW_COUNTS[k])
        check(f"{k} printed %", pct(d[k], LEDGER_NEW_N), PUBLIC_PRINTED[k])
    print(f"RESULT: {fails} FAIL")
    return 0 if fails == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--public_master",
                    help="released corpus_master.csv; runs the reader check only")
    ap.add_argument("--old")
    ap.add_argument("--new")
    ap.add_argument("--manuscript")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.public_master:
        return public_mode(args.public_master)
    for k in ("old", "new"):
        if getattr(args, k) is None:
            ap.error(f"--{k} is required unless --public_master is given")

    lines = []
    fails = []

    def emit(s):
        lines.append(s)
        print(s)

    def check(name, got, want):
        ok = got == want
        emit(f"  [{'OK  ' if ok else 'FAIL'}] {name}: got {got!r} want {want!r}")
        if not ok:
            fails.append(name)

    emit("Table 4 Human column recount")
    emit(f"  old input {args.old}")
    emit(f"            sha256 {sha256(args.old)}")
    emit(f"  new input {args.new}")
    emit(f"            sha256 {sha256(args.new)}")

    old = read_labels(args.old)
    new = read_labels(args.new)
    old_d, old_other = distribution(old)
    new_d, new_other = distribution(new)

    # ---- GATE 1: reproduce the recorded n=211 counts ------------------------
    emit("")
    emit("GATE 1  n=211 counts against EV-cmi0-recall-001")
    check("old row count", len(old), LEDGER_OLD_N)
    check("old labels outside HIGH/MEDIUM/LOW", old_other, 0)
    for k in ("HIGH", "MEDIUM", "LOW"):
        check(f"old {k}", old_d[k], LEDGER_OLD_COUNTS[k])
    check("old counts close to n", sum(old_d.values()), LEDGER_OLD_N)

    # ---- GATE 2: reproduce the printed percentages -------------------------
    emit("")
    emit("GATE 2  n=211 printed percentages, count / denominator rounded to 1 dp")
    for k in ("HIGH", "MEDIUM", "LOW"):
        check(f"printed {k}", pct(old_d[k], LEDGER_OLD_N), PRINTED_OLD[k])

    # ---- GATE 3: the manuscript still prints them ---------------------------
    if args.manuscript:
        emit("")
        emit("GATE 3  the manuscript still prints these strings")
        text = open(args.manuscript, encoding="utf-8-sig").read()
        emit(f"  manuscript sha256 {sha256(args.manuscript)}")
        for k in ("HIGH", "MEDIUM", "LOW"):
            cell = f"{PRINTED_OLD[k]}% ({LEDGER_OLD_COUNTS[k]})"
            check(f"cell {k} occurs exactly once", text.count(cell), 1)
        check("header 'Human (n=211)' occurs exactly once",
              text.count("Human (n=211)"), 1)
    else:
        emit("")
        emit("GATE 3  SKIPPED, no --manuscript given")

    if fails:
        emit("")
        emit(f"RESULT: FAIL ({len(fails)}) -> {fails}")
        emit("No n=205 value is emitted and no log is written.")
        return 1

    # ---- CLOSURE: the DEC-072 removals account for the whole change ---------
    emit("")
    emit("CLOSURE  the six DEC-072 removals account for the whole of the change")
    removed = set(old) - set(new)
    check("removed set equals DEC-072", sorted(removed), sorted(DEC072_REMOVED))
    check("added set empty", sorted(set(new) - set(old)), [])
    check("new row count", len(new), LEDGER_NEW_N)
    check("new labels outside HIGH/MEDIUM/LOW", new_other, 0)
    for k in ("HIGH", "MEDIUM", "LOW"):
        check(f"new {k} against EV-r196-029", new_d[k], LEDGER_NEW_COUNTS[k])
    moved = {k: old_d[k] - new_d[k] for k in old_d}
    check("per-label decrease sums to 6", sum(moved.values()), 6)
    check("every retained row keeps its label",
          all(old[t] == new[t] for t in new), True)

    if fails:
        emit("")
        emit(f"RESULT: FAIL ({len(fails)}) -> {fails}")
        return 1

    # ---- EMIT: the n=205 values --------------------------------------------
    emit("")
    emit("n=205 VALUES, for the block 2 manuscript edit")
    emit(f"  denominator {LEDGER_NEW_N}  (was {LEDGER_OLD_N}; definition unchanged, whole corpus)")
    for k in ("HIGH", "MEDIUM", "LOW"):
        emit(f"  {k:6s} {PRINTED_OLD[k]}% ({old_d[k]})  ->  "
             f"{pct(new_d[k], LEDGER_NEW_N)}% ({new_d[k]})   "
             f"[removed {moved[k]}]")

    emit("")
    emit(f"RESULT: 0 FAIL, ALL PASS")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"\nlog written: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
