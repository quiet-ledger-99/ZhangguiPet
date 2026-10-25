#!/usr/bin/env python3
"""v0.3.6 的离屏单元测试（不需要真屏幕、不出声、不碰真实设置）。
运行：QT_QPA_PLATFORM=offscreen python tests/test_v036.py
覆盖：左边躲边立绘是单独画的（不是右边的镜像）；下边躲边（判定、位置不压任务栏、多屏、鼠标靠近探头、
离开 2.5 秒缩回、气泡/计时牌位置、关掉「只露半身」就不躲）；上方探头发布版默认关闭（拖到上边不进 peek，素材保留）；表情 biz/pout 换成 wave/huff 且挥手不会一直挥；
旧的递包素材不再发布；素材尺寸/遮罩/清单一致；边缘去青边统计；版本号。
Windows 真机（真实多屏、混合 DPI、任务栏在左/右/上）这里用假屏幕几何模拟，最终还要真机看一眼。"""
import os, sys, json, time, tempfile, unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['ZHANGGUI_PET_NO_AUDIO'] = '1'; os.environ['ZHANGGUI_PET_NO_OPEN'] = '1'; os.environ['ZHANGGUI_PET_NO_DIALOG'] = '1'
os.environ.pop('ZHANGGUI_PET_DEBUG', None); os.environ.pop('ZHANGGUI_PET_ORDER', None)
TMP = tempfile.mkdtemp(prefix='zg_test36_')
os.environ['ZHANGGUI_PET_CONFIG_DIR'] = TMP
IDLE = os.path.join(TMP, 'idle.txt'); open(IDLE, 'w').write('0')
os.environ['ZHANGGUI_PET_SIM_IDLE_FILE'] = IDLE
os.environ['ZHANGGUI_PET_SIM_FULLSCREEN_FILE'] = os.path.join(TMP, 'fs.flag')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import zhanggui_pet as Z
import pet_platform as P
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from PySide6.QtCore import QPoint, QRect

app = QApplication.instance() or QApplication([])
A = os.path.join(ROOT, 'assets')


class FakeLock:
    def poked(self): return False


class FakeScreen:
    def __init__(self, full, avail, name='s'):
        self.full, self.avail, self.nm = full, avail, name
    def geometry(self): return QRect(self.full)
    def availableGeometry(self): return QRect(self.avail)
    def name(self): return self.nm


def make_pet(screens=None):
    log = P.Log(None)
    st = P.Settings(None, log)
    st['first_run_done'] = True
    pet = Z.Pet(TMP, log, st, FakeLock())
    pet.show()
    pet.brain_timer.stop(); pet.anim_timer.stop()
    if screens:
        def screen_of(pt):
            for s in screens:
                if s.geometry().contains(pt): return s
            return min(screens, key=lambda s: (s.geometry().center() - pt).manhattanLength())
        pet.screen_of = screen_of
        pet.occupied = lambda pt: any(s.geometry().contains(pt) for s in screens)
    return pet


def drop_at(pet, x, y):
    """把精灵左上角放到 (x, y) 后当作松手"""
    pet.move(x - pet.ox, y - pet.oy)
    return pet.edge_side()


# 1920x1080，任务栏在下面 40px
SCR = FakeScreen(QRect(0, 0, 1920, 1080), QRect(0, 0, 1920, 1040))


def rgba(path):
    im = QImage(path).convertToFormat(QImage.Format_RGBA8888)
    return im


