# -*- coding: utf-8 -*-
"""v0.4 的「联网人格 + TTS」薄层（可选；出问题自动退回内置台词/静音）。

设计边界（照抄 pet_brain.py 里给 v0.4 留的契约）：
    brain.line(category, ctx, strict=False) -> Line | None   同步、立刻返回，不能卡界面
    speaker.speak(line, volume)                              有新台词才合成，音频缓存

它只依赖标准库：
    * 台词：GET http://127.0.0.1:6790/line?category=…（DSH 侧生成，0.35 秒超时）
    * 发声：千问 TTS 脚本（需自备，ZHANGGUI_QWEN_PY / ZHANGGUI_QWEN_TTS 指定）或 macOS `say`；
      播放：macOS `afplay`，Windows `winsound`（只放 wav），其他系统 paplay/aplay（后台线程，不阻塞界面）
任何一步失败都退回 LocalBrain 的内置台词、或干脆不出声。

开关：环境变量 ZHANGGUI_PET_ONLINE=1（默认关）。没开、或 6790 上没有人格服务时，
桌宠照常用内置台词跑（四个新动作是纯本地素材，不依赖这里）。
本文件不写死任何个人路径、不读任何 key：TTS 脚本自己管凭据。
"""
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

from pet_brain import LocalBrain
from pet_lines import Line

ASPECTS = ('smile', 'smug', 'thinking', 'biz', 'pout', 'stretch', 'yawn', 'nod', 'nap')
DEFAULT_URL = os.environ.get('ZHANGGUI_PERSONA_URL', 'http://127.0.0.1:6790')
DEFAULT_VOICE = os.environ.get('ZHANGGUI_TTS_VOICE', 'Sandy (中文（中国大陆）)')
# 千问 TTS（longxing_v3.1，与成片同一套固定参数）
# 默认找 ~/Projects/dsh-coord/persona 下的脚本（DSH 的本机布局）；找不到就不合成，只出气泡。
_PERSONA = os.path.join(os.path.expanduser('~'), 'Projects', 'dsh-coord', 'persona')
_VENV_PY = os.path.join(_PERSONA, '.venv', 'Scripts' if os.name == 'nt' else 'bin', 'python.exe' if os.name == 'nt' else 'python')
QWEN_PY = os.environ.get('ZHANGGUI_QWEN_PY', _VENV_PY)
QWEN_SCRIPT = os.environ.get('ZHANGGUI_QWEN_TTS', os.path.join(_PERSONA, 'tts_qwen.py'))
TTS_PROVIDER = os.environ.get('ZHANGGUI_TTS', 'qwen')     # qwen | say（say 只有 macOS 有）
IS_MAC = sys.platform == 'darwin'
IS_WIN = os.name == 'nt'


