"""pr_wilson_ci.py -- Wilson 95% intervals for the Section 4.3 Precision and Recall (S552-J).

Reads data/frozen/v1_9r/corpus_master.csv, hash-gated. Recounts TP, FP and FN at the
standard (CMI >= 41) and high-precision (CMI >= 60) thresholds on the 196 documents with
CMI > 0, Recall denominator 118 (117 HIGH among the 196 plus 1 HIGH with CMI = 0), and
gates them against the counts Section 4.3 prints (L304 of manuscript 881f4ed5):
TP 41 / FP 1 / FN 77 and TP 6 / FP 0 / FN 112. Any mismatch exits 2 before a value is
printed. Then prints the Wilson score interval for each proportion, z = 1.959964
(two-sided 95%), in proportion units to four decimals and in percent to one decimal.

Wilson interval for k successes in n:
    centre = (p + z^2 / 2n) / (1 + z^2 / n)
    half   = z * sqrt(p (1 - p) / n + z^2 / 4n^2) / (1 + z^2 / n),   p = k / n
It reflects binomial sampling variation in the counts only.

Standard library only. Reads; writes nothing. Run from anywhere.
"""
import csv
import hashlib
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "data", "frozen", "v1_9r", "corpus_master.csv")
CORPUS_SHA = "57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b"
Z = 1.959964
RECALL_DEN = 118
EXPECTED = {41.0: (41, 1, 77), 60.0: (6, 0, 112)}


def fail(msg):
    print("GATE FAIL:", msg)
    print("RESULT: FAIL (%s)" % msg)
    sys.exit(2)


def wilson(k, n):
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def main():
    print("PRODUCER scripts/pr_wilson_ci.py argv=%s" % sys.argv[1:])
    got = hashlib.sha256(open(CORPUS, "rb").read()).hexdigest()
    print("INPUT data/frozen/v1_9r/corpus_master.csv %s" % got)
    if got != CORPUS_SHA:
        fail("corpus_master hash mismatch")
    rows = list(csv.DictReader(open(CORPUS, encoding="utf-8-sig")))
    valid = [r for r in rows if float(r["cmi"]) > 0]
    n_high_all = sum(r["human_label"] == "HIGH" for r in rows)
    print("GATE valid=%d high_all=%d" % (len(valid), n_high_all))
    if len(valid) != 196 or n_high_all != RECALL_DEN:
        fail("population")
    out = []
    for t, want in sorted(EXPECTED.items()):
        pos = [r for r in valid if float(r["cmi"]) >= t]
        tp = sum(r["human_label"] == "HIGH" for r in pos)
        fp = len(pos) - tp
        fn = RECALL_DEN - tp
        print("GATE t=%.0f tp=%d fp=%d fn=%d %s" % (t, tp, fp, fn,
              "OK" if (tp, fp, fn) == want else "EXPECTED %s" % (want,)))
        if (tp, fp, fn) != want:
            fail("counts at %.0f" % t)
        out.append((t, "precision", tp, tp + fp))
        out.append((t, "recall", tp, RECALL_DEN))
    print("GATE PASS")
    for t, name, k, n in out:
        lo, hi = wilson(k, n)
        print("RESULT t=%.0f %s k=%d n=%d point=%.4f wilson95=[%.4f, %.4f] pct=%.1f [%.1f%%, %.1f%%]"
              % (t, name, k, n, k / n, lo, hi, 100 * k / n, 100 * lo, 100 * hi))
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
