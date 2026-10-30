#!/usr/bin/env python3
"""v0.3.6 的离屏单元测试（不需要真屏幕、不出声、不碰真实设置）。
运行：QT_QPA_PLATFORM=offscreen python tests/test_v036.py
覆盖：左边躲边立绘是单独画的（不是右边的镜像）；下边躲边（判定、位置不压任务栏、多屏、鼠标靠近探头、
离开 2.5 秒缩回、气泡/计时牌位置、关掉「只露半身」就不躲）；上方探头发布版默认关闭（拖到上边不进 peek，素材保留）；表情 biz/pout 换成 wave/huff 且挥手不会一直挥；
躲边时流汗/zzz/感叹号/气团/爱心跟着露出来的发冠，不留在站姿头顶；
旧的递包素材不再发布；素材尺寸/遮罩/清单一致；边缘去青边统计；版本号。
Windows 真机（真实多屏、混合 DPI、任务栏在左/右/上）这里用假屏幕几何模拟，最终还要真机看一眼。"""
import hashlib, os, sys, json, time, tempfile, unittest
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
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import QPoint, QRect, Qt

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
            self.assertEqual((im.width(), im.height()), (d.get('w', man['w']), d.get('h', man['h'])), name)   # v0.3.11：stretch 是 251x416 高画布
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

    def test_fx_follows_visible_head(self):
        """流汗 / 气团 / zzz / 感叹号 / 爱心锚在当前探头图的发冠上。

        下边探头的人在画布底部，站姿锚点还在顶上；外接框中点又比发冠更靠右。
        没在躲边时坐标必须和改之前一样。害羞比探出再往下缩一截，zzz 要跟着。
        """
        pet = self.pet
        names = ('sweat', 'puff', 'zzz', 'excl')
        self.assertEqual(pet.fx_peek_shift(), (0, 0))
        idle = {n: QRect(pet.fx_rect(n)) for n in names}
        hearts = QRect(pet.hearts_rect())
        upper_cx = pet.sp.ux + pet.sp.uw / 2.0
        upper_top = float(pet.sp.uy)

        def crown_shift():
            cx, top = pet.sp.peek_crown(pet.peek_key()[1], pet.peek)
            return int(round(cx - upper_cx)), int(round(top - upper_top))

        for side in ('left', 'right', 'top', 'bottom'):
            for out, pose in ((False, 'shy'), (True, 'tilt')):
                pet.apply_peek(side, animate=False, out=out)
                pet.compose()
                dx, dy = crown_shift()
                self.assertEqual(pet.fx_peek_shift(), (dx, dy), (side, pose))
                for n, base in idle.items():
                    self.assertEqual(pet.fx_rect(n), base.translated(dx, dy), (side, pose, n))
                self.assertEqual(pet.hearts_rect(), hearts.translated(dx, dy), (side, pose))
                crown_x, crown_y = pet.sp.peek_crown(pose, side)
                body = pet.sp.peek_mask(pose, side).boundingRect()
                sweat = pet.fx_rect('sweat')
                # 和站姿一样：流汗在发冠右下方，而不是画布顶上的气泡区
                self.assertEqual(sweat.center().y() - pet.oy - int(round(crown_y)),
                                 idle['sweat'].center().y() - pet.oy - int(round(upper_top)))
                if side == 'bottom':
                    self.assertGreater(crown_y, pet.sp.sh * 0.5, pose)
                    self.assertGreater(sweat.center().y() - pet.oy, pet.sp.sh * 0.55, pose)
                    self.assertGreater(pet.fx_rect('zzz').y(), pet.oy + pet.sp.sh * 0.4, pose)
                if side == 'bottom' and pose == 'tilt':
                    # 整段身子的外接框中点比发冠靠右一大截；锚在外接框上会把流汗甩出脸
                    self.assertLess(crown_x, body.center().x() - 15)
                if side in ('left', 'right'):
                    self.assertGreater(sweat.center().x(), pet.ox + body.left() - sweat.width(), (side, pose))
                    self.assertLess(sweat.center().x(), pet.ox + body.right() + sweat.width(), (side, pose))

        pet.apply_peek('bottom', animate=False, out=False)
        y_shy = pet.fx_rect('zzz').y()
        pet.apply_peek('bottom', animate=False, out=True)
        y_tilt = pet.fx_rect('zzz').y()
        self.assertGreaterEqual(y_shy - y_tilt, 30)
        self.assertLessEqual(y_shy - y_tilt, 40)

        pet.leave_peek()
        pet.compose()
        for n, base in idle.items():
            self.assertEqual(pet.fx_rect(n), base, n)
        self.assertEqual(pet.hearts_rect(), hearts)
        self.assertEqual(pet.fx_peek_shift(), (0, 0))

        pet.set_scale(0.75)
        pet.apply_peek('bottom', animate=False, out=True)
        _cx, top = pet.sp.peek_crown('tilt', 'bottom')
        self.assertGreater(top, pet.sp.sh * 0.5)
        self.assertLess(top, 200)   # 跟着 0.75 缩小，不是 1x 的 y≈235
        self.assertGreater(pet.fx_rect('zzz').y(), pet.oy + pet.sp.sh * 0.4)
        self.assertGreater(pet.fx_rect('sweat').center().y() - pet.oy, pet.sp.sh * 0.55)
        pet.leave_peek()
        self.assertEqual(pet.fx_peek_shift(), (0, 0))


