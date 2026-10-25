# -*- coding: utf-8 -*-
"""和操作系统打交道的部分：配置目录、设置、日志、空闲时间、全屏检测、开机自启、播放语音。
全部离线；Windows 用 ctypes 调系统 API；macOS 用 ctypes 调 CoreGraphics / LaunchAgent / afplay（见 MAC_PORT.md）；
其他系统有降级实现（主要给开发/测试用）。"""
import os, sys, json, time, platform, subprocess, wave, array, ctypes, collections, datetime

ASSET_TAG = 0x13320F1D        # 资源包标签（打包时写入，自检用）

IS_WIN = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'
APP = 'ZhangguiPet'      # 程序的 ASCII 标识：配置文件夹、互斥量、自启项、日志都用它


# ---------------- 配置目录：一个个试，真的写得进去才用；全都不行就只记在内存里，绝不因此崩溃 ----------------
# 种类：env（测试指定）/ appdata / localappdata / portable（程序旁边的 data）/ temp / memory（不落盘）
CONF_KIND = 'memory'
STORAGE_NOTE = {
    'localappdata': '设置换了个地方保存啦，可能是安全软件拦了一下～',
    'portable': '设置先存在程序旁边啦，可能是安全软件拦了一下～',
    'temp': '设置先放在临时文件夹里啦，可能是安全软件拦了一下，清理电脑后我可能会忘掉哦～',
    'memory': '这次设置只能先记在脑子里啦，关掉就会忘……可能是安全软件拦了一下～',
}


