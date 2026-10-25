#!/usr/bin/env python3
"""v0.3.7 长脚模式离屏回归（v0.3.8 起按重画后的 375x614 几何更新）；独立运行，不触碰真实设置或正式桌宠。
QT_QPA_PLATFORM=offscreen python tests/test_v037.py
覆盖任务书 §5 九项；另验独立大小、托盘、切换缓存和待生效的滑块值。
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['ZHANGGUI_PET_NO_AUDIO'] = '1'
os.environ['ZHANGGUI_PET_NO_OPEN'] = '1'
os.environ['ZHANGGUI_PET_NO_DIALOG'] = '1'
os.environ['ZHANGGUI_PET_SIM_NO_TRAY'] = '1'
os.environ.pop('ZHANGGUI_PET_DEBUG', None)
os.environ.pop('ZHANGGUI_PET_ORDER', None)
TMP = tempfile.TemporaryDirectory(prefix='zg_test37_')
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
from PySide6.QtWidgets import QApplication, QMenu, QSlider

app = QApplication.instance() or QApplication([])
A = ROOT / 'assets'


class FakeLock:
    def poked(self): return False


class FakeScreen:
    def geometry(self): return QRect(0, 0, 1920, 1080)
    def availableGeometry(self): return QRect(0, 0, 1920, 1040)
    def name(self): return 'test_screen'


SCR = FakeScreen()


class Assets(unittest.TestCase):
    def test_01_all_frames_masks_manifest(self):
        old = json.loads((A / 'sprites/manifest.json').read_text(encoding='utf-8'))
        man = json.loads((A / 'sprites_legs/manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(tuple(man[k] for k in ('w', 'h', 'padx', 'upper_x', 'upper_y', 'upper_w', 'upper_h')),
                         (375, 614, 62, 58, 0, 251, 380))
        self.assertEqual(man['fps'], 24.0)          # v0.3.9：长脚 24fps
        self.assertEqual(old['fps'], 12.0)          # 飘着模式不变
        self.assertEqual(set(man['anims']), set(old['anims']))
        self.assertEqual(len(man['anims']), 8)
        for name, spec in man['anims'].items():
            with self.subTest(anim=name):
                self.assertEqual((spec['n'], spec['type']), (old['anims'][name]['n'] * 2, old['anims'][name]['type']))
                paths = sorted((A / 'sprites_legs' / name).glob('*.webp'))
                self.assertEqual([p.name for p in paths], [f'{i:03d}.webp' for i in range(spec['n'])])
                for p in paths:
                    im = QImage(str(p))
                    self.assertFalse(im.isNull(), str(p))
                    self.assertEqual((im.width(), im.height()), (375, 614), str(p))
                mask = QImage(str(A / 'masks_legs' / (name + '.png')))
                self.assertEqual((mask.width(), mask.height()), (375, 614))
        self.assertEqual(len(list((A / 'masks_legs').glob('*.png'))), 8)
        for name, fx in man['fx'].items():
            self.assertEqual(fx['img'], old['fx'][name]['img'])
            self.assertAlmostEqual(fx['at'][0], old['fx'][name]['at'][0] + man['upper_x'])
            self.assertAlmostEqual(fx['at'][1], old['fx'][name]['at'][1])
        # v0.3.8：wave/huff 也是有腿的整身重画，不再标 legs=False
        self.assertNotIn('legs', man['anims']['wave'])
        self.assertNotIn('legs', man['anims']['huff'])

    def test_01_peek_wall_edges(self):
        paths = sorted((A / 'peek_legs').glob('*.png'))
        self.assertEqual(len(paths), 6)
        for p in paths:
            im = QImage(str(p))
            self.assertEqual((im.width(), im.height()), (375, 614), p.name)
            side = p.stem.split('_')[-1]
            coords = ((0, y) for y in range(614)) if side == 'left' else (
                ((374, y) for y in range(614)) if side == 'right' else (
                ((x, 0) for x in range(375)) if side == 'top' else ((x, 613) for x in range(375))))
            self.assertTrue(any(im.pixelColor(x, y).alpha() > 128 for x, y in coords), p.name)


class PetModes(unittest.TestCase):
    def setUp(self):
        self.pets = []
        self.log = P.Log(None)

    def tearDown(self):
        for pet in self.pets:
            for timer in pet.findChildren(QTimer): timer.stop()
            pet.close()
            pet.deleteLater()

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

    def test_02_default_floating_geometry(self):
        pet = self.pet()
        self.assertIs(pet.st['legs'], False)
        self.assertEqual((pet.sp.w, pet.sp.h, pet.sp.s), (251, 380, 1.0))
        self.assertEqual((pet.sp.ux, pet.sp.uw, pet.sp.uh), (0, 251, 380))
        for scale in (0.2, 0.75, 1, 1.5):
            pet.set_scale(scale)
            sw, sh = pet.sp.sw, pet.sp.sh
            self.assertEqual(pet.fx_rect('zzz').x(), int(pet.ox + sw * 0.66))
            self.assertEqual(pet.fx_rect('excl').x(), int(pet.ox + sw * 0.74))
            self.assertEqual(pet.hearts_rect(), QRect(int(pet.ox + sw * .2), int(pet.oy - 30 * scale - 12),
                int(sw * .6), int(sh * .22 + 40 * scale + 12)))
            self.assertEqual(pet.badge_rect().y(), pet.oy + sh - 30)
        self.assertFalse(Z.PEEK_ENABLE_TOP)

    def test_03_switch_anchor_scales_and_restart(self):
        st = P.Settings(TMP.name, self.log)
        st['legs'] = False; st['scale'] = .85; st['scale_legs'] = .75
        pet = self.pet(st)
        a = pet.anchor()
        pet.set_legs(True)
        self.assertEqual((pet.sp.w, pet.sp.h, pet.sp.s), (375, 614, .85))     # nolegs-samesize：两种模式共用一个大小
        self.assertLessEqual((pet.anchor() - a).manhattanLength(), 1)
        self.assertIs(st['legs'], True)
        pet.set_scale(.65)
        pet.set_legs(False)
        self.assertEqual(pet.sp.s, .65)
        self.assertEqual((st['scale'], st['scale_legs']), (.65, .65))
        self.assertLessEqual((pet.anchor() - a).manhattanLength(), 1)
        pet.set_legs(True)
        self.assertEqual(pet.sp.s, .65)
        self.assertTrue(st.save())
        saved = json.loads(Path(st.path).read_text(encoding='utf-8'))
        self.assertIs(saved['legs'], True)
        restarted = self.pet(P.Settings(TMP.name, self.log))
        self.assertEqual((restarted.sp.w, restarted.sp.h, restarted.sp.s), (375, 614, .65))

    def test_04_left_right_bottom_peek_and_switch(self):
        pet = self.pet(); pet.set_legs(True)
        for side in ('left', 'right', 'bottom'):
            with self.subTest(side=side):
                pet.leave_peek()
                r = pet.sprite_rect()
                x = 0 if side == 'left' else (1920 - r.width() if side == 'right' else 800)
                y = 1040 - r.height() + int(.2 * pet.sp.uh) + 1 if side == 'bottom' else 200
                pet.move(x - pet.ox, y - pet.oy)
                self.assertEqual(pet.edge_side(), side)
                pet.apply_peek(side, animate=False); pet.compose()
                if side == 'bottom': self.assertEqual(pet.sprite_rect().bottom() + 1, 1040)
                else:
                    self.assertEqual(pet.sprite_rect().left() if side == 'left' else pet.sprite_rect().right(),
                                     -1 if side == 'left' else 1920)
                # v036 的左右墙边各越出画布可见边界 1px；下边严格不压任务栏。
                visible = SCR.availableGeometry().adjusted(-1, 0, 1, 0) if side != 'bottom' else SCR.availableGeometry()
                self.assertTrue(visible.contains(pet.peek_content().translated(pet.pos())))
                pet.set_peek_pose(True)
                self.assertTrue(pet.peek_out)
                pet.peek_fade = (time.time() - Z.PEEK_FADE - .1, pet.last_img, ('peek', 'shy', side))
                image, masks = pet.compose_peek()
                self.assertIsNone(pet.peek_fade)
                self.assertEqual((image.width(), image.height()), (pet.sp.sw, pet.sp.sh))
                pet.set_peek_pose(False)
                self.assertFalse(pet.peek_out)
                if side == 'bottom':
                    self.assertEqual(pet.sp.peek_retract(side), round(35 * pet.sp.s))
                    self.assertLess(pet.sp.peek_mask('shy', side).boundingRect().height(),
                                    pet.sp.peek_mask('tilt', side).boundingRect().height())
                for legs in (False, True):
                    pet.set_legs(legs)
                    self.assertEqual(pet.peek, side)
                    self.assertEqual((pet.cur_img.width(), pet.cur_img.height()), (pet.sp.sw, pet.sp.sh))
                    if side == 'bottom': self.assertEqual(pet.sprite_rect().bottom() + 1, 1040)

    def test_04_peek_mouse_hover_retract(self):
        pet = self.pet(); pet.set_legs(True)
        for side in ('left', 'right', 'bottom'):
            pet.apply_peek(side, animate=False); pet.compose()
            body = pet.peek_content().translated(pet.pos())
            with patch.object(Z.QCursor, 'pos', return_value=QPoint(960, 100)):
                pet.peek_poll(); self.assertTrue(pet.peek_armed)
            with patch.object(Z.QCursor, 'pos', return_value=body.center()):
                pet.peek_poll(); self.assertTrue(pet.peek_out)
            pet.bubble = None; pet.peek_away_t = time.time() - 2.6
            with patch.object(Z.QCursor, 'pos', return_value=QPoint(960, 100)):
                pet.peek_poll(); self.assertFalse(pet.peek_out)

    def test_05_bottom_threshold_upper_height(self):
        pet = self.pet()
        for legs in (False, True):
            pet.set_legs(legs)
            for frac, expected in ((0, ''), (.1, ''), (.2, 'bottom')):
                past = int(pet.sp.uh * frac)
                pet.move(800 - pet.ox, SCR.availableGeometry().bottom() - pet.sp.sh + 1 + past - pet.oy)
                self.assertEqual(pet.edge_side(), expected, (legs, frac))
            r = pet.sprite_rect()
            if not legs:
                self.assertEqual(Z.edge_hit(r, SCR.availableGeometry(), SCR.geometry(), lambda _: False, 25), 'bottom')
            else:
                self.assertEqual(Z.edge_hit(r, SCR.availableGeometry(), SCR.geometry(), lambda _: False, 25), '')
            pet.st['edge_peek'] = False
            self.assertEqual(pet.edge_side(), '')
            pet.st['edge_peek'] = True

    def test_06_head_and_body_click_regions(self):
        pet = self.pet(); pet.set_legs(True)
        for x, y, expected in ((.5, .1, 'head'), (.5, .5, 'body'), (.5, 1.3, 'body'), (-.1, .1, 'body')):
            local = QPoint(int(pet.ox + pet.sp.ux + pet.sp.uw * x), int(pet.oy + pet.sp.uh * y))
            e = QMouseEvent(QEvent.MouseButtonPress, QPointF(local), QPointF(pet.mapToGlobal(local)),
                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            pet.mousePressEvent(e)
            self.assertEqual(pet.zone, expected, (x, y))
            self.assertEqual(pet.press_timer.isActive(), expected == 'head')
            pet.cancel_interaction()

    def test_07_wave_huff_playback(self):
        pet = self.pet(); pet.set_legs(True); pet.set_scale(1)
        for expr, anim in (('biz', 'wave'), ('pout', 'huff')):
            pet.play_expr(expr)
            for i in range(48):
                pet.tick()
                self.assertEqual((pet.cur_img.width(), pet.cur_img.height()), (375, 614))
            self.assertEqual(pet.anim, anim)
            for i in (0, 24, 47):
                im = pet.sp.frame(anim, i)
                # v0.3.8：整身重画，下半张有腿和鞋（脚底在 y≈600）。
                self.assertTrue(any(im.pixelColor(x, y).alpha() > 200 for x in range(0, 375, 4) for y in range(560, 600, 4)))

    def test_08_fx_hearts_badge_and_bubble_upper_position(self):
        pet = self.pet(); pet.set_scale(.75)
        pet.show_bubble('这个大小可以吗？')
        original = {k: pet.fx_rect(k).translated(-pet.ox, -pet.oy) for k in ('sweat', 'puff', 'zzz', 'excl')}
        hearts = pet.hearts_rect().translated(-pet.ox, -pet.oy)
        badge_y = pet.badge_rect().y() - pet.oy
        bubble_y = pet.bubble_rect().y()
        pet.set_legs(True)
        dx = 58 * .75                                   # 头框 upper_x=58、upper_y=0
        for name, old in original.items():
            current = pet.fx_rect(name).translated(-pet.ox, -pet.oy)
            self.assertLessEqual(abs(current.x() - old.x() - dx), 1, name)
            self.assertEqual((current.y(), current.size()), (old.y(), old.size()), name)
        h = pet.hearts_rect().translated(-pet.ox, -pet.oy)
        self.assertLessEqual(abs(h.x() - hearts.x() - dx), 1)
        self.assertEqual((h.y(), h.size()), (hearts.y(), hearts.size()))
        self.assertEqual(pet.badge_rect().y() - pet.oy, badge_y)
        self.assertEqual(pet.bubble_rect().y(), bubble_y)
        self.assertEqual((pet.sp.ux, pet.sp.uy, pet.sp.uw, pet.sp.uh), (dx, 0, 188, 285))

    def test_09_version(self):
        self.assertEqual(Z.VERSION, '0.3.10')
        for path in ('README.md', 'CHANGELOG.md', '说明.txt', 'packaging/version_info.txt'):
            self.assertIn('0.3.10', (ROOT / path).read_text(encoding='utf-8-sig'))
        info = (ROOT / 'packaging/version_info.txt').read_text(encoding='utf-8')
        self.assertEqual(info.count('(0, 3, 10, 0)'), 2)
        self.assertNotIn('0.3.9', info)

    def test_cache_and_pending_slider_switch(self):
        pet = self.pet()
        pet.sp.frame('wave', 0); pet.sp.mask('wave'); pet.sp.peek_img('tilt', 'bottom')
        pet.sp.peek_retract('bottom'); pet.sp._retract['bottom'] = 999
        pet.pending_scale = .9; pet.scale_timer.start(10000)
        pet.set_legs(True)
        self.assertFalse(pet.scale_timer.isActive())
        self.assertEqual((pet.st['scale'], pet.st['scale_legs'], pet.sp.s), (.9, .9, .9))     # 滑块值落地后沿用到长脚
        self.assertFalse(pet.size_timer.isActive())
        self.assertEqual(pet.sp.peek_retract('bottom'), 32)     # 缓存已清空，按 .9 重新算（原 .75 时为 26）
        self.assertNotIn(('wave', 0), pet.sp.cache)
        self.assertNotIn('wave', pet.sp.masks)
        self.assertNotIn(('tilt', 'bottom'), pet.sp.peek_cache)
        self.assertTrue(all(im.width() == pet.sp.sw and im.height() == pet.sp.sh for im in pet.sp.cache.values()))
        self.assertIsNone(pet.prev)
        self.assertIsNone(pet.fade)
        self.assertIsNotNone(pet.mask_key)
        for i in range(4):
            pet.set_legs(not pet.st['legs'])
            self.assertEqual(pet.sp.bytes, sum(im.sizeInBytes() for im in pet.sp.cache.values()))

    def test_menu_current_scale_and_diagnostic_settings(self):
        pet = self.pet()
        menu = QMenu(pet)
        pet.fill_menu(menu)
        actions = menu.actions()     # 持有 QAction 包装器，并只取当前菜单中的子菜单。
        mode_action = next(a for a in actions if a.text() == '飘着 / 长脚')
        mode = mode_action.menu()
        floating, legs = mode.actions()
        self.assertTrue(floating.isChecked()); self.assertFalse(legs.isChecked())
        self.assertIs(floating.actionGroup(), legs.actionGroup())
        self.assertTrue(legs.actionGroup().isExclusive())
        legs.trigger()
        self.assertTrue(pet.st['legs'])
        self.assertTrue(legs.isChecked()); self.assertFalse(floating.isChecked())
        pet.fill_menu(menu)
        actions = menu.actions()
        size_action = next(a for a in actions if a.text().startswith('大小'))
        size = size_action.menu()
        self.assertIn('100%', size.title())          # 切到长脚大小不变
        slider = size.findChild(QSlider)
        self.assertEqual(slider.value(), 100)
        slider.setValue(60)
        pet.scale_timer.stop(); pet.set_scale(pet.pending_scale)
        self.assertEqual(pet.st['scale_legs'], .6)
        self.assertEqual(pet.st['scale'], .6)
        diag = Z.diag_settings(pet.st, {})
        self.assertEqual((diag['legs'], diag['scale_legs']), (True, .6))


if __name__ == '__main__':
    unittest.main(verbosity=2)
