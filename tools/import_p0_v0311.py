# -*- coding: utf-8 -*-
"""v0.3.11：导入 P0 四动作（stretch/yawn/nod/nap）的返工帧（消跳 + 首尾对齐 idle），
按仓库统一参数重编码 webp（Q90 / alpha 90 / method 6），并重做这四个动画的遮罩（所有帧 alpha 并集外扩 2px）。
用法：python tools/import_p0_v0311.py <浮空返工帧目录(含4个子目录)> <长脚返工帧目录(sprites_legs)>
浮空 stretch 是 24fps tall 画布 251x416（头顶多 36px，manifest anchor_offset_y=36），遮罩同尺寸。"""
import glob, os, shutil, sys
import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, 'assets')
NAMES = ['stretch', 'yawn', 'nod', 'nap']
# 有损 Q90 重编码后过不了 check_sprite_frames 的两组改用无损（浮空 tall stretch：画布下移 36px 后 webp 块对齐变了，
# 首尾帧与 idle 差 5.3；长脚 nod：动作幅度小，有损噪声让 6 处相邻差 11 > 10）。
LOSSLESS = {('sprites', 'stretch'), ('sprites_legs', 'nod')}


def imp(src, spr, masks):
    for name in NAMES:
        fs = sorted(glob.glob(os.path.join(src, name, '*.webp')) + glob.glob(os.path.join(src, name, '*.png')))
        d = os.path.join(A, spr, name)
        shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        idle_f = os.path.join(A, spr, 'idle', '000.webp')
        idle_px = np.array(Image.open(idle_f).convert('RGBA'))
        u = None
        for i, f in enumerate(fs):
            out = os.path.join(d, f'{i:03d}.webp')
            im = Image.open(f).convert('RGBA')
            if im.size == Image.open(idle_f).size and np.array_equal(np.array(im), idle_px):
                shutil.copyfile(idle_f, out)          # 首尾对齐帧＝idle 原文件，字节级一致
            elif (spr, name) in LOSSLESS:
                im.save(out, 'WEBP', lossless=True, quality=100, method=6, exact=True)
            else:
                im.save(out, 'WEBP', quality=90, alpha_quality=90, method=6)
            a = np.array(Image.open(out).convert('RGBA'))[:, :, 3] > 0
            u = a if u is None else (u | a)
        m = Image.fromarray((u * 255).astype('uint8')).filter(ImageFilter.MaxFilter(5))
        rgba = Image.new('RGBA', m.size, (0, 0, 0, 0)); rgba.putalpha(m.point(lambda v: 255 if v > 0 else 0))
        rgba.save(os.path.join(A, masks, name + '.png'), optimize=True)
        print(spr, name, len(fs), m.size, 'mask fill %.3f' % (np.array(m) > 0).mean())


if __name__ == '__main__':
    imp(sys.argv[1], 'sprites', 'masks')
    imp(sys.argv[2], 'sprites_legs', 'masks_legs')
