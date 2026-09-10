#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
table2_hp60_recount_r196.py

PRODUCER for two n=196 measurements that no evidence_ledger row currently owns,
identified at S320-J while fixing the Section 4.3 block-2 wording:

  MEASUREMENT A -- Table 2 (Section 4.2, manuscript L275-L281) genre x human_label
                   cell counts, and the manuscript L269 prose genre counts.
                   *** ALREADY OWNED. *** EV-table2-001 is VERIFIED and owns these
                   cells; its producer is scripts/table2_recount.py and its log is
                   data/frozen/v1_9r/audit_table2_v1_9r.txt
                   (033a10240da764e7d6cd2aa0e74038a1310790964c67a5a7480e9daf53ba080e).
                   S320-J initially recorded this set as unowned. That was an
                   assertion of absence made without inspecting the object, the
                   Pending 109 shape; corrected in the same session on finding
                   handout/S300-J_table2_recount_v2.py. Section 2 below is retained
                   as an INDEPENDENT CROSS-CHECK against EV-table2-001, not as a
                   new claim. Two producers reading the same inputs must agree;
                   disagreement is a defect.
  MEASUREMENT B -- Section 4.3 (L300) high-precision mode (CMI >= 60) classification
                   metrics: TP, FP, FN, Precision, Recall.
                   *** UNOWNED. *** This is the deliverable. Searched S320-J across
                   the whole ledger for the tokens '>= 60', 'high-precision',
                   'FN 115', '115' and '100.0'; the three hits are unrelated rows
                   (EV-book-003, EV-script-001, EV-instr-003). EV-r196-063, -064,
                   -065, EV-perf-003 and EV-prf-005 cover the standard mode and the
                   specificity only.

GATE DISCIPLINE (DEC-048 pattern): the script FIRST recomputes every affected value
on the pre-deduplication population and asserts equality with the values printed in
the EN canonical. If any gate check fails the script exits non-zero and writes no
n=196 result. Reproducing the printed values is what establishes that this
computation is the one that produced them.

DEFINITIONS, stated explicitly because they are not self-evident from the manuscript:
  Ground truth  = human_label, over the WHOLE population (CMI = 0 documents included).
  Prediction    = automated level by CMI threshold, over VALID documents (CMI > 0).
  Standard mode = CMI >= 41.  High-precision mode = CMI >= 60.
  FN            = (all human_label HIGH documents) - TP.  This is the all-documents
                  FN definition; it is the one the manuscript prints, confirmed at
                  n=202 by 79 = 121 - 42 and at standard mode by EV-r196-065.
  Precision     = TP / (TP + FP).   Recall = TP / (TP + FN).
  Percentages   = one decimal place, half-up.

INPUTS (both read-only, hash-checked at run time):
  data/frozen/v1_9/corpus_master.csv   b562425accd95cb64cd69b2462d6ddc3592fe0997d781b032742d3de0aaee362
  data/frozen/v1_9r/corpus_master.csv  57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b

OUTPUT:
  data/frozen/v1_9r/audit_table2_hp60_v1_9r.txt

Exit 0 only if every gate check passes.

Reader mode, the only mode that runs on the released data:
    python scripts/table2_hp60_recount_r196.py --public_master corpus_master.csv
