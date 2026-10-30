"""[停用方向] 用户已纠正：上边要倒挂不是正趴。正趴实验稿保留作备份。
读 peek_design/v036/top_prone_gen1.jpg → 写 assets/peek/tilt_top.png 与 tilt_top_prone_full.png。
用法：python tools/art036/cut_top_prone.py
旧倒挂备份在 peek_design/v036/tilt_top_hang_backup.png（不删）。
"""
import os, sys, json
import numpy as np, cv2
from PIL import Image
from rembg import remove, new_session
from pymatting import estimate_alpha_cf, estimate_foreground_ml

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from edgecheck import despill_f
ROOT = os.path.dirname(os.path.dirname(HERE))
RAW = os.path.join(ROOT, 'peek_design', 'v036', 'top_prone_gen1.jpg')
OUT_FULL = os.path.join(ROOT, 'peek_design', 'v036', 'tilt_top_prone_full.png')
OUT_PEEK = os.path.join(ROOT, 'assets', 'peek', 'tilt_top.png')
CW, CH, HEAD = 251, 380, 119
RETRACT_TOP = 48

def main():
    rgb_u8 = np.asarray(Image.open(RAW).convert('RGB'))
    white = rgb_u8.min(-1) > 240
    y_ledge = int(np.where(white.mean(1) > 0.5)[0][0])
    work = rgb_u8.copy(); work[y_ledge:, :] = 255
    wall_top = max(0, y_ledge - 36)
    work[wall_top:y_ledge, :] = 140
    sess = new_session('isnet-anime')
    a = work.astype(np.float64) / 255
    wall = np.zeros(work.shape[:2], bool); wall[wall_top:y_ledge, :] = True
    m = np.asarray(remove(Image.fromarray(work), session=sess, only_mask=True, post_process_mask=False)).astype(np.float64) / 255
    m[wall] = 0; m[y_ledge:, :] = 0
    k = np.ones((3, 3), np.uint8)
    white_px = a.min(-1) > 0.965
    fg = cv2.erode((m > 0.97).astype(np.uint8), k, iterations=3)
    bg = cv2.erode((m < 0.02).astype(np.uint8), k, iterations=3) | cv2.erode((white_px & (m < 0.25)).astype(np.uint8), k, iterations=2)
    tri = np.full(m.shape, 0.5); tri[fg > 0] = 1; tri[bg > 0] = 0; tri[wall] = 0
    al = estimate_alpha_cf(a, tri, laplacian_kwargs={'epsilon': 1e-6}, cg_kwargs={'maxiter': 2000})
    al = np.clip(al, 0, 1); al[al < 0.02] = 0; al[al > 0.98] = 1; al[wall] = 0; al[y_ledge:, :] = 0
    F = np.clip(estimate_foreground_ml(a, al), 0, 1)
    core = (al > 0.92).astype(np.float64)
    num = np.dstack([cv2.GaussianBlur(F[..., c] * core, (0, 0), 2.5) for c in range(3)])
    den = cv2.GaussianBlur(core, (0, 0), 2.5)[..., None]
    bleed = np.where(den > 1e-3, num / np.maximum(den, 1e-3), F)
    w = np.clip((0.92 - al) / 0.92, 0, 1)[..., None] ** 0.7
    F = despill_f(F * (1 - w) + bleed * w)
    bl = cv2.GaussianBlur(F, (0, 0), 1.0); F = despill_f(np.clip(F + 0.45 * (F - bl), 0, 1))
    full = np.dstack([F, al]).astype(np.float32)
    Image.fromarray((full * 255 + 0.5).astype(np.uint8), 'RGBA').save(OUT_FULL)

    crop = full[:y_ledge + 1].copy()
    ys = np.where(crop[..., 3] > 0.05)[0]
    head_px = max(90, int((ys.max() - ys.min()) * 0.70))
    s = HEAD / head_px
    P = crop.copy(); P[..., :3] *= P[..., 3:4]
    sm = cv2.resize(P, (round(P.shape[1] * s), round(P.shape[0] * s)), interpolation=cv2.INTER_AREA)
    ys2, xs2 = np.where(sm[..., 3] > 0.03)
    oy = -float(ys2.min()); ox = CW / 2 - (float(xs2.min()) + float(xs2.max())) / 2
    can = cv2.warpAffine(sm, np.float32([[1, 0, ox], [0, 1, oy]]), (CW, CH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    A = np.clip(can[..., 3:4], 0, 1)
    rgb = np.where(A > 1e-4, can[..., :3] / np.maximum(A, 1e-4), 0)
    A = A[..., 0] * np.clip((CH - np.arange(CH)) / 16.0, 0, 1)[:, None]
    A = np.clip(cv2.GaussianBlur(A, (0, 0), 0.4), 0, 1); A[A < 0.02] = 0
    out = (np.dstack([np.clip(despill_f(rgb), 0, 1), A]) * 255 + 0.5).astype(np.uint8)
    if not (out[0, :, 3] > 128).any():
        rows = np.where(out[..., 3].max(1) > 128)[0]
        if len(rows):
            shift = int(rows[0]); out = np.vstack([out[shift:], np.zeros((shift, CW, 4), np.uint8)])
    Image.fromarray(out, 'RGBA').save(OUT_PEEK, optimize=True)
    pj = os.path.join(ROOT, 'assets', 'peek', 'peek.json')
    meta = json.load(open(pj, encoding='utf-8'))
    meta['retract']['top'] = RETRACT_TOP
    meta['note'] = '上/下边：害羞 = 探头往墙里藏 retract 像素。上边为正趴探头（发不垂），retract.top=%d。' % RETRACT_TOP
    json.dump(meta, open(pj, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('tilt_top', Image.fromarray(out).getbbox(), 'retract.top', RETRACT_TOP)

if __name__ == '__main__':
    main()
