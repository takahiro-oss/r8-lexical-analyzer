#!/usr/bin/env python3
"""
gemini_kappa_stability.py
Gemini複数回実行のκ変動を分析するスクリプト

使い方:
  python scripts/gemini_kappa_stability.py \
    --master data/results/corpus_master.csv \
    --runs ailabel/results_gemini.csv ailabel/results_gemini_v2.csv \
           ailabel/results_gemini_v3.csv ailabel/results_gemini_v4.csv \
           ailabel/results_gemini_v5.csv ailabel/results_gemini_v6.csv
"""

import argparse
import csv
import statistics
import os

LABEL_ORDER = ["HIGH", "MEDIUM", "LOW"]


def load_csv(path):
    """CSVからtarget→ai_labelのdictを返す"""
    results = {}
    model = None
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            t = row["target"].strip()
            ai = row.get("ai_label", "").strip()
            if not model:
                model = row.get("model", "unknown").strip()
            results[t] = ai
    return model, results


def load_human_labels(master_path):
    """corpus_masterからtarget→human_labelを返す"""
    labels = {}
    with open(master_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            labels[row["target"]] = row.get("human_label", "").strip()
    return labels


def cohen_kappa(labels_a, labels_b):
    n = len(labels_a)
    if n == 0:
        return 0.0
    po = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    cats = set(labels_a + labels_b)
    pe = sum((labels_a.count(c) / n) * (labels_b.count(c) / n) for c in cats)
    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


def calc_kappa_for_run(ai_dict, human_dict):
    """1回の実行結果とhuman_labelのκを計算"""
    ai_labels, hu_labels = [], []
    for t, ai in ai_dict.items():
        hu = human_dict.get(t, "")
        if ai in LABEL_ORDER and hu in LABEL_ORDER:
            ai_labels.append(ai)
            hu_labels.append(hu)
    k = cohen_kappa(ai_labels, hu_labels)
    return k, len(ai_labels)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default="data/results/corpus_master.csv")
    parser.add_argument("--runs", nargs="+", required=True,
                        help="各実行のCSVファイルパス（複数指定）")
    parser.add_argument("--out", default="ailabel/kappa_stability.csv")
    args = parser.parse_args()

    human_dict = load_human_labels(args.master)
    print(f"human_label読み込み: {len(human_dict)}件\n")

    kappas = []
    rows = []

    print("=" * 55)
    print("  各実行のκ（vs human_label）")
    print("=" * 55)

    for i, path in enumerate(args.runs, 1):
        if not os.path.exists(path):
            print(f"  Run {i}: {path} — ファイルが見つかりません")
            continue
        model, ai_dict = load_csv(path)
        k, n = calc_kappa_for_run(ai_dict, human_dict)
        kappas.append(k)
        rows.append({"run": i, "file": path, "model": model, "kappa": round(k, 3), "n": n})
        print(f"  Run {i} ({os.path.basename(path)}): κ={k:.3f} (n={n})")

    if len(kappas) >= 2:
        print()
        print("=" * 55)
        print("  κ変動統計")
        print("=" * 55)
        mean_k = statistics.mean(kappas)
        sd_k = statistics.stdev(kappas) if len(kappas) >= 2 else 0.0
        min_k = min(kappas)
        max_k = max(kappas)
        print(f"  実行回数: {len(kappas)}")
        print(f"  平均κ:   {mean_k:.3f}")
        print(f"  SD:      {sd_k:.3f}")
        print(f"  範囲:    {min_k:.3f} – {max_k:.3f}")
        print(f"  変動幅:  {max_k - min_k:.3f}")

    # CSV出力
    os.makedirs(os.path.dirname(args.out) if os.path.dirname(args.out) else ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["run", "file", "model", "kappa", "n"])
        writer.writeheader()
        writer.writerows(rows)
        if len(kappas) >= 2:
            writer.writerow({
                "run": "summary", "file": "",
                "model": f"mean={mean_k:.3f} SD={sd_k:.3f} range={min_k:.3f}-{max_k:.3f}",
                "kappa": round(mean_k, 3), "n": ""
            })
    print(f"\n結果を保存: {args.out}")


if __name__ == "__main__":
    main()
