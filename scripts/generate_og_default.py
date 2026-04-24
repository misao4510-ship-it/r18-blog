#!/usr/bin/env python3
"""
OGPデフォルト画像生成スクリプト
雪音立ち絵 + サイト名で1200x630のOGP画像を生成する
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# パス設定
REPO_ROOT = Path(__file__).parent.parent
STANDING_IMG = Path("/mnt/c/tools/multi-agent-shogun/output_sd/yukine_standing_final.png")
OUTPUT_PATH = REPO_ROOT / "public" / "images" / "og" / "og-default.png"
FONT_PATH = Path("/mnt/c/Windows/Fonts/NotoSansJP-VF.ttf")

# OGP画像サイズ (Twitter summary_large_image推奨)
WIDTH = 1200
HEIGHT = 630

# カラー設定
BG_COLOR = (13, 13, 26)       # #0d0d1a
TITLE_COLOR = (232, 213, 255)  # #e8d5ff
TAGLINE_COLOR = (160, 100, 220)  # パープル系
ACCENT_COLOR = (224, 64, 251)   # #e040fb
MOON_COLOR = (255, 240, 180)    # 月の色


def draw_stars(draw, width, height):
    """背景に星を散りばめる"""
    import random
    random.seed(42)
    for _ in range(80):
        x = random.randint(0, width)
        y = random.randint(0, height)
        size = random.choice([1, 1, 1, 2])
        alpha = random.randint(100, 220)
        draw.ellipse([x - size, y - size, x + size, y + size],
                     fill=(255, 255, 255, alpha))


def load_font(path, size):
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        print(f"Warning: フォント {path} を読み込めません。デフォルトフォントを使用します。", file=sys.stderr)
        return ImageFont.load_default()


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ベース画像（RGBAで作業してからRGBに変換）
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img, "RGBA")

    # 星の描画
    draw_stars(draw, WIDTH, HEIGHT)

    # グラデーション風オーバーレイ（右側を少し明るく）
    for x in range(WIDTH // 2, WIDTH):
        alpha = int(15 * (x - WIDTH // 2) / (WIDTH // 2))
        draw.line([(x, 0), (x, HEIGHT)], fill=(100, 50, 150, alpha))

    # 雪音立ち絵の配置（左寄り、中央縦）
    if STANDING_IMG.exists():
        standing = Image.open(STANDING_IMG).convert("RGBA")
        # 高さ600pxにリサイズ
        target_h = 600
        ratio = target_h / standing.height
        target_w = int(standing.width * ratio)
        standing = standing.resize((target_w, target_h), Image.LANCZOS)

        # 左寄り中央に配置（x=60, y中央揃え）
        x_pos = 60
        y_pos = (HEIGHT - target_h) // 2
        img.paste(standing, (x_pos, y_pos), standing)
        print(f"立ち絵配置: {target_w}x{target_h} at ({x_pos}, {y_pos})")
    else:
        print(f"Warning: 立ち絵が見つかりません: {STANDING_IMG}", file=sys.stderr)

    # テキスト描画
    draw = ImageDraw.Draw(img, "RGBA")

    # テキスト開始X位置（立ち絵の右側）
    text_x = 480

    # サイト名「🌙 月灯の書架」
    font_title = load_font(FONT_PATH, 72)
    title_text = "月灯の書架"
    draw.text((text_x, 160), "🌙", font=load_font(FONT_PATH, 60), fill=MOON_COLOR)
    draw.text((text_x + 80, 155), title_text, font=font_title, fill=TITLE_COLOR)

    # アクセントライン
    draw.rectangle([text_x, 260, text_x + 580, 263], fill=ACCENT_COLOR)

    # タグライン
    font_tag = load_font(FONT_PATH, 32)
    tagline = "白鳥雪音がお届けする、"
    tagline2 = "大人のための作品ガイド"
    draw.text((text_x, 290), tagline, font=font_tag, fill=TAGLINE_COLOR)
    draw.text((text_x, 340), tagline2, font=font_tag, fill=TAGLINE_COLOR)

    # サブテキスト
    font_sub = load_font(FONT_PATH, 24)
    draw.text((text_x, 430), "厳選R18同人作品の詳細レビュー", font=font_sub, fill=(180, 150, 210))
    draw.text((text_x, 468), "18歳以上限定", font=font_sub, fill=(255, 77, 141))

    # RGBに変換して保存
    img_rgb = img.convert("RGB")
    img_rgb.save(str(OUTPUT_PATH), "PNG", optimize=True)
    print(f"OGP画像生成完了: {OUTPUT_PATH}")
    print(f"サイズ: {WIDTH}x{HEIGHT}px")


if __name__ == "__main__":
    main()
