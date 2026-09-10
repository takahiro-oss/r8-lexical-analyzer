#!/usr/bin/env python3
# r8.py — R8 Cognitive Risk Analyzer v17
# CMI (Cognitive Manipulation Index): 0=安全, 100=最高リスク
# 権威リスク v2: 偽権威/正当権威の2層判定導入
# 表記ゆれ正規化 Phase1: NFKC+カタカナ→ひらがな変換、辞書ひらがな読み追加
# v11: スピリチュアル・疑似科学・代替医療系語彙を辞書に追加
# v12: HYPE・STATISTICAL・LOGICAL・CLICKBAIT・ENEMY_FRAME語彙を拡張
# v13: アカシックレコード・ハイヤーセルフ・カルマ等スピリチュアル核心語彙を追加
# v14: 政治陰謀論系婉曲表現（PROPAGANDA・ENEMY_FRAME・FEAR・CONCLUSION）を追加
# v15: 国際陰謀論系語彙（ディープステート・イルミナティ・人口削減等）を追加

import sys
import io
import re
import unicodedata

# Windows cp932環境でのUnicodeEncodeError対策
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp932", "shift_jis", "shift-jis", "mbcs"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

VERSION = "v17"
# v17: dictionary expansion + variable threshold design (--threshold / --high-threshold)
#      default thresholds: HIGH=41 / MEDIUM=35
#      calibration metrics: see paper §4.3 and data/results/corpus_master.csv
#      high-precision mode: --high-threshold 60

# --- 外部ライブラリのインポート ---
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    YT_AVAILABLE = True
except ImportError:
    YT_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PDF_ENGINE = "pymupdf"
except ImportError:
    PDF_ENGINE = None

# ===========================
# 表記ゆれ正規化 (Phase 1)
# ===========================
def normalize_text(text):
    """
    Phase1 表記ゆれ正規化:
    - NFKC正規化: 全角英数→半角、！→! など記号統一
    - カタカナ→ひらがな変換（濁音・半濁音含む完全対応）
    - 連続空白・改行の圧縮
    制約: 漢字←→読み変換・多義性・文脈判定はPhase2（形態素解析）以降
    """
    if not text:
        return text
    # NFKC: 全角英数→半角、合字分解など
    text = unicodedata.normalize("NFKC", text)
    # カタカナ→ひらがな（ァ=12449〜ン=12531、差=96）
    result = []
    for ch in text:
        cp = ord(ch)
        if 12449 <= cp <= 12531:
            result.append(chr(cp - 96))
        else:
            result.append(ch)
    text = "".join(result)
    # 連続空白・改行の圧縮
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

# ===========================
# 12カテゴリ辞書
# ===========================

# --- 権威リスク v2: 2層構造 ---
PSEUDO_AUTHORITY = [
    "科学的に証明", "大学の研究", "実証済み", "データが示す",
    "アナリストチーム", "独自調査", "研究によれば", "研究によると",
    "調査によれば", "専門家が認めた", "権威ある機関が",
    # スピリチュアル・疑似科学系偽権威
    "波動", "ホメオパシー", "レメディ", "フラワーエッセンス",
    "レイキ", "オーラ", "チャクラ", "アカシックレコード",
    "エネルギー療法", "量子波動", "波動水", "波形エネルギー",
    "量子力学で証明", "素粒子の振動", "科学で証明されつつ",
    "論文で報告されている", "3000人のセラピー", "年間300万人",
    "細胞レベルで", "DNAに働きかける",
    "ハイヤーセルフ", "チャネリング", "クンダリーニ",
    "アストラル体", "エーテル体", "スピリットガイド",
    "アセンデッドマスター", "好転反応", "プラーナ",
    "サードアイ", "エネルギーワーク", "ヒーリング",
    "スピリチュアルヒーリング", "波動修正", "霊能力",
    # ひらがな読み（表記ゆれ対応）
    "かがくてきにしょうめい", "じっしょうずみ", "どくじちょうさ",
    "はどう", "ほめおぱしー", "れめでぃ", "おーら", "ちゃくら",
    # 選別・特別化による権威的誘導（Zimbardo, 2007）
    "あなただけに", "特別な方に", "選ばれた人", "あなたならできる",
    "あなただけが", "特別な存在", "選ばれし者",
    # 宗教的・道徳的権威借用（渡邉美樹著書由来）
    "敬天愛人", "よい気とわるい気",
]
LEGIT_AUTHORITY = [
    "専門家", "教授", "博士", "学者", "権威",
    "エビデンス", "論文", "研究者", "機関", "医師", "臨床",
    # ひらがな読み
    "せんもんか", "きょうじゅ", "はかせ", "がくしゃ",
]

