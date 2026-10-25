#!/usr/bin/env python3
"""v0.3.5 的离屏单元测试（不需要真屏幕、不出声、不碰真实设置）。
运行：QT_QPA_PLATFORM=offscreen python tests/test_v035.py
覆盖：命令开关在打包版里关闭 + 白名单；取消交互/找回她取消延迟隐藏；严格冷却；同秒事件优先级；
气泡纵向限制；全屏时小窗一起藏、不出声、计时提醒补一次；诊断导出脱敏；拖放只接受 Copy；系统壳窗口判断。
Windows 真机行为（Win32 全屏检测、托盘、混合 DPI）这里测不到。"""
import os, sys, time, tempfile, unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['ZHANGGUI_PET_NO_AUDIO'] = '1'; os.environ['ZHANGGUI_PET_NO_OPEN'] = '1'; os.environ['ZHANGGUI_PET_NO_DIALOG'] = '1'
os.environ.pop('ZHANGGUI_PET_DEBUG', None); os.environ.pop('ZHANGGUI_PET_ORDER', None)
TMP = tempfile.mkdtemp(prefix='zg_test_')
os.environ['ZHANGGUI_PET_CONFIG_DIR'] = TMP
IDLE = os.path.join(TMP, 'idle.txt'); open(IDLE, 'w').write('0')
FS = os.path.join(TMP, 'fs.flag')
os.environ['ZHANGGUI_PET_SIM_IDLE_FILE'] = IDLE
os.environ['ZHANGGUI_PET_SIM_FULLSCREEN_FILE'] = FS
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import zhanggui_pet as Z
import pet_platform as P
import pet_lines as PL
from pet_brain import LocalBrain
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QRect, QCoreApplication

app = QApplication.instance() or QApplication([])


class FakeLock:
    def poked(self): return False


def make_pet():
    log = P.Log(None)
    st = P.Settings(None, log)
    st['first_run_done'] = True
    pet = Z.Pet(TMP, log, st, FakeLock())
    pet.show()
    pet.brain_timer.stop(); pet.anim_timer.stop()         # 测试里手动调用 brain_tick / tick
    return pet


def pump(secs):
    end = time.time() + secs
    while time.time() < end:
        QCoreApplication.processEvents(); time.sleep(0.02)


class T1_DevHook(unittest.TestCase):
    def test_disabled_when_frozen(self):
        os.environ['ZHANGGUI_PET_CMD_FILE'] = os.path.join(TMP, 'cmd')
        try:
            self.assertTrue(Z.dev_cmd_file())
            sys.frozen = True
            self.assertIsNone(Z.dev_cmd_file())
        finally:
            if hasattr(sys, 'frozen'): del sys.frozen
            del os.environ['ZHANGGUI_PET_CMD_FILE']

    def test_whitelist_only(self):
        pet = make_pet()
        for bad in ('eval 1+1', "exec __import__('os')", '__import__ os', 'pet.close()', 'scale', 'scale 1 2'):
            r = Z.run_dev_command(pet, bad)
            self.assertEqual(r[0], 'error', bad)
        self.assertEqual(Z.run_dev_command(pet, 'scale 0.8'), 0.8)
        self.assertEqual(len(Z.run_dev_command(pet, 'sprite_rect')), 4)
        self.assertEqual(Z.run_dev_command(pet, 'line pat03'), 'pat03')
        self.assertEqual(Z.run_dev_command(pet, 'line nosuch')[0], 'error')
        pet.close()


