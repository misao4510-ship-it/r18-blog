#!/usr/bin/env python3
"""
DMM API 2カテゴリ取得 → works.json 自動更新 → build & deploy

処理:
  1. doujin / voice 各 300 件を sort=rank（人気順）で DMM API から取得
     （hits=100 × offset 3ページで計300件）
  2. 既存 works.json から adult_book・dsample-* を除外
  3. 既存 doujin/voice エントリと content_id でマージ（review_slug / fanza_link は保持）
  4. 変更があれば npm run build → wrangler deploy (--branch=main) → git push

使い方:
  python3 scripts/update_works_from_dmm.py
  python3 scripts/update_works_from_dmm.py --no-deploy   # works.json のみ更新
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dmm_api_client import get_doujin, get_voice

PROJECT_ROOT = Path(__file__).parent.parent
WORKS_JSON = PROJECT_ROOT / "data" / "works.json"

# 女性向け除外ジャンルID (GenreSearch floor_id=81 で特定: 乙女受け/乙女向け/女性向け/BL/百合/レズビアン)
EXCLUDE_GENRE_IDS: set[int] = {155011, 160026, 156006, 558, 153030, 4013}


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run(cmd: str) -> bool:
    log(f"$ {cmd}")
    r = subprocess.run(
        ["bash", "-c", cmd],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if r.stdout:
        print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    return r.returncode == 0


def fetch_category_300(fetch_fn, category: str) -> list:
    """hits=100 × 3ページ（offset 1/101/201）で最大300件取得"""
    items = []
    for page_offset in [0, 100, 200]:
        try:
            batch = fetch_fn(hits=100, offset=page_offset + 1, sort="rank")
            log(f"{category} offset={page_offset+1}: {len(batch)} 件取得")
            items.extend(batch)
            if len(batch) < 100:
                break
        except Exception as e:
            log(f"[WARN] {category} offset={page_offset+1} 取得失敗: {e}")
            break
    return items


def update_works() -> bool:
    if WORKS_JSON.exists():
        with open(WORKS_JSON) as f:
            data = json.load(f)
    else:
        data = {"works": []}

    works = data["works"]

    # adult_book・dsample-* を除外してクリーンな既存エントリ一覧を作成
    works = [
        w for w in works
        if w.get("category", "doujin") != "adult_book"
        and not w.get("id", "").startswith("dsample")
    ]

    existing_by_cid: dict = {w["id"]: w for w in works}

    new_count = 0
    updated_count = 0

    for fetch_fn, category in [
        (get_doujin, "doujin"),
        (get_voice,  "voice"),
    ]:
        items = fetch_category_300(fetch_fn, category)
        log(f"{category}: 合計 {len(items)} 件")

        for item in items:
            cid = item.get("content_id", "")
            if not cid:
                continue

            # 女性向けジャンル除外: genre_ids が空なら通過（ジャンル情報なし作品は除外しない）
            item_genre_ids = item.get("genre_ids", [])
            if item_genre_ids and EXCLUDE_GENRE_IDS.intersection(item_genre_ids):
                continue

            sale_fields = {
                "category":       item["category"],
                "price_original": item["price_original"],
                "price_sale":     item["price_sale"],
                "discount_rate":  item["discount_rate"],
                "sale_end_date":  None,
                "is_on_sale":     item["is_on_sale"],
            }

            if cid in existing_by_cid:
                existing_by_cid[cid].update(sale_fields)
                updated_count += 1
            else:
                new_entry = {
                    "id":           cid,
                    "title":        item["title"],
                    "author":       "",
                    "author_slug":  "",
                    "price":        item["price_sale"] or item["price_original"] or 0,
                    "release_date": item.get("date", ""),
                    "genres":       [],
                    "thumbnail":    item.get("imageURL", ""),
                    "fanza_link":   item.get("affiliateURL", "").replace("yukine0423-990", "yukine0423-002"),
                    "review_slug":  None,
                    **sale_fields,
                }
                works.append(new_entry)
                existing_by_cid[cid] = new_entry
                new_count += 1

    # 既存エントリのデフォルト値保証
    for w in works:
        w.setdefault("category",       "doujin")
        w.setdefault("price_original", None)
        w.setdefault("price_sale",     None)
        w.setdefault("discount_rate",  None)
        w.setdefault("sale_end_date",  None)
        w.setdefault("is_on_sale",     False)

    data["works"] = works
    with open(WORKS_JSON, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    sale_count = sum(1 for w in works if w.get("is_on_sale"))
    log(f"works.json 更新完了: +{new_count} 新規, {updated_count} 更新, 合計 {len(works)} 件, セール {sale_count} 件")
    return new_count + updated_count > 0


def build_and_deploy() -> bool:
    log("=== build 開始 ===")
    if not run("source ~/.nvm/nvm.sh && nvm use 22 && npm run build"):
        log("[ERROR] build 失敗")
        return False

    log("=== deploy 開始 ===")
    if not run("source ~/.nvm/nvm.sh && nvm use 22 && npx wrangler pages deploy dist --project-name=r18-blog --branch=main"):
        log("[ERROR] deploy 失敗")
        return False

    run(
        "git -C /home/misao/r18-blog add -A && "
        'git -C /home/misao/r18-blog commit -m "cmd_323f: 男性向け同人絞り込み（BL/GL/女性向け除外）" && '
        "git -C /home/misao/r18-blog push origin main"
    )
    return True


def main():
    parser = argparse.ArgumentParser(description="DMM API works.json 自動更新")
    parser.add_argument("--no-deploy", action="store_true", help="works.json のみ更新（build/deploy スキップ）")
    args = parser.parse_args()

    changed = update_works()
    if args.no_deploy:
        log("--no-deploy: build/deploy スキップ")
    elif changed:
        build_and_deploy()
    else:
        log("変更なし: build/deploy スキップ")


if __name__ == "__main__":
    main()
