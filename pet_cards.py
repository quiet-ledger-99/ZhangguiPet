# -*- coding: utf-8 -*-
"""任务卡确认流（L2 / M2）。

桌宠只摆卡片、记回执。不跑模型，不派单，不外发，也不提供 confirm 命令。
确认只能来自卡片上的按钮（user@pet）。回执写进配置目录的 receipts.jsonl，
只追加；写成功之后调用方才改界面。Mac 上配置目录是
~/Library/Application Support/ZhangguiPet（见 pet_platform.config_candidates）。

阶段只能往前走。completed / failed / blocked / unknown / rejected / unavailable
是终点。awaiting_confirmation 过 24 小时没人点，记 unavailable。
"""
import json, os, re, datetime, threading

RECEIPTS_NAME = 'receipts.jsonl'
CARD_SUBS = frozenset({'draft', 'prepare', 'receipt', 'report', 'withdraw'})
CATEGORIES = frozenset({'money', 'delete', 'outbound', 'direction'})
DECISION_EVENTS = frozenset({'confirmed', 'revise_requested', 'rejected'})
REPORT_PHASES = frozenset({
    'accepted', 'forwarding', 'completed', 'failed', 'blocked', 'unknown',
})
# 只允许紧挨着的下一步。跳步和倒退都是 bad phase。
REPORT_NEXT = {
    'confirmed': frozenset({'accepted'}),
    'accepted': frozenset({'forwarding'}),
    'forwarding': frozenset({'completed', 'failed', 'blocked', 'unknown'}),
}
TERMINAL = frozenset({
    'completed', 'failed', 'blocked', 'unknown', 'rejected', 'unavailable',
})
USER_KINDS = frozenset({'confirm', 'revise', 'reject'})
CATEGORY_LABEL = {
    'money': '💰 要花钱',
    'delete': '🗑 要删东西',
    'outbound': '📤 要发出去',
    'direction': '🧭 要你定方向',
}
PHASE_HINT = {
    'draft': '这是草稿哦，还没定下来～',
    'awaiting_confirmation': '这张要你点头才行～',
    'confirmed': '收到啦，等助手来取～',
    'accepted': '正在办…',
    'forwarding': '正在办…',
    'completed': '办好啦～',
    'failed': '没成功…',
    'blocked': '卡住了，要不要叫人？',
    'unknown': '我也不确定发出去没有…要去看一眼吗？',
    'rejected': '好，那就不做啦',
    'unavailable': '',
}
CONFLICT_HINT = '内容刚更新过，请再看一眼'
CONFIRMED_STATUS = '已确认，等助手去办'

TITLE_MAX = 20
BODY_MAX = 2000
TARGET_MAX = 40
SOURCE_MAX = 24
REPORT_TEXT_MAX = 200
REF_MAX = 200
AWAITING_MAX = 3
CONFIRM_TTL_MS = 24 * 60 * 60 * 1000
BY_USER = 'user@pet'

_CARD_ID = re.compile(r'^C-\d{8}-\d{3,}$')
_OP_ID = re.compile(r'^OP-\d{8}-\d{4,}$')
_DRAFT_NEW = frozenset({'category', 'title', 'rawText', 'target', 'source'})
_DRAFT_REV = frozenset({'cardId', 'dispatchText', 'baseVersion'})
_PREPARE = frozenset({'cardId', 'version'})
_WITHDRAW = frozenset({'cardId'})
_REPORT_OK = frozenset({'operationId', 'phase', 'text', 'ref'})


class CardError(Exception):
    def __init__(self, code, public=None, expired=None):
        super().__init__(public or code)
        self.code = code
        self.public = public or code
        self.expired = list(expired or [])


def receipts_path(conf):
    if not conf:
        return None
    return os.path.join(conf, RECEIPTS_NAME)


def _pos_int(value, lo, hi):
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return lo <= value <= hi


def _text(value, lo, hi, newlines=False):
    if not isinstance(value, str) or not (lo <= len(value) <= hi):
        return False
    for ch in value:
        o = ord(ch)
        if o < 0x20 and not (newlines and ch in '\n\r\t'):
            return False
    if lo > 0 and not value.strip():
        return False
    return True


