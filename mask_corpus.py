# mask_corpus.py
# R8 アノテーターコーパス 固有名マスクスクリプト v7
# 設計書: docs/design/preprocess_pipeline_design.md
#
# 方針:
#   - GiNZAは【翻訳 / Translation N】ブロックのみに適用（案A）
#   - 原文ブロックへの正規表現適用は廃止（誤検出が多すぎるため）
#   - ブランド除外：ヘッダーSourceURLからドメイン名を自動生成
#   - ソース不明ファイルのブランド指定は duplicate_brand_map.local.json（リポジトリ外）で行う
#   - ホワイトリスト：都度確認・追加・削除で取捨選択していく運用
#   - 組織名はマスクしない（名称の雰囲気情報を保持）
#   - 原文保全セクションはマスクしない（参照用として原文保持）
#
# ホワイトリスト運用方針:
#   - 一般性が高く今後も出現が見込まれるものを追加する
#   - イタチごっこになる個別的すぎる語句は追加しない
#   - dry-run結果を見て都度取捨選択する
#
# 既知の限界:
#   - ハンドルネームはGiNZAで検出困難
#     → 将来のnote・SNS系コーパス拡張時に改めて対処する
#   - 英語翻訳文に残った人名をGiNZAが取りこぼす場合あり
#     → 小規模コーパスでは手動確認で補完する
#
# 将来の英語圏拡張時の注意:
#   - GiNZAをen_core_web系モデルに切り替える際、ドメイン除外ロジックも再設計すること
#
# Usage:
#   .\.venv\Scripts\python.exe mask_corpus.py --dry-run
#   .\.venv\Scripts\python.exe mask_corpus.py --dry-run --targets AD_037
#   .\.venv\Scripts\python.exe mask_corpus.py
#   .\.venv\Scripts\python.exe mask_corpus.py --targets AD_037 AD_043

import json
import re
import argparse
from pathlib import Path
from urllib.parse import urlparse

import spacy

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

BASE_DIR    = Path(__file__).parent
CORPUS_DIR  = BASE_DIR / "corpus" / "annotator"
BACKUP_DIR  = BASE_DIR / "corpus" / "annotator" / "_backup_before_mask"

DEFAULT_TARGETS = [
    "AD_037", "AD_043", "AD_044", "AD_047", "AD_048",
    "AD_049", "AD_050", "AD_051", "AD_052", "AD_071",
]

# ソース不明ファイルのブランドトークンはリポジトリ外の設定ファイルで指定する
DUPLICATE_BRAND_MAP_PATH = BASE_DIR / "duplicate_brand_map.local.json"


def _load_duplicate_brand_map():
    """リポジトリ外の設定ファイルからブランド指定を読む。

    形式: {"AD_071": ["token"], ...}
    ファイル不在時は空辞書を返す。公開版に実在の企業名を含めないための
    分離であり、機構そのものは変わらない。
    """
    if not DUPLICATE_BRAND_MAP_PATH.exists():
        return {}
    with DUPLICATE_BRAND_MAP_PATH.open(encoding="utf-8") as f:
        return json.load(f)


DUPLICATE_BRAND_MAP = _load_duplicate_brand_map()

# ---------------------------------------------------------------------------
# ホワイトリスト（マスク除外）
# 運用: dry-run結果を見て都度追加・削除する。
#       一般性が高く今後も出現が見込まれるもののみ追加。
#       イタチごっこになる個別的すぎる語句は追加しない。
# ---------------------------------------------------------------------------

