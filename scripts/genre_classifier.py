"""
genre_classifier.py
corpus_archive の txt ファイルをキーワードマッチで一次ジャンル分類する。
信頼度が低いものは TAKAHIRO による人間判定用リストに出力する。

Genre codes:
  1 = 投資・金融
  2 = カルト・宗教
  3 = 恋愛・人間関係
  4 = 教育・自己啓発
  5 = 政治・陰謀
  6 = その他（要人間判定）
"""

import os
import csv
import glob
import re

_B = os.environ.get("R8_BASE")
if not _B:
    raise SystemExit(
        "R8_BASE is not set. Point it at your R8 data root, e.g.\n"
        "  Windows : set R8_BASE=X:\\\\path\\\\to\\\\r8_strategy\n"
        "  POSIX   : export R8_BASE=/path/to/r8_strategy")

# ────────────────────────────────────────────
# 設定
# ────────────────────────────────────────────
CORPUS_DIR = os.path.join(_B, "corpus", "corpus_archive")
CSV_IN     = os.path.join(_B, "data", "results", "audit_results_v3.csv")
OUT_ALL    = os.path.join(_B, "data", "results", "genre_labels_all.csv")
OUT_HUMAN  = os.path.join(_B, "data", "results", "genre_labels_human_review.csv")

# 信頼度しきい値：これ未満は人間判定へ
CONFIDENCE_THRESHOLD = 0.35

# ────────────────────────────────────────────
# キーワード辞書（スコア加算方式）
# 各キーワードにweight付き。複数マッチで加算。
# ────────────────────────────────────────────
GENRE_KEYWORDS = {
    1: {  # 投資・金融
        "高スコア": ["FX", "仮想通貨", "証拠金", "自動売買", "トレード", "配当",
                    "株式", "ビットコイン", "投資信託", "NISA", "損切り", "含み損",
                    "急騰", "大急騰", "スーパーインサイダー", "ロスカット", "スワップ",
                    "レバレッジ", "通貨ペア", "円高", "円安", "相場", "売買"],
        "低スコア": ["お金", "稼ぐ", "収入", "副業", "資産", "利益"]
    },
    2: {  # カルト・宗教
        "高スコア": ["教祖", "霊", "スピリチュアル", "信者", "修行", "瞑想",
                    "覚醒", "悟り", "波動", "カルマ", "輪廻", "神様", "神社",
                    "祈祷", "除霊", "浄化", "高次元", "宇宙の法則", "引き寄せの法則",
                    "救済", "解脱", "布教", "入信", "脱会"],
        "低スコア": ["感謝", "愛", "幸せ", "豊かさ"]
    },
    3: {  # 恋愛・人間関係
        "高スコア": ["彼女", "彼氏", "モテ", "マッチング", "LINE ID", "出会い",
                    "非モテ", "恋愛", "セフレ", "童貞", "恋人", "婚活", "マチアプ",
                    "ナンパ", "告白", "恋活", "不倫", "ワンナイト", "友達以上"],
        "低スコア": ["友達", "仲良く", "人間関係", "コミュニケーション"]
    },
    4: {  # 教育・自己啓発
        "高スコア": ["コーチング", "セミナー", "メンター", "自己啓発", "習慣",
                    "マインドセット", "メンタル", "成功法則", "潜在意識",
                    "ビジョン", "目標設定", "タスク管理", "生産性",
                    "ビジネス", "起業", "経営者", "社長", "年収"],
        "低スコア": ["成長", "学ぶ", "スキル", "努力", "挑戦"]
    },
    5: {  # 政治・陰謀
        "高スコア": ["反日", "陰謀", "マスコミ", "売国", "グローバリスト",
                    "ディープステート", "ワクチン 陰謀", "洗脳", "支配層",
                    "メディア 嘘", "工作員", "移民 問題", "在日",
                    "統一教会", "共産党 中国"],
        "低スコア": ["政治", "選挙", "政府", "自民党", "野党"]
    },
}

HIGH_WEIGHT = 2.0
LOW_WEIGHT  = 0.5

# ────────────────────────────────────────────
# テキストファイル検索：target名 → txtパス
# ────────────────────────────────────────────
def build_txt_index(corpus_dir):
    """corpus_archive 内の全txtをインデックス化。
    target名（例: AD_001）→ ファイルパスの辞書を返す。"""
    index = {}
    for fpath in glob.glob(os.path.join(corpus_dir, "*.txt")):
        fname = os.path.basename(fpath)
        # ファイル名から日付サフィックスを除去してtarget名を抽出
        # 例: AD_001_20260326.txt → AD_001
        #     note111.txt → note111
        base = os.path.splitext(fname)[0]
        # 末尾の _YYYYMMDD を除去
        key = re.sub(r'_\d{8}$', '', base)
        # 大文字小文字を正規化して登録（元のキーもそのまま登録）
        index[key] = fpath
        index[key.upper()] = fpath
        index[key.lower()] = fpath
    return index

