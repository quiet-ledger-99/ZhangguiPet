"""去掉帽徽右侧多出来的珍珠（v6 素材里旧「珍珠花」帽饰的残留：v9 把原设定徽章贴回去时，珍珠没被完全盖住）。
徽章本身是原设计（ZipZipPipe），保留不动。
做法：逐帧用模板匹配追踪徽章中心 → 珍珠相对徽章的位置固定（第 0 帧量好，见 PEARLS）→
在这几个小圆里，除了金色圆环以外的像素都当珍珠 → cv2.inpaint 用周围的帽子颜色补上；alpha 不动。"""
import numpy as np, cv2

# 第 0 帧徽章中心（v6 缓存 720x960 坐标）和珍珠相对徽章中心的位置 (dx, dy, r)
BADGE0 = {'v6_wave': (242, 132), 'v6_hips': (228, 128)}
PEARLS = {'v6_wave': [(38.5, -13.5, 7.5), (33.5, -3.5, 7)],
          'v6_hips': [(35.5, -28, 7), (30.5, -20.5, 7)]}

def track_badge(frames, c0, tpl_r=26, search=30, ref=None):
    f0 = (frames[0] if ref is None else ref)[..., :3]
    x0, y0 = c0
    tpl = cv2.cvtColor(np.ascontiguousarray(f0[y0 - tpl_r:y0 + tpl_r, x0 - tpl_r:x0 + tpl_r]), cv2.COLOR_RGB2GRAY)
    out = []; prev = c0
    for fr in frames:
        g = cv2.cvtColor(np.ascontiguousarray(fr[..., :3]), cv2.COLOR_RGB2GRAY)
        px, py = prev
        ys, xs = max(0, py - tpl_r - search), max(0, px - tpl_r - search)
        roi = g[ys:py + tpl_r + search, xs:px + tpl_r + search]
        res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _, sc, _, loc = cv2.minMaxLoc(res)
        c = (xs + loc[0] + tpl_r, ys + loc[1] + tpl_r)
        out.append((c, float(sc))); prev = c
    return out

def pearl_mask(fr, c, pearls):
    h, w = fr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    m = np.zeros((h, w), bool)
    for dx, dy, r in pearls:
        m |= (xx - c[0] - dx) ** 2 + (yy - c[1] - dy) ** 2 <= r * r
    hsv = cv2.cvtColor(np.ascontiguousarray(fr[..., :3]), cv2.COLOR_RGB2HSV).astype(int)
    H, S, V = hsv[..., 0] * 2, hsv[..., 1], hsv[..., 2]
    gold = (H >= 15) & (H <= 50) & (S > 62) & (V > 110)        # 金色圆环（珍珠是灰白，S<45）
    return m & ~gold & (fr[..., 3] > 0)

def remove(fr, m, radius=4):
    if not m.any(): return fr
    rgb = np.ascontiguousarray(fr[..., :3])
    fixed = cv2.inpaint(rgb, m.astype(np.uint8), radius, cv2.INPAINT_TELEA)
    out = fr.copy(); out[..., :3] = fixed
    return out

def track_pearls(frames, key, badge_tr, half=(12, 15), search=22, ref=None):
    """珍珠相对徽章会随帽子轻微转动而移位：再用第 0 帧的珍珠小块做模板，逐帧在徽章右上方找它。"""
    ps = PEARLS[key]
    cx0, cy0 = BADGE0[key]
    mx = sum(p[0] for p in ps) / len(ps); my = sum(p[1] for p in ps) / len(ps)
    px0, py0 = int(round(cx0 + mx)), int(round(cy0 + my))
    hw, hh = half
    g0 = cv2.cvtColor(np.ascontiguousarray((frames[0] if ref is None else ref)[..., :3]), cv2.COLOR_RGB2GRAY)
    tpl = g0[py0 - hh:py0 + hh, px0 - hw:px0 + hw]
    out = []; prev = None
    for fr, (c, _) in zip(frames, badge_tr):
        g = cv2.cvtColor(np.ascontiguousarray(fr[..., :3]), cv2.COLOR_RGB2GRAY)
        ex, ey = (int(c[0] + mx), int(c[1] + my)) if prev is None else prev
        xs, ys = max(0, ex - hw - search), max(0, ey - hh - search)
        roi = g[ys:ey + hh + search, xs:ex + hw + search]
        res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        _, sc, _, loc = cv2.minMaxLoc(res)
        p = (xs + loc[0] + hw, ys + loc[1] + hh)
        out.append((p, float(sc))); prev = p
    return out, (mx, my)

def clean_clip(frames, key, ref=None):
    """frames: list of HxWx4 uint8 (同一段动画)；ref = 量 BADGE0/PEARLS 用的那张第 0 帧（默认 frames[0]）。
    返回 (新帧列表, 徽章追踪, 珍珠追踪)。"""
    tr = track_badge(frames, BADGE0[key], ref=ref)
    ptr, (mx, my) = track_pearls(frames, key, tr, ref=ref)
    rel = [(dx - mx, dy - my, r) for dx, dy, r in PEARLS[key]]
    out = [remove(fr, pearl_mask(fr, p, rel)) for fr, (p, sc) in zip(frames, ptr)]
    return out, tr, ptr