def _copy_fields(payload, names):
    return {k: payload[k] for k in names}


def validate_card(sub, payload):
    """白名单。通过返回 (cmd, None)，多一个字段或类型不对就是 (None, 'bad args')。"""
    if sub not in CARD_SUBS or not isinstance(payload, dict):
        return None, 'bad args'
    keys = set(payload)
    cmd = {'action': 'card', 'op': sub}
    if sub == 'draft':
        if keys == _DRAFT_NEW:
            if payload.get('category') not in CATEGORIES:
                return None, 'bad args'
            if not _text(payload.get('title'), 1, TITLE_MAX):
                return None, 'bad args'
            if not _text(payload.get('rawText'), 1, BODY_MAX, newlines=True):
                return None, 'bad args'
            if not _text(payload.get('target'), 1, TARGET_MAX):
                return None, 'bad args'
            if not _text(payload.get('source'), 1, SOURCE_MAX):
                return None, 'bad args'
            cmd.update(_copy_fields(payload, _DRAFT_NEW))
            return cmd, None
        if keys == _DRAFT_REV:
            if not isinstance(payload.get('cardId'), str) or not _CARD_ID.match(payload['cardId']):
                return None, 'bad args'
            if not _text(payload.get('dispatchText'), 1, BODY_MAX, newlines=True):
                return None, 'bad args'
            if not _pos_int(payload.get('baseVersion'), 1, 100000):
                return None, 'bad args'
            cmd.update(_copy_fields(payload, _DRAFT_REV))
            return cmd, None
        return None, 'bad args'
    if sub == 'prepare':
        if keys != _PREPARE:
            return None, 'bad args'
        if not isinstance(payload.get('cardId'), str) or not _CARD_ID.match(payload['cardId']):
            return None, 'bad args'
        if not _pos_int(payload.get('version'), 1, 100000):
            return None, 'bad args'
        cmd.update(_copy_fields(payload, _PREPARE))
        return cmd, None
    if sub == 'receipt':
        if keys == frozenset({'operationId'}):
            if not isinstance(payload.get('operationId'), str) or not _OP_ID.match(payload['operationId']):
                return None, 'bad args'
            cmd['operationId'] = payload['operationId']
            return cmd, None
        if keys == frozenset({'since'}):
            if not _pos_int(payload.get('since'), 0, 2 ** 31 - 1):
                return None, 'bad args'
            cmd['since'] = payload['since']
            return cmd, None
        return None, 'bad args'
    if sub == 'report':
        if not frozenset({'operationId', 'phase'}) <= keys <= _REPORT_OK:
            return None, 'bad args'
        if not isinstance(payload.get('operationId'), str) or not _OP_ID.match(payload['operationId']):
            return None, 'bad args'
        if payload.get('phase') not in REPORT_PHASES:
            return None, 'bad args'
        cmd['operationId'] = payload['operationId']
        cmd['phase'] = payload['phase']
        if 'text' in payload:
            if not _text(payload.get('text'), 0, REPORT_TEXT_MAX, newlines=True):
                return None, 'bad args'
            cmd['text'] = payload['text']
        if 'ref' in payload:
            if not _text(payload.get('ref'), 0, REF_MAX):
                return None, 'bad args'
            cmd['ref'] = payload['ref']
        return cmd, None
    if sub == 'withdraw':
        if keys != _WITHDRAW:
            return None, 'bad args'
        if not isinstance(payload.get('cardId'), str) or not _CARD_ID.match(payload['cardId']):
            return None, 'bad args'
        cmd['cardId'] = payload['cardId']
        return cmd, None
    return None, 'bad args'


def _now_ms():
    return int(__import__('time').time() * 1000)


