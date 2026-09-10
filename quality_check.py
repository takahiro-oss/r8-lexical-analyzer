# quality_check.py
# R8 品質チェック体制
# 設計書: docs/design/preprocess_pipeline_design.md § 10
#
# このファイルはパイプライン実装の品質を保証するためのチェック体制を実装する。
# 対話で合意した設計思想をコードとして保存し、セッション間で再現可能にする。
#
# Usage:
#   # P0: タスク確認（セッション冒頭にClaudeが参照）
#   .\.venv\Scripts\python.exe quality_check.py --mode suggest --task "should_translateの閾値変更"
#
#   # P1: 閾値検証ループ
#   .\.venv\Scripts\python.exe quality_check.py --mode threshold
#
#   # P2: 回帰テスト
#   .\.venv\Scripts\python.exe quality_check.py --mode regression
#
#   # P3: LLM品質評価（要APIキー・手動承認後）
#   .\.venv\Scripts\python.exe quality_check.py --mode llm --targets AD_037 AD_052

import re
import json
import argparse
from pathlib import Path
from datetime import datetime

import preprocess as pp

BASE_DIR   = Path(__file__).parent
CORPUS_DIR = BASE_DIR / "corpus" / "corpus_clean"
RESULTS_DIR = BASE_DIR / "data" / "results"

# ---------------------------------------------------------------------------
# P0: Claude事前提案（セッション冒頭）
#
# TAKAHIROが今日のタスクを告げた時点でClaudeが参照し、
# 実行すべきチェックを提案する。
# ---------------------------------------------------------------------------

# 変更種別とキーワードのマッピング
CHECK_TRIGGERS = {
    "threshold_change": {
        "keywords": ["should_translate", "閾値", "threshold", "スキップ"],
        "required": ["P1: 閾値検証ループ（--mode threshold）"],
        "recommended": ["P3: LLM品質評価（--mode llm）"],
        "reason": "閾値変更は誤スキップ・誤通過に直接影響する",
    },
    "pipeline_change": {
        "keywords": ["PIPELINE_V1", "remove_", "join_", "P1:", "P2:", "P3:", "P4:", "P5:"],
        "required": ["P2: 回帰テスト（--mode regression）"],
        "recommended": ["P1: 閾値検証ループ（--mode threshold）"],
        "reason": "パイプライン変更は全件の処理結果に波及する",
    },
    "new_corpus": {
        "keywords": ["make_packet", "DUPLICATE_MAP", "DEFAULT_TARGETS", "新コーパス"],
        "required": ["P1: 閾値検証ループ（--mode threshold）", "P2: 回帰テスト（--mode regression）"],
        "recommended": [],
        "reason": "新コーパスは既存の閾値・テストケースに収まらない可能性がある",
    },
    "translation_change": {
        "keywords": ["translate_block", "SYSTEM_PROMPT", "翻訳ロジック"],
        "required": [],
        "recommended": ["P3: LLM品質評価（--mode llm）"],
        "reason": "翻訳品質の変化はアノテーターの判定精度に影響する",
    },
}


def suggest_checks(task_description: str) -> None:
    """
    P0: タスク内容からチェック項目を提案する。
    セッション冒頭またはタスク開始時にClaudeが呼び出す。
    """
    print("=" * 60)
    print("【P0: 品質チェック提案】")
    print(f"タスク: {task_description}")
    print("=" * 60)

    triggered = []
    for trigger_name, trigger_info in CHECK_TRIGGERS.items():
        if any(kw in task_description for kw in trigger_info["keywords"]):
            triggered.append((trigger_name, trigger_info))

    if not triggered:
        print("このタスクに対する必須チェックはありません。")
        print("変更後にP2（回帰テスト）を実行することを推奨します。")
        return

    for trigger_name, info in triggered:
        print(f"\n> 検出: {trigger_name}")
        print(f"  理由: {info['reason']}")
        if info["required"]:
            print(f"  【必須】")
            for check in info["required"]:
                print(f"    → {check}")
        if info["recommended"]:
            print(f"  【推奨】")
            for check in info["recommended"]:
                print(f"    → {check}")

    print()
    print("実装前にチェックを実行してください。")
    print("P3（LLM評価）はTAKAHIROの手動承認後に実行してください。")


