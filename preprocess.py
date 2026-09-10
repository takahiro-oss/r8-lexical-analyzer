# preprocess.py
# R8 前処理パイプライン v1
# 設計書: docs/design/preprocess_pipeline_design.md
#
# Usage（単体テスト）:
#   .\.venv\Scripts\python.exe preprocess.py --target AD_037 --dry-run
#   .\.venv\Scripts\python.exe preprocess.py --target AD_043 --dry-run --full
#   .\.venv\Scripts\python.exe preprocess.py --target AD_052 --dry-run

import re
import json
import argparse
import csv
from pathlib import Path
from datetime import datetime
from statistics import stdev, mean
from collections import Counter

# ---------------------------------------------------------------------------
# パス設定
# ---------------------------------------------------------------------------

BASE_DIR    = Path(__file__).parent
ARCHIVE_DIR = BASE_DIR / "corpus" / "corpus_archive"
CLEAN_DIR   = BASE_DIR / "corpus" / "corpus_clean"
LOG_CSV     = BASE_DIR / "data" / "results" / "preprocess_log.csv"

PIPELINE_VERSION = "v1"

DUPLICATE_MAP = {
    "AD_071": "AD_037",
}

# ---------------------------------------------------------------------------
# TextPacket 初期化
# ---------------------------------------------------------------------------

def make_packet(target: str) -> dict:
    archive_files = list(ARCHIVE_DIR.glob(f"{target}_*.txt"))
    if not archive_files:
        archive_files = [f for f in ARCHIVE_DIR.iterdir()
                         if f.stem.upper().startswith(target.upper() + "_")]
    raw_text = ""
    source_url = ""
    if archive_files:
        raw_text = archive_files[0].read_text(encoding="utf-8", errors="replace")
        for line in raw_text.splitlines():
            if line.startswith("[SOURCE]"):
                source_url = line.replace("[SOURCE]", "").strip()
                break

    clean_path = CLEAN_DIR / f"{target}.txt"
    clean_text = ""
    if clean_path.exists():
        clean_text = clean_path.read_text(encoding="utf-8", errors="replace")

    return {
        "target": target,
        "source_url": source_url,
        "raw_text": raw_text,
        "clean_text": clean_text,
        "working_text": clean_text,
        "structural_log": [],
        "metadata": {
            "processed_at": datetime.now().isoformat(),
            "pipeline_version": PIPELINE_VERSION,
            "modules_applied": [],
            "is_english": False,
            "is_duplicate": target in DUPLICATE_MAP,
            "duplicate_of": DUPLICATE_MAP.get(target, ""),
        }
    }


def _log(packet: dict, module: str, action: str, label: str,
         lines_before: list, lines_after: list, reason: str) -> None:
    packet["structural_log"].append({
        "module": module,
        "action": action,
        "label": label,
        "lines_before": lines_before,
        "lines_after": lines_after,
        "reason": reason,
    })
    if module not in packet["metadata"]["modules_applied"]:
        packet["metadata"]["modules_applied"].append(module)


# ---------------------------------------------------------------------------
# P1: 重複ブロック除去
# ---------------------------------------------------------------------------

def remove_duplicate_blocks(packet: dict) -> dict:
    lines = packet["working_text"].splitlines()
    freq = Counter(l.strip() for l in lines if l.strip())

    result = []
    seen_count: dict = {}
    removed = []

    for line in lines:
        key = line.strip()
        if not key:
            result.append(line)
            continue
        seen_count[key] = seen_count.get(key, 0) + 1
        if freq[key] >= 2 and seen_count[key] > 1:
            removed.append(line)
        else:
            result.append(line)

    if removed:
        _log(packet, "remove_duplicate_blocks", "removed", "DUPLICATE",
             removed, [], f"{len(removed)}行の重複行を除去")

    packet["working_text"] = "\n".join(result)
    return packet


# ---------------------------------------------------------------------------
# P2: UIノイズ除去 + ブロック単位ノイズ除去 + 段落境界の生成
#
# 行単位フィルタ：極短行・非ASCII行・UIパターン・スペイン語等
#
# ブロック単位フィルタ：
#   TYPE-C: 3語以下の行が6行以上連続 → ブロック全体を除去
#           多言語リスト・ナビメニュー細分化に対応
#   TYPE-D: アワード/受賞リスト
#           8行ウィンドウ内に年号行が4行以上含まれる密度パターン
#           → ウィンドウを含む連続ブロック全体を除去
#           ※ 「賞名行」と「受賞機関+年号行」が交互に出現する構造に対応
# ---------------------------------------------------------------------------

