#!/usr/bin/env python3
"""局部抬实 tilt_bottom 底边 soft：soft_colored & dilate(solid) → alpha>=245。
不移动立绘、不做 seal shift。默认对齐 v036_review/11_..._candidate.png（若存在则直接采用）。
"""
from pathlib import Path
import numpy as np
import cv2
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / 'assets/peek/tilt_bottom.png'
BACKUP = ROOT / 'peek_design/v036/tilt_bottom_soft_backup.png'
CAND = ROOT / 'v036_review/11_tilt_bottom_local_opaque_candidate.png'

def local_opaque_lift(rgba, solid_thr=200, soft_hi=245, color_thr=5, k=2, target=245):
    out = rgba.copy()
    a = out[..., 3]
    rgb = out[..., :3]
    solid = (a >= solid_thr).astype(np.uint8)
    soft = (a > 0) & (a < soft_hi)
    soft_colored = soft & (rgb.max(axis=-1) > color_thr)
    dil = cv2.dilate(solid, np.ones((2 * k + 1, 2 * k + 1), np.uint8)) > 0
    mask = soft_colored & dil
    out[..., 3] = np.where(mask, np.maximum(a, target).astype(np.uint8), a)
    return out, mask

def main():
    if not BACKUP.exists():
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        shutil_copy = __import__('shutil').copy2
        shutil_copy(ASSET, BACKUP)
    if CAND.exists():
        Image.open(CAND).save(ASSET)
        print('wrote candidate →', ASSET)
        return
    src = np.asarray(Image.open(BACKUP if BACKUP.exists() else ASSET))
    out, mask = local_opaque_lift(src)
    Image.fromarray(out, 'RGBA').save(ASSET)
    print('lifted', int(mask.sum()), 'px →', ASSET)

if __name__ == '__main__':
    main()
