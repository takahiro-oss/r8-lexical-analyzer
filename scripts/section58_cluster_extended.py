#!/usr/bin/env python3
"""
S417-J_cluster_extended.py -- gated producer for the Section 5.8 cluster-level
sensitivity analysis under the criterion Section 5.8 L454 states.

Written S417-J (2026-09-01) for Layer A A-1 finding F22.

WHAT THIS DOES AND DOES NOT DO.
It computes the cluster-level aggregation twice from ONE detection pass:
  (1) with the archived cluster_definitions.csv, five clusters -- this must
      reproduce the values the manuscript and CODEBOOK.md section 4.4 print,
      and it is the GATE;
  (2) with a sixth cluster added, the note163-note179 same-author serial series
      Section 5.7 analyses, restricted to its false-negative group members.
It reimplements nothing. load_master, detect_hits and cluster_agg are imported
from scripts/section58_recount.py, which itself imports the estimators from
scripts/analyze_section58.py, so both aggregations are by construction the
arithmetic that produced the printed values.

It does not touch scripts/section58_recount.py, any frozen directory, or any
released file. The extended cluster CSV is written to --sandbox_dir only.

Exit 1 on any input-hash, gate or membership assertion failure.
"""
import argparse, csv, hashlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# This producer runs from handout/ before its closing spec places it in
# scripts/. Both locations are put on the path so the import resolves either
# way; neither directory is written to.
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, os.pardir, "scripts")))
import section58_recount as R   # noqa: E402

# The sixth cluster, declared here rather than in a data file so that the
# extension is auditable in the producer itself. These are the members of the
# note163-note179 series that fall in the false-negative group. Section 5.7
# prints the series as 15 valid documents of which 8 reach CMI >= 41.
SIXTH_CLUSTER_ID = "CL_serial_note163"
SIXTH_CLUSTER_MEMBERS = [
    "note163", "note165", "note169", "note172", "note174", "note175", "note177",
]

EXPECT_MASTER_196 = "57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b"
EXPECT_CLUSTER = "5b2c7e5f911e2a837401f0bac48f7b6746b7cc0f106a1079f94274c532eaff6b"

# GATE: the five-cluster values the manuscript L456/L458 and CODEBOOK.md 4.4
# print. Stated before the run.
GATE_FIVE = {
    "c2b": "n=58; 44/58 vs 41/79; OR=2.91 CI[1.38,6.14] p=0.005",
    "c3b": "n=58; 42/58 vs 37/79; OR=2.98 CI[1.44,6.16] p=0.003",
}
# PREDICTION for the six-cluster run, stated BEFORE the run, computed by the
# S417-J judgment session from the released bundle. Reported as MATCH/DIFFER;
# a difference is not a failure, it is the measurement correcting the
# prediction, and the judgment session rules on it.
PREDICT_SIX = {
    "c2b": "n=52; 38/52 vs 41/79; OR=2.52 CI[1.18,5.35] p=0.018",
    "c3b": "n=52; 36/52 vs 37/79; OR=2.55 CI[1.22,5.33] p=0.013",
}


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def fail(msg):
    print("FAIL: " + msg)
    sys.exit(1)


def write_extended_cluster(base_csv, out_csv, fn_set, log):
    with open(base_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    base_targets = {r["target"] for r in rows}
    for t in SIXTH_CLUSTER_MEMBERS:
        if t in base_targets:
            fail(f"sixth-cluster member {t} already present in the archived cluster file")
        if t not in fn_set:
            fail(f"sixth-cluster member {t} is not in the false-negative group")
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["cluster_id", "target"])
        w.writeheader()
        for r in rows:
            w.writerow({"cluster_id": r["cluster_id"], "target": r["target"]})
        for t in SIXTH_CLUSTER_MEMBERS:
            w.writerow({"cluster_id": SIXTH_CLUSTER_ID, "target": t})
    log.append(f"extended cluster file {out_csv} sha256={sha(out_csv)} "
               f"rows={len(rows) + len(SIXTH_CLUSTER_MEMBERS)} "
               f"(base {len(rows)} + {len(SIXTH_CLUSTER_MEMBERS)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--clean-dir", required=True)
    ap.add_argument("--cluster", required=True, help="the archived cluster_definitions.csv")
    ap.add_argument("--sandbox_dir", required=True, help="where the extended cluster file is written")
    ap.add_argument("--log", required=True)
    args = ap.parse_args()

    log = ["S417-J_cluster_extended.py",
           f"argv: {' '.join(sys.argv[1:])}"]

    hm = sha(args.master)
    if hm != EXPECT_MASTER_196:
        fail(f"master hash {hm} != expected n=196 master {EXPECT_MASTER_196}")
    hc = sha(args.cluster)
    if hc != EXPECT_CLUSTER:
        fail(f"cluster hash {hc} != expected {EXPECT_CLUSTER}")
    log.append(f"input master {hm}")
    log.append(f"input cluster {hc}")

    for p in (os.path.abspath(args.sandbox_dir), os.path.abspath(args.log)):
        if os.sep + "frozen" + os.sep in p + os.sep:
            fail(f"output path is inside a frozen directory: {p}")

    rows, fn, nfn = R.load_master(args.master)
    fn_t = [r["target"] for r in fn]
    nfn_t = [r["target"] for r in nfn]
    if (len(fn_t), len(nfn_t)) != (76, 79):
        fail(f"group sizes {(len(fn_t), len(nfn_t))} != expected (76, 79)")
    log.append(f"fn_n={len(fn_t)} nfn_n={len(nfn_t)}")

    ext_csv = os.path.join(args.sandbox_dir, "cluster_definitions_six.csv")
    write_extended_cluster(args.cluster, ext_csv, set(fn_t), log)

    det_log = []
    fn_hits = R.detect_hits(args.clean_dir, fn_t, det_log)
    nfn_hits = R.detect_hits(args.clean_dir, nfn_t, det_log)
    log.append(f"detection: {len(det_log)} corpus_clean files read, one pass, "
               f"shared by both aggregations")

    nfail = 0
    log.append("")
    log.append("=== FIVE CLUSTERS (archived cluster_definitions.csv) -- GATE ===")
    for cat in ("c2b", "c3b"):
        c = R.cluster_agg(args.cluster, fn_t, nfn_t, fn_hits, nfn_hits, cat)
        got = R.fmt_cluster(c)
        ok = got == GATE_FIVE[cat]
        nfail += (not ok)
        log.append(f"[{'OK' if ok else 'FAIL'}] cluster.{cat}: got '{got}' expected '{GATE_FIVE[cat]}'")
    log.append(f"GATE: 2 checks, {nfail} FAIL")

    log.append("")
    log.append("=== SIX CLUSTERS (archived five + CL_serial_note163) ===")
    for cat in ("c2b", "c3b"):
        c = R.cluster_agg(ext_csv, fn_t, nfn_t, fn_hits, nfn_hits, cat)
        got = R.fmt_cluster(c)
        verdict = "MATCH" if got == PREDICT_SIX[cat] else "DIFFERS"
        log.append(f"[{verdict}] cluster.{cat}: got '{got}' predicted '{PREDICT_SIX[cat]}'")

    with open(args.log, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(log) + "\n")
    print("\n".join(log))
    print(f"LOG written: {args.log} sha256={sha(args.log)} bytes={os.path.getsize(args.log)}")
    if nfail:
        print(f"RESULT: {nfail} FAIL")
        sys.exit(1)
    print("RESULT: 0 FAIL")
    sys.exit(0)


if __name__ == "__main__":
    main()
