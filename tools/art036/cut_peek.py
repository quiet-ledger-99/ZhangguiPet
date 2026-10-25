"""v0.3.6 躲边立绘抠图：左边（单独画的，不再镜像）、上边、下边。
生成稿是「灰墙 + 白底」：墙的边 = 屏幕边。抠图按「抠图去绿」skill §1：
rembg isnet-anime 粗遮罩 → trimap → pymatting closed-form 求 alpha → estimate_foreground_ml 重建前景色 →
内侧实心颜色向外扩散 → 蓝发专用去溢色 → 轻锐化（不动 alpha）→ 预乘缩放 → 墙那边硬切。
缩放：头高（帽顶→下巴）= 119px，和 v0.3.2 右边那两张一样。
用法：python tools/art036/cut_peek.py   （读 peek_design/v036/*_raw.jpg，写 assets/peek/ 和 peek_design/v036/*_full.png）"""
import os, sys, json, time
import numpy as np, cv2
from PIL import Image
from rembg import remove, new_session
from pymatting import estimate_alpha_cf, estimate_foreground_ml
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from edgecheck import despill_f
ROOT = os.path.dirname(os.path.dirname(HERE))
RAW = os.path.join(ROOT, 'peek_design', 'v036')
OUTD = os.path.join(ROOT, 'assets', 'peek')
CW, CH = 251, 380
HEAD = 119
# 名字: (原图, 墙在哪边, 头高 px(原图), 对齐组)
JOBS = {
    'tilt_left': ('L_tilt_raw.jpg', 'left', 308),
    'shy_left':  ('L_shy_raw.jpg',  'left', 300),
    'tilt_bottom': ('bottom_raw_gen6a.jpg', 'bottom', 366),  # gen6a 重画：手/肩贴灰墙实边
    'tilt_top':    ('top_raw_gen5.jpg', 'top', 310),  # gen5 倒挂+发贴头无垂帘
}
RETRACT = {'bottom': 35, 'top': 64}       # 缩回去（害羞）时往墙里多藏多少 px（251x380 画布、100% 大小）

def wall_edge(a, side):
    g = (np.abs(a[..., 0] - a[..., 1]) < 12) & (np.abs(a[..., 1] - a[..., 2]) < 12) & (a.mean(2) > 90) & (a.mean(2) < 175)
    if side == 'left':  return int(np.where(g.mean(0) > 0.6)[0].max()) + 1
    if side == 'right': return int(np.where(g.mean(0) > 0.6)[0].min())
    if side == 'top':   return int(np.where(g.mean(1) > 0.6)[0].max()) + 1
    return int(np.where(g.mean(1) > 0.6)[0].min())

def wall_slice(side, e):
    return {'left': np.s_[:, :e], 'right': np.s_[:, e:], 'top': np.s_[:e, :], 'bottom': np.s_[e:, :]}[side]

def matte(rgb_u8, wall, sess):
    a = rgb_u8.astype(np.float64) / 255
    m = np.asarray(remove(Image.fromarray(rgb_u8), session=sess, only_mask=True, post_process_mask=False)).astype(np.float64) / 255
    m[wall] = 0
    k = np.ones((3, 3), np.uint8)
    white = a.min(-1) > 0.965
    fg = cv2.erode((m > 0.97).astype(np.uint8), k, iterations=3)
    bg = cv2.erode((m < 0.02).astype(np.uint8), k, iterations=3) | cv2.erode((white & (m < 0.25)).astype(np.uint8), k, iterations=2)
    tri = np.full(m.shape, 0.5); tri[fg > 0] = 1; tri[bg > 0] = 0; tri[wall] = 0
    al = estimate_alpha_cf(a, tri, laplacian_kwargs={'epsilon': 1e-6}, cg_kwargs={'maxiter': 2000})
    al = np.clip(al, 0, 1); al[al < 0.02] = 0; al[al > 0.98] = 1; al[wall] = 0
    F = np.clip(estimate_foreground_ml(a, al), 0, 1)
    core = (al > 0.92).astype(np.float64)
    num = np.dstack([cv2.GaussianBlur(F[..., c] * core, (0, 0), 2.5) for c in range(3)]); den = cv2.GaussianBlur(core, (0, 0), 2.5)[..., None]
    bleed = np.where(den > 1e-3, num / np.maximum(den, 1e-3), F)
    w = np.clip((0.92 - al) / 0.92, 0, 1)[..., None] ** 0.7
    F = F * (1 - w) + bleed * w
    F = despill_f(F)
    bl = cv2.GaussianBlur(F, (0, 0), 1.0); F = np.clip(F + 0.45 * (F - bl), 0, 1)
    F = despill_f(F)
    return np.dstack([F, al]).astype(np.float32)