# ---------------------------------------------------------------------------
# P1: 閾値検証ループ
#
# should_translate()の閾値を複数コーパスで検証する。
# 誤スキップ（翻訳すべき段落をスキップ）と
# 誤通過（スキップすべき段落を翻訳）を計測する。
# ---------------------------------------------------------------------------

# 正解ラベル付きテストケース
# action: "translate" = 翻訳すべき / "skip" = スキップすべき
THRESHOLD_TEST_CASES = [
    # 翻訳すべき段落（誤スキップしてはいけない）
    {
        "id": "TC-T01",
        "text": "Instant withdrawals\nFunds sent within seconds with seamless transactions.",
        "expected": "translate",
        "note": "AD_037の重要な広告コピー。2行・60文字超。スキップ禁止。",
    },
    {
        "id": "TC-T02",
        "text": "Trade with the world's largest retail broker and benefit from better-than-market conditions.",
        "expected": "translate",
        "note": "1行・90文字。重要な広告コピー。スキップ禁止。",
    },
    {
        "id": "TC-T03",
        "text": "Trading Contracts for Difference (CFDs) involves a high level of risk and may not be suitable for all traders.",
        "expected": "translate",
        "note": "免責事項の核心文。スキップ禁止。",
    },
    {
        "id": "TC-T04",
        "text": "Trusted since 2008\nMultiple regulatory licenses\n24/7 customer support\nPCI DSS certified",
        "expected": "translate",
        "note": "4行・信頼性訴求。スキップ禁止。",
    },
    {
        "id": "TC-T05",
        "text": "A world-class trading experience, backed by trust and excellence.",
        "expected": "translate",
        "note": "1行・65文字。広告コピーの核心。スキップ禁止。",
    },
    # スキップすべき段落（誤通過させてはいけない）
    {
        "id": "TC-S01",
        "text": "Markets",
        "expected": "skip",
        "note": "1行・1語。ナビメニュー項目。翻訳不要。",
    },
    {
        "id": "TC-S02",
        "text": "Your AI investing companion",
        "expected": "skip",
        "note": "1行・27文字。孤立したナビラベル。翻訳不要。",
    },
    {
        "id": "TC-S03",
        "text": "Learn",
        "expected": "skip",
        "note": "1行・1語。ナビ項目。翻訳不要。",
    },
    {
        "id": "TC-S04",
        "text": "Get your detailed annual report",
        "expected": "skip",
        "note": "1行・29文字。孤立したナビラベル。翻訳不要。",
    },
    {
        "id": "TC-S05",
        "text": "Search",
        "expected": "skip",
        "note": "1行・1語。ナビ項目。翻訳不要。",
    },
]


def should_translate(paragraph: str,
                     max_lines: int = 1,
                     min_chars: int = 40) -> bool:
    """
    翻訳する価値があるかどうかを判定する。

    Args:
        paragraph: 判定対象の段落テキスト
        max_lines: この行数以下の場合はスキップ候補
        min_chars: この文字数未満の場合はスキップ候補

    Returns:
        True: 翻訳する / False: スキップする

    閾値の根拠（2026-05-20確定・P1検証済み）:
        max_lines=1, min_chars=40 が正解率100%・誤スキップ0・誤通過0。
        min_chars=30 は TC-S04（29文字のナビラベル）を誤通過する。
        quality_check.py --mode threshold で全10テストケースに対して検証済み。
    """
    lines = [l for l in paragraph.splitlines() if l.strip()]
    total_chars = sum(len(l) for l in lines)

    if len(lines) <= max_lines and total_chars < min_chars:
        return False
    return True


