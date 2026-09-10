# translate_corpus.py
# R8 英語コーパス翻訳スクリプト v2
# 設計書: docs/design/preprocess_pipeline_design.md
#
# 処理フロー:
#   corpus_clean/{target}.txt
#     → preprocess.py（TextPacket生成・前処理・構造分類）
#     → Claude API（段落単位の日本語翻訳）
#     → corpus/annotator/{target}_ja.txt（原文併記・原文保全セクション付き）
#
# Usage:
#   .\.venv\Scripts\python.exe translate_corpus.py --dry-run
#   .\.venv\Scripts\python.exe translate_corpus.py
#   .\.venv\Scripts\python.exe translate_corpus.py --targets AD_037 AD_043

import time
import argparse
from pathlib import Path
from datetime import datetime

import preprocess as pp
from quality_check import should_translate

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "corpus" / "annotator"

DEFAULT_TARGETS = [
    "AD_037", "AD_043", "AD_044", "AD_047", "AD_048",
    "AD_049", "AD_050", "AD_051", "AD_052", "AD_071",
]

# 重複収集ファイルの注記（日英併記）
DUPLICATE_NOTES = {
    "AD_071": (
        "# Note: AD_071はAD_037と同一サイトの別収集版です。\n"
        "# 内容はほぼ同一ですが、κ計算サブグループとして独立ファイルとして管理します。\n"
        "# Note: AD_071 is a re-collected version of AD_037 (same site, near-identical content).\n"
        "# Maintained as a separate file for the κ calculation subgroup."
    )
}

# 翻訳スキップ時の注記（日英併記）
SKIP_NOTE = "（翻訳省略：短いナビゲーション要素 / Short navigation element — translation skipped）"

# ---------------------------------------------------------------------------
# 翻訳（Claude API）
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """あなたは日英翻訳の専門家です。
以下のルールに従って英語テキストを日本語に翻訳してください：

1. 原文のトーンと文体を忠実に再現すること（広告的な文体はそのまま広告的に）
2. 免責事項・リスク警告・法的文言は原文の構造を崩さず正確に翻訳すること
3. 固有名詞（会社名・プラットフォーム名・規制機関名）は原文のまま保持すること
   例：「（会社名）」「（取引プラットフォーム名）」「FCA」「FSC」はそのまま
4. 数値・パーセンテージ・通貨・ライセンス番号は変更しないこと
5. 翻訳のみを出力し、説明・コメントは一切追加しないこと
6. 入力が複数行の場合、行構造を維持すること"""


def translate_block(client, text: str) -> str:
    """1ブロックをClaude APIで日本語翻訳する。"""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}]
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# 段落分割
# ---------------------------------------------------------------------------

def split_to_paragraphs(working_text: str) -> list:
    """
    working_text（空行区切り）を段落リストに変換する。
    空のブロックは除外する。
    """
    paragraphs = []
    current = []
    for line in working_text.splitlines():
        if line.strip():
            current.append(line)
        else:
            if current:
                paragraphs.append("\n".join(current))
                current = []
    if current:
        paragraphs.append("\n".join(current))
    return [p for p in paragraphs if p.strip()]


# ---------------------------------------------------------------------------
# 出力ファイル生成
# ---------------------------------------------------------------------------

def build_output(packet: dict, translations: list, paragraphs: list) -> str:
    """
    翻訳結果からアノテーター向け出力ファイルの内容を構築する。

    構造:
      ヘッダー
      ─────────────────────────
      本文（原文段落 + 日本語訳、交互）
      ─────────────────────────
      原文保全セクション（raw text全文）
    """
    target = packet["target"]
    source_url = packet["source_url"] or "（ソース不明 / Source unknown）"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []

    # ── ヘッダー ──
    lines.append(f"# {target} — 翻訳テキスト（原文併記）")
    lines.append(f"# 原文ソース / Source: {source_url}")
    lines.append(f"# 原文ファイル / Original: corpus/corpus_archive/{target}_*.txt")
    lines.append(f"# クリーン版 / Clean: corpus/corpus_clean/{target}.txt")
    lines.append(f"# 翻訳モデル / Model: claude-sonnet-4-6")
    lines.append(f"# 生成日時 / Generated: {now}")
    lines.append(f"# パイプライン / Pipeline: preprocess.py v1 → translate_corpus.py v2")

    if target in DUPLICATE_NOTES:
        lines.append("")
        lines.append(DUPLICATE_NOTES[target])

    lines.append("")
    lines.append("=" * 60)
    lines.append("【本文】アノテーター判定用テキスト")
    lines.append("=" * 60)
    lines.append("")
    lines.append("※ 以下のテキストはWebページから取得したものです。")
    lines.append("※ UIナビゲーション要素・重複行は前処理で除去済みです。")
    lines.append("※ 判定に迷う箇所は末尾の「原文保全セクション」を参照してください。")
    lines.append("")

    # ── 本文（原文 + 翻訳、段落単位） ──
    for i, (para, trans) in enumerate(zip(paragraphs, translations), 1):
        lines.append(f"【原文 / Original {i}】")
        lines.append(para)
        lines.append("")
        lines.append(f"【翻訳 / Translation {i}】")
        lines.append(trans)
        lines.append("")
        lines.append("─" * 40)
        lines.append("")

    # ── 原文保全セクション ──
    lines.append("=" * 60)
    lines.append("【原文保全】処理前テキスト（参照用）")
    lines.append("=" * 60)
    lines.append("# 以下は前処理適用前のテキストです（corpus_clean版）。")
    lines.append("# アノテーション判定には使用しません。")
    lines.append("# 原文との整合性確認・構造確認が必要な場合に参照してください。")
    lines.append("")
    lines.append(packet["clean_text"])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------

