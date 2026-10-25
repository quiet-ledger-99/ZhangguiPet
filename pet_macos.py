# -*- coding: utf-8 -*-
"""macOS 专用的一点点原生调整（只用 ctypes 调 Objective-C 运行时，不依赖 pyobjc）。
- 不在 Dock 里出现图标（NSApplicationActivationPolicyAccessory，和打包后 Info.plist 的 LSUIElement 效果一样）；
- 桌宠窗口跟着你切换桌面（所有 Space 都在）、不参与 Cmd+` 窗口轮换、App 不在前台时也不自动藏起来；
  不设 FullScreenAuxiliary：别的程序全屏时（自己一个 Space）她不会叠上去 = macOS 上的“有全屏程序时自动躲起来”。
任何一步失败都只是少了这点体验，不影响她正常显示。"""
import sys, ctypes

IS_MAC = sys.platform == 'darwin'
_objc = None

# NSWindowCollectionBehavior
CAN_JOIN_ALL_SPACES = 1 << 0
STATIONARY = 1 << 4
IGNORES_CYCLE = 1 << 6


def _rt():
    global _objc
    if _objc is None:
        o = ctypes.cdll.LoadLibrary('/usr/lib/libobjc.A.dylib')
        o.objc_getClass.restype = ctypes.c_void_p; o.objc_getClass.argtypes = [ctypes.c_char_p]
        o.sel_registerName.restype = ctypes.c_void_p; o.sel_registerName.argtypes = [ctypes.c_char_p]
        _objc = o
    return _objc


def _send(obj, sel, *args, restype=ctypes.c_void_p, argtypes=()):
    o = _rt()
    fn = ctypes.cast(o.objc_msgSend, ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes))
    return fn(obj, o.sel_registerName(sel.encode()), *args)


def _cocoa():
    """只有真的用 macOS 原生窗口（Qt 的 cocoa 平台插件）时才动它；offscreen 测试时 winId 不是 NSView。"""
    if not IS_MAC:
        return False
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.platformName() == 'cocoa'


def hide_dock_icon():
    """QApplication 建好之后调用一次。打包成 .app 时 Info.plist 里的 LSUIElement 已经做了同样的事。"""
    if not _cocoa():
        return False
    try:
        app = _send(_rt().objc_getClass(b'NSApplication'), 'sharedApplication')
        return bool(_send(app, 'setActivationPolicy:', 1, restype=ctypes.c_bool, argtypes=(ctypes.c_long,)))
    except Exception:
        return False


def tune_pet_window(widget):
    """窗口 show() 之后调用（Qt 改窗口标志时可能重建原生窗口，所以每次 show 都调一次）。"""
    if not _cocoa():
        return False
    try:
        view = int(widget.winId())                       # macOS 上 winId() 是 NSView*
        win = _send(view, 'window') if view else None
        if not win:
            return False
        _send(win, 'setCollectionBehavior:', CAN_JOIN_ALL_SPACES | STATIONARY | IGNORES_CYCLE,
              restype=None, argtypes=(ctypes.c_ulong,))
        _send(win, 'setHidesOnDeactivate:', False, restype=None, argtypes=(ctypes.c_bool,))
        return True
    except Exception:
        return False
