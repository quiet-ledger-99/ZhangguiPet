"""v0.3.6 交付前自查：所有精灵帧（每段首/中/尾帧）+ 所有躲边立绘，在 4 种背景上统计边缘带的偏青绿和绿溢。
用法：python tools/art036/stats_v036.py [项目目录] [--all]   （--all = 每一帧都测）"""
import sys, os, glob, json
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edgecheck import stats
ROOT = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALL = '--all' in sys.argv
man = json.load(open(os.path.join(ROOT, 'assets/sprites/manifest.json')))
groups = {}
for n, d in man['anims'].items():
    N = d['n']; idx = range(N) if ALL else sorted({0, N // 2, N - 1})
    groups.setdefault('new' if n in ('wave', 'huff') else 'kept', []).extend(
        (f'{n}#{i}', np.asarray(Image.open(f'{ROOT}/assets/sprites/{n}/{i:03d}.webp').convert('RGBA'))) for i in idx)
for p in sorted(glob.glob(f'{ROOT}/assets/peek/*.png')):
    nm = os.path.basename(p)
    groups.setdefault('peek_new' if ('left' in nm or 'top' in nm or 'bottom' in nm) else 'peek_right', []).append(
        (nm, np.asarray(Image.open(p).convert('RGBA'))))
res = {}
for g, its in groups.items():
    tot, rows = stats(its)
    res[g] = {'n': len(its), **{k: dict(band=v[0], teal_pct=round(100 * v[1] / max(1, v[0]), 3), green_pct=round(100 * v[2] / max(1, v[0]), 3)) for k, v in tot.items()}}
    worst = max(rows, key=lambda r: r[3] + r[4])
    print(f'{g:10s} 张数 {len(its):3d}', ' | '.join(f'{k}: 偏青绿 {v["teal_pct"]:.3f}% 绿溢 {v["green_pct"]:.3f}%' for k, v in res[g].items() if k != 'n'),
          '| 最差', worst[0], worst[1], worst[3], worst[4])
json.dump(res, open(os.path.join(ROOT, 'v036_review', 'edge_stats.json'), 'w'), ensure_ascii=False, indent=1)
