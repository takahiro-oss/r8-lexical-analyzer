# scripts/analyze_section58.py
# Generate all §5.8 numeric values from corpus_master and corpus_clean.
# Outputs: terminal display, manuscript transcription block,
#          supplementary_table_s1.csv
#
# Blocks:
#   1 - Group definition (halts on size mismatch)
#   2 - Ten-test Fisher exact batch (c1a-c5c)
#   3 - Cluster-aggregated sensitivity analysis (c2b only)
#   4 - c2b context validity analysis (conditional on sheet existence)
#   5 - c3b context validity analysis (conditional on sheet existence)
#   6 - Manuscript transcription block (terminal output)
#   7 - Supplementary Table CSV output

import csv
import math
import os
import re
import sys

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR         = r"D:\r8_strategy"
CORPUS_CLEAN_DIR = os.path.join(BASE_DIR, "corpus", "corpus_clean")
MASTER_CSV       = os.path.join(BASE_DIR, "data", "results", "corpus_master.csv")
CLUSTER_CSV      = os.path.join(BASE_DIR, "data", "results", "cluster_definitions.csv")
C2B_VALIDITY_CSV = os.path.join(BASE_DIR, "data", "results", "c2b_validity_sheet.csv")
C3B_VALIDITY_CSV = os.path.join(BASE_DIR, "data", "results", "c3b_validity_sheet.csv")
SUPP_TABLE_CSV   = os.path.join(BASE_DIR, "data", "results", "supplementary_table_s1.csv")

# ---------------------------------------------------------------------------
# Expected group sizes (halt condition)
# ---------------------------------------------------------------------------
EXPECTED_FN  = 78
EXPECTED_NFN = 82

# ---------------------------------------------------------------------------
# C-pattern definitions (identical to diagnose_c_patterns.py)
# ---------------------------------------------------------------------------
C_PATTERNS = {
    "c1a": r"https?://\S+",
    "c1b": r"(紹介コード|アフィリエイト|ref=|affiliate|amzn\.to|bit\.ly)",
    "c2a": r"(LINE|ライン|公式LINE|@\w+|メールアドレス|電話番号|\d{2,4}-\d{2,4}-\d{4})",
    "c2b": (r"(フォロー|登録|チャンネル登録|Instagram|インスタ|TikTok|ティックトック"
            r"|Twitter|X\.com|Facebook|フェイスブック|Telegram|Discord|Slack)"),
    "c3a": r"(投げ銭|カンパ|お布施|寄付|サポート|支援金)",
    "c3b": (r"(¥[\d,]+|円|購入|買う|申し込み|お申し込み|有料|販売|セール|割引"
            r"|教材|書籍|商品|コンテンツ)"),
    "c4a": r"(セミナー|勉強会|説明会|ウェビナー|オンライン講座|講演会)",
    "c4b": r"(入会|入信|入門|メンバー登録|コミュニティ参加|サロン|会員)",
    "c5a": r"(住所|〒\d{3}|来館|ご来店|お越し|道場|教会|会館)",
    "c5c": r"(フォーム|アンケート|診断|無料診断|チェックリスト|申請)",
}
C_KEYS = list(C_PATTERNS.keys())

# ---------------------------------------------------------------------------
# Fisher exact test (two-sided)
# ---------------------------------------------------------------------------
def _log_hypergeometric(a, b, c, d):
    from math import lgamma
    n = a + b + c + d
    return (lgamma(a + b + 1) + lgamma(c + d + 1) +
            lgamma(a + c + 1) + lgamma(b + d + 1) -
            lgamma(n + 1) - lgamma(a + 1) - lgamma(b + 1) -
            lgamma(c + 1) - lgamma(d + 1))


