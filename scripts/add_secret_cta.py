#!/usr/bin/env python3
"""全12記事末尾にご褒美CTAリンクを追加するスクリプト"""

import os
import glob

POSTS_DIR = os.path.join(os.path.dirname(__file__), "../src/content/posts")
CTA_TEXT = """
---

📖 **最後まで読んでくれた方へ**
[→ ゆきねからの秘密のご褒美ページ](/yukine/secret/)
"""

def process_posts():
    posts = glob.glob(os.path.join(POSTS_DIR, "*.md"))
    added = 0
    skipped = 0

    for post_path in sorted(posts):
        with open(post_path, "r", encoding="utf-8") as f:
            content = f.read()

        if "秘密のご褒美ページ" in content:
            print(f"  SKIP (already has CTA): {os.path.basename(post_path)}")
            skipped += 1
            continue

        new_content = content.rstrip() + "\n" + CTA_TEXT
        with open(post_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  ADDED: {os.path.basename(post_path)}")
        added += 1

    print(f"\n完了: {added}件追加, {skipped}件スキップ")

if __name__ == "__main__":
    process_posts()
