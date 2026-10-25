#!/usr/bin/env python3
"""v0.3.9 长脚 24fps 离屏回归；独立运行，不触碰真实设置或正式桌宠。
QT_QPA_PLATFORM=offscreen python tests/test_v039.py
覆盖：长脚 manifest 24fps、飘着 12fps 不变；长脚帧数 = 飘着 ×2；huff 用 huff_f；
播放倍率 fk（长脚 2、飘着 1）、计时器间隔、EXPR 帧号换算、模式切换时帧号换算、各表情在 24fps 下完整播完回待机。
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
TMP = tempfile.TemporaryDirectory(prefix='zg_test39_')
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
A = ROOT / 'assets'
LEGS = json.loads((A / 'sprites_legs/manifest.json').read_text(encoding='utf-8'))
FLO = json.loads((A / 'sprites/manifest.json').read_text(encoding='utf-8'))
N24 = {'idle': 144, 'smile': 144, 'smug': 144, 'thinking': 144,
       'smug_hold': 48, 'thinking_hold': 48, 'wave': 96, 'huff': 96}


class FakeLock:
    def poked(self): return False


class FakeScreen:
    def geometry(self): return QRect(0, 0, 1920, 1080)
    def availableGeometry(self): return QRect(0, 0, 1920, 1040)
    def name(self): return 'test_screen'


SCR = FakeScreen()


class Art(unittest.TestCase):
    def test_01_fps(self):
        self.assertEqual(LEGS['fps'], 24.0)
        self.assertEqual(FLO['fps'], 12.0)

    def test_02_frame_counts(self):
        self.assertEqual({k: v['n'] for k, v in LEGS['anims'].items()}, N24)
        for name, spec in LEGS['anims'].items():
            with self.subTest(anim=name):
                self.assertEqual(spec['n'], FLO['anims'][name]['n'] * 2)
                files = sorted(p.name for p in (A / 'sprites_legs' / name).glob('*.webp'))
                self.assertEqual(files, [f'{i:03d}.webp' for i in range(spec['n'])])

    def test_03_huff_is_huff_f(self):
        self.assertEqual(LEGS['anims']['huff']['src'], 'v4_huff_f')
        self.assertEqual(LEGS['anims']['huff']['type'], 'clip')
        for name, spec in LEGS['anims'].items():
            self.assertNotIn(spec['src'], ('v4_huff_c', 'v4_huff_d', 'v4_huff_b', 'v4_huff_a'), name)
        tool = (ROOT / 'tools/make_legs_v038.py').read_text(encoding='utf-8')
        self.assertIn("'huff': ('huff_f', 'clip')", tool)

    def test_04_version(self):
        self.assertEqual(Z.VERSION, '0.3.10')
        ps = (ROOT / 'packaging/build_win.ps1').read_text(encoding='utf-8')
        self.assertIn("[string]$Version = '0.3.10'", ps)
        self.assertIn('tests\\test_v039.py', ps)
        info = (ROOT / 'packaging/version_info.txt').read_text(encoding='utf-8')
        self.assertEqual(info.count('(0, 3, 10, 0)'), 2)
        self.assertNotIn('0.3.9', info)
        for f in ('README.md', 'CHANGELOG.md', '说明.txt'):
            self.assertIn('0.3.10', (ROOT / f).read_text(encoding='utf-8-sig'), f)


class Playback(unittest.TestCase):
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

    def test_05_multiplier_and_timer(self):
        pet = self.pet()
        self.assertEqual((pet.sp.fps, pet.sp.fk), (12.0, 1))
        self.assertEqual(pet.eseg(('smile', 0, 56)), ('smile', 0, 56))
        pet.anim_timer.start(int(1000 / pet.sp.fps))
        pet.set_legs(True)
        self.assertEqual((pet.sp.fps, pet.sp.fk), (24.0, 2))
        self.assertEqual(pet.eseg(('smile', 0, 56)), ('smile', 0, 112))
        self.assertEqual(pet.anim_timer.interval(), int(1000 / 24))
        pet.set_legs(False)
        self.assertEqual(pet.anim_timer.interval(), int(1000 / 12))
        pet.anim_timer.stop()

    def test_06_toggle_rescales_current_segment(self):
        pet = self.pet()
        pet.go_idle(); pet.fade = None; pet.prev = None
        for _ in range(30): pet.tick()
        self.assertEqual((pet.anim, pet.idx), ('idle', 30))
        pet.set_legs(True)
        self.assertEqual(pet.seg, ('idle', 0, 144)); self.assertEqual(pet.idx, 60)
        pet.set_legs(False)
        self.assertEqual(pet.seg, ('idle', 0, 72)); self.assertEqual(pet.idx, 30)
        pet.play_expr('smile')
        for _ in range(10): pet.tick()
        pet.set_legs(True)
        self.assertEqual((pet.mode, pet.seg, pet.idx), ('enter', ('smile', 0, 112), 20))

    def test_07_every_expression_full_cycle_at_24fps(self):
        pet = self.pet(); pet.set_legs(True); pet.set_scale(1)
        for expr, spec in Z.EXPR.items():
            with self.subTest(expr=expr):
                pet.go_idle(); pet.fade = None; pet.prev = None
                pet.last_touch = 0
                pet.play_expr(expr, hold=0)
                enter = spec['enter']
                self.assertEqual(pet.seg, (enter[0], enter[1] * 2, enter[2] * 2))
                seen, modes = set(), []
                for _ in range(600):
                    pet.tick()
                    seen.add(pet.anim); modes.append(pet.mode)
                    self.assertLess(pet.idx, pet.sp.n(pet.anim))
                    self.assertEqual((pet.cur_img.width(), pet.cur_img.height()), (375, 614))
                    if pet.mode == 'idle':
                        break
                self.assertIn(spec['hold'][0], seen)
                self.assertIn('hold', modes)
                self.assertEqual(pet.mode, 'idle', '播完回到待机')

    def test_08_floating_still_12fps_same_duration(self):
        pet = self.pet(); pet.set_scale(1)
        e = Z.EXPR['smile']['enter']
        pet.go_idle(); pet.fade = None; pet.prev = None
        pet.play_expr('smile', hold=0)
        self.assertEqual(pet.seg, e)
        n = 0
        while pet.mode == 'enter' and n < 1000:
            pet.tick(); n += 1
        self.assertEqual(n, e[2] - e[1])
        pet.set_legs(True)
        pet.go_idle(); pet.play_expr('smile', hold=0)
        n = 0
        while pet.mode == 'enter' and n < 1000:
            pet.tick(); n += 1
        self.assertEqual(n, 2 * (e[2] - e[1]))      # 24fps 帧数 ×2，时长和 12fps 一样


if __name__ == '__main__':
    unittest.main(verbosity=2)