_UI_PATTERNS = [
    re.compile(r"^(Sign [Iu]n|Log [Iu]n|Sign Up|Register|Download App|Open [Aa]ccount)$"),
    re.compile(r"^(Read [Mm]ore|Learn [Mm]ore|View [Mm]ore|Get [Ss]tarted|Start [Nn]ow|Join [Nn]ow)$"),
    re.compile(r"^(Click here|Scan the code|Loading\.\.\.|Skip to content)$"),
    re.compile(r"^(Facebook|Twitter|X|LinkedIn|Instagram|YouTube|TikTok|Telegram)$"),
    re.compile(r"^(BUY|SELL|Bid|Ask|Spread|Symbol|Change)$"),
    re.compile(r"^\d+(\.\d+)?$"),
    re.compile(r"^[<>]\s*\d+\s*[<>]?$"),
    re.compile(r"^[-\u2013\u2014]+$"),
    re.compile(r"^\*+$"),
    re.compile(r"^(Install|Allow|Disallow|Acknowledge|Close)$"),
    re.compile(r"^(EN|en)$"),
    re.compile(r"^Thank [Yy]ou for [Yy]our .+!?$"),
    re.compile(r"^(Cookie Settings?|Accept Cookies?|Privacy Policy)$"),
]

_SPANISH_CHARS = set("áéíóúüñ¿¡àèìòùâêîôûäëïöüç")
_AWARD_YEAR_PAT = re.compile(r".+\b20\d{2}\b$")


