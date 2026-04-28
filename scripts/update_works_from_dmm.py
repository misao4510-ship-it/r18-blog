#!/usr/bin/env python3
"""
DMM API 2カテゴリ取得 → works.json + rankings.json 自動更新 → build & deploy

処理:
  1. doujin / voice 各 300 件を sort=rank（人気順）で DMM API から取得
  2. 既存 works.json から adult_book・dsample-* を除外
  3. 既存 doujin/voice エントリと content_id でマージ（review_slug / fanza_link は保持）
  4. 4ランキング(コミック/ボイス×月間/24h)を rankings.json に保存
  5. レビュー記事 frontmatter の voice_actresses を works.json に転記
  6. 変更があれば npm run build → wrangler deploy (--branch=main) → git push

使い方:
  python3 scripts/update_works_from_dmm.py
  python3 scripts/update_works_from_dmm.py --no-deploy   # works.json のみ更新
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dmm_api_client import get_doujin, get_voice, _request

PROJECT_ROOT = Path(__file__).parent.parent
WORKS_JSON = PROJECT_ROOT / "data" / "works.json"
RANKINGS_JSON = PROJECT_ROOT / "data" / "rankings.json"

# doujin floor (digital_doujin) 除外ジャンルID: 乙女受け/乙女向け/女性向け/BL/百合/レズビアン
EXCLUDE_GENRE_IDS: set[int] = {155011, 160026, 156006, 558, 153030, 4013}

# voice floor (digital_doujin_tl) 除外ジャンルID: BL/百合/レズビアンのみ
# digital_doujin_tl は TL（ティーンズラブ）フロアで全件 156006(女性向け) が付くため
# 女性向け系IDを除外すると全件0件になる。BL系のみ最小限除外する。
VOICE_EXCLUDE_GENRE_IDS: set[int] = {558, 153030, 4013}


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
    excluded_cids: set[str] = set()

    for fetch_fn, category in [
        (get_doujin, "doujin"),
        (get_voice,  "voice"),
    ]:
        # voiceはdigital_doujin_tl（TL）フロアのため女性向け除外なし、BLのみ除外
        exclude_ids = VOICE_EXCLUDE_GENRE_IDS if category == "voice" else EXCLUDE_GENRE_IDS
        items = fetch_category_300(fetch_fn, category)
        log(f"{category}: 合計 {len(items)} 件")

        for item in items:
            cid = item.get("content_id", "")
            if not cid:
                continue

            # ジャンル除外: genre_ids が空なら通過（ジャンル情報なし作品は除外しない）
            item_genre_ids = item.get("genre_ids", [])
            if item_genre_ids and exclude_ids.intersection(item_genre_ids):
                excluded_cids.add(cid)  # works.json から削除対象としてマーク
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

    # BL/女性向けとして検出されたアイテムを works.json から削除
    if excluded_cids:
        before_count = len(works)
        works = [w for w in works if w.get("id") not in excluded_cids]
        removed = before_count - len(works)
        log(f"BL/女性向け除外: {removed} 件削除 ({before_count} → {len(works)} 件)")
        # existing_by_cid も更新
        for cid in excluded_cids:
            existing_by_cid.pop(cid, None)

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


def _parse_ranking_item(item: dict, rank: int) -> dict:
    """DMM APIアイテム → ランキングエントリ"""
    prices = item.get("prices", {})
    def to_int(val):
        if val is None:
            return None
        try:
            return int(str(val).replace(",", "").replace("円", ""))
        except (ValueError, TypeError):
            return None

    price_sale = to_int(prices.get("price"))
    price_original = to_int(prices.get("list_price")) or price_sale
    is_on_sale = bool(price_sale and price_original and price_original > price_sale)
    discount_rate = int((1 - price_sale / price_original) * 100) if is_on_sale and price_original else None
    img = item.get("imageURL", {})
    af_url = item.get("affiliateURL", "").replace("yukine0423-990", "yukine0423-002")
    return {
        "rank":          rank,
        "id":            item.get("content_id", ""),
        "title":         item.get("title", ""),
        "price":         price_sale or price_original or 0,
        "price_original": price_original,
        "price_sale":    price_sale,
        "discount_rate": discount_rate,
        "is_on_sale":    is_on_sale,
        "imageURL":      img.get("large", img.get("list", "")) if isinstance(img, dict) else "",
        "affiliateURL":  af_url,
        "release_date":  (item.get("date", "") or "")[:10],
    }


VOICE_RANKING_FLOOR = "digital_doujin_tl"


def _fetch_ranking_raw(floor: str, hits: int = 30, gte_date: str = None) -> list:
    """_request 直接使用でランキング取得（raw DMM APIレスポンスアイテム）。BL/女性向け除外フィルタ適用。"""
    # voiceフロア(digital_doujin_tl)はTL全件156006(女性向け)のためBL除外のみ適用
    exclude_ids = VOICE_EXCLUDE_GENRE_IDS if floor == VOICE_RANKING_FLOOR else EXCLUDE_GENRE_IDS
    api_hits = hits if gte_date else min(hits * 3, 90)  # gte_date使用時はhitsをそのまま使用（API制限回避）
    params = {
        "site": "FANZA", "service": "doujin",
        "floor": floor, "sort": "rank", "hits": api_hits, "offset": 1,
    }
    if gte_date:
        params["gte_date"] = gte_date
    try:
        data = _request(params)
        items = data.get("result", {}).get("items", [])
        # ジャンル除外フィルタ
        filtered = []
        for item in items:
            info = item.get("iteminfo", {})
            genres_raw = info.get("genre", []) or []
            genre_ids = {int(g["id"]) for g in genres_raw if isinstance(g, dict) and "id" in g}
            if genre_ids and exclude_ids.intersection(genre_ids):
                continue
            filtered.append(item)
        return [_parse_ranking_item(item, i+1) for i, item in enumerate(filtered[:hits])]
    except Exception as e:
        log(f"[WARN] ランキング取得失敗 floor={floor}: {e}")
        return []


def update_rankings() -> None:
    """4ランキング(コミック/ボイス×月間/24h)を rankings.json に保存"""
    jst = timezone(timedelta(hours=9))
    yesterday = (datetime.now(jst) - timedelta(days=1)).strftime("%Y-%m-%d")

    log("=== ランキング更新開始 ===")

    comic_monthly = _fetch_ranking_raw("digital_doujin", hits=30)
    log(f"コミック月間: {len(comic_monthly)} 件")

    comic_daily = _fetch_ranking_raw("digital_doujin", hits=30, gte_date=yesterday)
    if not comic_daily:
        log("[WARN] コミック24h件数0、月間で代替")
        comic_daily = comic_monthly[:]
    log(f"コミック24h: {len(comic_daily)} 件")

    voice_monthly = _fetch_ranking_raw("digital_doujin_tl", hits=30)
    log(f"ボイス月間: {len(voice_monthly)} 件")

    voice_daily = _fetch_ranking_raw("digital_doujin_tl", hits=30, gte_date=yesterday)
    if not voice_daily:
        log("[WARN] ボイス24h件数0、月間で代替")
        voice_daily = voice_monthly[:]
    log(f"ボイス24h: {len(voice_daily)} 件")

    rankings = {
        "comic_monthly": comic_monthly,
        "comic_daily":   comic_daily,
        "voice_monthly": voice_monthly,
        "voice_daily":   voice_daily,
        "updated_at":    datetime.now(jst).isoformat(),
    }
    with open(RANKINGS_JSON, "w") as f:
        json.dump(rankings, f, ensure_ascii=False, indent=2)
    log(f"rankings.json 保存完了 (各カテゴリ最大30件)")


def sync_voice_actresses_from_posts(works_list: list) -> list:
    """レビュー記事 frontmatter の voice_actresses を works.json に転記。
    未登録レビュー作品は最小エントリで追加する。"""
    post_dir = Path('/home/misao/r18-blog/src/content/posts')
    va_map: dict[str, list[str]] = {}
    meta_map: dict[str, dict] = {}

    for md in post_dir.glob('*.md'):
        content = md.read_text(encoding='utf-8')
        m_id = re.search(r'^work_id:\s*["\']?([^"\'\n]+)["\']?', content, re.M)
        m_va = re.search(r'^voice_actresses:\s*\[([^\]]*)\]', content, re.M)
        m_title = re.search(r'^title:\s*["\'](.+?)["\']', content, re.M)
        m_fanza = re.search(r'https://al\.fanza\.co\.jp/[^\s)]+', content)
        if m_id:
            wid = m_id.group(1).strip()
            vas = []
            if m_va and m_va.group(1).strip():
                vas = [v.strip().strip('"\'') for v in m_va.group(1).split(',') if v.strip().strip('"\'')]
            va_map[wid] = vas
            meta_map[wid] = {
                'title': m_title.group(1) if m_title else '',
                'fanza_link': m_fanza.group(0) if m_fanza else '',
                'review_slug': md.stem,
            }

    existing_ids = {w.get('id', '') for w in works_list}

    for w in works_list:
        wid = w.get('id', '')
        if wid in va_map:
            w['voice_actresses'] = va_map[wid]
            if meta_map[wid].get('review_slug'):
                w.setdefault('review_slug', meta_map[wid]['review_slug'])

    # 未登録のレビュー作品を追加
    for wid, vas in va_map.items():
        if wid not in existing_ids:
            meta = meta_map[wid]
            new_entry = {
                'id': wid,
                'title': meta['title'],
                'author': '',
                'author_slug': '',
                'price': 0,
                'release_date': '',
                'genres': [],
                'thumbnail': '',
                'fanza_link': meta['fanza_link'],
                'review_slug': meta['review_slug'],
                'voice_actresses': vas,
                'category': 'voice',
                'price_original': None,
                'price_sale': None,
                'discount_rate': None,
                'sale_end_date': None,
                'is_on_sale': False,
            }
            works_list.append(new_entry)
            log(f"review作品を追加: {wid} ({meta['title'][:30]})")

    log(f"voice_actresses転記完了: {len(va_map)} 件のレビュー記事を処理")
    return works_list


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
        'git -C /home/misao/r18-blog commit -m "cron: works.json + rankings.json 自動更新" && '
        "git -C /home/misao/r18-blog push origin main"
    )
    return True


def main():
    parser = argparse.ArgumentParser(description="DMM API works.json + rankings.json 自動更新")
    parser.add_argument("--no-deploy", action="store_true", help="works.json のみ更新（build/deploy スキップ）")
    parser.add_argument("--rankings-only", action="store_true", help="rankings.json のみ更新（works.json スキップ）")
    args = parser.parse_args()

    if args.rankings_only:
        update_rankings()
        if not args.no_deploy:
            build_and_deploy()
        return

    changed = update_works()
    update_rankings()
    # レビュー記事の voice_actresses を works.json に転記
    if WORKS_JSON.exists():
        with open(WORKS_JSON) as f:
            data = json.load(f)
        data['works'] = sync_voice_actresses_from_posts(data['works'])
        with open(WORKS_JSON, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    if args.no_deploy:
        log("--no-deploy: build/deploy スキップ")
    else:
        build_and_deploy()


if __name__ == "__main__":
    main()