def run_threshold_check(max_lines_range=None, min_chars_range=None) -> None:
    """
    P1: 閾値検証ループ。
    閾値の組み合わせを試して誤スキップ・誤通過を計測する。
    """
    if max_lines_range is None:
        max_lines_range = [1, 2]
    if min_chars_range is None:
        min_chars_range = [20, 30, 40, 50]

    print("=" * 60)
    print("【P1: 閾値検証ループ】")
    print(f"テストケース数: {len(THRESHOLD_TEST_CASES)}")
    print("=" * 60)

    best_config = None
    best_score = -1

    for max_lines in max_lines_range:
        for min_chars in min_chars_range:
            false_skips = []   # 翻訳すべきなのにスキップ（致命的）
            false_passes = []  # スキップすべきなのに通過（許容）
            correct = []

            for tc in THRESHOLD_TEST_CASES:
                result = should_translate(tc["text"], max_lines, min_chars)
                predicted = "translate" if result else "skip"
                if predicted == tc["expected"]:
                    correct.append(tc)
                elif tc["expected"] == "translate" and not result:
                    false_skips.append(tc)
                else:
                    false_passes.append(tc)

            accuracy = len(correct) / len(THRESHOLD_TEST_CASES) * 100
            # 誤スキップは致命的なので重みを2倍にして評価
            score = accuracy - len(false_skips) * 20

            status = "[OK]" if len(false_skips) == 0 else "[FAIL]"
            print(f"\n{status} max_lines={max_lines}, min_chars={min_chars}")
            print(f"   正解率: {accuracy:.0f}% | 誤スキップ: {len(false_skips)} | 誤通過: {len(false_passes)}")

            if false_skips:
                for tc in false_skips:
                    print(f"   [誤スキップ] {tc['id']}: {tc['note']}")
            if false_passes:
                for tc in false_passes:
                    print(f"   [誤通過]   {tc['id']}: {tc['note']}")

            if score > best_score and len(false_skips) == 0:
                best_score = score
                best_config = (max_lines, min_chars)

    print()
    print("=" * 60)
    if best_config:
        print(f"【推奨閾値】 max_lines={best_config[0]}, min_chars={best_config[1]}")
        print("  誤スキップ0件・最高スコアの組み合わせ")
    else:
        print("【警告】誤スキップ0件の閾値が見つかりませんでした。")
        print("  テストケースを見直すか、閾値範囲を変更してください。")


# ---------------------------------------------------------------------------
# P2: 回帰テスト
#
# preprocess.pyのパイプラインが期待通りに動作するかを
# テストケース集で検証する。
# コード変更後に必ず実行する。
# ---------------------------------------------------------------------------

