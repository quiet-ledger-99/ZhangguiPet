# -*- coding: utf-8 -*-
"""本机表演通道（L1，实验，默认关）。

只监听 127.0.0.1。每个请求要带配置目录里 control_token 的口令（请求头 X-Pet-Token）。
带浏览器 Origin 的请求拒绝；Host 必须是 127.0.0.1:端口。
动作是一份严格 JSON：多一个不认识的字段就拒绝。这里不执行任意命令，也不写日志正文。
任务卡是 card/draft|prepare|receipt|report|withdraw。没有 confirm 这个动作。

网络线程只做校验，真正碰界面的动作交给 dispatch（桌宠在主线程里做）。
"""
import json, os, hmac, time, base64, socket, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pet_lines as PL
import pet_cards

DEFAULT_PORT = 6710
TOKEN_HEADER = 'X-Pet-Token'
TOKEN_NAME = 'control_token'
MAX_BODY = 8192
# 任务卡正文最长 2000 字。卡片请求单独放宽，别的动作仍是 MAX_BODY。
CARD_MAX_BODY = 65536
RATE_PER_SEC = 2
TEXT_MAX = 200
OPTION_MAX = 10
OPTIONS_MAX = 3
SOURCE_MAX = 24
CARD_SUBS = pet_cards.CARD_SUBS

ACTIONS = frozenset({
    'status', 'say', 'line', 'expr', 'peek', 'quiet', 'hide', 'show', 'feedback', 'wait',
})
EXPRS = frozenset({'smile', 'smug', 'thinking', 'biz', 'pout'})
PEEK_SIDES = frozenset({'left', 'right', 'nearest', 'off'})
PRIORITIES = frozenset({'normal', 'important'})
WAIT_MAX_MS = 25000
_FIELDS = {
    'status': frozenset(),
    'say': frozenset({'text', 'expr', 'options', 'voice', 'priority', 'source'}),
    'line': frozenset({'id'}),
    'expr': frozenset({'expr'}),
    'peek': frozenset({'side'}),
    'quiet': frozenset({'minutes'}),
    'hide': frozenset(),
    'show': frozenset(),
    'feedback': frozenset({'since'}),
    'wait': frozenset({'since', 'timeoutMs'}),
}
_REQUIRED = {
    'say': frozenset({'text'}),
    'line': frozenset({'id'}),
    'expr': frozenset({'expr'}),
    'peek': frozenset({'side'}),
    'quiet': frozenset({'minutes'}),
    'feedback': frozenset({'since'}),
    'wait': frozenset({'since', 'timeoutMs'}),
}


def token_path(conf):
    return os.path.join(conf, TOKEN_NAME)


def write_token(conf, force=False):
    """读已有口令，或生成一个新的。文件权限收成 600。失败抛 OSError。"""
    if not conf:
        raise OSError('no config dir')
    os.makedirs(conf, exist_ok=True)
    path = token_path(conf)
    if not force:
        existing = _read_token_file(path)
        if existing:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            return existing
    import secrets
    token = secrets.token_urlsafe(32)
    tmp = path + '.tmp'
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    fd = os.open(tmp, flags, 0o600)
    try:
        os.write(fd, (token + '\n').encode('ascii'))
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    return token


def read_token(conf):
    if not conf:
        return ''
    return _read_token_file(token_path(conf))


def _read_token_file(path):
    try:
        with open(path, encoding='ascii') as f:
            token = f.read().strip()
    except (OSError, UnicodeError):
        return ''
    if not token or any(c.isspace() for c in token):
        return ''
    return token


def read_port(conf, default=DEFAULT_PORT):
    """从 settings.json 读 control_port。读不到或不是合法端口就用默认 6710。"""
    if not conf:
        return default
    try:
        with open(os.path.join(conf, 'settings.json'), encoding='utf-8') as f:
            raw = json.load(f)
        port = raw.get('control_port', default)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return default
    if isinstance(port, bool) or not isinstance(port, int):
        return default
    if 1024 <= port <= 65535:
        return port
    return default


