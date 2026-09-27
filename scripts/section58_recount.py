#!/usr/bin/env python3
"""
section58_recount.py -- gated producer for the manuscript Section 5.8 values.

Written S308-J (2026-08-22) for Pending 113 cluster (3). It does NOT modify
scripts/analyze_section58.py; it imports that file's estimators (Fisher exact,
Bonferroni, BH-FDR, C_PATTERNS) so that the arithmetic is by construction the
one that produced the printed values, and supplies what that script lacks:

  * explicit input paths, hash-asserted (no D: constant);
  * a GATE over every value the manuscript prints at n=202, including the
    two contextual-validity rates (22.6 / 28.2) the original never emitted;
  * contextual-validity group membership taken from corpus_master, with the
    sheet's own `group` column used only as a consistency assertion, so the
    analysis follows the population (S302-J finding (c));
  * a CLOSURE check at n=196 that the DEC-072 removals account for the whole
    movement in both groups and in both validity sheets.

Populations. 202 = valid documents in data/frozen/v1_9 (pre-deduplication);
196 = data/frozen/v1_9r (DEC-072 applied). The FN group is human_label=HIGH,
0<CMI<41; the non-FN group is human_label!=HIGH, CMI>0.

Exit 1 on any assertion, gate or closure failure; nothing is written then.

--supp_s1_out writes supplementary_table_s1.csv, the ten-test table Section 5.8
defers to. Columns, rounding, row order, BOM and line endings reproduce the file
scripts/analyze_section58.py block 7 emits, that file being the one already on
disk at n=202. It is written ONLY when the gate or closure reports 0 FAIL, unlike
the log, which is written either way: the log is a record of what happened and
the table is a published artefact.
"""
import argparse, csv, hashlib, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_section58 as A58   # noqa: E402  (module-level D: constants are never dereferenced here)

DEC072_REMOVED = {"AD_065", "AD_067", "AD_071", "AD_072", "AD_073", "AD_074"}

EXPECT_INPUT = {
    # file role : {sha256: label}
    "master": {
        "b562425accd95cb64cd69b2462d6ddc3592fe0997d781b032742d3de0aaee362": 202,
        "57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b": 196,
    },
    "cluster": "5b2c7e5f911e2a837401f0bac48f7b6746b7cc0f106a1079f94274c532eaff6b",
    "c2b": "cda9601d2aafb1f7e7227c6841d03a51821bf80f4eeefa37c328b0d9882dd83b",
    "c3b": "048334d299528e1f235564e5aee874691f6335b5343689467fa2e4cbaff8f33e",
    "manuscript": "686f67827d5949d530ee19b0263402e5ee6a3578c0eb99224ca52a7b6ee46185",
}

# Every value the manuscript prints at L456/L458 (EN canonical 686f6782..., n=202).
# Keys are (block, name); values are the printed strings after formatting.
PRINTED_202 = {
    ("fn_n", ""): "78", ("nfn_n", ""): "82",
    ("main", "c2b"): "56/78 vs 42/82; OR=2.42 CI[1.26,4.67] p=0.009 Bonf=0.094 q=0.054",
    ("main", "c3b"): "53/78 vs 39/82; OR=2.34 CI[1.23,4.45] p=0.011 Bonf=0.107 q=0.054",
    ("cluster", "c2b"): "n=60; 45/60 vs 42/82; OR=2.86 CI[1.38,5.91] p=0.005",
    ("cluster", "c3b"): "n=60; 44/60 vs 39/82; OR=3.03 CI[1.48,6.22] p=0.003",
    ("validity", "c2b"): "13/56 vs 8/41 (excluded=1); OR=1.25 CI[0.46,3.36] p=0.804",
    ("validity", "c3b"): "12/53 vs 11/39 (excluded=0); OR=0.75 CI[0.29,1.92] p=0.629",
    ("validity_rate", "c3b"): "FN=22.6% NFN=28.2%",
}
# Predictions at n=196, stated BEFORE the run (S308-J, from S302-J group sizes
# and the DEC-072 membership measured on the two sheets). Group sizes only;
# no statistic is predicted.
PREDICT_196 = {"fn_n": 76, "nfn_n": 79,
               "c2b_fn_docs": 55, "c2b_nfn_docs_incl_excluded": 41,
               "c3b_fn_docs": 51, "c3b_nfn_docs": 37}


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def fail(msg):
    print("FAIL: " + msg)
    sys.exit(1)