class T1_Assets(unittest.TestCase):
    def test_sizes_and_files(self):
        for n in ('shy_left', 'tilt_left', 'shy_right', 'tilt_right', 'tilt_top', 'tilt_bottom'):
            im = QImage(os.path.join(A, 'peek', n + '.png'))
            self.assertFalse(im.isNull(), n)
            self.assertEqual((im.width(), im.height()), (251, 380), n)
        r = json.load(open(os.path.join(A, 'peek', 'peek.json'), encoding='utf-8'))['retract']
        self.assertTrue(20 <= r['bottom'] <= 120 and 20 <= r['top'] <= 160)

    def test_left_is_not_mirror(self):
        for pose in ('shy', 'tilt'):
            L = rgba(os.path.join(A, 'peek', f'{pose}_left.png'))
            Rm = rgba(os.path.join(A, 'peek', f'{pose}_right.png')).mirrored(True, False)
            diff = same = 0
            for y in range(0, 380, 4):
                for x in range(0, 251, 4):
                    a, b = L.pixelColor(x, y), Rm.pixelColor(x, y)
                    if a.alpha() > 200 and b.alpha() > 200:
                        d = abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())
                        diff += d > 60; same += 1
            self.assertGreater(diff / max(1, same), 0.3, f'{pose}_left 看起来还是右边的镜像')

    def test_wall_side(self):
        """墙那一边要贴着画布边：左=第 0 列有人，上=第 0 行有人，下=最后一行有人"""
        def has(im, xs, ys):
            return any(im.pixelColor(x, y).alpha() > 128 for x in xs for y in ys)
        self.assertTrue(has(rgba(os.path.join(A, 'peek', 'tilt_left.png')), [0], range(380)))
        self.assertTrue(has(rgba(os.path.join(A, 'peek', 'tilt_top.png')), range(251), [0]))
        self.assertTrue(has(rgba(os.path.join(A, 'peek', 'tilt_bottom.png')), range(251), [379]))

    def test_sprites_manifest(self):
        man = json.load(open(os.path.join(A, 'sprites', 'manifest.json'), encoding='utf-8'))
        for old in ('biz', 'biz_hold', 'pout', 'pout_hold'):
            self.assertNotIn(old, man['anims'])
            self.assertFalse(os.path.exists(os.path.join(A, 'sprites', old)), old)
            self.assertFalse(os.path.exists(os.path.join(A, 'masks', old + '.png')), old)
        for name, d in man['anims'].items():
            fs = sorted(f for f in os.listdir(os.path.join(A, 'sprites', name)) if f.endswith('.webp'))
            self.assertEqual(len(fs), d['n'], name)
            self.assertTrue(os.path.exists(os.path.join(A, 'masks', name + '.png')), name)
            im = QImage(os.path.join(A, 'sprites', name, fs[0]))
            self.assertEqual((im.width(), im.height()), (man['w'], man['h']), name)
        for e in Z.EXPR.values():
            for k in ('enter', 'hold', 'leave'):
                seg = e.get(k)
                if seg:
                    self.assertIn(seg[0], man['anims'])
                    self.assertLessEqual(seg[2], man['anims'][seg[0]]['n'])

    def test_edge_stats(self):
        try:
            import numpy as np
            from PIL import Image
            sys.path.insert(0, os.path.join(ROOT, 'tools', 'art036'))
            from edgecheck import stats
        except ImportError:
            self.skipTest('没有 numpy/Pillow')
        items = [(n, np.asarray(Image.open(os.path.join(A, 'peek', n)).convert('RGBA')))
                 for n in os.listdir(os.path.join(A, 'peek')) if n.endswith('.png')]
        for a in ('wave', 'huff', 'idle', 'smile'):
            for i in (0, 24, 47):
                items.append((f'{a}{i}', np.asarray(Image.open(os.path.join(A, 'sprites', a, f'{i:03d}.webp')).convert('RGBA'))))
        tot, _ = stats(items)
        for bg, (band, teal, green) in tot.items():
            self.assertLess(teal / band, 0.0005, f'{bg} 偏青绿 {100 * teal / band:.3f}%')
            self.assertLess(green / band, 0.0001, f'{bg} 绿溢')