def token_eq(got, expect):
    if not isinstance(got, str) or not isinstance(expect, str) or not got or not expect:
        return False
    a, b = got.encode('utf-8'), expect.encode('utf-8')
    if len(a) != len(b):
        return False
    return hmac.compare_digest(a, b)


def line_by_id(line_id):
    if not isinstance(line_id, str):
        return None
    for _, line in PL.all_lines():
        if line.id == line_id:
            return line
    return None


def _plain(text, lo, hi):
    """可显示的短字符串：长度在范围内，不含控制字符。"""
    if not isinstance(text, str) or not (lo <= len(text) <= hi):
        return False
    return all(ord(c) >= 0x20 for c in text)


def _int_in(value, lo, hi):
    """真整数，拒绝 bool。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return lo <= value <= hi


def validate(action, payload):
    """白名单校验。通过返回 (cmd, None)，否则 (None, 'bad args')。
    cmd 只含认识的字段，调用方不要再碰原始 payload。
    任务卡走 card/<子命令>。没有 confirm：确认只能在桌宠卡片上点。"""
    if isinstance(action, str) and action.startswith('card/'):
        return pet_cards.validate_card(action[5:], payload)
    if action not in ACTIONS or not isinstance(payload, dict):
        return None, 'bad args'
    if set(payload) - _FIELDS[action]:
        return None, 'bad args'
    missing = _REQUIRED.get(action, frozenset()) - set(payload)
    if missing:
        return None, 'bad args'
    cmd = {'action': action}
    if action == 'say':
        text = payload.get('text')
        if not isinstance(text, str) or not (1 <= len(text) <= TEXT_MAX) or '\x00' in text:
            return None, 'bad args'
        cmd['text'] = text
        if 'expr' in payload:
            if payload['expr'] not in EXPRS:
                return None, 'bad args'
            cmd['expr'] = payload['expr']
        if 'options' in payload:
            opts = payload['options']
            if not isinstance(opts, list) or not (1 <= len(opts) <= OPTIONS_MAX):
                return None, 'bad args'
            if not all(_plain(x, 1, OPTION_MAX) for x in opts):
                return None, 'bad args'
            cmd['options'] = list(opts)
        if 'voice' in payload:
            if not isinstance(payload['voice'], bool):
                return None, 'bad args'
            cmd['voice'] = payload['voice']
        else:
            cmd['voice'] = False
        if 'priority' in payload:
            if payload['priority'] not in PRIORITIES:
                return None, 'bad args'
            cmd['priority'] = payload['priority']
        else:
            cmd['priority'] = 'normal'
        if 'source' in payload:
            if not _plain(payload['source'], 1, SOURCE_MAX):
                return None, 'bad args'
            cmd['source'] = payload['source']
        return cmd, None
    if action == 'line':
        line = line_by_id(payload.get('id'))
        if line is None:
            return None, 'bad args'
        cmd['id'] = line.id
        cmd['priority'] = 'normal'
        cmd['voice'] = True
        return cmd, None
    if action == 'expr':
        if payload.get('expr') not in EXPRS:
            return None, 'bad args'
        cmd['expr'] = payload['expr']
        return cmd, None
    if action == 'peek':
        if payload.get('side') not in PEEK_SIDES:
            return None, 'bad args'
        cmd['side'] = payload['side']
        return cmd, None
    if action == 'quiet':
        minutes = payload.get('minutes')
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not (1 <= minutes <= 1440):
            return None, 'bad args'
        cmd['minutes'] = minutes
        return cmd, None
    if action == 'feedback':
        if not _int_in(payload.get('since'), 0, 2 ** 31 - 1):
            return None, 'bad args'
        cmd['since'] = payload['since']
        return cmd, None
    if action == 'wait':
        if not _int_in(payload.get('since'), 0, 2 ** 31 - 1):
            return None, 'bad args'
        if not _int_in(payload.get('timeoutMs'), 0, WAIT_MAX_MS):
            return None, 'bad args'
        cmd['since'] = payload['since']
        cmd['timeoutMs'] = payload['timeoutMs']
        return cmd, None
    return cmd, None


def _safe_action(action):
    if action in ACTIONS:
        return action
    if isinstance(action, str) and action.startswith('card/'):
        sub = action[5:]
        if sub in CARD_SUBS and '/' not in sub:
            return 'card ' + sub
    return 'request'


class _HTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    address_family = socket.AF_INET

    def server_bind(self):
        super().server_bind()
        host = self.socket.getsockname()[0]
        if host != '127.0.0.1':
            raise OSError('refusing non-loopback bind')


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        self._handle(allow_body=False)

    def do_POST(self):
        self._handle(allow_body=True)

    def do_PUT(self):
        self._handle(allow_body=False)

    def do_DELETE(self):
        self._handle(allow_body=False)

    def _handle(self, allow_body):
        ch = self.server.channel
        guarded = self._guard(ch)
        if guarded is not None:
            code, obj = guarded
            self._send(code, obj)
            return
        action = self._action_name()
        if self.command != 'POST' or not allow_body:
            ch.log('control %s rejected(bad args)' % _safe_action(action))
            self._send(400, {'ok': False, 'error': 'bad args', 'action': action})
            return
        payload, why = self._read_json()
        if why is not None:
            ch.log('control %s rejected(bad args)' % _safe_action(action))
            self._send(400, {'ok': False, 'error': 'bad args', 'action': action})
            return
        got = self.headers.get(TOKEN_HEADER, '')
        with ch.lock:
            expect = ch.token
        if not token_eq(got.strip(), expect):
            ch.log('control %s rejected(bad token)' % _safe_action(action))
            self._send(401, {'ok': False, 'error': '口令不对', 'action': action})
            return
        if not ch.allow():
            ch.log('control %s rejected(rate)' % _safe_action(action))
            self._send(429, {'ok': False, 'error': '太频繁', 'action': action})
            return
        if not ch.accepting:
            self._send(503, {'ok': False, 'error': '控制未开启', 'action': action})
            return
        cmd, err = validate(action, payload)
        if err:
            ch.log('control %s rejected(bad args)' % _safe_action(action))
            self._send(400, {'ok': False, 'error': 'bad args', 'action': action})
            return
        try:
            result = ch.dispatch(cmd)
        except Exception:
            ch.log('control %s rejected(error)' % _safe_action(action))
            result = {'ok': False, 'error': 'bad args', 'action': action}
        if not isinstance(result, dict) or 'ok' not in result:
            result = {'ok': False, 'error': 'bad args', 'action': action}
        self._send(_status_code(result), result)

    def _guard(self, ch):
        if not ch.accepting:
            return 503, {'ok': False, 'error': '控制未开启'}
        peer = self.client_address[0] if self.client_address else ''
        host = (self.headers.get('Host') or '').strip()
        expect = '127.0.0.1:%s' % ch.bound_port
        if peer != '127.0.0.1' or host != expect:
            ch.log('control request rejected(host)')
            return 403, {'ok': False, 'error': '地址不对'}
        if self.headers.get('Origin') is not None:
            ch.log('control request rejected(origin)')
            return 403, {'ok': False, 'error': '来源不对'}
        return None

    def _body_limit(self):
        raw = self.path or ''
        if raw.startswith('/card/'):
            return CARD_MAX_BODY
        return MAX_BODY

    def _action_name(self):
        raw = self.path or ''
        if '?' in raw or '#' in raw or '%' in raw or not raw.startswith('/'):
            return None
        name = raw[1:]
        if not name or name == 'confirm':
            return None
        if name in ACTIONS:
            return name
        if name.startswith('card/'):
            sub = name[5:]
            if sub in CARD_SUBS and sub != 'confirm' and '/' not in sub:
                return name
        return None

    def _read_json(self):
        raw_len = self.headers.get('Content-Length', '0').strip()
        if not raw_len.isdigit():
            return None, 'bad args'
        n = int(raw_len)
        if n > self._body_limit():
            return None, 'bad args'
        if n == 0:
            return {}, None
        ctype = (self.headers.get('Content-Type') or '').lower()
        if not ctype.startswith('application/json'):
            return None, 'bad args'
        try:
            data = self.rfile.read(n)
            obj = json.loads(data.decode('utf-8'))
        except Exception:
            return None, 'bad args'
        if not isinstance(obj, dict):
            return None, 'bad args'
        return obj, None

    def _send(self, code, obj):
        try:
            body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
        except (OSError, BrokenPipeError):
            pass
        self.close_connection = True


def _status_code(result):
    if result.get('ok'):
        return 200
    err = result.get('error')
    if err == '口令不对':
        return 401
    if err in ('来源不对', '地址不对'):
        return 403
    if err == '太频繁':
        return 429
    if err == '控制未开启':
        return 503
    if err == 'conflict':
        return 409
    return 400


class ControlServer:
    """只绑 127.0.0.1 的小服务。stop() 会真的关掉监听。"""

    def __init__(self, port, token, dispatch, log):
        self.port = int(port)
        self.bound_port = self.port
        self.token = token
        self.dispatch = dispatch
        self.log = log or (lambda *_: None)
        self.accepting = False
        self.hits = []
        self.lock = threading.Lock()
        self.httpd = None
        self.thread = None

    def start(self):
        httpd = _HTTPServer(('127.0.0.1', self.port), _Handler)
        host, bound = httpd.socket.getsockname()[:2]
        if host != '127.0.0.1':
            httpd.server_close()
            raise OSError('refusing non-loopback bind')
        httpd.channel = self
        self.httpd = httpd
        self.bound_port = bound
        self.accepting = True
        self.thread = threading.Thread(
            target=httpd.serve_forever, kwargs={'poll_interval': 0.2},
            name='pet-control', daemon=True)
        self.thread.start()
        return self

    def set_token(self, token):
        with self.lock:
            self.token = token

    def allow(self):
        now = time.monotonic()
        with self.lock:
            self.hits = [t for t in self.hits if now - t < 1.0]
            if len(self.hits) >= RATE_PER_SEC:
                return False
            self.hits.append(now)
            return True

    def stop(self, pump=None):
        """关掉监听。pump 在等待期间被调用，用来让主线程把已经进来的请求处理完。"""
        self.accepting = False
        httpd, thread = self.httpd, self.thread
        if httpd is not None:
            def _shutdown():
                try:
                    httpd.shutdown()
                except Exception:
                    pass
            threading.Thread(target=_shutdown, daemon=True).start()
        deadline = time.time() + 2.5
        while thread is not None and thread.is_alive() and time.time() < deadline:
            if pump is not None:
                try:
                    pump()
                except Exception:
                    pass
            time.sleep(0.01)
        if httpd is not None:
            try:
                httpd.server_close()
            except Exception:
                pass
        self.httpd = None
        self.thread = None


def call(port, token, action, payload=None, timeout=5.0):
    """给 pet_ctl 和测试用的客户端。只连 127.0.0.1，不跟随重定向。连不上时返回「控制未开启」。"""
    import http.client
    body = json.dumps(payload or {}, ensure_ascii=False).encode('utf-8')
    conn = http.client.HTTPConnection('127.0.0.1', int(port), timeout=timeout)
    try:
        conn.request('POST', '/' + action, body=body, headers={
            'Host': '127.0.0.1:%s' % int(port),
            'Content-Type': 'application/json; charset=utf-8',
            'X-Pet-Token': token or '',
            'Connection': 'close',
        })
        resp = conn.getresponse()
        raw = resp.read()
    except (OSError, http.client.HTTPException, TimeoutError):
        return {'ok': False, 'error': '控制未开启'}
    finally:
        try:
            conn.close()
        except Exception:
            pass
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError, TypeError):
        return {'ok': False, 'error': '控制未开启'}
    if not isinstance(data, dict) or 'ok' not in data:
        return {'ok': False, 'error': '控制未开启'}
    return data


def decode_json_base64(text):
    try:
        raw = base64.b64decode(text, validate=True)
        obj = json.loads(raw.decode('utf-8'))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    return obj
