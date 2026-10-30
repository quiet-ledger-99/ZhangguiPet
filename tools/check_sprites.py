#!/usr/bin/env python3
"""检查导出帧：循环接缝、动作首尾与待机首帧的差异、半透明边的绿边/青边比例。"""
import os, json, numpy as np
from PIL import Image
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'sprites')
man = json.load(open(os.path.join(R, 'manifest.json')))
def ld(n, i): return np.asarray(Image.open(os.path.join(R, n, f'{i:03d}.webp')).convert('RGBA')).astype(np.float32)
def pm(a): b = a.copy(); b[..., :3] *= a[..., 3:4] / 255; return b
def d(a, b): return float(np.abs(pm(a) - pm(b)).mean())
A = man['anims']; idle0 = ld('idle', 0)
for n, m in A.items():
    N = m['n']; steps = [d(ld(n, i), ld(n, i + 1)) for i in range(N - 1)]
    line = f"{n:10s} n={N:3d} 相邻帧差 均值{np.mean(steps):.2f} 最大{max(steps):.2f}"
    if m['type'] == 'loop': line += f" | 接缝(末→首) {d(ld(n, N-1), ld(n, 0)):.2f}"
    line += f" | 首帧vs待机首帧 {d(ld(n,0), idle0):.2f} 末帧vs待机首帧 {d(ld(n,N-1), idle0):.2f}"
    print(line)
# 边缘溢色
tot = gr = cy = 0; amin = 255
for n, m in A.items():
    for i in range(0, m['n'], 6):
        f = ld(n, i); a = f[..., 3]; e = (a > 20) & (a < 235); r, g, b = f[..., 0][e], f[..., 1][e], f[..., 2][e]
        tot += e.sum(); gr += ((g > np.maximum(r, b) + 12)).sum(); cy += ((g > r + 25) & (b > r + 25) & (np.abs(g - b) < 20)).sum()
        amin = min(amin, a.min())
print(f"半透明边像素 {tot}，偏绿 {gr} ({gr/tot*100:.3f}%)，青灰 {cy} ({cy/tot*100:.3f}%)，最小 alpha {amin:.0f}")
