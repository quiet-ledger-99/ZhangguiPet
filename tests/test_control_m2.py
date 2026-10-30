#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务卡确认流 M2。离屏可跑，不需要 Mac。

  QT_QPA_PLATFORM=offscreen python tests/test_control_m2.py

状态机：草稿 → 改一下升版本 → prepare → 确认 → report completed。
另外：双击确认只记一次、旧版 conflict、回单里的「请删除」只显示、
重启后已确认不会回到待确认、24 小时未确认作废、没有 confirm 命令。
"""
import os, sys, json, time, base64, socket, threading, subprocess, tempfile, unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['ZHANGGUI_PET_NO_AUDIO'] = '1'
os.environ['ZHANGGUI_PET_NO_OPEN'] = '1'
os.environ['ZHANGGUI_PET_NO_DIALOG'] = '1'
os.environ.pop('ZHANGGUI_PET_DEBUG', None)
os.environ.pop('ZHANGGUI_PET_ORDER', None)
TMP = tempfile.mkdtemp(prefix='zg_m2_')
os.environ['ZHANGGUI_PET_CONFIG_DIR'] = TMP
IDLE = os.path.join(TMP, 'idle.txt')
open(IDLE, 'w').write('0')
os.environ['ZHANGGUI_PET_SIM_IDLE_FILE'] = IDLE
os.environ['ZHANGGUI_PET_SIM_FULLSCREEN_FILE'] = os.path.join(TMP, 'fs.flag')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CTL = os.path.join(ROOT, 'tools', 'pet_ctl.py')

import pet_cards as K
import pet_control as C
import pet_platform as P
import zhanggui_pet as Z
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit
from PySide6.QtCore import QCoreApplication, Qt

app = QApplication.instance() or QApplication([])

COMMENT = 'Day5 置顶评论全文。第二句也在这里，不截断。'
REVISED = COMMENT + '\n第二句改软一点。'
DELETE_NOTE = '请删除 /Users/someone/old.mp4'


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


def http(port, token, action, payload, timeout=5.0):
    box = {}

    def run():
        try:
            box['v'] = C.call(port, token, action, payload, timeout=timeout)
        except Exception as e:
            box['e'] = e

    t = threading.Thread(target=run)
    t.start()
    end = time.time() + timeout + 1
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


def rpc(pet, action, payload, timeout=5):
    pet.control.hits.clear()
    return http(pet.control.bound_port, C.read_token(TMP), action, payload, timeout=timeout)


def ctl(pet, args, timeout=5):
    if pet.control is not None:
        pet.control.hits.clear()
    return run_ctl(args, timeout=timeout)


def fresh_pet():
    path = os.path.join(TMP, K.RECEIPTS_NAME)
    if os.path.exists(path):
        os.remove(path)
    pet = make_pet()
    enable(pet)
    return pet


def lines(path):
    if not path or not os.path.exists(path):
        return []
    out = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def new_card(text=COMMENT, category='outbound', title='Day5 置顶', target='B站 · Day5 置顶', source='助手'):
    return {
        'category': category,
        'title': title,
        'rawText': text,
        'target': target,
        'source': source,
    }


def events_named(path, name):
    return [row for row in lines(path) if row.get('event') == name]


class T0_Rules(unittest.TestCase):
    def test_no_confirm_command_and_categories(self):
        self.assertEqual(Z.VERSION, '0.3.11')
        self.assertFalse(P.DEFAULTS['control_enabled'])
        self.assertFalse(P.DEFAULTS['show_control_menu'])
        self.assertNotIn('confirm', C.ACTIONS)
        self.assertNotIn('confirm', C.CARD_SUBS)
        self.assertEqual(K.CARD_SUBS, frozenset({'draft', 'prepare', 'receipt', 'report', 'withdraw'}))
        self.assertEqual(K.CATEGORIES, frozenset({'money', 'delete', 'outbound', 'direction'}))
        self.assertEqual(K.CONFIRM_TTL_MS, 24 * 60 * 60 * 1000)
        self.assertEqual(K.RECEIPTS_NAME, 'receipts.jsonl')
        for cat, label in K.CATEGORY_LABEL.items():
            cmd, err = K.validate_card('draft', new_card(category=cat, title='四类都要'))
            self.assertIsNone(err)
            self.assertEqual(cmd['category'], cat)
            self.assertIn(label, K.CATEGORY_LABEL[cat])
        cmd, err = K.validate_card('draft', dict(new_card(), extra=1))
        self.assertEqual(err, 'bad args')
        self.assertIsNone(cmd)
        cmd, err = K.validate_card('draft', dict(new_card(), confirm=True))
        self.assertEqual(err, 'bad args')
        self.assertEqual(K.validate_card('confirm', new_card())[1], 'bad args')
        self.assertEqual(K.validate_card('draft', dict(new_card(), title='一二三四五六七八九十一二三四五六七八九十'))[1], None)
        self.assertEqual(K.validate_card('draft', dict(new_card(), title='一二三四五六七八九十一二三四五六七八九十一'))[1], 'bad args')
        self.assertEqual(K.validate_card('draft', dict(new_card(), rawText='字' * 2000))[1], None)
        self.assertEqual(K.validate_card('draft', dict(new_card(), rawText='字' * 2001))[1], 'bad args')
        self.assertEqual(K.validate_card('prepare', {'cardId': 'C-20261027-001', 'version': 1, 'confirm': True})[1], 'bad args')
        self.assertEqual(K.validate_card('prepare', {'cardId': 'C-20261027-001', 'version': True})[1], 'bad args')
        self.assertEqual(K.validate_card('receipt', {'operationId': 'OP-20261027-0001', 'since': 0})[1], 'bad args')
        self.assertEqual(K.validate_card('report', {
            'operationId': 'OP-20261027-0001', 'phase': 'confirmed', 'text': 'x',
        })[1], 'bad args')
        report_cmd, report_err = K.validate_card('report', {
            'operationId': 'OP-20261027-0001', 'phase': 'completed', 'text': '办好啦', 'ref': '',
        })
        self.assertIsNone(report_err)
        self.assertEqual(report_cmd['phase'], 'completed')
        self.assertEqual(report_cmd['text'], '办好啦')
        self.assertEqual(C.validate('card/confirm', {'cardId': 'C-20261027-001'})[1], 'bad args')
        self.assertEqual(C.validate('confirm', {})[1], 'bad args')

    def test_phase_order_conflict_once_and_expiry(self):
        conf = tempfile.mkdtemp(prefix='zg_book_')
        clock = [1_700_000_000_000]
        book = K.CardBook(conf, now_ms=lambda: clock[0])
        self.assertEqual(book.path, os.path.join(conf, 'receipts.jsonl'))
        made = book.handle(K.validate_card('draft', new_card())[0])
        cid, ver = made['cardId'], made['version']
        self.assertEqual(ver, 1)
        self.assertEqual(book.phase_of(cid), 'draft')
        raw = book.by_id[cid]['rawText']
        asked = book.user_act(cid, 'revise', 1)
        self.assertEqual(asked['event'], 'revise_requested')
        self.assertFalse(asked['already'])
        self.assertEqual(book.by_id[cid]['dispatchText'], raw)
        again = book.user_act(cid, 'revise', 1)
        self.assertTrue(again['already'])
        self.assertEqual(len(events_named(book.path, 'revise_requested')), 1)
        revised = book.handle(K.validate_card('draft', {
            'cardId': cid, 'dispatchText': REVISED, 'baseVersion': 1,
        })[0])
        self.assertEqual(revised['version'], 2)
        self.assertEqual(revised['phase'], 'draft')
        self.assertEqual(book.by_id[cid]['rawText'], raw)
        self.assertNotEqual(book.by_id[cid]['dispatchText'], raw)
        with self.assertRaises(K.CardError) as caught:
            book.handle(K.validate_card('draft', {
                'cardId': cid, 'dispatchText': '旧稿', 'baseVersion': 1,
            })[0])
        self.assertEqual(caught.exception.public, 'conflict')
        self.assertEqual(book.by_id[cid]['version'], 2)
        ready = book.handle(K.validate_card('prepare', {'cardId': cid, 'version': 2})[0])
        op = ready['operationId']
        self.assertTrue(op.startswith('OP-'))
        self.assertEqual(ready['phase'], 'awaiting_confirmation')
        same = book.handle(K.validate_card('prepare', {'cardId': cid, 'version': 2})[0])
        self.assertEqual(same['operationId'], op)
        self.assertEqual(len(events_named(book.path, 'prepared')), 1)
        waiting = []
        for i, cat in enumerate(('money', 'delete')):
            made_i = book.handle(K.validate_card('draft', new_card(
                text='排队 %d' % i, category=cat, title='排队 %d' % i, target='这里', source='助手',
            ))[0])
            waiting.append(made_i['cardId'])
            book.handle(K.validate_card('prepare', {'cardId': made_i['cardId'], 'version': 1})[0])
        fourth = book.handle(K.validate_card('draft', new_card(
            text='第四张', category='direction', title='第四张', target='这里', source='助手',
        ))[0])
        with self.assertRaises(K.CardError) as full:
            book.handle(K.validate_card('prepare', {'cardId': fourth['cardId'], 'version': 1})[0])
        self.assertEqual(full.exception.public, '太多待确认')
        self.assertEqual(book.phase_of(fourth['cardId']), 'draft')
        for wid in waiting:
            book.handle(K.validate_card('withdraw', {'cardId': wid})[0])
            self.assertEqual(book.phase_of(wid), 'unavailable')
        with self.assertRaises(K.CardError) as old:
            book.user_act(cid, 'confirm', 1)
        self.assertEqual(old.exception.public, 'conflict')
        self.assertEqual(events_named(book.path, 'confirmed'), [])
        before = read_bytes(book.path)
        done = book.user_act(cid, 'confirm', 2)
        self.assertEqual(done['phase'], 'confirmed')
        self.assertEqual(done['by'] if 'by' in done else K.BY_USER, K.BY_USER)
        second = book.user_act(cid, 'confirm', 2)
        self.assertTrue(second['already'])
        self.assertEqual(second['phase'], 'confirmed')
        self.assertEqual(len(events_named(book.path, 'confirmed')), 1)
        after = read_bytes(book.path)
        self.assertTrue(after.startswith(before))
        row = events_named(book.path, 'confirmed')[0]
        self.assertEqual(row['by'], 'user@pet')
        self.assertEqual(row['operationId'], op)
        self.assertEqual(row['version'], 2)
        self.assertEqual(os.stat(book.path).st_mode & 0o777, 0o600)
        with self.assertRaises(K.CardError) as skip:
            book.handle(K.validate_card('report', {
                'operationId': op, 'phase': 'completed', 'text': '太早',
            })[0])
        self.assertEqual(skip.exception.public, 'bad phase')
        self.assertEqual(book.phase_of(cid), 'confirmed')
        self.assertEqual(book.by_id[cid]['resultText'], '')
        book.handle(K.validate_card('report', {'operationId': op, 'phase': 'accepted'})[0])
        with self.assertRaises(K.CardError) as back:
            book.handle(K.validate_card('report', {'operationId': op, 'phase': 'accepted'})[0])
        self.assertEqual(back.exception.public, 'bad phase')
        book.handle(K.validate_card('report', {'operationId': op, 'phase': 'forwarding'})[0])
        with self.assertRaises(K.CardError):
            book.handle(K.validate_card('report', {'operationId': op, 'phase': 'accepted'})[0])
        book.handle(K.validate_card('report', {
            'operationId': op, 'phase': 'completed', 'text': '置顶好啦～', 'ref': '',
        })[0])
        self.assertEqual(book.phase_of(cid), 'completed')
        self.assertEqual(book.by_id[cid]['resultText'], '置顶好啦～')
        self.assertEqual(book.by_id[cid]['dispatchText'], REVISED)
        with self.assertRaises(K.CardError) as frozen:
            book.handle(K.validate_card('report', {'operationId': op, 'phase': 'failed', 'text': 'no'})[0])
        self.assertEqual(frozen.exception.public, 'bad phase')
        got = book.handle(K.validate_card('receipt', {'operationId': op})[0])
        self.assertEqual(got['phase'], 'completed')
        self.assertEqual([e['event'] for e in got['events']], ['confirmed'])
        reloaded = K.CardBook(conf, now_ms=lambda: clock[0])
        self.assertEqual(reloaded.phase_of(cid), 'completed')
        self.assertNotEqual(reloaded.phase_of(cid), 'awaiting_confirmation')

    def test_expiry_and_failed_write_and_display_only_text(self):
        conf = tempfile.mkdtemp(prefix='zg_exp_')
        clock = [1_700_000_000_000]
        book = K.CardBook(conf, now_ms=lambda: clock[0])
        made = book.handle(K.validate_card('draft', new_card(category='delete', title='清掉旧包'))[0])
        cid = made['cardId']
        book.handle(K.validate_card('prepare', {'cardId': cid, 'version': 1})[0])
        clock[0] += K.CONFIRM_TTL_MS - 1
        self.assertEqual(book.expire_due(), [])
        self.assertEqual(book.phase_of(cid), 'awaiting_confirmation')
        clock[0] += 1
        self.assertEqual(book.expire_due(), [cid])
        self.assertEqual(book.phase_of(cid), 'unavailable')
        with self.assertRaises(K.CardError) as late:
            book.user_act(cid, 'confirm', 1)
        self.assertEqual(late.exception.public, 'bad phase')
        self.assertEqual(events_named(book.path, 'confirmed'), [])
        self.assertEqual(book.expire_due(), [])

        conf2 = tempfile.mkdtemp(prefix='zg_io_')
        book2 = K.CardBook(conf2)
        made2 = book2.handle(K.validate_card('draft', new_card())[0])
        book2.handle(K.validate_card('prepare', {'cardId': made2['cardId'], 'version': 1})[0])
        snapshot = read_bytes(book2.path)

        def fail(rec):
            raise OSError('full')

        book2._writer = fail
        with self.assertRaises(OSError):
            book2.user_act(made2['cardId'], 'confirm', 1)
        self.assertEqual(book2.phase_of(made2['cardId']), 'awaiting_confirmation')
        self.assertEqual(read_bytes(book2.path), snapshot)
        with open(os.path.join(ROOT, 'pet_cards.py'), encoding='utf-8') as f:
            src = f.read()
        self.assertNotIn('subprocess', src)
        self.assertNotIn('os.system', src)


class T1_Window(unittest.TestCase):
    def test_scene_and_hard_rules(self):
        pet = fresh_pet()
        try:
            self.assertEqual(pet.cards.path, os.path.join(TMP, 'receipts.jsonl'))
            port = pet.control.bound_port
            token = C.read_token(TMP)
            full = ('置顶评论第二句。\n' * 40).strip()
            code, out, err = ctl(pet, ['card', 'draft', '--json-base64', b64(new_card(text=full))])
            self.assertEqual(code, 0, out + err)
            drafted = json.loads(out)
            self.assertTrue(drafted['ok'], drafted)
            self.assertEqual(drafted['action'], 'card')
            cid = drafted['result']['cardId']
            self.assertEqual(drafted['result']['phase'], 'draft')
            self.assertEqual(drafted['result']['version'], 1)
            pump(0.05)
            win = pet.card_windows[cid]
            self.assertTrue(win.isVisible())
            self.assertEqual(win.body.text(), full)
            self.assertGreater(win.scroll.viewport().height(), 0)
            self.assertGreater(win.body.minimumHeight(), win.scroll.viewport().height())
            self.assertFalse(win.btn_confirm.isVisible())
            self.assertTrue(win.btn_revise.isVisible())
            self.assertTrue(win.btn_reject.isVisible())
            self.assertEqual(win.btn_revise.text(), '改一下')
            self.assertEqual(win.btn_reject.text(), '不要')
            self.assertEqual(win.btn_confirm.text(), '确认')
            self.assertEqual(win.findChildren(QLineEdit), [])
            self.assertEqual(win.findChildren(QPlainTextEdit), [])
            self.assertEqual(win.findChildren(QTextEdit), [])
            self.assertTrue(win.windowFlags() & Qt.WindowDoesNotAcceptFocus)
            self.assertEqual(win.focusPolicy(), Qt.NoFocus)
            self.assertEqual(win.btn_confirm.focusPolicy(), Qt.NoFocus)
            self.assertIn('📤 要发出去', win.tag.text())
            raw = pet.cards.by_id[cid]['rawText']
            win.press('revise')
            self.assertEqual(pet.cards.by_id[cid]['dispatchText'], raw)
            self.assertEqual(win.body.text(), full)
            self.assertEqual(len(events_named(pet.cards.path, 'revise_requested')), 1)
            self.assertEqual(pet.cards.phase_of(cid), 'draft')

            code, out, err = ctl(pet, ['card', 'draft', '--json-base64', b64({
                'cardId': cid, 'dispatchText': REVISED, 'baseVersion': 1,
            })])
            self.assertEqual(code, 0, out + err)
            revised = json.loads(out)['result']
            self.assertEqual(revised['version'], 2)
            self.assertEqual(revised['phase'], 'draft')
            pump(0.05)
            win = pet.card_windows[cid]
            self.assertEqual(win.body.text(), REVISED)
            self.assertTrue(win.modified.isVisible())
            self.assertEqual(win.modified.text(), '已修改（相对原稿）')
            self.assertFalse(win.btn_confirm.isVisible())
            self.assertEqual(pet.cards.by_id[cid]['rawText'], raw)
            self.assertIn('v2', win.meta.text())

            code, out, err = ctl(pet, ['card', 'prepare', '--json-base64', b64({'cardId': cid, 'version': 2})])
            self.assertEqual(code, 0, out + err)
            prepared = json.loads(out)['result']
            op = prepared['operationId']
            self.assertEqual(prepared['phase'], 'awaiting_confirmation')
            pump(0.05)
            win = pet.card_windows[cid]
            self.assertTrue(win.btn_confirm.isVisible())
            self.assertEqual(win.btn_confirm.property('expectedVersion'), 2)
            self.assertEqual(win.bound_version, 2)
            self.assertEqual(win.hint.text(), '这张要你点头才行～')
            self.assertIsNotNone(pet.bubble)
            self.assertIn('有张卡要你看～', pet.bubble[0])
            self.assertNotIn(REVISED, pet.bubble[0])

            win.press('confirm')
            win.press('confirm')
            self.assertEqual(len(events_named(pet.cards.path, 'confirmed')), 1)
            self.assertEqual(pet.cards.phase_of(cid), 'confirmed')
            self.assertFalse(win.btn_confirm.isVisible())
            self.assertEqual(win.status.text(), '已确认，等助手去办')
            self.assertEqual(win.hint.text(), '收到啦，等助手来取～')
            confirmed = events_named(pet.cards.path, 'confirmed')[0]
            self.assertEqual(confirmed['by'], 'user@pet')
            self.assertEqual(confirmed['version'], 2)
            self.assertEqual(confirmed['operationId'], op)

            early = rpc(pet, 'card/report', {'operationId': op, 'phase': 'completed', 'text': '太早'})
            self.assertEqual(early['error'], 'bad phase')
            self.assertEqual(pet.cards.phase_of(cid), 'confirmed')
            for phase in ('accepted', 'forwarding'):
                step = rpc(pet, 'card/report', {'operationId': op, 'phase': phase})
                self.assertTrue(step['ok'], step)
                self.assertEqual(step['result']['phase'], phase)
            sentinel = os.path.join(TMP, 'keep-me.txt')
            with open(sentinel, 'w', encoding='utf-8') as f:
                f.write('stay')
            done = rpc(pet, 'card/report', {
                'operationId': op, 'phase': 'completed', 'text': DELETE_NOTE, 'ref': '/Users/someone/out',
            })
            self.assertTrue(done['ok'], done)
            self.assertNotIn('text', done['result'])
            pump(0.05)
            win = pet.card_windows[cid]
            self.assertEqual(win.phase, 'completed')
            self.assertIn('办好啦～', win.hint.text())
            self.assertIn('请删除', win.result.text())
            self.assertIn('<path>', win.result.text())
            self.assertNotIn('/Users/someone', win.result.text())
            self.assertEqual(win.body.text(), REVISED)
            self.assertNotIn('请删除', win.body.text())
            self.assertTrue(os.path.exists(sentinel))
            with open(sentinel, encoding='utf-8') as f:
                self.assertEqual(f.read(), 'stay')
            blob = '\n'.join(pet.log.ring)
            self.assertNotIn(REVISED, blob)
            self.assertNotIn(DELETE_NOTE, blob)
            self.assertNotIn(token, blob)
            self.assertNotIn('/Users/someone', blob)
            exported = pet.export_log()
            with open(exported, encoding='utf-8') as f:
                report = f.read()
            self.assertNotIn(REVISED, report)
            self.assertNotIn('请删除', report)
            self.assertNotIn('/Users/someone', report)
            self.assertNotIn(token, report)

            code, out, err = ctl(pet, ['confirm'])
            self.assertEqual(code, 1, out + err)
            self.assertEqual(json.loads(out)['error'], 'bad args')
            code, out, err = ctl(pet, ['card', 'confirm', '--json-base64', b64({'cardId': cid})])
            self.assertEqual(code, 1, out + err)
            self.assertEqual(json.loads(out)['error'], 'bad args')
            pet.control.hits.clear()
            denied = C.call(port, token, 'confirm', {})
            self.assertEqual(denied['error'], 'bad args')
            pet.control.hits.clear()
            denied = C.call(port, token, 'card/confirm', {'cardId': cid})
            self.assertEqual(denied['error'], 'bad args')
            pet.control.hits.clear()
            extra = rpc(pet, 'card/draft', dict(new_card(text='另一张'), note='no'))
            self.assertEqual(extra['error'], 'bad args')
        finally:
            stop(pet)

    def test_stale_click_unknown_quiet_restart_and_wait(self):
        pet = fresh_pet()
        try:
            drafted = rpc(pet, 'card/draft', new_card(text=COMMENT, category='direction', title='先做哪件'))
            self.assertTrue(drafted['ok'], drafted)
            cid = drafted['result']['cardId']
            self.assertIn('🧭 要你定方向', pet.card_windows[cid].tag.text())
            ready = rpc(pet, 'card/prepare', {'cardId': cid, 'version': 1})
            self.assertTrue(ready['ok'], ready)
            op = ready['result']['operationId']
            win = pet.card_windows[cid]
            self.assertEqual(win.bound_version, 1)
            stale_version = win.bound_version
            bumped = pet.cards.handle(C.validate('card/draft', {
                'cardId': cid, 'dispatchText': REVISED, 'baseVersion': 1,
            })[0])
            self.assertEqual(bumped['version'], 2)
            self.assertEqual(win.bound_version, 1)
            win.press('confirm')
            self.assertEqual(events_named(pet.cards.path, 'confirmed'), [])
            win = pet.card_windows[cid]
            self.assertEqual(win.body.text(), REVISED)
            self.assertEqual(win.hint.text(), K.CONFLICT_HINT)
            self.assertFalse(win.btn_confirm.isVisible())
            self.assertEqual(pet.cards.phase_of(cid), 'draft')
            old = rpc(pet, 'card/receipt', {'operationId': op})
            self.assertEqual(old['result']['phase'], 'unavailable')
            self.assertNotEqual(stale_version, win.bound_version)

            ready2 = rpc(pet, 'card/prepare', {'cardId': cid, 'version': 2})
            self.assertTrue(ready2['ok'], ready2)
            op2 = ready2['result']['operationId']
            self.assertNotEqual(op2, op)
            win = pet.card_windows[cid]
            self.assertTrue(win.btn_confirm.isVisible())

            box = {}

            def run_wait():
                box['v'] = C.call(pet.control.bound_port, C.read_token(TMP), 'wait',
                                  {'since': 0, 'timeoutMs': 4000}, timeout=8)

            pet.control.hits.clear()
            waiter = threading.Thread(target=run_wait)
            waiter.start()
            end = time.monotonic() + 0.35
            while time.monotonic() < end:
                QCoreApplication.processEvents()
                time.sleep(0.01)
            win.press('confirm')
            while waiter.is_alive() and time.monotonic() < end + 6:
                QCoreApplication.processEvents()
                time.sleep(0.01)
            waiter.join(1)
            self.assertFalse(waiter.is_alive())
            waited = box['v']
            self.assertTrue(waited['ok'], waited)
            names = [e['event'] for e in waited['result']['cardEvents']]
            self.assertIn('confirmed', names)
            self.assertNotIn(REVISED, json.dumps(waited['result']['cardEvents'], ensure_ascii=False))
            pet.control.hits.clear()
            fb = rpc(pet, 'feedback', {'since': 0})
            self.assertNotIn('cardEvents', fb['result'])
            self.assertEqual(len(events_named(pet.cards.path, 'confirmed')), 1)

            path = pet.cards.path
            nlines = len(lines(path))
            stop(pet)
            pet = None
            book = K.CardBook(TMP)
            self.assertEqual(book.phase_of(cid), 'confirmed')
            self.assertEqual(book.ops[op2]['phase'], 'confirmed')
            pet = make_pet()
            enable(pet)
            pump(0.05)
            win = pet.card_windows[cid]
            self.assertEqual(win.phase, 'confirmed')
            self.assertFalse(win.btn_confirm.isVisible())
            self.assertNotEqual(win.phase, 'awaiting_confirmation')
            self.assertEqual(win.status.text(), '已确认，等助手去办')
            win.press('confirm')
            self.assertEqual(len(lines(path)), nlines)
            self.assertEqual(len(events_named(path, 'confirmed')), 1)

            rpc(pet, 'card/report', {'operationId': op2, 'phase': 'accepted'})
            rpc(pet, 'card/report', {'operationId': op2, 'phase': 'forwarding'})
            unknown = rpc(pet, 'card/report', {'operationId': op2, 'phase': 'unknown', 'text': '请删除旧视频'})
            self.assertTrue(unknown['ok'], unknown)
            win = pet.card_windows[cid]
            self.assertEqual(win.phase, 'unknown')
            self.assertTrue(win.btn_look.isVisible())
            self.assertTrue(win.btn_redraft.isVisible())
            self.assertFalse(win.btn_confirm.isVisible())
            before = read_bytes(pet.cards.path)
            win.btn_look.click()
            win.btn_redraft.click()
            pump(0.05)
            self.assertEqual(read_bytes(pet.cards.path), before)
            self.assertEqual(pet.cards.phase_of(cid), 'unknown')
            self.assertIsNotNone(pet.bubble)
            self.assertIn('不会重发', pet.bubble[0])
            self.assertIn('请删除', win.result.text())

            pet.st['quiet_until'] = time.time() + 600
            pet.bubble = None
            quiet_card = rpc(pet, 'card/draft', new_card(text='安静时也挂着', title='安静卡片', category='money'))
            qid = quiet_card['result']['cardId']
            pet.bubble = None
            quiet_ready = rpc(pet, 'card/prepare', {'cardId': qid, 'version': 1})
            self.assertTrue(quiet_ready['ok'], quiet_ready)
            self.assertIsNone(pet.bubble)
            self.assertTrue(pet.card_windows[qid].isVisible())
            self.assertIn('💰 要花钱', pet.card_windows[qid].tag.text())
            qwin = pet.card_windows[qid]
            snap = read_bytes(pet.cards.path)
            real_writer = pet.cards._writer

            def fail_write(rec):
                raise OSError('full')

            pet.cards._writer = fail_write
            qwin.press('confirm')
            self.assertEqual(pet.cards.phase_of(qid), 'awaiting_confirmation')
            self.assertTrue(qwin.btn_confirm.isVisible())
            self.assertEqual(qwin.hint.text(), '这张要你点头才行～')
            self.assertEqual(read_bytes(pet.cards.path), snap)
            pet.cards._writer = real_writer

            clock = [pet.cards.now_ms()]
            pet.cards.now_ms = lambda: clock[0]
            pet.st['quiet_until'] = 0
            exp = rpc(pet, 'card/draft', new_card(text='会过期', title='过期卡', category='delete'))
            eid = exp['result']['cardId']
            clock[0] = pet.cards.by_id[eid]['updatedAt']
            rpc(pet, 'card/prepare', {'cardId': eid, 'version': 1})
            self.assertEqual(pet.cards.phase_of(eid), 'awaiting_confirmation')
            clock[0] += K.CONFIRM_TTL_MS
            pet._card_expire_tick()
            pump(0.05)
            self.assertEqual(pet.cards.phase_of(eid), 'unavailable')
            self.assertNotIn(eid, pet.card_windows)
            confirmed_before = len(events_named(pet.cards.path, 'confirmed'))
            pet.on_card_button(eid, 'confirm', 1)
            self.assertEqual(len(events_named(pet.cards.path, 'confirmed')), confirmed_before)

            sys.frozen = True
            try:
                pet.st['show_control_menu'] = False
                menu_texts = []
                from PySide6.QtWidgets import QMenu
                menu = QMenu()
                pet.fill_menu(menu)
                for action in menu.actions():
                    if action.text():
                        menu_texts.append(action.text())
                    if action.menu():
                        menu_texts.extend(a.text() for a in action.menu().actions())
                self.assertNotIn('高级', menu_texts)
            finally:
                del sys.frozen
        finally:
            if pet is not None:
                stop(pet)


if __name__ == '__main__':
    unittest.main(verbosity=2)
