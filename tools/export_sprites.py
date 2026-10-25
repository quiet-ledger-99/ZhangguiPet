#!/usr/bin/env python3
"""导出桌宠精灵帧（WebP 带透明，24fps 源降到 12fps）。
v0.3.6：
  - 去掉「拿扇子+把小包递到前面」的元气笑（略露齿）和鼓腮两段，换成 v6 表情动画：
      wave  回眸挥手（闭嘴浅笑，代替原来的 biz 元气笑）
      huff  合扇抵下巴、一手叉腰的小嘴硬（闭嘴，代替原来的 pout 鼓腮）
    v6 动画先去掉帽徽右上方多出来的珍珠（tools/art036/pearls.py，徽章本身保留），
    再按头高（帽顶→下巴）缩放、对齐到 v16 待机的坐标系，画布/锚点/大小和其他帧完全一致。
  - 所有帧统一用蓝发专用去溢色（tools/art036/edgecheck.py 的 despill：B>=R 时 G<=R+0.3(B-R)，否则 G<=R），
    代替旧的 G<=max(R,B)+4（旧规则漏掉发丝缝里的青色）。
用法: python tools/export_sprites.py <anim_cache_v16 目录> <anim_cache_v11 目录> [高度=380]
输出: assets/sprites/<动画名>/NNN.webp + assets/sprites/manifest.json + assets/fx/*.png"""
import sys, os, json, math, shutil
import numpy as np, cv2
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'art036'))
from edgecheck import despill_f          # noqa: E402
import pearls                             # noqa: E402

SRC = sys.argv[1]
SRC6 = sys.argv[2]
H = int(sys.argv[3]) if len(sys.argv) > 3 else 380
OUT = os.path.join(ROOT, 'assets', 'sprites')
STEP = 2                 # 24fps -> 12fps
Q = 90                   # webp 质量（v0.3.5 是 75；有损压缩会把一点青边带回来，90 时边缘统计≈0，体积多约 15%）
FADE_B = 0.10            # 源片下摆/两侧被画面裁掉：底部 10%、两侧 3% 做渐隐，让硬切边看起来像故意的半身

# (输出名, 缓存目录, 缓存名, 起始帧, 结束帧(不含), 类型)
SETS = [
    ('idle',          SRC,  'idle_neutral_143',   0, 144, 'loop'),   # 待机：双手交叠，呼吸/眨眼，首尾已烘焙成无缝
    ('smile',         SRC,  'neutral',            0, 144, 'clip'),   # 微笑 + 眨一下眼；首尾都≈待机
    ('smug',          SRC,  'smug',               0, 144, 'clip'),   # 眯眼温柔笑；首尾都≈待机
    ('thinking',      SRC,  'thinking',           0, 144, 'clip'),   # 手指抵下巴想事情；首尾都≈待机
    ('smug_hold',     SRC,  'idle_smug_143',      0, 48,  'hold'),   # 眯眼笑之后的轻轻摇晃（来回播放）
    ('thinking_hold', SRC,  'idle_thinking_95',   0, 48,  'hold'),   # 停在「手指抵下巴」的小循环（来回播放）
    ('wave',          SRC6, 'v6_wave',            0, 96,  'v6'),     # v0.3.6 回眸挥手（代替递包元气笑）
    ('huff',          SRC6, 'v6_hips',            0, 96,  'v6'),     # v0.3.6 合扇抵下巴小嘴硬（代替递包鼓腮）
]
# v6 表情（1024x1536 立绘 → 720x960 动画）对齐到 v16 坐标系（720x1088）：
# 头高 v16 待机 292px / v6 256px → 放大 1.14；帽顶对齐 y=8，头部横向重心对齐 x≈360（tools/art036 里量的）
V6_MAP = {'v6_wave': (1.14, -31.0, -18.2), 'v6_hips': (1.14, -33.0, -12.5)}
V16_W, V16_H = 720, 1088