def app_dir():
    """exe 所在目录（打包后）或脚本所在目录（源码运行）。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def config_candidates():
    out = []
    e = os.environ.get('ZHANGGUI_PET_CONFIG_DIR')          # 测试用
    if e:
        out.append(('env', e))
    if IS_WIN:
        for kind, var in (('appdata', 'APPDATA'), ('localappdata', 'LOCALAPPDATA')):
            v = os.environ.get(var)
            if v:
                out.append((kind, os.path.join(v, APP)))
    elif IS_MAC:
        out.append(('appdata', os.path.join(os.path.expanduser('~/Library/Application Support'), APP)))
    else:
        out.append(('appdata', os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), APP)))
    try:
        out.append(('portable', os.path.join(app_dir(), 'data')))
    except Exception:
        pass
    try:
        import tempfile
        out.append(('temp', os.path.join(tempfile.gettempdir(), APP)))
    except Exception:
        pass
    return out


# ---------------- 旧版（v0.3.3 及以前）留下的东西：只读，绝不删除 ----------------
# 旧版用的 ASCII 名。只用在下面两件事上：① 第一次启动时把旧设置读过来一次；② 识别旧版自己写的开机自启项。
# 这是旧文件夹/注册表项的名字，不会显示在任何界面上。
LEGACY_APP = 'QwenPet'
LEGACY_EXE_MARKS = ('qwenpet.exe', 'qwen_pet.py')    # 旧版自启命令里一定带其中之一（小写比较）
MIGRATED_MARK = 'migrated_from_old_version.txt'


def legacy_config_dirs():
    """旧版可能存设置的位置（和旧版的查找顺序一致）。测试可以用 ZHANGGUI_PET_LEGACY_DIR 指定。"""
    e = os.environ.get('ZHANGGUI_PET_LEGACY_DIR')
    if e:
        return [('env', e)]
    out = []
    if IS_WIN:
        for kind, var in (('appdata', 'APPDATA'), ('localappdata', 'LOCALAPPDATA')):
            v = os.environ.get(var)
            if v:
                out.append((kind, os.path.join(v, LEGACY_APP)))
    elif IS_MAC:
        out.append(('appdata', os.path.join(os.path.expanduser('~/Library/Application Support'), LEGACY_APP)))
    else:
        out.append(('appdata', os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), LEGACY_APP)))
    try:                                               # 便携模式：旧程序文件夹和新文件夹放在同一层时（比如 D:\ 下并排）
        out.append(('portable', os.path.join(os.path.dirname(app_dir()), LEGACY_APP, 'data')))
    except Exception:
        pass
    try:
        import tempfile
        out.append(('temp', os.path.join(tempfile.gettempdir(), LEGACY_APP)))
    except Exception:
        pass
    return out


def migrate_legacy_settings(conf, kind, log):
    """新配置目录里还没有 settings.json 时，从旧版目录读一次设置复制过来（旧目录原样保留，不删不改）。
    只做一次：复制成功后新目录里就有 settings.json 了；另外留一个标记文件。返回旧目录种类或 None。"""
    try:
        if not conf:
            return None
        if kind == 'env' and not os.environ.get('ZHANGGUI_PET_LEGACY_DIR'):
            return None                                  # 测试用的配置目录：不去碰真机上的旧设置
        new = os.path.join(conf, 'settings.json')
        if os.path.exists(new) or os.path.exists(os.path.join(conf, MIGRATED_MARK)):
            return None
        for lk, d in legacy_config_dirs():
            src = os.path.join(d, 'settings.json')
            if os.path.abspath(d) == os.path.abspath(conf) or not os.path.isfile(src):
                continue
            try:
                with open(src, encoding='utf-8') as f:
                    raw = json.load(f)
                if not isinstance(raw, dict):
                    continue
            except Exception as e:
                log('legacy settings unreadable', lk, type(e).__name__)
                continue
            if write_text_safely(new, json.dumps(raw, ensure_ascii=False, indent=1), log):
                write_text_safely(os.path.join(conf, MIGRATED_MARK),
                                  f'{datetime.datetime.now().isoformat(timespec="seconds")} 已从旧版设置（{lk}）复制一次；旧文件夹原样保留。\n', log)
                log('settings migrated from old version', lk)
                return lk
        return None
    except Exception as e:
        log('settings migration failed', type(e).__name__)
        return None


def dir_writable(d):
    """真的建目录 + 写一个小文件 + 读回来 + 删掉；任何一步失败都算不可用。"""
    try:
        os.makedirs(d, exist_ok=True)
        t = os.path.join(d, '.write_test_%d.tmp' % os.getpid())
        with open(t, 'w', encoding='utf-8') as f:
            f.write('ok')
        with open(t, encoding='utf-8') as f:
            ok = f.read() == 'ok'
        try:
            os.remove(t)
        except OSError:
            pass
        return ok
    except Exception:
        return False


def resolve_config_dir():
    """返回 (目录或 None, 种类, 试过但失败的种类列表)。目录为 None 表示只用内存。"""
    global CONF_KIND
    failed = []
    for kind, d in config_candidates():
        if dir_writable(d):
            CONF_KIND = kind
            return d, kind, failed
        failed.append(kind)
    CONF_KIND = 'memory'
    return None, 'memory', failed


def config_dir():
    """兼容旧调用：返回可写的配置目录，或 None（只用内存）。"""
    return resolve_config_dir()[0]


def folder_tag(d=None):
    """程序文件夹的短指纹（不记路径本身）：用来记“这个文件夹已经提示过了”。"""
    import hashlib
    try:
        d = os.path.normcase(os.path.abspath(d or app_dir()))
    except Exception:
        d = ''
    return hashlib.sha1(d.encode('utf-8', 'replace')).hexdigest()[:12]


def adopt_portable_settings(conf, kind, log):
    """v0.3.9 ilfix：以前在“低权限”文件夹里跑时，设置只能存在程序旁边的 data 文件夹里；
    现在 AppData 能写了，如果 data 文件夹里的 settings.json 比 AppData 里的新，就把它接过来（AppData 旧文件先留一份 .bak）。
    这样换回正常权限后不会突然用回一份过时的设置（比如“拖到屏幕边”被关掉的旧设置）。返回 True = 接过来了。"""
    try:
        if kind != 'appdata' or not conf:
            return False
        src = os.path.join(app_dir(), 'data', 'settings.json')
        dst = os.path.join(conf, 'settings.json')
        if not os.path.isfile(src) or os.path.abspath(src) == os.path.abspath(dst):
            return False
        if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            return False
        with open(src, encoding='utf-8') as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return False
        if os.path.isfile(dst):
            try:
                os.replace(dst, dst + '.bak')
            except OSError:
                pass
        ok = write_text_safely(dst, json.dumps(raw, ensure_ascii=False, indent=1), log)
        log('settings adopted from portable data', ok)
        return ok
    except Exception as e:
        log('adopt portable failed', type(e).__name__)
        return False


def write_text_safely(path, text, log=None):
    """写文本文件；失败只记日志并返回 False，绝不抛异常。"""
    if not path:
        return False
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return True
    except Exception as e:
        if log:
            try:
                log('write failed', type(e).__name__)
            except Exception:
                pass
        return False


# ---------------- 单实例：Windows 用命名互斥量 + 命名事件，完全不需要写文件 ----------------
class SingleInstance:
    NAME = 'Local\\ZhangguiPet-single-v1'
    WAKE = 'Local\\ZhangguiPet-wake-v1'

    def __init__(self, conf, log):
        self.conf, self.log = conf, log
        self.mutex = self.event = None
        self.qlock = None
        self.flag = os.path.join(conf, 'wake.flag') if conf else None

    def _k(self):
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        for fn in ('CreateMutexW', 'CreateEventW', 'OpenEventW'):
            getattr(k, fn).restype = ctypes.c_void_p
        return k

    def acquire(self):
        """True = 我是第一个；False = 已经有一个在跑了。拿不准的时候宁可让她跑起来。"""
        try:
            if IS_WIN:
                k = self._k()
                h = k.CreateMutexW(None, False, self.NAME)
                err = ctypes.get_last_error()
                if not h:
                    self.log('instance mutex unavailable', err)
                    return True
                if err == 183:                                   # ERROR_ALREADY_EXISTS
                    k.CloseHandle(ctypes.c_void_p(h))
                    return False
                self.mutex = h
                self.event = k.CreateEventW(None, False, False, self.WAKE) or None   # 自动复位
                return True
            from PySide6.QtCore import QLockFile
            import tempfile
            for d, n in ((self.conf, 'instance.lock'), (tempfile.gettempdir(), APP + '-instance.lock')):
                if not d:
                    continue
                try:
                    lk = QLockFile(os.path.join(d, n))
                    lk.setStaleLockTime(0)
                    if lk.tryLock(200):
                        self.qlock = lk
                        return True
                    if lk.error() == QLockFile.LockFailedError:
                        return False
                except Exception:
                    continue
            return True
        except Exception as e:
            self.log('instance check failed', type(e).__name__)
            return True

    def poke(self):
        """第二次启动时调用：叫已经开着的那个出来。失败就算了。"""
        try:
            if IS_WIN:
                k = self._k()
                h = k.OpenEventW(0x0002, False, self.WAKE)       # EVENT_MODIFY_STATE
                if h:
                    k.SetEvent(ctypes.c_void_p(h))
                    k.CloseHandle(ctypes.c_void_p(h))
                    return True
                return False
            return write_text_safely(self.flag, str(time.time()), self.log)
        except Exception:
            return False

    def poked(self):
        try:
            if IS_WIN:
                if self.event:
                    return ctypes.windll.kernel32.WaitForSingleObject(ctypes.c_void_p(self.event), 0) == 0
                return False
            if self.flag and os.path.exists(self.flag):
                try:
                    os.remove(self.flag)
                except OSError:
                    pass
                return True
        except Exception:
            pass
        return False

    def release(self):
        try:
            if IS_WIN:
                for h in (self.event, self.mutex):
                    if h:
                        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(h))
                self.event = self.mutex = None
            elif self.qlock:
                self.qlock.unlock()
        except Exception:
            pass


# ---------------- 日志（只记事件，不记文件名、不记任何个人内容） ----------------
class Log:
    MAX = 256 * 1024

    def __init__(self, d):
        self.path = os.path.join(d, 'zhanggui-pet.log') if d else None   # None = 只留在内存里（导出诊断时用）
        self.ring = collections.deque(maxlen=400)
        self.fails = 0

    def __call__(self, *a):
        try:
            s = time.strftime('%Y-%m-%d %H:%M:%S ') + ' '.join(str(x) for x in a)
        except Exception:
            return
        self.ring.append(s)
        if os.environ.get('ZHANGGUI_PET_DEBUG') == '1':
            try:
                print('[log]', s, flush=True)
            except Exception:
                pass
        if not self.path or self.fails >= 5:          # 连着写不进去就不再试，免得每次都卡一下
            return
        try:
            if os.path.exists(self.path) and os.path.getsize(self.path) > self.MAX:
                os.replace(self.path, self.path + '.1')
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(s + '\n')
            self.fails = 0
        except Exception:
            self.fails += 1


# ---------------- 设置 ----------------
DEFAULTS = {
    'scale': 1.0,            # 0.2 ~ 1.5
    'legs': False,           # 默认飘着；长脚模式独立记住大小
    'scale_legs': 0.75,
    'on_top': True,
    'muted': False,
    'volume': 0.35,          # 预录语音音量（默认偏小）
    'quiet_until': 0.0,      # 安静模式截止时间（time.time）
    'time_greet': True,      # 按时段问候
    'return_greet': True,    # 离开回来打招呼
    'remind_water': False,   # 喝水提醒（默认关）
    'water_min': 45,
    'remind_stand': False,   # 久坐提醒（默认关）
    'stand_min': 60,
    'micro': 'mid',          # 待机小动作：off / low / mid / high
    'fullscreen_hide': True,
    'edge_peek': True,
    'pomo_focus': 25,
    'pomo_break': 5,
    'show_timer_badge': True,
    'first_run_done': False,
    'pos': {},               # {屏幕名: [rx, ry]}  她脚底中点在该屏可用区域里的相对位置
    'last_screen': '',
    'peek_side': '',         # '' / 'left' / 'right'
    'storage_notice': '',    # 已经提示过的“设置换地方保存”种类（只提示一次）
    'lowil_notice': '',      # v0.3.9 ilfix：已经提示过“低权限运行”的程序文件夹指纹（同一个文件夹只提示一次）
}
RANGES = {'scale': (0.2, 1.5), 'scale_legs': (0.2, 1.5), 'volume': (0.0, 1.0), 'water_min': (10, 240), 'stand_min': (20, 240),
          'pomo_focus': (1, 180), 'pomo_break': (1, 60)}
CHOICES = {'micro': ('off', 'low', 'mid', 'high'), 'peek_side': ('', 'left', 'right')}


class Settings(dict):
    def __init__(self, d, log):
        super().__init__(DEFAULTS)
        self['pos'] = {}
        self.path = os.path.join(d, 'settings.json') if d else None    # None = 只在内存里，不保存
        self.log = log
        if not self.path:
            return
        try:
            with open(self.path, encoding='utf-8') as f:
                raw = json.load(f)
            self._merge(raw)
        except FileNotFoundError:
            pass
        except OSError as e:                          # 读不了（权限/被拦）：用默认值，别去动那个文件
            log('settings unreadable, defaults:', type(e).__name__)
        except Exception as e:                       # 损坏就用默认值，并留一份备份
            log('settings broken, reset:', type(e).__name__)
            try:
                os.replace(self.path, self.path + '.broken')
            except OSError:
                pass

    def _merge(self, raw):
        if not isinstance(raw, dict):
            return
        for k, dv in DEFAULTS.items():
            if k not in raw:
                continue
            v = raw[k]
            if isinstance(dv, bool):
                if isinstance(v, bool): self[k] = v
            elif isinstance(dv, (int, float)):
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    lo, hi = RANGES.get(k, (-1e18, 1e18))
                    self[k] = type(dv)(min(hi, max(lo, v)))
            elif k == 'pos':
                if isinstance(v, dict):
                    self[k] = {str(n): [float(p[0]), float(p[1])] for n, p in v.items()
                               if isinstance(p, list) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p)
                               and -0.5 <= p[0] <= 1.5 and -0.5 <= p[1] <= 1.5}
            elif isinstance(dv, str):
                if isinstance(v, str) and (k not in CHOICES or v in CHOICES[k]): self[k] = v

    def save(self):
        if not self.path:
            return False
        tmp = self.path + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)                  # 原子替换，写一半断电也不会坏
            return True
        except Exception as e:                          # 写不进去只记一笔，绝不崩
            try:
                self.log('settings save failed', type(e).__name__)
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            return False


# ---------------- 多久没操作（只读系统的“最后输入时间”，不装键盘钩子） ----------------
_xss = None


def idle_seconds():
    sim = os.environ.get('ZHANGGUI_PET_SIM_IDLE_FILE')      # 测试用：文件里写秒数
    if sim:
        try:
            return float(open(sim).read().strip() or 0)
        except (OSError, ValueError):
            pass
    if IS_WIN:
        class LII(ctypes.Structure):
            _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]
        lii = LII(); lii.cbSize = ctypes.sizeof(LII)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return ((ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0
        return None
    if IS_MAC:
        return _mac_idle()
    return _x11_idle()


_cg = None


def _mac_idle():
    """CGEventSourceSecondsSinceLastEventType(组合会话状态, 任意输入)：不需要辅助功能/录屏权限。"""
    global _cg
    if _cg is False:
        return None
    try:
        if _cg is None:
            _cg = ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
            _cg.CGEventSourceSecondsSinceLastEventType.restype = ctypes.c_double
            _cg.CGEventSourceSecondsSinceLastEventType.argtypes = [ctypes.c_int32, ctypes.c_uint32]
        return float(_cg.CGEventSourceSecondsSinceLastEventType(0, 0xFFFFFFFF))   # kCGEventSourceStateCombinedSessionState, kCGAnyInputEventType
    except Exception:
        _cg = False
        return None


def _x11_idle():
    global _xss
    if _xss is False:
        return None
    try:
        if _xss is None:
            x11 = ctypes.CDLL('libX11.so.6'); xss = ctypes.CDLL('libXss.so.1')
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XDefaultRootWindow.restype = ctypes.c_ulong
            x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            xss.XScreenSaverAllocInfo.restype = ctypes.c_void_p
            xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]
            dpy = x11.XOpenDisplay(None)
            if not dpy:
                raise OSError('no display')
            _xss = (x11, xss, dpy, xss.XScreenSaverAllocInfo())
        x11, xss, dpy, info = _xss

        class Info(ctypes.Structure):
            _fields_ = [('window', ctypes.c_ulong), ('state', ctypes.c_int), ('kind', ctypes.c_int),
                        ('til_or_since', ctypes.c_ulong), ('idle', ctypes.c_ulong), ('eventMask', ctypes.c_ulong)]
        xss.XScreenSaverQueryInfo(dpy, x11.XDefaultRootWindow(dpy), info)
        return Info.from_address(info).idle / 1000.0
    except Exception:
        _xss = False
        return None


# ---------------- 前台全屏检测 ----------------
# v0.3.5：Windows.UI.Core.CoreWindow 不再整类排除。这个类既用于开始菜单/搜索/通知中心等系统弹层，
# 也可能是 UWP 应用自己的窗口。现在只有它属于下面这些系统壳进程时才忽略；查不到进程名时，
# 为了和 v0.3.4 行为一致（宁可不躲，也不乱躲），仍按系统弹层处理。需要在真 Windows 上验证。
_SHELL_CLASSES = {'Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd',
                  'XamlExplorerHostIslandWindow', 'TopLevelWindowForOverflowXamlIsland', 'NotifyIconOverflowWindow'}
_COREWINDOW = 'Windows.UI.Core.CoreWindow'
_SHELL_HOSTS = {'startmenuexperiencehost.exe', 'searchhost.exe', 'searchapp.exe', 'searchui.exe',
                'shellexperiencehost.exe', 'textinputhost.exe', 'lockapp.exe', 'shellhost.exe', 'explorer.exe'}
_W32 = None


def _win32():
    """user32/kernel32 的函数声明只做一次（argtypes/restype 写全，句柄按指针宽度传，不会被截成 32 位）。
    用私有的 WinDLL 实例，不改全局 ctypes.windll.user32 上的声明。"""
    global _W32
    if _W32 is not None:
        return _W32
    from ctypes import wintypes as W

    class MONITORINFO(ctypes.Structure):
        _fields_ = [('cbSize', W.DWORD), ('rcMonitor', W.RECT), ('rcWork', W.RECT), ('dwFlags', W.DWORD)]

    u = ctypes.WinDLL('user32', use_last_error=True)
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    u.GetForegroundWindow.argtypes = []
    u.GetForegroundWindow.restype = W.HWND
    u.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
    u.MonitorFromWindow.restype = W.HANDLE
    u.GetMonitorInfoW.argtypes = [W.HANDLE, ctypes.POINTER(MONITORINFO)]
    u.GetMonitorInfoW.restype = W.BOOL
    u.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    u.GetClassNameW.restype = ctypes.c_int
    for name in ('IsIconic', 'IsWindowVisible'):
        fn = getattr(u, name)
        fn.argtypes = [W.HWND]
        fn.restype = W.BOOL
    u.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
    u.GetWindowRect.restype = W.BOOL
    u.GetWindowLongW.argtypes = [W.HWND, ctypes.c_int]          # 只读 GWL_STYLE（32 位值），不需要 ...LongPtrW
    u.GetWindowLongW.restype = W.LONG
    u.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    u.GetWindowThreadProcessId.restype = W.DWORD
    k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k.OpenProcess.restype = W.HANDLE
    k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
    k.QueryFullProcessImageNameW.restype = W.BOOL
    k.CloseHandle.argtypes = [W.HANDLE]
    k.CloseHandle.restype = W.BOOL
    _W32 = (u, k, W, MONITORINFO)
    return _W32


def _process_exe_name(hwnd):
    """窗口所属进程的 exe 文件名（小写，只要文件名不要路径）；拿不到返回 None。"""
    u, k, W, _ = _win32()
    pid = W.DWORD(0)
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None
    h = k.OpenProcess(0x1000, False, pid.value)                 # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(520)
        n = W.DWORD(520)
        if not k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return None
        return os.path.basename(buf.value).lower()
    finally:
        k.CloseHandle(h)


def is_shell_window(cls, exe_name):
    """前台窗口是不是系统壳（桌面、任务栏、开始菜单这类）：是的话不算“全屏程序”。纯函数，方便测试。"""
    if cls in _SHELL_CLASSES:
        return True
    if cls == _COREWINDOW:
        return exe_name is None or exe_name in _SHELL_HOSTS
    return False


def fullscreen_on_my_monitor(my_hwnd):
    """前台窗口是否占满了“她所在的那块屏幕”。返回 True/False。
    系统接口出错时会抛异常（由调用方记日志），不再在这里悄悄变成 False。"""
    sim = os.environ.get('ZHANGGUI_PET_SIM_FULLSCREEN_FILE')   # 测试用：文件存在 = 有全屏程序
    if sim:
        return os.path.exists(sim)
    if not IS_WIN:
        # macOS：全屏程序在自己的 Space 里；桌宠窗口没设 FullScreenAuxiliary，系统本来就不会把她叠在全屏程序上面。
        return False
    u, k, W, MONITORINFO = _win32()
    fg = u.GetForegroundWindow()
    if not fg or int(fg) == int(my_hwnd):
        return False
    buf = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(fg, buf, 256)
    cls = buf.value
    if cls in _SHELL_CLASSES:
        return False
    if cls == _COREWINDOW and is_shell_window(cls, _process_exe_name(fg)):
        return False
    if u.IsIconic(fg) or not u.IsWindowVisible(fg):
        return False
    mon_fg = u.MonitorFromWindow(fg, 2)
    mon_me = u.MonitorFromWindow(W.HWND(int(my_hwnd)), 2)
    if not mon_fg or mon_fg != mon_me:
        return False
    mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not u.GetMonitorInfoW(mon_fg, ctypes.byref(mi)):
        return False
    r = W.RECT()
    if not u.GetWindowRect(fg, ctypes.byref(r)):               # 读不到窗口矩形：别拿全 0 的矩形去比
        return False
    m = mi.rcMonitor
    covers = r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom
    if not covers:
        return False
    exact = (r.left, r.top, r.right, r.bottom) == (m.left, m.top, m.right, m.bottom)
    # 普通最大化窗口的矩形会比屏幕大一圈边框（任务栏自动隐藏时也会“盖满”），它们带标题栏样式；
    # 真全屏（游戏、F11、播放器全屏）要么正好等于屏幕，要么没有标题栏
    style = u.GetWindowLongW(fg, -16) & 0xFFFFFFFF          # GWL_STYLE
    has_caption = (style & 0x00C00000) == 0x00C00000         # WS_CAPTION
    return exact or not has_caption


# ---------------- 开机自启（只在用户勾选时写 HKCU\...\Run；取消就删掉） ----------------
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def autostart_command():
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    exe = sys.executable
    if IS_WIN and exe.lower().endswith('python.exe'):
        exe = exe[:-10] + 'pythonw.exe'
    return f'"{exe}" "{os.path.abspath(sys.argv[0])}"'


def _run_key_values():
    import winreg
    out = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        i = 0
        while True:
            try:
                n, v, _ = winreg.EnumValue(k, i)
            except OSError:
                break
            out[n] = v
            i += 1
    return out


# macOS：~/Library/LaunchAgents/<MAC_AGENT_ID>.plist（只在用户勾选时写；取消就删掉，只删我们自己的这一个文件）
MAC_AGENT_ID = 'local.ZhangguiPet'


def _mac_agent_path():
    return os.path.join(os.path.expanduser('~/Library/LaunchAgents'), MAC_AGENT_ID + '.plist')


def _mac_program_args():
    if getattr(sys, 'frozen', False):
        exe = os.path.abspath(sys.executable)
        i = exe.find('.app/Contents/MacOS/')
        if i > 0:                                        # 打包成 .app：用 open 起，Dock/权限归属都按 .app 走
            return ['/usr/bin/open', exe[:i + 4]]
        return [exe]
    return [sys.executable, os.path.abspath(sys.argv[0])]


def autostart_supported():
    return IS_WIN or IS_MAC


def autostart_get():
    if IS_MAC:
        return os.path.exists(_mac_agent_path())
    if not IS_WIN:
        return False
    try:
        return APP in _run_key_values()
    except Exception:                                   # 读不了注册表就当没开
        return False


def legacy_autostart():
    """旧版写的开机自启项还在吗？只认旧版自己的那一项（名字是旧名，命令里带旧 exe/脚本名）。
    返回 'ours'（是旧版自己的）、'other'（同名但命令不像旧版，不碰）或 None（没有）。只读。"""
    if not IS_WIN:
        return None
    try:
        vals = _run_key_values()
    except Exception:
        return None
    if LEGACY_APP not in vals:
        return None
    cmd = str(vals[LEGACY_APP] or '').lower()
    return 'ours' if any(m in cmd for m in LEGACY_EXE_MARKS) else 'other'


def autostart_set(on):
    """只在用户点「开机自动启动」时调用。顺手清掉旧版自己的那一项（同名且命令里带旧 exe/脚本名才删），
    免得开机时新旧两个一起起来。返回 True；清掉了旧项时返回 'legacy_removed'。"""
    if IS_MAC:
        import plistlib
        path = _mac_agent_path()
        if on:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                plistlib.dump({'Label': MAC_AGENT_ID, 'ProgramArguments': _mac_program_args(),
                               'RunAtLoad': True, 'ProcessType': 'Interactive'}, f)
        elif os.path.exists(path):
            os.remove(path)
        return True
    if not IS_WIN:
        return False
    import winreg
    removed = False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP)
            except FileNotFoundError:
                pass
        if legacy_autostart() == 'ours':
            try:
                winreg.DeleteValue(k, LEGACY_APP)
                removed = True
            except OSError:
                pass
    return 'legacy_removed' if removed else True


# ---------------- 预录语音播放（不依赖 QtMultimedia） ----------------
class Voice:
    """assets/voice/<台词id>.wav（16-bit PCM）。按音量把采样缩放后写到配置目录的临时文件再播：
    Windows 用自带的 winsound（异步），macOS 用系统自带 afplay，其他系统找 paplay/aplay/ffplay。没有语音文件就静默。"""

    def __init__(self, voice_dir, conf, log):
        self.dir = voice_dir
        if conf:
            self.cache_dir = os.path.join(conf, 'cache')
        else:
            import tempfile
            self.cache_dir = os.path.join(tempfile.gettempdir(), APP + '-cache')
        self.log = log
        self.flip = 0
        self.proc = None
        self.ids = set()
        if os.path.isdir(voice_dir):
            self.ids = {f[:-4] for f in os.listdir(voice_dir) if f.endswith('.wav')}
        self.player = None
        if IS_MAC:
            self.player = ['/usr/bin/afplay']
        elif not IS_WIN:
            import shutil
            for p in (['paplay'], ['aplay', '-q'], ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet']):
                if shutil.which(p[0]):
                    self.player = p; break
        self.last = None   # 测试用：最近一次播放的 (id, 文件)

    def available(self):
        return bool(self.ids)

    def has(self, line_id):
        return line_id in self.ids

    def play(self, line_id, volume):
        if line_id not in self.ids or volume <= 0:
            return False
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            src = os.path.join(self.dir, line_id + '.wav')
            with wave.open(src, 'rb') as w:
                params = w.getparams()
                data = w.readframes(w.getnframes())
            if params.sampwidth == 2:
                a = array.array('h', data)
                if sys.byteorder == 'big': a.byteswap()
                k = max(0.0, min(1.0, volume))
                a = array.array('h', (int(x * k) for x in a))
                if sys.byteorder == 'big': a.byteswap()
                data = a.tobytes()
            self.flip ^= 1
            out = os.path.join(self.cache_dir, f'say{self.flip}.wav')
            with wave.open(out, 'wb') as w:
                w.setparams(params)
                w.writeframes(data)
            self.last = (line_id, out)
            if os.environ.get('ZHANGGUI_PET_NO_AUDIO') == '1':      # 测试机没有声卡
                return True
            if IS_WIN:
                import winsound
                winsound.PlaySound(out, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            elif self.player:
                if self.proc and self.proc.poll() is None:
                    self.proc.terminate()
                self.proc = subprocess.Popen(self.player + [out], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            self.log('voice failed', type(e).__name__)
            return False

    def stop(self):
        try:
            if IS_WIN:
                import winsound
                winsound.PlaySound(None, 0)
            elif self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass


def integrity_level():
    """Windows 进程的完整性级别：0x1000 低 / 0x2000 中（普通程序）/ 0x3000 高。拿不到返回 None。
    低完整性的进程（比如 exe 放在被标成“低完整性”的文件夹里）既写不了 AppData，也加不了托盘图标。"""
    if not IS_WIN:
        return None
    if os.environ.get('ZHANGGUI_PET_SIM_LOW_IL') == '1':       # 测试用
        return 0x1000
    try:
        from ctypes import wintypes as W
        a = ctypes.WinDLL('advapi32'); k = ctypes.WinDLL('kernel32')
        k.GetCurrentProcess.restype = ctypes.c_void_p
        a.OpenProcessToken.argtypes = [ctypes.c_void_p, W.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        a.GetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD)]
        a.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]; a.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        a.GetSidSubAuthority.argtypes = [ctypes.c_void_p, W.DWORD]; a.GetSidSubAuthority.restype = ctypes.POINTER(W.DWORD)
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        t = ctypes.c_void_p()
        if not a.OpenProcessToken(k.GetCurrentProcess(), 8, ctypes.byref(t)):      # TOKEN_QUERY
            return None
        try:
            n = W.DWORD()
            a.GetTokenInformation(t, 25, None, 0, ctypes.byref(n))                    # TokenIntegrityLevel
            buf = ctypes.create_string_buffer(n.value)
            if not a.GetTokenInformation(t, 25, buf, n, ctypes.byref(n)):
                return None
            psid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
            cnt = a.GetSidSubAuthorityCount(psid)[0]
            return int(a.GetSidSubAuthority(psid, cnt - 1)[0])
        finally:
            k.CloseHandle(t)
    except Exception:
        return None


def system_summary():
    return f'{platform.system()} {platform.release()} ({platform.version()}) py{platform.python_version()}'