# 交回 A（251×380 右侧）和 B（502×760 六张，含 shy_right）的文件哈希
PEEK_SHA = {
    'shy_right.png': '734a7fc8884f44b7a48ab493d7003713db8231d1bf3b6734ee8011c7df90d337',
    'tilt_right.png': '06d7b8cd74756185c168c9c5bb6911b285fea4957c769c4e546442a5d9674629',
    '@2x/shy_left.png': '1b4237c72595db647b7c5b7c9275549f138b7264118a2bc9e837cc5310466810',
    '@2x/shy_right.png': '670a59ddca06a8de2bf426b80da0a92fa2842dd7577da864bb201c150305eb2f',
    '@2x/tilt_left.png': 'de3139a9adf645c193cc40164c793852b93296e0a484b6e8e27d277b7a5ee592',
    '@2x/tilt_right.png': '85c9feefad45bdfce819a60f5db6163dd533320e439061a227b862bf25bdfc51',
    '@2x/tilt_top.png': '3afdb4f83588c9bd94f746c7eaa62e42031404ef4faf0ef36672e4cf6d93beb4',
    '@2x/tilt_bottom.png': '8093dd7d0bda26dd9cbdb28d72535c60381cddb5bc8e1de213bec18a0aee779e',
}


def rgba_bytes(im):
    im = im.convertToFormat(QImage.Format_RGBA8888)
    bpl, w = im.bytesPerLine(), im.width()
    raw = bytes(im.constBits())
    return b''.join(raw[y * bpl:y * bpl + w * 4] for y in range(im.height()))