Run with no arguments, the script runs the internal gate above and writes its
audit log; that mode needs the unreleased frozen inputs.
"""

import csv
import hashlib
import os
import sys
from decimal import Decimal, ROUND_HALF_UP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD_CSV = os.path.join(ROOT, "data", "frozen", "v1_9", "corpus_master.csv")
NEW_CSV = os.path.join(ROOT, "data", "frozen", "v1_9r", "corpus_master.csv")
OUT = os.path.join(ROOT, "data", "frozen", "v1_9r", "audit_table2_hp60_v1_9r.txt")

OLD_SHA = "b562425accd95cb64cd69b2462d6ddc3592fe0997d781b032742d3de0aaee362"
NEW_SHA = "57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b"

GENRES = [
    ("1: \u6295\u8cc7\u30fb\u91d1\u878d", "Investment/Finance"),
    ("2: \u30ab\u30eb\u30c8\u30fb\u5b97\u6559", "Cult/Religion"),
    ("3: \u604b\u611b\u30fb\u4eba\u9593\u95a2\u4fc2", "Romance/Relationships"),
    ("4: \u6559\u80b2\u30fb\u81ea\u5df1\u5553\u767a", "Education/Self-help"),
    ("5: \u653f\u6cbb\u30fb\u9670\u8b00", "Politics/Conspiracy"),
    ("6: \u305d\u306e\u4ed6", "Other"),
]
LABELS = ["HIGH", "MEDIUM", "LOW"]

STD_THRESHOLD = 41.0
HP_THRESHOLD = 60.0

# PUBLIC MODE expectations at the deduplicated population, transcribed BEFORE any
# public-mode run existed so that the check is not fitted to its own output.
# hp60: EV-hp60-001 (TP 6, FP 0, FN 112, Precision 100.0, Recall 5.1).
# std, all-documents FN definition: EV-r196-065 (TP 41, FP 1, FN 77, Recall
# 34.7; Precision 97.6 = 41/42). n_total, n_valid, all_high: EV-r196-029.
PUBLIC_EXPECT = {
    "hp60": {"n_total": 205, "n_valid": 196, "all_high": 118, "TP": 6, "FP": 0,
             "FN": 112, "Precision": 100.0, "Recall": 5.1},
    "std":  {"n_total": 205, "n_valid": 196, "all_high": 118, "TP": 41, "FP": 1,
             "FN": 77, "Precision": 97.6, "Recall": 34.7},
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pct1(num, den):
    if den == 0:
        return None
    v = Decimal(num) * Decimal(100) / Decimal(den)
    return float(v.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def table2(rows):
    out = {}
    for key, _en in GENRES:
        sub = [r for r in rows if r["genre_label"] == key]
        out[key] = {
            "n": len(sub),
            "HIGH": sum(1 for r in sub if r["human_label"] == "HIGH"),
            "MEDIUM": sum(1 for r in sub if r["human_label"] == "MEDIUM"),
            "LOW": sum(1 for r in sub if r["human_label"] == "LOW"),
        }
    out["TOTAL"] = {
        "n": len(rows),
        "HIGH": sum(1 for r in rows if r["human_label"] == "HIGH"),
        "MEDIUM": sum(1 for r in rows if r["human_label"] == "MEDIUM"),
        "LOW": sum(1 for r in rows if r["human_label"] == "LOW"),
    }
    return out


def mode_metrics(rows, threshold):
    valid = [r for r in rows if float(r["cmi"]) > 0]
    predicted = [r for r in valid if float(r["cmi"]) >= threshold]
    tp = sum(1 for r in predicted if r["human_label"] == "HIGH")
    fp = len(predicted) - tp
    all_high = sum(1 for r in rows if r["human_label"] == "HIGH")
    fn = all_high - tp
    return {
        "n_total": len(rows),
        "n_valid": len(valid),
        "predicted": len(predicted),
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "all_high": all_high,
        "Precision": pct1(tp, tp + fp),
        "Recall": pct1(tp, tp + fn),
    }


def public_mode(path):
    """Reader mode. Recompute the high-precision (CMI >= 60) and standard
    (CMI >= 41) classification metrics from the released corpus_master.csv and
    compare them with the recorded values. Writes nothing. Exit 0 only when
    every value matches."""
    print("table2_hp60_recount_r196.py -- public mode")
    print("corpus_master : %s" % path)
    print("  sha256      : %s" % sha256(path))
    rows = load(path)
    fails = checks = 0
    for mode, thr in (("hp60", HP_THRESHOLD), ("std", STD_THRESHOLD)):
        m = mode_metrics(rows, thr)
        for k, exp in PUBLIC_EXPECT[mode].items():
            ok = m[k] == exp
            fails += (not ok)
            checks += 1
            print("  %-4s %-10s computed=%-8s expected=%-8s [%s]"
                  % (mode, k, m[k], exp, "OK" if ok else "FAIL"))
    print("RESULT: %d checks, %d FAIL" % (checks, fails))
    return 0 if fails == 0 else 1


def main():
    if len(sys.argv) > 1:
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--public_master", required=True,
                        help="released corpus_master.csv; runs the reader check only")
        return public_mode(ap.parse_args().public_master)
    lines = []
    w = lines.append

    for path, expect in ((OLD_CSV, OLD_SHA), (NEW_CSV, NEW_SHA)):
        if not os.path.isfile(path):
            print("MISSING INPUT: %s" % path)
            return 2
        got = sha256(path)
        if got != expect:
            print("INPUT HASH MISMATCH: %s\n  expected %s\n  got      %s"
                  % (path, expect, got))
            return 2

    old = load(OLD_CSV)
    new = load(NEW_CSV)

    w("audit_table2_hp60_v1_9r.txt")
    w("PRODUCER: scripts/table2_hp60_recount_r196.py")
    w("ORIGIN:   S320-J spec 01. Two manuscript value sets with no owning ledger row.")
    w("INPUT old (n=%d): data/frozen/v1_9/corpus_master.csv  %s" % (len(old), OLD_SHA))
    w("INPUT new (n=%d): data/frozen/v1_9r/corpus_master.csv %s" % (len(new), NEW_SHA))
    w("")

    # ---------------- GATE: reproduce the printed n=202-basis values ----------------
    w("--- SECTION 1: GATE (reproduce the EN canonical's printed values) ---")
    t_old = table2(old)
    m_old_std = mode_metrics(old, STD_THRESHOLD)
    m_old_hp = mode_metrics(old, HP_THRESHOLD)

    gate = []

    # Table 2 as printed in the manuscript (L275-L281).
    printed_t2 = {
        "1: \u6295\u8cc7\u30fb\u91d1\u878d": (49, 22, 23, 4),
        "2: \u30ab\u30eb\u30c8\u30fb\u5b97\u6559": (40, 17, 21, 2),
        "3: \u604b\u611b\u30fb\u4eba\u9593\u95a2\u4fc2": (36, 30, 6, 0),
        "4: \u6559\u80b2\u30fb\u81ea\u5df1\u5553\u767a": (58, 37, 14, 7),
        "5: \u653f\u6cbb\u30fb\u9670\u8b00": (24, 14, 10, 0),
        "6: \u305d\u306e\u4ed6": (4, 1, 2, 1),
        "TOTAL": (211, 121, 76, 14),
    }
    for key, (n, hi, me, lo) in printed_t2.items():
        c = t_old[key]
        gate.append(("Table2 %-24s n" % key, c["n"], n))
        gate.append(("Table2 %-24s HIGH" % key, c["HIGH"], hi))
        gate.append(("Table2 %-24s MEDIUM" % key, c["MEDIUM"], me))
        gate.append(("Table2 %-24s LOW" % key, c["LOW"], lo))

    # Standard mode, printed at L300. Present as a cross-check on the definitions.
    gate.append(("std TP", m_old_std["TP"], 42))
    gate.append(("std FP", m_old_std["FP"], 1))
    gate.append(("std FN", m_old_std["FN"], 79))
    gate.append(("std Precision", m_old_std["Precision"], 97.7))
    gate.append(("std Recall", m_old_std["Recall"], 34.7))

    # High-precision mode, printed at L300. This is MEASUREMENT B's gate.
    gate.append(("hp60 TP", m_old_hp["TP"], 6))
    gate.append(("hp60 FP", m_old_hp["FP"], 0))
    gate.append(("hp60 FN", m_old_hp["FN"], 115))
    gate.append(("hp60 Precision", m_old_hp["Precision"], 100.0))
    gate.append(("hp60 Recall", m_old_hp["Recall"], 5.0))

    fails = 0
    for name, got, exp in gate:
        ok = (got == exp)
        if not ok:
            fails += 1
        w("  %-4s %-40s got=%-8s expected=%s" % ("OK" if ok else "FAIL", name, got, exp))
    w("")
    w("GATE: %d checks, %d FAIL" % (len(gate), fails))
    w("")

    if fails:
        w("ABORTED. No n=196 result is written when the gate fails.")
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        print("\n".join(lines))
        return 1

    # ---------------- MEASUREMENT A ----------------
    w("--- SECTION 2: MEASUREMENT A -- Table 2 at the deduplicated population ---")
    t_new = table2(new)
    w("  %-24s %-18s %-18s" % ("genre", "n=211 (n/H/M/L)", "n=205 (n/H/M/L)"))
    for key, en in GENRES + [("TOTAL", "Total")]:
        a, b = t_old[key], t_new[key]
        w("  %-24s %-18s %-18s   %s" % (
            en,
            "%d/%d/%d/%d" % (a["n"], a["HIGH"], a["MEDIUM"], a["LOW"]),
            "%d/%d/%d/%d" % (b["n"], b["HIGH"], b["MEDIUM"], b["LOW"]),
            "MOVED" if a != b else "unchanged"))
    w("")

    # ---------------- MEASUREMENT B ----------------
    w("--- SECTION 3: MEASUREMENT B -- CMI >= 60 high-precision mode at n=196 ---")
    m_new_hp = mode_metrics(new, HP_THRESHOLD)
    m_new_std = mode_metrics(new, STD_THRESHOLD)
    for label, a, b in (("high-precision (CMI >= 60)", m_old_hp, m_new_hp),
                        ("standard (CMI >= 41)", m_old_std, m_new_std)):
        w("  %s" % label)
        for k in ("n_total", "n_valid", "all_high", "predicted", "TP", "FP", "FN",
                  "Precision", "Recall"):
            w("    %-12s %-10s -> %-10s %s" % (
                k, a[k], b[k], "MOVED" if a[k] != b[k] else "unchanged"))
        w("")

    # ---------------- CLOSURE ----------------
    w("--- SECTION 4: CLOSURE CHECKS ---")
    closure = []
    tn = t_new["TOTAL"]
    genre_sum = [sum(t_new[k]["n"] for k, _ in GENRES),
                 sum(t_new[k]["HIGH"] for k, _ in GENRES),
                 sum(t_new[k]["MEDIUM"] for k, _ in GENRES),
                 sum(t_new[k]["LOW"] for k, _ in GENRES)]
    closure.append(("genre column sums == Total row",
                    tuple(genre_sum), (tn["n"], tn["HIGH"], tn["MEDIUM"], tn["LOW"])))
    closure.append(("Total row == EV-r196-029 (205/118/73/14)",
                    (tn["n"], tn["HIGH"], tn["MEDIUM"], tn["LOW"]), (205, 118, 73, 14)))
    closure.append(("H+M+L == n", tn["HIGH"] + tn["MEDIUM"] + tn["LOW"], tn["n"]))
    closure.append(("std TP == EV-r196-065 (41)", m_new_std["TP"], 41))
    closure.append(("std FN == EV-r196-065 (77)", m_new_std["FN"], 77))
    closure.append(("hp60 FN == all_high - TP", m_new_hp["FN"],
                    m_new_hp["all_high"] - m_new_hp["TP"]))
    cfails = 0
    for name, got, exp in closure:
        ok = (got == exp)
        if not ok:
            cfails += 1
        w("  %-4s %-42s got=%-22s expected=%s" % ("OK" if ok else "FAIL", name, got, exp))
    w("")
    w("CLOSURE: %d checks, %d FAIL" % (len(closure), cfails))
    w("")
    w("NOT APPLIED to the manuscript. This script writes only its own audit log.")
    w("RESULT: %s" % ("PASSED" if cfails == 0 else "FAILED"))

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("")
    print("audit log written: %s" % OUT)
    print("sha256: %s" % sha256(OUT))
    return 0 if cfails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