HYPE_WORDS = [
    "急騰","大急騰","急騰目前","急上昇","爆上げ",
    "期待される","可能性がある","指摘されている","と言われている",
    "確実視","見込まれる","予想される","とも言える","かもしれない",
    # スピリチュアル・疑似科学系責任回避語
    "といわれています","とされています","という考え方があります",
    "体感される方が多い","感じる方もいます","つながると言われ",
    "宇宙からのメッセージ","サインかもしれません","暗示しています",
    "スピリチュアル的には","霊的に見ると","魂レベルでは",
    "エネルギー的に","波動的に","高次元では",
    # 煽り系誇張語
    "激減","劇的に改善","驚異の","奇跡の","たった3ヶ月で",
    "99%の人が","ほとんどの人が知らない","知らなきゃ損",
    "鳥肌が立った","眠れなくなる","震えが止まらない",
    # ひらがな読み
    "きたいされる","かのうせいがある","みこまれる",
    # 簡単さ誇張・誇大語（FN実測分析 2026-04-28に基づく追加）
    "変えるだけで","たったそれだけで","が圧倒的に",
    "万人を突破",
]
URGENCY_WORDS = [
    "一度しか言いません","必ず買うべき","スーパーインサイダー","一攫千金","今だけ","期間限定","急げ","残りわずか","本日限定",
    "締め切り","今すぐ","最後のチャンス","今が買い時","今のうち",
    # LINE・SNS誘導語彙
    "LINEはこちら","LINE追加","LINEで受け取る","LINE登録","IDはこちら",
    "DMください","気軽にDM","まずはDM","無料で受け取る","無料配布中",
    "今すぐ登録","登録はこちら","友達追加","限定公開","シークレット",
    # 削除系緊急誘導
    "8時間後に削除","25分後に削除","今週限り","今だけ公開",
    "削除前に","消される前に",
    "以内に削除","日後に消","時間で消","時間後に消します","日以内に消します",
    # ひらがな読み
    "いまだけ","きかんげんてい","いそげ","のこりわずか",
    "ほんじつげんてい","しめきり","いますぐ","さいごのちゃんす",
    # アフィリエイト・相談誘導型（FN実測分析 2026-04-28に基づく追加）
    # 法律・投資・健康系アフィリエイトサイトに共通する即時行動誘導語彙
    "無料相談はこちら","今すぐ相談","無料で相談",
    "解決への近道","プロに相談",
]
ABSOLUTIST_WORDS = [
    "絶対","必ず","100%","完全","間違いなく","確実に","全員","誰でも","保証",
    # 疑似科学・スピリチュアル系断定語
    "副作用が全くない","どんな病気にも","必ず引き寄せられる",
    "どんな症状にも効く","年齢を問わない","安全で効果的",
    "好転反応","再現性がある","細胞レベルで回復",
    # 煽り系断定語
    "必ず買い","今すぐやれ","一度だけ言う","8時間後に削除",
    "命の危険を冒して","1億回でも言います","本っっ当に大事",
    "ゾッとした","衝撃展開",
    # ひらがな読み
    "ぜったい","かならず","かんぜん","まちがいなく","かくじつに",
    "ぜんいん","だれでも","ほしょう",
    # 労働搾取系断定語（渡邉美樹著書由来）
    "死ぬまで働け","のーはありえない",
]
EMOTIONAL_WORDS = [
    "奇跡","衝撃","感動","驚愕","革命的","人生が変わる","夢の",
    # スピリチュアル系感情語
    "覚醒","次元上昇","魂","引き寄せ","潜在意識","使命",
    "ツインレイ","ツインソウル","宇宙の法則","光の存在",
    "愛のエネルギー","スターシード","ライトワーカー",
    "ミラクル","奇跡的回復","人生が好転","運命の人",
    "カルマ","前世","守護霊","魂の覚醒","ソウルメイト",
    "エンジェル","グラウンディング","次元","神聖",
    "宇宙からのメッセージ","サイン","シンクロニシティ",
    # ひらがな読み
    "きせき","しょうげき","かんどう","きょうがく","かくめいてき",
    "かくせい","じげんじょうしょう","たましい","ひきよせ",
    "せんざいいしき","しめい",
    # やりがい搾取系感情語（渡邉美樹著書由来）
    "お金以上のもの","ありがとうを集める",
]
FEAR_WORDS = [
    "危険","崩壊","破滅","恐怖","脅威","危機",
    # 代替医療・疑似科学系恐怖語
    "標準治療では治らない","副反応","余命","手遅れ",
    "このままでは","悪化する一方","西洋医学の限界",
    "抗がん剤の毒性","ワクチンの危険",
    # 政治陰謀論系恐怖語
    "国が滅びる","日本終わる","手遅れになる","取り返しがつかない",
    "侵略される","乗っ取られる","消滅する","存亡の危機",
    "外国人に占領","文化が破壊","伝統が失われる","子孫に申し訳ない",
    # 国際陰謀論系恐怖語
    "人類が滅びる","文明がリセット","核攻撃","世界が終わる",
    "闇の勢力に支配","人口が削減される","マイクロチップで管理",
    "電磁波攻撃","5Gで洗脳","監視社会が来る",
    # ひらがな読み
    "きけん","ほうかい","はめつ","きょうふ","きょうい","きき",
    # 法的恐怖・損失回避型（FN実測分析 2026-04-28に基づく追加）
    # 弁護士詐称・投資詐欺・カルト勧誘系に共通する恐怖誘導語彙
    "最悪のシナリオ","人生を棒に振る","取り返しのつかない",
    "後悔することになる","年以下の懲役","円以下の罰金",
]
ANECDOTAL_MARKERS  = [
    "私の場合","体験談","友人が","実際に試した","お客様の声",
    # スピリチュアル・疑似科学系体験談
    "私が体験した","奇跡が起きた","実際に引き寄せた",
    "本当に治った","信じられない変化","体感した","腑に落ちた",
    # 権威的価値判断語彙（Milgram, 1974）
    "自己責任だ","勉強不足だ","覚悟がない","本気でないから",
    "甘えている","努力が足りない","意識が低い",
]
STATISTICAL_WORDS  = [
    "累計","最大","平均","No.1","利用者数","成功率","合格率","改善率","実績",
    # スピリチュアル・疑似科学系統計語
    "万人が体験","千人以上","%が改善","倍の効果","年間","施術数",
    "症例","モニター","満足度","効果を実感","リピート率",
    "3000人","1万人","95%","99%","97%",
]
CONCLUSION_MARKERS = [
    "だから","つまり","したがって","結果として","以上より","当然","明らかに",
    # スピリチュアル・疑似科学系論理飛躍語
    "これが証拠","だからこそ","それが真実","宇宙の摂理","自然の法則",
    "科学では説明できない","理屈ではなく","感じればわかる",
    "信じる者だけが","目覚めた人には","波動が証明する",
    "カルマの法則","因果の法則","必然的に","すべては繋がっている",
    "宇宙が答えてくれる","引き寄せられる","魂が知っている",
    # 政治陰謀論系論理飛躍語
    "これが現実","だから日本は","このままでは","見えてくる",
    "裏を読めば","本質は","真相は","実はこれが","歴史が証明する",
    "データが示すように","事実として","明白である","疑いようがない",
]
CLICKBAIT_WORDS    = [
    "衝撃の事実","絶対に見て","知らないと損","閲覧注意",
    # スピリチュアル系クリックベイト
    "知らないと危険","見逃してはいけない","今すぐ確認","衝撃の真実",
    "99%が知らない","医師が隠す","公式が認めない",
    # 結末煽り語彙（FearRisk複合）
    "の末路",
    # SNS煽り見出し語（FN実測分析 2026-04-28に基づく追加）
    "【警告】","【悲報】",
]
PROPAGANDA_WORDS   = [
    "メディアは嘘","誰も言わない","裏の勢力","洗脳",
    # 陰謀論・疑似科学系
    "三大標準治療","製薬会社が隠す","GHQが封印","本当のことを言わない",
    "隠されてきた真実","西洋医学の嘘","陰謀","闇の勢力",
    # 政治陰謀論系婉曲表現
    "マスコミは","メディアが隠す","報道されない","既存メディアは",
    "テレビは言わない","新聞は報じない","政府が隠している",
    "真実を知らせない","覚醒","目を覚ます","国民を欺く",
    "売国","グローバリスト","ディープステート","影の政府",
    "占領政策","GHQの洗脳","戦後レジーム","日本を守る",
    "外資に売られる","国益を守る","日本人ファースト",
    "スパイ","工作員","情報戦","認知戦",
    # 国際陰謀論系
    "人類削減計画","マインドコントロール","偽史",
    "捏造された歴史","真実の歴史は隠蔽","歴史を書き換えた",
    "WGIP","占領政策によって","世界統一政府を目指す",
    "ケムトレイル","5Gで支配","マイクロチップを埋め込む",
    "フラットアース","地球平面","タルタリア",
]
ENEMY_FRAME        = [
    "敵","支配","騙されている","操作されている",
    # スピリチュアル・疑似科学系敵フレーム
    "西洋医学に騙される","製薬会社の罠","目覚めていない人",
    "洗脳された","真実を知らない","マトリックス","覚醒できない",
    # 政治陰謀論系敵フレーム
    "外国勢力","反日","売国奴","国を売る","乗っ取られる",
    "外国人に支配される","日本が危ない","国民が気づかない",
    "エリートに支配","既得権益","利権","闇の組織",
    "グローバル資本","多国籍企業の陰謀","WHO支配","国連の罠",
    # 国際陰謀論系敵フレーム
    "ディープステート","影の政府","新世界秩序","闇の政府",
    "フリーメイソン","イルミナティ","レプティリアン",
    "世界支配","人口削減","秘密結社","三百人委員会",
    "ロスチャイルド","ロックフェラー","ビルダーバーグ",
    "グローバリズムの罠","世界統一政府","人類削減計画",
    # 敵の無能化・矮小化（Janis, 1972）
    "連中には無理だ","所詮","どうせ","あいつらには","たかが知れている",
    # レイシズム系敵フレーム（高優先度・文脈依存低）
    "売国議員","反日左翼","反日勢力","在日特権","特定外国人",
]
ALLY_FRAME         = [
    "我々","みんな","国民","真実を知る人",
    # スピリチュアル系味方フレーム
    "目覚めた人","覚醒した仲間","光の民","波動が高い人",
    "選ばれし","使命を持つ","スターシードの仲間",
    # 政治陰謀論系味方フレーム
    "真の日本人","愛国者","志ある人","目覚めた国民",
    "本当の日本を守る","日本人として","大和魂","武士道精神",
    "先人の知恵","日本の伝統","国体を守る",
]
SEXUAL_INDUCTION_WORDS = [
    # 直接的誘導（ひらがな変換後にマッチする形で記載）
    "せふれ","おふぱこ","わんないと","出会い募集","即会い",
    "写真交換","動画送ります","体の関係","大人の関係",
    # 婉曲・SNS誘導
    "ご縁があれば","気軽にメッセージ","IDを教えます","LINE教えます",
    "仲良くしたい","お話しませんか","暇な人DM","気が合う人",
    "大人の友達","割り切り","真剣な出会い","恋活","婚活以外",
]
BEAUTY_DIET_WORDS = [
    # ダイエット煽り（正規化後にマッチする形）
    "痩せるは通過点","何でも食べてすぐ戻る","たった1週間で",
    "食べても太らない","リバウンドなし","脂肪が燃える",
    "せるらいと撃退","代謝爆上がり","むくみ即解消",
    "りばうんどなし",
    # 美容・夜職・収入系
    "稼げる身体","夜職","売上UP","指名本数",
    "2〜3ヶ月でさっさと終わらせ","身体で稼ぐ",
    # ひらがな読み
    "やせる","ぜいにく","たいしゃ",
]
DISCLAIMER_WORDS   = ["投資助言ではありません","損失の責任","情報提供および教育目的","投資顧問として","元本を失う可能性","将来の成果を保証","デューデリジェンス"]
ANONYMOUS_SUBJECT  = [
    "当社","一部のアナリスト","市場では","業界では","関係者によると","一部で","見方が出ている","強気の買い判断","目標株価を示す",
    # 全員一致の幻想（Janis, 1972）
    "皆さんご存知の通り","言うまでもなく","常識的に考えて","誰もが認める",
    "当然のことながら","言わずもがな","周知の通り",
]

