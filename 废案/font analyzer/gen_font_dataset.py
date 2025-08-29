#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_font_dataset.py

离线生成字体模板数据集（不包含 ROI）。

用法示例:
  python gen_font_dataset.py --font MyFont.ttf --out ocr_font_dataset --heights 12 16 22 32 --perturb 6 --highsz 96

依赖:
  pip install pillow opencv-python numpy
"""
import os
import argparse
import json
import datetime
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import numpy as np
import cv2
import pypinyin

# ---------------- config defaults ----------------
DEFAULT_CHARS = list("0123456789:/")
DEFAULT_WORDS = ["暂停"]

# ---------------- utilities ----------------
def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def pil_to_cv_gray(img_pil):
    arr = np.array(img_pil)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return arr

def binarize_invert(arr_gray):
    # produce foreground=255, background=0
    if arr_gray.dtype != np.uint8:
        arr_gray = arr_gray.astype(np.uint8)
    _, th = cv2.threshold(arr_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return th

def save_png(path, arr):
    ensure_dir(os.path.dirname(path))
    cv2.imwrite(path, arr)
    
    
def is_chinese_char(char):
    """判断一个字符是否为汉字"""
    if '\u4e00' <= char <= '\u9fff':
        return True
    return False

def safe_filename_char(ch):
    """把字符转为安全的文件名字符"""
    if is_chinese_char(ch):
        return ''.join(pypinyin.lazy_pinyin(ch))
    if ch == ':':
        return 'colon'
    if ch == '/':
        return 'slash'
    if ch == '\\':
        return 'backslash'
    return ch
# ---------------- rendering ----------------
def render_high_res_text(text, font_path, high_sz=96, pad=12):
    """Return PIL grayscale image rendered at high size"""
    font = ImageFont.truetype(font_path, high_sz)

    ascent, descent = font.getmetrics()
    w, _ = font.getmask(text).size
    h = ascent + descent

    im = Image.new("L", (w + pad*2, h + pad*2), 255)  # white bg
    draw = ImageDraw.Draw(im)
    draw.text((pad, pad), text, font=font, fill=0)  # black text

    # 去掉多余空白，防止顶部/底部被截
    im = im.crop(im.getbbox())
    return im

# ---------------- perturbations ----------------
def perturb_blur(img):
    k = random.choice([1, 3])
    if k <= 1:
        return img
    return cv2.GaussianBlur(img, (k, k), 0)

def perturb_noise(img, var=8):
    if var <= 0:
        return img
    noise = np.random.normal(0, var, img.shape).astype(np.float32)
    out = img.astype(np.float32) + noise
    out = np.clip(out, 0, 255).astype(np.uint8)
    return out

def perturb_translate(img, max_trans=2):
    tx = random.randint(-max_trans, max_trans)
    ty = random.randint(-max_trans, max_trans)
    M = np.float32([[1, 0, tx], [0, 1, ty]])
    out = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderValue=0)
    return out

def perturb_rotate(img, max_angle=2.0):
    ang = random.uniform(-max_angle, max_angle)
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w/2, h/2), ang, 1.0)
    out = cv2.warpAffine(img, M, (w, h), borderValue=0)
    return out

def perturb_morph(img):
    op = random.choice(['none', 'dilate', 'erode'])
    k = random.choice([1, 2])
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    if op == 'dilate':
        return cv2.dilate(img, ker)
    elif op == 'erode':
        return cv2.erode(img, ker)
    return img

def perturb_contrast_brightness(pil_img):
    # PIL image in 'L' mode
    if random.random() < 0.4:
        enh = ImageEnhance.Brightness(pil_img)
        pil_img = enh.enhance(random.uniform(0.9, 1.1))
    if random.random() < 0.4:
        enh = ImageEnhance.Contrast(pil_img)
        pil_img = enh.enhance(random.uniform(0.9, 1.15))
    return pil_img

def apply_random_perturbations(bin_img, pil_original=None):
    img = bin_img.copy()
    if pil_original is not None and random.random() < 0.35:
        pil_mod = perturb_contrast_brightness(pil_original)
        arr = pil_to_cv_gray(pil_mod)
        img = binarize_invert(arr)
    if random.random() < 0.7:
        img = perturb_blur(img)
    if random.random() < 0.6:
        img = perturb_noise(img)
    if random.random() < 0.6:
        img = perturb_translate(img)
    if random.random() < 0.5:
        img = perturb_rotate(img)
    if random.random() < 0.4:
        img = perturb_morph(img)
    _, final = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
    return final

# ---------------- main generation ----------------
def gen_font_dataset(font_path, out_dir, heights, perturb_count=6, high_sz=96, pad=12, chars=None, words=None):
    out_dir = Path(out_dir)
    templates_dir = out_dir / "templates"
    words_dir = out_dir / "words"
    ensure_dir(templates_dir)
    ensure_dir(words_dir)

    chars = chars if chars is not None else DEFAULT_CHARS
    words = words if words is not None else DEFAULT_WORDS

    manifest = []
    # single chars
    for ch in chars:
        pil_high = render_high_res_text(ch, font_path, high_sz=high_sz, pad=pad)
        for h in heights:
            w_new = max(1, int(pil_high.width * (h / pil_high.height)))
            pil_rs = pil_high.resize((w_new, h), resample=Image.LANCZOS)
            arr = pil_to_cv_gray(pil_rs)
            base_bin = binarize_invert(arr)

            safe_ch = safe_filename_char(ch)
            fname_base = f"{safe_ch}_{h}.png"
            pbase = templates_dir / str(h) / fname_base
            save_png(str(pbase), base_bin)
            manifest.append({"path": str(pbase.relative_to(out_dir)), "label": ch, "height": h, "perturb": False})

            for i in range(perturb_count):
                pert = apply_random_perturbations(base_bin, pil_original=pil_rs)
                fname_p = f"{safe_ch}_{h}_p{i}.png"
                pp = templates_dir / str(h) / fname_p
                save_png(str(pp), pert)
                manifest.append({"path": str(pp.relative_to(out_dir)), "label": ch, "height": h, "perturb": True})

    
    # word templates
    for wtext in words:
        pil_high = render_high_res_text(wtext, font_path, high_sz=high_sz, pad=pad)
        # 将每个字符安全化并拼接作文件名
        safe_name = ''.join([safe_filename_char(c) for c in wtext])
        for h in heights:
            w_new = max(1, int(pil_high.width * (h / pil_high.height)))
            pil_rs = pil_high.resize((w_new, h), resample=Image.LANCZOS)
            arr = pil_to_cv_gray(pil_rs)
            base_bin = binarize_invert(arr)

            fname_base = f"{safe_name}_{h}.png"
            pbase = words_dir / str(h) / fname_base
            save_png(str(pbase), base_bin)
            manifest.append({
                "path": str(pbase.relative_to(out_dir)),
                "label": wtext,
                "height": h,
                "word": True,
                "perturb": False
            })

            # perturbations
            for i in range(perturb_count):
                pert = apply_random_perturbations(base_bin, pil_original=pil_rs)
                fname_p = f"{safe_name}_{h}_p{i}.png"
                pp = words_dir / str(h) / fname_p
                save_png(str(pp), pert)
                manifest.append({
                    "path": str(pp.relative_to(out_dir)),
                    "label": wtext,
                    "height": h,
                    "word": True,
                    "perturb": True
                })

    # metadata
    meta = {
        "generator": "gen_font_dataset.py",
        "font": os.path.basename(font_path),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "heights": heights,
        "chars": chars,
        "words": words,
        "perturb_count_each": perturb_count,
        "high_render_size": high_sz,
        "notes": "binary images: foreground=255 (white), background=0 (black). No ROI data included."
    }
    with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"Done. Templates saved to: {out_dir}")
    print("metadata:", out_dir / "metadata.json")
    print("manifest:", out_dir / "manifest.json")
    return out_dir

# ---------------- CLI ----------------
def parse_args():
    p = argparse.ArgumentParser(description="Generate font template dataset (no ROI).")
    p.add_argument("--font", "-f", required=True, help="Path to TTF/OTF font file")
    p.add_argument("--out", "-o", default="ocr_font_dataset", help="Output directory")
    p.add_argument("--heights", "-H", nargs="+", type=int, default=[12, 16, 22, 32], help="Target heights (px)")
    p.add_argument("--perturb", "-p", type=int, default=6, help="Perturbation count per char per height")
    p.add_argument("--highsz", type=int, default=96, help="High-res render baseline height")
    p.add_argument("--pad", type=int, default=12, help="Padding around characters when rendering")
    return p.parse_args()

def main():
    args = parse_args()
    if not os.path.exists(args.font):
        print("Font file not found:", args.font)
        return
    heights = sorted(set(args.heights))
    gen_font_dataset(args.font, args.out, heights, perturb_count=args.perturb, high_sz=args.highsz, pad=args.pad)

if __name__ == "__main__":
    main()
