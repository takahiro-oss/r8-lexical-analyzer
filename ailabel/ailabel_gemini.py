#!/usr/bin/env python3
"""
ailabel_gemini.py — Gemini API を使ったAIlabelアノテーションツール (v0.7.1対応)

使い方:
  python ailabel/ailabel_gemini.py --corpus corpus --out ailabel/results_gemini.csv

必要:
  pip install google-generativeai

引数:
  --corpus   : コーパスルートディレクトリ（デフォルト: corpus）
  --master   : corpus_master.csvのパス（デフォルト: data/results/corpus_master.csv）
  --out      : 出力CSVパス（デフォルト: ailabel/results_gemini.csv）
  --model    : 使用モデル（デフォルト: gemini-2.0-flash）
  --api-key  : APIキー（省略時はGEMINI_API_KEY環境変数を使用）
  --only-blank : ailabelが空白の行のみ処理（再実行時に使用）
"""

import argparse
import csv
import json
import os
import re
import sys
import time

try:
    import google.generativeai as genai
except ImportError:
    print("ERROR: google-generativeai パッケージが必要です")
    print("  pip install google-generativeai")
    sys.exit(1)

PROMPT_TEMPLATE = """あなたは認知的操作リスクのアノテーターです。
以下のアノテーション基準（annotation_criteria v0.7.1）に従い、
テキストにHIGH・MEDIUM・LOW・Intent-Unresolvedのいずれかのラベルを付けてください。

【前提原則】
- テキスト内の言語構造のみに基づいて判定する
- 発信者の属性・利益構造等テキスト外情報は使用しない
- CMIスコアはHIGH判定の必要条件ではない（陰性偽装が存在するため）

【判定基準】

HIGH: H-1〜H-4のいずれか1つ以上を満たす
  H-1（表面安全語彙型・陰性偽装）:
    ①一人称体験談形式であること
    ②操作主体（商品・人物・手法・概念）が本文の主要論述部で前景化されていないこと
    ①②の2点が共存していれば該当。
    ※操作主体が「不可視」とみなす状態:
      - 本文末尾・注記・リンクにのみ登場し主要論述部では言及されない
      - 疑似科学的概念が操作手法として機能しているが名称化されていない
      - 読者の欲求を言語化して鏡として提示し充足手段が因果関係なしに接続

  H-2（感情根拠型規範誘導）:
    以下パターンA・B・Cが複合的に確認できる場合
    A: 内容の異なる複数エピソード・権威・事実が並列に並び同一規範に収束
    B: テキスト末尾または複数段落末に規範的結論文が存在
    C: 累積された根拠全体に対して読者が反論できる余地が設計上与えられていない
    ※かつ規範収束の方向が外部行動誘導または経済的・社会的変容を向いていること
    ※内省・信仰の内面化のみに向かう場合は非該当→M-1/M-4方向

  H-3（欲求喚起型）:
    金銭的・社会的欲求への明示的語彙が複数存在し、行動変容への誘導と結合

  H-4（恐怖・切迫感型）:
    ①恐怖・切迫感・損失回避語彙（「手遅れになる前に」「本日限り」等）
    ②即時かつ単一の外部行動選択肢の提示（「今すぐ登録」等）
    ①②の2条件が同時に存在すること
    ※報道・批評・公益的提言は適用除外

MEDIUM: H-1〜H-4を満たさず、M-1〜M-4のいずれかを満たす
  M-1: 間接的・漸進的行動誘導（将来的リスク提示・内省促進等）
  M-2: 検証不能な権威・統計の引用（著者・年・掲載誌等が欠落）
  M-3: 商業的誘導意図が確認できるが操作的語彙密度がHIGH未満
  M-4: 感情誘導語彙が同一段落内に3語以上集中（行動変容誘導なし）

LOW: HIGH・MEDIUMいずれにも該当しないと積極的に判断できる
  L-1: 操作的語彙の不在、または検証可能形式での引用
  L-2: 中立文脈における語彙使用（報道・学術等）
  L-3: 行動変容誘導の不在
  ※報道・公益的提言・行政文書・学術文書は原則LOW方向

Intent-Unresolved: 判定不能（保留）
  - 操作的意図の有無が原理的に判断不能
  - 固有名詞バイアスが排除できない
  - 複数ラベル間で判断が定まらない

【判定フロー（この順番で確認すること）】
Step1: H-1確認 → 一人称体験談＋操作主体不可視の共存があるか？（最初に確認・最も見落としやすい）
Step2: H-2確認 → パターンA・B・Cの複合＋外部行動誘導方向の規範収束があるか？
Step3: H-3/H-4確認
Step4: M-1〜M-4のいずれかを満たすか？
Step5: 積極的にLOWと判断できるか？

【複合判定ルール】
- 複数のH条件が成立する場合、labelはHIGH（1つ）で確定
- primary_conditionの優先順位: H-4 > H-3 > H-1 > H-2

【重要な注意事項】
- 肯定的・感謝・愛・光等の語彙が多くても操作的構造があればHIGH
- SNS等の短文テキストはCMIが低くても内容判断でHIGHになりうる
- 「判断できない」はLOWではない→Intent-Unresolvedを使用すること

【出力形式】
以下のJSON形式のみで回答してください。説明文・前置き・コードブロックは不要です。
{{
  "label": "HIGH/MEDIUM/LOW/Intent-Unresolved",
  "primary_condition": "H-1/H-2/H-3/H-4/M-1/M-2/M-3/M-4/L-1/L-2/L-3/IU",
  "confidence": "high/medium/low",
  "reason": "判定根拠を1〜2文で"
}}

【対象テキスト】
{text}
"""