class OnlineBrain(LocalBrain):
    """台词优先问 DSH；连不上/超时/返回空就退回父类的内置台词。"""

    name = 'dsh'

    def __init__(self, order=None, url=DEFAULT_URL, timeout=0.35, log=print):
        super().__init__(order)
        self.url = url.rstrip('/')
        self.timeout = timeout
        self.log = log
        # 说话频率沿用桌宠原来的节奏：只有 LocalBrain 本来要说话时才说，只是把词换掉。
        # min_gap 是防连击的保险（同一分钟内最多一句）。
        self.min_gap = float(os.environ.get('ZHANGGUI_TALK_MIN_GAP', '20'))
        self._last = 0.0

    def line(self, category, ctx=None, strict=False):
        # 先让原来的台词库判断「现在该不该说话」——冷却/权重/安静时段全在它手里。
        # 它说该说，我们才去生成新词；它说不该说，就保持安静（这才是原来的频率）。
        base = super().line(category, ctx, strict=strict)
        if base is None:
            return None
        now = time.time()
        if now - self._last < self.min_gap:
            return base                      # 刚说过，这回用原来的词，不再多发一句
        fetched = self._fetch(category, ctx)
        if fetched:
            expr, text = fetched
            self._last = now
            lid = 'online_' + hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]
            return Line(lid, text, expr, 1.0, 0)
        return base

    def _fetch(self, category, ctx=None):
        try:
            query = urllib.parse.urlencode({'category': category, 'ctx': ctx or ''})
            with urllib.request.urlopen(self.url + '/line?' + query, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if data.get('source') != 'dsh':           # 服务给的兜底句交给父类，保留它的冷却/去重
                return None
            text = (data.get('text') or '').strip()
            if not text:
                return None
            expr = data.get('expr') if data.get('expr') in ASPECTS else 'smile'
            return expr, text
        except Exception as error:                        # 网络/服务没开都走这里
            self.log('online', 'line fallback', str(error)[:60])
            return None


class TTSSpeaker:
    """包住原来的 Voice：有预录音频先放预录音频，没有就用 say 合成这句新台词。"""

    def __init__(self, voice, voice_id=DEFAULT_VOICE, rate=190, cache_dir=None, log=print):
        self.voice = voice
        self.voice_id = voice_id
        self.rate = rate
        self.log = log
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), 'zhanggui-pet-tts')
        os.makedirs(self.cache_dir, exist_ok=True)
        # 她主动说的话默认不出声（只出气泡），避免一直有人在耳边念；
        # 被戳/摸头/打字聊天这种你主动找她的，一定出声。
        self.speak_proactive = os.environ.get('ZHANGGUI_TTS_PROACTIVE', '0') == '1'
        self._proc = None
        self._lock = threading.Lock()
        # 快速静音开关：ZHANGGUI_PET_TTS=0 只出气泡不出声（换声线时用）
        self.enabled = os.environ.get('ZHANGGUI_PET_TTS', '1') != '0'

    # ---- 与 Voice 的接口保持一致 ----
    def __getattr__(self, name):
        # Voice 还有 scan()/voices()/set_voice() 等菜单用的方法：原样委托，
        # 不在这里重写，免得漏一个就崩（2026-10-29 就因为少 scan 崩过一次）。
        return getattr(self.voice, name)

    def scan(self):
        try:
            return self.voice.scan()
        except Exception:
            return None

    def can_synth(self):
        if TTS_PROVIDER == 'qwen':
            return os.path.isfile(QWEN_PY) and os.path.isfile(QWEN_SCRIPT)
        return IS_MAC and os.path.exists('/usr/bin/say')

    def available(self):
        try:
            if self.voice is not None and self.voice.available():
                return True
        except Exception:
            pass
        return self.can_synth()

    def stop(self):
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()

    def play(self, line_id, volume=1.0):
        """老接口：只有 id 时走预录音频。"""
        try:
            return self.voice.play(line_id, volume)
        except Exception:
            return None

    # ---- 新台词：合成 + 播放 ----
    def speak(self, line, volume=1.0, proactive=False):
        if not self.enabled:
            return None
        lid = getattr(line, 'id', 'online')
        if proactive and not self.speak_proactive:
            # 主动台词：只放本地预录（零调用、即时），没有预录就闭嘴。
            # 不现场合成 —— 否则又变成"一直有人在耳边念"。
            try:
                voice = self.voice
                if (voice is not None and getattr(voice, 'available', lambda: False)()
                        and getattr(voice, 'has', lambda _id: False)(lid)):
                    ok = voice.play(lid, volume)
                    if ok:
                        self.log('tts', 'local', lid)
                    return ok or None
            except Exception as error:
                self.log('tts', 'local failed', str(error)[:60])
            return None
        text = getattr(line, 'text', '').strip()
        if not text:
            return None
        lid = getattr(line, 'id', 'online')
        # 预录优先（内置台词本来就有配音的话不重复合成）
        try:
            path = self.voice.play(lid, volume) if getattr(self.voice, 'available', lambda: False)() else None
            if path:
                return path
        except Exception:
            pass
        if not self.can_synth():
            return None                       # 这台机器没有可用的合成：只出气泡
        threading.Thread(target=self._synth_and_play, args=(text, volume), daemon=True).start()
        return None

    def _cache_path(self, text, ext='wav'):
        key = hashlib.sha1((self.voice_id + '|' + text).encode('utf-8')).hexdigest()[:16]
        return os.path.join(self.cache_dir, key + '.' + ext)

    def _synth_and_play(self, text, volume):
        try:
            if TTS_PROVIDER == 'qwen':
                path = self._cache_path(text, 'wav')
                if not os.path.exists(path):
                    subprocess.run([QWEN_PY, QWEN_SCRIPT, '--text', text, '--out', path],
                                   check=True, timeout=30,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                path = self._cache_path(text, 'aiff')
                if not os.path.exists(path):
                    subprocess.run(['/usr/bin/say', '-v', self.voice_id, '-r', str(self.rate), '-o', path, text],
                                   check=True, timeout=20,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._play_file(path, volume)
            self.log('tts', 'spoken', text[:20])
        except Exception as error:
            self.log('tts', 'failed', str(error)[:80])

    def _play_file(self, path, volume):
        vol = max(0.0, min(1.0, float(volume or 1.0)))
        if IS_WIN:
            import winsound                    # 只放 wav；音量跟系统
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        if IS_MAC:
            cmd = ['/usr/bin/afplay', '-v', f'{vol:.2f}', path]
        else:
            exe = shutil.which('paplay') or shutil.which('aplay')
            if not exe:
                raise RuntimeError('no audio player')
            cmd = [exe, path]
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install(pet, order=None):
    """给桌宠实例挂上联网人格与 TTS；任何异常都不影响启动。"""
    try:
        brain = OnlineBrain(order, log=pet.log)
        speaker = TTSSpeaker(getattr(pet, 'voice', None), log=pet.log)
        pet.brain = brain
        pet.voice = speaker
        pet.log('online', 'brain+tts enabled', DEFAULT_URL)
        # 浮窗/全局热键已移除（见文件末尾说明），只保留菜单里的模态输入框。
        try:
            start_ui_pump(pet)
        except Exception as error:
            pet.log('chat', 'ui pump failed', str(error)[:80])
        if os.environ.get('ZHANGGUI_CHAT_SELFTEST') == '1':
            from PySide6.QtCore import QTimer
            QTimer.singleShot(4000, lambda: say_to_pet(pet, '自检：回一句给我听'))
        return True
    except Exception as error:
        pet.log('online', 'install failed', str(error)[:100])
        return False





# ---- 打字对话（模态输入框 + 主线程 UI 队列） --------------------------------
# 2026-10-29：QTimer.singleShot 从后台线程调是不可靠的（对话框按了没反应就是它）。
# 改成：后台线程只往队列塞回调，主线程的 QTimer 定时取走执行。
UI_QUEUE = queue.Queue()


def _drain_ui(pet):
    try:
        while True:
            fn = UI_QUEUE.get_nowait()
            try:
                fn()
            except Exception as error:
                pet.log('chat', 'ui error', str(error)[:80])
    except queue.Empty:
        return


def start_ui_pump(pet):
    from PySide6.QtCore import QTimer
    timer = QTimer(pet)
    timer.timeout.connect(lambda: _drain_ui(pet))
    timer.start(80)
    pet._chat_ui_timer = timer          # 挂住，别被回收
    pet.log('chat', 'ui pump started')


def fetch_chat(text, url=DEFAULT_URL, timeout=60):
    payload = json.dumps({'text': text}).encode('utf-8')
    req = urllib.request.Request(url + '/chat', data=payload,
                                 headers={'content-type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    reply = (data.get('text') or '').strip()
    expr = data.get('expr') if data.get('expr') in ASPECTS else 'smile'
    return reply, expr


def say_to_pet(pet, text):
    """用户说一句 → 气泡先给反馈 → 后台问 DSH → 主线程更新气泡 + 出声。"""
    text = str(text).strip()
    if not text:
        return
    pet.log('chat', 'send', text[:30])

    def thinking():
        try:
            pet.show_bubble('嗯……')
            pet.play_expr('nod')          # 2026-10-30：用点头当"我在听"，比静止的思考更像在听
        except Exception:
            pass

    UI_QUEUE.put(thinking)

    def work():
        try:
            reply, expr = fetch_chat(text)
        except Exception as error:
            pet.log('chat', 'failed', str(error)[:60])
            UI_QUEUE.put(lambda: pet.show_bubble('（没连上她的大脑，等一下再说？）'))
            return
        if not reply:
            return

        def show():
            try:
                pet.show_bubble(reply)
                pet.play_expr(expr)
            except Exception as error:
                pet.log('chat', 'show failed', str(error)[:60])
                return
            try:
                if hasattr(pet.voice, 'speak') and not pet.st.get('muted'):
                    pet.voice.speak(Line('chat', reply, expr, 1.0, 0), pet.st.get('volume', 1.0))
            except Exception as error:
                pet.log('chat', 'speak failed', str(error)[:60])
            pet.log('chat', 'reply', reply[:30])

        UI_QUEUE.put(show)

    threading.Thread(target=work, daemon=True).start()


def open_chat(pet):
    """菜单「和她说话…」→ 普通模态输入框（不常驻、不抢热键、不抢输入法）。"""
    try:
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(pet, '和她说一句', '你说：')
    except Exception as error:
        pet.log('chat', 'dialog failed', str(error)[:60])
        return
    if ok and str(text).strip():
        say_to_pet(pet, text)