def find_txt(target, index):
    """target名に対応するtxtパスを返す。見つからない場合はNone。"""
    candidates = [
        target,
        target.upper(),
        target.lower(),
        # _ch1 など書籍サブファイルのケース
    ]
    for c in candidates:
        if c in index:
            return index[c]
    # 部分一致フォールバック
    for key, path in index.items():
        if key.startswith(target) or target.startswith(key):
            return path
    return None

# ────────────────────────────────────────────
# ジャンル分類
# ────────────────────────────────────────────
def classify(text):
    """テキストからジャンルコードと信頼度を返す。"""
    scores = {g: 0.0 for g in GENRE_KEYWORDS}
    text_lower = text.lower()

    for genre, kw_dict in GENRE_KEYWORDS.items():
        for kw in kw_dict.get("高スコア", []):
            if kw.lower() in text_lower:
                scores[genre] += HIGH_WEIGHT
        for kw in kw_dict.get("低スコア", []):
            if kw.lower() in text_lower:
                scores[genre] += LOW_WEIGHT

    total = sum(scores.values())
    if total == 0:
        return 6, 0.0  # その他、信頼度ゼロ

    best_genre = max(scores, key=lambda g: scores[g])
    best_score = scores[best_genre]
    confidence = best_score / total

    # 2位との差が小さい場合は信頼度を下げる
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) >= 2 and sorted_scores[1] > 0:
        margin = (sorted_scores[0] - sorted_scores[1]) / sorted_scores[0]
        confidence = confidence * margin  # マージンが小さいと信頼度低下

    # 絶対スコアが低すぎる場合も信頼度を下げる
    if best_score < 2.0:
        confidence *= 0.5

    return best_genre, round(confidence, 3)

# ────────────────────────────────────────────
# メイン処理
# ────────────────────────────────────────────
def main():
    txt_index = build_txt_index(CORPUS_DIR)
    print(f"txt index size: {len(txt_index) // 3} files")

    # CSV読み込み
    with open(CSV_IN, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    print(f"CSV rows: {len(rows)}")

    results_all = []
    results_human = []

    GENRE_NAMES = {
        1: "投資・金融",
        2: "カルト・宗教",
        3: "恋愛・人間関係",
        4: "教育・自己啓発",
        5: "政治・陰謀",
        6: "その他",
    }

    for row in rows:
        target = row.get("target", "").strip()
        if not target:
            continue

        txt_path = find_txt(target, txt_index)
        if txt_path is None:
            genre_code = 6
            confidence = 0.0
            reason = "txt_not_found"
        else:
            try:
                with open(txt_path, encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                # URLのみの場合は最初の行を除外
                lines = text.strip().split("\n")
                if lines and lines[0].startswith("http"):
                    text = "\n".join(lines[1:])

                genre_code, confidence = classify(text)
                reason = "auto"
            except Exception as e:
                genre_code = 6
                confidence = 0.0
                reason = f"error:{e}"

        result = {
            "target": target,
            "genre_code": genre_code,
            "genre_name": GENRE_NAMES[genre_code],
            "confidence": confidence,
            "needs_human": confidence < CONFIDENCE_THRESHOLD or genre_code == 6,
            "reason": reason,
            "human_label": row.get("human_label", ""),
            "txt_path": txt_path or "NOT_FOUND",
        }
        results_all.append(result)
        if result["needs_human"]:
            results_human.append(result)

    # 全件出力
    with open(OUT_ALL, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results_all[0].keys())
        writer.writeheader()
        writer.writerows(results_all)

    # 人間判定必要分のみ出力
    with open(OUT_HUMAN, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results_all[0].keys())
        writer.writeheader()
        writer.writerows(results_human)

    # サマリー
    genre_counts = {}
    for r in results_all:
        gn = r["genre_name"]
        genre_counts[gn] = genre_counts.get(gn, 0) + 1

    print("\n=== 分類結果サマリー ===")
    for gn, cnt in sorted(genre_counts.items()):
        print(f"  {gn}: {cnt}件")
    print(f"\n自動分類確定: {sum(1 for r in results_all if not r['needs_human'])}件")
    print(f"人間判定必要: {len(results_human)}件")
    print(f"\n出力: {OUT_ALL}")
    print(f"人間判定リスト: {OUT_HUMAN}")

if __name__ == "__main__":
    main()
