#!/usr/bin/env python3
"""
ocr_batch.py — スクリーンショット一括OCR→corpus保存ツール

使い方:
  python ocr_batch.py web    # screenshot/フォルダのpng/jpgをweb###.txtとしてscan/に保存
  python ocr_batch.py sn     # sn###.txtとして保存

手順:
  1. corpus/screenshot/ にスクリーンショット（png/jpg）を置く
  2. python ocr_batch.py <種別> を実行
  3. OCR→txt変換→scan/に自動保存

注意:
  - tesseractのパスが通っていない場合は TESSERACT_PATH を修正する
  - 日本語テキストはjpn、横書き前提
"""

import os
import sys
import re
import shutil
import subprocess
import shutil

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "corpus", "screenshot")
SCAN_DIR       = os.path.join(BASE_DIR, "corpus", "phase2", "scan")
PHASE2_DIR     = os.path.join(BASE_DIR, "corpus", "phase2")

# tesseractのパス（PATHが通っていない場合はフルパスを指定）
TESSERACT_PATH = os.environ.get("TESSERACT_PATH") or shutil.which("tesseract")
if not TESSERACT_PATH:
    raise SystemExit("tesseract not found. Install it and put it on PATH, "
                     "or set TESSERACT_PATH to the executable.")

VALID_TYPES = ["web", "note", "sn", "ad", "bl", "phish"]
IMAGE_EXTS  = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}


def find_max_number():
    """phase2以下の全ファイルから最大連番を取得（archiveフォルダは除外）"""
    max_num = 0
    EXCLUDE = {"sample_archive", "date_archive"}
    pattern = re.compile(r'(?:web|note|sn|ad|bl|phish)[_]?(\d+)', re.IGNORECASE)
    for root, dirs, files in os.walk(PHASE2_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE]
        for f in files:
            m = pattern.search(f)
            if m:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num
    return max_num


def ocr_image(image_path, output_txt_path):
    """tesseractでOCR実行"""
    out_base = output_txt_path.replace(".txt", "")
    cmd = [
        TESSERACT_PATH,
        image_path,
        out_base,
        "-l", "jpn",
        "--psm", "6"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"tesseractエラー: {result.stderr}")
    return output_txt_path


def main():
    if len(sys.argv) < 2:
        print("使い方: python ocr_batch.py <種別>")
        print(f"種別: {', '.join(VALID_TYPES)}")
        sys.exit(1)

    file_type = sys.argv[1].lower()
    if file_type not in VALID_TYPES:
        print(f"エラー: 種別は {', '.join(VALID_TYPES)} のいずれか")
        sys.exit(1)

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(SCAN_DIR, exist_ok=True)

    images = sorted([
        f for f in os.listdir(SCREENSHOT_DIR)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    ])

    if not images:
        print(f"画像ファイルがありません: {SCREENSHOT_DIR}")
        sys.exit(0)

    print(f"種別    : {file_type}")
    print(f"対象画像: {len(images)} 件")
    print()

    next_num = find_max_number() + 1
    saved = []
    failed = []

    for img_name in images:
        img_path = os.path.join(SCREENSHOT_DIR, img_name)
        out_name = f"{file_type}{next_num}.txt"
        out_path = os.path.join(SCAN_DIR, out_name)

        try:
            ocr_image(img_path, out_path)

            with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(f"[SOURCE] screenshot: {img_name}\n\n")
                f.write(content)

            done_dir = os.path.join(SCREENSHOT_DIR, "done")
            os.makedirs(done_dir, exist_ok=True)
            shutil.move(img_path, os.path.join(done_dir, img_name))

            print(f"[OK] {img_name} -> {out_name}")
            saved.append(out_path)
            next_num += 1

        except Exception as e:
            print(f"[ERROR] {img_name} -> {e}")
            failed.append(img_name)

    print(f"\n完了: {len(saved)}件保存 / {len(failed)}件失敗")

    if saved:
        file_list = " ".join(f'"{p}"' for p in saved)
        print(f"\n次のステップ — スキャン:")
        print(f"  python mass_audit.py --targets {file_list} --out data/results/scan_ocr.csv --append")


if __name__ == "__main__":
    main()
