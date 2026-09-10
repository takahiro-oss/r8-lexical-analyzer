#!/usr/bin/env python3
"""Short-form SNS documents: author non-LOW vs. rater LOW assignments, at n = 196.

Produces the figures cited by manuscript Section 7.1, third design implication
(pending_edits S409-F31): base 21, Rater 1 LOW 11, Rater 2 LOW 12, Rater 2 LOW reasons
all residual ("other"). Inputs are the RELEASED rater label files and the frozen
post-DEC-072 corpus_master, so a reader holding the public bundle can recompute.

Usage (Git Bash, from C:/r8/r8_strategy):
  /c/r8/r8_strategy/.venv/Scripts/python.exe scripts/short_form_rater_labels.py \
      --master data/frozen/v1_9r/corpus_master.csv \
      --rater1 data/frozen/v1_9_public_r4/rater1_labels.csv \
      --rater2 data/frozen/v1_9_public_r4/rater2_labels.csv

Reader use: pass the released corpus_master.csv as --master and the released
rater label files as --rater1 / --rater2.
Gates (exit 1 on failure): input SHA256 against the values recorded below; base size;
the two LOW counts; Rater 2 LOW reasons all equal to the residual code. Values were
first measured S409-J, 2026-08-31, on the judgment surface; the gates encode them so
that a later run confirms rather than re-derives.
"""
import argparse, csv, hashlib, sys
from collections import Counter

EXPECT_SHA = {
    "master": "57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b",
    "rater1": "95e0d7d46c12fcab3d4e64c6920077e8653575a3f9ae881e657c800780ca50c2",
    "rater2": "9706415d123faa3f95f42e3d755840e33b61732f0eb6dfcec805c830756d3657",
}
# The released corpus_master.csv (data/frozen/v1_9_public_r4, manifest_sha256.json)
# is accepted as well: the short-form documents carry the same identifiers and
# values in both files, which the value gates below re-check on every run.
MASTER_RELEASED_SHA = "90333c431d47eb4069feb1eb385fd16661da061bd1a6cf3b874747944ede7e0a"
EXPECT = {"short_form_total": 25, "cmi0": 4, "base": 21, "r1_low": 11, "r2_low": 12}
RESIDUAL = "\u305d\u306e\u4ed6"  # the raters' residual option ("other")

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--rater1", required=True)
    ap.add_argument("--rater2", required=True)
    a = ap.parse_args()
    fails = []
    for k, p in (("master", a.master), ("rater1", a.rater1), ("rater2", a.rater2)):
        h = sha(p)
        ok = h == EXPECT_SHA[k] or (k == "master" and h == MASTER_RELEASED_SHA)
        print(f"[{'OK' if ok else 'FAIL'}] sha256 {k}: {h}")
        if not ok:
            fails.append(f"sha256 {k}")
    cm = list(csv.DictReader(open(a.master, encoding="utf-8-sig")))
    r1 = {r["target"]: r for r in csv.DictReader(open(a.rater1, encoding="utf-8-sig"))}
    r2 = {r["target"]: r for r in csv.DictReader(open(a.rater2, encoding="utf-8-sig"))}
    sn = [r for r in cm if r["target"].lower().startswith("sn")]
    cmi0 = [r["target"] for r in sn if float(r["cmi"]) == 0]
    base = [r for r in sn if r["human_label"] != "LOW" and r["target"] in r1 and r["target"] in r2]
    print(f"short-form documents: {len(sn)}; author labels: {dict(Counter(r['human_label'] for r in sn))}")
    print(f"CMI = 0 among them: {len(cmi0)} {sorted(cmi0)}")
    print(f"base (author non-LOW, present in both rater files): {len(base)}")
    out = {}
    for name, rr in (("r1", r1), ("r2", r2)):
        labs = Counter(rr[r["target"]]["rater_label"] for r in base)
        low_docs = [r for r in base if rr[r["target"]]["rater_label"] == "LOW"]
        codes_low = Counter(v.strip() for r in low_docs for k in ("reason_1", "reason_2", "reason_3")
                            for v in [rr[r["target"]][k]] if v.strip())
        out[name] = (labs, len(low_docs), codes_low)
        print(f"{name}: labels {dict(labs)}; LOW {len(low_docs)}/{len(base)} = {100*len(low_docs)/len(base):.1f}%")
        print(f"{name}: reason codes on the LOW subset: {dict(codes_low)}")
    checks = [
        ("short_form_total", len(sn)), ("cmi0", len(cmi0)), ("base", len(base)),
        ("r1_low", out["r1"][1]), ("r2_low", out["r2"][1]),
    ]
    for k, v in checks:
        ok = v == EXPECT[k]
        print(f"[{'OK' if ok else 'FAIL'}] {k}: {v} (expected {EXPECT[k]})")
        if not ok:
            fails.append(k)
    r2_codes = out["r2"][2]
    ok = set(r2_codes) == {RESIDUAL} and sum(r2_codes.values()) == out["r2"][1]
    print(f"[{'OK' if ok else 'FAIL'}] r2 LOW reasons all residual: {dict(r2_codes)}")
    if not ok:
        fails.append("r2_residual")
    print("RESULT:", "ALL CHECKS PASSED" if not fails else "FAILED: " + ", ".join(fails))
    sys.exit(0 if not fails else 1)

if __name__ == "__main__":
    main()