class T6_HidpiPeek(unittest.TestCase):
    def test_files_are_the_returned_set(self):
        for rel, sha in PEEK_SHA.items():
            p = os.path.join(A, 'peek', rel)
            self.assertTrue(os.path.isfile(p), rel)
            with open(p, 'rb') as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), sha, rel)
            im = QImage(p)
            if rel.startswith('@2x/'):
                self.assertEqual((im.width(), im.height()), (502, 760), rel)
            else:
                self.assertEqual((im.width(), im.height()), (251, 380), rel)

    def test_dpr1_right_uses_new_1x_not_2x_buffer(self):
        sp = Z.Sprites(False)
        self.assertEqual(sp.peek_dpr(), 1.0)
        for pose in ('shy', 'tilt'):
            im = sp.peek_img(pose, 'right')
            self.assertEqual((im.width(), im.height()), (251, 380), pose)
            src = QImage(os.path.join(A, 'peek', f'{pose}_right.png')).convertToFormat(QImage.Format_ARGB32_Premultiplied)
            self.assertEqual(rgba_bytes(im), rgba_bytes(src), pose)

    def test_dpr2_uses_502_bitmap_and_logical_mask(self):
        sp = Z.Sprites(False)
        sp.set_scale(1.0)
        self.assertTrue(sp.set_dpr(2))
        self.assertEqual((sp.sw, sp.sh), (251, 380))
        for pose, side in (('shy', 'left'), ('shy', 'right'), ('tilt', 'left'), ('tilt', 'right'),
                           ('tilt', 'top'), ('tilt', 'bottom')):
            im = sp.peek_img(pose, side)
            self.assertEqual((im.width(), im.height()), (502, 760), f'{pose}_{side}')
            src = QImage(os.path.join(A, 'peek', '@2x', f'{pose}_{side}.png')).convertToFormat(QImage.Format_ARGB32_Premultiplied)
            self.assertEqual(rgba_bytes(im), rgba_bytes(src), f'{pose}_{side} 应是 @2x 原图像素，不是 251 放大')
        for side in ('top', 'bottom'):
            shy = sp.peek_img('shy', side)
            self.assertEqual((shy.width(), shy.height()), (502, 760), f'shy_{side}')
            rect = sp.peek_mask(pose, side).boundingRect()
            self.assertGreaterEqual(rect.left(), 0)
            self.assertGreaterEqual(rect.top(), 0)
            self.assertLess(rect.right(), sp.sw, f'{pose}_{side}')
            self.assertLess(rect.bottom(), sp.sh, f'{pose}_{side}')
        # 墙边仍贴着逻辑画布，不能因为高清把人缩进半格
        self.assertEqual(sp.peek_mask('tilt', 'right').boundingRect().right(), sp.sw - 1)
        self.assertEqual(sp.peek_mask('tilt', 'left').boundingRect().left(), 0)
        self.assertEqual(sp.peek_mask('tilt', 'top').boundingRect().top(), 0)
        self.assertEqual(sp.peek_mask('tilt', 'bottom').boundingRect().bottom(), sp.sh - 1)
        shy = sp.peek_mask('shy', 'bottom').boundingRect()
        tilt = sp.peek_mask('tilt', 'bottom').boundingRect()
        self.assertLess(shy.height(), tilt.height() - 20)
        self.assertEqual(shy.bottom(), sp.sh - 1)
        # 跟把 1x 放大到 502 不是同一张图
        blown = QImage(os.path.join(A, 'peek', 'tilt_right.png')).scaled(502, 760, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        hi = sp.peek_img('tilt', 'right')
        diff = sum(a != b for a, b in zip(rgba_bytes(hi), rgba_bytes(blown)))
        self.assertGreater(diff, 1000, '高清缓冲不应只是旧 251 的放大')

    def test_enlarged_at_dpr1_scales_from_2x(self):
        """100% 屏幕但立绘放大超过 1x 画布时，用 @2x 缩小，而不是把 251 放大。"""
        sp = Z.Sprites(False)
        sp.set_scale(1.5)
        self.assertGreater(sp.sw, sp.w)
        im = sp.peek_img('tilt', 'right')
        self.assertEqual((im.width(), im.height()), (sp.sw, sp.sh))
        src = QImage(os.path.join(A, 'peek', '@2x', 'tilt_right.png')).convertToFormat(QImage.Format_ARGB32_Premultiplied)
        src = src.scaled(sp.sw, sp.sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.assertEqual(rgba_bytes(im), rgba_bytes(src))

    def test_dpr2_draw_and_place_stay_on_logical_canvas(self):
        pet = make_pet([SCR])
        pet.screen_of = lambda pt: SCR
        # 离屏 dpr 是 1；这里钉住 2，避免 apply_peek / compose 又读回窗口缩放
        pet.sync_peek_dpr = lambda: False
        pet.sp.set_dpr(2)
        pet.apply_peek('right', animate=False)
        pet.compose()
        self.assertEqual((pet.cur_img.width(), pet.cur_img.height()), (502, 760))
        self.assertEqual((pet.sprite_rect().width(), pet.sprite_rect().height()), (251, 380))
        # 右缘仍贴可用区域右缘（peek_place 的 +2 再减 1）
        self.assertEqual(pet.sprite_rect().right(), SCR.avail.right() + 1)
        canvas = QImage(502, 760, QImage.Format_ARGB32_Premultiplied)
        canvas.setDevicePixelRatio(2)
        canvas.fill(Qt.transparent)
        p = QPainter(canvas)
        ox, oy = pet.ox, pet.oy
        pet.ox, pet.oy = 0, 0
        pet.draw_sprite(p)
        pet.ox, pet.oy = ox, oy
        p.end()
        # 画进逻辑框后，设备像素应仍是 @2x 那张，而不是先缩成 251
        self.assertEqual((canvas.width(), canvas.height()), (502, 760))
        self.assertEqual(rgba_bytes(canvas), rgba_bytes(pet.cur_img))
        pet.close()

    def test_legs_have_no_2x_peek(self):
        sp = Z.Sprites(True)
        sp.set_dpr(2)
        im = sp.peek_img('tilt', 'right')
        self.assertEqual((im.width(), im.height()), (sp.sw, sp.sh))
        self.assertNotEqual((im.width(), im.height()), (502, 760))


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
        self.assertEqual(Z.VERSION, '0.3.11')
        for f in ('README.md', 'CHANGELOG.md', '说明.txt'):
            self.assertIn('0.3.11', open(os.path.join(ROOT, f), encoding='utf-8-sig').read(), f)
        info = open(os.path.join(ROOT, 'packaging', 'version_info.txt'), encoding='utf-8').read()
        self.assertIn('0.3.11', info)
        self.assertNotIn('0.3.9', info)

    def test_no_bad_strings(self):
        for f in ('zhanggui_pet.py', 'pet_lines.py', 'README.md', 'CHANGELOG.md'):
            t = open(os.path.join(ROOT, f), encoding='utf-8').read()
            self.assertNotIn('我是' + '千问', t, f)


if __name__ == '__main__':
    unittest.main(verbosity=2)
