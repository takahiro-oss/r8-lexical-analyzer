#!/usr/bin/env python3
"""
Verify that the manuscript's reported figures reproduce from the public bundle.

This is the data-reproduction half of [FREEZE_REVIEW_GATE] Layer B: it answers
"does an external reader, given only the released bundle, obtain the numbers the
manuscript reports?" It deliberately does NOT compare the manuscript text against
constants; that is proof-reading and belongs elsewhere.

Every expected value below is a figure stated in the manuscript or recorded in the
evidence ledger. Each check recomputes it from the bundle and compares. A single
mismatch exits non-zero.

Kappa is not recomputed here: kappa_compute.py is the canonical script for it and
carries its own ledger gate. Run it separately against the same bundle with
--manifest.

Usage:
    python verify_public_bundle.py --bundle_dir data/frozen/v1_9_public_r4
"""

import argparse
import csv
import io
import json
import math
import os
import statistics
import sys
from collections import Counter

ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

# Genre codes and their expected (n, HIGH, MEDIUM, LOW) from Table 2.
GENRE_EXPECTED = {
    "1": (45, 21, 20, 4),
    "2": (40, 17, 21, 2),
    "3": (34, 28, 6, 0),
    "4": (58, 37, 14, 7),
    "5": (24, 14, 10, 0),
    "6": (4, 1, 2, 1),
}

# Pseudonymised chapter counts stated in the manuscript / Data Availability.
BOOK_EXPECTED = {"book001": 7, "book002": 6, "book003": 6, "book004": 5}

# Book-title stems that must not survive in a released identifier column. Checked
# against corpus_master, cluster_definitions, the results files, supplementary
# table S2, and the two rater label files. The corpus_sources.csv exception this
# comment used to carry is GONE with the file: DEC-085 withholds source URLs from
# the bundle entirely, so no released cell carries a retrieval path.
#
# THE LIST IS NOT IN THIS FILE. Written out here it would name the four book titles
# DEC-022 pseudonymises, so publishing this script would reverse the pseudonymisation
# it exists to enforce. The stems live in an unpublished local configuration file,
# read when present. In any clone of the public repository the file is absent and the
# residue checks report SKIPPED: the run neither passes nor fails on them, and the
# skipped count is printed so that a reader cannot mistake silence for a pass.
# Pending 123 (b) fixed this mechanism; Pending 125 R1 applies it here.
STEMS_CONFIG_ENV = "R8_LOCAL_CONFIG"
STEMS_CONFIG_DEFAULT = "config/publication_safety.local.json"


def load_forbidden_stems():
    """Return the stem list, or None when no local configuration is available."""
    path = os.environ.get(STEMS_CONFIG_ENV) or STEMS_CONFIG_DEFAULT
    if not os.path.exists(path):
        return None
    raw = open(path, "rb").read().decode("utf-8-sig")
    stems = json.loads(raw).get("forbidden_stems")
    if not stems:
        return None
    return [str(x) for x in stems]


FORBIDDEN_STEMS = load_forbidden_stems()

RESULTS_FILES = [
    "results_claude.csv", "results_claude_v2.csv", "results_claude_v3.csv",
    "results_claude_v4.csv", "results_claude_v5.csv",
    "results_gemini_v2.csv", "results_gemini_v3.csv", "results_gemini_v4.csv",
    "results_gemini_v5.csv", "results_gemini_v6.csv",
]


# Supplementary Table S1. The manuscript prints c2b and c3b in Section 5.8 and the
# full ten-test batch is released as supplementary_table_s1.csv. What a reader can
# check from the bundle alone is recorded as EV-sec58-002: every derived column
# follows from the four count columns, and the two count columns themselves do not,
# because the category membership patterns live in scripts/analyze_section58.py,
# which is in neither the bundle nor the public code repository. The two
# implementations below are written here rather than imported, so that agreement
# with the producer is evidence and not a tautology.
S1_CATEGORIES = ["c1a", "c1b", "c2a", "c2b", "c3a", "c3b", "c4a", "c4b", "c5a", "c5c"]
S1_FIELDS = ["bh_q", "category", "ci_95_hi", "ci_95_lo", "fn_n", "fn_positive",
             "nfn_n", "nfn_positive", "odds_ratio", "p_bonferroni", "p_raw"]