# ===========================
# 重み付けと閾値
# ===========================
THRESHOLDS = {
    "authority":           0.05,
    "emotional":           0.08,
    "logical":             0.04,
    "statistical":         0.06,
    "hype":                0.05,
    "clickbait":           0.04,
    "propaganda":          0.04,
    "fear":                0.05,
    "enemy_frame":         0.04,
    "disclaimer_exploit":  0.30,
    "anonymous_authority": 0.30,
    "naked_number":        0.30,
    "sexual_induction":    0.03,
    "beauty_diet":         0.04,
}
WEIGHTS = {
    "authority":           0.12,
    "emotional":           0.10,
    "logical":             0.08,
    "statistical":         0.14,
    "hype":                0.08,
    "clickbait":           0.04,
    "propaganda":          0.04,
    "fear":                0.08,
    "enemy_frame":         0.08,
    "disclaimer_exploit":  0.08,
    "anonymous_authority": 0.06,
    "naked_number":        0.06,
    "sexual_induction":    0.04,
    "beauty_diet":         0.00,
}
CATEGORY_LABELS = {
    "authority":           "Authority Risk        (権威リスク)",
    "emotional":           "Emotional Risk        (感情誘導リスク)",
    "logical":             "Logical Risk          (論理飛躍リスク)",
    "statistical":         "Statistical Risk      (統計操作リスク) ★",
    "hype":                "Hype Risk             (責任回避型煽りリスク)",
    "clickbait":           "Clickbait Risk        (クリックベイト)",
    "propaganda":          "Propaganda Risk       (プロパガンダ)",
    "fear":                "Fear Risk             (恐怖煽動リスク)",
    "enemy_frame":         "Enemy Frame           (敵/味方フレーム)",
    "disclaimer_exploit":  "Disclaimer Exploit    (免責文逆利用) ★",
    "anonymous_authority": "Anonymous Authority   (匿名権威)",
    "naked_number":        "Naked Number          (根拠なき具体数値)",
    "sexual_induction":    "Sexual Induction      (性的誘導リスク)",
    "beauty_diet":         "Beauty/Diet Hype      (美容ダイエット煽り) ※参考値",
}