class T2_EdgePure(unittest.TestCase):
    H, Wd = 380, 251

    def r(self, x, y):
        return QRect(x, y, self.Wd, self.H)

    def test_left_right(self):
        occ = lambda p: False
        self.assertEqual(Z.edge_hit(self.r(5, 300), SCR.avail, SCR.full, occ, 25), 'left')
        self.assertEqual(Z.edge_hit(self.r(1920 - 251 - 3, 300), SCR.avail, SCR.full, occ, 25), 'right')
        self.assertEqual(Z.edge_hit(self.r(800, 300), SCR.avail, SCR.full, occ, 25), '')

    def test_taskbar_left_is_still_edge(self):
        """任务栏在左边：可用区域从 x=60 开始，屏幕外没有别的屏幕 → 照样能躲左边（v0.3.5 这里会误判成「有隔壁屏幕」）"""
        full, avail = QRect(0, 0, 1920, 1080), QRect(60, 0, 1860, 1080)
        occ = lambda p: full.contains(p)
        self.assertEqual(Z.edge_hit(self.r(62, 300), avail, full, occ, 25), 'left')

    def test_top(self):
        """纯几何：贴顶仍可判为 top；allow_top/allow_tb 可关掉。运行时是否启用见 PEEK_ENABLE_TOP。"""
        occ = lambda p: False
        self.assertEqual(Z.edge_hit(self.r(800, -50), SCR.avail, SCR.full, occ, 25), 'top')
        self.assertEqual(Z.edge_hit(self.r(800, 10), SCR.avail, SCR.full, occ, 25), 'top')
        self.assertEqual(Z.edge_hit(self.r(800, 60), SCR.avail, SCR.full, occ, 25), '')
        self.assertEqual(Z.edge_hit(self.r(800, -50), SCR.avail, SCR.full, occ, 25, allow_tb=False), '')
        self.assertEqual(Z.edge_hit(self.r(800, -50), SCR.avail, SCR.full, occ, 25, allow_top=False), '')
        # 只关 top 时下边仍可判
        stand_past = 1040 - 380 + int(380 * Z.PEEK_BOTTOM_PAST) + 1
        self.assertEqual(Z.edge_hit(self.r(800, stand_past), SCR.avail, SCR.full, occ, 25, allow_top=False), 'bottom')

    def test_bottom_needs_drag_past_taskbar(self):
        occ = lambda p: False
        stand = 1040 - 380                      # 平时站在任务栏上：不躲
        self.assertEqual(Z.edge_hit(self.r(800, stand), SCR.avail, SCR.full, occ, 25), '')
        self.assertEqual(Z.edge_hit(self.r(800, stand + 40), SCR.avail, SCR.full, occ, 25), '')
        self.assertEqual(Z.edge_hit(self.r(800, stand + 100), SCR.avail, SCR.full, occ, 25), 'bottom')

    def test_multi_monitor(self):
        top_s = FakeScreen(QRect(0, -1080, 1920, 1080), QRect(0, -1080, 1920, 1080))
        right_s = FakeScreen(QRect(1920, 0, 1920, 1080), QRect(1920, 0, 1920, 1040))
        below_s = FakeScreen(QRect(0, 1080, 1920, 1080), QRect(0, 1080, 1920, 1040))
        occ = lambda scrs: (lambda p: any(s.geometry().contains(p) for s in scrs))
        o = occ([SCR, top_s, right_s])
        self.assertEqual(Z.edge_hit(self.r(800, -50), SCR.avail, SCR.full, o, 25), '', '上面接着屏幕')
        self.assertEqual(Z.edge_hit(self.r(1920 - 251, 300), SCR.avail, SCR.full, o, 25), '', '右边接着屏幕')
        self.assertEqual(Z.edge_hit(self.r(5, 300), SCR.avail, SCR.full, o, 25), 'left')
        o2 = occ([SCR, below_s])
        self.assertEqual(Z.edge_hit(self.r(800, 1040 - 380 + 100), SCR.avail, SCR.full, o2, 25), '', '下面接着屏幕')

    def test_place_never_over_taskbar(self):
        content = QRect(37, 245, 178, 135)
        p = Z.peek_place('bottom', self.r(1900, 900), SCR.avail, content)
        self.assertEqual(p.y() + self.H - 1, SCR.avail.bottom())
        self.assertLessEqual(p.x() + content.right(), SCR.avail.right())
        p = Z.peek_place('top', self.r(-200, -100), SCR.avail, QRect(48, 0, 157, 324))
        self.assertEqual(p.y(), SCR.avail.top())
        self.assertGreaterEqual(p.x() + 48, SCR.avail.left())
        tb_top = QRect(0, 48, 1920, 1032)                 # 任务栏在上面
        self.assertEqual(Z.peek_place('top', self.r(500, 0), tb_top).y(), 48)