def fisher_exact_2x2(a, b, c, d):
    """Two-sided Fisher exact test.
    Returns (odds_ratio, ci_lo, ci_hi, p_value).
    a = FN positive, b = FN negative
    c = NFN positive, d = NFN negative
    """
    log_p_obs = _log_hypergeometric(a, b, c, d)
    n = a + b + c + d
    r1 = a + b
    c1 = a + c
    p = 0.0
    for x in range(max(0, r1 + c1 - n), min(r1, c1) + 1):
        y = r1 - x
        z = c1 - x
        w = (c + d) - z
        if y < 0 or z < 0 or w < 0:
            continue
        lp = _log_hypergeometric(x, y, z, w)
        if lp <= log_p_obs + 1e-10:
            p += math.exp(lp)

    if b * c > 0:
        or_val = (a * d) / (b * c)
    elif a > 0 and d > 0:
        or_val = float("inf")
    else:
        or_val = float("nan")

    if all(v > 0 for v in [a, b, c, d]):
        se = math.sqrt(1/a + 1/b + 1/c + 1/d)
        ci_lo = math.exp(math.log(or_val) - 1.96 * se)
        ci_hi = math.exp(math.log(or_val) + 1.96 * se)
    else:
        ci_lo = ci_hi = float("nan")

    return or_val, ci_lo, ci_hi, p


def bonferroni(p, m):
    return min(p * m, 1.0)


def bh_fdr(p_values):
    """Benjamini-Hochberg FDR correction.
    Returns list of q-values in original order.
    """
    m = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    q_values = [1.0] * m
    min_q = 1.0
    for rank, (orig_i, p) in enumerate(reversed(indexed)):
        rank_from_top = m - rank
        q = p * m / rank_from_top
        min_q = min(min_q, q)
        q_values[orig_i] = min_q
    return q_values

