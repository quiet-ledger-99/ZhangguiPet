import sys, glob, os, json, numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__)); from edgecheck import stats, despill_u8
ROOT = sys.argv[1]
man = json.load(open(os.path.join(ROOT, 'assets/sprites/manifest.json')))
items = []
for n, d in man['anims'].items():
    N = d['n']
    for i in sorted({0, N // 2, N - 1}):
        items.append((f'{n}#{i}', np.asarray(Image.open(f'{ROOT}/assets/sprites/{n}/{i:03d}.webp').convert('RGBA'))))
peek = [(os.path.basename(p), np.asarray(Image.open(p).convert('RGBA'))) for p in sorted(glob.glob(f'{ROOT}/assets/peek/*.png'))]
for label, its in [('sprites', items), ('peek', peek), ('sprites+despill', [(n, despill_u8(a)) for n, a in items]), ('peek+despill', [(n, despill_u8(a)) for n, a in peek])]:
    tot, rows = stats(its)
    print(label, len(its), {k: f'band {v[0]} 偏青绿 {100*v[1]/max(1,v[0]):.3f}% 绿溢 {100*v[2]/max(1,v[0]):.3f}%' for k, v in tot.items()})