WHITELIST_PATTERNS = [
    # 大学
    r"大学", r"[Uu]niversity", r"[Cc]ollege", r"[Ii]nstitut",

    # 国際機関
    r"国連", r"WHO", r"IMF", r"UNESCO", r"UNICEF",
    r"[Ww]orld [Bb]ank", r"[Ww]orld [Hh]ealth",

    # 金融規制当局・国家機関・仲裁機関
    r"金融庁", r"消費者庁", r"警察庁", r"内閣府",
    r"FSC", r"FCA", r"SEC", r"CFTC", r"ASIC", r"MAS", r"MISA",
    r"[Ff]inancial [Cc]onduct",
    r"[Ff]inancial [Oo]mbudsman",
    r"[Ss]ecurities [Cc]ommission",
    r"[Ss]ecurities [Aa]uthority",

    # 報道機関
    r"NHK", r"[Bb][Bb][Cc]", r"[Rr]euters",
    r"[Nn]ikkei", r"日経", r"朝日", r"毎日", r"読売",

    # 金融メディア・業界誌
    r"[Ww]orld [Ff]inance",
    r"[Ff]inance [Mm]agnates",

    # 金融商品・通貨ペア・商品名（v7追加: USOILを個別追加）
    r"\b[A-Z]{3,6}USD\b",
    r"\b[A-Z]{3,6}JPY\b",
    r"\b[A-Z]{3,6}EUR\b",
    r"\bUSOIL\b",                   # v7追加: [A-Z]{3,6}USDにマッチしないため個別指定
    r"\bXAUUSD\b",                  # 念のため個別指定
    r"\bS&P\b", r"\bSPDR\b",

    # 賞・格付け機関の一般名称
    r"[Gg]lobal [Bb]rands",
    r"[Gg]lobal [Bb]anking",
]

WHITELIST_RE = re.compile("|".join(WHITELIST_PATTERNS))