def v6_frames(nm, a, b):
    arr = np.load(os.path.join(SRC6, nm + '.npy'), mmap_mode='r')
    frs = [np.array(arr[i]) for i in range(a, min(b, len(arr)))]
    clean, tr, ptr = pearls.clean_clip(frs, nm)
    k, dx, dy = V6_MAP[nm]
    h6 = frs[0].shape[0]
    fb = np.clip((h6 - np.arange(h6)) / (0.06 * h6), 0, 1); fb = fb * fb * (3 - 2 * fb)   # v6 自己的下沿也渐隐，免得映射后留一条硬边
    M = np.float32([[k, 0, dx], [0, k, dy]])
    out = []
    for fr in clean:
        f = fr.astype(np.float32); f[..., 3] *= fb[:, None]
        f[..., :3] *= f[..., 3:4] / 255.0
        w = cv2.warpAffine(f, M, (V16_W, V16_H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        w = np.clip(w, 0, None); w[..., 3] = np.clip(w[..., 3], 0, 255); w[..., :3] = np.minimum(w[..., :3], w[..., 3:4])
        out.append(w)                     # 预乘 float
    scores = [s for _, s in ptr]
    print(nm, 'badge/pearl track min score', round(min(s for _, s in tr), 3), round(min(scores), 3))
    return out

x0, y0, x1, y1 = 0, 0, V16_W, V16_H       # v16 所有片段的 alpha 并集就是整幅画面（和 v0.3.5 一样）
sc = H / (y1 - y0)
W = int(round((x1 - x0) * sc))
print('scale', round(sc, 4), 'out', W, 'x', H)
hh, ww = y1 - y0, x1 - x0
fy = np.clip((hh - np.arange(hh)) / (FADE_B * hh), 0, 1); fy = fy * fy * (3 - 2 * fy)
fx_ = np.clip(np.minimum(np.arange(ww), ww - 1 - np.arange(ww)) / (0.03 * ww), 0, 1); fx_ = fx_ * fx_ * (3 - 2 * fx_)
FADE = fy[:, None] * fx_[None, :]
man = dict(w=W, h=H, fps=24 / STEP, anims={})
for old in ('biz', 'biz_hold', 'pout', 'pout_hold'):          # v0.3.5 的递包两段：不再随程序发布（备份在 desktop_pet_v035_backup）
    d = os.path.join(OUT, old)
    if os.path.isdir(d): shutil.rmtree(d)
total = 0; nbytes = 0
for name, src, nm, a, b, typ in SETS:
    d = os.path.join(OUT, name); os.makedirs(d, exist_ok=True)
    for f in os.listdir(d): os.remove(os.path.join(d, f))
    if typ == 'v6':
        allf = v6_frames(nm, a, b)
        frs = []
        for fr in allf[::STEP]:
            fr = fr.copy(); fr *= FADE[..., None]
            frs.append(fr)
    else:
        arr = np.load(os.path.join(src, nm + '.npy'), mmap_mode='r')
        idx = list(range(a, min(b, len(arr)), STEP))
        def get(i):
            fr = np.asarray(arr[i, y0:y1, x0:x1]).astype(np.float32)
            fr[..., 3] *= FADE
            fr[..., :3] *= fr[..., 3:4] / 255.0          # 预乘，混合/缩放都在预乘空间做，避免半透明边发黑发绿
            return fr
        frs = [get(i) for i in idx]
    if typ == 'loop':   # 无缝循环：最后 K 帧逐渐「回落」到首帧（=定格 hold 帧，也是各动作的起点），末帧→首帧不跳
        K = 12
        L = len(frs)
        for j in range(K):
            t = (j + 1) / (K + 1); t = t * t * (3 - 2 * t)
            frs[L - K + j] = frs[L - K + j] * (1 - t) + frs[0] * t
    n = 0
    for fr in frs:
        sm = cv2.resize(fr, (W, H), interpolation=cv2.INTER_AREA)      # 预乘空间缩小
        al = np.clip(sm[..., 3:4], 0, 255)
        rgb = np.where(al > 0.5, sm[..., :3] * 255.0 / np.maximum(al, 1e-3), 0)
        rgb = despill_f(np.clip(rgb, 0, 255))
        fr8 = np.dstack([rgb, al]).round().clip(0, 255).astype(np.uint8)
        im = Image.fromarray(fr8, 'RGBA')
        p = os.path.join(d, f'{n:03d}.webp')
        im.save(p, 'WEBP', quality=Q, alpha_quality=90, method=6)
        nbytes += os.path.getsize(p); n += 1
    man['anims'][name] = dict(n=n, type='clip' if typ == 'v6' else typ, src=nm)
    total += n; print(name, n)

# 2) 特效：汗滴 / 鼓腮气团（与 Day0 v18 渲染同款画法），位置换算到精灵坐标
def sweat(h):
    S = 4; w = int(h * 0.68); im = Image.new('RGBA', (w*S+8*S, h*S+8*S), (0,0,0,0)); dr = ImageDraw.Draw(im)
    cx = im.width/2; r = w*S*0.46; cy = im.height - r - 5*S
    poly = [(cx, 4*S)] + [(cx + r*math.sin(math.radians(t)), cy - r*math.cos(math.radians(t))) for t in range(35, 326, 5)]
    dr.polygon(poly, fill=(176,220,255,255), outline=(40,58,130,255), width=5*S)
    dr.ellipse((cx-r*0.55, cy-r*0.45, cx-r*0.12, cy+r*0.05), fill=(255,255,255,235))
    return im.resize((im.width//S, im.height//S), Image.LANCZOS).rotate(-12, resample=Image.BICUBIC, expand=True)
def puff(w):
    S = 4; h = int(w*0.62); im = Image.new('RGBA', (w*S+10*S, h*S+10*S), (0,0,0,0)); dr = ImageDraw.Draw(im)
    o = 5*S; NV = (40,58,130,255); cs = [(0.66,0.50,0.25),(0.84,0.40,0.17),(0.86,0.66,0.15)]
    for (x,y,r) in cs: R=r*w*S; dr.ellipse((o+x*w*S-R-4*S, o+y*h*S-R-4*S, o+x*w*S+R+4*S, o+y*h*S+R+4*S), fill=NV)
    for (x,y,r) in cs: R=r*w*S; dr.ellipse((o+x*w*S-R, o+y*h*S-R, o+x*w*S+R, o+y*h*S+R), fill=(255,255,255,255))
    for (y,l) in [(0.30,0.26),(0.52,0.34),(0.74,0.26)]:
        xa = o+0.40*w*S; xb = xa-l*w*S; yy = o+y*h*S
        dr.line((xb,yy,xa,yy), fill=NV, width=6*S)
        dr.ellipse((xb-3*S,yy-3*S,xb+3*S,yy+3*S), fill=NV); dr.ellipse((xa-3*S,yy-3*S,xa+3*S,yy+3*S), fill=NV)
    return im.resize((im.width//S, im.height//S), Image.LANCZOS)
fxd = os.path.join(ROOT, 'assets', 'fx'); os.makedirs(fxd, exist_ok=True)
k = sc * 1.25  # Day0 里特效尺寸是按原片坐标给的，桌宠里按精灵缩放比例略放大
sweat(int(100*k)).save(os.path.join(fxd, 'sweat.png'))
puff(int(118*k)).save(os.path.join(fxd, 'puff.png'))
def v2s(vx, vy): return [round((vx-x0)*sc, 1), round((vy-y0)*sc, 1)]
man['fx'] = dict(sweat=dict(img='sweat.png', at=v2s(505, 150)), puff=dict(img='puff.png', at=v2s(215, 300)))
json.dump(man, open(os.path.join(OUT, 'manifest.json'), 'w'), ensure_ascii=False, indent=1)
print('frames', total, 'bytes', nbytes, f'{nbytes/1024/1024:.2f}MB')
