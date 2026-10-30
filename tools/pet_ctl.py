#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""让本机的千问娘说一句、换表情、探头。只连 127.0.0.1。

口令从桌宠配置目录的 control_token 自动读取，不要把口令写进命令行或聊天。
默认端口 6710，和桌宠设置里的 control_port 一致。桌宠菜单里的开关默认关；
关着的时候这里连不上，退出码 1，输出 {"ok":false,"error":"控制未开启"}。

例子：
  python3 tools/pet_ctl.py status
  python3 tools/pet_ctl.py say --json-base64 BASE64
  python3 tools/pet_ctl.py feedback --json-base64 BASE64
  python3 tools/pet_ctl.py wait --json-base64 BASE64
  python3 tools/pet_ctl.py card draft --json-base64 BASE64

BASE64 是 UTF-8 JSON 的标准 base64（要有 padding）。say 的 JSON 例如：
  {"text":"今天也辛苦啦。","expr":"smile","priority":"normal"}
feedback 只读气泡按钮：{"since":0}
wait 最多等 25 秒，有新点击立刻返回，超时也返回当前游标：{"since":0,"timeoutMs":25000}
任务卡子命令只有 draft / prepare / receipt / report / withdraw。没有 confirm。
多一个不认识的字段，桌宠会拒绝。
"""
import os, sys, json, socket

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pet_control as C
import pet_platform as P


USAGE = """用法：
  python3 tools/pet_ctl.py status
  python3 tools/pet_ctl.py say --json-base64 BASE64
  python3 tools/pet_ctl.py line --json-base64 BASE64
  python3 tools/pet_ctl.py expr --json-base64 BASE64
  python3 tools/pet_ctl.py peek --json-base64 BASE64
  python3 tools/pet_ctl.py quiet --json-base64 BASE64
  python3 tools/pet_ctl.py hide
  python3 tools/pet_ctl.py show
  python3 tools/pet_ctl.py feedback --json-base64 BASE64
  python3 tools/pet_ctl.py wait --json-base64 BASE64
  python3 tools/pet_ctl.py card draft --json-base64 BASE64
  python3 tools/pet_ctl.py card prepare --json-base64 BASE64
  python3 tools/pet_ctl.py card receipt --json-base64 BASE64
  python3 tools/pet_ctl.py card report --json-base64 BASE64
  python3 tools/pet_ctl.py card withdraw --json-base64 BASE64

只连接 127.0.0.1。口令自动从配置目录的 control_token 读取。
feedback / wait 的 JSON 只有 since（以及 wait 的 timeoutMs，0–25000）。
返回 result.cursor 和 result.clicks（id、option、index、at）。
since 用上次的 cursor，旧点击不会再出现。wait 超时也算成功，退出码 0。
任务卡没有 confirm 子命令。确认只能在桌宠的卡片上点。
多一个不认识的字段会被拒绝。
"""


def emit(obj, code):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
    return code


def _port_open(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect(('127.0.0.1', int(port)))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _rpc_timeout(action, payload):
    """wait 要盖住 timeoutMs，再留几秒给来回。别的动作几秒够了。"""
    if action != 'wait' or not isinstance(payload, dict):
        return 5.0
    raw = payload.get('timeoutMs', 0)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raw = 0
    raw = max(0, min(C.WAIT_MAX_MS, raw))
    return raw / 1000.0 + 3.0


def _parse_card(rest):
    """card <子命令> --json-base64。子命令里没有 confirm。"""
    if len(rest) < 1 or rest[0] not in C.CARD_SUBS or rest[0] == 'confirm':
        return None, None
    sub, tail = rest[0], rest[1:]
    if len(tail) != 2 or tail[0] != '--json-base64':
        return None, None
    payload = C.decode_json_base64(tail[1])
    if payload is None:
        return None, None
    return sub, payload


def _call_action(action, payload):
    conf = P.config_dir()
    port = C.read_port(conf)
    if not _port_open(port):
        return emit({'ok': False, 'error': '控制未开启', 'action': action}, 1)
    token = C.read_token(conf)
    if not token:
        return emit({'ok': False, 'error': '找不到口令', 'action': action}, 1)
    result = C.call(port, token, action, payload, timeout=_rpc_timeout(action, payload))
    return emit(result, 0 if result.get('ok') else 1)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        sys.stdout.write(USAGE)
        return 0 if argv else 2
    action = argv[0]
    rest = argv[1:]
    if action == 'confirm' or (action == 'card' and rest[:1] == ['confirm']):
        return emit({'ok': False, 'error': 'bad args'}, 1)
    if action == 'card':
        sub, payload = _parse_card(rest)
        if sub is None:
            return emit({'ok': False, 'error': 'bad args'}, 1)
        return _call_action('card/' + sub, payload)
    if action not in C.ACTIONS:
        return emit({'ok': False, 'error': 'bad args'}, 1)
    payload = {}
    if rest:
        if len(rest) != 2 or rest[0] != '--json-base64':
            return emit({'ok': False, 'error': 'bad args'}, 1)
        payload = C.decode_json_base64(rest[1])
        if payload is None:
            return emit({'ok': False, 'error': 'bad args'}, 1)
    return _call_action(action, payload)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(1)
