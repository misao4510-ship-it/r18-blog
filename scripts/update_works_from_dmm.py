#!/usr/bin/env python3
"""
DMM API 3カテゴリ取得 → works.json 自動更新 → build & deploy

処理:
  1. doujin / adult_book / voice 各 50 件を DMM API から取得
  2. 既存 works.json と content_id でマージ（review_slug / fanza_link は保持）
  3. 新着エントリを追加（review_slug=null）
  4. 変更があれば npm run build → wrangler deploy → git push

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
from dmm_api_client import get_doujin, get_adult_book, get_voice

PROJECT_ROOT = Path(__file__).parent.parent
WORKS_JSON = PROJECT_ROOT / "data" / "works.json"


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


def update_works() -> bool:
    if WORKS_JSON.exists():
        with open(WORKS_JSON) as f:
            data = json.load(f)
    else:
        data = {"works": []}

    works = data["works"]

    # Build index by content_id (dsample- エントリはスキップ)
    existing_by_cid: dict = {
        w["id"]: w for w in works if not w.get("id", "").startswith("dsample")
    }

    new_count = 0
    updated_count = 0

    for fetch_fn, category in [
        (get_doujin,     "doujin"),
        (get_adult_book, "adult_book"),
        (get_voice,      "voice"),
    ]:
        try:
            items = fetch_fn(hits=50)
            log(f"{category}: {len(items)} 件取得")
        except Exception as e:
            log(f"[WARN] {category} 取得失敗: {e}")
            items = []

        for item in items:
            cid = item.get("content_id", "")
            if not cid:
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

    # 既存エントリに新フィールドのデフォルト値を保証
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

    log(f"works.json 更新完了: +{new_count} 新規, {updated_count} 更新, 合計 {len(works)} 件")
    return new_count + updated_count > 0


def build_and_deploy() -> bool:
    log("=== build 開始 ===")
    if not run("source ~/.nvm/nvm.sh && nvm use 22 && npm run build"):
        log("[ERROR] build 失敗")
        return False

    log("=== deploy 開始 ===")
    if not run("source ~/.nvm/nvm.sh && nvm use 22 && npx wrangler pages deploy dist --project-name=r18-blog"):
        log("[ERROR] deploy 失敗")
        return False

    run(
        "git -C /home/misao/r18-blog add -A && "
        'git -C /home/misao/r18-blog commit -m "chore: update works.json from DMM API" && '
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
