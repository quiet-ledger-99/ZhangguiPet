#!/usr/bin/env python3
"""nolegs v8：切换有腿/藏腿时立绘显示大小一致的离屏回归；独立运行，不触碰真实设置或正式桌宠。
QT_QPA_PLATFORM=offscreen python tests/test_samesize.py
覆盖：切换前后上半身像素大小相同、比例不变、脚底中心不动、出腿时整个人往上长（头顶变高）、
贴屏幕底时出腿也整个可见、任一模式调大小两边同步、旧设置（两套大小）启动时按当前模式迁移、重启保持。
"""
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
TMP = tempfile.TemporaryDirectory(prefix='zg_test_samesize_')
os.environ['ZHANGGUI_PET_CONFIG_DIR'] = TMP.name
idle = Path(TMP.name, 'idle.txt'); idle.write_text('0')
os.environ['ZHANGGUI_PET_SIM_IDLE_FILE'] = str(idle)
os.environ['ZHANGGUI_PET_SIM_FULLSCREEN_FILE'] = str(Path(TMP.name, 'fs.flag'))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import zhanggui_pet as Z
import pet_platform as P
from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


class FakeLock:
    def poked(self): return False


class FakeScreen:
    def geometry(self): return QRect(0, 0, 1920, 1080)
    def availableGeometry(self): return QRect(0, 0, 1920, 1040)
    def name(self): return 'test_screen'


SCR = FakeScreen()


class SameSize(unittest.TestCase):
    def setUp(self):
        self.pets = []
        self.log = P.Log(None)

    def tearDown(self):
        for pet in self.pets:
            for timer in pet.findChildren(QTimer): timer.stop()
            pet.close(); pet.deleteLater()

    def pet(self, st=None, anchor=QPoint(960, 1000)):
        st = P.Settings(None, self.log) if st is None else st
        st['first_run_done'] = True
        pet = Z.Pet(TMP.name, self.log, st, FakeLock())
        self.pets.append(pet)
        pet.show()
        pet.brain_timer.stop(); pet.anim_timer.stop()
        pet.screen_of = lambda pt: SCR
        pet.occupied = lambda pt: SCR.geometry().contains(pt)
        pet.set_anchor(anchor)
        pet.compose()
        return pet

    def upper(self, pet):
        r = pet.sprite_rect()
        return QRect(r.x() + pet.sp.ux, r.y() + pet.sp.uy, pet.sp.uw, pet.sp.uh)

    def test_01_upper_body_same_size_and_feet_fixed(self):
        for s in (0.3, 0.5, 0.75, 0.85, 1.0, 1.2):
            with self.subTest(scale=s):
                st = P.Settings(None, self.log); st['legs'] = False; st['scale'] = s; st['scale_legs'] = .75
                pet = self.pet(st)
                a, u0, top0 = pet.anchor(), self.upper(pet), pet.sprite_rect().top()
                for _ in range(3):
                    pet.set_legs(True)
                    u1 = self.upper(pet)
                    self.assertEqual(pet.sp.s, s)
                    self.assertLessEqual(abs(u1.width() - u0.width()), 1)
                    self.assertLessEqual(abs(u1.height() - u0.height()), 1)
                    self.assertLessEqual((pet.anchor() - a).manhattanLength(), 1)
                    self.assertLess(pet.sprite_rect().top(), top0)          # 出腿：整个人往上长
                    self.assertLess(u1.top(), u0.top())
                    self.assertEqual((pet.st['scale'], pet.st['scale_legs']), (s, s))
                    pet.set_legs(False)
                    self.assertEqual(pet.sp.s, s)
                    self.assertEqual((self.upper(pet).width(), self.upper(pet).height()), (u0.width(), u0.height()))
                    self.assertLessEqual((pet.anchor() - a).manhattanLength(), 1)
                    self.assertLessEqual(abs(pet.sprite_rect().top() - top0), 1)   # 收腿：落回原位

    def test_02_legs_fully_visible_near_bottom(self):
        g = SCR.availableGeometry()
        for s in (0.5, 1.0, 1.5):
            with self.subTest(scale=s):
                st = P.Settings(None, self.log); st['legs'] = False; st['scale'] = s
                pet = self.pet(st, anchor=QPoint(960, g.bottom()))
                pet.ensure_visible()
                pet.set_legs(True)
                r = pet.sprite_rect()
                self.assertTrue(g.contains(r.topLeft()) or r.height() > g.height(), (r, g))
                self.assertLessEqual(r.bottom(), g.bottom() + 1)
                self.assertEqual(pet.sp.s, s)

    def test_03_resize_syncs_both_modes_and_restart(self):
        st = P.Settings(TMP.name, self.log); st['legs'] = True; st['scale'] = 1.0; st['scale_legs'] = .6
        pet = self.pet(st)
        self.assertEqual((pet.sp.s, st['scale'], st['scale_legs']), (.6, .6, .6))   # 旧设置迁移：以当前模式为准
        pet.set_scale(.9)
        self.assertEqual((st['scale'], st['scale_legs']), (.9, .9))
        pet.set_legs(False)
        self.assertEqual(pet.sp.s, .9)
        pet.set_scale(.7)
        pet.set_legs(True)
        self.assertEqual(pet.sp.s, .7)
        self.assertTrue(st.save())
        saved = json.loads(Path(st.path).read_text(encoding='utf-8'))
        self.assertEqual((saved['scale'], saved['scale_legs'], saved['legs']), (.7, .7, True))
        restarted = self.pet(P.Settings(TMP.name, self.log))
        self.assertEqual(restarted.sp.s, .7)
        restarted.set_legs(False)
        self.assertEqual(restarted.sp.s, .7)

    def test_04_pending_slider_carries_over(self):
        pet = self.pet()
        pet.pending_scale = .55; pet.scale_timer.start(10000)
        pet.set_legs(True)
        self.assertFalse(pet.scale_timer.isActive())
        self.assertEqual((pet.sp.s, pet.st['scale'], pet.st['scale_legs']), (.55, .55, .55))

    def test_05_peek_toggle_keeps_scale(self):
        pet = self.pet(); pet.set_scale(.8)
        for side in ('left', 'right', 'bottom'):
            with self.subTest(side=side):
                pet.apply_peek(side, animate=False)
                pet.set_legs(not pet.st['legs'])
                self.assertEqual(pet.sp.s, .8)
                pet.leave_peek()


if __name__ == '__main__':
    unittest.main(verbosity=2)