class T3_PetTopBottom(unittest.TestCase):
    def setUp(self):
        self.pet = make_pet([SCR])

    def tearDown(self):
        self.pet.close()

    def test_drop_bottom_and_position(self):
        pet = self.pet
        sw, sh = pet.sp.sw, pet.sp.sh
        self.assertEqual(drop_at(pet, 900, 1040 - sh + int(sh * 0.3)), 'bottom')
        pet.apply_peek('bottom', animate=False)
        r = pet.sprite_rect()
        self.assertEqual(r.bottom(), SCR.avail.bottom(), '精灵底边正好在任务栏上沿')
        self.assertLessEqual(pet.y() + pet.height() - 1, SCR.avail.bottom() + 1)
        c = pet.peek_content().translated(pet.pos())
        self.assertTrue(SCR.avail.contains(c), '露出来的人整个在可用区域里')

    def test_drop_top(self):
        """发布版 PEEK_ENABLE_TOP=False：拖到上边不进 top peek，回落为普通可见（ensure_visible）。"""
        pet = self.pet
        self.assertFalse(Z.PEEK_ENABLE_TOP, '周日发布版应关掉上方探头')
        self.assertEqual(drop_at(pet, 900, -60), '', '上边不应触发探头')
        # 模拟松手：与 on_drop 无 side 分支一致
        pet.leave_peek()
        pet.move(900 - pet.ox, -60 - pet.oy)
        pet.ensure_visible()
        self.assertEqual(pet.peek, '')
        r = pet.sprite_rect()
        self.assertGreaterEqual(r.top(), SCR.avail.top(), '应被拉回可用区域内')
        # 素材仍在，手动 apply 仍可用（方便以后再开）
        self.assertIsNotNone(pet.sp.peek_img('tilt', 'top'))
        pet.apply_peek('top', animate=False)
        self.assertEqual(pet.sprite_rect().top(), SCR.avail.top())

    def test_setting_off(self):
        pet = self.pet
        pet.st['edge_peek'] = False
        self.assertEqual(drop_at(pet, 900, -60), '')
        self.assertEqual(drop_at(pet, 5, 300), '')

    def test_top_peek_disabled_others_ok(self):
        """关上方探头时：左/右/下边仍可躲，上边不触发。"""
        pet = self.pet
        self.assertFalse(Z.PEEK_ENABLE_TOP)
        self.assertEqual(drop_at(pet, 5, 300), 'left')
        self.assertEqual(drop_at(pet, 1920 - 251 - 3, 300), 'right')
        sh = pet.sp.sh
        self.assertEqual(drop_at(pet, 900, 1040 - sh + int(sh * 0.3)), 'bottom')
        self.assertEqual(drop_at(pet, 900, -60), '')
        self.assertEqual(drop_at(pet, 900, 10), '')

    def test_shy_is_retracted(self):
        sp = self.pet.sp
        for side in ('top', 'bottom'):
            t = sp.peek_mask('tilt', side).boundingRect(); s = sp.peek_mask('shy', side).boundingRect()
            self.assertLess(s.height(), t.height() - 20, side)
            if side == 'top':
                self.assertEqual(s.top(), 0)
            else:
                self.assertEqual(s.bottom(), sp.sh - 1)

    def test_mouse_near_and_leave(self):
        pet = self.pet
        pet.apply_peek('bottom', animate=False)
        body = pet.peek_content().translated(pet.pos())
        cur = {'p': QPoint(100, 100)}
        class FakeCursor:
            @staticmethod
            def pos(): return QPoint(cur['p'])
        real = Z.QCursor; Z.QCursor = FakeCursor
        try:
            pet.peek_poll(); self.assertFalse(pet.peek_out)            # 鼠标远：武装
            cur['p'] = body.center(); pet.peek_poll()
            self.assertTrue(pet.peek_out, '鼠标靠近要探头')
            pet.compose()
            pet.bubble = None
            cur['p'] = QPoint(100, 100); pet.peek_poll()
            self.assertTrue(pet.peek_out, '刚离开还不缩')
            pet.peek_away_t = time.time() - 2.6; pet.peek_poll()
            self.assertFalse(pet.peek_out, '离开 2.5 秒缩回去')
        finally:
            Z.QCursor = real

    def test_slide_frames(self):
        pet = self.pet
        pet.apply_peek('top', animate=False)
        pet.compose()
        pet.set_peek_pose(True)
        self.assertIsNotNone(pet.peek_fade)
        img, masks = pet.compose_peek()
        self.assertEqual((img.width(), img.height()), (pet.sp.sw, pet.sp.sh))
        self.assertEqual(len(masks), 2)
        time.sleep(Z.PEEK_FADE + 0.02)
        img, masks = pet.compose_peek()
        self.assertIsNone(pet.peek_fade)

    def test_bubble_and_badge(self):
        pet = self.pet
        for side in ('top', 'bottom'):
            pet.apply_peek(side, animate=False, out=True)
            pet.compose()
            pet.show_bubble('鼠标一靠过来我就探头啦～')
            b = pet.bubble_rect()
            c = pet.sp.peek_mask('tilt', side).boundingRect().translated(pet.ox, pet.oy)
            vis = SCR.avail.translated(-pet.x(), -pet.y())
            self.assertTrue(vis.contains(b.translated(0, 0)), side)
            if side == 'bottom':
                self.assertLessEqual(b.bottom(), c.top())
            else:
                self.assertGreaterEqual(b.top(), c.top() + c.height() // 2)
                self.assertTrue(pet.bubble_tail_up())
            pet.badge_text = '计时 00:12:34'
            self.assertTrue(vis.contains(pet.badge_rect()), side)
            pet.badge_text = None
            pet.bubble = None; pet.bubble_cache = None


class T4_Expr(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(Z.EXPR['biz']['enter'][0], 'wave')
        self.assertEqual(Z.EXPR['pout']['enter'][0], 'huff')
        self.assertEqual(set(Z.POSE_ANIMS), {'wave', 'huff'})

    def test_wave_max_hold(self):
        pet = make_pet()
        pet.last_touch = time.time()
        pet.play_expr('biz')
        for _ in range(60):
            pet.tick()
            if pet.mode == 'hold': break
        self.assertEqual(pet.mode, 'hold')
        self.assertLessEqual(pet.hold_until - time.time(), 4.05)
        pet.touch()
        self.assertLessEqual(pet.hold_until - time.time(), 4.05, '点她也不会让她一直挥手')
        pet.close()


class T5_Version(unittest.TestCase):
    def test_version(self):
        self.assertEqual(Z.VERSION, '0.3.9')
        for f in ('README.md', 'CHANGELOG.md'):
            self.assertIn('0.3.9', open(os.path.join(ROOT, f), encoding='utf-8').read(), f)
        self.assertIn('0.3.9', open(os.path.join(ROOT, 'packaging', 'version_info.txt'), encoding='utf-8').read())

    def test_no_bad_strings(self):
        for f in ('zhanggui_pet.py', 'pet_lines.py', 'README.md', 'CHANGELOG.md'):
            t = open(os.path.join(ROOT, f), encoding='utf-8').read()
            self.assertNotIn('我是' + '千问', t, f)


if __name__ == '__main__':
    unittest.main(verbosity=2)
