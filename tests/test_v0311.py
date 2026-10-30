#!/usr/bin/env python3
"""v0.3.11 P0 四动作（伸懒腰 / 打哈欠 / 点头 / 打盹）离屏回归；独立运行，不触碰真实设置或正式桌宠。
QT_QPA_PLATFORM=offscreen python tests/test_v0311.py
覆盖：两套 manifest（飘着 24fps tall stretch 251x416 + anchor_offset_y 36、nap loop_from 48/64）、帧文件与遮罩尺寸、
单动作 fps 倍率 akf、节拍 frame_ms、高画布往上画、四个动作在两种模式下完整播完、打盹呼吸只在 loop_from 之后循环、
碰一下醒、台词类别、联网人格默认关且不写死 Mac 路径。
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['ZHANGGUI_PET_NO_AUDIO'] = '1'
os.environ['ZHANGGUI_PET_NO_OPEN'] = '1'
os.environ['ZHANGGUI_PET_NO_DIALOG'] = '1'
os.environ['ZHANGGUI_PET_SIM_NO_TRAY'] = '1'
os.environ.pop('ZHANGGUI_PET_DEBUG', None)
os.environ.pop('ZHANGGUI_PET_ONLINE', None)
TMP = tempfile.TemporaryDirectory(prefix='zg_test311_')
os.environ['ZHANGGUI_PET_CONFIG_DIR'] = TMP.name
idle = Path(TMP.name, 'idle.txt'); idle.write_text('0')
os.environ['ZHANGGUI_PET_SIM_IDLE_FILE'] = str(idle)
os.environ['ZHANGGUI_PET_SIM_FULLSCREEN_FILE'] = str(Path(TMP.name, 'fs.flag'))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import zhanggui_pet as Z
import pet_platform as P
import pet_lines as PL
from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMenu

app = QApplication.instance() or QApplication([])
A = ROOT / 'assets'
FLO = json.loads((A / 'sprites/manifest.json').read_text(encoding='utf-8'))
LEGS = json.loads((A / 'sprites_legs/manifest.json').read_text(encoding='utf-8'))
NEW = ('stretch', 'yawn', 'nod', 'nap')
N = {'stretch': 120, 'yawn': 96, 'nod': 48, 'nap': 144}


class FakeLock:
    def poked(self): return False


class FakeScreen:
    def geometry(self): return QRect(0, 0, 1920, 1080)
    def availableGeometry(self): return QRect(0, 0, 1920, 1040)
    def name(self): return 'test_screen'


SCR = FakeScreen()


class Art(unittest.TestCase):
    def test_01_float_manifest(self):
        self.assertEqual(FLO['fps'], 12.0)                       # 旧动作还是 12fps
        s = FLO['anims']['stretch']
        self.assertEqual((s['n'], s['type'], s['fps'], s['w'], s['h'], s['anchor_offset_y']), (120, 'clip', 24, 251, 416, 36))
        self.assertEqual(s['h'] - s['anchor_offset_y'], FLO['h'])
        self.assertEqual((FLO['anims']['yawn']['type'], FLO['anims']['nod']['type'], FLO['anims']['nap']['type']), ('clip', 'loop', 'loop'))
        self.assertEqual(FLO['anims']['nap']['loop_from'], 48)
        for n in NEW:
            self.assertEqual((FLO['anims'][n]['n'], FLO['anims'][n]['fps']), (N[n], 24), n)

    def test_02_legs_manifest(self):
        self.assertEqual(LEGS['fps'], 24.0)
        self.assertEqual(LEGS['anims']['nap']['loop_from'], 64)
        for n in NEW:
            self.assertEqual(LEGS['anims'][n]['n'], N[n], n)
            self.assertNotIn('anchor_offset_y', LEGS['anims'][n])

    def test_03_frames_and_masks(self):
        for spr, msk, man in (('sprites', 'masks', FLO), ('sprites_legs', 'masks_legs', LEGS)):
            for n in NEW:
                with self.subTest(spr=spr, anim=n):
                    spec = man['anims'][n]
                    size = (spec.get('w', man['w']), spec.get('h', man['h']))
                    files = sorted(p.name for p in (A / spr / n).glob('*.webp'))
                    self.assertEqual(files, [f'{i:03d}.webp' for i in range(spec['n'])])
                    for i in (0, spec['n'] // 2, spec['n'] - 1):
                        im = QImage(str(A / spr / n / f'{i:03d}.webp'))
                        self.assertEqual((im.width(), im.height()), size)
                    m = QImage(str(A / msk / (n + '.png')))
                    self.assertEqual((m.width(), m.height()), size)

    def test_04_first_last_match_idle(self):
        """首尾对齐：除 nap 末帧（睡着）外，首末帧和待机第 0 帧一致（tall stretch 比较下面 380 行）。"""
        # 只用 QImage（PySide6 已在），不依赖 numpy/Pillow：Windows 打包 venv 里两者都没有
        def premul(path, h=None):
            im = QImage(str(path)).convertToFormat(QImage.Format_RGBA8888)
            w, H = im.width(), im.height()
            h = H if h is None else h
            raw = bytes(im.constBits())[:im.sizeInBytes()]
            bpl = im.bytesPerLine()
            px = b''.join(raw[y * bpl:y * bpl + w * 4] for y in range(H - h, H))
            return [px[k + c] * px[k + 3] / 255.0 for k in range(0, len(px), 4) for c in range(3)], (w, h)

        for spr in ('sprites', 'sprites_legs'):
            idle0, isz = premul(A / spr / 'idle' / '000.webp')
            for n in NEW:
                last = N[n] - 1
                for i in ((0,) if n == 'nap' else (0, last)):
                    with self.subTest(spr=spr, anim=n, frame=i):
                        im, sz = premul(A / spr / n / f'{i:03d}.webp', isz[1])
                        self.assertEqual(sz, isz)
                        d = sum(abs(x - y) for x, y in zip(im, idle0)) / len(idle0)
                        self.assertLess(d, 3.0)

    def test_05_lines(self):
        self.assertGreater(PL.check(), 140)                      # 断言式检查：重复 id、表情名、禁用词
        for cat, expr in (('stretch', 'stretch'), ('yawn', 'yawn'), ('ack', 'nod'), ('nap', 'nap')):
            self.assertTrue(PL.LINES.get(cat), cat)
            self.assertTrue(all(l.expr == expr for l in PL.LINES[cat]), cat)
        for e in NEW:
            self.assertIn(e, Z.EXPR)

    def test_06_online_off_and_portable(self):
        src = (ROOT / 'pet_online.py').read_text(encoding='utf-8')
        for bad in ('/Users/', 'launchctl', 'LaunchAgents', 'qianweitao'):
            self.assertNotIn(bad, src)
        self.assertNotIn('pet_online', sys.modules)              # 默认关：根本不导入


class Playback(unittest.TestCase):
    def setUp(self):
        self.pets = []
        self.log = P.Log(None)

    def tearDown(self):
        for pet in self.pets:
            for timer in pet.findChildren(QTimer): timer.stop()
            pet.close(); pet.deleteLater()

    def pet(self, legs=False):
        st = P.Settings(None, self.log)
        st['first_run_done'] = True
        pet = Z.Pet(TMP.name, self.log, st, FakeLock())
        self.pets.append(pet)
        pet.show()
        pet.brain_timer.stop(); pet.anim_timer.stop()
        pet.screen_of = lambda pt: SCR
        pet.occupied = lambda pt: SCR.geometry().contains(pt)
        pet.set_anchor(QPoint(960, 1000))
        if legs:
            pet.set_legs(True)
        pet.set_scale(1)
        pet.compose()
        return pet

    def test_01_akf_and_frame_ms(self):
        pet = self.pet()
        self.assertEqual([pet.sp.akf(n) for n in ('idle', 'smile', 'stretch', 'yawn', 'nod', 'nap')], [1, 1, 2, 2, 2, 2])
        self.assertEqual(pet.eseg(Z.EXPR['stretch']['enter']), ('stretch', 0, 120))
        self.assertEqual(pet.eseg(Z.EXPR['smile']['enter']), Z.EXPR['smile']['enter'])
        pet.go_idle()
        self.assertEqual(pet.frame_ms(), int(1000 / 12))
        pet.play_expr('stretch', hold=0)
        self.assertEqual(pet.frame_ms(), int(1000 / 24))
        pet.away = True
        self.assertEqual(pet.frame_ms(), 250)
        pet.away = False
        pet.set_legs(True)
        self.assertEqual(pet.sp.akf('stretch'), 2)
        self.assertEqual(pet.sp.akf('idle'), 2)

    def test_02_tall_stretch_draws_upward(self):
        pet = self.pet()
        pet.go_idle(); pet.fade = None; pet.prev = None
        pet.compose()
        self.assertEqual(pet.cur_top, 0)
        geo_idle = pet.geometry()
        pet.play_expr('stretch', hold=0); pet.fade = None; pet.prev = None
        pet.tick(); pet.compose()
        s = pet.sp.s
        self.assertEqual(pet.sp.top('stretch'), round(36 * s))
        self.assertEqual(pet.cur_img.height() - pet.sp.sh, round(36 * s))
        self.assertEqual(pet.cur_top, round(36 * s))
        self.assertEqual(pet.cur_img.width(), pet.sp.sw)         # 不缩放不拉伸
        # 脚底锚点不动
        self.assertEqual(pet.geometry().bottom(), geo_idle.bottom())

    def full_cycle(self, pet, expr):
        pet.go_idle(); pet.fade = None; pet.prev = None
        pet.play_expr(expr, hold=0.01 if expr != 'nap' else 0.3)
        seen_hold = False
        for _ in range(3000):
            pet.tick()
            self.assertLess(pet.idx, pet.sp.n(pet.anim))
            self.assertGreaterEqual(pet.idx, 0)
            seen_hold |= pet.mode == 'hold'
            if pet.mode == 'idle':
                break
            time.sleep(0.0005)
        return seen_hold

    def test_03_every_new_action_full_cycle_both_modes(self):
        for legs in (False, True):
            pet = self.pet(legs)
            for e in NEW:
                with self.subTest(legs=legs, expr=e):
                    self.full_cycle(pet, e)
                    self.assertEqual(pet.mode, 'idle', '播完回到待机')

    def test_04_nap_breath_loops_from_loop_from(self):
        for legs, lf in ((False, 48), (True, 64)):
            pet = self.pet(legs)
            pet.go_idle(); pet.fade = None; pet.prev = None
            pet.play_expr('nap', hold=60)
            while pet.mode == 'enter':
                pet.tick()
            self.assertEqual(pet.mode, 'hold')
            idxs = []
            for _ in range(400):
                pet.tick(); idxs.append(pet.idx)
            self.assertGreaterEqual(min(idxs), lf if legs else 48, legs)
            self.assertEqual(max(idxs), 143)
            # 正向循环：除了回到起点那一下，帧号都在增加
            back = [i for i in range(1, len(idxs)) if idxs[i] < idxs[i - 1]]
            self.assertTrue(back)
            self.assertTrue(all(idxs[i] == max(lf, pet.seg[1]) for i in back))

    def test_05_wake_from_nap(self):
        pet = self.pet()
        pet.go_idle(); pet.fade = None; pet.prev = None
        pet.act_at = {}
        pet.napping = True
        pet.play_expr('nap', hold=60)
        self.assertTrue(pet.wake_from_nap())
        self.assertFalse(pet.napping)
        self.assertEqual(pet.expr, 'stretch')
        self.assertFalse(pet.wake_from_nap())                   # 再点一下就是普通点击

    def test_06_menu_has_actions_no_chat_by_default(self):
        pet = self.pet()
        m = QMenu(pet); pet.fill_menu(m)
        labels = [a.text() for a in m.actions()]
        self.assertIn('动作试播', labels)
        self.assertFalse(any('和她说话' in t for t in labels))
        act = next(a for a in m.actions() if a.text() == '动作试播')   # 先留住 QAction：PySide6 6.10 对临时 QAction 取 .menu() 会连子菜单一起释放
        sub = act.menu()
        self.assertEqual(len(sub.actions()), 4)

    def test_07_no_auto_action_right_after_start(self):
        pet = self.pet()
        cands = []
        pet.new_action_tick(time.time(), True, True, cands)
        self.assertEqual(cands, [])                              # 刚启动 5 分钟内不抢话


if __name__ == '__main__':
    unittest.main(verbosity=2)
