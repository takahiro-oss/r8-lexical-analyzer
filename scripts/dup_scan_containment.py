# scripts/dup_scan_containment.py
# Pending 97 step 1-b, second pass: containment-type duplication.
# READ-ONLY. Opens files for reading only. Writes nothing, deletes nothing.
# Prints identifiers, counts, hashes and ratios only -- never document text
# ([COMMON] Third-Party Information Handling [4]).
#
# WHY THIS EXISTS. dup_scan_full.py compares by difflib ratio behind a Jaccard
# prefilter. Both measures put the union in the denominator, so a document wholly
# contained in a longer one scores low on each and passes both nets. That class is
# structurally invisible to the first pass and is what this script measures.
#
# Measure: containment = |A intersect B| / min(|A|, |B|), over the set of distinct
# normalised lines. It reaches 1.0 when every line of the shorter document also
# appears in the longer one, at any length ratio.
#
# The normalise() function is identical to dup_scan_full.py's, so both passes
# partition the same text. Do not change one without the other.

import argparse
import csv
import difflib
import hashlib
import os
import sys

HEADER_PREFIXES = ("[CATEGORY]", "[SOURCE]", "[DATE]")
HEADER_EXACT = ("[TEXT]",)

CONTAINMENT_MIN = 0.90   # report threshold
MIN_LINES = 5            # below this a document is not compared; it is listed instead
TOP_N = 25               # distribution report, printed regardless of threshold


def normalise(text):
    """Drop archive header lines, remove all whitespace within lines,
    drop lines that become empty. Returns a list of lines."""
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith(HEADER_PREFIXES) or s in HEADER_EXACT:
            continue
        s = "".join(s.split())
        if s:
            out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--clean_dir", required=True)
    args = ap.parse_args()

    print("=== dup_scan_containment.py  (READ-ONLY) ===")
    print("master    :", args.master)
    print("clean_dir :", args.clean_dir)
    print(f"containment = |A&B| / min(|A|,|B|) over distinct normalised lines")
    print(f"threshold   : {CONTAINMENT_MIN}   min_lines: {MIN_LINES}")

    with open(args.master, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    targets = [r["target"] for r in rows]
    print("master rows        :", len(rows))
    print("master targets uniq:", len(set(targets)))
    if len(set(targets)) != len(targets):
        print("[FAIL] duplicate target identifiers in master")
        return 2

    on_disk = sorted(x for x in os.listdir(args.clean_dir) if x.endswith(".txt"))
    stem_exact = {x[:-4]: x for x in on_disk}
    stem_lower = {}
    for x in on_disk:
        stem_lower.setdefault(x[:-4].lower(), []).append(x)

    mapping = {}
    missing = []
    for t in targets:
        if t in stem_exact:
            mapping[t] = stem_exact[t]
        else:
            cands = stem_lower.get(t.lower(), [])
            if len(cands) == 1:
                mapping[t] = cands[0]
            else:
                missing.append(t)

    print("files in clean_dir :", len(on_disk))
    print("mapped             :", len(mapping))
    print("targets w/o file   :", len(missing), missing if missing else "")
    if missing:
        print("[FAIL] every master target must map to a file; nothing was compared")
        return 2

    body = {}
    meta = {}
    for t, fname in mapping.items():
        with open(os.path.join(args.clean_dir, fname),
                  encoding="utf-8-sig", errors="replace") as f:
            raw = f.read()
        lines = normalise(raw)
        body[t] = lines
        meta[t] = {
            "lines_norm": len(lines),
            "uniq": len(set(lines)),
            "sha": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(),
        }

    # exact groups are collapsed to one representative: members are identical,
    # so containment between them is 1.0 and carries no new information.
    groups = {}
    for t in body:
        groups.setdefault(meta[t]["sha"], []).append(t)
    exact_pairs = set()
    reps = []
    for h, v in groups.items():
        v = sorted(v)
        reps.append(v[0])
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                exact_pairs.add(tuple(sorted((v[i], v[j]))))
    reps.sort()
    print("exact-identity groups collapsed:", sum(1 for v in groups.values() if len(v) > 1))
    print("representatives compared       :", len(reps))

    short = [t for t in reps if meta[t]["uniq"] < MIN_LINES]
    usable = [t for t in reps if meta[t]["uniq"] >= MIN_LINES]
    print(f"documents with <{MIN_LINES} distinct lines (NOT compared):",
          len(short), short if short else "")
    print("documents compared             :", len(usable))

    sets = {t: set(body[t]) for t in usable}
    scored = []
    pairs = 0
    for i in range(len(usable)):
        a = usable[i]
        sa = sets[a]
        for j in range(i + 1, len(usable)):
            b = usable[j]
            sb = sets[b]
            pairs += 1
            inter = len(sa & sb)
            if inter == 0:
                continue
            cont = inter / min(len(sa), len(sb))
            scored.append((cont, a, b, inter, len(sa), len(sb)))
    scored.sort(reverse=True)
    print("pairs examined                 :", pairs)

    hits = [s for s in scored if s[0] >= CONTAINMENT_MIN]

    print()
    print(f"=== HITS  containment >= {CONTAINMENT_MIN} ===")
    print("count:", len(hits))
    for cont, a, b, inter, la, lb in hits:
        sm = difflib.SequenceMatcher(None, body[a], body[b], autojunk=False)
        ratio = sm.ratio()
        short_side, long_side = (a, b) if la <= lb else (b, a)
        flag = "SEEN-BY-PASS-1" if ratio >= 0.90 else "NEW: invisible to pass 1"
        print(f"  containment={cont:.4f} ratio={ratio:.4f} "
              f"shared={inter} sizes={la}/{lb}  {a} .. {b}")
        print(f"      shorter={short_side}  longer={long_side}  [{flag}]")

    print()
    print(f"=== DISTRIBUTION  top {TOP_N} by containment, threshold or not ===")
    print("printed so the threshold can be judged against the data rather than assumed")
    for cont, a, b, inter, la, lb in scored[:TOP_N]:
        print(f"  {cont:.4f}  shared={inter:5d} sizes={la:5d}/{lb:5d}  {a} .. {b}")

    print()
    print("=== SUMMARY ===")
    print("documents compared       :", len(usable))
    print("pairs examined           :", pairs)
    print(f"containment >= {CONTAINMENT_MIN}    :", len(hits))
    print("of those, NEW to pass 1  :",
          sum(1 for c, a, b, i, la, lb in hits
              if difflib.SequenceMatcher(None, body[a], body[b],
                                         autojunk=False).ratio() < 0.90))
    print("NOTE: a hit is a CANDIDATE. Containment measures line overlap, not")
    print("      that one document is an extract of the other; confirmation is")
    print("      a read of the differing lines and is outside this script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