class CardBook:
    """内存里的卡片 + 只追加的回执簿。先写盘再改内存。"""

    def __init__(self, conf, now_ms=None, writer=None):
        self.conf = conf
        self.path = receipts_path(conf)
        self.now_ms = now_ms or _now_ms
        self._writer = writer or self._append_file
        self.lock = threading.RLock()
        self.by_id = {}
        self.ops = {}
        self.events = []
        self.seq = 0
        self._counts = {}
        self._load()

    def handle(self, cmd):
        with self.lock:
            expired = self.expire_due()
            try:
                result = self._handle(cmd)
            except CardError as e:
                e.expired = expired
                raise
            if expired:
                result = dict(result)
                result['_expired'] = expired
            return result

    def user_act(self, card_id, kind, expected_version):
        if kind not in USER_KINDS:
            raise CardError('bad args', 'bad args')
        if not _pos_int(expected_version, 1, 100000):
            raise CardError('bad args', 'bad args')
        with self.lock:
            expired = self.expire_due()
            try:
                if kind == 'confirm':
                    result = self._user_confirm(card_id, expected_version)
                elif kind == 'revise':
                    result = self._user_revise(card_id, expected_version)
                else:
                    result = self._user_reject(card_id, expected_version)
            except CardError as e:
                e.expired = expired
                raise
            if expired:
                result = dict(result)
                result['_expired'] = expired
            return result

    def expire_due(self):
        """把超过 24 小时还停在待确认的卡记成 unavailable。返回这次作废的 cardId。"""
        with self.lock:
            changed = []
            now = self.now_ms()
            for card in list(self.by_id.values()):
                if card['phase'] != 'awaiting_confirmation':
                    continue
                started = int(card.get('awaitingAt') or 0)
                if now - started < CONFIRM_TTL_MS:
                    continue
                self._commit(self._unavailable_record(card, 'expired'))
                changed.append(card['cardId'])
            return changed

    def view(self, card_id):
        with self.lock:
            card = self.by_id.get(card_id)
            if not card:
                return None
            return {
                'cardId': card['cardId'],
                'version': card['version'],
                'phase': card['phase'],
                'category': card['category'],
                'categoryLabel': CATEGORY_LABEL.get(card['category'], card['category']),
                'title': card['title'],
                'target': card['target'],
                'source': card['source'],
                'dispatchText': card['dispatchText'],
                'modified': card['dispatchText'] != card['rawText'],
                'hint': PHASE_HINT.get(card['phase'], ''),
                'resultText': card.get('resultText') or '',
                'resultRef': card.get('resultRef') or '',
                'operationId': card.get('operationId'),
            }

    def phase_of(self, card_id):
        with self.lock:
            card = self.by_id.get(card_id)
            return None if card is None else card['phase']

    def open_ids(self):
        with self.lock:
            return [cid for cid, card in self.by_id.items() if card['phase'] != 'unavailable']

    def events_since(self, since):
        with self.lock:
            return [self._public_event(e) for e in self.events
                    if e.get('seq', 0) > since and e.get('event') in DECISION_EVENTS]

    def _handle(self, cmd):
        op = cmd.get('op') if isinstance(cmd, dict) else None
        if op == 'draft':
            if 'cardId' in cmd:
                return self._revise(cmd)
            return self._create(cmd)
        if op == 'prepare':
            return self._prepare(cmd)
        if op == 'receipt':
            return self._receipt(cmd)
        if op == 'report':
            return self._report(cmd)
        if op == 'withdraw':
            return self._withdraw(cmd)
        raise CardError('bad args', 'bad args')

    def _create(self, cmd):
        cid = self._mint('C')
        text = cmd['rawText']
        self._commit({
            'event': 'draft',
            'cardId': cid,
            'version': 1,
            'phase': 'draft',
            'category': cmd['category'],
            'title': cmd['title'],
            'rawText': text,
            'dispatchText': text,
            'target': cmd['target'],
            'source': cmd['source'],
        })
        return {'cardId': cid, 'version': 1, 'phase': 'draft'}

    def _revise(self, cmd):
        card = self.by_id.get(cmd['cardId'])
        if card is None:
            raise CardError('not found', '找不到')
        if card['version'] != cmd['baseVersion']:
            raise CardError('conflict', 'conflict')
        if card['phase'] not in ('draft', 'awaiting_confirmation'):
            raise CardError('bad phase', 'bad phase')
        version = card['version'] + 1
        rec = {
            'event': 'draft',
            'cardId': card['cardId'],
            'version': version,
            'baseVersion': card['version'],
            'phase': 'draft',
            'dispatchText': cmd['dispatchText'],
        }
        if card['phase'] == 'awaiting_confirmation' and card.get('operationId'):
            rec['voidOperationId'] = card['operationId']
        self._commit(rec)
        return {'cardId': card['cardId'], 'version': version, 'phase': 'draft'}

    def _prepare(self, cmd):
        card = self.by_id.get(cmd['cardId'])
        if card is None:
            raise CardError('not found', '找不到')
        if card['version'] != cmd['version']:
            raise CardError('conflict', 'conflict')
        op = self.ops.get(card.get('operationId') or '')
        if (card['phase'] == 'awaiting_confirmation' and op is not None
                and op['version'] == card['version'] and op['phase'] == 'awaiting_confirmation'):
            return {
                'cardId': card['cardId'],
                'operationId': op['operationId'],
                'version': card['version'],
                'phase': 'awaiting_confirmation',
                '_already': True,
            }
        if card['phase'] != 'draft':
            raise CardError('bad phase', 'bad phase')
        waiting = sum(1 for c in self.by_id.values() if c['phase'] == 'awaiting_confirmation')
        if waiting >= AWAITING_MAX:
            raise CardError('full', '太多待确认')
        oid = self._mint('OP')
        self._commit({
            'event': 'prepared',
            'cardId': card['cardId'],
            'operationId': oid,
            'version': card['version'],
            'phase': 'awaiting_confirmation',
        })
        return {
            'cardId': card['cardId'],
            'operationId': oid,
            'version': card['version'],
            'phase': 'awaiting_confirmation',
            '_enteredAwaiting': True,
        }

    def _receipt(self, cmd):
        if 'operationId' in cmd:
            op = self.ops.get(cmd['operationId'])
            if op is None:
                raise CardError('not found', '找不到')
            events = [self._public_event(e) for e in self.events
                      if e.get('operationId') == op['operationId'] and e.get('event') in DECISION_EVENTS]
            return {
                'cursor': self.seq,
                'cardId': op['cardId'],
                'operationId': op['operationId'],
                'version': op['version'],
                'phase': op['phase'],
                'events': events,
            }
        since = cmd.get('since', 0)
        events = [self._public_event(e) for e in self.events
                  if e.get('seq', 0) > since and e.get('event') in DECISION_EVENTS]
        return {'cursor': self.seq, 'events': events}

    def _report(self, cmd):
        op = self.ops.get(cmd['operationId'])
        if op is None:
            raise CardError('not found', '找不到')
        phase = cmd['phase']
        allowed = REPORT_NEXT.get(op['phase'])
        if not allowed or phase not in allowed:
            raise CardError('bad phase', 'bad phase')
        rec = {
            'event': 'report',
            'cardId': op['cardId'],
            'operationId': op['operationId'],
            'version': op['version'],
            'phase': phase,
        }
        if 'text' in cmd:
            rec['text'] = cmd['text']
        if 'ref' in cmd:
            rec['ref'] = cmd['ref']
        self._commit(rec)
        return {
            'cardId': op['cardId'],
            'operationId': op['operationId'],
            'version': op['version'],
            'phase': phase,
        }

    def _withdraw(self, cmd):
        card = self.by_id.get(cmd['cardId'])
        if card is None:
            raise CardError('not found', '找不到')
        if card['phase'] == 'unavailable':
            return {'cardId': card['cardId'], 'phase': 'unavailable', '_already': True}
        if card['phase'] not in ('draft', 'awaiting_confirmation', 'confirmed'):
            raise CardError('bad phase', 'bad phase')
        self._commit(self._unavailable_record(card, 'withdraw'))
        return {'cardId': card['cardId'], 'phase': 'unavailable'}

    def _user_confirm(self, card_id, expected_version):
        card = self.by_id.get(card_id)
        if card is None:
            raise CardError('not found', '找不到')
        if card['version'] != expected_version:
            raise CardError('conflict', 'conflict')
        oid = card.get('operationId')
        if oid and self._has_event(oid, 'confirmed'):
            return self._user_result(card, True, 'confirmed')
        if card['phase'] != 'awaiting_confirmation':
            raise CardError('bad phase', 'bad phase')
        op = self.ops.get(oid or '')
        if op is None or op['phase'] != 'awaiting_confirmation' or op['version'] != card['version']:
            raise CardError('bad phase', 'bad phase')
        self._commit({
            'event': 'confirmed',
            'by': BY_USER,
            'cardId': card['cardId'],
            'operationId': op['operationId'],
            'version': card['version'],
        })
        return self._user_result(card, False, 'confirmed')

    def _user_revise(self, card_id, expected_version):
        card = self.by_id.get(card_id)
        if card is None:
            raise CardError('not found', '找不到')
        if card['version'] != expected_version:
            raise CardError('conflict', 'conflict')
        if card['phase'] not in ('draft', 'awaiting_confirmation'):
            raise CardError('bad phase', 'bad phase')
        if self._has_revise(card['cardId'], card['version']):
            return self._user_result(card, True, 'revise_requested')
        rec = {
            'event': 'revise_requested',
            'by': BY_USER,
            'cardId': card['cardId'],
            'version': card['version'],
        }
        if card.get('operationId'):
            rec['operationId'] = card['operationId']
        self._commit(rec)
        return self._user_result(card, False, 'revise_requested')

    def _user_reject(self, card_id, expected_version):
        card = self.by_id.get(card_id)
        if card is None:
            raise CardError('not found', '找不到')
        if card['version'] != expected_version:
            raise CardError('conflict', 'conflict')
        if card['phase'] == 'rejected':
            return self._user_result(card, True, 'rejected')
        if card['phase'] not in ('draft', 'awaiting_confirmation'):
            raise CardError('bad phase', 'bad phase')
        rec = {
            'event': 'rejected',
            'by': BY_USER,
            'cardId': card['cardId'],
            'version': card['version'],
            'phase': 'rejected',
        }
        if card.get('operationId'):
            rec['operationId'] = card['operationId']
        self._commit(rec)
        return self._user_result(card, False, 'rejected')

    def _user_result(self, card, already, event):
        out = {
            'cardId': card['cardId'],
            'version': card['version'],
            'phase': card['phase'],
            'already': already,
            'event': event,
        }
        if card.get('operationId'):
            out['operationId'] = card['operationId']
        return out

    def _unavailable_record(self, card, reason):
        rec = {
            'event': 'unavailable',
            'reason': reason,
            'cardId': card['cardId'],
            'version': card['version'],
            'phase': 'unavailable',
        }
        if card.get('operationId'):
            rec['operationId'] = card['operationId']
        return rec

    def _has_event(self, operation_id, name):
        return any(e.get('operationId') == operation_id and e.get('event') == name for e in self.events)

    def _has_revise(self, card_id, version):
        return any(e.get('event') == 'revise_requested' and e.get('cardId') == card_id
                   and e.get('version') == version for e in self.events)

    def _commit(self, rec):
        rec = dict(rec)
        rec['seq'] = self.seq + 1
        rec['at'] = self.now_ms()
        self._writer(rec)
        self._apply(rec)
        return rec

    def _append_file(self, rec):
        if not self.conf or not self.path:
            raise OSError('no config dir')
        os.makedirs(self.conf, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n'
        data = line.encode('utf-8')
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.path, flags, 0o600)
        try:
            view = memoryview(data)
            while view:
                wrote = os.write(fd, view)
                if wrote <= 0:
                    raise OSError('short write')
                view = view[wrote:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _load(self):
        if not self.path or not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding='utf-8') as f:
                lines = f.readlines()
        except OSError:
            return
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or 'event' not in rec:
                continue
            try:
                self._apply(rec)
            except Exception:
                continue

    def _apply(self, rec):
        event = rec.get('event')
        seq = rec.get('seq', 0)
        if isinstance(seq, int) and not isinstance(seq, bool):
            self.seq = max(self.seq, seq)
        if event == 'draft':
            self._apply_draft(rec)
        elif event == 'prepared':
            self._apply_prepared(rec)
        elif event == 'confirmed':
            self._apply_confirmed(rec)
        elif event == 'revise_requested':
            pass
        elif event == 'rejected':
            self._apply_rejected(rec)
        elif event == 'report':
            self._apply_report(rec)
        elif event == 'unavailable':
            self._apply_unavailable(rec)
        else:
            raise CardError('bad args', 'bad args')
        self.events.append(rec)
        self._note_id(rec.get('cardId'))
        self._note_id(rec.get('operationId'))
        self._note_id(rec.get('voidOperationId'))

    def _apply_draft(self, rec):
        cid = rec['cardId']
        if cid not in self.by_id:
            self.by_id[cid] = {
                'cardId': cid,
                'version': rec['version'],
                'phase': 'draft',
                'category': rec['category'],
                'title': rec['title'],
                'rawText': rec['rawText'],
                'dispatchText': rec.get('dispatchText', rec['rawText']),
                'target': rec['target'],
                'source': rec['source'],
                'operationId': None,
                'resultText': '',
                'resultRef': '',
                'awaitingAt': None,
                'createdAt': rec.get('at'),
                'updatedAt': rec.get('at'),
            }
            return
        card = self.by_id[cid]
        void = rec.get('voidOperationId')
        if void and void in self.ops:
            self.ops[void]['phase'] = 'unavailable'
        card['version'] = rec['version']
        card['dispatchText'] = rec['dispatchText']
        card['phase'] = 'draft'
        card['operationId'] = None
        card['awaitingAt'] = None
        card['updatedAt'] = rec.get('at')

    def _apply_prepared(self, rec):
        card = self.by_id[rec['cardId']]
        self.ops[rec['operationId']] = {
            'operationId': rec['operationId'],
            'cardId': rec['cardId'],
            'version': rec['version'],
            'phase': 'awaiting_confirmation',
        }
        card['operationId'] = rec['operationId']
        card['phase'] = 'awaiting_confirmation'
        card['awaitingAt'] = rec.get('at')
        card['updatedAt'] = rec.get('at')

    def _apply_confirmed(self, rec):
        op = self.ops[rec['operationId']]
        op['phase'] = 'confirmed'
        card = self.by_id.get(rec['cardId'])
        if card and card.get('operationId') == rec['operationId'] and card['version'] == rec['version']:
            card['phase'] = 'confirmed'
            card['updatedAt'] = rec.get('at')

    def _apply_rejected(self, rec):
        oid = rec.get('operationId')
        if oid and oid in self.ops:
            self.ops[oid]['phase'] = 'rejected'
        card = self.by_id.get(rec['cardId'])
        if card and card['version'] == rec['version']:
            card['phase'] = 'rejected'
            card['updatedAt'] = rec.get('at')

    def _apply_report(self, rec):
        op = self.ops[rec['operationId']]
        op['phase'] = rec['phase']
        card = self.by_id.get(rec['cardId'])
        if card and card.get('operationId') == rec['operationId']:
            card['phase'] = rec['phase']
            card['updatedAt'] = rec.get('at')
            if 'text' in rec:
                card['resultText'] = rec['text']
            if 'ref' in rec:
                card['resultRef'] = rec['ref']

    def _apply_unavailable(self, rec):
        oid = rec.get('operationId')
        if oid and oid in self.ops:
            self.ops[oid]['phase'] = 'unavailable'
        card = self.by_id.get(rec['cardId'])
        if card and card['version'] == rec.get('version', card['version']):
            card['phase'] = 'unavailable'
            card['updatedAt'] = rec.get('at')

    def _public_event(self, event):
        out = {
            'seq': event.get('seq'),
            'cardId': event.get('cardId'),
            'version': event.get('version'),
            'event': event.get('event'),
            'at': event.get('at'),
        }
        if event.get('operationId'):
            out['operationId'] = event['operationId']
        if event.get('by'):
            out['by'] = event['by']
        return out

    def _day(self):
        ms = self.now_ms()
        return datetime.datetime.fromtimestamp(ms / 1000.0).strftime('%Y%m%d')

    def _mint(self, kind):
        day = self._day()
        n = self._counts.get((kind, day), 0) + 1
        if kind == 'C':
            return 'C-%s-%03d' % (day, n)
        return 'OP-%s-%04d' % (day, n)

    def _note_id(self, ident):
        if not isinstance(ident, str):
            return
        if ident.startswith('OP-'):
            kind, rest = 'OP', ident[3:]
        elif ident.startswith('C-'):
            kind, rest = 'C', ident[2:]
        else:
            return
        day, _, num = rest.partition('-')
        if not day.isdigit() or not num.isdigit():
            return
        key = (kind, day)
        self._counts[key] = max(self._counts.get(key, 0), int(num))
