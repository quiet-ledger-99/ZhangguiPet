#!/usr/bin/env python3
"""安静菜单位置，以及可选离线语音包：缺文件不报错，macOS 播放会调用 afplay。
运行：QT_QPA_PLATFORM=offscreen python tests/test_voice_pack.py
"""
import os
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['ZHANGGUI_PET_NO_AUDIO'] = '1'
os.environ['ZHANGGUI_PET_NO_OPEN'] = '1'
os.environ['ZHANGGUI_PET_NO_DIALOG'] = '1'
os.environ['ZHANGGUI_PET_SIM_NO_TRAY'] = '1'
os.environ.pop('ZHANGGUI_PET_DEBUG', None)
os.environ.pop('ZHANGGUI_PET_ORDER', None)
TMP = tempfile.TemporaryDirectory(prefix='zg_voice_')
os.environ['ZHANGGUI_PET_CONFIG_DIR'] = TMP.name
idle = Path(TMP.name, 'idle.txt')
idle.write_text('0')
os.environ['ZHANGGUI_PET_SIM_IDLE_FILE'] = str(idle)
os.environ['ZHANGGUI_PET_SIM_FULLSCREEN_FILE'] = str(Path(TMP.name, 'fs.flag'))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pet_platform as P
import zhanggui_pet as Z
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QMenu

app = QApplication.instance() or QApplication([])


def write_wav(path, n=8):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b'\x00\x00' * n)


class FakeLock:
    def poked(self):
        return False


class FakeScreen:
    def geometry(self):
        return QRect(0, 0, 1920, 1080)

    def availableGeometry(self):
        return QRect(0, 0, 1920, 1040)

    def name(self):
        return 'test_screen'


SCR = FakeScreen()


def top_labels(menu):
    return [a.text() for a in menu.actions() if a.text()]


class PlayerProbe(unittest.TestCase):
    def test_mac_prefers_afplay_over_paplay(self):
        def which(name):
            return {'afplay': '/usr/bin/afplay', 'paplay': '/usr/bin/paplay'}.get(name)

        kind, argv = P.resolve_audio_player(is_win=False, is_mac=True, which=which, executable=lambda p: False)
        self.assertEqual(kind, 'afplay')
        self.assertEqual(argv[0], '/usr/bin/afplay')

    def test_linux_does_not_pick_afplay(self):
        def which(name):
            return {'afplay': '/usr/bin/afplay', 'paplay': '/usr/bin/paplay'}.get(name)

        kind, argv = P.resolve_audio_player(is_win=False, is_mac=False, which=which, executable=lambda p: True)
        self.assertEqual(kind, 'paplay')
        self.assertEqual(argv, ['/usr/bin/paplay'])

    def test_afplay_fallback_path(self):
        kind, argv = P.resolve_audio_player(
            is_win=False, is_mac=True, which=lambda name: None,
            executable=lambda path: path == '/usr/bin/afplay')
        self.assertEqual((kind, argv), ('afplay', ['/usr/bin/afplay']))

    def test_no_player(self):
        kind, argv = P.resolve_audio_player(
            is_win=False, is_mac=True, which=lambda name: None, executable=lambda path: False)
        self.assertEqual((kind, argv), (None, None))

    def test_windows_winsound(self):
        self.assertEqual(P.resolve_audio_player(is_win=True, is_mac=False)[0], 'winsound')


