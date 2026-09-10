"""
clean_corpus.py  v1.2 本番版
処理A（確実除去）のみ。情報損失ゼロ優先。
実行中にチェックを走らせ、問題があれば即停止して報告する。

修正履歴:
  v1.1: 繰り返し除去から数字・順位語を含む行を除外（AD_079対応）
  v1.2: 元から空のファイルをSKIPとして継続処理（BL_014対応）

入力: $R8_BASE/corpus/corpus_archive/*.txt
出力: $R8_BASE/corpus/corpus_clean/*.txt
     $R8_BASE/data/results/corpus_paths.csv（clean_path列を更新）
"""

import os, re, csv
from pathlib import Path
from datetime import datetime
from collections import Counter

_B = os.environ.get("R8_BASE")
if not _B:
    raise SystemExit(
        "R8_BASE is not set. Point it at your R8 data root, e.g.\n"
        "  Windows : set R8_BASE=X:\\\\path\\\\to\\\\r8_strategy\n"
        "  POSIX   : export R8_BASE=/path/to/r8_strategy")

BASE        = _B
ARCHIVE_DIR = os.path.join(BASE, "corpus", "corpus_archive")
CLEAN_DIR   = os.path.join(BASE, "corpus", "corpus_clean")
PATHS_CSV   = os.path.join(BASE, "data", "results", "corpus_paths.csv")

# ────────────────────────────────────────────
# 確実除去パターン（A）
# ────────────────────────────────────────────
DEFINITE_REMOVE = [
    re.compile(r'^\[(SOURCE|DATE|CATEGORY|TEXT)\]'),
    re.compile(r'^\s*https?://\S+\s*$'),
    re.compile(r'^#PR[\s\u3000]'),
    re.compile(r'^\[ad#'),
    re.compile(r'^(#\S+[\s\u3000]*){2,}$'),
    re.compile(r'^画像\d*$'),
    re.compile(r'^コンテンツへスキップ$'),
    re.compile(r'^メニューへスキップ$'),
    re.compile(r'^ナビゲーションへスキップ$'),
    re.compile(r'^Proudly powered by'),
    re.compile(r'^Copyright\s'),
    re.compile(r'^\u00a9 \d{4}'),
    re.compile(r'^All Rights Reserved'),
    re.compile(r'^桜のイラスト$'),
    re.compile(r'^見出し画像$'),
    re.compile(r'^チップで応援する$'),
    re.compile(r'^いいなと思ったら応援しよう'),
    re.compile(r'^よかったらシェアしてね'),
    re.compile(r'^この記事が気に入ったら'),
    re.compile(r'^noteプレミアム$'),
    re.compile(r'^note pro$'),
    re.compile(r'^キーワードやクリエイターで検索$'),
    re.compile(r'^クリエイターへのお問い合わせ$'),
    re.compile(r'^通常ポイント利用特約$'),
    re.compile(r'^加盟店規約$'),
    re.compile(r'^資金決済法に基づく表示$'),
    re.compile(r'^特商法表記$'),
    re.compile(r'^投資情報の免責事項$'),
    re.compile(r'^\s*\u00b7\s*$'),
]

def is_definite_remove(line):
    s = line.strip()
    if not s:
        return False
    for pat in DEFINITE_REMOVE:
        if pat.search(s):
            return True
    return False

def detect_repeating_short(lines, max_len=15, min_count=2):
    """
    max_len文字以下の行がmin_count回以上出現するものを除去候補とする。
    数字・順位語・日付を含む行は除外（ランキングサイト対応）。
    """
    short = []
    for l in lines:
        s = l.strip()
        if not (1 <= len(s) <= max_len):
            continue
        if re.match(r'^[\d\s]+$', s):
            continue
        if re.search(r'\d+\s*位', s):
            continue
        if re.search(r'\d{4}[年./]\d{1,2}', s):
            continue
        if re.search(r'[（(]\d{2}月\d{2}日[）)]', s):
            continue
        short.append(s)

    counts = Counter(short)
    return {line for line, cnt in counts.items() if cnt >= min_count}

# ────────────────────────────────────────────
# 整形処理
# ────────────────────────────────────────────
def clean_text(raw_text):
    lines = raw_text.splitlines()
    repeat_set = detect_repeating_short(lines)

    removed = []
    kept    = []
    for line in lines:
        s = line.strip()
        if not s:
            kept.append(line)
            continue
        if is_definite_remove(line):
            removed.append(("pattern", s))
            continue
        if s in repeat_set:
            removed.append(("repeat", s))
            continue
        kept.append(line)

    text = "\n".join(l.rstrip() for l in kept)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip(), removed

# ────────────────────────────────────────────
# 実行中チェック
# ────────────────────────────────────────────
CRITICAL_THRESHOLD_RATIO = 0.60
MIN_CLEAN_CHARS          = 50

