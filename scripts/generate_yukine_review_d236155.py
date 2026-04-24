#!/usr/bin/env python3
"""
cmd_241: 雪音レビュー挿絵生成 (d_236155)
novaAnimeXL_ilV170 + kurokawa_v1 LoRA
作品: カレからワタシを奪ってみてよ♪ ～幼馴染の意地悪お姉ちゃん～【KU100】 / 陽向葵ゅか
"""
import requests
import base64
import json
import shutil
import sys
from pathlib import Path

SD_API = "http://172.18.208.1:7860"
OUTPUT_DIR = Path("/home/misao/r18-blog/public/images/works/d_236155")
OUTPUT_SD_DIR = Path("/mnt/c/tools/multi-agent-shogun/output_sd")

TARGET_MODEL = "novaAnimeXL_ilV170.safetensors"
RESTORE_MODEL = "waiIllustriousSDXL_v160.safetensors"

BASE_POSITIVE = (
    "masterpiece, best quality, amazing quality, absurdres, kurokawa style, soft lineart, thin outlines, "
    "digital painting, smooth shading, gradient shading, soft shadows, soft lighting, "
    "beautiful face, small face, slim face, v-shaped chin, gentle eyes, soft gaze, kind eyes, "
    "beautiful detailed eyes, detailed iris, eye reflection, vivid purple eyes, purple iris, violet eyes, "
    "beautiful hairstyle, beautiful skin, perfect body, "
    "1girl, solo, young woman, 20 years old, medium breasts, long straight hair, black brown hair, very dark hair, dark hair, "
    "elegant, youthful, ojou-sama, refined, <lora:kurokawa_v1:0.70>"
)

BASE_NEGATIVE = (
    "worst quality, low quality, blurry, bad anatomy, bad hands, extra fingers, missing fingers, "
    "2girls, 3girls, multiple girls, multiple people, "
    "nipples, nude, completely nude, exposed breasts, topless, "
    "oil painting, impasto, mature, old, elderly, wrinkles, "
    "silver hair, white hair, grey hair, blonde hair, "
    "purple hair, violet hair, blue hair, light brown hair, "
    "sharp eyes, glaring, angry eyes, blue eyes, green eyes, red eyes"
)

IMAGES = [
    {
        "name": "hero",
        "filename": "hero.png",
        "sd_filename": "yukine_review_d_236155_hero.png",
        "extra_positive": (
            "wearing in-ear headphones, slightly flustered expression, small blush, "
            "surprised look, hand near ear touching earphone, "
            "cozy indoor atmosphere, soft evening light, casual home outfit, "
            "sitting at desk, gentle confused expression, tilting head slightly"
        ),
    },
    {
        "name": "review",
        "filename": "review.png",
        "sd_filename": "yukine_review_d_236155_review.png",
        "extra_positive": (
            "arms crossed, thoughtful expression, thinking pose, "
            "soft smile, slightly skeptical look, finger on chin, "
            "casual outfit, indoor bookshelf background, warm lighting, "
            "pondering, analytical expression, refined posture"
        ),
    },
]


def get_current_model():
    resp = requests.get(f"{SD_API}/sdapi/v1/options", timeout=30)
    resp.raise_for_status()
    return resp.json().get("sd_model_checkpoint", "")


def set_model(model_name: str):
    print(f"  モデル切替 → {model_name}")
    resp = requests.post(
        f"{SD_API}/sdapi/v1/options",
        json={"sd_model_checkpoint": model_name},
        timeout=120,
    )
    resp.raise_for_status()


def generate_image(positive: str, negative: str, seed: int = -1) -> bytes:
    payload = {
        "prompt": positive,
        "negative_prompt": negative,
        "steps": 28,
        "sampler_name": "DPM++ 2M SDE Karras",
        "cfg_scale": 7,
        "width": 1024,
        "height": 1024,
        "seed": seed,
        "batch_size": 1,
    }
    resp = requests.post(f"{SD_API}/sdapi/v1/txt2img", json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    image_b64 = data["images"][0]
    return base64.b64decode(image_b64)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_SD_DIR.mkdir(parents=True, exist_ok=True)

    original_model = get_current_model()
    print(f"現在のモデル: {original_model}")

    try:
        set_model(TARGET_MODEL)

        for img_info in IMAGES:
            positive = BASE_POSITIVE + ", " + img_info["extra_positive"]
            print(f"\n生成中: {img_info['name']} ...")
            img_bytes = generate_image(positive, BASE_NEGATIVE)

            out_path = OUTPUT_DIR / img_info["filename"]
            sd_path = OUTPUT_SD_DIR / img_info["sd_filename"]

            out_path.write_bytes(img_bytes)
            shutil.copy2(out_path, sd_path)

            print(f"  保存: {out_path}")
            print(f"  保存: {sd_path}")

        print("\n全画像生成完了！")

    finally:
        restore = RESTORE_MODEL if original_model == TARGET_MODEL else original_model
        print(f"\nモデル戻し → {restore}")
        try:
            set_model(restore)
            print("モデル戻し完了")
        except Exception as e:
            print(f"警告: モデル戻し失敗 ({e})", file=sys.stderr)


if __name__ == "__main__":
    main()
