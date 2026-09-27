"""fn_saturation_counterfactual.py -- producer for the S533-J false-negative saturation counterfactual.

For each valid document (CMI > 0) with human_label = HIGH and CMI < 41 (the false-negative
group of Section 6.2), set the normalised activation D_i of every scored component already
active (D_i > 0) to 1.0, recompute CMI with the r8.py WEIGHTS table, and count the documents
reaching the standard HIGH threshold. A sensitivity pass multiplies each active D_i by k and
caps at 1.0. Inactive components are never raised.

Inputs are hash-gated. Before any new value is printed, the script reproduces EV-r196-055
(n, group means, TP minimum) and the EV-ensub-009 CMI recomputation; any gate failure exits 2.
Run from the repository root. Reads only; writes nothing. Output goes to stdout.
"""
import ast
import csv
import hashlib
import statistics
import sys

CORPUS = "data/frozen/v1_9r/corpus_master.csv"
R8 = "r8.py"
CORPUS_SHA = "57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b"
R8_SHA = "53553ce13a815a4bcc30f448cbb3ed2808a6ce3fedb61a26059fc949b3fd09b5"
HIGH = 41.0
FACTORS = (1.25, 1.5, 2.0, 3.0, 5.0)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def fail(msg):
    print("GATE FAIL:", msg)
    sys.exit(2)


def weights():
    tree = ast.parse(open(R8, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "WEIGHTS" for t in node.targets):
            return ast.literal_eval(node.value)
    fail("WEIGHTS not found in r8.py")


def main():
    print("PRODUCER scripts/fn_saturation_counterfactual.py argv=%s" % sys.argv[1:])
    for path, want in ((CORPUS, CORPUS_SHA), (R8, R8_SHA)):
        got = sha(path)
        print("INPUT %s %s" % (path, got))
        if got != want:
            fail("%s hash %s != %s" % (path, got, want))
    w = weights()
    if abs(sum(w.values()) - 1.0) > 1e-9:
        fail("weights sum %r" % sum(w.values()))
    comps = [c for c in w if w[c] > 0]
    print("COMPONENTS scored=%d (weight > 0)" % len(comps))

    rows = list(csv.DictReader(open(CORPUS, encoding="utf-8-sig")))
    d = lambda r, c: float(r[c])
    cmi = lambda r: float(r["cmi"])
    valid = [r for r in rows if cmi(r) > 0]
    off = [r["target"] for r in valid if abs(round(100 * sum(w[c] * d(r, c) for c in w), 1) - cmi(r)) > 0.1 + 1e-9]
    print("GATE ensub-009 recompute |diff|>0.1: %d" % len(off))
    if off:
        fail("recompute mismatch %s" % off)

    high = [r for r in valid if r["human_label"] == "HIGH"]
    tp = [r for r in high if cmi(r) >= HIGH]
    fn = [r for r in high if cmi(r) < HIGH]
    active = lambda r: [c for c in comps if d(r, c) > 0]
    m_tp = round(statistics.mean(len(active(r)) for r in tp), 2)
    m_fn = round(statistics.mean(len(active(r)) for r in fn), 2)
    min_tp = min(len(active(r)) for r in tp)
    print("GATE r196-055 n_high=%d tp=%d fn=%d mean_tp=%.2f mean_fn=%.2f min_tp=%d"
          % (len(high), len(tp), len(fn), m_tp, m_fn, min_tp))
    if (len(high), len(tp), len(fn), m_tp, m_fn, min_tp) != (117, 41, 76, 7.29, 5.12, 4):
        fail("EV-r196-055 not reproduced")
    print("GATE PASS")

    cap = lambda r: round(100 * sum(w[c] for c in active(r)), 1)
    reach = [r for r in fn if cap(r) >= HIGH]
    bound = [r for r in fn if cap(r) < HIGH]
    caps = [cap(r) for r in fn]
    print("RESULT saturation fn_reaching_41=%d of %d" % (len(reach), len(fn)))
    print("RESULT saturation fn_not_reaching_41=%d of %d" % (len(bound), len(fn)))
    print("RESULT saturated_cmi min=%.1f max=%.1f mean=%.2f median=%.1f"
          % (min(caps), max(caps), statistics.mean(caps), statistics.median(caps)))
    print("RESULT reaching group: mean_active=%.2f cmi_min=%.1f cmi_max=%.1f cmi_mean=%.1f"
          % (statistics.mean(len(active(r)) for r in reach), min(cmi(r) for r in reach),
             max(cmi(r) for r in reach), statistics.mean(cmi(r) for r in reach)))
    print("RESULT non-reaching group: mean_active=%.2f max_active=%d"
          % (statistics.mean(len(active(r)) for r in bound), max(len(active(r)) for r in bound)))
    print("RESULT tp saturated_cmi min=%.1f" % min(cap(r) for r in tp))
    for k in FACTORS:
        n = sum(100 * sum(w[c] * min(d(r, c) * k, 1.0) for c in comps) >= HIGH for r in fn)
        print("RESULT sensitivity k=%.2f fn_reaching_41=%d of %d" % (k, n, len(fn)))
    print("RESULT fn_ids_not_reaching_41=%s" % ",".join(sorted(r["target"] for r in bound)))
    print("DONE exit 0")


if __name__ == "__main__":
    main()