def hard_wall_contact(full, side, e):
    """墙沿内侧 实心化：从最近实心核把颜色填到墙边，alpha=1；墙内清零。
    不整体平移立绘，避免切下巴；专治手套/肩贴边 soft 透底。"""
    out = full.copy()
    al = out[..., 3]
    F = out[..., :3]
    H, W = al.shape
    thr = 0.85
    if side == 'bottom':
        for x in range(W):
            above = al[:e, x]
            sy = np.where(above >= thr)[0]
            if sy.size == 0:
                # 无实心：清掉贴墙 soft，勿造假
                soft = (above > 0.02) & (above < thr)
                if soft.any():
                    al[:e, x][soft] = 0.0
                al[e:, x] = 0.0
                continue
            yb = int(sy.max())
            # 实心核到墙沿（不含墙）全部抬实并取样填色
            for y in range(yb, e):
                F[y, x] = F[yb, x]
                al[y, x] = 1.0
            al[e:, x] = 0.0
    elif side == 'top':
        for x in range(W):
            below = al[e:, x]
            sy = np.where(below >= thr)[0]
            if sy.size == 0:
                soft = (below > 0.02) & (below < thr)
                if soft.any():
                    al[e:, x][soft] = 0.0
                al[:e, x] = 0.0
                continue
            yt = int(sy.min()) + e
            for y in range(e, yt + 1):
                F[y, x] = F[yt, x]
                al[y, x] = 1.0
            al[:e, x] = 0.0
    out[..., :3] = F
    out[..., 3] = al
    return out

def harden_sprite_wall(rgba_u8, side, solid=200, reach=3):
    """251x380 画布：若实心距墙 ≤reach px，把实心色填到墙边 alpha=255；否则只清墙侧 soft。
    不平移整图。"""
    out = rgba_u8.copy()
    a = out[..., 3]
    H, W = a.shape
    if side == 'bottom':
        for x in range(W):
            sy = np.where(a[:, x] >= solid)[0]
            if sy.size == 0:
                soft = (a[:, x] > 0) & (a[:, x] < solid)
                a[soft, x] = 0
                continue
            yb = int(sy.max())
            if H - 1 - yb <= reach:
                for y in range(yb, H):
                    out[y, x, :3] = out[yb, x, :3]
                    a[y, x] = 255
            else:
                below = slice(yb + 1, H)
                soft = (a[below, x] > 0) & (a[below, x] < solid)
                if soft.any():
                    a[below, x][soft] = 0
    elif side == 'top':
        for x in range(W):
            sy = np.where(a[:, x] >= solid)[0]
            if sy.size == 0:
                soft = (a[:, x] > 0) & (a[:, x] < solid)
                a[soft, x] = 0
                continue
            yt = int(sy.min())
            if yt <= reach:
                for y in range(0, yt + 1):
                    out[y, x, :3] = out[yt, x, :3]
                    a[y, x] = 255
            else:
                above = slice(0, yt)
                soft = (a[above, x] > 0) & (a[above, x] < solid)
                if soft.any():
                    a[above, x][soft] = 0
    out[..., 3] = a
    return out