class Playback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='zg_vdir_')
        self.logs = []

    def tearDown(self):
        self.tmp.cleanup()

    def voice(self, is_mac=True, which=None):
        if which is None:
            def which(name):
                return '/usr/bin/afplay' if name == 'afplay' else None
        with patch.object(P, 'IS_MAC', is_mac), patch.object(P, 'IS_WIN', False), \
                patch.object(P.shutil, 'which', side_effect=which):
            return P.Voice(self.tmp.name, None, lambda *a: self.logs.append(a))

    def play_live(self, v, line_id, volume):
        os.environ.pop('ZHANGGUI_PET_NO_AUDIO', None)
        try:
            with patch.object(P.subprocess, 'Popen') as popen:
                popen.return_value.poll.return_value = 0
                ok = v.play(line_id, volume)
                argv = popen.call_args.args[0] if popen.call_args else None
                return ok, argv, popen
        finally:
            os.environ['ZHANGGUI_PET_NO_AUDIO'] = '1'

    def test_missing_file_is_silent(self):
        v = self.voice()
        ok, argv, popen = self.play_live(v, 'no-such-line', 0.35)
        self.assertFalse(ok)
        popen.assert_not_called()
        self.assertIsNone(argv)
        self.assertEqual(self.logs, [])
        self.assertFalse(v.available())

    def test_missing_dir_does_not_raise(self):
        with patch.object(P, 'IS_MAC', True), patch.object(P, 'IS_WIN', False), \
                patch.object(P.shutil, 'which', return_value=None):
            v = P.Voice(os.path.join(self.tmp.name, 'missing'), None, lambda *a: self.logs.append(a))
        self.assertFalse(v.play('hi', 0.35))
        self.assertEqual(v.ids, set())
        self.assertEqual(self.logs, [])

    def test_mac_wav_calls_afplay(self):
        write_wav(os.path.join(self.tmp.name, 'hello.wav'))
        v = self.voice()
        self.assertTrue(v.available())
        self.assertEqual(v.kind, 'afplay')
        ok, argv, popen = self.play_live(v, 'hello', 0.35)
        self.assertTrue(ok)
        popen.assert_called_once()
        self.assertTrue(argv[0].endswith('afplay'), argv)
        self.assertTrue(argv[-1].endswith('.wav'), argv)
        self.assertNotIn('-v', argv)
        self.assertEqual(self.logs, [])

    def test_mac_ogg_calls_afplay_with_volume(self):
        ogg = os.path.join(self.tmp.name, 'hello.ogg')
        Path(ogg).write_bytes(b'OggSnot-a-real-page')
        v = self.voice()
        ok, argv, _popen = self.play_live(v, 'hello', 0.35)
        self.assertTrue(ok)
        self.assertTrue(argv[0].endswith('afplay'), argv)
        self.assertEqual(argv[1:3], ['-v', '0.35'])
        self.assertEqual(argv[-1], ogg)
        self.assertEqual(self.logs, [])

    def test_wav_preferred_over_ogg(self):
        write_wav(os.path.join(self.tmp.name, 'hello.wav'))
        Path(os.path.join(self.tmp.name, 'hello.ogg')).write_bytes(b'OggS')
        v = self.voice()
        self.assertEqual(v.paths['hello'][1], '.wav')
        ok, argv, _popen = self.play_live(v, 'hello', 0.2)
        self.assertTrue(ok)
        self.assertTrue(argv[-1].endswith('.wav'), argv)
        self.assertNotIn('-v', argv)

    def test_ogg_without_capable_player_returns_false(self):
        Path(os.path.join(self.tmp.name, 'hello.ogg')).write_bytes(b'OggS')
        v = self.voice(is_mac=False, which=lambda name: '/usr/bin/aplay' if name == 'aplay' else None)
        self.assertEqual(v.kind, 'aplay')
        self.assertTrue(v.available())
        ok, argv, popen = self.play_live(v, 'hello', 0.35)
        self.assertFalse(ok)
        popen.assert_not_called()
        self.assertIsNone(argv)
        self.assertEqual(self.logs, [])

    def test_bad_wav_logs_type_only(self):
        Path(os.path.join(self.tmp.name, 'hello.wav')).write_bytes(b'not a wav')
        v = self.voice()
        ok, _argv, _popen = self.play_live(v, 'hello', 0.35)
        self.assertFalse(ok)
        self.assertTrue(self.logs)
        self.assertEqual(self.logs[0][0], 'voice failed')
        blob = ' '.join(str(x) for x in self.logs[0])
        self.assertNotIn(self.tmp.name, blob)
        self.assertNotIn('hello.wav', blob)

    def test_readme_is_not_a_line(self):
        Path(os.path.join(self.tmp.name, 'README.md')).write_text('hi', encoding='utf-8')
        v = self.voice()
        self.assertEqual(v.ids, set())