def _is_ui_noise(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    words = stripped.split()
    if len(words) <= 2 and len(stripped) <= 20:
        return True
    ascii_ratio = sum(1 for c in stripped if ord(c) < 128) / max(len(stripped), 1)
    if ascii_ratio < 0.5 and len(stripped) > 5:
        return True
    if len(stripped) > 30 and any(c in _SPANISH_CHARS for c in stripped.lower()):
        return True
    for pat in _UI_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def _is_short_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and len(stripped.split()) <= 3


def _is_award_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and bool(_AWARD_YEAR_PAT.match(stripped))


def _is_award_block_start(lines: list, i: int,
                           window: int = 8, threshold: int = 4) -> bool:
    """
    TYPE-D: 密度判定によるアワードブロック開始検出。

    位置iからwindow行のウィンドウ内に年号行がthreshold行以上含まれる場合、
    アワードブロックの開始とみなす。
    賞名行（非年号）と年号行が交互に出現する構造に対応。
    """
    non_blank = [l for l in lines[i:i+window] if l.strip()]
    if len(non_blank) < threshold:
        return False
    award_count = sum(1 for l in non_blank if _is_award_line(l))
    return award_count >= threshold


def _apply_block_filters(lines: list) -> tuple:
    """
    ブロック単位フィルタを適用する。

    TYPE-C: 3語以下の行が6行以上連続 → ブロック全体を除去
    TYPE-D: 8行ウィンドウ内の年号行密度が4/8以上 → ブロック全体を除去

    Returns:
        (filtered_lines, removed_blocks)
    """
    result = []
    removed_blocks = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            result.append(line)
            i += 1
            continue

        # TYPE-C: 連続短行ブロック検出
        if _is_short_line(line):
            block = []
            j = i
            while j < len(lines) and lines[j].strip() and _is_short_line(lines[j]):
                block.append(lines[j])
                j += 1
            if len(block) >= 6:
                removed_blocks.append((block, f"TYPE-C: 連続短行{len(block)}行を除去"))
                result.append("")
                i = j
                continue

        # TYPE-D: アワードブロック密度検出
        if _is_award_block_start(lines, i):
            # ブロック全体を収集（短行または年号行が続く限り）
            block = []
            j = i
            while j < len(lines) and lines[j].strip():
                l = lines[j]
                # 短行（賞名・機関名）または年号行 → ブロックに含める
                if _is_short_line(l) or _is_award_line(l):
                    block.append(l)
                    j += 1
                else:
                    # 長文が来たらブロック終了
                    break
            if len(block) >= 6:
                removed_blocks.append((block, f"TYPE-D: アワードブロック{len(block)}行を除去"))
                result.append("")
                i = j
                continue

        result.append(line)
        i += 1

    return result, removed_blocks


def remove_ui_fragments(packet: dict) -> dict:
    """P2: UIノイズ除去（行単位 + ブロック単位）+ 段落境界生成。"""

    # Step 1: ブロック単位フィルタ
    lines = packet["working_text"].splitlines()
    lines, removed_blocks = _apply_block_filters(lines)

    for block_lines, reason in removed_blocks:
        _log(packet, "remove_ui_fragments", "removed", "BLOCK_NOISE",
             block_lines, [], reason)

    # Step 2: 行単位フィルタ + 段落境界生成
    result = []
    removed_lines = []
    in_noise_block = False

    for line in lines:
        if not line.strip():
            if not in_noise_block:
                result.append("")
            in_noise_block = False
            continue

        if _is_ui_noise(line):
            removed_lines.append(line)
            in_noise_block = True
        else:
            if in_noise_block:
                result.append("")
            in_noise_block = False
            result.append(line)

    if removed_lines:
        _log(packet, "remove_ui_fragments", "removed", "FRAGMENT",
             removed_lines, [], f"{len(removed_lines)}行のUIノイズ・非英語行を除去")

    # Step 3: 連続空行を1行に圧縮
    compressed = []
    prev_blank = False
    for line in result:
        if line.strip() == "":
            if not prev_blank:
                compressed.append("")
            prev_blank = True
        else:
            compressed.append(line)
            prev_blank = False

    packet["working_text"] = "\n".join(compressed).strip()
    return packet


# ---------------------------------------------------------------------------
# P3: 断片行結合
# ---------------------------------------------------------------------------

_INCOMPLETE_ENDINGS = {
    "the", "a", "an", "and", "or", "but", "for", "with",
    "from", "to", "of", "in", "on", "at", "by", "as",
    "that", "which", "who", "how",
    "leading", "based", "powered", "trusted",
    "class", "edge", "time",
}

_HYPHEN_INCOMPLETE = re.compile(
    r".+-(leading|based|powered|trusted|class|edge|time|winning|driven|focused)$",
    re.IGNORECASE
)


def _is_incomplete_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    words = stripped.split()
    if len(words) > 6:
        return False
    if stripped[-1] in ".!?:;,。！？":
        return False
    last_word = words[-1]
    if _HYPHEN_INCOMPLETE.match(last_word):
        return True
    last_word_clean = last_word.lower().rstrip(".,!?-")
    return last_word_clean in _INCOMPLETE_ENDINGS


def join_broken_lines(packet: dict) -> dict:
    lines = packet["working_text"].splitlines()
    result = []
    joined_log = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            result.append(line)
            i += 1
            continue

        if _is_incomplete_line(line) and i + 1 < len(lines):
            next_line = lines[i + 1]
            if next_line.strip():
                joined = line.rstrip() + " " + next_line.strip()
                joined_log.append({"lines_before": [line, next_line],
                                   "lines_after": [joined]})
                result.append(joined)
                i += 2
                continue

        result.append(line)
        i += 1

    if joined_log:
        all_before = [l for e in joined_log for l in e["lines_before"]]
        all_after  = [l for e in joined_log for l in e["lines_after"]]
        _log(packet, "join_broken_lines", "joined", "FRAGMENT",
             all_before, all_after, f"{len(joined_log)}箇所の断片行を結合")

    packet["working_text"] = "\n".join(result)
    return packet


# ---------------------------------------------------------------------------
# P4: テーブルデータ除去
# ---------------------------------------------------------------------------

_TICKER_PAT  = re.compile(r"^[A-Z]{2,6}(USD|JPY|EUR|GBP|AUD|CAD)?$")
_NUMERIC_PAT = re.compile(r"^\d[\d\.,\s%]+$")
_UNIT_PAT    = re.compile(r"^(pips?|lots?|USD|EUR|JPY|GBP|\$|€|¥)[\d\s]*$", re.I)


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _TICKER_PAT.match(stripped):
        return True
    if _NUMERIC_PAT.match(stripped):
        return True
    if _UNIT_PAT.match(stripped):
        return True
    return False


def remove_table_data(packet: dict) -> dict:
    lines = packet["working_text"].splitlines()
    result = []
    removed = []
    i = 0

    while i < len(lines):
        if _is_table_row(lines[i]):
            prev_table = i > 0 and _is_table_row(lines[i-1])
            next_table = i + 1 < len(lines) and _is_table_row(lines[i+1])
            if prev_table or next_table:
                removed.append(lines[i])
                i += 1
                continue
        result.append(lines[i])
        i += 1

    if removed:
        _log(packet, "remove_table_data", "removed", "TABLE",
             removed, [], f"{len(removed)}行のテーブルデータを除去")

    packet["working_text"] = "\n".join(result)
    return packet


# ---------------------------------------------------------------------------
# P5: 構造分類
# ---------------------------------------------------------------------------

def _classify_block(block_lines: list) -> tuple:
    stripped = [l.strip() for l in block_lines if l.strip()]
    if not stripped:
        return "FRAGMENT", "empty"

    n = len(stripped)

    table_count = sum(1 for l in stripped if _is_table_row(l))
    if n >= 3 and table_count / n >= 0.6:
        return "TABLE", f"table rows: {table_count}/{n}"

    fragment_count = sum(1 for l in stripped if len(l.split()) <= 2)
    if fragment_count / n >= 0.8:
        return "FRAGMENT", f"fragment lines: {fragment_count}/{n}"

    lengths     = [len(l) for l in stripped]
    word_counts = [len(l.split()) for l in stripped]
    avg_len     = mean(lengths)
    len_std     = stdev(lengths) if n >= 2 else 0
    avg_words   = mean(word_counts)

    short_count = sum(1 for wc in word_counts if wc <= 3)
    if n >= 4 and short_count / n >= 0.7:
        return "STACCATO", f"short lines: {short_count}/{n}, avg_words={avg_words:.1f}"

    if n >= 3 and len_std < 8 and avg_len < 40:
        alternating = (n >= 4 and all(
            word_counts[i] == word_counts[i % 2] for i in range(n)
        ))
        if alternating or (len_std < 5 and avg_words <= 4):
            return "RHYTHMIC", f"len_std={len_std:.1f}, avg_words={avg_words:.1f}"

    long_count = sum(1 for l in stripped if len(l) >= 40)
    if long_count / n >= 0.5:
        return "NARRATIVE", f"long lines: {long_count}/{n}, avg_len={avg_len:.0f}"

    return "NARRATIVE", f"default, avg_len={avg_len:.0f}, avg_words={avg_words:.1f}"


def classify_structural_blocks(packet: dict) -> dict:
    lines = packet["working_text"].splitlines()
    current_block = []
    classified = []

    for line in lines:
        if line.strip():
            current_block.append(line)
        else:
            if current_block:
                label, reason = _classify_block(current_block)
                classified.append((current_block[:], label, reason))
                current_block = []

    if current_block:
        label, reason = _classify_block(current_block)
        classified.append((current_block[:], label, reason))

    for block_lines, label, reason in classified:
        _log(packet, "classify_structural_blocks", "classified", label,
             block_lines, block_lines, reason)

    return packet


# ---------------------------------------------------------------------------
# パイプライン定義
# ---------------------------------------------------------------------------

PIPELINE_V1 = [
    remove_duplicate_blocks,
    remove_ui_fragments,
    join_broken_lines,
    remove_table_data,
    classify_structural_blocks,
]


def run_pipeline(packet: dict, pipeline: list = None) -> dict:
    if pipeline is None:
        pipeline = PIPELINE_V1
    for module in pipeline:
        packet = module(packet)
    return packet


# ---------------------------------------------------------------------------
# ログ出力
# ---------------------------------------------------------------------------

def write_log(packet: dict) -> None:
    LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    write_header = not LOG_CSV.exists()

    with open(LOG_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "target", "module", "action", "label",
                "lines_before", "lines_after", "reason", "processed_at"
            ])
        ts = packet["metadata"]["processed_at"]
        for entry in packet["structural_log"]:
            writer.writerow([
                packet["target"],
                entry["module"],
                entry["action"],
                entry["label"],
                json.dumps(entry["lines_before"], ensure_ascii=False),
                json.dumps(entry["lines_after"], ensure_ascii=False),
                entry["reason"],
                ts,
            ])