def fmt_main(r, fn_n, nfn_n):
    return (f"{r['fn_pos']}/{fn_n} vs {r['nfn_pos']}/{nfn_n}; "
            f"OR={r['or']:.2f} CI[{r['ci_lo']:.2f},{r['ci_hi']:.2f}] "
            f"p={r['p_raw']:.3f} Bonf={r['p_bonf']:.3f} q={r['bh_q']:.3f}")


def fmt_cluster(c):
    return (f"n={c['agg_n_fn']}; {c['fn_pos']}/{c['agg_n_fn']} vs "
            f"{c['nfn_pos']}/{c['nfn_pos']+c['nfn_neg']}; "
            f"OR={c['or']:.2f} CI[{c['ci_lo']:.2f},{c['ci_hi']:.2f}] p={c['p']:.3f}")


def fmt_validity(v):
    return (f"{v['fn_valid']}/{v['fn_total']} vs {v['nfn_valid']}/{v['nfn_total']} "
            f"(excluded={v['excluded']}); OR={v['or']:.2f} "
            f"CI[{v['ci_lo']:.2f},{v['ci_hi']:.2f}] p={v['p']:.3f}")


def load_master(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    fn = [r for r in rows if r["human_label"] == "HIGH" and 0 < float(r["cmi"] or 0) < 41]
    nfn = [r for r in rows if r["human_label"] != "HIGH" and float(r["cmi"] or 0) > 0]
    return rows, fn, nfn


def detect_hits(clean_dir, targets, log):
    res, missing = {}, []
    for t in targets:
        p = os.path.join(clean_dir, t + ".txt")
        if not os.path.exists(p):
            missing.append(t); continue
        with open(p, "rb") as f:
            b = f.read()
        log.append(f"clean_sha256 {t} {hashlib.sha256(b).hexdigest()} {len(b)}")
        text = b.decode("utf-8")
        res[t] = {k: bool(re.search(A58.C_PATTERNS[k], text)) for k in A58.C_KEYS}
    if missing:
        fail(f"{len(missing)} corpus_clean files missing: {missing[:5]}")
    return res


def ten_tests(fn_t, nfn_t, fn_hits, nfn_hits):
    out, ps = [], []
    for k in A58.C_KEYS:
        a = sum(fn_hits[t][k] for t in fn_t); b = len(fn_t) - a
        c = sum(nfn_hits[t][k] for t in nfn_t); d = len(nfn_t) - c
        o, lo, hi, p = A58.fisher_exact_2x2(a, b, c, d)
        out.append({"category": k, "fn_pos": a, "nfn_pos": c, "or": o,
                    "ci_lo": lo, "ci_hi": hi, "p_raw": p, "p_bonf": A58.bonferroni(p, 10)})
        ps.append(p)
    for r, q in zip(out, A58.bh_fdr(ps)):
        r["bh_q"] = q
    return out


def cluster_agg(cluster_csv, fn_t, nfn_t, fn_hits, nfn_hits, cat):
    with open(cluster_csv, encoding="utf-8-sig", newline="") as f:
        cmap = {r["target"]: r["cluster_id"] for r in csv.DictReader(f)}
    used, agg = set(), []
    for t in fn_t:
        cl = cmap.get(t)
        if cl:
            if cl in used: continue
            used.add(cl)
            members = [t2 for t2 in fn_t if cmap.get(t2) == cl]
            agg.append(any(fn_hits[m][cat] for m in members))
        else:
            agg.append(fn_hits[t][cat])
    a = sum(agg); b = len(agg) - a
    c = sum(nfn_hits[t][cat] for t in nfn_t); d = len(nfn_t) - c
    o, lo, hi, p = A58.fisher_exact_2x2(a, b, c, d)
    return {"agg_n_fn": a + b, "fn_pos": a, "nfn_pos": c, "nfn_neg": d,
            "or": o, "ci_lo": lo, "ci_hi": hi, "p": p}


def validity(sheet_csv, fn_set, nfn_set, population):
    """Membership from corpus_master; sheet `group` asserted, never trusted."""
    with open(sheet_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    docs = {}
    for r in rows:
        docs.setdefault(r["target"], {"group": r["group"], "j": []})
        docs[r["target"]]["j"].append(r["judgment"].strip().lower())
    dropped = []
    fn_valid = nfn_valid = fn_total = nfn_total = excluded = 0
    for t, d in docs.items():
        in_fn, in_nfn = t in fn_set, t in nfn_set
        if not (in_fn or in_nfn):
            dropped.append(t); continue
        sheet_g = "FN" if d["group"] == "FN" else "NFN"
        if (sheet_g == "FN") != in_fn:
            fail(f"sheet group {sheet_g} for {t} contradicts corpus_master membership")
        if all(j == "m" for j in d["j"]):
            excluded += 1; continue
        valid = "y" in d["j"]
        if in_fn:
            fn_total += 1; fn_valid += valid
        else:
            nfn_total += 1; nfn_valid += valid
    a, b, c, dd = fn_valid, fn_total - fn_valid, nfn_valid, nfn_total - nfn_valid
    o, lo, hi, p = A58.fisher_exact_2x2(a, b, c, dd)
    if population == 202 and dropped:
        fail(f"at n=202 no sheet document may be outside the groups; dropped={dropped}")
    if population == 196 and not set(dropped) <= DEC072_REMOVED:
        fail(f"at n=196 dropped documents must be DEC-072 removals; dropped={dropped}")
    return {"fn_valid": a, "fn_total": fn_total, "nfn_valid": c, "nfn_total": nfn_total,
            "excluded": excluded, "or": o, "ci_lo": lo, "ci_hi": hi, "p": p,
            "dropped": sorted(dropped), "n_docs": len(docs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--clean-dir", required=True)
    ap.add_argument("--cluster", required=True)
    ap.add_argument("--c2b", required=True)
    ap.add_argument("--c3b", required=True)
    ap.add_argument("--population", type=int, choices=[202, 196], required=True)
    ap.add_argument("--manuscript", help="assert EN canonical hash and Recovery Guard strings")
    ap.add_argument("--log", required=True)
    ap.add_argument("--supp_s1_out",
                    help="write supplementary_table_s1.csv here; only on 0 FAIL")
    args = ap.parse_args()
    log = [f"section58_recount.py population={args.population}",
           f"argv: {' '.join(sys.argv[1:])}"]

    # --- input identity
    h = sha(args.master)
    if EXPECT_INPUT["master"].get(h) != args.population:
        fail(f"master hash {h} does not match the declared population {args.population}")
    for role in ("cluster", "c2b", "c3b"):
        p = getattr(args, role); hh = sha(p)
        if hh != EXPECT_INPUT[role]:
            fail(f"{role} hash {hh} != expected {EXPECT_INPUT[role]}")
        log.append(f"input {role} {hh}")
    log.append(f"input master {h}")
    if args.manuscript:
        hm = sha(args.manuscript)
        if hm != EXPECT_INPUT["manuscript"]:
            fail(f"manuscript hash {hm} != expected")
        txt = open(args.manuscript, encoding="utf-8-sig").read()
        for s, n in (("OR = 2.42", 1), ("OR = 2.34", 1), ("22.6%", 1), ("28.2%", 1),
                     ("n = 78", 4), ("n = 82", 1)):
            if txt.count(s) != n:
                fail(f"RECOVERY GUARD: manuscript count of '{s}' is {txt.count(s)}, expected {n}")
        log.append(f"manuscript {hm} guard strings OK")

    # --- groups
    rows, fn, nfn = load_master(args.master)
    fn_t = [r["target"] for r in fn]; nfn_t = [r["target"] for r in nfn]
    fn_set, nfn_set = set(fn_t), set(nfn_t)
    log.append(f"valid_n={sum(1 for r in rows if float(r['cmi'] or 0) > 0)} fn_n={len(fn_t)} nfn_n={len(nfn_t)}")
    exp = (78, 82) if args.population == 202 else (PREDICT_196["fn_n"], PREDICT_196["nfn_n"])
    if (len(fn_t), len(nfn_t)) != exp:
        fail(f"group sizes {(len(fn_t), len(nfn_t))} != expected {exp}")

    fn_hits = detect_hits(args.clean_dir, fn_t, log)
    nfn_hits = detect_hits(args.clean_dir, nfn_t, log)
    ten = ten_tests(fn_t, nfn_t, fn_hits, nfn_hits)
    by = {r["category"]: r for r in ten}
    clu = {c: cluster_agg(args.cluster, fn_t, nfn_t, fn_hits, nfn_hits, c) for c in ("c2b", "c3b")}
    val = {"c2b": validity(args.c2b, fn_set, nfn_set, args.population),
           "c3b": validity(args.c3b, fn_set, nfn_set, args.population)}

    # --- emit
    out = {("fn_n", ""): str(len(fn_t)), ("nfn_n", ""): str(len(nfn_t))}
    for c in ("c2b", "c3b"):
        out[("main", c)] = fmt_main(by[c], len(fn_t), len(nfn_t))
        out[("cluster", c)] = fmt_cluster(clu[c])
        out[("validity", c)] = fmt_validity(val[c])
        v = val[c]
        out[("validity_rate", c)] = (f"FN={100*v['fn_valid']/v['fn_total']:.1f}% "
                                     f"NFN={100*v['nfn_valid']/v['nfn_total']:.1f}%")
    log.append("")
    log.append("=== ALL TEN TESTS ===")
    for r in ten:
        log.append(f"{r['category']}: {fmt_main(r, len(fn_t), len(nfn_t))}")
    log.append("")
    log.append(f"=== VALUES n={args.population} ===")
    for k, v in out.items():
        log.append(f"{k[0]}{'.'+k[1] if k[1] else ''}: {v}")
    for c in ("c2b", "c3b"):
        log.append(f"validity_dropped.{c}: {val[c]['dropped']} (sheet docs={val[c]['n_docs']})")

    # --- gate / closure
    nfail = 0
    log.append("")
    if args.population == 202:
        log.append("=== GATE n=202 against printed values ===")
        for k, exp_s in PRINTED_202.items():
            ok = out[k] == exp_s
            nfail += (not ok)
            log.append(f"[{'OK' if ok else 'FAIL'}] {k[0]}.{k[1]}: got '{out[k]}' expected '{exp_s}'")
        log.append(f"GATE: {len(PRINTED_202)} checks, {nfail} FAIL")
    else:
        log.append("=== CLOSURE n=196 (DEC-072 accounts for the whole movement) ===")
        # the removed rows must be absent from the master entirely
        present = DEC072_REMOVED & {r["target"] for r in rows}
        ok = not present; nfail += (not ok)
        log.append(f"[{'OK' if ok else 'FAIL'}] DEC-072 targets absent from master: present={sorted(present)}")
        for name, got, exp_v in (
            ("c2b FN docs", val["c2b"]["fn_total"] + 0, PREDICT_196["c2b_fn_docs"]),
            ("c2b NFN docs incl excluded", val["c2b"]["nfn_total"] + val["c2b"]["excluded"],
             PREDICT_196["c2b_nfn_docs_incl_excluded"]),
            ("c3b FN docs", val["c3b"]["fn_total"], PREDICT_196["c3b_fn_docs"]),
            ("c3b NFN docs", val["c3b"]["nfn_total"] + val["c3b"]["excluded"], PREDICT_196["c3b_nfn_docs"]),
        ):
            ok = got == exp_v; nfail += (not ok)
            log.append(f"[{'OK' if ok else 'FAIL'}] {name}: got {got} predicted {exp_v}")
        log.append(f"CLOSURE: {nfail} FAIL")

    if args.supp_s1_out:
        if nfail:
            log.append(f"supp_s1: NOT WRITTEN ({nfail} FAIL)")
        else:
            fieldnames = ["category", "fn_n", "nfn_n",
                          "fn_positive", "nfn_positive",
                          "odds_ratio", "ci_95_lo", "ci_95_hi",
                          "p_raw", "p_bonferroni", "bh_q"]
            with open(args.supp_s1_out, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                for r in ten:
                    w.writerow({
                        "category":     r["category"],
                        "fn_n":         len(fn_t),
                        "nfn_n":        len(nfn_t),
                        "fn_positive":  r["fn_pos"],
                        "nfn_positive": r["nfn_pos"],
                        "odds_ratio":   round(r["or"], 4),
                        "ci_95_lo":     round(r["ci_lo"], 4),
                        "ci_95_hi":     round(r["ci_hi"], 4),
                        "p_raw":        round(r["p_raw"], 4),
                        "p_bonferroni": round(r["p_bonf"], 4),
                        "bh_q":         round(r["bh_q"], 4),
                    })
            log.append(f"supp_s1: {args.supp_s1_out} "
                       f"sha256={sha(args.supp_s1_out)} "
                       f"bytes={os.path.getsize(args.supp_s1_out)} rows={len(ten)}")

    with open(args.log, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(log) + "\n")
    print("\n".join(l for l in log if not l.startswith("clean_sha256")))
    print(f"LOG written: {args.log} sha256={sha(args.log)} bytes={os.path.getsize(args.log)}")
    if nfail:
        print(f"RESULT: {nfail} FAIL"); sys.exit(1)
    print("RESULT: 0 FAIL"); sys.exit(0)


if __name__ == "__main__":
    main()