VALID_LABELS = {"HIGH", "MEDIUM", "LOW", "Intent-Unresolved"}
DEFAULT_MODEL = "gemini-2.0-flash"


def load_master(master_path):
    targets = []
    with open(master_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            targets.append({
                "target": row["target"],
                "cmi": row["cmi"],
                "r8_level": row["level"],
                "human_label": row.get("human_label", ""),
                "ailabel": row.get("ailabel", ""),
            })
    return targets


def find_text_file(target, corpus_root):
    # corpus_clean優先
    clean_path = os.path.join(corpus_root, "corpus_clean", target + ".txt")
    if os.path.exists(clean_path):
        return clean_path

    # book/サブディレクトリ対応
    book_match = re.match(r'^book_(.+)_(ch\d+|part\d+)$', target, re.IGNORECASE)
    if book_match:
        folder = book_match.group(1)
        chapter = book_match.group(2)
        book_path = os.path.join(corpus_root, "book", folder, chapter + ".txt")
        if os.path.exists(book_path):
            return book_path

    # corpus_archiveで前方一致（日付サフィックス対応）
    target_lower = target.lower()
    for root, dirs, files in os.walk(corpus_root):
        dirs[:] = [d for d in dirs if d not in ("junkdata", "corpus_clean")]
        for f in files:
            if not f.endswith(".txt"):
                continue
            name = os.path.splitext(f)[0].lower()
            if name == target_lower:
                return os.path.join(root, f)
            remainder = name[len(target_lower):]
            if name.startswith(target_lower) and (remainder == "" or re.match(r'^_\d', remainder)):
                return os.path.join(root, f)

    return None


def annotate(model, text):
    prompt = PROMPT_TEMPLATE.format(text=text[:8000])
    response = model.generate_content(prompt)
    raw = response.text.strip()
    try:
        raw_clean = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(raw_clean)
    except json.JSONDecodeError:
        result = {
            "label": "PARSE_ERROR",
            "primary_condition": "",
            "confidence": "",
            "reason": raw[:200]
        }
    if result.get("label") not in VALID_LABELS:
        result["label"] = "PARSE_ERROR"
    return result


def main():
    parser = argparse.ArgumentParser(description="AIlabel annotator using Gemini API (v0.7.1)")
    parser.add_argument("--corpus", default="corpus")
    parser.add_argument("--master", default="data/results/corpus_master.csv")
    parser.add_argument("--out", default="ailabel/results_gemini.csv")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--only-blank", action="store_true", help="ailabelが空白の行のみ処理")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: APIキーが必要です")
        print("  --api-key オプションか GEMINI_API_KEY 環境変数を設定してください")
        sys.exit(1)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(args.model)

    all_targets = load_master(args.master)

    if args.only_blank:
        targets = [t for t in all_targets if not t["ailabel"].strip()]
        print(f"--only-blank モード: 空白ailabelのみ処理")
    else:
        targets = all_targets

    print(f"モデル    : {args.model}")
    print(f"対象件数  : {len(targets)}件 / 全{len(all_targets)}件")
    print(f"出力先    : {args.out}")
    print(f"プロンプト: annotation_criteria v0.7.1")
    print()

    os.makedirs(os.path.dirname(args.out) if os.path.dirname(args.out) else ".", exist_ok=True)
    fieldnames = ["target", "model", "human_label", "cmi", "r8_level",
                  "ai_label", "primary_condition", "confidence", "reason", "text_found"]

    errors = []
    done_count = 0

    # 既存結果を読み込んでスキップ対象を特定
    already_done = set()
    file_exists = os.path.exists(args.out)
    if file_exists:
        try:
            with open(args.out, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("ai_label") not in ("", "FILE_NOT_FOUND", None):
                        already_done.add(row["target"])
            print(f"再開モード: {len(already_done)}件スキップ（既存結果）")
        except Exception:
            pass

    targets_to_run = [t for t in targets if t["target"] not in already_done]
    print(f"実行対象  : {len(targets_to_run)}件 / 全{len(targets)}件")
    print()

    # CSVをオープン（追記 or 新規）
    write_mode = "a" if file_exists and already_done else "w"
    with open(args.out, write_mode, encoding="utf-8-sig", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if write_mode == "w":
            writer.writeheader()

        for i, item in enumerate(targets_to_run, 1):
            target = item["target"]
            print(f"[{i:03d}/{len(targets_to_run)}] {target} ... ", end="", flush=True)

            text_path = find_text_file(target, args.corpus)
            if not text_path:
                print("FILE NOT FOUND")
                errors.append(target)
                writer.writerow({
                    "target": target, "model": args.model,
                    "human_label": item["human_label"], "cmi": item["cmi"],
                    "r8_level": item["r8_level"], "ai_label": "FILE_NOT_FOUND",
                    "primary_condition": "", "confidence": "", "reason": "", "text_found": "0"
                })
                csvfile.flush()
                continue

            try:
                with open(text_path, encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception as e:
                print(f"READ ERROR: {e}")
                errors.append(target)
                continue

            try:
                result = annotate(model, text)
                print(f"{result['label']} ({result['confidence']})")
                writer.writerow({
                    "target": target, "model": args.model,
                    "human_label": item["human_label"], "cmi": item["cmi"],
                    "r8_level": item["r8_level"],
                    "ai_label": result["label"],
                    "primary_condition": result.get("primary_condition", ""),
                    "confidence": result.get("confidence", ""),
                    "reason": result.get("reason", ""),
                    "text_found": "1"
                })
                csvfile.flush()
                done_count += 1
            except Exception as e:
                print(f"API ERROR: {e}")
                errors.append(target)

            time.sleep(1.0)

    print()
    print(f"完了: {done_count}件処理 / {len(errors)}件エラー / スキップ{len(already_done)}件")
    if errors:
        print(f"\nエラー対象 ({len(errors)}件):")
        for e in errors:
            print(f"  {e}")
    print(f"\n次のステップ — kappa計算:")
    print(f"  python ailabel/ailabel_analyze.py --results {args.out}")


if __name__ == "__main__":
    main()
