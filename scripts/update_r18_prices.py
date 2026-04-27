#!/usr/bin/env python3
"""
r18-blog 既存記事の価格情報を DMM API で自動更新する。

処理内容:
  1. src/content/posts/*.md を全走査
  2. frontmatter の work_id フィールドで DMM API を叩く
  3. 価格が変わっていれば frontmatter の price/affiliate_url を更新
  4. 変更あれば npm run build && wrangler deploy
  5. 変更なければスキップ

使い方:
  python3 scripts/update_r18_prices.py
  python3 scripts/update_r18_prices.py --dry-run   # 実際には更新しない
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# dmm_api_client を同ディレクトリから import
sys.path.insert(0, str(Path(__file__).parent))
from dmm_api_client import search_by_cid, make_affiliate_link

PROJECT_ROOT = Path(__file__).parent.parent
POSTS_DIR    = PROJECT_ROOT / "src" / "content" / "posts"
LOG_FILE     = Path("/tmp/r18_price_update.log")

_PRICE_PATTERN        = re.compile(r'^(price\s*:\s*)[^\n]*$', re.MULTILINE)
_AFFILIATE_PATTERN    = re.compile(r'^(affiliate_url\s*:\s*)[^\n]*$', re.MULTILINE)
_WORK_ID_PATTERN      = re.compile(r'^work_id\s*:\s*["\']?(\S+?)["\']?\s*$', re.MULTILINE)
_PRICE_FIND_PATTERN   = re.compile(r'^price\s*:\s*(\d+)', re.MULTILINE)
_FRONTMATTER_PATTERN  = re.compile(r'^---\n(.*?)\n---', re.DOTALL)


def log(msg: str, lf=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if lf:
        lf.write(line + "\n")
        lf.flush()


def get_work_id(content: str) -> str | None:
    m = _WORK_ID_PATTERN.search(content)
    return m.group(1) if m else None


def get_current_price(content: str) -> int | None:
    m = _PRICE_FIND_PATTERN.search(content)
    return int(m.group(1)) if m else None


def update_frontmatter(content: str, new_price: int, new_affiliate_url: str) -> str:
    """frontmatter の price / affiliate_url を更新または追加する"""
    fm_match = _FRONTMATTER_PATTERN.match(content)
    if not fm_match:
        return content

    fm_text = fm_match.group(1)
    rest    = content[fm_match.end():]

    # price フィールドを更新 or 追加
    if _PRICE_FIND_PATTERN.search(fm_text):
        fm_text = _PRICE_PATTERN.sub(rf'\g<1>{new_price}', fm_text)
    else:
        fm_text = fm_text.rstrip() + f"\nprice: {new_price}"

    # affiliate_url フィールドを更新 or 追加
    if _AFFILIATE_PATTERN.search(fm_text):
        fm_text = _AFFILIATE_PATTERN.sub(
            rf'\g<1>"{new_affiliate_url}"', fm_text
        )
    else:
        fm_text = fm_text.rstrip() + f'\naffiliate_url: "{new_affiliate_url}"'

    return f"---\n{fm_text}\n---{rest}"


def run_build_and_deploy(dry_run: bool, lf=None) -> bool:
    if dry_run:
        log("[DRY-RUN] npm run build && wrangler deploy をスキップ", lf)
        return True

    nvm_init = "source ~/.nvm/nvm.sh && nvm use 22"
    build_cmd = f"bash -c '{nvm_init} && cd {PROJECT_ROOT} && npm run build 2>&1'"
    log("npm run build を実行中...", lf)
    result = subprocess.run(build_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"[ERROR] build 失敗:\n{result.stdout}\n{result.stderr}", lf)
        return False
    log("build 完了", lf)

    deploy_cmd = (
        f"bash -c '{nvm_init} && cd {PROJECT_ROOT} && "
        f"npx wrangler pages deploy dist --project-name r18-blog "
        f"--commit-message \"chore: auto price update {datetime.now().strftime('%Y-%m-%d')}\" 2>&1'"
    )
    log("wrangler deploy を実行中...", lf)
    result = subprocess.run(deploy_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"[ERROR] deploy 失敗:\n{result.stdout}\n{result.stderr}", lf)
        return False
    log("deploy 完了", lf)
    return True


def main():
    parser = argparse.ArgumentParser(description="r18-blog 価格自動更新スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="ファイル更新・deploy をスキップ")
    args = parser.parse_args()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as lf:
        log("=== update_r18_prices.py 開始 ===", lf)

        md_files = sorted(POSTS_DIR.glob("*.md"))
        if not md_files:
            log("[WARN] posts が見つかりません", lf)
            return

        log(f"{len(md_files)} 本の記事を対象に確認します", lf)
        updated_count = 0
        skip_count    = 0
        error_count   = 0

        for md_path in md_files:
            content = md_path.read_text(encoding="utf-8")
            work_id = get_work_id(content)
            if not work_id:
                log(f"  SKIP (work_id なし): {md_path.name}", lf)
                skip_count += 1
                continue

            try:
                info = search_by_cid(work_id)
            except Exception as e:
                log(f"  [ERROR] {md_path.name} (work_id={work_id}): {e}", lf)
                error_count += 1
                continue

            if not info:
                log(f"  [WARN] API で見つからず: {md_path.name} (work_id={work_id})", lf)
                skip_count += 1
                continue

            new_price = info.get("price", 0)
            new_affiliate_url = info.get("affiliateURL") or make_affiliate_link(work_id)
            current_price = get_current_price(content)

            if current_price == new_price:
                log(f"  変更なし: {md_path.name} (price={new_price})", lf)
                skip_count += 1
                continue

            log(f"  価格更新: {md_path.name} {current_price} → {new_price} 円", lf)
            if not args.dry_run:
                new_content = update_frontmatter(content, new_price, new_affiliate_url)
                md_path.write_text(new_content, encoding="utf-8")
            updated_count += 1

        log(f"更新: {updated_count} 件 / スキップ: {skip_count} 件 / エラー: {error_count} 件", lf)

        if updated_count > 0:
            success = run_build_and_deploy(args.dry_run, lf)
            if success:
                log("✅ 価格更新・デプロイ完了", lf)
            else:
                log("❌ デプロイ失敗", lf)
                sys.exit(1)
        else:
            log("変更なし — デプロイ不要", lf)

        log("=== 正常終了 ===", lf)


if __name__ == "__main__":
    main()
