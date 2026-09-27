"""llm_input_truncation.py -- the 8,000-character input truncation of the two model runs (S554-J).

WHAT IT OWNS. Section 3.8 L219 of manuscript 881f4ed5 prints, for the prompt truncation
PROMPT_TEMPLATE.format(text=text[:8000]) in ailabel/ailabel_claude.py and ailabel_gemini.py:
53 of the 205 corpus documents exceed 8,000 characters, 52 of them in the n = 196 valid set;
across the 53 the models received 424,000 of 971,585 characters, 43.6%; HIGH 39 of 117
against non-HIGH 13 of 79, Fisher's exact test two-sided p = .009; MEDIUM 10 of 67, LOW 3 of 12.
It supersedes, as a producer, handout/S435-J_measure_trunc.py 6ef660eb, which measured the
same quantities S435-J but printed no p value and is gitignored.

METHOD. Path resolution is NOT reimplemented: find_text_file is extracted verbatim from
ailabel/ailabel_claude.py at run time and exec'd, so resolution is the annotation run's.
Text is read as that run reads it: open(path, encoding="utf-8", errors="ignore").read().
A document resolving to a .pdf (read by PyMuPDF in the annotation run) is a HALT, not
handled here. Fisher's exact test is the two-sided sum of hypergeometric probabilities no
greater than the observed table's (relative tolerance 1e-7), the definition scipy uses.

GATES, before any result is printed: the input hashes of data/frozen/v1_9r/corpus_master.csv
and ailabel/ailabel_claude.py; exactly one text[:8000] in the latter; 205 rows, 196 with
CMI > 0, human_label 117 / 67 / 12 among the 196; every target resolved, none to a .pdf.
Then every printed value is compared with the manuscript's; any mismatch is RESULT: FAIL.

Prints NO document text and NO target identifier (targets carry title stems, DEC-022):
counts, character totals and the test only. Needs the corpus texts under corpus/, which are
not released (DEC-085). Standard library only. Reads; writes nothing. Run from anywhere.
"""
import csv
import hashlib
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "data", "frozen", "v1_9r", "corpus_master.csv")
MASTER_SHA = "57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b"
SRC = os.path.join(ROOT, "ailabel", "ailabel_claude.py")
SRC_SHA = "1069cdae3593dd4251a73cc5206c8accfda31b6a01335ffa492cbd2d93190bae"
CORPUS = os.path.join(ROOT, "corpus")
LIMIT = 8000

# As printed at L219 of manuscript 881f4ed5.
PRINTED = {
    "over_all": 53, "over_valid": 52, "kept": 424000, "total": 971585, "pct": "43.6",
    "HIGH": (39, 117), "nonHIGH": (13, 79), "MEDIUM": (10, 67), "LOW": (3, 12), "p": ".009",
}


def fail(msg):
    print("GATE FAIL:", msg)
    print("RESULT: FAIL (%s)" % msg)
    sys.exit(2)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def log_comb(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher_two_sided(a, b, c, d):
    """Two-sided Fisher exact p for [[a, b], [c, d]]."""
    r1, c1, n = a + b, a + c, a + b + c + d
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)

    def pr(x):
        return math.exp(log_comb(r1, x) + log_comb(n - r1, c1 - x) - log_comb(n, c1))
    p_obs = pr(a)
    return min(1.0, sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p_obs * (1 + 1e-7)))


def load_find_text_file(src_path):
    src = open(src_path, encoding="utf-8").read()
    start = src.find("def find_text_file")
    if start < 0:
        fail("find_text_file not found in ailabel_claude.py")
    nxt = src.find("\ndef ", start + 1)
    ns = {"os": os, "re": re}
    exec(compile(src[start:nxt] if nxt > 0 else src[start:], src_path, "exec"), ns)
    return ns["find_text_file"], src