# ===========================
# CMIレベル判定
# ===========================
# high_threshold / medium_thresholdはデフォルト引数で設定。
# 既存の cmi_level(cmi) 呼び出しはそのまま動作（後方互換性維持）。
# r8.py単体実行時は --high-threshold / --medium-threshold で上書き可能。
# mass_audit.pyからのimport時はデフォルト値が使われる。
#
# Calibration metrics are referenced from the paper §4.3 and data/results/corpus_master.csv.
# Hard-coding numeric values in comments introduces staleness risk on corpus updates.
CMI_HIGH_DEFAULT   = 41
CMI_MEDIUM_DEFAULT = 35

def cmi_level(cmi, high_threshold=CMI_HIGH_DEFAULT, medium_threshold=CMI_MEDIUM_DEFAULT):
    if cmi >= high_threshold:
        return "HIGH"
    elif cmi >= medium_threshold:
        return "MEDIUM"
    else:
        return "LOW"

# ===========================
# 分析ロジック
# ===========================
def density(text, words):
    if not text:
        return 0.0
    count = sum(text.count(w) for w in words)
    return count / (len(text) / 100)

def authority_score(text):
    """
    権威リスク v2: 2層判定
    - PSEUDO_AUTHORITY: 偽権威専用語はそのままリスクカウント
    - LEGIT_AUTHORITY:  正当権威語はHYPE共起度に応じてリスク加算
    """
    pseudo = density(text, PSEUDO_AUTHORITY)
    legit  = density(text, LEGIT_AUTHORITY)
    hype   = density(text, HYPE_WORDS)
    hype_ratio = min(hype / 0.05, 1.0)
    legit_risk = legit * hype_ratio * 0.5
    return pseudo + legit_risk