def place(full, side, e, head):
    """full: HxWx4 float straight 0..1 → 251x380 画布（预乘缩放）。墙边 = 画布边。"""
    s = HEAD / head
    P = full.copy(); P[..., :3] *= P[..., 3:4]
    h, w = P.shape[:2]
    nw, nh = round(w * s), round(h * s)
    sm = cv2.resize(P, (nw, nh), interpolation=cv2.INTER_AREA)
    es = e * s
    al = sm[..., 3]
    ys, xs = np.where(al > 0.03)
    can = np.zeros((CH, CW, 4), np.float32)
    if side == 'left':
        ox = -es
        oy = 8 - ys.min()
    elif side == 'bottom':
        oy = CH - es
        ox = CW / 2 - (xs.min() + xs.max()) / 2
    elif side == 'top':
        oy = -es
        ox = CW / 2 - (xs.min() + xs.max()) / 2
    M = np.float32([[1, 0, ox], [0, 1, oy]])
    can = cv2.warpAffine(sm, M, (CW, CH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    # 墙那边硬切（亚像素平移会在边上留半透明一列/一行：直接补满，墙边要贴实）
    can = seal_wall(can, side)
    return can, (ox, oy)

def seal_wall(can, side, solid=0.40):
    """只清墙边 soft alpha，不把实心内容整体平移，避免切脸切手。
    can: HxWx4 float（预乘或直通均可，只改 alpha 通道）。
    bottom：每列 solid 下沿以下的半透明清零；不 shift、不抬末行、不造假实心。
    top：对称。宁肯留一点软边/空隙，也不下压立绘。
    """
    out = can.copy()
    a = out[..., 3]
    H, W = a.shape
    thr = float(solid)
    if side == 'bottom':
        for x in range(W):
            col = a[:, x]
            solid_ys = np.where(col >= thr)[0]
            if solid_ys.size == 0:
                soft = (col > 0) & (col < thr)
                if soft.any():
                    a[soft, x] = 0.0
                continue
            y_bot = int(solid_ys.max())
            below = a[y_bot + 1 :, x]
            soft_below = (below > 0) & (below < thr)
            if soft_below.any():
                a[y_bot + 1 :, x][soft_below] = 0.0
            if 0 < a[H - 1, x] < thr:
                a[H - 1, x] = 0.0
    elif side == 'top':
        for x in range(W):
            col = a[:, x]
            solid_ys = np.where(col >= thr)[0]
            if solid_ys.size == 0:
                soft = (col > 0) & (col < thr)
                if soft.any():
                    a[soft, x] = 0.0
                continue
            y_top = int(solid_ys.min())
            above = a[:y_top, x]
            soft_above = (above > 0) & (above < thr)
            if soft_above.any():
                a[:y_top, x][soft_above] = 0.0
            if 0 < a[0, x] < thr:
                a[0, x] = 0.0
    out[..., 3] = a
    return out


def finish(can, side):
    A = np.clip(can[..., 3:4], 0, 1)
    rgb = np.where(A > 1e-4, can[..., :3] / np.maximum(A, 1e-4), 0)
    A = A[..., 0]
    if side == 'left':   # 和右边一样：底部 36px 渐隐
        f = np.clip((CH - np.arange(CH)) / 36.0, 0, 1); A = A * f[:, None]
    if side == 'top':    # 发尾太长时最下面 24px 渐隐（勿糊墙边：顶边稍后重封）
        f = np.clip((CH - np.arange(CH)) / 24.0, 0, 1); A = A * f[:, None]
    # 轻模糊只作用于非墙边，避免把贴任务栏/屏边的实边又糊软
    blur = np.clip(cv2.GaussianBlur(A, (0, 0), 0.4), 0, 1)
    if side == 'bottom':
        blur[-2:] = A[-2:]
    elif side == 'top':
        blur[:2] = A[:2]
    elif side == 'left':
        blur[:, :2] = A[:, :2]
    A = blur
    A[A < 0.02] = 0
    out = np.dstack([np.clip(despill_f(rgb), 0, 1), A]).astype(np.float32)
    # 模糊后可能又软了：再封一次墙边
    out = seal_wall(out, side)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)

if __name__ == '__main__':
    sess = new_session('isnet-anime')
    meta = {}
    only = sys.argv[1:] or list(JOBS)

    for name in ['tilt_left', 'shy_left', 'tilt_bottom', 'tilt_top']:
        if name not in only: continue
        raw, side, head = JOBS[name]
        t = time.time()
        im = np.asarray(Image.open(os.path.join(RAW, raw)).convert('RGB'))
        e = wall_edge(im.astype(int), side)
        b = im.copy(); ws = wall_slice(side, e); b[ws] = 255
        wall = np.zeros(im.shape[:2], bool); wall[ws] = True
        cache = os.path.join(RAW, name + '_full.png')
        if os.path.exists(cache) and '--recut' not in sys.argv:
            full = np.asarray(Image.open(cache)).astype(np.float32) / 255
        else:
            full = matte(b, wall, sess)
            full = hard_wall_contact(full, side, e)
            Image.fromarray((full * 255 + 0.5).astype(np.uint8), 'RGBA').save(cache)
        if name == 'shy_left' and 'tilt_left' in meta:
            # 害羞和探头用同一套原图坐标对齐（两张稿子构图一样：墙边同一位置），只按各自头高缩放
            s = HEAD / head; P = full.copy(); P[..., :3] *= P[..., 3:4]
            sm = cv2.resize(P, (round(P.shape[1] * s), round(P.shape[0] * s)), interpolation=cv2.INTER_AREA)
            ox = -e * s; oy = meta['tilt_left']['oy'] * (s / meta['tilt_left']['s'])
            can = cv2.warpAffine(sm, np.float32([[1, 0, ox], [0, 1, oy]]), (CW, CH), flags=cv2.INTER_LINEAR)
            off = (ox, oy)
        else:
            can, off = place(full, side, e, head)
        out = finish(can, side)
        if side == 'bottom':
            out = harden_sprite_wall(out, 'bottom')
        elif side == 'top':
            out = harden_sprite_wall(out, 'top')
        Image.fromarray(out, 'RGBA').save(os.path.join(OUTD, name + '.png'), optimize=True)
        meta[name] = dict(raw=raw, edge=e, s=HEAD / head, ox=float(off[0]), oy=float(off[1]))
        print(name, 'edge', e, 'bbox', Image.fromarray(out).getbbox(), round(time.time() - t, 1), 's', flush=True)
    json.dump({'retract': RETRACT, 'note': '上/下边：害羞 = 探头那张往墙里再藏 retract 像素（100% 大小），程序里画的时候平移'},
              open(os.path.join(OUTD, 'peek.json'), 'w'), ensure_ascii=False, indent=1)