class Menu(unittest.TestCase):
    def setUp(self):
        self.pets = []
        self.log = P.Log(None)

    def tearDown(self):
        for pet in self.pets:
            pet.close()
            pet.deleteLater()

    def pet(self):
        st = P.Settings(None, self.log)
        st['first_run_done'] = True
        pet = Z.Pet(TMP.name, self.log, st, FakeLock())
        self.pets.append(pet)
        pet.show()
        pet.brain_timer.stop()
        pet.anim_timer.stop()
        pet.screen_of = lambda pt: SCR
        pet.occupied = lambda pt: SCR.geometry().contains(pt)
        pet.set_anchor(QPoint(960, 1000))
        return pet

    def test_quiet_is_near_the_top(self):
        pet = self.pet()
        menu = QMenu(pet)
        pet.fill_menu(menu)
        labels = top_labels(menu)
        quiet = next(i for i, t in enumerate(labels) if t.startswith('安静一小时'))
        show = next(i for i, t in enumerate(labels) if t.startswith(('显示她', '先藏起来', '躲到屏幕边上')))
        legs = labels.index('飘着 / 长脚')
        size = next(i for i, t in enumerate(labels) if t.startswith('大小'))
        self.assertLess(show, quiet)
        self.assertLess(quiet, legs)
        self.assertLess(quiet, size)
        self.assertLess(quiet, 4)
        pet.st['quiet_until'] = time.time() + 3600
        pet.fill_menu(menu)
        labels = top_labels(menu)
        text = next(t for t in labels if t.startswith('结束安静'))
        self.assertRegex(text, r'^结束安静（还剩 \d+ 分钟）$')
        self.assertLess(labels.index(text), labels.index('飘着 / 长脚'))
        self.assertFalse(any(t.startswith('安静一小时') for t in labels))

    def test_sound_menu_shows_pack_state(self):
        pet = self.pet()
        menu = QMenu(pet)
        pet.fill_menu(menu)
        sound = next(a for a in menu.actions() if a.text() == '声音').menu()
        texts = [a.text() for a in sound.actions()]
        self.assertTrue(any('还没装语音包' in t for t in texts))
        self.assertFalse(any(t.startswith('语音包：已装') for t in texts))
        d = tempfile.mkdtemp(prefix='zg_pack_')
        write_wav(os.path.join(d, 'poke01.wav'))
        Path(os.path.join(d, 'other.ogg')).write_bytes(b'OggS')
        pet.voice.dir = d
        pet.fill_menu(menu)
        sound = next(a for a in menu.actions() if a.text() == '声音').menu()
        texts = [a.text() for a in sound.actions()]
        self.assertIn('语音包：已装 2 句', texts)
        self.assertFalse(any('还没装语音包' in t for t in texts))

    def test_say_without_voice_file_still_bubbles(self):
        pet = self.pet()
        empty = tempfile.mkdtemp(prefix='zg_empty_voice_')
        pet.voice.dir = empty
        pet.voice.scan()
        line = pet.say('poke')
        self.assertIsNotNone(line)
        self.assertIsNotNone(pet.bubble)
        self.assertIn(line.text, pet.bubble[0])
        self.assertFalse(pet.voice.has(line.id))

    def test_tray_and_context_share_fill_menu(self):
        src = (ROOT / 'zhanggui_pet.py').read_text(encoding='utf-8')
        self.assertIn('def contextMenuEvent', src)
        self.assertIn('self.fill_menu(m)', src)
        self.assertIn('self.tray_menu.aboutToShow.connect(lambda: self.fill_menu(self.tray_menu))', src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