def bar(v, width=20):
    filled = max(0, min(width, round(v * width)))
    return "[" + "█" * filled + "░" * (width - filled) + f"] {v:.2f}"

# ===========================
# テキスト取得
# ===========================
def get_text(target):
    if target.startswith("http://") or target.startswith("https://"):
        if "youtube.com" in target or "youtu.be" in target:
            if not YT_AVAILABLE:
                return "[Error] youtube-transcript-api がありません"
            vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", target)
            if not vid_match:
                return "[Error] YouTube URL 不正"
            vid = vid_match.group(1)
            try:
                ts = YouTubeTranscriptApi.get_transcript(vid, languages=["ja", "en"])
                print("YouTube字幕取得完了\n")
                return " ".join([x["text"] for x in ts])
            except Exception as e:
                return f"[Error] 字幕取得失敗: {e}"
        try:
            import requests
            from bs4 import BeautifulSoup
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = requests.get(target, headers=headers, timeout=15)
            if r.status_code != 200:
                return f"[Error] HTTP {r.status_code}: {target}"
            r.encoding = r.apparent_encoding
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script","style","nav","footer","header"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            if len(text) < 100:
                return "[Error] テキスト取得失敗（JS動的サイトの可能性）"
            return text
        except Exception as e:
            return f"[Error] URL取得失敗: {e}"

    if target.lower().endswith(".pdf"):
        if not PDF_ENGINE:
            return "[Error] PDF用ライブラリ(PyMuPDF)がありません"
        try:
            doc = fitz.open(target)
            return "\n".join(page.get_text() for page in doc)
        except Exception as e:
            return f"[Error] PDF読み込み失敗: {e}"

    try:
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except FileNotFoundError:
        return f"[Error] ファイル未検出: {target}"