def fisher_exact_two_sided(a, b, c, d):
    """Two-sided Fisher exact p for [[a, b], [c, d]], summed over the exact
    hypergeometric distribution. No SciPy dependency: this script imports only
    the standard library and must keep doing so."""
    n = a + b + c + d
    row1 = a + b
    col1 = a + c
    lo = max(0, col1 - (n - row1))
    hi = min(row1, col1)

    def hyp(x):
        return (math.comb(row1, x) * math.comb(n - row1, col1 - x)) / math.comb(n, col1)

    p0 = hyp(a)
    total = 0.0
    for x in range(lo, hi + 1):
        px = hyp(x)
        if px <= p0 * (1 + 1e-9):
            total += px
    return min(1.0, total)


def bh_step_up(ps):
    """Benjamini-Hochberg adjusted p-values, in the input order."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    q = [0.0] * m
    prev = 1.0
    for rank, i in enumerate(reversed(order)):
        prev = min(prev, ps[i] * m / (m - rank))
        q[i] = prev
    return q


def read_csv(path):
    raw = open(path, "rb").read()
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))), raw


class Report(object):
    def __init__(self):
        self.rows = []
        self.failed = 0
        self.skipped = 0

    def check(self, name, got, expected):
        ok = got == expected
        if not ok:
            self.failed += 1
        self.rows.append((name, got, expected, ok))

    def skip(self, name, reason):
        """Record a check that could not be run. Never counted as a pass."""
        self.skipped += 1
        self.rows.append((name, "SKIPPED", reason, None))

    def emit(self):
        width = max(len(r[0]) for r in self.rows)
        for name, got, exp, ok in self.rows:
            if ok is None:
                verdict = "SKIPPED"
            elif ok:
                verdict = "MATCH"
            else:
                verdict = "MISMATCH"
            print("  %-*s  got=%-24s expected=%-24s %s"
                  % (width, name, str(got), str(exp), verdict))
        print()
        total = len(self.rows)
        ran = total - self.skipped
        print("  %d/%d checks matched (%d run, %d skipped)"
              % (ran - self.failed, total, ran, self.skipped))
        return self.failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle_dir", required=True)
    args = ap.parse_args()
    d = args.bundle_dir.rstrip("/\\")
    rep = Report()

    rows, cm_raw = read_csv(d + "/corpus_master.csv")
    valid = [r for r in rows if float(r["cmi"]) > 0]

    def dist(pop, key):
        c = Counter(r[key] for r in pop)
        return (c["HIGH"], c["MEDIUM"], c["LOW"])

    # --- corpus composition ---
    # EV-r196-029 (composition), EV-table3-001 (median, unchanged at n=196).
    rep.check("n total", len(rows), 205)
    rep.check("human label H/M/L (all)", dist(rows, "human_label"), (118, 73, 14))
    rep.check("n valid (cmi>0)", len(valid), 196)
    rep.check("human label H/M/L (valid)", dist(valid, "human_label"), (117, 67, 12))
    rep.check("median CMI (valid)",
              statistics.median(sorted(float(r["cmi"]) for r in valid)), 31.25)

    # --- detection performance ---
    tp = sum(1 for r in valid if r["level"] == "HIGH" and r["human_label"] == "HIGH")
    fp = sum(1 for r in valid if r["level"] == "HIGH" and r["human_label"] != "HIGH")
    fn_valid = sum(1 for r in valid
                   if r["level"] != "HIGH" and r["human_label"] == "HIGH")
    fn_all = sum(1 for r in rows
                 if r["level"] != "HIGH" and r["human_label"] == "HIGH")
    # EV-r196-065.
    rep.check("TP", tp, 41)
    rep.check("FP", fp, 1)
    rep.check("FP identifier",
              [r["target"] for r in valid
               if r["level"] == "HIGH" and r["human_label"] != "HIGH"], ["note223"])
    rep.check("FN (valid subset)", fn_valid, 76)
    rep.check("FN (all 205)", fn_all, 77)

    precision = tp / float(tp + fp)
    recall = tp / float(tp + fn_all)
    f1 = 2 * precision * recall / (precision + recall)
    rep.check("Precision %", round(precision * 100, 1), 97.6)
    rep.check("Recall %", round(recall * 100, 1), 34.7)
    rep.check("F1 %", round(f1 * 100, 1), 51.2)

    # --- author vs automated agreement ---
    exact = sum(1 for r in valid if r["level"] == r["human_label"])
    within1 = sum(1 for r in valid
                  if abs(ORDER[r["level"]] - ORDER[r["human_label"]]) <= 1)
    # EV-r196-063 (exact), EV-r196-064 (within-one).
    rep.check("exact match n/%", (exact, round(100.0 * exact / len(valid), 1)),
              (58, 29.6))
    rep.check("within-1 n/%", (within1, round(100.0 * within1 / len(valid), 1)),
              (146, 74.5))

    # --- Table 2, by genre ---
    for g in sorted(GENRE_EXPECTED):
        sel = [r for r in rows if r["genre_label"].startswith(g + ":")]
        rep.check("Table 2 genre %s" % g,
                  (len(sel),) + dist(sel, "human_label"), GENRE_EXPECTED[g])

    # --- author reason-code rates (manuscript Section 5.3) ---
    # EV-r196-030 / EV-r196-031, author side.
    for code, expected in [("Emotional Induction", 57.7),
                           ("No academic/empirical support", 42.9)]:
        n = sum(1 for r in valid if code in (r["riskfactor_1"],
                                             r["riskfactor_2"],
                                             r["riskfactor_3"]))
        rep.check("reason-code rate: %s" % code,
                  round(100.0 * n / len(valid), 1), expected)

    # --- pseudonymisation integrity ---
    cm_text = cm_raw.decode("utf-8-sig")
    for label, count in sorted(BOOK_EXPECTED.items()):
        rep.check("chapters for %s" % label, cm_text.count(label + "_ch"), count)

    if FORBIDDEN_STEMS is None:
        rep.skip("residual title stems (12 files)", "local stem configuration absent")
    else:
        residual = 0
        for name in ["corpus_master.csv", "cluster_definitions.csv"] + RESULTS_FILES:
            text = open(d + "/" + name, "rb").read().decode("utf-8-sig")
            residual += sum(text.count(s) for s in FORBIDDEN_STEMS)
        rep.check("residual title stems (12 files)", residual, 0)

    dropped = 0
    for name in RESULTS_FILES:
        rs, _ = read_csv(d + "/" + name)
        dropped += 1 if "reason" in rs[0] else 0
    rep.check("results files retaining free-text reason", dropped, 0)
    rep.check("corpus_master retaining ailabel_reason",
              1 if "ailabel_reason" in rows[0] else 0, 0)
    rep.check("corpus_master retaining remarks",
              1 if "remarks" in rows[0] else 0, 0)

    # --- run-level row counts (Table 4 denominators, per DEC-028) ---
    for name, expected in [(f, 217) for f in RESULTS_FILES[:5]] + \
                          [(f, 213) for f in RESULTS_FILES[5:]]:
        rs, _ = read_csv(d + "/" + name)
        rep.check("rows in %s" % name, len(rs), expected)

    # --- supplementary table S2 derives from corpus_master (section 5.10) ---
    # The manuscript cites supplementary_table_s2.csv by filename. Presence in
    # the bundle is not enough: the table must agree with the data released
    # alongside it, or a reader following the citation reaches an unverifiable
    # artefact. The population is regenerated here from corpus_master.csv by the
    # same rule the manuscript states -- EnemyFrame and PropagandaRisk both at
    # the saturation ceiling -- and every reported cell is compared.
    S2_DENSITY = {
        "AuthorityRisk": "authority", "EmotionalRisk": "emotional",
        "LogicalRisk": "logical", "StatisticalRisk": "statistical",
        "HypeRisk": "hype", "ClickbaitRisk": "clickbait", "FearRisk": "fear",
        "AnonymousAuthority": "anonymous_authority",
        "DisclaimerExploit": "disclaimer_exploit",
    }
    s2_rows, s2_raw = read_csv(d + "/supplementary_table_s2.csv")
    sat = [r for r in rows
           if float(r["enemy_frame"]) == 1.0 and float(r["propaganda"]) == 1.0]
    rep.check("S2 population = saturated pair in corpus_master",
              sorted(r["corpus_id"] for r in s2_rows),
              sorted(r["target"] for r in sat))
    by_id = dict((r["target"], r) for r in sat)
    s2_bad = 0
    for r in s2_rows:
        src = by_id.get(r["corpus_id"])
        if src is None:
            s2_bad += 1
            continue
        if float(src["cmi"]) != float(r["cmi"]):
            s2_bad += 1
        if src["level"] != r["classification"]:
            s2_bad += 1
        listed = {}
        if r["other_active_categories"] != "none":
            for part in r["other_active_categories"].split(";"):
                k, v = part.strip().rsplit(" ", 1)
                listed[k] = float(v)
        actual = dict((k, float(src[c])) for k, c in S2_DENSITY.items()
                      if float(src[c]) > 0)
        if listed != actual:
            s2_bad += 1
    rep.check("S2 cells reproduced from corpus_master", s2_bad, 0)
    rep.check("S2 CMI range",
              (min(float(r["cmi"]) for r in s2_rows),
               max(float(r["cmi"]) for r in s2_rows)), (12.0, 45.7))
    if FORBIDDEN_STEMS is None:
        rep.skip("residual title stems in S2", "local stem configuration absent")
    else:
        rep.check("residual title stems in S2",
                  sum(s2_raw.decode("utf-8-sig").count(s) for s in FORBIDDEN_STEMS), 0)

    # --- supplementary table S1 reproduces from its own counts (EV-sec58-002) ---
    s1_rows, _ = read_csv(d + "/supplementary_table_s1.csv")
    rep.check("S1 rows", len(s1_rows), 10)
    rep.check("S1 categories", [r["category"] for r in s1_rows], S1_CATEGORIES)
    rep.check("S1 fields", sorted(s1_rows[0].keys()), S1_FIELDS)

    # The two group sizes are the link between this table and the released data:
    # they are recomputed from corpus_master rather than read from the table.
    nfn_valid = sum(1 for r in valid if r["human_label"] != "HIGH")
    rep.check("S1 fn_n constant across rows",
              sorted(set(int(r["fn_n"]) for r in s1_rows)), [76])
    rep.check("S1 nfn_n constant across rows",
              sorted(set(int(r["nfn_n"]) for r in s1_rows)), [79])
    rep.check("S1 fn_n = FN group in corpus_master", fn_valid, 76)
    rep.check("S1 nfn_n = non-HIGH valid in corpus_master", nfn_valid, 79)

    bad_or = bad_lo = bad_hi = bad_p = bad_bonf = bad_cell = 0
    s1_ps = []
    for r in s1_rows:
        fn, nfn = int(r["fn_n"]), int(r["nfn_n"])
        a = int(r["fn_positive"])
        b = fn - a
        c = int(r["nfn_positive"])
        e = nfn - c
        if not (0 < a < fn and 0 < c < nfn):
            # A zero or full cell leaves the odds ratio and its interval undefined.
            bad_cell += 1
            s1_ps.append(float(r["p_raw"]))
            continue
        orv = (a / float(b)) / (c / float(e))
        se = math.sqrt(1.0 / a + 1.0 / b + 1.0 / c + 1.0 / e)
        lo = math.exp(math.log(orv) - 1.96 * se)
        hi = math.exp(math.log(orv) + 1.96 * se)
        p = fisher_exact_two_sided(a, b, c, e)
        s1_ps.append(p)
        bad_or += round(orv, 4) != float(r["odds_ratio"])
        bad_lo += round(lo, 4) != float(r["ci_95_lo"])
        bad_hi += round(hi, 4) != float(r["ci_95_hi"])
        bad_p += round(p, 4) != float(r["p_raw"])
        bad_bonf += round(min(1.0, p * 10), 4) != float(r["p_bonferroni"])
    rep.check("S1 rows with an undefined odds ratio", bad_cell, 0)
    rep.check("S1 odds_ratio not reproduced", bad_or, 0)
    rep.check("S1 ci_95_lo not reproduced (Woolf)", bad_lo, 0)
    rep.check("S1 ci_95_hi not reproduced (Woolf)", bad_hi, 0)
    rep.check("S1 p_raw not reproduced (Fisher exact)", bad_p, 0)
    rep.check("S1 p_bonferroni not reproduced", bad_bonf, 0)
    s1_q = bh_step_up(s1_ps)
    rep.check("S1 bh_q not reproduced (BH step-up)",
              sum(1 for i, r in enumerate(s1_rows)
                  if round(s1_q[i], 4) != float(r["bh_q"])), 0)
    # NOT a pass and NOT a silent omission: the counts these statistics are computed
    # from cannot be recomputed without the corpus texts, which are not released.
    rep.skip("S1 fn_positive / nfn_positive",
             "needs the corpus texts, which are not released; the patterns are in "
             "CODEBOOK.md section 4.5")

    # --- supplementary table S3 reproduces the contextual validity figures ---
    # Section 5.8 reports a masked single-rater contextual validity evaluation for the
    # two strongest patterns, and states a sensitivity analysis over the indeterminate
    # judgements. supplementary_table_s3.csv carries the instance-level judgements those
    # figures are computed from. Every count, odds ratio, interval and p-value the
    # manuscript prints for that evaluation is recomputed here from the released table.
    #
    # Aggregation rules, exactly as Section 5.8 states them: a document counts as
    # contextually valid if at least one of its instances is judged genuine ("y"); a
    # document whose instances are all indeterminate ("m") is excluded from the main
    # analysis; the sensitivity analysis reassigns every indeterminate instance to
    # genuine, and then to non-genuine, over the unreduced document set.
    #
    # LIMIT, recorded beside the verdict so that a later reader does not take it wider
    # than it is. The "document counts vs S1" check below is NOT independent evidence
    # against the corpus texts: S1 and S3 both descend from
    # scripts/analyze_section58.py, so their agreement cannot establish that either
    # matches the corpus. What it catches is a divergence between two released files --
    # a regeneration or transcription error. The S1 fn_positive / nfn_positive check
    # above stays SKIPPED and is not converted to a pass by anything here.
    S3_PATTERNS = ["c2b", "c3b"]
    S3_FIELDS = ["group", "instance", "judgment", "pattern", "target"]
    S3_MAIN = {("c2b", "FN"): (12, 55), ("c2b", "NFN"): (7, 40),
               ("c3b", "FN"): (12, 51), ("c3b", "NFN"): (11, 37)}
    S3_SENS_GENUINE = {("c2b", "FN"): (14, 55), ("c2b", "NFN"): (8, 41),
                       ("c3b", "FN"): (12, 51), ("c3b", "NFN"): (12, 37)}
    S3_SENS_NON = {("c2b", "FN"): (12, 55), ("c2b", "NFN"): (7, 41),
                   ("c3b", "FN"): (12, 51), ("c3b", "NFN"): (11, 37)}
    # (odds ratio, ci low, ci high, p) as printed in Section 5.8.
    S3_STATS = {"c2b": (1.32, 0.47, 3.71, 0.796),
                "c3b": (0.73, 0.28, 1.89, 0.624)}

    s3_rows, s3_raw = read_csv(d + "/supplementary_table_s3.csv")
    rep.check("S3 rows", len(s3_rows), 552)
    rep.check("S3 fields", sorted(s3_rows[0].keys()), S3_FIELDS)
    rep.check("S3 patterns", sorted(set(r["pattern"] for r in s3_rows)), S3_PATTERNS)
    rep.check("S3 judgments outside y/n/m",
              sum(1 for r in s3_rows if r["judgment"] not in ("y", "n", "m")), 0)
    s3_keys = [(r["pattern"], r["target"], r["instance"]) for r in s3_rows]
    rep.check("S3 duplicate pattern/target/instance",
              len(s3_keys) - len(set(s3_keys)), 0)

    # The group column is not taken on trust: FN membership is re-derived from
    # corpus_master by the same rule the detection-performance checks above use.
    s3_fn = set(r["target"] for r in valid
                if r["level"] != "HIGH" and r["human_label"] == "HIGH")
    rep.check("S3 group label vs corpus_master",
              sum(1 for r in s3_rows
                  if (r["group"] == "FN") != (r["target"] in s3_fn)), 0)

    s3_docs = {}
    for r in s3_rows:
        s3_docs.setdefault((r["pattern"], r["group"]), {}).setdefault(
            r["target"], []).append(r["judgment"])

    # Document counts are the join to supplementary table S1: the number of documents S3
    # carries for a pattern and group is that pattern's positive count in S1.
    s1_by_cat = dict((r["category"], r) for r in s1_rows)
    s3_vs_s1 = 0
    for pat in S3_PATTERNS:
        row = s1_by_cat[pat]
        if len(s3_docs[(pat, "FN")]) != int(row["fn_positive"]):
            s3_vs_s1 += 1
        if len(s3_docs[(pat, "NFN")]) != int(row["nfn_positive"]):
            s3_vs_s1 += 1
    rep.check("S3 document counts vs S1 positive counts", s3_vs_s1, 0)

    def s3_counts(pat, grp, mode):
        """(valid, total) under one aggregation rule. Rules are stated above."""
        sel = s3_docs[(pat, grp)]
        if mode == "main":
            sel = dict((k, v) for k, v in sel.items()
                       if not all(j == "m" for j in v))
            return sum(1 for v in sel.values() if "y" in v), len(sel)
        if mode == "genuine":
            return sum(1 for v in sel.values() if "y" in v or "m" in v), len(sel)
        return sum(1 for v in sel.values() if "y" in v), len(sel)

    for pat in S3_PATTERNS:
        rep.check("S3 %s contextual counts (main)" % pat,
                  (s3_counts(pat, "FN", "main"), s3_counts(pat, "NFN", "main")),
                  (S3_MAIN[(pat, "FN")], S3_MAIN[(pat, "NFN")]))

    def s3_stats(pat, mode):
        a, na = s3_counts(pat, "FN", mode)
        c, nc = s3_counts(pat, "NFN", mode)
        b, e = na - a, nc - c
        orv = (a / float(b)) / (c / float(e))
        se = math.sqrt(1.0 / a + 1.0 / b + 1.0 / c + 1.0 / e)
        return (round(orv, 2),
                round(math.exp(math.log(orv) - 1.96 * se), 2),
                round(math.exp(math.log(orv) + 1.96 * se), 2),
                round(fisher_exact_two_sided(a, b, c, e), 3))

    for pat in S3_PATTERNS:
        rep.check("S3 %s odds ratio / CI / p (main)" % pat,
                  s3_stats(pat, "main"), S3_STATS[pat])

    for mode, table, label in [
            ("genuine", S3_SENS_GENUINE, "indeterminate -> genuine"),
            ("non", S3_SENS_NON, "indeterminate -> non-genuine")]:
        got = dict(((pat, grp), s3_counts(pat, grp, mode))
                   for pat in S3_PATTERNS for grp in ("FN", "NFN"))
        rep.check("S3 sensitivity counts, %s" % label,
                  sorted(got.items()), sorted(table.items()))

    # Section 5.8 states that no sensitivity contrast approached a group difference, at
    # all p > .46. Checked as a count of contrasts falling at or below that bound.
    rep.check("S3 sensitivity contrasts with p <= .46",
              sum(1 for mode in ("genuine", "non") for pat in S3_PATTERNS
                  if s3_stats(pat, mode)[3] <= 0.46), 0)

    if FORBIDDEN_STEMS is None:
        rep.skip("residual title stems in S3", "local stem configuration absent")
    else:
        rep.check("residual title stems in S3",
                  sum(s3_raw.decode("utf-8-sig").count(s) for s in FORBIDDEN_STEMS), 0)

    # --- corpus_sources.csv and corpus_archive_provenance.csv are NOT released.
    # DEC-085 withholds source URLs from every public artefact, and S371-J excluded
    # the provenance file with them. The checks that stood here opened both files;
    # they are removed rather than skipped, because a check for a file the bundle
    # is designed not to carry is not a gap in coverage.

    # --- rater label files (Pending 88) -----------------------------------
    # Both raters' labels enter the bundle under the written consent recorded in
    # Pending 45. Section 5.3's McNemar tests are computed from the reason codes,
    # so the reason columns travel with the labels. reason_2 and reason_3 are
    # empty in every row: that emptiness is the record that up to three reasons
    # could be entered and one was chosen, and is retained rather than dropped.
    # The identifier rename does not apply here -- these files were extracted
    # already carrying book-format labels -- so the residue gate below is what
    # establishes that, rather than the rename count used for the generated files.
    #
    # EXPECTED VALUES: the H/M/L distributions at n=196 are recorded as
    # EV-bundle-002. Unlike the n=202 values they replace, they have a source
    # independent of the files they gate: they were read from the frozen
    # xlsm-derived log 9f2f6754, while these CSVs descend from the r3 CSVs.
    # A mismatch here therefore means the extraction changed; the kappa gate in
    # human_kappa_compute.py is what confirms it.
    RATER_EXPECTED = {
        "rater1_labels.csv": (60, 73, 63),
        "rater2_labels.csv": (106, 63, 27),
    }
    valid_targets = set(r["target"] for r in valid)
    for name, hml in RATER_EXPECTED.items():
        rrows, rraw = read_csv(d + "/" + name)
        rtext = rraw.decode("utf-8-sig")
        rep.check("%s rows" % name, len(rrows), 196)
        rep.check("%s fields" % name, sorted(rrows[0].keys()),
                  ["rater_label", "reason_1", "reason_2", "reason_3", "target"])
        # Set equality, not order: the extraction order differs from
        # corpus_master at 13 positions and every canonical script joins on
        # target, so order carries no meaning here.
        rtargets = [r["target"] for r in rrows]
        rep.check("%s target set = valid subset" % name,
                  set(rtargets) == valid_targets, True)
        rep.check("%s duplicate targets" % name,
                  len(rtargets) - len(set(rtargets)), 0)
        rep.check("%s label H/M/L" % name,
                  tuple(sum(1 for r in rrows if r["rater_label"] == k)
                        for k in ("HIGH", "MEDIUM", "LOW")), hml)
        rep.check("%s labels outside H/M/L" % name,
                  sum(1 for r in rrows if r["rater_label"] not in ORDER), 0)
        rep.check("%s reason_1 empty" % name,
                  sum(1 for r in rrows if not r["reason_1"].strip()), 0)
        rep.check("%s reason_2/3 non-empty" % name,
                  sum(1 for r in rrows
                      if r["reason_2"].strip() or r["reason_3"].strip()), 0)
        rep.check("%s book-format targets" % name,
                  sum(1 for t in rtargets if t.startswith("book0")), 24)
        if FORBIDDEN_STEMS is None:
            rep.skip("residual title stems in %s" % name, "local stem configuration absent")
        else:
            rep.check("residual title stems in %s" % name,
                      sum(rtext.count(s) for s in FORBIDDEN_STEMS), 0)

    print("Layer B -- data reproduction from the public bundle")
    print()
    failed = rep.emit()
    if failed:
        print()
        print("[FAIL] %d check(s) did not reproduce" % failed)
        sys.exit(1)
    print()
    if rep.skipped:
        print("[OK] every check the released files can decide reproduces; "
              "%d check(s) skipped, each named above with what it needs"
              % rep.skipped)
    else:
        print("[OK] every reported figure reproduces from the released bundle")


if __name__ == "__main__":
    main()
