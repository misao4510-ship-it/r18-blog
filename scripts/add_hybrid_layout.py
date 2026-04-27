#!/usr/bin/env python3
"""
subtask_322b: 全記事に DMM作品画像×ゆきね横並び（.hybrid-thumb）を挿入する
購入リンクセクション（## 🛒 作品を試してみる）の直前に挿入。既存スキップ。
"""
import os
import re
import json
import urllib.request
import urllib.parse
import glob

POSTS_DIR = "/home/misao/r18-blog/src/content/posts"
DMM_API_ID = "sprDfWL0wSeW9sNDcDB4"
DMM_AFFILIATE_ID = "yukine0423-990"
YUKINE_IMG = "/images/yukine/standing.png"
PURCHASE_HEADING = "## 🛒 作品を試してみる"


def get_dmm_image_url(work_id: str) -> str | None:
    """DMM APIからlarge imageURLを取得。失敗時はNone。"""
    cid = work_id.replace("d_", "d_")
    params = urllib.parse.urlencode({
        "api_id": DMM_API_ID,
        "affiliate_id": DMM_AFFILIATE_ID,
        "site": "FANZA",
        "service": "doujin",
        "floor": "digital_doujin",
        "cid": cid,
        "output": "json",
    })
    url = f"https://api.dmm.com/affiliate/v3/ItemList?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        items = data.get("result", {}).get("items", [])
        if items:
            img = items[0].get("imageURL", {}).get("large")
            return img
    except Exception as e:
        print(f"  [API error] {work_id}: {e}")
    return None


def build_hybrid_html(img_src: str, alt: str) -> str:
    return (
        '<div class="hybrid-thumb">\n'
        f'  <img src="{img_src}" alt="{alt}" loading="lazy" />\n'
        f'  <img src="{YUKINE_IMG}" alt="ゆきねのおすすめ" loading="lazy" />\n'
        '</div>\n'
    )


def extract_frontmatter_value(content: str, key: str) -> str | None:
    m = re.search(rf'^{key}:\s*["\']?([^"\'\n]+)["\']?', content, re.MULTILINE)
    return m.group(1).strip() if m else None


def process_file(md_path: str) -> bool:
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "hybrid-thumb" in content:
        print(f"  [SKIP] already has hybrid-thumb: {os.path.basename(md_path)}")
        return False

    work_id = extract_frontmatter_value(content, "work_id")
    if not work_id:
        print(f"  [SKIP] no work_id: {os.path.basename(md_path)}")
        return False

    title = extract_frontmatter_value(content, "title") or work_id

    print(f"  processing {os.path.basename(md_path)} (work_id={work_id})")

    # DMM APIで画像URL取得
    img_src = get_dmm_image_url(work_id)
    if img_src:
        print(f"    API OK: {img_src[:60]}...")
    else:
        # フォールバック: /images/works/{work_id}/hero.png
        img_src = f"/images/works/{work_id}/hero.png"
        print(f"    API NG, fallback: {img_src}")

    hybrid_html = build_hybrid_html(img_src, title)

    # 購入リンク見出しの直前に挿入
    if PURCHASE_HEADING not in content:
        print(f"  [WARN] purchase heading not found: {os.path.basename(md_path)}")
        return False

    new_content = content.replace(
        PURCHASE_HEADING,
        hybrid_html + "\n" + PURCHASE_HEADING,
        1,
    )

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"    written OK")
    return True


def main():
    md_files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.md")))
    print(f"Found {len(md_files)} posts")
    updated = 0
    for path in md_files:
        if process_file(path):
            updated += 1
    print(f"\nDone. {updated}/{len(md_files)} files updated.")


if __name__ == "__main__":
    main()