# ===========================
# 分析
# ===========================
def analyze(text):
    text = normalize_text(text)  # Phase1: 表記ゆれ正規化
    raw = {
        "authority":           authority_score(text),
        "emotional":           (density(text, URGENCY_WORDS) + density(text, ABSOLUTIST_WORDS) + density(text, EMOTIONAL_WORDS)) / 3,
        "logical":             density(text, ANECDOTAL_MARKERS + CONCLUSION_MARKERS),
        "statistical":         density(text, STATISTICAL_WORDS) + (len(re.findall(r"\d+%", text)) / 10),
        "hype":                density(text, HYPE_WORDS),
        "clickbait":           density(text, CLICKBAIT_WORDS),
        "propaganda":          density(text, PROPAGANDA_WORDS),
        "fear":                density(text, FEAR_WORDS),
        "enemy_frame":         density(text, ENEMY_FRAME + ALLY_FRAME),
        "disclaimer_exploit":  0.8 if (density(text, DISCLAIMER_WORDS) > 0.1 and density(text, HYPE_WORDS) > 0.1) else 0.0,
        "anonymous_authority": min(density(text, ANONYMOUS_SUBJECT) * 2, 1.0),
        "naked_number":        0.8 if (re.search(r"\d+倍|\d+円", text) and not re.search(r"出典|引用", text)) else 0.0,
        "sexual_induction":    density(text, SEXUAL_INDUCTION_WORDS),
        "beauty_diet":         density(text, BEAUTY_DIET_WORDS),
        "_structure":          round(density(text, ["なぜなら", "原因", "解決"]) / 3, 3),
        "_sentiment_bias":     round(abs(density(text, EMOTIONAL_WORDS) - density(text, FEAR_WORDS)), 3),
    }
    return raw