class T3_CancelInteraction(unittest.TestCase):
    def test_hide_clears_state(self):
        pet = make_pet()
        pet.press_pos = QPoint(10, 10); pet.last_move = QPoint(12, 12)
        pet.patting = True; pet.dragging = True; pet.vx = 5.0; pet.angle = 4.0
        pet.press_timer.start(10000)
        pet.user_hidden = True; pet.apply_visibility()
        self.assertFalse(pet.isVisible())
        self.assertIsNone(pet.press_pos); self.assertIsNone(pet.last_move)
        self.assertFalse(pet.patting or pet.dragging)
        self.assertEqual((pet.vx, pet.angle), (0.0, 0.0))
        self.assertFalse(pet.press_timer.isActive())
        pet.user_hidden = False; pet.apply_visibility()
        self.assertTrue(pet.isVisible())
        pet.close()

    def test_recenter_cancels_pending_hide(self):
        pet = make_pet()
        pet.tray_ok = True
        pet.toggle_hidden()                     # 「先藏起来」：1.4 秒后才真的藏
        self.assertTrue(pet.hide_pending)
        pump(0.3)
        pet.recenter()                          # 「找回她」
        self.assertFalse(pet.hide_pending)
        pump(1.6)
        self.assertTrue(pet.isVisible(), '找回她之后不该再被旧的延迟隐藏藏掉')
        self.assertFalse(pet.user_hidden)
        pet.close()

    def test_lost_grab(self):
        pet = make_pet()
        pet.press_pos = QPoint(5, 5); pet.press_t = time.time() - 1; pet.patting = True
        self.assertTrue(pet.check_grab())        # 系统里左键没按着（离屏环境）：当作取消
        self.assertIsNone(pet.press_pos); self.assertFalse(pet.patting)
        pet.press_pos = QPoint(5, 5); pet.press_t = time.time()
        self.assertFalse(pet.check_grab())       # 刚按下 0.3 秒内不判断
        pet.close()

    def test_real_mouse_longpress_and_click(self):
        from PySide6.QtTest import QTest
        pet = make_pet()
        w = pet.windowHandle()
        head = QPoint(pet.ox + pet.sp.sw // 2, pet.oy + 40)
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, head)
        pump(0.7); pet.tick()                    # 兜底检查不能把正常的长按当成丢了抓取
        self.assertTrue(pet.patting)
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, head)
        self.assertFalse(pet.patting); self.assertIsNone(pet.press_pos)
        pet.bubble = None
        QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, QPoint(pet.ox + pet.sp.sw // 2, pet.oy + 300))
        self.assertIsNotNone(pet.bubble)         # 普通点击照常有回应
        pet.close()


class T5_StrictCooldown(unittest.TestCase):
    def test_strict_never_picks_cooling(self):
        b = LocalBrain()
        now = time.time()
        for l in PL.LINES['lift']:
            b.used[l.id] = now
        self.assertIsNone(b.line('lift', strict=True))
        self.assertIsNotNone(b.line('lift'))      # 普通点击：都在冷却也要有回应
        b = LocalBrain()
        ls = PL.LINES['drop']
        for l in ls[1:]:
            b.used[l.id] = time.time()
        for _ in range(50):
            l = b.line('drop', strict=True)
            if l is None:
                break
            self.assertEqual(l.id, ls[0].id)
            b.used.pop(l.id)                     # 只让第一句一直可用
            b.recent.clear()

    def test_pet_strict(self):
        pet = make_pet()
        for l in PL.LINES['lift']:
            pet.brain.used[l.id] = time.time()
        self.assertIsNone(pet.say('lift', strict=True))
        pet.close()


class T6_Priority(unittest.TestCase):
    def setUp(self):
        self.pet = make_pet()
        self.slot = PL.SLOTS[0][0]
        self._cs = PL.current_slot
        PL.current_slot = lambda now=None: self.slot
        self.pet.t_start = time.time() - 120
        self.pet.greeted.clear()
        self.pet.st['time_greet'] = True

    def tearDown(self):
        PL.current_slot = self._cs
        self.pet.close()

    def test_only_one_and_order(self):
        pet = self.pet
        said = []
        orig = pet.say
        pet.say = lambda cat, **kw: (said.append(cat), orig(cat, **kw))[1]
        r = pet.run_candidates([
            dict(prio=Z.PRIO_WATER, cat='water', proactive=True, oneshot=False),
            dict(prio=Z.PRIO_RETURN, cat='return_short', proactive=True, oneshot=True),
            dict(prio=Z.PRIO_TIMER, cat='pomo_focus_end', proactive=False, oneshot=True),
            dict(prio=Z.PRIO_SLOT, cat=self.slot, proactive=True, oneshot=False)])
        self.assertEqual(r, 'pomo_focus_end')
        self.assertEqual(said, ['pomo_focus_end'])
        self.assertEqual(pet.pending_ev[1], 'return_short')     # 最多留一个：一次性事件里最重要的

    def test_greeting_marked_only_when_shown(self):
        pet = self.pet
        pet.bubble = None
        pet.st['quiet_until'] = time.time() + 600                # 安静模式：说不出口
        pet.brain_tick()
        self.assertEqual(pet.greeted, set())
        pet.st['quiet_until'] = 0.0; pet.was_quiet = False
        pet.bubble = None
        pet.brain_tick()
        self.assertEqual(len(pet.greeted), 1)

    def test_water_vs_greeting(self):
        pet = self.pet
        pet.st['remind_water'] = True; pet.last_water = time.time() - 99999
        pet.bubble = None
        pet.brain_tick()
        self.assertGreater(pet.last_water, time.time() - 5)      # 喝水优先，说了才记
        self.assertEqual(pet.greeted, set())                     # 问候这一秒没轮上，不能记成已问候
        pet.brain_tick()                                          # 气泡还在：不打断
        self.assertEqual(pet.greeted, set())
        pet.bubble = None
        pet.brain_tick()
        self.assertEqual(len(pet.greeted), 1)

    def test_timer_during_fullscreen(self):
        pet = self.pet
        pet.st['time_greet'] = False
        pet.panel = Z.TimerPanel(pet); pet.panel.show()
        voices = []
        pet.voice.ids = {l.id for _, l in PL.all_lines()}
        pet.voice.play = lambda i, v: voices.append(i) or True
        open(FS, 'w').close()
        try:
            pet.brain_tick()
            self.assertTrue(pet.fs_hidden); self.assertFalse(pet.isVisible())
            self.assertFalse(pet.panel.isVisible(), '全屏时计时器小窗也要藏')
            pet.say('poke')                                       # 全屏中不出声
            self.assertEqual(voices, [])
            pet.timer.mode = 'pomo'; pet.timer.start(); pet.timer.acc = pet.timer.phase_len() + 1
            pet.brain_tick()
            self.assertEqual(pet.fs_missed, 'pomo_focus_end')
        finally:
            os.remove(FS)
        pet.bubble = None
        pet.brain_tick()                                          # 退出全屏：小窗回来，计时提醒在这一秒补说一次
        self.assertTrue(pet.isVisible()); self.assertTrue(pet.panel.isVisible())
        self.assertIsNone(pet.pending_ev)
        self.assertIsNotNone(pet.bubble)
        ids = {l.text for l in PL.LINES['pomo_focus_end']}
        self.assertIn(pet.bubble[0], ids)
        b = pet.bubble[0]
        pet.bubble = None
        pet.brain_tick()                                          # 只补一次
        self.assertIsNone(pet.bubble)
        pet.panel.close()


class T7_Bubble(unittest.TestCase):
    def test_pure(self):
        vis = QRect(0, 80, 340, 400)
        self.assertEqual(Z.clamp_bubble_y(10, 50, vis), 82)
        self.assertEqual(Z.clamp_bubble_y(100, 50, vis), 100)
        self.assertEqual(Z.clamp_bubble_y(460, 50, vis), 479 - 2 - 12 - 50)

    def test_top_of_screen(self):
        pet = make_pet()
        g = pet.screen_of(pet.sprite_rect().center()).availableGeometry()
        pet.move(pet.x(), g.top() - 80)                        # 窗口上沿伸出屏幕 80px（ensure_visible 允许的情况）
        pet.show_bubble('这是一句挺长的台词，用来看气泡会不会跑出屏幕顶上去呀～')
        r = pet.bubble_rect().translated(pet.pos())
        self.assertGreaterEqual(r.top(), g.top())
        self.assertLessEqual(r.bottom(), g.bottom())
        pet.close()


class T8_Diagnostics(unittest.TestCase):
    def test_pure(self):
        smap = Z.screen_map(['DELL U2720Q', '\\\\.\\DISPLAY2'])
        self.assertEqual(smap, {'DELL U2720Q': 'screen_1', '\\\\.\\DISPLAY2': 'screen_2'})
        st = dict(P.DEFAULTS); st['pos'] = {'DELL U2720Q': [0.5, 0.9], 'Other': [0.1, 0.1]}
        st['last_screen'] = 'DELL U2720Q'; st['future_secret_setting'] = 'abc'
        d = Z.diag_settings(st, smap)
        self.assertNotIn('future_secret_setting', d)
        self.assertEqual(d['last_screen'], 'screen_1')
        self.assertEqual(set(d['pos']), {'screen_1', 'screen_other'})
        t = Z.redact_text('restore pos DELL U2720Q at C:\\Users\\me\\x.png and /home/me/a and \\\\srv\\share', smap)
        for bad in ('DELL', 'Users', '/home', 'srv'):
            self.assertNotIn(bad, t)
        self.assertEqual(Z.ext_label('PNG'), '.png')
        self.assertEqual(Z.ext_label('mysecretproject'), 'other')

    def test_export(self):
        pet = make_pet()
        pet.st['pos']['MyMonitorName'] = [0.5, 0.5]
        pet.log('fake line with', TMP)
        path = pet.export_log()
        self.assertTrue(path and os.path.exists(path))
        text = open(path, encoding='utf-8').read()
        self.assertNotIn('MyMonitorName', text)
        self.assertNotIn(TMP, text)
        for s in app.screens():
            if len(s.name()) >= 3:
                self.assertNotIn(s.name(), text)
        pet.close()


class FakeMime:
    def __init__(self, urls): self._u = urls
    def hasUrls(self): return bool(self._u)
    def urls(self): return self._u


class FakeDrag:
    def __init__(self, urls, actions):
        self.md = FakeMime(urls); self.actions = actions; self.accepted = None; self.action = None
    def mimeData(self): return self.md
    def possibleActions(self): return self.actions
    def setDropAction(self, a): self.action = a
    def accept(self): self.accepted = True
    def ignore(self): self.accepted = False


class T9_DragAndShell(unittest.TestCase):
    def test_copy_only(self):
        from PySide6.QtCore import QUrl
        u = [QUrl.fromLocalFile('/tmp/a.png')]
        e = FakeDrag(u, Qt.CopyAction | Qt.MoveAction)
        self.assertTrue(Z.Pet.accept_copy_only(e)); self.assertEqual(e.action, Qt.CopyAction)
        e = FakeDrag(u, Qt.MoveAction)
        self.assertFalse(Z.Pet.accept_copy_only(e)); self.assertFalse(e.accepted)
        e = FakeDrag([QUrl('https://example.com/a.png')], Qt.CopyAction)
        self.assertFalse(Z.Pet.accept_copy_only(e))

    def test_shell(self):
        self.assertTrue(P.is_shell_window('Shell_TrayWnd', None))
        self.assertTrue(P.is_shell_window('Windows.UI.Core.CoreWindow', 'startmenuexperiencehost.exe'))
        self.assertTrue(P.is_shell_window('Windows.UI.Core.CoreWindow', None))     # 查不到进程：保持旧行为
        self.assertFalse(P.is_shell_window('Windows.UI.Core.CoreWindow', 'somegame.exe'))
        self.assertFalse(P.is_shell_window('UnityWndClass', 'somegame.exe'))


class T10_SizeAskAndAbout(unittest.TestCase):
    """v0.3.5 补丁：调完大小问一句 size01；关于页用统一声明。"""
    def setUp(self):
        self.old_ms = Z.SIZE_ASK_MS; Z.SIZE_ASK_MS = 80

    def tearDown(self):
        Z.SIZE_ASK_MS = self.old_ms

    def said(self, pet):
        return pet.bubble is not None and pet.bubble[0] == '这个大小可以吗？'

    def test_startup_restore_does_not_ask(self):
        st_scale = 0.8
        log = P.Log(None); st = P.Settings(None, log); st['first_run_done'] = True; st['scale'] = st_scale
        pet = Z.Pet(TMP, log, st, FakeLock()); pet.show(); pet.brain_timer.stop(); pet.anim_timer.stop()
        self.assertFalse(pet.size_timer.isActive())
        pet.bubble = None; pump(0.3)
        self.assertFalse(self.said(pet))
        pet.close()

    def test_debounced_once_after_last_step(self):
        pet = make_pet(); pet.bubble = None
        for v in (0.9, 0.85, 0.8, 0.75):            # 连续拖滑块
            pet.set_scale(v); pump(0.03)
        self.assertFalse(self.said(pet), '还在调的时候不该问')
        pump(0.3)
        self.assertTrue(self.said(pet))
        pet.bubble = None
        pet.set_scale(0.7); pump(0.3)              # 20 秒冷却内再调：不重复问
        self.assertFalse(self.said(pet))
        pet.close()

    def test_same_scale_no_ask(self):
        pet = make_pet(); pet.bubble = None
        pet.set_scale(pet.sp.s); pump(0.3)
        self.assertFalse(pet.size_timer.isActive()); self.assertFalse(self.said(pet))
        pet.close()

    def test_respects_quiet_hidden_drag(self):
        pet = make_pet(); pet.bubble = None
        pet.st['quiet_until'] = time.time() + 3600
        pet.set_scale(0.9); pump(0.3)
        self.assertFalse(self.said(pet), '安静模式不问')
        pet.st['quiet_until'] = 0
        pet.user_hidden = True; pet.apply_visibility()
        pet.set_scale(0.8); pump(0.3)
        self.assertFalse(self.said(pet), '藏起来不问')
        pet.user_hidden = False; pet.apply_visibility()
        pet.fs_hidden = True; pet.apply_visibility()
        pet.set_scale(0.7); pump(0.3)
        self.assertFalse(self.said(pet), '全屏躲开不问')
        pet.fs_hidden = False; pet.apply_visibility()
        pet.dragging = True
        pet.set_scale(0.6); pump(0.3)
        self.assertFalse(self.said(pet), '正拖着不问')
        pet.dragging = False
        pet.set_scale(0.65); pump(0.3)
        self.assertTrue(self.said(pet), '前面都没说出口，不该占冷却')
        pet.close()

    def test_about_disclaimer(self):
        d = '非官方粉丝二创，与阿里巴巴及通义千问无隶属或合作关系。'
        self.assertEqual(Z.DISCLAIMER, d)
        html = Z.ABOUT_HTML.format(v=Z.VERSION)
        self.assertIn(d, html)
        self.assertNotIn('无关', html.replace(Z.NOTICE, ''))   # v0.3.9：只有用户定稿的发布声明里出现「官方无关」
        self.assertIn('ZipZipPipe', html); self.assertIn('AI 生成内容', html); self.assertIn('下架', html)
        readme = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
        self.assertIn(d, readme); self.assertIn('千问娘今天也在记账', readme)
        self.assertIn('将停止分发并下架', readme)


if __name__ == '__main__':
    unittest.main(verbosity=2)
