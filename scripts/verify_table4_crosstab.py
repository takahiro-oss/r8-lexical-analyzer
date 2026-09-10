#!/usr/bin/env python3
"""
Verify that manuscript Table 4 reproduces from the public bundle.

THIRD COMPONENT OF [FREEZE_REVIEW_GATE] Layer B, alongside
verify_public_bundle.py and human_kappa_compute.py. It exists as a separate
file rather than as an addition to verify_public_bundle.py for one measured
reason: the released bundle CARRIES verify_public_bundle.log, so changing that
script would leave a file inside a frozen directory that the current code no
longer reproduces, and a frozen directory may not be edited.

WHAT IT CHECKS. Manuscript Section 4.3, Table 4, the cross-tabulation of
automated classification level against human_label over the valid (CMI > 0)
subset, together with its row totals, column totals, grand total, and the
sentence that follows it.

WHY IT EXISTS. The nine cells were computed in a judgment session (S492-J) and
were therefore NOT producer-owned under DEC-081, which requires that a linked
evidence-ledger row name the script that produces the value. This script is that
producer. Its expected values are the ACCEPTANCE TEST fixed at S492-J BEFORE any
producer existed, per DEC-083 rule 3; they are not fitted to this implementation
after the fact.

TOTALS ARE DERIVED FROM THE MATRIX, NOT RECOMPUTED FROM THE POPULATION. Summing
the population again would merely repeat checks verify_public_bundle.py already
makes. Deriving them from the 3x3 matrix tests two things at once: that the
matrix is internally consistent, and that it agrees with a distribution computed
independently elsewhere.

Usage:
    python scripts/verify_table4_crosstab.py --bundle_dir data/frozen/v1_9_public_r4

Exit 0 when every check matches, 1 otherwise.
"""

import argparse
import csv
import io
import sys

LABELS = ["HIGH", "MEDIUM", "LOW"]

# ACCEPTANCE TEST, fixed at S492-J before this script existed (DEC-083 rule 3).
# Source: docs/drafts/drafts_archive/S492-J_pending_edits.md, entry S492-E01.
EXPECT_ROWS = {
    "HIGH": (41, 0, 1),
    "MEDIUM": (27, 7, 1),
    "LOW": (49, 60, 10),
}
EXPECT_ROW_TOTALS = (42, 35, 119)
EXPECT_COL_TOTALS = (117, 67, 12)
EXPECT_GRAND = 196
EXPECT_DIAGONAL = 58
EXPECT_HIGH_OFF_DIAGONAL = 1
# Manuscript L302 states the 205-document distribution. The nine CMI = 0.0
# documents are the whole of the difference, recorded at S449-E06.
EXPECT_ALL_DISTRIBUTION = (118, 73, 14)
EXPECT_DIFFERENCE = (1, 6, 2)


class Report(object):
    def __init__(self):
        self.lines = []
        self.failed = 0

    def check(self, name, got, expected):
        ok = got == expected
        if not ok:
            self.failed += 1
        self.lines.append((name, got, expected, ok))

    def emit(self):
        for name, got, expected, ok in self.lines:
            print("  %-52s got=%-28s expected=%-28s %s"
                  % (name, got, expected, "MATCH" if ok else "FAIL"))
        print()
        print("  %d/%d checks matched" % (len(self.lines) - self.failed,
                                          len(self.lines)))
        return self.failed


def read_csv(path):
    raw = open(path, "rb").read()
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))), raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle_dir", required=True)
    args = ap.parse_args()
    d = args.bundle_dir.rstrip("/\\")
    rep = Report()

    rows, _ = read_csv(d + "/corpus_master.csv")
    valid = [r for r in rows if float(r["cmi"]) > 0]

    # The 3x3 matrix. Rows are the automated level, columns human_label.
    matrix = {}
    for lvl in LABELS:
        matrix[lvl] = tuple(
            sum(1 for r in valid
                if r["level"] == lvl and r["human_label"] == hl)
            for hl in LABELS)

    for lvl in LABELS:
        rep.check("Table 4 row %s (HIGH/MEDIUM/LOW)" % lvl,
                  matrix[lvl], EXPECT_ROWS[lvl])

    rep.check("Table 4 (HIGH,MEDIUM) + (HIGH,LOW)",
              matrix["HIGH"][1] + matrix["HIGH"][2], EXPECT_HIGH_OFF_DIAGONAL)

    row_totals = tuple(sum(matrix[lvl]) for lvl in LABELS)
    rep.check("Table 4 row totals, derived from the matrix",
              row_totals, EXPECT_ROW_TOTALS)

    col_totals = tuple(sum(matrix[lvl][i] for lvl in LABELS)
                       for i in range(3))
    rep.check("Table 4 column totals, derived from the matrix",
              col_totals, EXPECT_COL_TOTALS)

    rep.check("Table 4 grand total, derived from the matrix",
              sum(row_totals), EXPECT_GRAND)

    rep.check("Table 4 diagonal sum, derived from the matrix",
              sum(matrix[lvl][i] for i, lvl in enumerate(LABELS)),
              EXPECT_DIAGONAL)

    all_dist = tuple(sum(1 for r in rows if r["human_label"] == hl)
                     for hl in LABELS)
    rep.check("205-document human_label distribution (manuscript L302)",
              all_dist, EXPECT_ALL_DISTRIBUTION)
    rep.check("difference from the Table 4 column totals",
              tuple(all_dist[i] - col_totals[i] for i in range(3)),
              EXPECT_DIFFERENCE)

    print("Layer B -- manuscript Table 4 reproduction from the public bundle")
    print()
    failed = rep.emit()
    if failed:
        print()
        print("[FAIL] %d check(s) did not reproduce" % failed)
        sys.exit(1)
    print()
    print("[OK] Table 4 reproduces from the released bundle")


if __name__ == "__main__":
    main()