def main():
    print("PRODUCER scripts/llm_input_truncation.py argv=%s" % sys.argv[1:])
    for label, path, want in (("data/frozen/v1_9r/corpus_master.csv", MASTER, MASTER_SHA),
                              ("ailabel/ailabel_claude.py", SRC, SRC_SHA)):
        if not os.path.exists(path):
            fail("missing " + label)
        got = sha(path)
        print("INPUT %s %s" % (label, got))
        if got != want:
            fail("hash mismatch " + label)
    find_text_file, src = load_find_text_file(SRC)
    n_slice = src.count("text=text[:%d]" % LIMIT)
    print("GATE text[:%d] occurrences in ailabel_claude.py = %d" % (LIMIT, n_slice))
    if n_slice != 1:
        fail("truncation literal count")

    rows = list(csv.DictReader(open(MASTER, encoding="utf-8-sig")))
    valid = [r for r in rows if float(r["cmi"]) > 0]
    vl = {k: sum(r["human_label"] == k for r in valid) for k in ("HIGH", "MEDIUM", "LOW")}
    print("GATE rows=%d valid=%d valid_labels=%d/%d/%d"
          % (len(rows), len(valid), vl["HIGH"], vl["MEDIUM"], vl["LOW"]))
    if (len(rows), len(valid), vl["HIGH"], vl["MEDIUM"], vl["LOW"]) != (205, 196, 117, 67, 12):
        fail("population")

    recs, unresolved, pdf = [], 0, 0
    for r in rows:
        path = find_text_file(r["target"], CORPUS)
        if not path:
            unresolved += 1
            continue
        if path.lower().endswith(".pdf"):
            pdf += 1
            continue
        with open(path, encoding="utf-8", errors="ignore") as fh:
            n = len(fh.read())
        recs.append((n, r["human_label"], float(r["cmi"]) > 0))
    print("GATE resolved=%d unresolved=%d pdf=%d" % (len(recs), unresolved, pdf))
    if unresolved or pdf or len(recs) != 205:
        fail("text resolution")
    print("GATE PASS")

    over = [x for x in recs if x[0] > LIMIT]
    over_v = [x for x in over if x[2]]
    kept = sum(min(x[0], LIMIT) for x in over)
    total = sum(x[0] for x in over)
    pct = "%.1f" % (100.0 * kept / total)
    lab = {k: (sum(x[1] == k for x in over_v), vl[k]) for k in ("HIGH", "MEDIUM", "LOW")}
    non = (lab["MEDIUM"][0] + lab["LOW"][0], vl["MEDIUM"] + vl["LOW"])
    a, n1 = lab["HIGH"]
    c, n2 = non
    p = fisher_two_sided(a, n1 - a, c, n2 - c)
    p_print = ("%.3f" % p).lstrip("0")
    got = {"over_all": len(over), "over_valid": len(over_v), "kept": kept, "total": total,
           "pct": pct, "HIGH": lab["HIGH"], "nonHIGH": non, "MEDIUM": lab["MEDIUM"],
           "LOW": lab["LOW"], "p": p_print}

    print("RESULT over_all=%d over_valid=%d under_all=%d" % (len(over), len(over_v), len(recs) - len(over)))
    print("RESULT kept=%d total=%d pct=%s kept_eq_over_x_limit=%s"
          % (kept, total, pct, kept == LIMIT * len(over)))
    for k in ("HIGH", "MEDIUM", "LOW"):
        print("RESULT over_valid %s %d/%d" % (k, lab[k][0], lab[k][1]))
    print("RESULT over_valid nonHIGH %d/%d" % non)
    print("RESULT fisher_two_sided HIGH_vs_nonHIGH p=%.6f printed=%s" % (p, p_print))
    lens = sorted(x[0] for x in over)
    print("RESULT over_lengths min=%d median=%d max=%d" % (lens[0], lens[len(lens) // 2], lens[-1]))

    bad = [k for k in PRINTED if got[k] != PRINTED[k]]
    for k in PRINTED:
        print("CHECK %-10s printed=%s measured=%s %s"
              % (k, PRINTED[k], got[k], "OK" if k not in bad else "MISMATCH"))
    if bad:
        print("RESULT: FAIL (mismatch %s)" % ", ".join(bad))
        sys.exit(1)
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
