#!/usr/bin/env python3
# mass_audit.py — R8 Batch Auditor v4
# CMI (Cognitive Manipulation Index) 対応版
# v2の機能 + Gemini版の良点（追記モード・timestamp・run_audit分離）を統合

import sys
import io
import re
import os
import csv
from datetime import datetime

# Windows cp932環境でのUnicodeEncodeError対策
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp932", "shift_jis", "shift-jis", "mbcs"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# --- r8.py を同一ディレクトリからインポート ---
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import r8
    from r8 import THRESHOLDS, WEIGHTS, CATEGORY_LABELS, cmi_level
except ImportError:
    print("[ERROR] r8.py not found. Place it in the same directory as mass_audit.py.")
    sys.exit(1)

# --- 外部ライブラリ ---
try:
    import requests
    from bs4 import BeautifulSoup
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

try:
    import fitz
    PDF_ENGINE = "pymupdf"
except ImportError:
    PDF_ENGINE = None

# ===========================
# テキスト取得
# ===========================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def fetch_url(url):
    if not WEB_AVAILABLE:
        return None, "[ERROR] requests/BeautifulSoup not available"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text, None
    except Exception as e:
        return None, f"[ERROR] Failed to fetch URL: {e}"

def fetch_pdf(path):
    if not PDF_ENGINE:
        return None, "[ERROR] PyMuPDF not available"
    try:
        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc), None
    except Exception as e:
        return None, f"[ERROR] Failed to read PDF: {e}"

def fetch_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(), None
    except FileNotFoundError:
        return None, f"[ERROR] File not found: {path}"

def get_text(target):
    if target.startswith("http://") or target.startswith("https://"):
        return fetch_url(target)
    if target.lower().endswith(".pdf"):
        return fetch_pdf(target)
    return fetch_text(target)

# ===========================
# 1件分析（Gemini版由来: 関数分離）
# ===========================
def run_audit(target):
    """
    1ターゲットを分析して結果辞書を返す。
    エラー時も同じ構造で返すため呼び出し側でのハンドリングが簡潔になる。
    """
    text, error = get_text(target)

    base = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target":    target,
        "cmi":       "",
        "level":     "ERROR",
        "error":     None,
    }
    # カテゴリ列を空で初期化（エラー時もCSV行が揃う）
    for cat in CATEGORY_LABELS:
        base[cat] = ""

    if error:
        base["error"] = error
        return base
    if not text or len(text.strip()) < 50:
        base["error"] = "[ERROR] Text too short (fewer than 50 characters)"
        return base

    raw = r8.analyze(text)
    ri  = {cat: min(raw.get(cat, 0) / THRESHOLDS[cat], 1.0) for cat in WEIGHTS}
    cmi = round(sum(WEIGHTS[c] * ri[c] * 100 for c in WEIGHTS), 1)

    base["cmi"]   = cmi
    base["level"] = cmi_level(cmi).split()[0]
    for cat in CATEGORY_LABELS:
        base[cat] = round(ri.get(cat, 0), 3)

    return base

# ===========================
# ターゲットリスト読み込み
# ===========================
def load_targets(list_file):
    """
    以下の形式に対応:
    - 1行1エントリのテキストファイル（# コメント行はスキップ）
    - CSVファイル: source列 または 1列目を使用（ヘッダー行自動スキップ）
    """
    targets = []
    is_csv  = list_file.lower().endswith(".csv")

    with open(list_file, "r", encoding="utf-8-sig", errors="ignore") as f:
        if is_csv:
            reader = csv.DictReader(f)
            for row in reader:
                val = row.get("source", list(row.values())[0] if row else "").strip()
                if val and not val.startswith("#"):
                    targets.append(val)
        else:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    targets.append(line)
    return targets

# ===========================
# 出力フォーマット
# ===========================
def bar(v, width=16):
    filled = max(0, min(width, round(v * width)))
    return "[" + "█" * filled + "░" * (width - filled) + f"] {v:.2f}"