# ===========================
# レポート出力
# ===========================
def report(text, source, high_threshold=CMI_HIGH_DEFAULT, medium_threshold=CMI_MEDIUM_DEFAULT):
    raw = analyze(text)
    ri = {cat: min(raw.get(cat, 0) / THRESHOLDS[cat], 1.0) for cat in WEIGHTS}
    cmi = round(sum(WEIGHTS[c] * ri[c] * 100 for c in WEIGHTS), 1)
    level = cmi_level(cmi, high_threshold, medium_threshold)

    print("\n" + "=" * 54)
    print(f"  R8 Analyzer {VERSION} | Source: {source[:38]}")
    print("=" * 54)
    print(f"  CMI  : {cmi:5.1f} / 100   [{level}]")
    print(f"  (Cognitive Manipulation Index: 高いほど高リスク)")
    print("-" * 54)
    for cat, lbl in CATEGORY_LABELS.items():
        print(f"  {lbl}\n    {bar(ri[cat])}")
    print("-" * 54)
    print(f"  _structure_score    : {raw['_structure']:.3f}  (論理構造密度)")
    print(f"  _sentiment_bias     : {raw['_sentiment_bias']:.3f}  (感情極性偏差)")
    print("-" * 54)
    print("\n[Notice] R8は認知リスクのフラグ提示ツールです。")
    print("[Notice] CMIは操作構造の定量化であり、真偽判定ではありません。\n")

    return cmi

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="R8 Cognitive Risk Analyzer — CMIスコアで認知的操作リスクを定量化します",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
threshold guide:
  --high-threshold 41  <- default (standard mode)
  --high-threshold 60  <- high-precision mode
  calibration metrics: see paper §4.3 and data/results/corpus_master.csv

examples:
  python r8.py https://example.com/article
  python r8.py mytext.txt
  python r8.py mytext.txt --high-threshold 60
  python r8.py mytext.txt --high-threshold 35 --medium-threshold 20
        """
    )
    parser.add_argument("target", help="解析対象（URL / ファイルパス）")
    parser.add_argument(
        "--high-threshold", type=float, default=CMI_HIGH_DEFAULT,
        metavar="N",
        help=f"HIGHと判定するCMI閾値（デフォルト: {CMI_HIGH_DEFAULT}）"
    )
    parser.add_argument(
        "--medium-threshold", type=float, default=CMI_MEDIUM_DEFAULT,
        metavar="N",
        help=f"MEDIUMと判定するCMI閾値（デフォルト: {CMI_MEDIUM_DEFAULT}）"
    )

    args = parser.parse_args()

    if args.high_threshold <= args.medium_threshold:
        print(f"[Error] --high-threshold ({args.high_threshold}) は --medium-threshold ({args.medium_threshold}) より大きくしてください")
        sys.exit(1)

    content = get_text(args.target)
    if content.startswith("[Error]"):
        print(content)
    else:
        report(content, args.target, args.high_threshold, args.medium_threshold)
