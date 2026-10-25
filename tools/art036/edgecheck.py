"""v0.3.6 素材自查（按「抠图去绿」skill §3/§5）：
- despill_u8：蓝发角色专用去溢色（B>=R 时 G<=R+0.30*(B-R)，否则 G<=R）
- band：边缘带 = alpha>0 且（半透明，或离透明区 7px 以内）
- metric：合成到给定背景后，统计边缘带里 偏青绿（色相 70–212° 且 S>38）和 绿溢（G-max(R,B)>5）的像素数
桌宠放在任意桌面上，所以测 4 种背景：白、深灰、淡蓝、蓝。"""
import numpy as np, cv2
C = 0.30
BGS = {'white': np.array([255., 255, 255]), 'dark': np.array([32., 32, 32]),
       'pale': np.array([205., 220, 240]), 'blue': np.array([95., 124, 186])}

def despill_u8(a):
    a = np.array(a, copy=True)
    r = a[..., 0].astype(np.int16); g = a[..., 1].astype(np.int16); b = a[..., 2].astype(np.int16)
    lim = np.where(b >= r, r + ((b - r) * C).astype(np.int16), r)
    a[..., 1] = np.minimum(g, lim).astype(np.uint8)
    return a

def despill_f(rgb):
    """float 0..1 / 0..255 straight RGB(A)"""
    out = rgb.copy(); r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lim = np.where(b >= r, r + (b - r) * C, r)
    out[..., 1] = np.minimum(g, lim)
    return out

def comp(a, bg):
    al = a[..., 3:4] / 255.
    return (a[..., :3] * al + bg * (1 - al)).clip(0, 255).astype(np.uint8)

def band(a):
    A = a[..., 3]; tr = (A < 128).astype(np.uint8)
    near = cv2.dilate(tr, np.ones((7, 7), np.uint8)) > 0
    return (A > 0) & (near | (A < 255))

def metric(a, bg):
    c = comp(a, bg); b = band(a)
    hsv = cv2.cvtColor(c, cv2.COLOR_RGB2HSV).astype(int); H = hsv[..., 0] * 2; S = hsv[..., 1]
    ci = c.astype(int); gd = ci[..., 1] - np.maximum(ci[..., 0], ci[..., 2])
    teal = b & (H >= 70) & (H <= 212) & (S > 38)
    green = b & (gd > 5)
    return int(b.sum()), int(teal.sum()), int(green.sum())

def stats(items):
    """items: [(name, rgba uint8)] -> {bg: [band, teal, green]}, rows"""
    tot = {k: [0, 0, 0] for k in BGS}; rows = []
    for n, a in items:
        for bn, bg in BGS.items():
            b, t, g = metric(a, bg)
            T = tot[bn]; T[0] += b; T[1] += t; T[2] += g
            rows.append((n, bn, b, t, g))
    return tot, rows

def worst_window(a, bg, win=150):
    c = comp(a, bg); hsv = cv2.cvtColor(c, cv2.COLOR_RGB2HSV).astype(int)
    m = (band(a) & (hsv[..., 0] * 2 >= 70) & (hsv[..., 0] * 2 <= 212) & (hsv[..., 1] > 38)).astype(np.float32)
    win = min(win, a.shape[0], a.shape[1])
    s = cv2.boxFilter(m, -1, (win, win), normalize=False); y, x = np.unravel_index(np.argmax(s), s.shape)
    y0 = max(0, min(y - win // 2, a.shape[0] - win)); x0 = max(0, min(x - win // 2, a.shape[1] - win))
    return x0, y0, win