def print_summary(results):
    """results: list of run_audit()が返す辞書"""
    ok = [r for r in results if r["error"] is None]
    ng = [r for r in results if r["error"] is not None]
    ok_sorted = sorted(ok, key=lambda x: x["cmi"], reverse=True)

    print("\n" + "=" * 60)
    print("  R8 Mass Audit v3 — CMI Ranking (highest risk first)")
    print("=" * 60)

    for rank, res in enumerate(ok_sorted, 1):
        level = cmi_level(res["cmi"])
        label = os.path.basename(res["target"])[:42]
        print(f"\n  #{rank:02d}  CMI: {res['cmi']:5.1f}  [{level}]")
        print(f"       {label}")
        flagged = {cat: res[cat] for cat in CATEGORY_LABELS if isinstance(res[cat], float) and res[cat] >= 0.5}
        if flagged:
            top = sorted(flagged.items(), key=lambda x: x[1], reverse=True)[:4]
            for cat, v in top:
                lbl = CATEGORY_LABELS[cat].split("(")[0].strip()
                print(f"       {lbl:<30} {bar(v)}")
        else:
            print(f"       (no flags)")

    if ng:
        print(f"\n  --- Fetch failed: {len(ng)} item(s) ---")
        for r in ng:
            print(f"  {os.path.basename(r['target'])}: {r['error']}")

    print("\n" + "=" * 60)
    if ok_sorted:
        avg = sum(r["cmi"] for r in ok_sorted) / len(ok_sorted)
        hi  = sum(1 for r in ok_sorted if r["cmi"] >= 60)
        med = sum(1 for r in ok_sorted if 35 <= r["cmi"] < 60)
        lo  = sum(1 for r in ok_sorted if r["cmi"] < 35)
        print(f"  Count: {len(ok_sorted)}  Avg CMI: {avg:.1f}")
        print(f"  HIGH: {hi}  MEDIUM: {med}  LOW: {lo}")
    print("=" * 60 + "\n")

