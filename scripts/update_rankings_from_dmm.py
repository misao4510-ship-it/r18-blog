#!/usr/bin/env python3
"""
DMM API 4ランキング取得 → rankings.json 保存 → build & deploy

ランキング種別:
  comic_monthly  : 同人コミック 月間TOP30 (sort=rank, 男性向け絞り込み)
  comic_daily    : 同人コミック 新着TOP30 (sort=date, 男性向け絞り込み)
  voice_monthly  : ボイス・TL 月間TOP30   (sort=rank, digital_doujin_tl)
  voice_daily    : ボイス・TL 新着TOP30   (sort=date, digital_doujin_tl)

コミックは男性向けジャンル絞り込み（BL/GL/女性向け除外）
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dmm_api_client import _request, _map_item_full

PROJECT_ROOT = Path(__file__).parent.parent
RANKINGS_JSON = PROJECT_ROOT / "data" / "rankings.json"

JST = timezone(timedelta(hours=9))

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


def _is_male_oriented(item_full: dict) -> bool:
    genre_ids = item_full.get("genre_ids", [])
    if genre_ids and EXCLUDE_GENRE_IDS.intersection(genre_ids):
        return False
    return True


def fetch_ranking(floor: str, category: str, sort: str = "rank", hits: int = 60, filter_male: bool = True) -> list:
    """指定フロアのランキング取得。filter_male=True なら男性向け絞り込み。"""
    params = {
        "site": "FANZA",
        "service": "doujin",
        "floor": floor,
        "sort": sort,
        "hits": hits,
        "offset": 1,
    }

    try:
        data = _request(params)
        items_raw = data.get("result", {}).get("items", [])
    except Exception as e:
        log(f"[WARN] {floor} sort={sort} 取得失敗: {e}")
        return []

    items = []
    for item in items_raw:
        mapped = _map_item_full(item, category)
        if filter_male and not _is_male_oriented(mapped):
            continue
        mapped["affiliateURL"] = mapped["affiliateURL"].replace("yukine0423-990", "yukine0423-002")
        items.append(mapped)

    log(f"{floor} sort={sort}: {len(items)} 件（raw {len(items_raw)} 件）")
    return items


def _to_ranking_item(rank: int, item: dict) -> dict:
    return {
        "rank": rank,
        "id": item["content_id"],
        "title": item["title"],
        "price": item.get("price_sale") or item.get("price_original") or 0,
        "price_original": item.get("price_original"),
        "price_sale": item.get("price_sale"),
        "discount_rate": item.get("discount_rate"),
        "is_on_sale": item.get("is_on_sale", False),
        "imageURL": item.get("imageURL", ""),
        "affiliateURL": item.get("affiliateURL", ""),
        "release_date": item.get("date", ""),
    }


def update_rankings() -> bool:
    comic_monthly_raw = fetch_ranking("digital_doujin",    "doujin", sort="rank", filter_male=True)
    comic_daily_raw   = fetch_ranking("digital_doujin",    "doujin", sort="date", filter_male=True)
    voice_monthly_raw = fetch_ranking("digital_doujin_tl", "voice",  sort="rank", filter_male=False)
    voice_daily_raw   = fetch_ranking("digital_doujin_tl", "voice",  sort="date", filter_male=False)

    def top30(items):
        return [_to_ranking_item(i + 1, item) for i, item in enumerate(items[:30])]

    rankings = {
        "comic_monthly": top30(comic_monthly_raw),
        "comic_daily":   top30(comic_daily_raw),
        "voice_monthly": top30(voice_monthly_raw),
        "voice_daily":   top30(voice_daily_raw),
        "updated_at":    datetime.now(JST).isoformat(),
    }

    RANKINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(RANKINGS_JSON, "w") as f:
        json.dump(rankings, f, ensure_ascii=False, indent=2)

    counts = {k: len(v) for k, v in rankings.items() if k != "updated_at"}
    log(f"rankings.json 更新完了: {counts}")
    return True


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
        'git -C /home/misao/r18-blog commit -m "cmd_323g: 4ランキング自動更新" && '
        "git -C /home/misao/r18-blog push origin main"
    )
    return True


def main():
    parser = argparse.ArgumentParser(description="DMM API 4ランキング更新")
    parser.add_argument("--no-deploy", action="store_true", help="rankings.json のみ更新")
    args = parser.parse_args()

    update_rankings()
    if args.no_deploy:
        log("--no-deploy: build/deploy スキップ")
    else:
        build_and_deploy()


if __name__ == "__main__":
    main()