def process_target(client, target: str, dry_run: bool = False) -> dict:
    """
    1ターゲットを処理する：
    1. TextPacket生成
    2. 前処理パイプライン実行
    3. 段落分割
    4. 翻訳（dry_runの場合はスキップ）
    5. 出力ファイル生成
    """
    print(f"\n{'=' * 60}")
    print(f"Target: {target}")

    # 1. TextPacket生成
    packet = pp.make_packet(target)
    packet["metadata"]["is_english"] = True

    if not packet["clean_text"]:
        return {"target": target, "status": "ERROR",
                "reason": f"corpus_clean/{target}.txt が見つかりません"}

    # 2. 前処理パイプライン実行
    packet = pp.run_pipeline(packet)

    # 3. 段落分割
    paragraphs = split_to_paragraphs(packet["working_text"])

    print(f"Source   : {packet['source_url'] or '不明'}")
    print(f"段落数   : {len(paragraphs)}")

    # 構造分類サマリ表示
    label_counts: dict = {}
    for entry in packet["structural_log"]:
        if entry["action"] == "classified":
            label_counts[entry["label"]] = label_counts.get(entry["label"], 0) + 1
    if label_counts:
        summary = " / ".join(f"{k}:{v}" for k, v in sorted(label_counts.items()))
        print(f"構造分類 : {summary}")

    if dry_run:
        skip_count = sum(1 for p in paragraphs if not should_translate(p))
        translate_count = len(paragraphs) - skip_count
        print(f"[DRY RUN] 翻訳予定: {translate_count}件 / スキップ予定: {skip_count}件")
        print("  先頭段落プレビュー:")
        if paragraphs:
            print("  " + paragraphs[0][:200].replace("\n", "\n  "))
        return {"target": target, "status": "DRY_RUN",
                "paragraphs": len(paragraphs), "skip": skip_count}

    # 4. 翻訳
    translations = []
    skipped = 0
    for i, para in enumerate(paragraphs, 1):
        if not should_translate(para):
            print(f"  スキップ {i}/{len(paragraphs)} ({sum(len(l) for l in para.splitlines() if l.strip())}文字)")
            translations.append(SKIP_NOTE)
            skipped += 1
            continue
        print(f"  翻訳中 {i}/{len(paragraphs)}...", end=" ", flush=True)
        try:
            trans = translate_block(client, para)
            translations.append(trans)
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
            translations.append(f"（翻訳エラー / Translation error: {e}）")
        time.sleep(0.3)
    if skipped:
        print(f"  翻訳スキップ: {skipped}件（短いナビゲーション要素）")

    # 5. 出力ファイル生成
    output_text = build_output(packet, translations, paragraphs)
    output_path = OUTPUT_DIR / f"{target}_ja.txt"
    output_path.write_text(output_text, encoding="utf-8")
    print(f"  → 出力: {output_path}")

    # 前処理ログ書き込み
    pp.write_log(packet)

    return {"target": target, "status": "OK",
            "paragraphs": len(paragraphs), "output": str(output_path)}


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="R8 英語コーパス翻訳スクリプト v2"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="翻訳・ファイル出力なし（前処理確認のみ）")
    parser.add_argument("--targets", nargs="+", default=DEFAULT_TARGETS,
                        help="処理対象ターゲットID（デフォルト：全10件）")
    args = parser.parse_args()

    # anthropicはdry-run以外でのみimport
    client = None
    if not args.dry_run:
        import anthropic
        client = anthropic.Anthropic()

    print("translate_corpus.py v2")
    print(f"Mode   : {'DRY RUN' if args.dry_run else 'TRANSLATE'}")
    print(f"Targets: {args.targets}")
    print(f"Output : {OUTPUT_DIR}")

    results = []
    for target in args.targets:
        result = process_target(client, target, dry_run=args.dry_run)
        results.append(result)

    # サマリ
    print(f"\n{'=' * 60}")
    print("Summary:")
    ok     = [r for r in results if r["status"] in ("OK", "DRY_RUN")]
    errors = [r for r in results if r["status"] == "ERROR"]
    print(f"  Success: {len(ok)}")
    print(f"  Errors : {len(errors)}")
    for r in errors:
        print(f"    ERROR - {r['target']}: {r.get('reason', '')}")

    if not args.dry_run and ok:
        print(f"\n出力先: {OUTPUT_DIR}")
        print("次のステップ: mask_corpus.py を実行してください")


if __name__ == "__main__":
    main()