def save_csv(results, output_path, append=False):
    """
    結果をCSVに保存。
    append=True の場合は追記モード（Gemini版由来）。
    ファイルが存在しない場合はヘッダーを自動付与。
    """
    file_exists = os.path.isfile(output_path)
    mode = "a" if append else "w"

    fieldnames = ["timestamp", "target", "cmi", "level", "error"] + list(CATEGORY_LABELS.keys()) + ["human_label", "riskfactor"]

    with open(output_path, mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        # 新規ファイル or 上書きモードの場合はヘッダーを書く
        if not file_exists or not append:
            writer.writeheader()
        for res in results:
            # human_label, riskfactorが未設定なら空文字で初期化
            if "human_label" not in res:
                res["human_label"] = ""
            if "riskfactor" not in res:
                res["riskfactor"] = ""
            writer.writerow(res)

    print(f"  [CSV] Saved: {output_path}")
    print(f"  [INFO] human_label column: enter 1=HIGH 2=MEDIUM 3=LOW")
    print(f"  [INFO] riskfactor column: enter a code number (see below)")
    print(f"         1=No academic/empirical support")
    print(f"         2=Potential concealment of adverse info")
    print(f"         3=Emotional Induction")
    print(f"         4=Desire Activation")
    print(f"         5=Fear/Urgency Manipulation")
    print(f"         6=Normative Induction via Emotional Grounding")
    print(f"         7=Authority Halo")
    print(f"         Note: FP/FN classification is computed post-hoc by comparing level vs human_label; annotators do not assign these codes.")


# ===========================
# auto-label: targets.csvへの自動追記
# ===========================
def auto_label_and_append(results, targets_csv):
    """
    スキャン結果をtargets.csvに自動追記する。
    CMIからlabelを自動判定。既存エントリは上書きしない。
    """
    # 既存エントリを読み込む
    existing = set()
    if os.path.isfile(targets_csv):
        with open(targets_csv, "r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.add(row.get("source", "").strip())

    added = 0
    with open(targets_csv, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        # ヘッダーがなければ追加
        if not os.path.isfile(targets_csv) or os.path.getsize(targets_csv) == 0:
            writer.writerow(["source", "label", "note"])

        for res in results:
            if res["error"]:
                continue
            target = res["target"]
            if target in existing:
                print(f"  [SKIP] Already exists: {os.path.basename(target)}")
                continue
            label = cmi_level(res["cmi"]).split()[0]
            note  = f"CMI{res['cmi']:.1f} auto-appended"
            writer.writerow([target, label, note])
            print(f"  [ADD]  {os.path.basename(target)[:40]} -> {label} (CMI {res['cmi']:.1f})")
            added += 1

    print(f"\n  Appended {added} entry(ies) to targets.csv: {targets_csv}")
    return added

# ===========================
# 統計サマリー
# ===========================
def print_corpus_stats(targets_csv):
    """
    targets.csvの現在の全サンプルを統計解析して表示する。
    """
    if not os.path.isfile(targets_csv):
        print("  [Stats] targets.csv not found")
        return

    rows = []
    with open(targets_csv, "r", encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("  [Stats] No samples found")
        return

    total  = len(rows)
    high   = [r for r in rows if r.get("label","").upper() == "HIGH"]
    medium = [r for r in rows if r.get("label","").upper() == "MEDIUM"]
    low    = [r for r in rows if r.get("label","").upper() == "LOW"]

    # CMI値を抽出（noteに含まれる場合）
    import re
    cmis = []
    for r in rows:
        note = r.get("note", "")
        m = re.search(r"CMI(\d+\.?\d*)", note)
        if m:
            cmis.append(float(m.group(1)))

    print("\n" + "=" * 60)
    print("  Corpus statistics summary")
    print("=" * 60)
    print(f"  Total samples : {total}  (target: 60, progress: {total/60*100:.0f}%)")
    print(f"  HIGH          : {len(high)}  (target: 20)")
    print(f"  MEDIUM        : {len(medium)}  (target: 20)")
    print(f"  LOW           : {len(low)}  (target: 20)")
    if cmis:
        print(f"\n  CMI statistics ({len(cmis)} recorded)")
        print(f"  Mean CMI  : {sum(cmis)/len(cmis):.1f}")
        print(f"  Max CMI   : {max(cmis):.1f}")
        print(f"  Min CMI   : {min(cmis):.1f}")

    # 不足カテゴリの警告
    print("\n  [Priority collection categories]")
    if len(high) < 20:
        print(f"  [WARN] HIGH   needs {20-len(high)} more")
    if len(medium) < 20:
        print(f"  [WARN] MEDIUM needs {20-len(medium)} more")
    if len(low) < 20:
        print(f"  [WARN] LOW    needs {20-len(low)} more")
    if len(high) >= 20 and len(medium) >= 20 and len(low) >= 20:
        print(f"  [OK] All category targets met")
    print("=" * 60 + "\n")

# ===========================
# scan log: mechanical provenance recording
# ===========================
SCAN_LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "results", "corpus_scan_log.csv"
)

def _get_r8_version():
    """Return r8.py VERSION constant safely; 'unknown' if absent."""
    return getattr(r8, "VERSION", "unknown")

def append_scan_log(results, caller="mass_audit.py", extra=None):
    """
    Append measurement provenance to corpus_scan_log.csv on every scan.

    Records source path, script, timestamp, and r8 version so that any
    corpus_master value can later be traced to the exact input and run.

    - Logging failure never halts the main process (isolated by try/except).
    - error-bearing results are also recorded, for completeness of provenance.

    [EXTENSION POINT] `extra`: pass {column: value} to append extra columns.
        Omit it for current behaviour (existing callers need no change).
        To add new provenance fields in future, pass them via `extra`
        instead of editing the core schema below.

    [SCHEMA NOTE] Because `extra` lets new columns appear from a certain row
        onward, row width may vary across the file's history. This is safe
        when read with csv.DictReader (missing keys become None), but a tool
        expecting a strict fixed schema should be aware of it.
    """
    try:
        os.makedirs(os.path.dirname(SCAN_LOG_PATH), exist_ok=True)
        file_exists = os.path.isfile(SCAN_LOG_PATH)
        # Continue scan_id sequence from existing max
        next_id = 1
        if file_exists:
            try:
                with open(SCAN_LOG_PATH, "r", encoding="utf-8-sig", errors="ignore") as f:
                    rows = list(csv.DictReader(f))
                    if rows:
                        next_id = max(int(r["scan_id"]) for r in rows if r.get("scan_id", "").isdigit()) + 1
            except Exception:
                next_id = 1  # keep appending even if read fails
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ver = _get_r8_version()
        core_fields = ["scan_id", "target", "scan_source", "scan_script",
                       "scan_date", "cmi", "level", "r8_version", "error"]
        # [EXTENSION POINT] extra keys are appended as trailing columns; core order stays fixed
        extra_keys = list(extra.keys()) if extra else []
        fieldnames = core_fields + extra_keys
        with open(SCAN_LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            for res in results:
                row = {
                    "scan_id":     next_id,
                    "target":      res.get("target", ""),
                    "scan_source": res.get("target", ""),
                    "scan_script": caller,
                    "scan_date":   ts,
                    "cmi":         res.get("cmi", ""),
                    "level":       res.get("level", ""),
                    "r8_version":  ver,
                    "error":       res.get("error") or "",
                }
                if extra:
                    row.update(extra)
                writer.writerow(row)
                next_id += 1
        print(f"  [SCANLOG] {len(results)} record(s) appended: {SCAN_LOG_PATH}")
    except Exception as e:
        print(f"  [SCANLOG][WARN] Failed to write scan log; continuing: {e}")


# ===========================
# バッチ実行
# ===========================
def run(targets, csv_out=None, append=False):
    results = []
    total   = len(targets)

    print(f"\n[Mass Audit] Processing {total} target(s)...\n")

    for i, target in enumerate(targets, 1):
        label = os.path.basename(target)[:50]
        print(f"  [{i:02d}/{total:02d}] {label} ", end="", flush=True)
        res = run_audit(target)
        if res["error"]:
            print(f"-> FAILED: {res['error']}")
        else:
            level = cmi_level(res["cmi"]).split()[0]
            print(f"-> CMI: {res['cmi']:5.1f}  [{level}]")
        results.append(res)

    append_scan_log(results)
    print_summary(results)

    if csv_out:
        save_csv(results, csv_out, append=append)

    return results

# ===========================
# エントリポイント
# ===========================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="R8 Mass Audit v3 — バッチCMIスキャナ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方の例:
  # CSVリストから一括スキャン（CSV自動出力）
  python mass_audit.py data/targets/targets.csv

  # 出力先を指定
  python mass_audit.py data/targets/targets.csv --out data/results/result.csv

  # 既存CSVに追記
  python mass_audit.py data/targets/targets.csv --out data/results/result.csv --append

  # ターゲットを直接指定
  python mass_audit.py --targets https://example.com file.txt doc.pdf
        """
    )
    parser.add_argument("list_file", nargs="?", help="ターゲットリスト (.txt or .csv)")
    parser.add_argument("--targets", nargs="+", help="ターゲットを直接指定")
    parser.add_argument("--out",    metavar="FILE", help="出力CSVパス")
    parser.add_argument("--append",     action="store_true", help="既存CSVに追記する")
    parser.add_argument("--auto-label", action="store_true", help="CMIから自動でlabel判定しtargets.csvに追記")
    parser.add_argument("--stats",      action="store_true", help="targets.csvの統計サマリーを表示")

    args = parser.parse_args()

    targets = []
    if args.list_file:
        if not os.path.exists(args.list_file):
            print(f"[ERROR] File not found: {args.list_file}")
            sys.exit(1)
        targets = load_targets(args.list_file)
    elif args.targets:
        targets = args.targets
    else:
        parser.print_help()
        sys.exit(1)

    if not targets:
        print("[ERROR] No targets specified.")
        sys.exit(1)

    csv_out = args.out
    if not csv_out:
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "results")
        os.makedirs(results_dir, exist_ok=True)
        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_out = os.path.join(results_dir, f"r8_audit_{ts}.csv")

    results = run(targets, csv_out, append=args.append)

    # auto-label: targets.csvへの自動追記
    if getattr(args, 'auto_label', False):
        targets_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "targets", "targets.csv")
        auto_label_and_append(results, targets_csv)

    # stats: 統計サマリー表示
    if getattr(args, 'stats', False) or getattr(args, 'auto_label', False):
        targets_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "targets", "targets.csv")
        print_corpus_stats(targets_csv)
