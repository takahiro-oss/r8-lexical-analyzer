r"""
pdf_to_corpus_clean.py
ir_report.pdf / vol01.pdf → corpus_clean/への書き込みスクリプト
- ir_report: pdfplumberでテキスト抽出
- vol01: pdfplumberで抽出 + OCR由来の文字間スペース除去 + ページ番号残骸除去
実行: .\.venv\Scripts\python.exe scripts\pdf_to_corpus_clean.py
"""

import re
from pathlib import Path
import os

_B = os.environ.get("R8_BASE")
if not _B:
    raise SystemExit(
        "R8_BASE is not set. Point it at your R8 data root, e.g.\n"
        "  Windows : set R8_BASE=X:\\\\path\\\\to\\\\r8_strategy\n"
        "  POSIX   : export R8_BASE=/path/to/r8_strategy")

try:
    import pdfplumber
except ImportError:
    print("pdfplumberが必要です: pip install pdfplumber")
    raise

BASE = Path(_B)
SRC_DIR = BASE / "corpus" / "PDF"
DST_DIR = BASE / "corpus" / "corpus_clean"


def extract_pdf(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        pages_text = []
        for page in pdf.pages:
            t = page.extract_text() or ""
            pages_text.append(t)
    return "\n".join(pages_text)


def clean_vol01(text: str) -> str:
    """OCR由来の文字間スペース除去とページ番号残骸除去"""
    # 全角文字間の単一スペースを除去
    text = re.sub(r'(?<=[\u3000-\u9fff\uff00-\uffef])\s(?=[\u3000-\u9fff\uff00-\uffef])', '', text)
    # 全角+半角英数のスペースも除去
    text = re.sub(r'(?<=[\u3000-\u9fff])\s(?=[a-zA-Z0-9])', '', text)
    text = re.sub(r'(?<=[a-zA-Z0-9])\s(?=[\u3000-\u9fff])', '', text)
    # 行末・行頭の孤立した数字（ページ番号残骸）を除去
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
    # 連続する空行を整理
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


targets = {
    "ir_report": {"src": SRC_DIR / "ir_report.pdf", "dst": DST_DIR / "ir_report.txt"},
    "vol01":     {"src": SRC_DIR / "vol01.pdf",     "dst": DST_DIR / "vol01.txt"},
}

for name, cfg in targets.items():
    text = extract_pdf(cfg["src"])

    if name == "vol01":
        text = clean_vol01(text)

    cfg["dst"].write_text(text, encoding="utf-8")
    print(f"  {name}: 書き込み完了 -> {cfg['dst'].name} ({len(text)}文字)")

print("\nir_report・vol01 corpus_clean/への書き込み完了")