def check_result(src_name, raw_text, cleaned_text, removed):
    """
    severity: "OK" / "WARN" / "SKIP" / "ERROR"
    """
    raw_len   = len(raw_text.strip())
    clean_len = len(cleaned_text)

    # チェック0: 元ファイルが空（取得失敗）→ SKIPして継続
    if raw_len == 0:
        return True, "SKIP", "元ファイルが空（取得失敗）"

    # チェック1: 整形後テキストが短すぎる
    if clean_len < MIN_CLEAN_CHARS:
        return False, "ERROR", (
            f"整形後テキストが{clean_len}文字（閾値{MIN_CLEAN_CHARS}文字）。"
            f"本文が失われた可能性があります。"
        )

    # チェック2: 除去率が異常に高い
    ratio = 1 - clean_len / max(len(raw_text), 1)
    if ratio > CRITICAL_THRESHOLD_RATIO:
        return False, "ERROR", (
            f"除去率{ratio*100:.0f}%（閾値{CRITICAL_THRESHOLD_RATIO*100:.0f}%）。"
            f"本文が失われた可能性があります。"
        )

    # チェック3: 繰り返し除去に句読点を含む行
    suspicious = [
        line for kind, line in removed
        if kind == "repeat"
        and any(c in line for c in "。、！？")
        and len(line) > 10
    ]
    if suspicious:
        return True, "WARN", (
            f"繰り返し除去に句読点を含む行が{len(suspicious)}件あります。"
            f"確認推奨: {suspicious[:3]}"
        )

    return True, "OK", f"正常 ({ratio*100:.0f}%削減, {clean_len:,}文字)"

# ────────────────────────────────────────────
# corpus_paths.csv 更新
# ────────────────────────────────────────────
def load_paths_csv(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return {r["target"]: r for r in rows}

def save_paths_csv(path, records):
    if not records:
        return
    existing_cols = list(list(records.values())[0].keys())
    new_cols = ["clean_path", "clean_applied", "noise_type"]
    all_cols = existing_cols.copy()
    for c in new_cols:
        if c not in all_cols:
            all_cols.append(c)

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols)
        writer.writeheader()
        for row in records.values():
            for c in new_cols:
                if c not in row:
                    row[c] = ""
            writer.writerow(row)

# ────────────────────────────────────────────
# ファイル名正規化
# ────────────────────────────────────────────
def normalize_stem(stem):
    return re.sub(r'_\d{8}$', '', stem)

# ────────────────────────────────────────────
# メイン
# ────────────────────────────────────────────
def run():
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(CLEAN_DIR, exist_ok=True)

    txt_files = sorted(Path(ARCHIVE_DIR).glob("*.txt"))
    total     = len(txt_files)

    print(f"\n=== clean_corpus.py v1.2 本番実行 ===")
    print(f"実行日: {today}")
    print(f"入力:   {ARCHIVE_DIR}")
    print(f"出力:   {CLEAN_DIR}")
    print(f"対象:   {total}件")
    print(f"{'='*60}\n")

    paths_records = load_paths_csv(PATHS_CSV)

    ok_count   = 0
    warn_count = 0
    skip_count = 0
    skipped    = []
    errors     = []
    warnings   = []

    for i, src in enumerate(txt_files, 1):
        stem    = normalize_stem(src.stem)
        dst     = os.path.join(CLEAN_DIR, f"{stem}.txt")
        rel_dst = os.path.relpath(dst, BASE)

        try:
            with open(src, encoding="utf-8", errors="ignore") as f:
                raw = f.read()
        except Exception as e:
            print(f"  [{i:03d}/{total}] ERROR {src.name}: 読み込みエラー: {e}")
            print(f"\n[STOP] 作業停止")
            return False

        cleaned, removed = clean_text(raw)
        ok, severity, message = check_result(src.name, raw, cleaned, removed)

        if severity == "ERROR":
            print(f"  [{i:03d}/{total}] ERROR {src.name}")
            print(f"\n{'='*60}")
            print(f"[STOP] 作業停止: チェックエラー")
            print(f"  ファイル: {src.name}")
            print(f"  問題:     {message}")
            print(f"  除去された行（先頭10件）:")
            for kind, line in removed[:10]:
                print(f"    [{kind}] {line[:60]}")
            print(f"  整形後テキスト（先頭200文字）:")
            print(f"    {cleaned[:200]}")
            print(f"{'='*60}")
            return False

        if severity == "SKIP":
            skip_count += 1
            skipped.append(src.name)
            # corpus_paths に空ファイルとして記録
            if stem in paths_records:
                paths_records[stem]["clean_applied"] = "False"
                paths_records[stem]["noise_type"]    = "empty_file"
            print(f"  [{i:03d}/{total}] SKIP {src.name}: {message}")
            continue  # ファイル書き込みはしない

        if severity == "WARN":
            warn_count += 1
            warnings.append((src.name, message))
            print(f"  [{i:03d}/{total}] WARN {src.name}: {message}")
        else:
            ok_count += 1
            print(f"  [{i:03d}/{total}] OK   {src.name} {message}")

        with open(dst, "w", encoding="utf-8") as f:
            f.write(cleaned)

        if stem in paths_records:
            paths_records[stem]["clean_path"]    = rel_dst
            paths_records[stem]["clean_applied"] = "True"
            paths_records[stem]["noise_type"]    = ""

    try:
        save_paths_csv(PATHS_CSV, paths_records)
        print(f"\ncorpus_paths.csv 更新完了")
    except Exception as e:
        print(f"\nWARN: corpus_paths.csv 更新失敗: {e}")

    print(f"\n{'='*60}")
    print(f"=== 完了サマリー ===")
    print(f"  OK:    {ok_count}件")
    print(f"  WARN:  {warn_count}件")
    print(f"  SKIP:  {skip_count}件")
    print(f"  ERROR: {len(errors)}件")

    if skipped:
        print(f"\n--- SKIP一覧（空ファイル）---")
        for name in skipped:
            print(f"  {name}")

    if warnings:
        print(f"\n--- WARN一覧 ---")
        for name, msg in warnings:
            print(f"  {name}: {msg}")

    print(f"\n出力先: {CLEAN_DIR}")
    print(f"{'='*60}")
    return True

if __name__ == "__main__":
    import sys
    success = run()
    if not success:
        sys.exit(1)
