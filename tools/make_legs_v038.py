#!/usr/bin/env python3
"""v0.3.8：把长脚重画素材（375x614 PNG 帧）导出成 assets/sprites_legs/*.webp，重做 masks_legs，
并把 v0.3.7 的 331 宽躲边图按墙侧补齐到 375（不重画）。只在开发机上跑。
用法：python tools/make_legs_v038.py <重画帧目录(内含 idle_a/ smile_b/ ...)>"""
import os, sys, json, glob, shutil
import numpy as np
from PIL import Image, ImageFilter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, 'assets')
SRC = sys.argv[1]
W, H = 375, 614
OLD_W = 331
UPPER_X, UPPER_Y = 58, 0          # 头/上半身框（251x380）在新画布里的位置：用旧上半身的头部模板在新 idle 上匹配得到
MAP = {'idle': ('idle_a', 'loop'), 'smile': ('smile_b', 'clip'), 'smug': ('smug_b', 'clip'),
       'thinking': ('thinking_b', 'clip'), 'smug_hold': ('smug_hold_b', 'hold'),
       'thinking_hold': ('thinking_hold_b', 'hold'), 'wave': ('wave_a', 'clip'), 'huff': ('huff_f', 'clip')}
Q = 90
FPS = float(os.environ.get('LEGS_FPS', '24'))   # v0.3.9：长脚素材 24fps（飘着模式仍 12fps）

flo = json.load(open(os.path.join(A, 'sprites', 'manifest.json'), encoding='utf-8'))
spr = os.path.join(A, 'sprites_legs'); masks = os.path.join(A, 'masks_legs')
anims = {}
for name, (src, typ) in MAP.items():
    d = os.path.join(spr, name)
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    fs = sorted(glob.glob(os.path.join(SRC, src, '*.png')))
    assert len(fs) == flo['anims'][name]['n'] * round(FPS / flo['fps']), (name, len(fs))
    u = None
    for i, f in enumerate(fs):
        im = Image.open(f).convert('RGBA')
        assert im.size == (W, H), f
        im.save(os.path.join(d, f'{i:03d}.webp'), 'WEBP', quality=Q, alpha_quality=90, method=6)
        a = np.array(Image.open(os.path.join(d, f'{i:03d}.webp')).convert('RGBA'))[:, :, 3] > 0
        u = a if u is None else (u | a)
    m = Image.fromarray((u * 255).astype('uint8')).filter(ImageFilter.MaxFilter(5))  # 所有帧并集外扩 2px
    rgba = Image.new('RGBA', m.size, (0, 0, 0, 0)); rgba.putalpha(m.point(lambda v: 255 if v > 0 else 0))
    rgba.save(os.path.join(masks, name + '.png'), optimize=True)
    anims[name] = {'n': len(fs), 'type': typ, 'src': 'v4_' + src}
    print(name, len(fs), 'mask fill %.3f' % (np.array(m) > 0).mean())

fx = {k: {'img': v['img'], 'at': [round(v['at'][0] + UPPER_X, 1), round(v['at'][1] + UPPER_Y, 1)]} for k, v in flo['fx'].items()}
man = {'w': W, 'h': H, 'fps': FPS, 'padx': (W - 251) // 2, 'upper_x': UPPER_X, 'upper_y': UPPER_Y,
       'upper_w': 251, 'upper_h': 380, 'foot_y': 600, 'foot_x': W / 2, 'anims': anims, 'fx': fx,
       'note': 'v0.3.9 长脚 24fps（v0.3.8 起 8 段都是 v4 风格整身重画，有腿，wave/huff 也有；huff 用 huff_f）。画布 375x614，左右各留 62；'
               '脚底 y=600、脚中 x=187.5。upper_x/upper_y/upper_w/upper_h = 头和上半身框（摸头区、zzz、爱心、计时牌、'
               '下边躲藏阈值用），由旧 251x380 上半身的头部在新图上匹配得到；fx.at 已经加过 upper_x/upper_y。'}
json.dump(man, open(os.path.join(spr, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# 躲边图：331 -> 375，墙那一侧不动，另一侧补透明；上/下边两边各补一半
pad = W - OLD_W
for p in sorted(glob.glob(os.path.join(A, 'peek_legs', '*.png'))):
    im = Image.open(p).convert('RGBA')
    if im.size == (W, H):
        continue
    assert im.size == (OLD_W, H), p
    side = os.path.basename(p)[:-4].split('_')[1]
    x = {'left': 0, 'right': pad}.get(side, pad // 2)
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0)); out.paste(im, (x, 0))
    out.save(p, optimize=True)
    print('peek', os.path.basename(p), 'x+%d' % x)
