#!/usr/bin/env python3
"""
全12記事に FANZA アフィリエイト購入リンクを追加する。
既にリンクがある記事はスキップ。

使い方:
  python3 scripts/add_affiliate_links.py          # 本番実行
  python3 scripts/add_affiliate_links.py --dry-run # 確認のみ (ファイル更新なし)
"""

import argparse
import os
import re
import time
from pathlib import Path

import requests

# ─── 設定 ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
POSTS_DIR = PROJECT_ROOT / "src" / "content" / "posts"
CONFIG_FILE = PROJECT_ROOT / "config" / "dmm_auth.env"
DMM_API_BASE = "https://api.dmm.com/affiliate/v3/ItemList"
AFFILIATE_LINK_MARKER = "FANZAで視聴・試聴する"

# ─── 環境変数読み込み ──────────────────────────────────────────────────────
def load_env():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

# ─── CTA テンプレート ─────────────────────────────────────────────────────
CTA_TEMPLATE = """
---

## 🛒 作品を試してみる

**[▶ FANZAで視聴・試聴する]({url})**（アフィリエイトリンク）

"""

# ─── API ──────────────────────────────────────────────────────────────────
def get_affiliate_url(work_id: str) -> str:
    """DMM API から affiliateURL を取得。失敗時は直接URL生成。"""
    api_id = os.environ.get("DMM_API_ID", "")
    affiliate_id = os.environ.get("DMM_AFFILIATE_ID", "")
    if not api_id or not affiliate_id:
        raise RuntimeError("DMM_API_ID / DMM_AFFILIATE_ID が未設定です")

    params = {
        "api_id": api_id,
        "affiliate_id": affiliate_id,
        "site": "FANZA",
        "service": "doujin",
        "floor": "digital_doujin",
        "cid": work_id,
        "hits": 1,
        "output": "json",
    }
    try:
        resp = requests.get(DMM_API_BASE, params=params, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("result", {}).get("items", [])
        if items:
            url = items[0].get("affiliateURL", "")
            if url:
                return url
    except Exception as e:
        print(f"  [WARN] API エラー ({work_id}): {e}")

    # フォールバック: 直接URL生成
    from urllib.parse import quote
    cid = work_id
    base_url = f"https://www.dmm.co.jp/dc/doujin/-/detail/=/cid={cid}/"
    return (
        f"https://al.dmm.co.jp/?lurl={quote(base_url)}"
        f"&af_id={affiliate_id}&ch=api&ch_id=link"
    )


# ─── frontmatter パース ───────────────────────────────────────────────────
def get_work_id(content: str) -> str:
    m = re.search(r'^work_id:\s*["\']?([^"\'{\n]+?)["\']?\s*$', content, re.MULTILINE)
    return m.group(1).strip() if m else ""


# ─── 挿入位置: 最終PR表記の直前 ──────────────────────────────────────────
def insert_cta(content: str, cta: str) -> str:
    """最終 PR 表記（> **PR**）の直前に CTA を挿入する。"""
    # パターン: 行頭が "> **PR**" で始まる行
    pr_pattern = re.compile(r'^>\s*\*\*PR\*\*', re.MULTILINE)
    m = pr_pattern.search(content)
    if m:
        insert_pos = m.start()
        return content[:insert_pos] + cta + content[insert_pos:]

    # フォールバック: ファイル末尾に追加
    return content.rstrip() + "\n" + cta + "\n"


# ─── メイン ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="ファイル更新しない")
    args = parser.parse_args()

    posts = sorted(POSTS_DIR.glob("*.md"))
    if not posts:
        print("[ERROR] 記事が見つかりません")
        return

    added = []
    skipped = []
    errors = []

    for post in posts:
        content = post.read_text(encoding="utf-8")

        if AFFILIATE_LINK_MARKER in content:
            skipped.append(post.name)
            print(f"[SKIP] {post.name} (既にリンクあり)")
            continue

        work_id = get_work_id(content)
        if not work_id:
            errors.append(post.name)
            print(f"[ERROR] {post.name}: work_id が見つかりません")
            continue

        print(f"[PROC] {post.name} (work_id={work_id}) ...", end=" ", flush=True)
        try:
            url = get_affiliate_url(work_id)
            cta = CTA_TEMPLATE.format(url=url)
            new_content = insert_cta(content, cta)

            if not args.dry_run:
                post.write_text(new_content, encoding="utf-8")
                added.append(post.name)
                print(f"OK -> {url[:60]}...")
            else:
                added.append(post.name)
                print(f"[DRY-RUN] -> {url[:60]}...")

            time.sleep(0.3)  # API レート制限対策
        except Exception as e:
            errors.append(post.name)
            print(f"ERROR: {e}")

    print(f"\n=== 完了 ===")
    print(f"追加: {len(added)} 件 / スキップ: {len(skipped)} 件 / エラー: {len(errors)} 件")
    if errors:
        print(f"エラー記事: {errors}")


if __name__ == "__main__":
    main()