REGRESSION_TEST_CASES = [
    # 重複ブロック除去（P1）
    {
        "id": "RT-P1-01",
        "module": "remove_duplicate_blocks",
        "input_lines": ["Marketing", "Products", "Marketing", "Products"],
        "check": lambda result: "Marketing" in result and result.count("Marketing") == 1,
        "description": "重複行の2回目以降が除去される",
    },
    # UIノイズ除去（P2）
    {
        "id": "RT-P2-01",
        "module": "remove_ui_fragments",
        "input_lines": ["Facebook", "Twitter", "LinkedIn"],
        "check": lambda result: "Facebook" not in result and "Twitter" not in result,
        "description": "SNSアイコン名（3語以下短行）が除去される",
        # 設計注記: 'Invest now'は2語・10文字の短行のため_is_short_lineで除去される。
        # SNSパターンマッチの検証にはFacebook等を使用する。
    },
    {
        "id": "RT-P2-02",
        "module": "remove_ui_fragments",
        "input_lines": ["Trade & Invest", "Markets", "Stocks", "Crypto",
                        "ETFs", "Indices", "Commodities", "Currencies", "All Markets"],
        "check": lambda result: "Trade & Invest" not in result,
        "description": "TYPE-C連続短行ブロック（9行）が除去される",
    },
    {
        "id": "RT-P2-03",
        "module": "remove_ui_fragments",
        "input_lines": [
            "Invest in thousands of stocks, crypto, ETFs in one easy-to-use app.",
            "Facebook",
            "Twitter",
            "This is a longer sentence that should survive the filter.",
        ],
        "check": lambda result: (
            "Invest in thousands" in result and
            "This is a longer" in result and
            "Facebook" not in result
        ),
        "description": "長文コンテンツはノイズ除去後も保持される",
    },
    # 断片行結合（P3）
    {
        "id": "RT-P3-01",
        "module": "join_broken_lines",
        "input_lines": ["Trade with PU Prime, a world-leading", "online Forex and CFD broker"],
        "check": lambda result: "world-leading online Forex" in result,
        "description": "ハイフン複合語末尾の断片行が結合される",
    },
    {
        "id": "RT-P3-02",
        "module": "join_broken_lines",
        "input_lines": ["Benefits of", "our platform"],
        "check": lambda result: "Benefits of our platform" in result,
        "description": "前置詞末尾（of）の断片行が結合される",
        # 設計注記: 'way'は意図的に_INCOMPLETE_ENDINGSから除外済み。
        # 広告コピーの改行演出（Upgrade the way / you trade）と区別不能なため。
        # 前置詞末尾の検証には'of'等を使用する。
    },
    # 構造分類（P5）
    {
        "id": "RT-P5-01",
        "module": "classify_structural_blocks",
        "input_lines": [
            "Trade CFDs on Forex, Gold, Oil, Bonds, Stocks, and more anytime, anywhere.",
            "Stay in control of global markets with seamless access to global platforms.",
        ],
        # classify_structural_blocksはworking_textを変更せずstructural_logに記録する。
        # check関数はpacketのstructural_logを検査できないため、
        # working_textが変更されないことを検証する（正常動作の確認）。
        "check": lambda result: (
            "Trade CFDs on Forex" in result and
            "Stay in control" in result
        ),
        "description": "classify_structural_blocksはworking_textを変更しない（分類のみ）",
    },
    {
        "id": "RT-P5-02",
        "module": "classify_structural_blocks",
        "input_lines": [
            "Trade CFDs on Forex, Gold, Oil, Bonds, Stocks, and more anytime, anywhere.",
            "Stay in control of global markets with seamless access to global platforms.",
        ],
        # structural_logへの記録はpacketを直接操作する必要があるため
        # _run_module_on_linesの戻り値（working_text）では検証不可。
        # このテストはパイプライン全体での動作をpreprocess.pyのdry-runで確認する。
        # ここでは「working_textが空にならない」という最低限の健全性チェックのみ実施。
        "check": lambda result: len(result.strip()) > 0,
        "description": "classify_structural_blocks実行後working_textが空にならない",
    },
]


def _run_module_on_lines(module_name: str, input_lines: list) -> str:
    """指定モジュールを行リストに適用してworking_textを返す。"""
    packet = {
        "target": "TEST",
        "source_url": "",
        "raw_text": "",
        "clean_text": "\n".join(input_lines),
        "working_text": "\n".join(input_lines),
        "structural_log": [],
        "metadata": {
            "processed_at": datetime.now().isoformat(),
            "pipeline_version": "v1",
            "modules_applied": [],
            "is_english": True,
            "is_duplicate": False,
            "duplicate_of": "",
        }
    }

    module_fn = getattr(pp, module_name, None)
    if module_fn is None:
        return f"[ERROR] モジュール {module_name} が見つかりません"

    packet = module_fn(packet)
    return packet["working_text"]


def run_regression_tests() -> None:
    """P2: 回帰テストを実行する。"""
    print("=" * 60)
    print("【P2: 回帰テスト】")
    print(f"テストケース数: {len(REGRESSION_TEST_CASES)}")
    print("=" * 60)

    passed = []
    failed = []

    for tc in REGRESSION_TEST_CASES:
        result = _run_module_on_lines(tc["module"], tc["input_lines"])
        ok = tc["check"](result)

        status = "[PASS]" if ok else "[FAIL]"
        print(f"\n{status} [{tc['id']}] {tc['description']}")
        print(f"  モジュール: {tc['module']}")

        if not ok:
            failed.append(tc)
            print(f"  入力: {tc['input_lines']}")
            print(f"  出力: {result[:200]}")

        if ok:
            passed.append(tc)

    print()
    print("=" * 60)
    print(f"結果: {len(passed)}/{len(REGRESSION_TEST_CASES)} PASS")
    if failed:
        print(f"\n【失敗したテスト】")
        for tc in failed:
            print(f"  [FAIL] {tc['id']}: {tc['description']}")
        print("\nコードを修正して再度実行してください。")
    else:
        print("全テスト通過。パイプラインは正常に動作しています。")