# 引用元直前パターン
CITATION_RE = re.compile(
    r"(によれば|によると|の研究では|の調査では|の報告では"
    r"|according to|based on|reported by|cited by)",
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# ヘッダーからSourceURLを抽出してブランド除外語を生成
# ---------------------------------------------------------------------------

SOURCE_RE = re.compile(r"# 原文ソース / Source: (https?://\S+)")

def extract_brand_exclusions(content: str, target: str) -> list[str]:
    if target in DUPLICATE_BRAND_MAP:
        return DUPLICATE_BRAND_MAP[target]
    m = SOURCE_RE.search(content[:500])
    if not m:
        return []
    url = m.group(1).rstrip("/")
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        return []
    parts = hostname.replace("www.", "").split(".")
    domain_core = parts[0] if parts else ""
    tokens = [t for t in domain_core.split("-") if len(t) >= 3]
    return tokens

def is_brand(text: str, brand_tokens: list[str]) -> bool:
    return any(token in text.lower() for token in brand_tokens)

# ---------------------------------------------------------------------------
# ブロック抽出
# ---------------------------------------------------------------------------

TRANSLATION_BLOCK_RE = re.compile(
    r"【翻訳 / Translation \d+】\n(.*?)(?=\n────|$)",
    re.DOTALL
)

PRESERVE_MARKER = "【原文保全】処理前テキスト（参照用）"

# ---------------------------------------------------------------------------
# GiNZA ロード
# ---------------------------------------------------------------------------

def load_nlp():
    return spacy.load("ja_ginza", exclude=["compound_splitter"])

# ---------------------------------------------------------------------------
# 人名検出（翻訳ブロックのみ・GiNZA）
# ---------------------------------------------------------------------------

def is_whitelisted(text: str) -> bool:
    return bool(WHITELIST_RE.search(text))

def is_citation_context(sentence_text: str, ent_start: int) -> bool:
    prefix = sentence_text[max(0, ent_start - 40):ent_start]
    return bool(CITATION_RE.search(prefix))

def detect_persons(nlp, main_part: str, brand_tokens: list[str]) -> list[str]:
    seen = []
    for m in TRANSLATION_BLOCK_RE.finditer(main_part):
        text = m.group(1).strip()
        if "翻訳省略" in text:
            continue
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ != "Person":
                continue
            name = ent.text.strip()
            if is_whitelisted(name):
                continue
            if is_brand(name, brand_tokens):
                continue
            if is_citation_context(ent.sent.text, ent.start_char - ent.sent.start_char):
                continue
            if name not in seen:
                seen.append(name)
    return seen

# ---------------------------------------------------------------------------
# マスクラベル割り当て
# ---------------------------------------------------------------------------

def assign_labels(persons: list[str]) -> dict[str, str]:
    labels = {}
    for i, name in enumerate(persons):
        if i == 0:
            labels[name] = "[著者A]"
        else:
            letter = chr(ord("A") + i - 1)
            labels[name] = f"[人物{letter}]"
    return labels

# ---------------------------------------------------------------------------
# 置換実行
# ---------------------------------------------------------------------------

def apply_masks(text: str, labels: dict[str, str]) -> str:
    for name in sorted(labels.keys(), key=len, reverse=True):
        text = text.replace(name, labels[name])
    return text

# ---------------------------------------------------------------------------
# ファイル処理
# ---------------------------------------------------------------------------

def mask_file(nlp, input_path: Path, dry_run: bool) -> dict:
    content = input_path.read_text(encoding="utf-8")
    target = input_path.stem.replace("_ja", "")

    brand_tokens = extract_brand_exclusions(content, target)

    if PRESERVE_MARKER in content:
        main_part, preserve_part = content.split(PRESERVE_MARKER, 1)
        preserve_section = PRESERVE_MARKER + preserve_part
    else:
        main_part = content
        preserve_section = ""

    persons = detect_persons(nlp, main_part, brand_tokens)
    labels = assign_labels(persons)

    summary = {
        "target": target,
        "brand_tokens": brand_tokens,
        "masks_applied": len(labels),
        "labels": labels,
    }

    prefix = "[DRY-RUN]" if dry_run else "[DONE]"

    if not labels:
        print(f"  {prefix} {target}: マスク対象なし  (ブランド除外: {brand_tokens})")
        return summary

    if dry_run:
        print(f"  {prefix} {target}: {len(labels)}件マスク予定  (ブランド除外: {brand_tokens})")
        for name, label in labels.items():
            print(f"    {name!r} → {label}")
        return summary

    # 本番: メイン部分全体に置換適用
    masked_main = apply_masks(main_part, labels)
    masked_content = masked_main + preserve_section

    # バックアップ（初回のみ）
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / input_path.name
    if not backup_path.exists():
        backup_path.write_text(content, encoding="utf-8")

    input_path.write_text(masked_content, encoding="utf-8")

    print(f"  {prefix} {target}: {len(labels)}件マスク  (ブランド除外: {brand_tokens})")
    for name, label in labels.items():
        print(f"    {name!r} → {label}")

    return summary

# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="R8 アノテーターコーパス 個人名マスク v7")
    parser.add_argument("--dry-run", action="store_true",
                        help="実際には書き込まず、マスク予定を表示")
    parser.add_argument("--targets", nargs="+", default=None,
                        help="処理対象ID（例: AD_037 AD_043）。省略時は全10件。")
    args = parser.parse_args()

    targets = args.targets if args.targets else DEFAULT_TARGETS

    print(f"{'[DRY-RUN] ' if args.dry_run else ''}mask_corpus.py v7 開始")
    print(f"対象: {targets}\n")

    print("GiNZAロード中...")
    nlp = load_nlp()
    print("GiNZAロード完了\n")

    total_masks = 0
    for target in targets:
        input_path = CORPUS_DIR / f"{target}_ja.txt"
        if not input_path.exists():
            print(f"  [SKIP] {target}: ファイルが見つかりません")
            continue
        summary = mask_file(nlp, input_path, dry_run=args.dry_run)
        total_masks += summary["masks_applied"]

    print(f"\n完了。合計マスク: {total_masks}件")
    if args.dry_run:
        print("※ dry-runのため実際の書き込みは行っていません。")

if __name__ == "__main__":
    main()