# ---------------------------------------------------------------------------
# 単体テスト用エントリポイント
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="R8 前処理パイプライン単体テスト")
    parser.add_argument("--target", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--full", action="store_true", help="処理済みテキスト全文表示")
    args = parser.parse_args()

    print(f"preprocess.py — target: {args.target}")
    packet = make_packet(args.target)

    if not packet["clean_text"]:
        print(f"[ERROR] corpus_clean/{args.target}.txt が見つかりません")
        return

    print(f"clean_text : {len(packet['clean_text'].splitlines())}行")
    packet = run_pipeline(packet)
    working_lines = [l for l in packet["working_text"].splitlines() if l.strip()]
    print(f"working_text: {len(working_lines)}行（空行除く）")
    print(f"structural_log: {len(packet['structural_log'])}エントリ")
    print()

    label_counts: dict = {}
    for entry in packet["structural_log"]:
        if entry["action"] == "classified":
            label_counts[entry["label"]] = label_counts.get(entry["label"], 0) + 1

    print("【構造分類サマリ】")
    for label, count in sorted(label_counts.items()):
        print(f"  {label}: {count}ブロック")

    print()
    if args.full:
        print("【処理済みテキスト（全文）】")
        print(packet["working_text"])
    else:
        print("【処理済みテキスト（先頭600文字）】")
        print(packet["working_text"][:600])
        print("...")
        print("（--full で全文表示）")

    if not args.dry_run:
        write_log(packet)
        print(f"\nログ書き込み完了: {LOG_CSV}")
    else:
        print("\n[DRY RUN] ログ書き込みなし")


if __name__ == "__main__":
    main()
