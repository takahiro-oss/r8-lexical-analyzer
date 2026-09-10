"""
url_to_txt.py
URLのテキストを取得してcorpus/phase2にtxtファイルとして保存するスクリプト
使い方: python url_to_txt.py https://example.com https://example2.com
"""

import requests
from bs4 import BeautifulSoup
import sys
import os
import re


def url_to_txt(url, out_dir="corpus/phase2"):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, timeout=15, headers=headers)

        # エンコード自動判定（Shift-JIS対応）
        res.encoding = res.apparent_encoding

        soup = BeautifulSoup(res.text, "html.parser")

        # ノイズタグを除去
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n")

        # 空行を圧縮・前後の空白を除去
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        clean = "\n".join(lines)

        # ファイル名を生成（URL→安全なファイル名）
        fname = url.replace("https://", "").replace("http://", "")
        fname = re.sub(r"[\\/:*?\"<>|]", "_", fname)[:80]
        out_path = os.path.join(out_dir, fname + ".txt")

        os.makedirs(out_dir, exist_ok=True)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(url + "\n\n")
            f.write(clean)

        print(f"[OK] 保存完了: {out_path}")
        return out_path

    except Exception as e:
        print(f"[ERROR] {url} → {e}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python url_to_txt.py https://example.com [https://example2.com ...]")
        sys.exit(1)

    results = []
    for url in sys.argv[1:]:
        path = url_to_txt(url)
        if path:
            results.append(path)

    if results:
        print("\n--- 保存されたファイル ---")
        for p in results:
            print(p)
        print("\n次のコマンドでスキャンできます:")
        targets = " ".join(results)
        print(f"python mass_audit.py --targets {targets} --out data/results/audit_YYYYMMDD.csv --append")
