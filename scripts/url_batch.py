#!/usr/bin/env python3
"""
url_batch.py — URL一括取得・自動リネームツール

使い方:
  python url_batch.py web    # corpus/url/内の全.txtを処理してweb###としてscan/へ
  python url_batch.py note
  python url_batch.py ad
  python url_batch.py sn
  python url_batch.py bl

URLファイルの置き方:
  corpus/url/ フォルダに任意の名前の.txtを置く（複数可）
  例:
    corpus/url/陰謀論まとめ.txt
    corpus/url/カルト系.txt
    corpus/url/todo.txt

URLファイルの書き方:
  https://example.com
  https://example2.com
  [済] https://done.com     ← 処理済みは[済]が自動付与されスキップ
  # コメント行はスキップ

注意:
  - corpus/url/内の全.txtが処理対象になる
  - 処理済みURLには[済]が自動付与される（再実行時はスキップ）
  - inboxは経由せず直接scan/に保存される
"""

import requests
from bs4 import BeautifulSoup
import sys
import os
import re
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
URL_DIR  = os.path.join(BASE_DIR, "corpus", "url")
SCAN     = os.path.join(BASE_DIR, "corpus", "phase2", "scan")
PHASE2   = os.path.join(BASE_DIR, "corpus", "phase2")

VALID_TYPES = ["web", "note", "sn", "ad", "bl", "phish"]


def fetch_url(url):
    """URLからテキストを取得してクリーニング"""
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, timeout=15, headers=headers)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]
    text = "\n".join(lines)
    if len(text) < 50:
        raise ValueError("テキストが短すぎます（50文字未満）")
    return text


def find_max_number():
    """phase2以下の全ファイルから最大連番を取得"""
    max_num = 0
    pattern = re.compile(r'(?:web|note|sn|ad|bl|phish)[_]?(\d+)', re.IGNORECASE)
    for root, dirs, files in os.walk(PHASE2):
        for f in files:
            m = pattern.search(f)
            if m:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num
    return max_num


def load_urls_from_dir(url_dir):
    """
    url_dir内の全.txtを読み込み、URLと元ファイルパスのリストを返す。
    [済]行・#行・空行はスキップ。
    """
    entries = []  # (url, filepath, line_index)
    txt_files = sorted([
        f for f in os.listdir(url_dir) if f.endswith(".txt")
    ])
    if not txt_files:
        return entries

    for fname in txt_files:
        fpath = os.path.join(url_dir, fname)
        with open(fpath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            if stripped.startswith("[済]"):
                continue
            if stripped.startswith("[エラー]"):
                continue
            if stripped.startswith("http://") or stripped.startswith("https://"):
                entries.append((stripped, fpath, i))

    return entries


def mark_done(filepath, line_index):
    """処理済みURLの行頭に[済]を付ける"""
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    line = lines[line_index]
    if not line.startswith("[済]"):
        lines[line_index] = "[済] " + line
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)


def main():
    if len(sys.argv) < 2:
        print("使い方: python url_batch.py <種別>")
        print(f"種別: {', '.join(VALID_TYPES)}")
        sys.exit(1)

    file_type = sys.argv[1].lower()
    if file_type not in VALID_TYPES:
        print(f"エラー: 種別は {', '.join(VALID_TYPES)} のいずれか")
        sys.exit(1)

    # corpus/url/ フォルダ確認
    os.makedirs(URL_DIR, exist_ok=True)
    os.makedirs(SCAN, exist_ok=True)

    if not os.listdir(URL_DIR):
        print(f"[INFO] corpus/url/ にURLファイルがありません。")
        print(f"       任意の名前の.txtを置いて1行1URLを記入してください。")
        sys.exit(0)

    # URLリスト読み込み
    entries = load_urls_from_dir(URL_DIR)
    if not entries:
        print("処理対象のURLがありません（全て[済]または空）。")
        sys.exit(0)

    print(f"種別    : {file_type}")
    print(f"対象URL : {len(entries)} 件")
    print(f"URLファイル: corpus/url/")
    print()

    # 取得・scan保存
    next_num = find_max_number() + 1
    saved = []
    failed = []

    for url, fpath, line_idx in entries:
        new_name = f"{file_type}{next_num}.txt"
        dst = os.path.join(SCAN, new_name)
        try:
            text = fetch_url(url)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(url + "\n\n")
                f.write(text)
            mark_done(fpath, line_idx)
            print(f"[OK] {new_name} ← {url[:60]}")
            saved.append(dst)
            next_num += 1
        except Exception as e:
            print(f"[ERROR] {url[:60]} → {e}")
            failed.append((url, str(e)))
            # 失敗URLに[エラー]を付けて再実行時スキップ
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            if not lines[line_idx].startswith("[エラー]"):
                lines[line_idx] = "[エラー] " + lines[line_idx]
            with open(fpath, "w", encoding="utf-8") as f:
                f.writelines(lines)

    print(f"\n完了: {len(saved)}件保存 / {len(failed)}件失敗")

    if saved:
        print("\n次のステップ — スキャン:")
        file_list = " ".join(f'"{p}"' for p in saved)
        print(f"  python mass_audit.py --targets {file_list} --out data/results/scan_batch.csv --append")


if __name__ == "__main__":
    main()
