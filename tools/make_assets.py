#!/usr/bin/env python3
"""生成 v0.3 用的辅助素材（需要 numpy、Pillow，只在开发机上跑一次）：
- assets/masks/<动画>.png：该动画所有帧 alpha 的并集（外扩 2px），运行时当窗口遮罩，避免每帧 setMask。
- assets/icon.png / icon_64.png / icon.ico：托盘和 exe 图标（位图，Windows 托盘不认 SVG）。"""
import os, glob, json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(ROOT, 'assets', 'sprites')
MASKS = os.path.join(ROOT, 'assets', 'masks')
os.makedirs(MASKS, exist_ok=True)
man = json.load(open(os.path.join(SPR, 'manifest.json'), encoding='utf-8'))
for name in man['anims']:
    u = None
    for f in sorted(glob.glob(os.path.join(SPR, name, '*.webp'))):
        a = np.array(Image.open(f).convert('RGBA'))[:, :, 3] > 0
        u = a if u is None else (u | a)
    m = Image.fromarray((u * 255).astype('uint8')).filter(ImageFilter.MaxFilter(5))  # 外扩 2px
    rgba = Image.new('RGBA', m.size, (0, 0, 0, 0))
    rgba.putalpha(m.point(lambda v: 255 if v > 0 else 0))   # 透明=穿透，不透明=她（运行时用 createAlphaMask）
    rgba.save(os.path.join(MASKS, name + '.png'), optimize=True)
    print(name, 'mask fill %.2f' % (np.array(m) > 0).mean())

# 图标：待机第 0 帧的脸部裁圆，加淡色底
im = Image.open(os.path.join(SPR, 'idle', '000.webp')).convert('RGBA')
face = im.crop((63, 18, 193, 148)).resize((256, 256), Image.LANCZOS)
bg = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(bg)
d.ellipse((4, 4, 252, 252), fill=(232, 238, 255, 255), outline=(60, 80, 160, 255), width=10)
mask = Image.new('L', (256, 256), 0)
ImageDraw.Draw(mask).ellipse((14, 14, 242, 242), fill=255)
layer = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
layer.paste(face, (0, 0), Image.composite(face.getchannel('A'), Image.new('L', (256, 256), 0), mask))
bg.alpha_composite(layer)
bg.save(os.path.join(ROOT, 'assets', 'icon.png'))
bg.resize((64, 64), Image.LANCZOS).save(os.path.join(ROOT, 'assets', 'icon_64.png'))
bg.save(os.path.join(ROOT, 'assets', 'icon.ico'), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print('icon ok')
