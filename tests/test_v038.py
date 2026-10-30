#!/usr/bin/env python3
"""v0.3.8 长脚重画离屏回归；独立运行，不触碰真实设置或正式桌宠。
QT_QPA_PLATFORM=offscreen python tests/test_v038.py
覆盖：8 段整身重画素材（含 wave/huff 有腿）、脚底/脚中一致、头框和画面相符、遮罩覆盖每一帧、
躲边图 375 宽且墙侧不动、切换模式脚底不动、各表情在长脚模式能完整播放、飘着模式素材与几何和 v0.3.7 一致。
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['ZHANGGUI_PET_NO_AUDIO'] = '1'
os.environ['ZHANGGUI_PET_NO_OPEN'] = '1'
os.environ['ZHANGGUI_PET_NO_DIALOG'] = '1'
os.environ['ZHANGGUI_PET_SIM_NO_TRAY'] = '1'
os.environ.pop('ZHANGGUI_PET_DEBUG', None)
os.environ.pop('ZHANGGUI_PET_ORDER', None)
TMP = tempfile.TemporaryDirectory(prefix='zg_test38_')
os.environ['ZHANGGUI_PET_CONFIG_DIR'] = TMP.name
idle = Path(TMP.name, 'idle.txt'); idle.write_text('0')
os.environ['ZHANGGUI_PET_SIM_IDLE_FILE'] = str(idle)
os.environ['ZHANGGUI_PET_SIM_FULLSCREEN_FILE'] = str(Path(TMP.name, 'fs.flag'))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import zhanggui_pet as Z
import pet_platform as P
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QEvent, QTimer
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
A = ROOT / 'assets'
W, H, SOLE_Y, FOOT_X = 375, 614, 600, 187.5
ANIMS = ('idle', 'smile', 'smug', 'thinking', 'smug_hold', 'thinking_hold', 'wave', 'huff',
         'stretch', 'yawn', 'nod', 'nap')   # v0.3.11：+ P0 四动作（返工帧，24fps）
# assets/sprites、masks、peek、fx（飘着模式用的全部素材）的合并哈希：v0.3.9 发布包合并哈希（含发布处理）
FLOAT_ASSETS_SHA = '740e2715dbf4cb2ca8eff2e8c2a20e4bc41cf87b8064dda259e80fa535258f94'  # 飘着躲边：右侧 1x 换成交回 A，@2x 接入 B 的 502×760；v0.3.11 加 P0 四动作（stretch 高画布）+ manifest，旧文件未动


class Alpha:
    """只取 alpha 通道（不依赖 numpy，打包用的 Windows venv 里没有它）。"""
    def __init__(self, path):
        im = QImage(str(path)).convertToFormat(QImage.Format_RGBA8888)
        self.w, self.h = im.width(), im.height()
        raw = bytes(im.constBits())[:im.sizeInBytes()]
        bpl = im.bytesPerLine()
        self.a = b''.join(raw[y * bpl:y * bpl + self.w * 4][3::4] for y in range(self.h))

    def rows(self, thr, x0=0, x1=None):
        x1 = self.w if x1 is None else x1
        return [y for y in range(self.h) if max(self.a[y * self.w + x0:y * self.w + x1]) > thr]

    def cols(self, thr, y0=0, y1=None):
        y1 = self.h if y1 is None else y1
        sub = self.a[y0 * self.w:y1 * self.w]
        return [x for x in range(self.w) if sub[x::self.w] and max(sub[x::self.w]) > thr]

    def bits(self):
        return int.from_bytes(self.a.translate(bytes([0] + [1] * 255)), 'big')

    def fill(self):
        return 1 - self.a.count(0) / len(self.a)


class FakeLock:
    def poked(self): return False


class FakeScreen:
    def geometry(self): return QRect(0, 0, 1920, 1080)
    def availableGeometry(self): return QRect(0, 0, 1920, 1040)
    def name(self): return 'test_screen'


SCR = FakeScreen()


class LegsArt(unittest.TestCase):
    man = json.loads((A / 'sprites_legs/manifest.json').read_text(encoding='utf-8'))

    def test_01_manifest(self):
        m = self.man
        self.assertEqual((m['w'], m['h'], m['padx'], m['foot_y'], m['foot_x']), (W, H, 62, SOLE_Y, FOOT_X))
        self.assertEqual(tuple(m['anims']), ANIMS)
        for name in ANIMS:
            self.assertNotIn('legs', m['anims'][name])          # 不再有「无腿」标记

    def test_02_every_anim_has_legs_and_planted_feet(self):
        for name in ANIMS:
            n = self.man['anims'][name]['n']
            for i in sorted({0, n // 2, n - 1}):
                with self.subTest(anim=name, frame=i):
                    a = Alpha(A / 'sprites_legs' / name / f'{i:03d}.webp')
                    self.assertEqual((a.h, a.w), (H, W))
                    rows = a.rows(40)
                    self.assertLessEqual(abs(max(rows) - SOLE_Y), 2)                     # 鞋底在 y=600
                    # 帽顶贴近画布顶，但没出画布；v0.3.11 打盹低头，帽顶会往下掉十几像素
                    self.assertLessEqual(min(rows), 24 if name == 'nap' else 6)
                    feet = a.cols(128, SOLE_Y - 30, SOLE_Y)
                    self.assertGreater(len(feet), 20)                                    # 下面确实有腿/鞋
                    self.assertLessEqual(abs((min(feet) + max(feet)) / 2 - FOOT_X), 6)
                    self.assertFalse(a.cols(40) and (min(a.cols(40)) < 2 or max(a.cols(40)) > W - 3))   # 左右没贴画布边被裁

    def test_03_head_box_matches_art(self):
        ux, uy, uw, uh = (self.man[k] for k in ('upper_x', 'upper_y', 'upper_w', 'upper_h'))
        for name in ('idle', 'smile', 'smug_hold', 'thinking_hold'):
            a = Alpha(A / 'sprites_legs' / name / '000.webp')
            head = a.cols(128, uy, uy + int(uh * 0.30))
            c = (min(head) + max(head)) / 2
            self.assertLessEqual(abs(c - (ux + uw / 2)), 12, name)               # 头框横向对着帽子/头
            self.assertGreaterEqual(min(a.rows(40)), uy - 2, name)
        for k, fx in self.man['fx'].items():
            self.assertTrue(ux <= fx['at'][0] <= ux + uw and uy <= fx['at'][1] <= uy + uh, k)

    def test_04_masks_cover_every_frame(self):
        for name in ANIMS:
            ma = Alpha(A / 'masks_legs' / (name + '.png'))
            self.assertEqual((ma.h, ma.w), (H, W))
            m = ma.bits()
            for p in sorted((A / 'sprites_legs' / name).glob('*.webp')):
                with self.subTest(frame=p.parent.name + '/' + p.name):
                    self.assertEqual(Alpha(p).bits() | m, m)                     # 帧里有像素的地方遮罩都有
            self.assertLess(ma.fill(), 0.85 if name == 'stretch' else 0.62)      # 不是整块矩形（伸懒腰两臂张开，并集大些）

    def test_05_peek_padded_wall_side_kept(self):
        for p in sorted((A / 'peek_legs').glob('*.png')):
            a = Alpha(p)
            side = p.stem.split('_')[-1]
            self.assertEqual((a.h, a.w), (H, W), p.name)
            cols = a.cols(0)
            if side == 'left':
                self.assertEqual(min(a.cols(128)), 0); self.assertLess(max(cols), W - 44)
            elif side == 'right':
                self.assertEqual(max(a.cols(128)), W - 1); self.assertGreaterEqual(min(cols), 44)
            else:
                rows = a.rows(128)
                self.assertEqual(min(rows) if side == 'top' else max(rows), 0 if side == 'top' else H - 1)
                self.assertTrue(min(cols) >= 22 and max(cols) < W - 22)

    def test_06_floating_assets_unchanged(self):
        h = hashlib.sha256()
        for d in ('assets/sprites', 'assets/masks', 'assets/peek', 'assets/fx'):
            for r, ds, fs in sorted(os.walk(ROOT / d)):
                ds.sort()
                for f in sorted(fs):
                    p = os.path.join(r, f)
                    h.update(os.path.relpath(p, ROOT).replace(os.sep, '/').encode()); h.update(Path(p).read_bytes())
        self.assertEqual(h.hexdigest(), FLOAT_ASSETS_SHA)


class LegsPet(unittest.TestCase):
    def setUp(self):
        self.pets = []
        self.log = P.Log(None)

    def tearDown(self):
        for pet in self.pets:
            for timer in pet.findChildren(QTimer): timer.stop()
            pet.close(); pet.deleteLater()

    def pet(self, st=None):
        st = P.Settings(None, self.log) if st is None else st
        st['first_run_done'] = True
        pet = Z.Pet(TMP.name, self.log, st, FakeLock())
        self.pets.append(pet)
        pet.show()
        pet.brain_timer.stop(); pet.anim_timer.stop()
        pet.screen_of = lambda pt: SCR
        pet.occupied = lambda pt: SCR.geometry().contains(pt)
        pet.set_anchor(QPoint(960, 1000))
        pet.compose()
        return pet

    def test_07_floating_geometry_same_as_v037(self):
        pet = self.pet()
        self.assertEqual((pet.sp.ux, pet.sp.uy, pet.sp.uw, pet.sp.uh), (0, 0, 251, 380))
        for scale in (0.2, 0.75, 1, 1.5):
            pet.set_scale(scale)
            sw, sh, s, ox, oy = pet.sp.sw, pet.sp.sh, pet.sp.s, pet.ox, pet.oy
            self.assertEqual(pet.W, max(sw + 40, 340))
            self.assertEqual(pet.fx_rect('zzz'), QRect(int(ox + sw * 0.66), int(oy - 10 * s), int(70 * s) + 20, int(80 * s) + 20))
            self.assertEqual(pet.fx_rect('excl'), QRect(int(ox + sw * 0.74), int(oy + 4 * s), int(30 * s) + 12, int(44 * s) + 12))
            self.assertEqual(pet.hearts_rect(), QRect(int(ox + sw * .2), int(oy - 30 * s - 12), int(sw * .6), int(sh * .22 + 40 * s + 12)))
            pet.badge_text = '计时 00:01'
            self.assertEqual(pet.badge_rect().y(), oy + sh - 30)
            pet.badge_text = None
            sweat = json.loads((A / 'sprites/manifest.json').read_text(encoding='utf-8'))['fx']['sweat']['at']
            self.assertEqual(pet.sp.fx['sweat'][1], (sweat[0] * s, sweat[1] * s))
            for y, zone in ((-5, 'head'), (int(sh * .29), 'head'), (int(sh * .31), 'body')):
                local = QPoint(ox + sw // 2, oy + y)
                pet.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(local), QPointF(pet.mapToGlobal(local)),
                                                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
                self.assertEqual(pet.zone, zone, (scale, y))
                pet.cancel_interaction()

    def test_08_legs_geometry_and_head_zone(self):
        pet = self.pet(); pet.set_legs(True)
        for scale in (0.5, 0.75, 1.0):
            pet.set_scale(scale)
            s = pet.sp.s
            self.assertEqual((pet.sp.sw, pet.sp.sh), (round(W * s), round(H * s)))
            self.assertEqual((pet.sp.ux, pet.sp.uy), (58 * s, 0))
            for fx, y, zone in ((.5, .05, 'head'), (.5, .28, 'head'), (.5, .4, 'body'), (.5, 1.4, 'body'), (.05, .1, 'body')):
                local = QPoint(int(pet.ox + pet.sp.ux + pet.sp.uw * fx), int(pet.oy + pet.sp.uy + pet.sp.uh * y))
                pet.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(local), QPointF(pet.mapToGlobal(local)),
                                                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
                self.assertEqual(pet.zone, zone, (scale, fx, y))
                pet.cancel_interaction()
            # 头区（帽子到下巴）落在画面里有人的地方
            hz = QRect(int(pet.ox + pet.sp.ux + pet.sp.uw * .15), pet.oy, int(pet.sp.uw * .7), int(pet.sp.uh * .3))
            self.assertTrue(pet.sp.mask('idle').translated(pet.ox, pet.oy).intersects(hz))
            pet.badge_text = '计时 00:01'
            self.assertEqual(pet.badge_rect().y(), int(pet.oy) + pet.sp.uh - 30)   # 徽章在上半身框底部，不掉到腿上
            pet.badge_text = None

    def test_09_toggle_keeps_feet_at_all_scales(self):
        st = P.Settings(TMP.name, self.log)
        for sf, sl in ((1.0, .75), (.5, 1.2), (1.5, .3)):
            st['legs'] = False; st['scale'] = sf; st['scale_legs'] = sl
            pet = self.pet(st)
            a = pet.anchor()
            for _ in range(3):
                pet.set_legs(True)
                self.assertEqual((pet.sp.w, pet.sp.s), (W, sf))      # nolegs-samesize：沿用飘着的大小
                self.assertLessEqual((pet.anchor() - a).manhattanLength(), 1)
                pet.set_legs(False)
                self.assertEqual((pet.sp.w, pet.sp.s), (251, sf))
                self.assertLessEqual((pet.anchor() - a).manhattanLength(), 1)

    def test_10_every_expression_plays_in_legs_mode(self):
        pet = self.pet(); pet.set_legs(True); pet.set_scale(1)
        for expr, spec in Z.EXPR.items():
            with self.subTest(expr=expr):
                pet.go_idle(); pet.fade = None; pet.prev = None
                pet.play_expr(expr)
                seen = set()
                for _ in range(120 * pet.sp.fk):          # v0.3.9：长脚 24fps，帧数翻倍，tick 次数按倍率放大（时长不变）
                    pet.tick()
                    seen.add(pet.anim)
                    self.assertEqual((pet.cur_img.width(), pet.cur_img.height()), (W, H))
                self.assertIn(spec['enter'][0], seen)
                self.assertIn(spec['hold'][0], seen)


if __name__ == '__main__':
    unittest.main(verbosity=2)
