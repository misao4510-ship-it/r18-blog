#!/usr/bin/env python3
"""
DMM Web API v3 クライアント — FANZA同人作品データ取得スクリプト
data/works.json を更新する。

使い方:
  python3 scripts/fetch_fanza_works.py             # 通常モード (要 .env)
  python3 scripts/fetch_fanza_works.py --dry-run   # ダミーモード (APIキー不要)
  python3 scripts/fetch_fanza_works.py --keyword "作者名"  # キーワード絞り込み
  python3 scripts/fetch_fanza_works.py --max-hits 200      # 最大取得件数
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("[ERROR] requests ライブラリが必要です: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    # python-dotenv 未インストール時は os.environ から直接読む
    pass

# ─── 定数 ───────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
WORKS_JSON = DATA_DIR / "works.json"
MOCK_JSON = SCRIPT_DIR / "fanza_api_mock.json"
LOG_FILE = Path("/tmp/fanza_dry.log")

DMM_API_BASE = "https://api.dmm.com/affiliate/v3/ItemList"
HITS_PER_PAGE = 100
RATE_LIMIT_SLEEP = 0.5  # RPS制限対策 (秒)

# ─── ユーティリティ ──────────────────────────────────────────────────────────

def log(msg: str, file=None):
    """コンソールとファイルの両方に出力"""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if file:
        file.write(line + "\n")


def slugify(text: str) -> str:
    """日本語名 → ASCII スラッグ (簡易変換)"""
    text = unicodedata.normalize("NFKC", text)
    # ひらがな/カタカナ/漢字はローマ字変換できないので、
    # スペースと記号を除いた後ハイフン区切りにする簡易実装
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    text = text.strip("-").lower()
    return text or "unknown"


def parse_price(price_val) -> int:
    """価格文字列/数値を int に変換。失敗時は 0"""
    try:
        return int(str(price_val).replace(",", "").replace("円", ""))
    except (ValueError, TypeError):
        return 0


def parse_date(date_str: str) -> str:
    """日付文字列を YYYY-MM-DD に正規化"""
    if not date_str:
        return ""
    # "2026/01/15 00:00:00" → "2026-01-15"
    date_str = date_str.replace("/", "-").strip()
    return date_str[:10]


def parse_rating(review: dict) -> float | None:
    """review.average を float に変換"""
    try:
        val = float(review.get("average", 0) or 0)
        return round(val, 1) if val > 0 else None
    except (ValueError, TypeError):
        return None


def map_item_to_work(item: dict) -> dict:
    """
    DMM API レスポンス item → works.json エントリ

    フィールドマッピング:
      DMM API            | works.json      | メモ
      -------------------|-----------------|---------------------------
      content_id         | id              | 例 "d_123456"
      title              | title           |
      iteminfo.maker[0]  | author          | .name の先頭。複数時は先頭
      prices.price       | price           | int変換
      date               | release_date    | YYYY-MM-DD
      iteminfo.genre[]   | genres          | .name 配列
      imageURL.list      | thumbnail       | FANZA画像直リンク
      affiliateURL       | fanza_link      | アフィリエイトURL
      iteminfo.volume    | pages           | ページ数 (文字列→int, なければ null)
      review.average     | rating          | float, なければ null
      (新規追加)          | author_slug     | slugify(author)
      (固定)             | review_slug     | null (手動管理)
    """
    iteminfo = item.get("iteminfo", {})

    # 作者
    makers = iteminfo.get("maker", [])
    author = makers[0]["name"] if makers else "不明"
    author_slug = slugify(author)

    # ジャンル
    genres = [g["name"] for g in iteminfo.get("genre", [])]

    # 価格
    prices = item.get("prices", {})
    price = parse_price(prices.get("price", 0))

    # サムネイル
    image_url = item.get("imageURL", {})
    thumbnail = image_url.get("list", "") or image_url.get("large", "")

    # ページ数
    volume = iteminfo.get("volume")
    pages = int(volume) if volume and str(volume).isdigit() else None

    # 評価
    rating = parse_rating(item.get("review", {}))

    return {
        "id": item.get("content_id", ""),
        "title": item.get("title", ""),
        "author": author,
        "author_slug": author_slug,
        "price": price,
        "release_date": parse_date(item.get("date", "")),
        "genres": genres,
        "thumbnail": thumbnail,
        "fanza_link": item.get("affiliateURL", ""),
        "review_slug": None,
        "pages": pages,
        "rating": rating,
    }


# ─── API フェッチ ───────────────────────────────────────────────────────────

def fetch_from_api(api_id: str, affiliate_id: str, keyword: str = "", max_hits: int = 100) -> list[dict]:
    """DMM Web API v3 を叩いて全件取得する"""
    works = []
    offset = 1
    fetched = 0

    session = requests.Session()
    session.headers.update({"User-Agent": "FanzaWorksFetcher/1.0"})

    while True:
        hits = min(HITS_PER_PAGE, max_hits - fetched)
        if hits <= 0:
            break

        params = {
            "api_id": api_id,
            "affiliate_id": affiliate_id,
            "site": "FANZA",
            "service": "doujin",
            "floor": "digital_doujin",
            "hits": hits,
            "offset": offset,
            "sort": "date",
            "output": "json",
        }
        if keyword:
            params["keyword"] = keyword

        try:
            resp = session.get(DMM_API_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"[ERROR] API リクエスト失敗 (offset={offset}): {e}")
            break

        result = data.get("result", {})
        items = result.get("items", [])
        if not items:
            break

        for item in items:
            works.append(map_item_to_work(item))
        fetched += len(items)
        offset += len(items)

        total = result.get("total_count", 0)
        print(f"  取得中: {fetched}/{min(total, max_hits)} 件")

        if fetched >= max_hits or fetched >= total:
            break

        time.sleep(RATE_LIMIT_SLEEP)

    return works


def fetch_from_mock(log_file) -> list[dict]:
    """ダミーモード: fanza_api_mock.json からデータを読み込む"""
    log(f"ダミーモード: {MOCK_JSON} を使用", log_file)
    with open(MOCK_JSON, encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("result", {}).get("items", [])
    works = [map_item_to_work(item) for item in items]
    log(f"ダミーデータ {len(works)} 件を変換しました", log_file)
    return works


# ─── メイン ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="DMM Web API v3 から FANZA 同人作品データを取得して works.json を更新する"
    )
    parser.add_argument("--dry-run", action="store_true", help="ダミーモード (APIキー不要)")
    parser.add_argument("--keyword", default="", help="キーワード絞り込み (作者名・ジャンル等)")
    parser.add_argument("--max-hits", type=int, default=100, help="最大取得件数 (デフォルト: 100)")
    parser.add_argument("--no-backup", action="store_true", help="works.json のバックアップを作成しない")
    args = parser.parse_args()

    # ログファイルを開く
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as lf:
        log("=== fetch_fanza_works.py 開始 ===", lf)
        log(f"モード: {'ダミー' if args.dry_run else '通常'}", lf)

        # ─── APIキー確認 ──────────────────────────────────────────────
        api_id = os.environ.get("DMM_API_ID", "")
        affiliate_id = os.environ.get("DMM_AFFILIATE_ID", "")

        if not args.dry_run and (not api_id or not affiliate_id):
            log("⚠️  DMM_API_ID / DMM_AFFILIATE_ID が未設定のためダミーモードに切り替えます", lf)
            log("   .env を作成して DMM_API_ID と DMM_AFFILIATE_ID を設定してください", lf)
            args.dry_run = True

        # ─── データ取得 ───────────────────────────────────────────────
        if args.dry_run:
            new_works = fetch_from_mock(lf)
        else:
            log(f"DMM Web API v3 を叩きます (max_hits={args.max_hits})", lf)
            new_works = fetch_from_api(api_id, affiliate_id, args.keyword, args.max_hits)
            log(f"取得完了: {len(new_works)} 件", lf)

        if not new_works:
            log("[ERROR] 取得件数が 0 件です。処理を中断します", lf)
            sys.exit(1)

        # ─── バックアップ ─────────────────────────────────────────────
        if WORKS_JSON.exists() and not args.no_backup:
            bak_path = WORKS_JSON.with_suffix(".json.bak")
            shutil.copy2(WORKS_JSON, bak_path)
            log(f"バックアップ作成: {bak_path}", lf)

        # ─── works.json 上書き ───────────────────────────────────────
        output = {"works": new_works}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(WORKS_JSON, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        log(f"✅ {WORKS_JSON} を更新しました ({len(new_works)} 件)", lf)

        # ─── サマリー ─────────────────────────────────────────────────
        authors = list(dict.fromkeys(w["author"] for w in new_works))
        log(f"作者一覧 ({len(authors)} 名): {', '.join(authors[:10])}", lf)
        log(f"価格帯: {min(w['price'] for w in new_works)}〜{max(w['price'] for w in new_works)} 円", lf)
        log("=== 正常終了 ===", lf)

    print(f"\nログ: {LOG_FILE}")


if __name__ == "__main__":
    main()