# ---------------------------------------------------------------------------
# Block 1: Group definition
# ---------------------------------------------------------------------------
def load_groups():
    rows = []
    with open(MASTER_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    fn_group  = [r for r in rows
                 if r["human_label"] == "HIGH"
                 and 0 < float(r["cmi"] or 0) < 41]
    nfn_group = [r for r in rows
                 if r["human_label"] != "HIGH"
                 and float(r["cmi"] or 0) > 0]

    print("=" * 60)
    print("Block 1: Group definition")
    print("=" * 60)
    print(f"  FN group  (human_label=HIGH, 0<CMI<41): n={len(fn_group)}")
    print(f"  Non-FN group (human_label!=HIGH, CMI>0): n={len(nfn_group)}")

    errors = []
    if len(fn_group) != EXPECTED_FN:
        errors.append(
            f"  ERROR: FN group expected n={EXPECTED_FN}, "
            f"observed n={len(fn_group)}"
        )
    if len(nfn_group) != EXPECTED_NFN:
        errors.append(
            f"  ERROR: Non-FN group expected n={EXPECTED_NFN}, "
            f"observed n={len(nfn_group)}"
        )
    if errors:
        for e in errors:
            print(e)
        print("  HALTED: group size mismatch. "
              "Verify corpus_master before proceeding.")
        sys.exit(1)

    print("  Group sizes match expected values. Proceeding.")
    return fn_group, nfn_group

# ---------------------------------------------------------------------------
# Detect c-pattern hits in corpus_clean
# ---------------------------------------------------------------------------
def detect_hits(targets):
    """Return dict: target -> dict of c-key -> bool."""
    results = {}
    for t in targets:
        fpath = os.path.join(CORPUS_CLEAN_DIR, t + ".txt")
        if not os.path.exists(fpath):
            print(f"  WARNING: {fpath} not found. Treating as no-hit.")
            results[t] = {k: False for k in C_KEYS}
            continue
        with open(fpath, encoding="utf-8") as f:
            text = f.read()
        results[t] = {k: bool(re.search(C_PATTERNS[k], text))
                      for k in C_KEYS}
    return results

# ---------------------------------------------------------------------------
# Block 2: Ten-test Fisher exact batch
# ---------------------------------------------------------------------------
def block2_ten_test(fn_group, nfn_group):
    print()
    print("=" * 60)
    print("Block 2: Ten-test Fisher exact batch (c1a-c5c)")
    print("=" * 60)

    fn_targets  = [r["target"] for r in fn_group]
    nfn_targets = [r["target"] for r in nfn_group]

    fn_hits  = detect_hits(fn_targets)
    nfn_hits = detect_hits(nfn_targets)

    results = []
    p_values = []
    for key in C_KEYS:
        a = sum(1 for t in fn_targets  if fn_hits[t][key])
        b = len(fn_targets)  - a
        c = sum(1 for t in nfn_targets if nfn_hits[t][key])
        d = len(nfn_targets) - c
        or_val, ci_lo, ci_hi, p = fisher_exact_2x2(a, b, c, d)
        p_bonf = bonferroni(p, 10)
        results.append({
            "category": key,
            "fn_pos": a, "fn_neg": b,
            "nfn_pos": c, "nfn_neg": d,
            "or": or_val, "ci_lo": ci_lo, "ci_hi": ci_hi,
            "p_raw": p, "p_bonf": p_bonf,
        })
        p_values.append(p)

    q_values = bh_fdr(p_values)
    for i, res in enumerate(results):
        res["bh_q"] = q_values[i]

    for res in results:
        print(f"  {res['category']}: "
              f"FN={res['fn_pos']}/{res['fn_pos']+res['fn_neg']} "
              f"NFN={res['nfn_pos']}/{res['nfn_pos']+res['nfn_neg']} "
              f"OR={res['or']:.2f} "
              f"95%CI[{res['ci_lo']:.2f},{res['ci_hi']:.2f}] "
              f"p={res['p_raw']:.3f} "
              f"Bonf={res['p_bonf']:.3f} "
              f"BH-q={res['bh_q']:.3f}")

    return results, fn_hits, nfn_hits

# ---------------------------------------------------------------------------
# Block 3: Cluster-aggregated sensitivity analysis (c2b)
# ---------------------------------------------------------------------------
def block3_cluster_sensitivity(fn_group, nfn_group, fn_hits, nfn_hits,
                               category="c2b"):
    print()
    print("=" * 60)
    print(f"Block 3: Cluster-aggregated sensitivity analysis ({category})")
    print("=" * 60)

    # Load cluster definitions
    cluster_map = {}  # target -> cluster_id
    with open(CLUSTER_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cluster_map[row["target"]] = row["cluster_id"]

    fn_targets = [r["target"] for r in fn_group]

    # Aggregate FN group
    used_clusters = set()
    agg_fn = []
    for t in fn_targets:
        cl = cluster_map.get(t)
        if cl:
            if cl in used_clusters:
                continue
            used_clusters.add(cl)
            # Cluster positive if any member is positive
            members = [t2 for t2 in fn_targets
                       if cluster_map.get(t2) == cl]
            pos = any(fn_hits[m][category] for m in members)
            agg_fn.append((cl, pos))
        else:
            agg_fn.append((t, fn_hits[t][category]))

    nfn_targets = [r["target"] for r in nfn_group]
    agg_nfn = [(t, nfn_hits[t][category]) for t in nfn_targets]

    a = sum(1 for _, v in agg_fn  if v)
    b = sum(1 for _, v in agg_fn  if not v)
    c = sum(1 for _, v in agg_nfn if v)
    d = sum(1 for _, v in agg_nfn if not v)

    or_val, ci_lo, ci_hi, p = fisher_exact_2x2(a, b, c, d)

    print(f"  Aggregated FN group: n={a+b} "
          f"(original n={len(fn_targets)}, reduced by {len(fn_targets)-(a+b)})")
    print(f"  {category} positive: FN={a}/{a+b}, NFN={c}/{c+d}")
    print(f"  OR={or_val:.2f}, 95%CI[{ci_lo:.2f},{ci_hi:.2f}], p={p:.3f}")

    return {
        "category": category,
        "agg_n_fn": a + b,
        "fn_pos": a, "fn_neg": b,
        "nfn_pos": c, "nfn_neg": d,
        "or": or_val, "ci_lo": ci_lo, "ci_hi": ci_hi,
        "p": p,
    }

# ---------------------------------------------------------------------------
# Block 4/5: Context validity analysis (conditional)
# ---------------------------------------------------------------------------
def _validity_analysis(csv_path, pattern_name):
    """Read validity sheet and compute three-pattern Fisher exact results."""
    judgments = {}  # target -> list of judgments
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row["target"]
            g = row["group"]   # FN or NFN
            j = row["judgment"].strip().lower()
            judgments.setdefault(t, {"group": g, "judgments": []})
            judgments[t]["judgments"].append(j)

    def doc_valid(judgments_list, m_as):
        """Document-level validity: True if any hit judged as m_as."""
        resolved = [j if j != "m" else m_as for j in judgments_list]
        return "y" in resolved

    patterns = [
        ("main",   None),   # m excluded
        ("m_as_y", "y"),
        ("m_as_n", "n"),
    ]

    results = {}
    for label, m_as in patterns:
        fn_valid = nfn_valid = fn_total = nfn_total = 0
        for t, data in judgments.items():
            g = data["group"]
            jlist = data["judgments"]
            if m_as is None:
                # Exclude documents where all hits are m
                if all(j == "m" for j in jlist):
                    continue
                valid = "y" in jlist
            else:
                valid = doc_valid(jlist, m_as)

            if g == "FN":
                fn_total += 1
                if valid:
                    fn_valid += 1
            else:
                nfn_total += 1
                if valid:
                    nfn_valid += 1

        a, b = fn_valid, fn_total - fn_valid
        c, d = nfn_valid, nfn_total - nfn_valid
        or_val, ci_lo, ci_hi, p = fisher_exact_2x2(a, b, c, d)
        results[label] = {
            "fn_valid": a, "fn_total": fn_total,
            "nfn_valid": c, "nfn_total": nfn_total,
            "or": or_val, "ci_lo": ci_lo, "ci_hi": ci_hi, "p": p,
        }

    return results


def block4_c2b_validity():
    print()
    print("=" * 60)
    print("Block 4: c2b context validity analysis")
    print("=" * 60)
    if not os.path.exists(C2B_VALIDITY_CSV):
        print("  c2b_validity_sheet.csv not found. Block 4 skipped.")
        return None
    res = _validity_analysis(C2B_VALIDITY_CSV, "c2b")
    for label, r in res.items():
        print(f"  [{label}] FN={r['fn_valid']}/{r['fn_total']} "
              f"NFN={r['nfn_valid']}/{r['nfn_total']} "
              f"OR={r['or']:.2f} 95%CI[{r['ci_lo']:.2f},{r['ci_hi']:.2f}] "
              f"p={r['p']:.3f}")
    return res


def block5_c3b_validity():
    print()
    print("=" * 60)
    print("Block 5: c3b context validity analysis")
    print("=" * 60)
    if not os.path.exists(C3B_VALIDITY_CSV):
        print("  c3b_validity_sheet.csv not found. Block 5 skipped.")
        return None
    res = _validity_analysis(C3B_VALIDITY_CSV, "c3b")
    for label, r in res.items():
        print(f"  [{label}] FN={r['fn_valid']}/{r['fn_total']} "
              f"NFN={r['nfn_valid']}/{r['nfn_total']} "
              f"OR={r['or']:.2f} 95%CI[{r['ci_lo']:.2f},{r['ci_hi']:.2f}] "
              f"p={r['p']:.3f}")
    return res

# ---------------------------------------------------------------------------
# Block 6: Manuscript transcription block
# ---------------------------------------------------------------------------
def block6_transcription(fn_group, nfn_group,
                          ten_results, cluster_res, cluster_res_c3b,
                          c2b_validity, c3b_validity):
    print()
    print("=" * 60)
    print("Block 6: Manuscript transcription block")
    print("=" * 60)
    print()
    print("=== §5.8 manuscript transcription block ===")
    print()

    fn_n  = len(fn_group)
    nfn_n = len(nfn_group)
    print(f"[Group definition]")
    print(f"FN group: n={fn_n} (human_label=HIGH, CMI>0, CMI<41)")
    print(f"Non-FN group: n={nfn_n} (human_label != HIGH, CMI>0)")
    print()

    # c2b main
    c2b = next(r for r in ten_results if r["category"] == "c2b")
    print(f"[c2b: SNS follow induction]")
    print(f"Main: {c2b['fn_pos']}/{fn_n} vs {c2b['nfn_pos']}/{nfn_n}; "
          f"OR={c2b['or']:.2f}, 95% CI [{c2b['ci_lo']:.2f}, {c2b['ci_hi']:.2f}], "
          f"p={c2b['p_raw']:.3f}; Bonferroni p={c2b['p_bonf']:.3f}; "
          f"BH q={c2b['bh_q']:.3f}")
    cr = cluster_res
    print(f"Cluster-aggregated: n={cr['agg_n_fn']}, "
          f"OR={cr['or']:.2f}, 95% CI [{cr['ci_lo']:.2f}, {cr['ci_hi']:.2f}], "
          f"p={cr['p']:.3f}")
    if c2b_validity:
        m = c2b_validity["main"]
        print(f"Context validity (main): "
              f"FN={m['fn_valid']}/{m['fn_total']} valid, "
              f"NFN={m['nfn_valid']}/{m['nfn_total']} valid, "
              f"OR={m['or']:.2f}, 95% CI [{m['ci_lo']:.2f}, {m['ci_hi']:.2f}], "
              f"p={m['p']:.3f}")
    else:
        print(f"Context validity: pending (sheet not found)")
    print()

    # c3b main
    c3b = next(r for r in ten_results if r["category"] == "c3b")
    print(f"[c3b: purchase-related vocabulary]")
    print(f"Main: {c3b['fn_pos']}/{fn_n} vs {c3b['nfn_pos']}/{nfn_n}; "
          f"OR={c3b['or']:.2f}, 95% CI [{c3b['ci_lo']:.2f}, {c3b['ci_hi']:.2f}], "
          f"p={c3b['p_raw']:.3f}; Bonferroni p={c3b['p_bonf']:.3f}; "
          f"BH q={c3b['bh_q']:.3f}")
    cr3 = cluster_res_c3b
    print(f"Cluster-aggregated: n={cr3['agg_n_fn']}, "
          f"OR={cr3['or']:.2f}, 95% CI [{cr3['ci_lo']:.2f}, {cr3['ci_hi']:.2f}], "
          f"p={cr3['p']:.3f}")
    if c3b_validity:
        m = c3b_validity["main"]
        print(f"Context validity (main): "
              f"FN={m['fn_valid']}/{m['fn_total']} valid, "
              f"NFN={m['nfn_valid']}/{m['nfn_total']} valid, "
              f"OR={m['or']:.2f}, 95% CI [{m['ci_lo']:.2f}, {m['ci_hi']:.2f}], "
              f"p={m['p']:.3f}")
    else:
        print(f"Context validity: pending (sheet not found)")
    print()

    print(f"[Full 10-test results]")
    print(f"-> See supplementary_table_s1.csv")
    print()
    print("=" * 60)

# ---------------------------------------------------------------------------
# Block 7: Supplementary Table CSV
# ---------------------------------------------------------------------------
def block7_supp_table(ten_results, fn_n, nfn_n):
    print()
    print("=" * 60)
    print("Block 7: Supplementary Table CSV output")
    print("=" * 60)

    fieldnames = [
        "category", "fn_n", "nfn_n",
        "fn_positive", "nfn_positive",
        "odds_ratio", "ci_95_lo", "ci_95_hi",
        "p_raw", "p_bonferroni", "bh_q",
    ]
    with open(SUPP_TABLE_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for res in ten_results:
            writer.writerow({
                "category":     res["category"],
                "fn_n":         fn_n,
                "nfn_n":        nfn_n,
                "fn_positive":  res["fn_pos"],
                "nfn_positive": res["nfn_pos"],
                "odds_ratio":   round(res["or"], 4),
                "ci_95_lo":     round(res["ci_lo"], 4),
                "ci_95_hi":     round(res["ci_hi"], 4),
                "p_raw":        round(res["p_raw"], 4),
                "p_bonferroni": round(res["p_bonf"], 4),
                "bh_q":         round(res["bh_q"], 4),
            })
    print(f"  Written: {SUPP_TABLE_CSV}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    fn_group, nfn_group = load_groups()
    ten_results, fn_hits, nfn_hits = block2_ten_test(fn_group, nfn_group)
    cluster_res = block3_cluster_sensitivity(fn_group, nfn_group,
                                             fn_hits, nfn_hits,
                                             category="c2b")
    cluster_res_c3b = block3_cluster_sensitivity(fn_group, nfn_group,
                                                 fn_hits, nfn_hits,
                                                 category="c3b")
    c2b_validity = block4_c2b_validity()
    c3b_validity = block5_c3b_validity()
    block6_transcription(fn_group, nfn_group,
                         ten_results, cluster_res, cluster_res_c3b,
                         c2b_validity, c3b_validity)
    block7_supp_table(ten_results, len(fn_group), len(nfn_group))
    print()
    print("analyze_section58.py completed.")
