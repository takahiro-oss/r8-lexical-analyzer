"""
remove_duplicate.py
BL_017（AD_019の重複コンテンツ）をコーパスから削除する。

削除対象:
  corpus/corpus_archive/BL_017_20260326.txt
  corpus/corpus_clean/BL_017.txt
  data/results/corpus_master.csv
  data/results/corpus_paths.csv
  data/results/audit_results_v3.csv

xlsmの7行目削除はTAKAHIROが手動で行うこと。
"""

import os, csv, shutil
from datetime import datetime

_B = os.environ.get("R8_BASE")
if not _B:
    raise SystemExit(
        "R8_BASE is not set. Point it at your R8 data root, e.g.\n"
        "  Windows : set R8_BASE=X:\\\\path\\\\to\\\\r8_strategy\n"
        "  POSIX   : export R8_BASE=/path/to/r8_strategy")

BASE = _B

TARGET = "BL_017"
ARCHIVE_TXT  = os.path.join(BASE, "corpus", "corpus_archive", "BL_017_20260326.txt")
CLEAN_TXT    = os.path.join(BASE, "corpus", "corpus_clean", "BL_017.txt")
MASTER_CSV   = os.path.join(BASE, "data", "results", "corpus_master.csv")
PATHS_CSV    = os.path.join(BASE, "data", "results", "corpus_paths.csv")
AUDIT_CSV    = os.path.join(BASE, "data", "results", "audit_results_v3.csv")

def remove_csv_row(path, target_col, target_val):
    """CSVからtarget_val行を除去して上書き保存。除去件数を返す。"""
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    original = len(rows)
    rows = [r for r in rows if r.get(target_col, "").strip() != target_val]
    removed = original - len(rows)

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return removed

def main():
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n=== remove_duplicate.py ===")
    print(f"実行日時: {today}")
    print(f"削除対象: {TARGET}\n")

    # 1. txtファイル削除
    for path, label in [(ARCHIVE_TXT, "corpus_archive"), (CLEAN_TXT, "corpus_clean")]:
        if os.path.exists(path):
            os.remove(path)
            print(f"  削除OK: {label}/{os.path.basename(path)}")
        else:
            print(f"  SKIP（存在しない）: {path}")

    # 2. corpus_master.csv
    removed = remove_csv_row(MASTER_CSV, "target", TARGET)
    print(f"  corpus_master.csv: {removed}行削除")

    # 3. corpus_paths.csv
    removed = remove_csv_row(PATHS_CSV, "target", TARGET)
    print(f"  corpus_paths.csv: {removed}行削除")

    # 4. audit_results_v3.csv
    removed = remove_csv_row(AUDIT_CSV, "target", TARGET)
    print(f"  audit_results_v3.csv: {removed}行削除")

    print(f"\n完了。xlsmの7行目（BL_017）はTAKAHIROが手動削除してください。")
    print(f"corpus件数: 217 → 216件")

if __name__ == "__main__":
    main()