# ---------------------------------------------------------------------------
# P3: LLM品質評価（重要実装前・手動承認）
#
# 第三者視点プロンプトで翻訳・スキップ判定の品質を評価する。
# 「アノテーターはこの空欄を見て困惑するか」という視点で設計。
# Claude自己評価バイアスを避けるため評価プロンプトを実装者と切り離す。
# ---------------------------------------------------------------------------

P3_EVALUATOR_PROMPT = """あなたはR8研究プロジェクトのアノテーター品質評価者です。
以下のテキストを見て、アノテーター（心理学・経済学の専門的背景を持つ評価者）が
このテキストを読んで認知操作リスクを判定できるかどうかを評価してください。

評価観点：
1. 翻訳省略箇所はアノテーターが原文で理解できるか
2. テキストの意味的な流れが保たれているか
3. 重要な広告コピーや法的文言が欠落していないか

テキスト：
{text}

以下のJSON形式のみで回答してください（説明不要）：
{{"quality": "good"|"acceptable"|"poor", "reason": "簡潔な理由（50文字以内）", "missing": "欠落している重要情報があれば記述、なければnull"}}"""


def run_llm_evaluation(targets: list) -> None:
    """
    P3: LLM品質評価。
    翻訳済みファイルを読み込み、第三者視点で品質を評価する。
    手動承認後にのみ実行する。
    """
    import anthropic

    print("=" * 60)
    print("【P3: LLM品質評価】")
    print(f"対象: {targets}")
    print("[WARN] APIを呼び出します。手動承認済みの場合のみ実行してください。")
    print("=" * 60)

    client = anthropic.Anthropic()
    annotator_dir = BASE_DIR / "corpus" / "annotator"

    for target in targets:
        ja_file = annotator_dir / f"{target}_ja.txt"
        if not ja_file.exists():
            print(f"\n[SKIP] {target}: {ja_file} が見つかりません")
            continue

        content = ja_file.read_text(encoding="utf-8")
        # 本文部分のみ抽出（原文保全セクション除外）
        body = content.split("【原文保全】")[0] if "【原文保全】" in content else content

        print(f"\n--- {target} ---")

        prompt = P3_EVALUATOR_PROMPT.format(text=body[:3000])
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            result = json.loads(response.content[0].text)
            quality = result.get("quality", "unknown")
            reason = result.get("reason", "")
            missing = result.get("missing")

            status = {"good": "[OK]", "acceptable": "[WARN]", "poor": "[NG]"}.get(quality, "[?]")
            print(f"  {status} 品質: {quality}")
            print(f"  理由: {reason}")
            if missing:
                print(f"  欠落: {missing}")
        except Exception as e:
            print(f"  [ERROR] レスポンス解析失敗: {e}")
            print(f"  raw: {response.content[0].text[:200]}")


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="R8 品質チェック体制")
    parser.add_argument("--mode", required=True,
                        choices=["suggest", "threshold", "regression", "llm"],
                        help="実行モード: suggest/threshold/regression/llm")
    parser.add_argument("--task", default="",
                        help="[suggest] 今日のタスク内容（文字列）")
    parser.add_argument("--targets", nargs="+",
                        help="[llm] 評価対象ターゲットID")
    args = parser.parse_args()

    if args.mode == "suggest":
        if not args.task:
            print("[ERROR] --task にタスク内容を指定してください")
            return
        suggest_checks(args.task)

    elif args.mode == "threshold":
        run_threshold_check()

    elif args.mode == "regression":
        run_regression_tests()

    elif args.mode == "llm":
        if not args.targets:
            print("[ERROR] --targets に対象ターゲットを指定してください")
            return
        confirm = input("P3はAPIを呼び出します。実行しますか？ (yes/no): ")
        if confirm.lower() != "yes":
            print("中止しました。")
            return
        run_llm_evaluation(args.targets)


if __name__ == "__main__":
    main()
