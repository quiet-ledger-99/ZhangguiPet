#!/usr/bin/env python3
"""离屏压力测试：所有台词（含连戳、按时间的）各触发一次并走完 进入→停留→回待机，再连点打断；
统计显示帧之间的跳变：整体最大、切换淡化期间按目标动画分组的最大值。
注意（v0.3.5）：这个脚本还是按 v0.3 早期接口写的（q.LINES、q.Pet() 等），对 v0.3.4/0.3.5 跑不起来，
不能当作本版本通过压力测试的依据；重写排在下一轮。"""
import os, sys, random
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen'); os.environ['ZHANGGUI_PET_DEBUG'] = '1'
os.environ.setdefault('ZHANGGUI_PET_HOLD', '2')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import zhanggui_pet as q
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from collections import defaultdict
pool = q.LINES + q.TEASE_LINES + [x for _, x in q.TIME_LINES]
q.ORDER[:] = list(range(len(pool))) + [random.Random(1).randrange(len(pool)) for _ in range(12)]
app = QApplication([]); pet = q.Pet(); pet.show()
t = 300
for k in range(len(pool)): QTimer.singleShot(t, pet.on_click); t += 11000                 # 完整走一遍
for k in range(12): QTimer.singleShot(t, pet.on_click); t += random.Random(k).choice([150, 400, 900, 2500])  # 连点打断
QTimer.singleShot(t + 12000, app.quit); app.exec()
J = pet.jumps
print(f'显示帧 {len(J)}，最大跳变 {max(j[2] for j in J):.2f}')
g = defaultdict(float); g2 = defaultdict(float)
for a, i, d, f in J:
    (g if f > 0 else g2)[a] = max((g if f > 0 else g2)[a], d)
for a in sorted(set(g) | set(g2)):
    print(f'  {a:14s} 淡化中最大 {g.get(a, 0):5.2f} | 正常播放最大 {g2.get(a, 0):5.2f}')
