#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机助手通道 M1。离屏可跑，不需要 Mac。

  QT_QPA_PLATFORM=offscreen python tests/test_control_m1.py

覆盖：开关关着时连不上、离线脑照旧；打开后 say 出气泡；错口令拒绝；
带 Origin 拒绝；安静时 normal 不说。另外核对 Host、优先级、关开关会停监听。
"""
import os, sys, json, time, base64, socket, threading, subprocess, tempfile, unittest
import http.client as http_client

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['ZHANGGUI_PET_NO_AUDIO'] = '1'
os.environ['ZHANGGUI_PET_NO_OPEN'] = '1'
os.environ['ZHANGGUI_PET_NO_DIALOG'] = '1'
os.environ.pop('ZHANGGUI_PET_DEBUG', None)
os.environ.pop('ZHANGGUI_PET_ORDER', None)
TMP = tempfile.mkdtemp(prefix='zg_m1_')
os.environ['ZHANGGUI_PET_CONFIG_DIR'] = TMP
IDLE = os.path.join(TMP, 'idle.txt')
open(IDLE, 'w').write('0')
os.environ['ZHANGGUI_PET_SIM_IDLE_FILE'] = IDLE
os.environ['ZHANGGUI_PET_SIM_FULLSCREEN_FILE'] = os.path.join(TMP, 'fs.flag')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CTL = os.path.join(ROOT, 'tools', 'pet_ctl.py')

import pet_control as C
import pet_platform as P
import zhanggui_pet as Z
from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtCore import QCoreApplication

app = QApplication.instance() or QApplication([])

MARK = 'M1_BUBBLE_唯一台词'
TOKEN_MARK = 'token-should-not-leak'


class FakeLock:
    def poked(self):
        return False


def make_pet():
    log = P.Log(TMP)
    st = P.Settings(None, log)
    st['first_run_done'] = True
    st['time_greet'] = False
    pet = Z.Pet(TMP, log, st, FakeLock())
    pet.show()
    pet.brain_timer.stop()
    pet.anim_timer.stop()
    return pet


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def publish_port(port):
    path = os.path.join(TMP, 'settings.json')
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    data['control_port'] = port
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def pump(secs=0.05):
    end = time.time() + secs
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def enable(pet):
    port = free_port()
    pet.st['control_port'] = port
    publish_port(port)
    ok = pet.set_control_enabled(True)
    pet.bubble = None
    if not ok:
        raise AssertionError('control did not start')
    return pet.control.bound_port


def stop(pet):
    try:
        pet.set_control_enabled(False)
    except Exception:
        pet._control_stop()
    pet.close()


def b64(obj):
    return base64.b64encode(json.dumps(obj, ensure_ascii=False).encode('utf-8')).decode('ascii')


def http(port, token, action, payload):
    """在别的线程里请求，主线程抽事件，避免和界面抢同一条线程。"""
    box = {}

    def run():
        try:
            box['v'] = C.call(port, token, action, payload)
        except Exception as e:
            box['e'] = e

    t = threading.Thread(target=run)
    t.start()
    end = time.time() + 5
    while t.is_alive() and time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    t.join(0.5)
    if 'e' in box:
        raise box['e']
    return box.get('v')


def run_ctl(args, timeout=5):
    env = os.environ.copy()
    env['ZHANGGUI_PET_CONFIG_DIR'] = TMP
    proc = subprocess.Popen(
        [sys.executable, CTL, *args], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    end = time.time() + timeout
    while proc.poll() is None and time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    if proc.poll() is None:
        proc.kill()
    out, err = proc.communicate(timeout=2)
    return proc.returncode, out, err


def log_text(pet):
    return '\n'.join(pet.log.ring)


class T0_Protocol(unittest.TestCase):
    def test_defaults_and_token_mode(self):
        self.assertEqual(C.DEFAULT_PORT, 6710)
        conf = tempfile.mkdtemp(prefix='zg_tok_')
        token = C.write_token(conf)
        path = C.token_path(conf)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(C.read_token(conf), token)
        again = C.write_token(conf)
        self.assertEqual(again, token)
        fresh = C.write_token(conf, force=True)
        self.assertNotEqual(fresh, token)
        self.assertEqual(os.stat(path).st_mode & 0o600, 0o600)
        cmd, err = C.validate('say', {'text': 'hi', 'extra': 1})
        self.assertEqual(err, 'bad args')
        self.assertIsNone(cmd)
        cmd, err = C.validate('say', {'text': MARK, 'expr': 'smile'})
        self.assertIsNone(err)
        self.assertEqual(cmd['priority'], 'normal')
        self.assertFalse(cmd['voice'])
        self.assertEqual(C.validate('say', {'text': ''})[1], 'bad args')
        self.assertEqual(C.validate('say', {'text': 'x' * 201})[1], 'bad args')
        self.assertEqual(C.validate('quiet', {'minutes': True})[1], 'bad args')
        self.assertEqual(C.validate('quiet', {'minutes': 0})[1], 'bad args')
        self.assertEqual(C.validate('line', {'id': 'poke08'})[0]['id'], 'poke08')
        self.assertEqual(C.validate('line', {'id': 'no-such'})[1], 'bad args')

    def _server(self, dispatch):
        logs = []
        token = 'proto-token-not-for-logs'
        srv = C.ControlServer(0, token, dispatch, logs.append)
        srv.start()
        self.addCleanup(srv.stop)
        return srv, token, logs

    def test_rejects_token_origin_host_and_limits(self):
        seen = []
        srv, token, logs = self._server(lambda cmd: seen.append(cmd) or {'ok': True, 'action': cmd['action'], 'result': {'status': 'ok'}})
        port = srv.bound_port
        self.assertEqual(srv.httpd.socket.getsockname()[0], '127.0.0.1')
        bad = C.call(port, 'wrong-token', 'status', {})
        self.assertFalse(bad['ok'])
        self.assertEqual(bad['error'], '口令不对')
        self.assertEqual(seen, [])
        conn = http_client.HTTPConnection('127.0.0.1', port, timeout=3)
        conn.request('POST', '/say', b'{"text":"%s"}' % MARK.encode(), headers={
            'Host': '127.0.0.1:%d' % port,
            'Origin': 'http://evil.example/secret',
            'Content-Type': 'application/json',
            'X-Pet-Token': token,
        })
        resp = conn.getresponse()
        body = json.loads(resp.read().decode())
        conn.close()
        self.assertEqual(body['error'], '来源不对')
        self.assertEqual(seen, [])
        conn = http_client.HTTPConnection('127.0.0.1', port, timeout=3)
        conn.request('POST', '/status', b'{}', headers={
            'Host': 'localhost:%d' % port,
            'Content-Type': 'application/json',
            'X-Pet-Token': token,
        })
        body = json.loads(conn.getresponse().read().decode())
        conn.close()
        self.assertEqual(body['error'], '地址不对')
        unknown = C.call(port, token, 'say', {'text': MARK, 'extra': 1})
        self.assertEqual(unknown['error'], 'bad args')
        self.assertEqual(seen, [])
        srv.hits.clear()
        self.assertTrue(C.call(port, token, 'status', {})['ok'])
        self.assertTrue(C.call(port, token, 'status', {})['ok'])
        limited = C.call(port, token, 'status', {})
        self.assertEqual(limited['error'], '太频繁')
        blob = '\n'.join(logs)
        self.assertNotIn(token, blob)
        self.assertNotIn(MARK, blob)
        self.assertNotIn('evil.example', blob)
        self.assertIn('rejected(bad token)', blob)
        self.assertIn('rejected(origin)', blob)
        self.assertIn('rejected(host)', blob)
        srv.stop()
        self.assertFalse(C.call(port, token, 'status', {})['ok'])
        self.assertEqual(C.call(port, token, 'status', {})['error'], '控制未开启')


class T1_Off(unittest.TestCase):
    def test_off_connect_fails_and_offline_brain_unchanged(self):
        pet = make_pet()
        try:
            self.assertFalse(pet.st['control_enabled'])
            self.assertIsNone(pet.control)
            port = free_port()
            publish_port(port)
            s = socket.socket()
            s.settimeout(0.3)
            with self.assertRaises(OSError):
                s.connect(('127.0.0.1', port))
            s.close()
            code, out, err = run_ctl(['status'])
            self.assertEqual(code, 1, out + err)
            self.assertEqual(json.loads(out)['error'], '控制未开启')
            self.assertEqual(err, '')
            said = []
            orig = pet.say
            pet.say = lambda cat, **kw: (said.append(cat), orig(cat, **kw))[1]
            r = pet.run_candidates([
                dict(prio=Z.PRIO_WATER, cat='water', proactive=True, oneshot=False),
                dict(prio=Z.PRIO_TIMER, cat='pomo_focus_end', proactive=False, oneshot=True),
            ])
            self.assertEqual(r, 'pomo_focus_end')
            self.assertEqual(said, ['pomo_focus_end'])
            pet.bubble = None
            pet.on_click('body')
            self.assertTrue(pet.bubble and pet.bubble[0])
            self.assertNotIn('control ', log_text(pet))
        finally:
            stop(pet)


class T2_On(unittest.TestCase):
    def test_say_expr_line_and_log_redaction(self):
        pet = make_pet()
        try:
            port = enable(pet)
            token = C.read_token(TMP)
            self.assertTrue(token)
            self.assertEqual(os.stat(C.token_path(TMP)).st_mode & 0o777, 0o600)
            self.assertNotIn(token, log_text(pet))
            code, out, err = run_ctl(['status'])
            self.assertEqual(code, 0, out + err)
            status = json.loads(out)
            self.assertTrue(status['ok'])
            self.assertTrue(status['result']['enabled'])
            self.assertFalse(status['result']['quiet'])
            self.assertEqual(status['result']['cursor'], 0)
            pet.bubble = None
            result = http(port, token, 'say', {'text': MARK + ' /Users/secret/note', 'expr': 'smile', 'source': '助手'})
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['result']['status'], 'ok')
            self.assertIn(MARK, pet.bubble[0])
            self.assertIn('· 助手', pet.bubble[0])
            self.assertEqual(pet.expr, 'smile')
            blob = log_text(pet)
            self.assertIn('control say ok', blob)
            self.assertNotIn(MARK, blob)
            self.assertNotIn(token, blob)
            self.assertNotIn('/Users/secret', blob)
            path = pet.export_log()
            with open(path, encoding='utf-8') as f:
                exported = f.read()
            self.assertNotIn(MARK, exported)
            self.assertNotIn(token, exported)
            self.assertNotIn('/Users/secret', exported)
            pet.bubble = None
            pet.control.hits.clear()
            line = http(port, token, 'line', {'id': 'poke08'})
            self.assertTrue(line['ok'], line)
            self.assertIn('你已经做得很好了', pet.bubble[0])
            self.assertEqual(line['result'].get('voice'), 'skipped')
            bad = http(port, 'nope-' + token, 'say', {'text': '不该出现'})
            self.assertEqual(bad['error'], '口令不对')
            self.assertNotIn('不该出现', pet.bubble[0])
            conn = http_client.HTTPConnection('127.0.0.1', port, timeout=3)
            conn.request('POST', '/say', json.dumps({'text': '网页不该说'}).encode(), headers={
                'Host': '127.0.0.1:%d' % port,
                'Origin': 'http://evil.example/secret',
                'Content-Type': 'application/json',
                'X-Pet-Token': token,
            })
            body = json.loads(conn.getresponse().read().decode())
            conn.close()
            pump(0.1)
            self.assertEqual(body['error'], '来源不对')
            self.assertNotIn('网页不该说', pet.bubble[0])
            self.assertNotIn('evil.example', log_text(pet))
            self.assertIn('rejected(origin)', log_text(pet))
            pet.bubble = None
            pet.control.hits.clear()
            code, out, err = run_ctl(['say', '--json-base64', b64({'text': '命令行说一句', 'expr': 'thinking'})])
            self.assertEqual(code, 0, out + err)
            self.assertIn('命令行说一句', pet.bubble[0])
            self.assertEqual(pet.expr, 'thinking')
        finally:
            stop(pet)

    def test_quiet_skips_normal_and_important_is_silent(self):
        pet = make_pet()
        try:
            port = enable(pet)
            token = C.read_token(TMP)
            pet.st['quiet_until'] = time.time() + 600
            pet.bubble = None
            played = []
            pet.voice.play = lambda *a, **k: played.append(a) or True
            skipped = http(port, token, 'say', {'text': MARK + '安静时不说', 'priority': 'normal', 'voice': True})
            self.assertTrue(skipped['ok'], skipped)
            self.assertEqual(skipped['result']['status'], 'skipped:quiet')
            self.assertIsNone(pet.bubble)
            self.assertEqual(played, [])
            self.assertIn('skipped(quiet)', log_text(pet))
            self.assertNotIn(MARK, log_text(pet))
            shown = http(port, token, 'say', {
                'text': MARK + '要紧的只出字', 'priority': 'important', 'voice': True, 'expr': 'thinking'})
            self.assertTrue(shown['ok'], shown)
            self.assertEqual(shown['result']['status'], 'ok')
            self.assertEqual(shown['result']['voice'], 'skipped')
            self.assertIn(MARK + '要紧的只出字', pet.bubble[0])
            self.assertEqual(played, [])
            self.assertEqual(pet.expr, 'thinking')
            until = pet.st['quiet_until']
            shorter = pet._control_quiet(1)
            self.assertEqual(shorter['error'], '只能更安静')
            self.assertGreater(pet.st['quiet_until'], until - 1)
        finally:
            stop(pet)

    def test_normal_does_not_steal_poke_timer_or_water(self):
        pet = make_pet()
        try:
            port = enable(pet)
            token = C.read_token(TMP)
            pet.on_click('body')
            poke = pet.bubble[0]
            queued = http(port, token, 'say', {'text': MARK + '别打断戳', 'priority': 'normal'})
            self.assertEqual(queued['result']['status'], 'queued')
            self.assertEqual(pet.bubble[0], poke)
            pet.bubble = None
            pet.timer.mode = 'pomo'
            pet.timer.running = True
            pet.timer.phase = 'focus'
            pet.timer.acc = pet.timer.phase_len()
            pet.timer.t0 = time.monotonic()
            queued = http(port, token, 'say', {'text': MARK + '别打断计时'})
            self.assertEqual(queued['result']['status'], 'queued')
            self.assertIsNone(pet.bubble)
            pet.brain_tick()
            self.assertIsNotNone(pet.bubble)
            self.assertNotIn(MARK, pet.bubble[0])
            self.assertIn('pomo_focus_end', log_text(pet))
            pet.timer.running = False
            pet.bubble = None
            pet.control_q.clear()
            pet.st['remind_water'] = True
            pet.last_water = 0
            pet.away = False
            pet.control.hits.clear()
            queued = http(port, token, 'say', {'text': MARK + '别抢喝水'})
            self.assertEqual(queued['result']['status'], 'queued', queued)
            self.assertIsNone(pet.bubble)
            before = log_text(pet).count(' say water ')
            pet.brain_tick()
            self.assertGreater(log_text(pet).count(' say water '), before)
            self.assertNotIn(MARK, pet.bubble[0])
            pet.bubble = None
            pet.last_water = time.time()
            pet.brain_tick()
            self.assertIn(MARK + '别抢喝水', pet.bubble[0])
            pet.bubble = None
            pet.last_water = 0
            water_after = log_text(pet).count(' say water ')
            pet.brain_tick()
            self.assertEqual(log_text(pet).count(' say water '), water_after)
        finally:
            stop(pet)

    def test_off_stops_listener_and_clears_queue(self):
        pet = make_pet()
        try:
            port = enable(pet)
            token = C.read_token(TMP)
            pet.bubble = ('先占着', time.time() + 60)
            queued = http(port, token, 'say', {'text': MARK + '关掉就丢掉'})
            self.assertEqual(queued['result']['status'], 'queued')
            self.assertTrue(pet.control_q)
            self.assertTrue(pet.set_control_enabled(False) is False)
            self.assertIsNone(pet.control)
            self.assertEqual(pet.control_q, [])
            self.assertFalse(pet.st['control_enabled'])
            gone = C.call(port, token, 'status', {})
            self.assertEqual(gone['error'], '控制未开启')
            pet.bubble = None
            pet.brain_tick()
            self.assertTrue(pet.bubble is None or MARK not in pet.bubble[0])
        finally:
            stop(pet)

    def test_menu_hidden_when_frozen(self):
        pet = make_pet()
        try:
            pet.st['control_port'] = free_port()
            menu = QMenu()
            pet.fill_menu(menu)
            texts = _texts(menu)
            self.assertIn('高级', texts)
            self.assertIn('允许本机助手控制我（实验）', texts)
            toggle = _find(menu, '允许本机助手控制我（实验）')
            self.assertFalse(toggle.isChecked())
            toggle.trigger()
            pump(0.05)
            self.assertTrue(pet.st['control_enabled'])
            self.assertIsNotNone(pet.control)
            self.assertTrue(pet.control.accepting)
            sys.frozen = True
            try:
                pet.st['show_control_menu'] = False
                menu = QMenu()
                pet.fill_menu(menu)
                self.assertNotIn('高级', _texts(menu))
                pet.st['show_control_menu'] = True
                menu = QMenu()
                pet.fill_menu(menu)
                self.assertIn('允许本机助手控制我（实验）', _texts(menu))
            finally:
                del sys.frozen
        finally:
            stop(pet)

    def test_queue_drops_oldest(self):
        pet = make_pet()
        try:
            for i in range(6):
                pet._control_enqueue({'action': 'say', 'text': 'q%d' % i, 'priority': 'normal'})
            self.assertEqual(len(pet.control_q), 5)
            self.assertEqual([x['text'] for x in pet.control_q], ['q1', 'q2', 'q3', 'q4', 'q5'])
        finally:
            stop(pet)

    def test_setting_defaults_off_and_persists(self):
        conf = tempfile.mkdtemp(prefix='zg_set_')
        log = P.Log(None)
        st = P.Settings(conf, log)
        self.assertFalse(st['control_enabled'])
        self.assertFalse(st['show_control_menu'])
        self.assertEqual(st['control_port'], 6710)
        st['control_enabled'] = True
        st['control_port'] = 6719
        self.assertTrue(st.save())
        again = P.Settings(conf, log)
        self.assertTrue(again['control_enabled'])
        self.assertEqual(again['control_port'], 6719)
        diag = Z.diag_settings(again, {})
        self.assertNotIn('control_enabled', diag)
        self.assertNotIn('control_port', diag)


def _texts(menu):
    out = []
    for action in menu.actions():
        if action.text():
            out.append(action.text())
        if action.menu():
            out.extend(_texts(action.menu()))
    return out


def _find(menu, text):
    for action in menu.actions():
        if action.text() == text:
            return action
        if action.menu():
            found = _find(action.menu(), text)
            if found is not None:
                return found
    return None


if __name__ == '__main__':
    unittest.main(verbosity=2)
