#!/usr/bin/env python3
"""
freeze_corpus_clean.py -- byte-exact copy of the corpus_clean files that feed
Section 5.8 into data/frozen/v1_9r/corpus_clean/, with a manifest.

S308-J (2026-08-22), Pending 113 cluster (3). The joining set is FN + non-FN at
n=202 (data/frozen/v1_9/corpus_master.csv), which is a superset of the n=196
set. Refuses to overwrite an existing copy that differs (Frozen Dataset
Principle: a frozen copy is never rewritten).

Usage: python scripts/freeze_corpus_clean.py --master data/frozen/v1_9/corpus_master.csv
           --src corpus/corpus_clean --dst data/frozen/v1_9r/corpus_clean
           --manifest data/frozen/v1_9r/corpus_clean_manifest_v1_9r.csv
"""
import argparse, csv, hashlib, os, shutil, sys

EXPECT_MASTER = "b562425accd95cb64cd69b2462d6ddc3592fe0997d781b032742d3de0aaee362"
EXPECT_N = 160


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--manifest", required=True)
    a = ap.parse_args()
    with open(a.master, "rb") as f:
        mb = f.read()
    if sha(mb) != EXPECT_MASTER:
        print("FAIL: master is not data/frozen/v1_9 (n=202)"); sys.exit(1)
    rows = list(csv.DictReader(open(a.master, encoding="utf-8-sig", newline="")))
    tg = sorted(r["target"] for r in rows
                if float(r["cmi"] or 0) > 0 and
                (r["human_label"] != "HIGH" or float(r["cmi"]) < 41))
    if len(tg) != EXPECT_N:
        print(f"FAIL: joining set is {len(tg)}, expected {EXPECT_N}"); sys.exit(1)
    os.makedirs(a.dst, exist_ok=True)
    man, copied, kept = [], 0, 0
    for t in tg:
        s = os.path.join(a.src, t + ".txt"); d = os.path.join(a.dst, t + ".txt")
        if not os.path.exists(s):
            print(f"FAIL: source missing {s}"); sys.exit(1)
        sb = open(s, "rb").read()
        if os.path.exists(d):
            if open(d, "rb").read() != sb:
                print(f"FAIL: frozen copy already exists and DIFFERS: {d}"); sys.exit(1)
            kept += 1
        else:
            shutil.copyfile(s, d); copied += 1
        db = open(d, "rb").read()
        if db != sb:
            print(f"FAIL: copy not byte-exact {d}"); sys.exit(1)
        man.append((t, sha(db), len(db)))
    with open(a.manifest, "w", encoding="utf-8", newline="\n") as f:
        f.write("target,sha256,bytes\n")
        for t, h, n in man:
            f.write(f"{t},{h},{n}\n")
    mh = sha(open(a.manifest, "rb").read())
    print(f"joining set {len(tg)}; copied {copied}; already frozen and identical {kept}")
    print(f"manifest {a.manifest} sha256={mh} bytes={os.path.getsize(a.manifest)}")
    print("RESULT: 0 FAIL")


if __name__ == "__main__":
    main()
