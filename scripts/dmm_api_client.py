#!/usr/bin/env python3
"""
DMM Affiliate API v3 クライアント
コンテンツIDで商品情報を取得し、アフィリエイトURLを生成する。

使い方:
  python3 scripts/dmm_api_client.py             # API接続テスト (d_540594)
  python3 scripts/dmm_api_client.py --cid d_540594
  python3 scripts/dmm_api_client.py --new-releases --hits 10
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("[ERROR] requests が必要です: pip install requests")
    sys.exit(1)

# ─── 設定読み込み ─────────────────────────────────────────────────────────────
_CONFIG = Path(__file__).parent.parent / "config" / "dmm_auth.env"

def _load_env():
    if _CONFIG.exists():
        with open(_CONFIG) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

DMM_API_BASE = "https://api.dmm.com/affiliate/v3/ItemList"
_DEFAULT_SITE    = "FANZA"
_DEFAULT_SERVICE = "digital"
_DEFAULT_FLOOR   = "videoa"


def _get_credentials():
    api_id = os.environ.get("DMM_API_ID", "")
    affiliate_id = os.environ.get("DMM_AFFILIATE_ID", "")
    if not api_id or not affiliate_id:
        raise RuntimeError(
            "DMM_API_ID / DMM_AFFILIATE_ID が未設定です。"
            f"{_CONFIG} を確認してください。"
        )
    return api_id, affiliate_id


# ─── 内部ユーティリティ ───────────────────────────────────────────────────────

def _parse_price(prices: dict) -> int:
    for key in ("price", "list_price"):
        val = prices.get(key)
        if val is not None:
            try:
                return int(str(val).replace(",", "").replace("円", ""))
            except (ValueError, TypeError):
                pass
    return 0


def _map_item(item: dict) -> dict:
    """DMM API レスポンス item → 内部辞書"""
    info = item.get("iteminfo", {})
    prices = item.get("prices", {})

    actresses_raw = info.get("actress", []) or info.get("voice_actress", []) or []
    actresses = [a["name"] for a in actresses_raw if isinstance(a, dict)]

    makers = info.get("maker", [])
    maker = makers[0]["name"] if makers else ""
    labels = info.get("label", [])
    label = labels[0]["name"] if labels else ""

    img = item.get("imageURL", {})
    sample_imgs = item.get("sampleImageURL", {})
    sample_list = []
    if isinstance(sample_imgs, dict):
        for key in ("sample_s", "sample_l"):
            val = sample_imgs.get(key)
            if isinstance(val, list):
                sample_list.extend(v.get("image", "") for v in val if isinstance(v, dict))
            elif isinstance(val, str) and val:
                sample_list.append(val)

    return {
        "content_id":        item.get("content_id", ""),
        "title":             item.get("title", ""),
        "price":             _parse_price(prices),
        "list_price":        _parse_price({"price": prices.get("list_price")}),
        "imageURL":          img.get("large", img.get("list", "")),
        "sampleImageURL":    sample_list,
        "actresses":         actresses,
        "maker":             maker,
        "label":             label,
        "affiliateURL":      item.get("affiliateURL", ""),
    }


def _request(params: dict) -> dict:
    api_id, affiliate_id = _get_credentials()
    params.update({
        "api_id":       api_id,
        "affiliate_id": affiliate_id,
        "output":       "json",
    })
    resp = requests.get(DMM_API_BASE, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ─── 公開 API ─────────────────────────────────────────────────────────────────

def search_by_cid(cid: str) -> dict:
    """コンテンツIDで1件検索して情報を返す。見つからなければ空辞書。"""
    data = _request({
        "site":    _DEFAULT_SITE,
        "service": _DEFAULT_SERVICE,
        "floor":   _DEFAULT_FLOOR,
        "cid":     cid,
        "hits":    1,
    })
    items = data.get("result", {}).get("items", [])
    if not items:
        return {}
    return _map_item(items[0])


def search_new_releases(floor: str = _DEFAULT_FLOOR, hits: int = 10) -> list:
    """新着作品を取得してリストで返す。"""
    data = _request({
        "site":    _DEFAULT_SITE,
        "service": _DEFAULT_SERVICE,
        "floor":   floor,
        "sort":    "date",
        "hits":    hits,
    })
    items = data.get("result", {}).get("items", [])
    return [_map_item(i) for i in items]


def make_affiliate_link(cid: str) -> str:
    """af_id 付きアフィリエイトURLを生成する。"""
    _, affiliate_id = _get_credentials()
    return f"https://al.dmm.co.jp/?lurl=https%3A%2F%2Fwww.dmm.co.jp%2Fdigital%2Fvideoa%2F-%2Fdetail%2F%3D%2Fcid%3D{cid}%2F&af_id={affiliate_id}&ch=link"


# ─── CLI テスト ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DMM API クライアント CLI")
    parser.add_argument("--cid", default="d_540594", help="コンテンツID (デフォルト: d_540594)")
    parser.add_argument("--new-releases", action="store_true", help="新着取得モード")
    parser.add_argument("--hits", type=int, default=5, help="新着取得件数")
    args = parser.parse_args()

    if args.new_releases:
        print(f"新着 {args.hits} 件を取得中...")
        works = search_new_releases(hits=args.hits)
        print(json.dumps(works, ensure_ascii=False, indent=2))
        print(f"\n取得件数: {len(works)} 件")
    else:
        cid = args.cid
        print(f"コンテンツID '{cid}' を検索中...")
        result = search_by_cid(cid)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            link = make_affiliate_link(cid)
            print(f"\nアフィリエイトURL: {link}")
        else:
            print(f"[WARN] '{cid}' が見つかりませんでした (floor=videoa)")
            print("同人フロア(doujin)の作品の場合はAPIパラメータを変更してください")

    print("\n✅ API接続テスト完了")


if __name__ == "__main__":
    main()
