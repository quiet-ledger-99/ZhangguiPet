#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""掌柜台桌宠 v0.3.9 —— 非官方粉丝二创，与阿里巴巴及通义千问无隶属或合作关系；含 AI 生成内容（详见 README「署名与授权」）。
完全离线：不联网、不要任何 key、不监听键盘、不打开/移动/删除你的文件。
依赖：PySide6（Essentials 即可）。运行：python zhanggui_pet.py
台词在 pet_lines.py；系统相关（设置、全屏检测、空闲时间、自启、语音）在 pet_platform.py；
“说什么”的接口在 pet_brain.py（v0.4 的可选联网聊天/TTS 从这里接）。"""
import os, sys, json, random, time, datetime, traceback

VERSION = '0.3.9'
_BUILD_SIG = 0x13320F1D        # 构建签名（资源完整性）


# ======================= 兜底：任何没接住的异常都写崩溃记录 + 温柔的提示框（不弹 PyInstaller 原始错误框） =======================
_STARTED = False          # app.exec() 之后为 True：运行中的小错误只记录、不打扰
_CRASH_DIR = None
_crash_count = 0


def _crash_dirs():
    ds = [_CRASH_DIR] if _CRASH_DIR else []
    try:
        import pet_platform as _P
        ds += [d for _, d in _P.config_candidates()]
    except Exception:
        pass
    try:
        import tempfile
        ds.append(tempfile.gettempdir())
    except Exception:
        pass
    return ds


def write_crash_log(text):
    name = time.strftime('ZhangguiPet-crash-%Y%m%d-%H%M%S.log')
    for d in _crash_dirs():
        try:
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, name)
            with open(p, 'a', encoding='utf-8') as f:
                f.write(text)
            return p
        except Exception:
            continue
    return None


def friendly_box(msg):
    try:
        if os.environ.get('ZHANGGUI_PET_NO_DIALOG') == '1':      # 测试用：不弹框
            print('[dialog]', msg, flush=True); return
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, '掌柜台桌宠', 0x40 | 0x10000)   # 信息图标 + 置前
        else:
            print(msg, file=sys.stderr)
    except Exception:
        pass


def _excepthook(et, ev, tb):
    global _crash_count
    if et is not None and issubclass(et, KeyboardInterrupt):
        os._exit(130)
    _crash_count += 1
    try:
        text = ''.join(traceback.format_exception(et, ev, tb))
    except Exception:
        text = repr(ev)
    head = (f'掌柜台桌宠 v{VERSION}  {time.strftime("%Y-%m-%d %H:%M:%S")}  {"运行中" if _STARTED else "启动时"}\n'
            '（这是留在本机的完整崩溃记录，可能带文件夹路径；要分享请用菜单「导出诊断日志」，那份会去掉路径和屏幕名）\n')
    path = write_crash_log(head + text + '\n') if _crash_count <= 20 else None
    if _STARTED:
        return                       # 运行中某个小功能出错：记下来就好，她继续陪你
    short = f'{getattr(et, "__name__", "Error")}: {ev}'[:300]
    friendly_box('她出门的时候被绊了一下，这次没能出来……\n\n'
                 f'原因：{short}\n\n'
                 + (f'详细记录放在这里啦：\n{path}\n\n' if path else '')
                 + '如果装了安全软件，可以试试把 ZhangguiPet.exe 加进信任，再打开一次～\n'
                   '把记录发给作者，也能帮她早点改好哦（记录里可能有文件夹路径，发之前可以先看一眼）。')
    os._exit(1)


sys.excepthook = _excepthook
from collections import OrderedDict
from PySide6.QtCore import (Qt, QTimer, QPoint, QRect, QRectF, QPointF, QPropertyAnimation,
                            QEasingCurve, QUrl, qVersion)
from PySide6.QtGui import (QImage, QPainter, QRegion, QBitmap, QFont, QFontMetrics, QColor, QPainterPath, QPen,
                           QAction, QActionGroup, QGuiApplication, QIcon, QCursor, QDesktopServices)
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon, QWidgetAction, QSlider, QLabel,
                               QHBoxLayout, QVBoxLayout, QPushButton, QSpinBox, QCheckBox, QRadioButton, QButtonGroup)

import pet_lines as PL
import pet_platform as P
from pet_brain import LocalBrain

BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(BASE, 'assets', 'sprites')
FXD = os.path.join(BASE, 'assets', 'fx')
MASKD = os.path.join(BASE, 'assets', 'masks')
VOICED = os.path.join(BASE, 'assets', 'voice')
ICON = os.path.join(BASE, 'assets', 'icon.png')
ICON_ICO = os.path.join(BASE, 'assets', 'icon.ico')     # 多尺寸（16/24/32/48/64），托盘用它更清楚
PEEKD = os.path.join(BASE, 'assets', 'peek')             # 躲屏幕边的立绘：shy_/tilt_ + right/left/top/bottom
PEEK_FADE = 0.15                                          # 害羞 <-> 探头 的淡入淡出秒数（上/下边是同样时长的滑动）
PEEK_SIDES = ('left', 'right', 'top', 'bottom')
PEEK_TB = ('top', 'bottom')                               # 上/下边：只有一张探头图，害羞 = 同一张图往屏幕外缩回去一截
PEEK_RETRACT = {'top': 64, 'bottom': 35}                  # 缩回去多少（251x380 画布上的像素），assets/peek/peek.json 可覆盖
PEEK_BOTTOM_PAST = 0.2                                    # 往下拖过可用区域底边（任务栏上沿）这么多（身高比例）才算「躲到下边」
PEEK_BOTTOM_SEAL_PX = 0                                 # 不要整体下压立绘进任务栏（曾切下巴）；空隙只靠清 soft
PEEK_ENABLE_TOP = False                                   # 周日发布版先关掉上方探头；tilt_top 等素材保留，以后改 True 即可再开
ENV = os.environ.get
DEBUG = ENV('ZHANGGUI_PET_DEBUG') == '1'
NOMASK = ENV('ZHANGGUI_PET_NOMASK') == '1'
HOLD_SECS = float(ENV('ZHANGGUI_PET_HOLD', '30'))       # 点完后保持表情多久（无操作）再回到待机
AWAY_SECS = float(ENV('ZHANGGUI_PET_AWAY_SECS', '300'))  # 多久没操作算“离开”
# v0.3.3：切换淡化按“秒”算（不再绑 12fps 节拍），整体大幅缩短——0.67 秒的长淡化正是“糊一下就换了”的重影来源
FADE_CUT = 0.07       # 普通表情（笑/得意/思考）进出待机、同一表情内部衔接：几乎硬切（≈ 12fps 下不到 1 帧）
FADE_POSE = 0.15      # 牵涉整身姿势变化（回眸挥手 wave、合扇叉腰 huff）：约 2 帧
POSE_ANIMS = ('wave', 'huff')
# 切换瞬间的“落定”小动作：以脚底为锚点竖向轻压再弹回（只缩不放，头顶永远不出画布/遮罩，窗口位置不动）
SETTLE_SECS = 0.19
SETTLE_KEYS = ((0.0, 1.0), (0.065, 0.975), (0.13, 1.0), (0.16, 0.993), (0.19, 1.0))
CONTINUOUS = {('enter', 'hold'), ('hold', 'leave'), ('leave', 'idle')}   # 这几种衔接画面本来就连着：不加小动作
FAST_MS = 16          # 淡化/落定期间额外重画的间隔（约 60fps），不受 12fps 动画节拍限制
BUBBLE_H = 96
LONGPRESS_MS = 550
SIZE_ASK_MS = 1000     # 调大小停手多久后问「这个大小可以吗？」

# 关于页（署名与授权；和 README「署名与授权」一致）
DISCLAIMER = '非官方粉丝二创，与阿里巴巴及通义千问无隶属或合作关系。'
NOTICE = '千问娘桌宠为粉丝二创作品，与阿里巴巴/通义千问官方无关；永久免费发布，禁止商用、倒卖、二次打包收费。唯一发布渠道：B站 千问娘 账号（UID 322047773）置顶评论。'
CREDIT = '粉丝二创 · 永久免费 · 禁止商用倒卖 · 唯一发布：B站 千问娘（UID 322047773）'
ABOUT_HTML = (
    '<b>掌柜台桌宠 v{v}</b><br>'
    '千问娘形象二创的桌面小伙伴，角色名文昭。<br><br>'
    '<b>' + DISCLAIMER + '</b><br>'
    '<b>' + NOTICE + '</b><br>'
    '免费、无广告、不盈利。含 AI 生成内容；代码大部分由 AI 编写。完全离线，不联网。<br><br>'
    '<b>美术</b>：千问娘原作形象 © '
    '<a href="https://space.bilibili.com/4168597">@ZipZipPipe</a>（B站 UID 4168597）。'
    '本程序里的立绘、表情和动作是基于原作形象（借助 AI 工具）制作的二创。'
    '美术版权归原作者，仅按原作者公开条件免费使用；美术不适用下面的 MIT 许可。<br>'
    '<b>代码</b>：MIT 许可（见 LICENSE.txt）。<br>'
    '<b>第三方</b>：界面库 PySide6 / Qt 按 LGPL-3.0 使用，未经修改，以独立的库文件分发，'
    '可以自行替换（见 THIRD_PARTY_NOTICES.txt）。字体只用系统自带字体，不附带任何字体文件。<br><br>'
    '只通过作者 B站账号「千问娘今天也在记账」（UID 322047773）置顶评论发布的链接分发，其他来源请勿下载。<br>'
    '如角色原作者或相关权利方提出要求，将停止分发并下架；权利人如有异议请通过 B站私信联系。'
)

# 表情播放方案（片段 = (动画名, 起始帧, 结束帧)，按 12fps 帧号写；v0.3.9 长脚素材是 24fps，播放时按 fps/12 放大帧号，飘着模式仍是 12fps、不变）
EXPR = {
    'smile':    dict(enter=('smile', 0, 56), hold=('smile', 44, 56), leave=('smile', 56, 72)),
    'smug':     dict(enter=('smug', 0, 72), hold=('smug_hold', 0, 24), leave=None),
    'thinking': dict(enter=('thinking', 0, 48), hold=('thinking_hold', 0, 24), leave=('thinking', 48, 72)),
    # v0.3.6：台词里的表情名 biz / pout 不变（语音方案不受影响），画面换成更像民国千金的动作：
    #   biz  -> wave 回眸挥手、闭嘴浅笑（原来是把小包递到前面的露齿营业笑）；挥手最多停 4 秒，不会一直挥
    #   pout -> huff 合扇抵下巴、一手叉腰的小嘴硬（原来也是递包的鼓腮）
    'biz':      dict(enter=('wave', 0, 48), hold=('wave', 0, 48), leave=None, max_hold=4.0),
    'pout':     dict(enter=('huff', 0, 48), hold=('huff', 0, 48), leave=None),
}
MICRO = {'off': None, 'low': (240, 480), 'mid': (90, 200), 'high': (35, 80)}
MICRO_NAMES = [('off', '关'), ('low', '偶尔（4～8 分钟）'), ('mid', '适中（1.5～3 分钟）'), ('high', '经常（半分钟～1 分多）')]
# 同一秒有好几件事想说时的优先级（数字小的先说）
PRIO_TIMER, PRIO_RETURN, PRIO_STAND, PRIO_WATER, PRIO_SLOT = 0, 1, 2, 3, 4
PENDING_MAX_SECS = 90     # 被挤掉的一次性事件最多等这么久，过了就不补了


# ======================= 小工具（纯函数，方便测试） =======================
def clamp_bubble_y(y, h, vis):
    """气泡的 y 限制在可见区域 vis（窗口坐标）里：上面放不下就往下挪（压在她身上/身前），
    下面也留出 12px 给气泡尾巴。"""
    top = vis.top() + 2
    bottom = vis.bottom() - 2 - 12
    if y < top:
        y = top
    if y + h > bottom:
        y = max(top, bottom - h)
    return y


def edge_hit(r, avail, full, occupied, tol, allow_tb=True, allow_top=None, allow_bottom=None, body_h=None):
    """松手时贴着哪条屏幕边（纯函数，方便测试）。
    r: 精灵矩形；avail: 这块屏幕的可用区域（不含任务栏）；full: 这块屏幕的整个区域；
    occupied(QPoint) -> 那个点上是不是还有别的屏幕（有就不算边，继续拖到那块屏幕上去）。
    左/右优先；上边贴着可用区域顶就算；下边要往下拖过任务栏上沿 PEEK_BOTTOM_PAST 个身高才算
    （平时就站在任务栏上，不能一放下就躲起来）。
    allow_top / allow_bottom 可单独关某一边；默认跟 allow_tb 一致（兼容旧测试）。
    body_h 可指定上半身高度；省略时沿用整个精灵高度。"""
    cy = min(max(r.center().y(), avail.top()), avail.bottom())
    cx = min(max(r.center().x(), avail.left()), avail.right())
    if r.left() <= avail.left() + tol and not occupied(QPoint(full.left() - 5, cy)):
        return 'left'
    if r.right() >= avail.right() - tol and not occupied(QPoint(full.right() + 5, cy)):
        return 'right'
    if allow_top is None:
        allow_top = allow_tb
    if allow_bottom is None:
        allow_bottom = allow_tb
    if allow_top and r.top() <= avail.top() + tol and not occupied(QPoint(cx, full.top() - 5)):
        return 'top'
    if allow_bottom and r.bottom() >= avail.bottom() + int((r.height() if body_h is None else body_h) * PEEK_BOTTOM_PAST) and not occupied(QPoint(cx, full.bottom() + 5)):
        return 'bottom'
    return ''


def peek_place(side, r, avail, content=None):
    """躲边时精灵左上角（全局坐标）该放哪（纯函数）。画布的墙那一边贴着可用区域的边：
    下边 = 精灵底边正好是任务栏上沿（一点都不压任务栏），上边 = 精灵顶边贴屏幕可用区域顶；
    content = 立绘里有人那块（精灵坐标），上/下边时横向保证人整个在屏幕里。"""
    if side == 'left':
        return QPoint(avail.left() - 1, min(max(r.y(), avail.top() + 4), avail.bottom() + 1 - r.height()))
    if side == 'right':
        return QPoint(avail.right() + 2 - r.width(), min(max(r.y(), avail.top() + 4), avail.bottom() + 1 - r.height()))
    c = content if content is not None else QRect(0, 0, r.width(), r.height())
    x = min(max(r.x(), avail.left() - c.left()), avail.right() + 1 - c.right() - 1)
    y = avail.top() if side == 'top' else avail.bottom() + 1 - r.height()
    return QPoint(x, y)


def screen_map(names):
    """屏幕名 -> screen_1 / screen_2 …（按 Qt 给的顺序）。屏幕名里可能带显示器型号，诊断文件里不放原名。"""
    out = {}
    for n in names:
        if n not in out:
            out[n] = f'screen_{len(out) + 1}'
    return out


def screen_label(scr):
    try:
        return screen_map([s.name() for s in QGuiApplication.screens()]).get(scr.name(), 'screen_?')
    except Exception:
        return 'screen_?'


def ext_label(ext):
    """日志里记的扩展名：认识的原样记（.png），不认识的统一记 other（扩展名本身也可能带个人信息）。"""
    ext = (ext or '').lower().lstrip('.')
    return '.' + ext if ext in PL.EXT2CAT else 'other'


# 诊断文件里只放这些设置（固定白名单；以后加了新设置，默认不会被导出）
DIAG_FIELDS = ('scale', 'scale_legs', 'legs', 'on_top', 'muted', 'volume', 'time_greet', 'return_greet', 'remind_water', 'water_min',
               'remind_stand', 'stand_min', 'micro', 'fullscreen_hide', 'edge_peek', 'pomo_focus', 'pomo_break',
               'show_timer_badge', 'first_run_done', 'peek_side', 'storage_notice')


def diag_settings(st, smap):
    out = {k: st.get(k) for k in DIAG_FIELDS if k in st}
    out['quiet_active'] = time.time() < float(st.get('quiet_until', 0) or 0)
    pos = st.get('pos') or {}
    out['pos'] = {smap.get(n, 'screen_other'): v for n, v in pos.items()}
    out['last_screen'] = smap.get(st.get('last_screen', ''), 'screen_other' if st.get('last_screen') else '')
    return out


def redact_text(text, smap):
    """日志文字再过一遍：屏幕名换编号，像路径的东西（盘符、\\\\server、/home、/Users）换成 <path>。"""
    import re
    for name, lab in sorted(smap.items(), key=lambda kv: -len(kv[0])):
        if name and len(name) >= 3:
            text = text.replace(name, lab)
    text = re.sub(r'(?i)\b[a-z]:[\\/][^\s"\']*', '<path>', text)
    text = re.sub(r'\\\\[^\s"\']+', '<path>', text)
    text = re.sub(r'(?<![\w.])/(?:home|Users|root|tmp|mnt|media|var|private)/[^\s"\']*', '<path>', text)
    return text


# ======================= 精灵帧 =======================
class Sprites:
    """按当前大小缓存缩放好的帧：待机帧优先常驻，其他片段用到才解码（LRU，按字节预算）。"""

    def __init__(self, legs=False):
        self.set_assets(legs)

    def set_assets(self, legs):
        """只保留当前素材集；切换后所有帧、遮罩、躲边和 retract 缓存重读。"""
        suffix = '_legs' if legs else ''
        self.spr = os.path.join(BASE, 'assets', 'sprites' + suffix)
        self.maskd = os.path.join(BASE, 'assets', 'masks' + suffix)
        self.peekd = os.path.join(BASE, 'assets', 'peek' + suffix)
        with open(os.path.join(self.spr, 'manifest.json'), encoding='utf-8') as f:
            self.man = json.load(f)
        self.w, self.h, self.fps = self.man['w'], self.man['h'], self.man['fps']
        self.fk = max(1, round(self.fps / 12))      # v0.3.9：EXPR 帧号倍率（飘着 12fps=1，长脚 24fps=2）
        self.padx = self.man.get('padx', 0)
        # v0.3.8：头/上半身框的位置可单独给（长脚重画后按实际画面量出来）；没给就沿用 (padx, 0)，飘着模式两者都没有 = (0, 0)
        self.upper_x = self.man.get('upper_x', self.padx)
        self.upper_y = self.man.get('upper_y', 0)
        self.upper_w = self.man.get('upper_w', self.w)
        self.upper_h = self.man.get('upper_h', self.h)
        self.fx_src = {k: (QImage(os.path.join(FXD, v['img'])), v['at']) for k, v in self.man['fx'].items()}
        if hasattr(self, '_retract'):
            del self._retract
        self.set_scale(getattr(self, 's', 1.0))

    def set_scale(self, s):
        self.s = s
        self.sw, self.sh = max(1, round(self.w * s)), max(1, round(self.h * s))
        self.ux = self.upper_x * s
        self.uy = self.upper_y * s
        self.uw, self.uh = max(1, round(self.upper_w * s)), max(1, round(self.upper_h * s))
        self.cache = OrderedDict()
        self.bytes = 0
        fb = self.sw * self.sh * 4
        idle_b = fb * self.n('idle')
        k = getattr(self, 'fk', 1)
        self.budget = idle_b + max(20 * 2**20 * k, 26 * k * fb)    # 待机全常驻 + 至少 26 帧（24fps 时 52 帧）给其他片段，停留循环不会反复解码
        self.masks = {}
        self.peek_cache = {}
        self.fx = {k: (im.scaled(max(1, round(im.width() * s)), max(1, round(im.height() * s)),
                                 Qt.KeepAspectRatio, Qt.SmoothTransformation), (at[0] * s, at[1] * s))
                   for k, (im, at) in self.fx_src.items()}

    def n(self, name):
        return self.man['anims'][name]['n']

    def frame(self, name, i):
        k = (name, i)
        im = self.cache.get(k)
        if im is not None:
            self.cache.move_to_end(k)
            return im
        im = QImage(os.path.join(self.spr, name, f'{i:03d}.webp'))
        if im.isNull():
            raise RuntimeError(f'读不到精灵帧 {name}/{i:03d}.webp（缺少 Qt 的 webp 插件？）')
        im = im.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        if self.s != 1.0:
            im = im.scaled(self.sw, self.sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.cache[k] = im
        self.bytes += im.sizeInBytes()
        while self.bytes > self.budget and len(self.cache) > 1:
            victim = next((kk for kk in self.cache if kk[0] != 'idle'), None) or next(iter(self.cache))
            if victim == k:
                break
            self.bytes -= self.cache.pop(victim).sizeInBytes()
        return im

    def drop_non_idle(self):
        for k in [k for k in self.cache if k[0] != 'idle']:
            self.bytes -= self.cache.pop(k).sizeInBytes()

    def peek_retract(self, side):
        """上/下边「害羞」时整张图往屏幕外缩回去多少像素（当前大小）"""
        if not hasattr(self, '_retract'):
            self._retract = dict(PEEK_RETRACT)
            try:
                with open(os.path.join(self.peekd, 'peek.json'), encoding='utf-8') as f:
                    self._retract.update({k: float(v) for k, v in json.load(f).get('retract', {}).items() if k in PEEK_TB})
            except Exception:
                pass
        return round(self._retract.get(side, 0) * self.s)

    def peek_shifted(self, side, frac):
        """上/下边：探头图往屏幕外缩回 frac（0=探头，1=害羞）后的样子，墙外的部分裁掉"""
        src = self.peek_img('tilt', side)
        if src is None:
            return None
        d = round(self.peek_retract(side) * frac) * (-1 if side == 'top' else 1)
        if d == 0:
            return src
        im = QImage(src.size(), QImage.Format_ARGB32_Premultiplied); im.fill(Qt.transparent)
        p = QPainter(im); p.setCompositionMode(QPainter.CompositionMode_Source); p.drawImage(0, d, src); p.end()
        return im

    def peek_img(self, pose, side):
        """当前素材集的躲边立绘（屏幕边 = 画布右/左/上/下边），按当前大小缩放；读不到返回 None。
        上/下边只有 tilt_top / tilt_bottom 一张图，害羞那张由它往屏幕外缩回去得到。"""
        k = (pose, side)
        if k not in self.peek_cache:
            if side in PEEK_TB and pose == 'shy':
                self.peek_cache[k] = self.peek_shifted(side, 1.0)
                return self.peek_cache[k]
            im = QImage(os.path.join(self.peekd, f'{pose}_{side}.png'))
            if im.isNull():
                self.peek_cache[k] = None
            else:
                im = im.convertToFormat(QImage.Format_ARGB32_Premultiplied)
                if (im.width(), im.height()) != (self.sw, self.sh):
                    im = im.scaled(self.sw, self.sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                self.peek_cache[k] = im
        return self.peek_cache[k]

    def peek_mask(self, pose, side):
        key = ('peek', pose, side)
        r = self.masks.get(key)
        if r is None:
            im = self.peek_img(pose, side)
            r = QRegion(QBitmap.fromImage(im.createAlphaMask())) if im is not None else QRegion(0, 0, self.sw, self.sh)
            self.masks[key] = r
        return r

    def mask(self, name):
        """该动画所有帧 alpha 的并集（make_assets.py 预先生成），缩放后当窗口遮罩：每段动画只 setMask 一次。"""
        r = self.masks.get(name)
        if r is None:
            m = QImage(os.path.join(self.maskd, name + '.png'))
            if m.isNull():
                r = QRegion(0, 0, self.sw, self.sh)
            else:
                m = m.convertToFormat(QImage.Format_ARGB32).scaled(self.sw, self.sh, Qt.IgnoreAspectRatio, Qt.FastTransformation)
                r = QRegion(QBitmap.fromImage(m.createAlphaMask()))
            self.masks[name] = r
        return r


# ======================= 计时器（关掉面板也在跑） =======================
class PetTimer:
    def __init__(self, st):
        self.st = st
        self.mode = 'pomo'      # pomo / count
        self.running = False
        self.phase = 'focus'
        self.acc = 0.0
        self.t0 = 0.0
        self.pomos = 0
        self.next_ms = 1800

    def elapsed(self):
        return self.acc + (time.monotonic() - self.t0 if self.running else 0)

    def phase_len(self):
        return 60 * (self.st['pomo_focus'] if self.phase == 'focus' else self.st['pomo_break'])

    def shown(self):
        """面板/脚边显示的秒数：番茄钟显示剩余，正计时显示已过"""
        if self.mode == 'pomo':
            return max(0, self.phase_len() - self.elapsed())
        return self.elapsed()

    def start(self):
        if not self.running:
            self.running, self.t0 = True, time.monotonic()

    def pause(self):
        if self.running:
            self.acc, self.running = self.elapsed(), False

    def reset(self):
        self.running, self.acc, self.phase, self.next_ms = False, 0.0, 'focus', 1800

    def set_mode(self, m):
        if m != self.mode:
            self.reset(); self.mode = m

    def active(self):
        return self.running or self.acc > 0

    def tick(self):
        """返回需要她说的台词类别（或 None）"""
        if not self.running:
            return None
        e = self.elapsed()
        if self.mode == 'pomo':
            if e >= self.phase_len():
                if self.phase == 'focus':
                    self.pomos += 1
                    self.phase, self.acc, self.t0 = 'break', 0.0, time.monotonic()
                    return 'pomo_focus_end'
                self.phase, self.acc, self.t0 = 'focus', 0.0, time.monotonic()
                return 'pomo_break_end'
        else:
            if e >= self.next_ms:
                ms = self.next_ms
                self.next_ms += 1800
                return 'count_120' if ms % 7200 == 0 else 'count_30'
        return None

    def label(self):
        s = int(self.shown())
        t = f'{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}' if s >= 3600 else f'{s // 60:02d}:{s % 60:02d}'
        if self.mode == 'count':
            return '计时 ' + t
        return ('专注 ' if self.phase == 'focus' else '休息 ') + t


class TimerPanel(QWidget):
    def __init__(self, pet):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint | Qt.WindowTitleHint)
        self.pet, self.t = pet, pet.timer
        self.setWindowTitle('掌柜台桌宠 · 计时器')
        self.setWindowIcon(pet.icon)
        self.setStyleSheet('QWidget{background:#f6f7ff;color:#283a82;font-size:13px}'
                           'QPushButton{background:#e4e8ff;border:1px solid #9aa6e0;border-radius:8px;padding:5px 12px}'
                           'QPushButton:hover{background:#d6dcff}')
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        self.r_pomo, self.r_count = QRadioButton('番茄钟'), QRadioButton('正计时')
        g = QButtonGroup(self); g.addButton(self.r_pomo); g.addButton(self.r_count)
        self.r_pomo.setChecked(self.t.mode == 'pomo'); self.r_count.setChecked(self.t.mode == 'count')
        self.r_pomo.toggled.connect(lambda on: on and self._mode('pomo'))
        self.r_count.toggled.connect(lambda on: on and self._mode('count'))
        row.addWidget(self.r_pomo); row.addWidget(self.r_count); row.addStretch(1)
        v.addLayout(row)
        self.big = QLabel(); self.big.setAlignment(Qt.AlignCenter)
        self.big.setStyleSheet('font-size:34px;font-weight:bold;color:#283a82;padding:6px')
        v.addWidget(self.big)
        self.status = QLabel(); self.status.setAlignment(Qt.AlignCenter)
        v.addWidget(self.status)
        row2 = QHBoxLayout()
        self.sf, self.sb = QSpinBox(), QSpinBox()
        self.sf.setRange(1, 180); self.sb.setRange(1, 60)
        self.sf.setValue(pet.st['pomo_focus']); self.sb.setValue(pet.st['pomo_break'])
        self.sf.setSuffix(' 分'); self.sb.setSuffix(' 分')
        self.sf.valueChanged.connect(lambda x: self._set('pomo_focus', x))
        self.sb.valueChanged.connect(lambda x: self._set('pomo_break', x))
        row2.addWidget(QLabel('专注')); row2.addWidget(self.sf); row2.addWidget(QLabel('休息')); row2.addWidget(self.sb)
        self.pomo_row = QWidget(); self.pomo_row.setLayout(row2)
        v.addWidget(self.pomo_row)
        row3 = QHBoxLayout()
        self.b_go, self.b_reset = QPushButton('开始'), QPushButton('重置')
        self.b_go.clicked.connect(self._go); self.b_reset.clicked.connect(self._reset)
        row3.addWidget(self.b_go); row3.addWidget(self.b_reset)
        v.addLayout(row3)
        self.cb = QCheckBox('在她脚边显示时间')
        self.cb.setChecked(pet.st['show_timer_badge'])
        self.cb.toggled.connect(lambda on: self._set('show_timer_badge', on))
        v.addWidget(self.cb)
        tip = QLabel('关掉这个小窗也会继续计时'); tip.setStyleSheet('color:#7a84b8;font-size:11px')
        tip.setAlignment(Qt.AlignCenter); v.addWidget(tip)
        self.setFixedWidth(260)
        self.refresh()

    def _set(self, k, x):
        self.pet.st[k] = x; self.pet.save_later(); self.refresh()

    def _mode(self, m):
        self.t.set_mode(m); self.refresh()

    def _go(self):
        if self.t.running:
            self.t.pause(); self.pet.log('timer pause')
        else:
            first = not self.t.active()
            self.t.start(); self.pet.log('timer start', self.t.mode)
            if first and self.t.mode == 'pomo':
                self.pet.say('pomo_start')
        self.refresh()

    def _reset(self):
        self.t.reset(); self.refresh()

    def refresh(self):
        self.big.setText(self.t.label().split(' ')[1])
        if self.t.mode == 'pomo':
            st = ('专注中' if self.t.phase == 'focus' else '休息中') if self.t.running else ('已暂停' if self.t.active() else '准备好了吗？')
            st += f' · 今天完成 {self.t.pomos} 个'
        else:
            st = '计时中' if self.t.running else ('已暂停' if self.t.active() else '点开始计时')
        self.status.setText(st)
        self.pomo_row.setVisible(self.t.mode == 'pomo')
        self.b_go.setText('暂停' if self.t.running else ('继续' if self.t.active() else '开始'))
        self.pet.update_badge()


# ======================= 桌宠本体 =======================
class Pet(QWidget):
    def __init__(self, conf, log, st, lock):
        self.st, self.log, self.conf, self.lock = st, log, conf, lock     # conf 可能是 None（只用内存）
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint
        if st['on_top']:
            flags |= Qt.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAcceptDrops(True)
        self.setWindowTitle('掌柜台桌宠')
        self.icon = QIcon(ICON)
        self.tray_icon = QIcon(ICON_ICO) if os.path.exists(ICON_ICO) else self.icon
        if self.tray_icon.isNull():
            self.tray_icon = self.icon
        self.setWindowIcon(self.icon)
        order = [x.strip() for x in ENV('ZHANGGUI_PET_ORDER', '').split(',') if x.strip()]
        self.brain = LocalBrain(order)
        self.voice = P.Voice(VOICED, conf, log)
        self.timer = PetTimer(st)
        self.panel = None
        self.sp = Sprites(st['legs'])
        # 播放状态
        self.mode, self.expr = 'idle', None
        self.seg = ('idle', 0, self.sp.n('idle'))
        self.anim, self.idx, self.dir = 'idle', 0, 1
        self.hold_until = 0.0
        self.hold_override = None
        self.prev = None; self.prev_anim = None; self.fade = None    # fade = (开始时间, 时长秒)
        self.settle_t0 = None; self.fast_pending = False
        self.last_img = None; self.cur_img = None
        self.bubble = None                  # (text, until)
        self.fx_on = []                     # [(kind, t0, t1)]
        self.hearts = []                    # [(t0, x)] 摸头时冒的小爱心
        self.last_touch = time.time()
        self.clicks = []
        self.press_pos = None; self.dragging = False; self.patting = False; self.zone = 'body'
        self.angle = 0.0; self.vx = 0.0; self.last_move = None
        self.dozing = False
        self.user_hidden = False; self.fs_hidden = False
        self.peek = st['peek_side'] if st['edge_peek'] else ''
        if self.peek == 'top' and not PEEK_ENABLE_TOP:   # 发布版关掉上方探头时，旧设置里的 top 清掉
            self.peek = ''
        self.peek_out = False; self.peek_away_t = 0.0; self.peek_armed = False
        self.peek_fade = None               # (开始时间, 上一张图, 上一张的遮罩键)：害羞 <-> 探头 的淡入淡出
        self.peek_drawn = None              # 上次画出来的躲边状态（没变就不重画，省 CPU）
        self.tray_ok = False                # 托盘图标确实在：才允许“完全藏起来”
        self.hide_pending = False
        self.press_t = 0.0                  # 这次按下的时间（丢失鼠标抓取的兜底检查用）
        self.fs_aux = []                    # 全屏躲起来时一起藏起来的小窗（计时器、关于页），退出全屏只恢复这些
        self.fs_aux_hidden = False
        self.fs_missed = None               # 全屏期间到点的计时事件：退出全屏后最多补说一次
        self.pending_ev = None              # 同一秒被更重要的事挤掉的一次性主动事件：(优先级, 类别, 主动?, 时间)，最多留一个
        self.fs_err_t = 0.0; self.fs_err_n = 0
        self.il = P.integrity_level()
        self._bs = _BUILD_SIG ^ P.ASSET_TAG        # 资源标签自检（为 0 即匹配）
        self.mask_key = None
        self.last_chrome = None
        self.bubble_cache = None
        self.idle_since = time.time()
        self.badge_text = None
        self.font = QFont()
        self.font.setFamilies(['Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC',
                               'WenQuanYi Micro Hei', 'sans-serif'])
        self.font.setBold(True)
        self.small = QFont(self.font); self.small.setPixelSize(13)
        # v0.3.9-nolegs：飘着/长脚共用同一个立绘大小（长脚的上半身和飘着的立绘像素一样大）。
        # 旧设置两套各记一个：以当前模式那套为准，这样升级后眼前的大小不变。
        s0 = st['scale_legs' if st['legs'] else 'scale']
        st['scale'] = st['scale_legs'] = s0
        self.apply_scale(s0, keep_anchor=False)
        # 计时器们
        self.anim_timer = QTimer(self); self.anim_timer.timeout.connect(self.tick)
        self.anim_timer.start(int(1000 / self.sp.fps))
        self.brain_timer = QTimer(self); self.brain_timer.timeout.connect(self.brain_tick); self.brain_timer.start(1000)
        self.press_timer = QTimer(self); self.press_timer.setSingleShot(True); self.press_timer.timeout.connect(self.start_longpat)
        self.peek_timer = QTimer(self); self.peek_timer.timeout.connect(self.peek_poll)
        self.save_timer = QTimer(self); self.save_timer.setSingleShot(True); self.save_timer.timeout.connect(self.st.save)
        self.scale_timer = QTimer(self); self.scale_timer.setSingleShot(True)
        self.scale_timer.timeout.connect(lambda: self.set_scale(self.pending_scale))
        # v0.3.5：用户调完大小（最后一次变化后约 1 秒）问一句「这个大小可以吗？」；开机恢复大小不走这里
        self.size_timer = QTimer(self); self.size_timer.setSingleShot(True)
        self.size_timer.timeout.connect(self.ask_size)
        self.slide = QPropertyAnimation(self, b'pos', self); self.slide.setDuration(260)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        self.slide.finished.connect(self.save_position)
        # 主动行为的状态
        self.t_start = time.time()
        self.away = False; self.away_start = 0.0
        self.session_start = time.time()
        self.last_stand = time.time(); self.last_water = time.time()
        self.was_quiet = self.quiet()
        self.greeted = set()
        slot = PL.current_slot()
        if slot:
            self.greeted.add(datetime.date.today().isoformat() + slot)   # 开机问候已经覆盖当前时段
        self.next_micro = time.time() + self.micro_gap()
        self.restore_position()
        self.compose()
        self.tray = None
        self.setup_tray()
        app = QApplication.instance()
        app.screenAdded.connect(lambda *_: QTimer.singleShot(800, self.ensure_visible))
        app.screenRemoved.connect(lambda *_: QTimer.singleShot(800, self.ensure_visible))
        log(f'start v{VERSION}', P.system_summary(), f'Qt {qVersion()}', f'scale {self.sp.s:.2f}',
            'voice', 'yes' if self.voice.available() else 'none')

    # ---------- 尺寸 / 位置 ----------
    def apply_scale(self, s, keep_anchor=True):
        a = self.anchor() if keep_anchor else None
        self.sp.set_scale(s)
        self.font.setPixelSize(16 if s >= 0.6 else 14)
        sw, sh = self.sp.sw, self.sp.sh
        self.W = max(sw + 40, 340)
        self.setFixedSize(self.W, sh + BUBBLE_H)
        self.ox, self.oy = (self.W - sw) // 2, BUBBLE_H
        self.prev = None; self.fade = None; self.settle_t0 = None; self.last_img = None; self.mask_key = None
        self.peek_fade = None; self.peek_drawn = None
        if a is not None:
            self.set_anchor(a)

    def set_scale(self, s):
        s = round(max(0.2, min(1.5, s)), 2)
        if abs(s - self.sp.s) < 0.005:
            return
        self.apply_scale(s)
        self.st['scale'] = self.st['scale_legs'] = s       # 两种模式共用一个大小
        if self.peek:
            self.apply_peek(self.peek, animate=False)
        else:
            self.ensure_visible()
        self.compose()
        self.save_position()
        self.log('scale', s)
        self.size_timer.start(SIZE_ASK_MS)          # 连续拖滑块会一直重新计时，停手后只问一次

    def set_legs(self, legs):
        if legs == self.st['legs']:
            return
        # 先让尚未生效的滑块值落地，切换后沿用同一个大小。
        if self.scale_timer.isActive():
            self.scale_timer.stop()
            self.set_scale(self.pending_scale)
        self.size_timer.stop()
        a, side = self.anchor(), self.peek
        self.cancel_interaction()
        self.leave_peek()
        old_k = self.sp.fk
        self.sp.set_assets(legs)
        if self.sp.fk != old_k:                        # v0.3.9：长脚 24fps / 飘着 12fps，切换时把当前片段帧号按比例换算，节拍也跟着换
            r = self.sp.fk / old_k
            self.seg = (self.seg[0], int(self.seg[1] * r), int(self.seg[2] * r))
            self.idx = int(self.idx * r)
            if self.anim_timer.isActive():
                self.anim_timer.setInterval(250 if self.away else int(1000 / self.sp.fps))
        self.st['legs'] = legs
        # 大小不变：立绘按同一比例显示，脚底中心钉住原位——出腿时整个人往上长出腿，收腿时落回原来的位置，不会忽大忽小。
        self.apply_scale(self.sp.s, keep_anchor=False)
        self.st['scale'] = self.st['scale_legs'] = self.sp.s
        self.set_anchor(a)
        if side:
            self.apply_peek(side, animate=False)
        self.ensure_visible()
        self.last_chrome = None; self.bubble_cache = None
        self.compose()
        self.save_position()
        self.log('legs', legs)

    def ask_size(self):
        """调完大小后问一句：和其他主动台词同样守规矩——安静模式、藏起来/全屏躲开时不说，冷却中不说，正被拖着/摸着也不说。"""
        if self.dragging or self.patting or self.press_pos is not None:
            return None
        return self.say('size', proactive=True, strict=True)

    def anchor(self):
        """她脚底中点的全局坐标"""
        return QPoint(self.x() + self.ox + self.sp.sw // 2, self.y() + self.oy + self.sp.sh)

    def set_anchor(self, a):
        self.move(a.x() - self.ox - self.sp.sw // 2, a.y() - self.oy - self.sp.sh)

    def sprite_rect(self, pos=None):
        p = pos or self.pos()
        return QRect(p.x() + self.ox, p.y() + self.oy, self.sp.sw, self.sp.sh)

    def screen_of(self, pt):
        s = QGuiApplication.screenAt(pt)
        if s:
            return s
        best, bd = QGuiApplication.primaryScreen(), 1e18
        for sc in QGuiApplication.screens():
            c = sc.availableGeometry().center()
            d = (c.x() - pt.x()) ** 2 + (c.y() - pt.y()) ** 2
            if d < bd: best, bd = sc, d
        return best

    def restore_position(self):
        scr = next((s for s in QGuiApplication.screens() if s.name() == self.st['last_screen']), None) \
            or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        p = self.st['pos'].get(scr.name())
        if p:
            a = QPoint(round(g.x() + p[0] * g.width()), round(g.y() + p[1] * g.height()))
        else:
            a = QPoint(g.right() - self.sp.sw // 2 - 40, g.bottom() - 4)
        self.set_anchor(a)
        self.ensure_visible()
        if self.peek:
            self.apply_peek(self.peek, animate=False)
        self.log('restore pos', screen_label(scr), 'rel' if p else 'default', 'peek=' + (self.peek or '-'))

    def ensure_visible(self):
        """整个人要在某块屏幕的可用区域里（躲在边上时除外）；屏幕没了就回主屏。"""
        if self.peek:
            g = self.screen_of(self.anchor()).availableGeometry()
            if self.sprite_rect().intersects(g):
                return
            self.leave_peek()
        r = self.sprite_rect()
        scr = self.screen_of(r.center())
        g = scr.availableGeometry()
        x = min(max(r.x(), g.left()), g.right() - r.width() + 1)
        y = min(max(r.y(), g.top() + 10), g.bottom() - r.height() + 1)
        if (x, y) != (r.x(), r.y()):
            self.move(x - self.ox, y - self.oy)
            self.log('ensure_visible moved')

    def save_position(self):
        a = self.anchor()
        scr = self.screen_of(a)
        g = scr.availableGeometry()
        self.st['pos'][scr.name()] = [round((a.x() - g.x()) / max(1, g.width()), 4),
                                      round((a.y() - g.y()) / max(1, g.height()), 4)]
        self.st['last_screen'] = scr.name()
        self.st['peek_side'] = self.peek
        self.save_later()

    def save_later(self):
        self.save_timer.start(600)

    def recenter(self):
        self.hide_pending = False            # 「先藏起来」的 1.4 秒还没到就点了「找回她」：取消那次隐藏
        self.cancel_interaction()
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.leave_peek()
        self.set_anchor(QPoint(g.center().x(), g.center().y() + self.sp.sh // 2))
        self.ensure_visible()
        self.user_hidden = False; self.fs_hidden = False
        self.apply_visibility()
        self.save_position()
        self.say('recenter')

    # ---------- 躲到屏幕边 ----------
    def leave_peek(self):
        if self.peek:
            self.last_img = None               # 别拿躲边立绘去和站姿做交叉淡化（会有重影）
        self.peek = ''; self.peek_out = False; self.peek_fade = None; self.peek_drawn = None
        self.peek_timer.stop()
        self.mask_key = None

    def peek_art_ok(self):
        return bool(self.peek) and self.sp.peek_img('shy', self.peek) is not None and self.sp.peek_img('tilt', self.peek) is not None

    def peek_key(self):
        return ('peek', 'tilt' if self.peek_out else 'shy', self.peek)

    def peek_content(self):
        """当前躲边立绘里“有人”的那块（窗口坐标）"""
        return self.sp.peek_mask('shy', self.peek).boundingRect().united(
            self.sp.peek_mask('tilt', self.peek).boundingRect()).translated(self.ox, self.oy)

    def set_peek_pose(self, out):
        if out == self.peek_out:
            return
        if self.peek_art_ok() and self.last_img is not None:
            self.peek_fade = (time.time(), self.last_img, self.peek_key())
        self.peek_out = out
        self.compose()

    def nearest_side(self):
        """离哪边近就躲哪边；那边接着别的屏幕就换另一边"""
        r = self.sprite_rect()
        g = self.screen_of(r.center()).availableGeometry()
        full = self.screen_of(r.center()).geometry()          # 用整块屏幕的边去看隔壁（任务栏在左/右时也不会误判）
        free_l = not self.occupied(QPoint(full.left() - 5, r.center().y()))
        free_r = not self.occupied(QPoint(full.right() + 5, r.center().y()))
        pref = 'left' if r.center().x() < g.center().x() else 'right'
        if pref == 'left' and not free_l and free_r: return 'right'
        if pref == 'right' and not free_r and free_l: return 'left'
        return pref

    def occupied(self, pt):
        """这个点上有没有屏幕（用来判断「那边还接着别的屏幕」）"""
        return QGuiApplication.screenAt(pt) is not None

    def peek_screen(self):
        """躲边/松手时以哪块屏幕为准：她脚底所在的屏幕（往下拖过任务栏时中心可能已经出了屏幕）"""
        r = self.sprite_rect()
        return self.screen_of(QPoint(r.center().x(), min(r.center().y(), r.top() + r.height() // 3)))

    def edge_side(self):
        """松手时如果贴着屏幕左/右/上边，或往下拖过了任务栏上沿（且那边没有别的屏幕），返回对应的边。
        上方探头由 PEEK_ENABLE_TOP 控制（发布版可关，素材仍保留）。"""
        if not self.st['edge_peek']:
            return ''
        r = self.sprite_rect()
        scr = self.peek_screen()
        tol = max(10, r.width() // 10)
        has = {s: self.sp.peek_img('tilt', s) is not None for s in PEEK_TB}
        return edge_hit(r, scr.availableGeometry(), scr.geometry(), self.occupied, tol,
                        allow_top=PEEK_ENABLE_TOP and has['top'],
                        allow_bottom=has['bottom'], body_h=self.sp.uh)

    def peek_pos(self, side, out=False):
        """新立绘本身就是“贴着墙探出来”的样子：画布的墙那一边正好对齐屏幕可用区域的边（不压任务栏）"""
        r = self.sprite_rect()
        g = self.peek_screen().availableGeometry()
        sw = self.sp.sw
        if self.sp.peek_img('shy', side) is None:              # 没有新立绘（不该发生）：退回老办法，露半个身子
            sx = g.left() - int(sw * 0.5) if side == 'left' else g.right() + 1 - int(sw * 0.5)
            return QPoint(sx - self.ox, self.y())
        c = self.sp.peek_mask('tilt', side).boundingRect() if side in PEEK_TB else None
        p = peek_place(side, r, g, c)
        return QPoint(p.x() - self.ox, p.y() - self.oy)

    def apply_peek(self, side, animate=True, out=False):
        self.peek, self.peek_out = side, out
        self.peek_fade = None; self.peek_drawn = None; self.mask_key = None
        if not out:
            self.peek_armed = False          # 鼠标先离开一次，才会再探头（刚松手时光标就在她身上）
        target = self.peek_pos(side, out)
        if animate:
            self.slide.stop(); self.slide.setStartValue(self.pos()); self.slide.setEndValue(target); self.slide.start()
        else:
            self.move(target)
        self.peek_timer.start(100)

    def peek_poll(self):
        if not self.peek or self.dragging or self.press_pos is not None:
            if not self.peek: self.peek_timer.stop()
            return
        if self.slide.state() == QPropertyAnimation.Running:
            return
        c = QCursor.pos()
        g = self.peek_screen().availableGeometry()
        body = self.peek_content().translated(self.x(), self.y()).intersected(g)
        near = body.adjusted(-40, -40, 40, 40).contains(c)
        now = time.time()
        if not self.peek_out:
            if not near:
                self.peek_armed = True
            elif self.peek_armed:
                self.set_peek_pose(True)          # 鼠标靠近：从害羞变成探头（淡入淡出，位置不动）
                self.peek_away_t = now
                if random.random() < 0.5:
                    self.say('peek_found', proactive=True, strict=True, expr=False)
        else:
            if near:
                self.peek_away_t = now
            elif now - self.peek_away_t > 2.5 and not self.bubble:
                self.set_peek_pose(False)

    # ---------- 显示 / 隐藏 ----------
    def apply_visibility(self):
        vis = not self.user_hidden and not self.fs_hidden
        if vis and not self.isVisible():
            self.cancel_interaction()
            # 重新出来：位置、遮罩、画面都重新算一遍（藏着的时候屏幕可能变了）
            if self.peek:
                self.apply_peek(self.peek, animate=False, out=False)
            else:
                self.ensure_visible()
            self.mask_key = None; self.last_chrome = None; self.bubble_cache = None
            self.show(); self.anim_timer.start(250 if self.away else int(1000 / self.sp.fps))
            self.compose()
            self.log('shown')
        elif not vis and self.isVisible():
            self.cancel_interaction()
            self.hide(); self.anim_timer.stop(); self.voice.stop()
            self.log('hidden', 'fullscreen' if self.fs_hidden else 'user')
        self.sync_fs_aux()

    def sync_fs_aux(self):
        """全屏躲起来时，计时器小窗和关于页也一起藏；退出全屏只把当时开着的那些放回来，
        并把全屏期间到点的计时提醒补说一次。"""
        if self.fs_hidden and not self.fs_aux_hidden:
            self.fs_aux_hidden = True
            self.fs_aux = []
            for w in (self.panel, getattr(self, 'about_box', None)):
                if w is not None and w.isVisible():
                    w.hide(); self.fs_aux.append(w)
            if self.fs_aux:
                self.log('fullscreen: aux windows hidden', len(self.fs_aux))
        elif not self.fs_hidden and self.fs_aux_hidden:
            self.fs_aux_hidden = False
            for w in self.fs_aux:
                if not self.user_hidden:
                    w.show()
            self.fs_aux = []
            if self.fs_missed:
                self.pending_ev = (0, self.fs_missed, False, time.time())   # 由 brain_tick 补说一次（只说最后一个）
                self.log('fullscreen: missed timer event queued', self.fs_missed)
                self.fs_missed = None

    def cancel_interaction(self):
        """把“正在按着/拖着/摸着”的状态全部清掉：藏起来、丢了鼠标抓取、找回她时调用。"""
        self.press_timer.stop()
        if self.slide.state() == QPropertyAnimation.Running:
            self.slide.stop()
        was = (self.press_pos is not None, self.dragging, self.patting)
        self.press_pos = None; self.last_move = None
        self.patting = False; self.dragging = False
        self.vx = 0.0; self.angle = 0.0
        if any(was):
            self.mask_key = None
            self.log('interaction cancelled', 'drag' if was[1] else ('pat' if was[2] else 'press'))
        return any(was)

    def check_grab(self):
        """兜底：按下之后系统里左键其实已经松开了（松手的消息被别的窗口/系统吃掉），就当这次操作取消。"""
        if self.press_pos is None or time.time() - self.press_t < 0.3:
            return False
        if QGuiApplication.mouseButtons() & Qt.LeftButton:
            return False
        was_drag = self.dragging
        self.cancel_interaction()
        if was_drag:
            self.ensure_visible(); self.save_position()
        return True

    def hideEvent(self, e):
        self.cancel_interaction()
        super().hideEvent(e)

    def set_on_top(self, on):
        self.st['on_top'] = on; self.save_later()
        was = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        if was:
            self.show()
        self.log('on_top', on)

    # ---------- 播放 ----------
    def eseg(self, seg):
        """EXPR 里的 12fps 帧号 -> 当前素材帧号（长脚 24fps 时 ×2）。"""
        k = self.sp.fk
        return seg if k == 1 else (seg[0], seg[1] * k, seg[2] * k)

    def start_seg(self, mode, seg):
        now = time.time()
        jump = (self.mode, mode) not in CONTINUOUS and not (self.mode == mode == 'idle')
        if self.last_img is not None:
            self.prev = self.last_img
            self.prev_anim = self.anim
            pose = seg[0] in POSE_ANIMS or self.anim in POSE_ANIMS
            self.fade = (now, FADE_POSE if (pose and jump) else FADE_CUT)
            if jump and not self.peek:
                self.settle_t0 = now          # 换表情/换姿势：轻轻“落定”一下，让切换读起来像动作
        self.mode, self.seg = mode, seg
        self.anim, self.idx, self.dir = seg[0], seg[1], 1

    def play_expr(self, expr, hold=None):
        self.expr = expr
        self.hold_override = hold
        self.start_seg('enter', self.eseg(EXPR[expr]['enter']))

    def go_idle(self):
        self.idle_since = time.time()
        self.expr = None
        self.start_seg('idle', ('idle', 0, self.sp.n('idle')))

    def tick(self):
        now = time.time()
        if self.press_pos is not None:
            self.check_grab()
        anim, a, b = self.seg
        b = min(b, self.sp.n(anim))
        if self.mode == 'hold':
            if a + 1 < b:
                nxt = self.idx + self.dir
                if nxt >= b or nxt < a:
                    self.dir = -self.dir; nxt = self.idx + self.dir
                self.idx = nxt
            if now >= self.hold_until and not self.patting:
                lv = EXPR[self.expr]['leave']
                self.start_seg('leave', self.eseg(lv)) if lv else self.go_idle()
        else:
            self.idx += self.sp.fk if (self.away and self.mode == 'idle') else 1   # 离开省电模式 250ms 一拍，24fps 素材一次走 2 帧，速度和以前一样
            if self.idx >= b:
                if self.mode == 'idle':
                    self.idx = a
                elif self.mode == 'enter':
                    if self.hold_override is not None:
                        self.hold_until = now + self.hold_override
                    else:
                        self.hold_until = max(self.last_touch + HOLD_SECS, now + 1.0)
                    mh = EXPR[self.expr].get('max_hold')
                    if mh is not None:                  # 挥手这种动作：停一会儿就回待机，不一直挥
                        self.hold_until = min(self.hold_until, now + mh)
                    self.start_seg('hold', self.eseg(EXPR[self.expr]['hold']))
                else:
                    self.go_idle()
        if self.bubble and now > self.bubble[1]:
            self.bubble = None
        self.fx_on = [f for f in self.fx_on if f[2] > now]
        if self.patting and (not self.hearts or now - self.hearts[-1][0] > 0.45):
            self.hearts.append((now, random.uniform(0.32, 0.68)))
        self.hearts = [h for h in self.hearts if now - h[0] < 1.3]
        # 拖动时轻轻摆动（按横向速度），松手后回正
        target = max(-9.0, min(9.0, -self.vx * 0.5)) if self.dragging else 0.0
        self.angle += (target - self.angle) * 0.35
        self.vx *= 0.5
        if abs(self.angle) < 0.15 and not self.dragging:
            self.angle = 0.0
        self.compose()

    def compose_peek(self):
        k = self.peek_key()
        cur = self.sp.peek_img(k[1], k[2])
        masks = (k,)
        f = self.peek_fade
        if f is not None:
            t = (time.time() - f[0]) / PEEK_FADE
            if t >= 1.0 or f[2] == k or f[1].size() != cur.size():
                self.peek_fade = None
            elif k[2] in PEEK_TB:                           # 上/下边：不淡化，整张图滑出来/缩回去
                e = t * t * (3 - 2 * t)
                cur = self.sp.peek_shifted(k[2], (1 - e) if k[1] == 'tilt' else e)
                masks = (k, f[2])
                QTimer.singleShot(16, self.compose)
            else:
                img = scaled_copy(f[1], 1 - t)
                p = QPainter(img)
                p.setCompositionMode(QPainter.CompositionMode_Plus)
                p.drawImage(0, 0, scaled_copy(cur, t))
                p.end()
                cur = img
                masks = (k, f[2])
                QTimer.singleShot(16, self.compose)          # 150ms 的淡化不受 12fps 动画节拍限制
        return cur, masks

    def compose(self):
        sp = self.sp
        if self.peek and self.peek_art_ok():
            state = (self.peek_key(), self.peek_fade is not None)
            if state == self.peek_drawn and self.peek_fade is None and self.cur_img is not None:
                cur, masks = self.cur_img, (self.peek_key(),)      # 立绘没变：不重做图
            else:
                cur, masks = self.compose_peek()
            self.peek_drawn = (self.peek_key(), self.peek_fade is not None)
            self.last_img = cur
            self.cur_img = cur
            self.update_mask(masks)
            chrome = (self.bubble, self.bubble_rect().getRect() if self.bubble else None, self.badge_text, self.pos().toTuple(),
                      bool(self.fx_on), bool(self.hearts), self.angle != 0.0, state)
            if chrome != self.last_chrome or chrome[4] or chrome[5] or chrome[6] or self.peek_fade is not None:
                self.update()
            self.last_chrome = chrome
            return
        self.peek_drawn = None
        cur = sp.frame(self.anim, min(self.idx, sp.n(self.anim) - 1))
        masks = (self.anim,)
        now = time.time()
        busy = False
        if self.fade is not None and self.prev is not None:
            t = (now - self.fade[0]) / self.fade[1]
            if t >= 1.0 or self.prev.size() != cur.size():
                self.fade = None; self.prev = None
            else:
                t = max(0.0, t)
                img = scaled_copy(self.prev, 1 - t)
                p = QPainter(img)
                p.setCompositionMode(QPainter.CompositionMode_Plus)
                p.drawImage(0, 0, scaled_copy(cur, t))
                p.end()
                cur = img
                masks = (self.anim, self.prev_anim)
                busy = True
        if self.settle_t0 is not None:
            k = settle_scale(now - self.settle_t0)
            if k is None:
                self.settle_t0 = None
            else:
                cur = squash_y(cur, k)
                busy = True
        if busy and not self.fast_pending:            # 淡化/落定期间约 60fps 重画，不等 12fps 节拍
            self.fast_pending = True
            QTimer.singleShot(FAST_MS, self._fast_compose)
        self.last_img = cur
        self.cur_img = cur
        self.update_mask(masks)
        # 只有角色在动时，只重画角色那块；气泡/特效/摆动变化时才整窗重画（省 CPU）
        chrome = (self.bubble, self.bubble_rect().getRect() if self.bubble else None, self.badge_text, self.pos().toTuple() if self.peek else None,
                  bool(self.fx_on), bool(self.hearts), self.angle != 0.0)
        if chrome == self.last_chrome and not chrome[4] and not chrome[5] and not chrome[6]:
            self.update(self.sprite_local())
        else:
            self.update()
        self.last_chrome = chrome

    def _fast_compose(self):
        self.fast_pending = False
        if self.isVisible():
            self.compose()

    def update_mask(self, masks):
        if NOMASK:
            return
        now = time.time()
        fxk = tuple(sorted({k for k, t0, t1 in self.fx_on if now >= t0}))
        br = self.bubble_rect() if self.bubble else None
        key = (masks, None if br is None else br.getRect(), fxk, bool(self.hearts) or self.patting,
               self.angle != 0.0, self.badge_rect().getRect() if self.badge_text is not None else None, self.sp.sw)
        if key == self.mask_key:
            return
        self.mask_key = key
        if self.angle != 0.0:
            full = QRegion(self.sprite_local().adjusted(-60, -20, 60, 10))
        else:
            full = QRegion()
            for m in masks:
                if isinstance(m, tuple): full = full.united(self.sp.peek_mask(m[1], m[2]))
                elif m: full = full.united(self.sp.mask(m))
            full = full.translated(self.ox, self.oy)
        if br is not None:
            full = full.united(QRegion(br.adjusted(-3, -16 if self.bubble_tail_up() else -3, 3, 16)))
        for k in fxk:
            full = full.united(QRegion(self.fx_rect(k).adjusted(-2, -2, 2, 14)))
        if key[3]:
            full = full.united(QRegion(self.hearts_rect()))
        if self.badge_text is not None:
            full = full.united(QRegion(self.badge_rect()))
        self.setMask(full)

    # ---------- 绘制 ----------
    def sprite_local(self):
        return QRect(self.ox, self.oy, self.sp.sw, self.sp.sh)

    def bubble_rect(self):
        k = (self.bubble[0], self.x(), self.y(), self.W, self.font.pixelSize(), self.peek, self.sp.sw)
        if self.bubble_cache and self.bubble_cache[0] == k:
            return QRect(self.bubble_cache[1])
        r = self._bubble_rect()
        self.bubble_cache = (k, QRect(r))
        return r

    def _bubble_rect(self):
        fm = QFontMetrics(self.font)
        text = self.bubble[0]
        # 躲在屏幕边时，气泡只能画在“窗口 ∩ 屏幕”里：挪回可见的一侧，必要时折成多行
        g = self.peek_screen().availableGeometry().translated(-self.x(), -self.y())
        vis = g.intersected(self.rect())
        if vis.isEmpty():                                   # 窗口整个不在任何屏幕上（不该发生）：按窗口本身算
            vis = self.rect()
        maxw = max(130, min(self.W - 16, 320, vis.width() - 8))
        br = fm.boundingRect(QRect(0, 0, maxw - 28, 200), Qt.TextWordWrap | Qt.AlignCenter, text)
        w = min(maxw, br.width() + 32); h = br.height() + 22
        x = (self.W - w) // 2; y = BUBBLE_H - h - 4
        if self.peek and self.peek_art_ok():
            if self.peek in PEEK_TB:                        # 上/下边：气泡在她和屏幕中间那一侧，横向对着她
                c = self.sp.peek_mask(self.peek_key()[1], self.peek).boundingRect().translated(self.ox, self.oy)
                x = c.center().x() - w // 2
                y = c.bottom() + 14 if self.peek == 'top' else c.top() - h - 14
            else:                                           # 左/右边：气泡靠墙那边、在她头顶
                x = vis.right() - 4 - w if self.peek == 'right' else vis.left() + 4
                y = min(y, self.peek_content().top() - h - 2)
        if x + w > vis.right() - 4: x = vis.right() - 4 - w
        if x < vis.left() + 4: x = vis.left() + 4
        return QRect(x, clamp_bubble_y(y, h, vis), w, h)

    def bubble_tail_up(self):
        return self.peek == 'top' and self.peek_art_ok()

    def fx_rect(self, name):
        if name == 'zzz':
            s = self.sp.s
            return QRect(int(self.ox + self.sp.ux + self.sp.uw * 0.66), int(self.oy + self.sp.uy - 10 * s), int(70 * s) + 20, int(80 * s) + 20)
        if name == 'excl':
            s = self.sp.s
            return QRect(int(self.ox + self.sp.ux + self.sp.uw * 0.74), int(self.oy + self.sp.uy + 4 * s), int(30 * s) + 12, int(44 * s) + 12)
        img, (ax, ay) = self.sp.fx[name]
        return QRect(int(self.ox + ax - img.width() / 2), int(self.oy + ay - img.height() / 2), img.width(), img.height())

    def hearts_rect(self):
        uw, uh = self.sp.uw, self.sp.uh
        return QRect(int(self.ox + self.sp.ux + uw * 0.2), int(self.oy + self.sp.uy - 30 * self.sp.s - 12), int(uw * 0.6), int(uh * 0.22 + 40 * self.sp.s + 12))

    def badge_rect(self):
        fm = QFontMetrics(self.small)
        w = fm.horizontalAdvance(self.badge_text or '计时 00:00:00') + 22
        x = int(self.ox + self.sp.ux + (self.sp.uw - w) // 2)
        y = int(self.oy + self.sp.uy) + self.sp.uh - 30
        if self.peek:     # 躲在屏幕边时，挪到露出来的人下面、靠墙那边
            vis = self.peek_screen().availableGeometry().translated(-self.x(), -self.y()).intersected(self.rect())
            if self.peek_art_ok():
                c = self.sp.peek_mask('shy', self.peek).boundingRect().translated(self.ox, self.oy)
                if self.peek in PEEK_TB:                    # 上边：挂在露出来的人下面；下边：在她头顶
                    x = c.center().x() - w // 2
                    y = c.bottom() + 4 if self.peek == 'top' else c.top() - 28
                else:
                    x = c.right() - w - 2 if self.peek == 'right' else c.left() + 2
                    y = min(y, c.bottom() + 4)
            x = max(vis.left() + 4, min(x, vis.right() - 4 - w))
            y = max(vis.top() + 2, min(y, vis.bottom() - 26))
        return QRect(x, y, w, 24)

    def update_badge(self):
        t = self.timer
        new = t.label() if (t.active() and self.st['show_timer_badge']) else None
        if new != self.badge_text:
            self.badge_text = new
            self.mask_key = None
            if self.isVisible(): self.compose()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        if self.angle:
            p.fillRect(self.rect(), Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            pv = QPointF(self.ox + self.sp.ux + self.sp.uw / 2, self.oy + self.sp.uy + self.sp.uh * 0.1)
            p.save(); p.translate(pv); p.rotate(self.angle); p.translate(-pv)
            if self.cur_img is not None:
                p.drawImage(self.ox, self.oy, self.cur_img)
        else:
            # 角色那块直接整块覆盖（Source 模式比逐像素混合快），其余区域清成透明
            sr = self.sprite_local()
            clip = ev.rect()
            if not sr.contains(clip):
                p.setClipRegion(QRegion(clip).subtracted(QRegion(sr)))
                p.fillRect(self.rect(), Qt.transparent)
                p.setClipping(False)
            if self.cur_img is not None:
                p.drawImage(self.ox, self.oy, self.cur_img)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.Antialiasing)
        now = time.time()
        for name, t0, t1 in self.fx_on:
            if now < t0: continue
            u = now - t0
            a = min(1.0, u / 0.15) * min(1.0, (t1 - now) / 0.3)
            p.setOpacity(max(0.0, a))
            r = self.fx_rect(name)
            if name == 'zzz':
                self.paint_zzz(p, r, u)
            elif name == 'excl':
                self.paint_excl(p, r)
            else:
                if name == 'sweat':
                    r.translate(0, int(min(1.0, u / 1.6) * 10 * self.sp.s))
                p.drawImage(r, self.sp.fx[name][0])
        p.setOpacity(1.0)
        for t0, hx in self.hearts:
            u = (now - t0) / 1.3
            p.setOpacity(max(0.0, min(1.0, (1 - u) * 1.6)))
            x = self.ox + self.sp.ux + self.sp.uw * hx
            y = self.oy + self.sp.uy + self.sp.uh * 0.12 - u * 40 * self.sp.s
            paint_heart(p, x, y, 12 + 6 * self.sp.s)
        p.setOpacity(1.0)
        if self.angle:
            p.restore()
        if self.badge_text is not None:
            r = QRectF(self.badge_rect())
            p.setPen(QPen(QColor(40, 58, 130), 1.5)); p.setBrush(QColor(255, 255, 255, 235))
            p.drawRoundedRect(r, 11, 11)
            p.setFont(self.small); p.setPen(QColor(40, 46, 92))
            p.drawText(r, Qt.AlignCenter, self.badge_text)
        if self.bubble:
            r = QRectF(self.bubble_rect())
            path = QPainterPath()
            path.addRoundedRect(r, 14, 14)
            tail = QPainterPath()
            cx = self.ox + self.sp.sw / 2 + 10
            if self.bubble_tail_up():                     # 躲在上边时气泡在她下面：尾巴朝上指着她
                cx = self.ox + self.sp.peek_mask(self.peek_key()[1], self.peek).boundingRect().center().x()
                cx = max(r.left() + 18, min(r.right() - 18, cx))
                tail.moveTo(cx - 10, r.top() + 1); tail.lineTo(cx + 6, r.top() - 12); tail.lineTo(cx + 10, r.top() + 1)
            else:
                cx = max(r.left() + 18, min(r.right() - 18, cx))
                tail.moveTo(cx - 10, r.bottom() - 1); tail.lineTo(cx + 6, r.bottom() + 12); tail.lineTo(cx + 10, r.bottom() - 1)
            path = path.united(tail)
            p.setPen(QPen(QColor(40, 58, 130), 2.5))
            p.setBrush(QColor(255, 255, 255, 245))
            p.drawPath(path)
            p.setFont(self.font)
            p.setPen(QColor(40, 46, 92))
            p.drawText(r.adjusted(14, 8, -14, -8), Qt.TextWordWrap | Qt.AlignCenter, self.bubble[0])
        p.end()

    def paint_zzz(self, p, r, u):
        f = QFont(self.font)
        for i in range(3):
            ph = (u * 0.6 + i / 3) % 1.0
            f.setPixelSize(int((11 + 7 * i) * max(0.6, self.sp.s)))
            p.setFont(f)
            p.setOpacity(min(1.0, ph * 3) * (1 - ph))
            p.setPen(QColor(70, 90, 170))
            p.drawText(QPointF(r.left() + 6 + i * r.width() * 0.25, r.bottom() - 8 - i * r.height() * 0.28 - ph * 8), 'z')
        p.setOpacity(1.0)

    def paint_excl(self, p, r):
        f = QFont(self.font); f.setPixelSize(max(14, int(34 * self.sp.s)))
        p.setFont(f); p.setPen(QPen(QColor(230, 90, 90)))
        p.drawText(r, Qt.AlignCenter, '!')

    # ---------- 说话 ----------
    def quiet(self):
        return time.time() < self.st['quiet_until']

    def say(self, cat, proactive=False, strict=False, voice=True, expr=True):
        """proactive=她主动说的（安静模式/隐藏时不说）；strict=冷却中就不说"""
        if proactive and (self.quiet() or not self.isVisible()):
            return None
        line = self.brain.line(cat) if not strict else self.brain_strict(cat)
        if not line:
            return None
        self.show_bubble(line.text)
        if expr:
            self.wake()
            self.play_expr(line.expr)
            if cat == 'tease':
                now = time.time()
                self.fx_on += [('puff', now + 0.5, now + 3.0), ('sweat', now + 0.5, now + 3.0)]
        if voice and not self.st['muted'] and not self.quiet() and not self.fs_hidden:
            self.voice.play(line.id, self.st['volume'])
        self.log('say', cat, line.id)
        return line

    def brain_strict(self, cat):
        """冷却中的台词一句都不选；全在冷却就返回 None（v0.3.5：冷却判断挪进 LocalBrain.pick）。"""
        return self.brain.line(cat, strict=True)

    def show_bubble(self, text):
        self.bubble = (text, time.time() + max(3.2, 1.2 + len(text) * 0.17))
        self.mask_key = None

    def wake(self):
        if self.dozing:
            self.dozing = False
            self.fx_on = [f for f in self.fx_on if f[0] != 'zzz']

    # ---------- 鼠标 ----------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self.press_pos = e.globalPosition().toPoint()
        self.press_t = time.time()
        self.win_pos = self.pos()
        self.dragging = False
        self.slide.stop()
        lp = e.position().toPoint() - QPoint(self.ox, self.oy)
        ux, uy, uw, uh = self.sp.ux, self.sp.uy, self.sp.uw, self.sp.uh
        self.zone = 'head' if (lp.y() < uy + uh * 0.30 and ux + uw * 0.15 < lp.x() < ux + uw * 0.85) else 'body'
        if self.zone == 'head':
            self.press_timer.start(LONGPRESS_MS)

    def mouseMoveEvent(self, e):
        if self.press_pos is None:
            return
        if not (e.buttons() & Qt.LeftButton):        # 按着的时候左键没了：松手消息丢了，当作取消
            was_drag = self.dragging
            self.cancel_interaction()
            if was_drag:
                self.ensure_visible(); self.save_position()
            return
        gp = e.globalPosition().toPoint()
        d = gp - self.press_pos
        if not self.dragging and d.manhattanLength() > (14 if self.patting else 5):
            self.press_timer.stop()
            if self.patting:
                self.patting = False
            self.dragging = True
            self.leave_peek()
            self.on_lift()
        if self.dragging:
            if self.last_move is not None:
                self.vx = 0.6 * self.vx + 0.4 * (gp.x() - self.last_move.x())
            self.last_move = gp
            np_ = self.win_pos + d
            g = self.screen_of(gp).availableGeometry()
            sw, sh = self.sp.sw, self.sp.sh
            # 可以拖到屏幕边（为了“躲在边上”），但至少留 40% 在屏幕里
            np_.setX(max(g.left() - self.ox - int(sw * 0.6), min(np_.x(), g.right() - self.ox - int(sw * 0.4))))
            np_.setY(max(g.top() - self.oy - int(sh * 0.3), min(np_.y(), g.bottom() - self.oy - int(sh * 0.35))))
            self.move(np_)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self.press_pos is None:   # 没有对应的按下（已经被取消了）：不当成点击
            return
        self.press_timer.stop()
        if self.dragging:
            self.on_drop()
        elif self.patting:
            self.end_longpat()
        else:
            self.on_click(self.zone)
        self.press_pos = None
        self.dragging = False
        self.last_move = None

    def touch(self):
        self.last_touch = time.time()
        if self.mode == 'hold' and self.hold_override is None:
            mh = EXPR.get(self.expr or '', {}).get('max_hold')
            self.hold_until = self.last_touch + (HOLD_SECS if mh is None else min(HOLD_SECS, mh))

    def on_click(self, zone):
        self.touch()
        now = time.time()
        if self.dozing:
            self.say('sleepy'); return
        self.clicks = [t for t in self.clicks if now - t < 8] + [now]
        if len(self.clicks) >= 3:
            self.say('tease')
        elif zone == 'head':
            self.say('pat')
            self.hearts.append((now, 0.5))
        else:
            self.say('poke')
        self.log('click', zone)

    def start_longpat(self):
        if self.press_pos is None or self.dragging:
            return
        self.patting = True
        self.touch()
        self.wake()
        self.say('longpat')
        self.log('longpat start')

    def end_longpat(self):
        self.patting = False
        self.touch()
        self.say('longpat_end')

    def on_lift(self):
        self.touch()
        self.wake()
        now = time.time()
        self.fx_on += [('excl', now, now + 0.9), ('sweat', now + 0.1, now + 2.2)]
        self.say('lift', strict=True)
        self.log('lift')

    def on_drop(self):
        self.touch()
        side = self.edge_side()
        if side:
            self.apply_peek(side)
            self.say('peek', strict=True, expr=False)     # 躲边立绘自己就是表情，不再播（会闭眼的）眯眼笑
        else:
            self.leave_peek()
            self.ensure_visible()
            self.say('drop', strict=True)
            self.save_position()
        self.log('drop', side or 'free')

    # ---------- 拖文件给她：只看扩展名，绝不打开/移动/删除 ----------
    @staticmethod
    def accept_copy_only(e):
        """只接受“本地文件 + 对方允许复制”的拖放，并且只回答 Copy。
        一定不能接受 Move：资源管理器会以为我们搬走了文件而删掉原文件。"""
        md = e.mimeData()
        if not md.hasUrls() or not any(u.isLocalFile() for u in md.urls()) \
                or not (e.possibleActions() & Qt.CopyAction):
            e.ignore()
            return False
        e.setDropAction(Qt.CopyAction)
        e.accept()
        return True

    def dragEnterEvent(self, e):
        if self.accept_copy_only(e):
            self.say('drop_hover', strict=True)

    def dragMoveEvent(self, e):
        self.accept_copy_only(e)

    def dropEvent(self, e):
        if not self.accept_copy_only(e):
            return
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        self.touch()
        if len(paths) >= 3:
            cat, kind = 'drop_multi', f'{len(paths)} items'
        elif os.path.isdir(paths[0]):
            cat, kind = 'drop_folder', 'dir'
        else:
            ext = os.path.splitext(paths[0])[1].lower().lstrip('.')
            cat = PL.EXT2CAT.get(ext, 'drop_other')
            kind = ext_label(ext)                 # 认识的扩展名才原样记；不认识的统一记成 other
        self.say(cat)
        self.log('file drop', kind)          # 只记扩展名，不记文件名

    # ---------- 菜单（托盘和右键共用） ----------
    def contextMenuEvent(self, e):
        m = QMenu()
        self.fill_menu(m)
        m.exec(e.globalPos())

    def fill_menu(self, m):
        m.clear()
        st = self.st
        def act(text, fn=None, checked=None, enabled=True, menu=m):
            a = QAction(text, menu)
            if checked is not None:
                a.setCheckable(True); a.setChecked(checked)
            a.setEnabled(enabled)
            if fn: a.triggered.connect(fn)
            menu.addAction(a)
            return a
        act(f'掌柜台桌宠 v{VERSION}（非官方粉丝二创 · 含AI生成内容）', enabled=False)
        m.addSeparator()
        act('显示她' if (self.user_hidden or not self.isVisible()) else ('先藏起来' if self.tray_ok else '躲到屏幕边上'), self.toggle_hidden)
        act('总在最前', lambda on: self.set_on_top(on), checked=st['on_top'])
        mode_menu = m.addMenu('飘着 / 长脚')
        modes = QActionGroup(mode_menu); modes.setExclusive(True)
        for legs, label in ((False, '飘着'), (True, '长脚')):
            a = act(label, lambda _=False, legs=legs: self.set_legs(legs), checked=st['legs'] == legs, menu=mode_menu)
            modes.addAction(a)
        # 大小
        sm = m.addMenu(f'大小（现在 {round(self.sp.s * 100)}%）')
        wa = QWidgetAction(sm)
        box = QWidget(); hl = QHBoxLayout(box); hl.setContentsMargins(12, 6, 12, 6)
        lab = QLabel(f'{round(self.sp.s * 100)}%'); lab.setMinimumWidth(42)
        sl = QSlider(Qt.Horizontal); sl.setRange(20, 150); sl.setSingleStep(5); sl.setPageStep(10)
        sl.setValue(round(self.sp.s * 100)); sl.setMinimumWidth(170)
        def on_slide(v):
            lab.setText(f'{v}%'); self.pending_scale = v / 100; self.scale_timer.start(150)
        sl.valueChanged.connect(on_slide)
        hl.addWidget(sl); hl.addWidget(lab)
        wa.setDefaultWidget(box); sm.addAction(wa)
        sm.addSeparator()
        for v in (50, 75, 100, 125, 150):
            act(f'{v}%', lambda _=False, v=v: self.set_scale(v / 100), menu=sm)
        # 安静 / 声音
        if self.quiet():
            left = int((st['quiet_until'] - time.time()) // 60) + 1
            act(f'结束安静（还剩 {left} 分钟）', self.end_quiet)
        else:
            act('安静一小时（不主动说话、不出声）', self.start_quiet)
        vm = m.addMenu('声音')
        act('静音', lambda on: self.set_opt('muted', on), checked=st['muted'], menu=vm)
        if not self.voice.available():
            act('（还没装语音包，现在只有文字气泡）', enabled=False, menu=vm)
        vm.addSeparator()
        g = QActionGroup(vm)
        for name, v in (('小声', 0.2), ('适中', 0.35), ('大声', 0.6), ('最大', 0.9)):
            a = act(f'音量：{name}', lambda _=False, v=v: self.set_opt('volume', v), checked=abs(st['volume'] - v) < 0.01, menu=vm)
            g.addAction(a)
        # 提醒与小动作
        rm = m.addMenu('提醒和小动作')
        act('离开回来时打招呼', lambda on: self.set_opt('return_greet', on), checked=st['return_greet'], menu=rm)
        act('按时段问候（早安、饭点、深夜）', lambda on: self.set_opt('time_greet', on), checked=st['time_greet'], menu=rm)
        act(f'喝水提醒（每 {st["water_min"]} 分钟）', lambda on: self.set_opt('remind_water', on), checked=st['remind_water'], menu=rm)
        act(f'久坐提醒（连续用电脑 {st["stand_min"]} 分钟）', lambda on: self.set_opt('remind_stand', on), checked=st['remind_stand'], menu=rm)
        im = rm.addMenu('提醒间隔')
        for v in (30, 45, 60, 90):
            act(f'喝水：{v} 分钟', lambda _=False, v=v: self.set_opt('water_min', v), checked=st['water_min'] == v, menu=im)
        im.addSeparator()
        for v in (45, 60, 90, 120):
            act(f'久坐：{v} 分钟', lambda _=False, v=v: self.set_opt('stand_min', v), checked=st['stand_min'] == v, menu=im)
        mm = rm.addMenu('待机小动作')
        g2 = QActionGroup(mm)
        for k, name in MICRO_NAMES:
            g2.addAction(act(name, lambda _=False, k=k: self.set_micro(k), checked=st['micro'] == k, menu=mm))
        rm.addSeparator()
        act('有全屏程序时自动躲起来', lambda on: self.set_opt('fullscreen_hide', on), checked=st['fullscreen_hide'], menu=rm)
        act('拖到屏幕边时只露半个身子', lambda on: self.set_opt('edge_peek', on), checked=st['edge_peek'], menu=rm)
        act('计时器（番茄钟 / 正计时）…', self.open_panel)
        m.addSeparator()
        act('找回她（回到屏幕中间）', self.recenter)
        if P.IS_WIN:
            act('开机自动启动', self.toggle_autostart, checked=P.autostart_get())
            if P.legacy_autostart() == 'ours':
                act('（发现旧版的开机自启项：点上面这项时会一并清掉）', enabled=False)
        else:
            act('开机自动启动（仅 Windows）', enabled=False)
        act('导出诊断日志', self.export_log)
        act('关于…', self.show_about)
        m.addSeparator()
        act('退出', QApplication.quit)

    def set_opt(self, k, v):
        self.st[k] = v; self.save_later(); self.log('opt', k, v)
        if k == 'edge_peek' and not v and self.peek:
            self.leave_peek(); self.ensure_visible(); self.save_position()
        if k == 'remind_water' and v: self.last_water = time.time()
        if k == 'remind_stand' and v: self.last_stand = time.time()
        if k == 'fullscreen_hide' and not v and self.fs_hidden:
            self.fs_hidden = False; self.apply_visibility()
        if k == 'muted' and v: self.voice.stop()

    def set_micro(self, k):
        self.set_opt('micro', k); self.next_micro = time.time() + self.micro_gap()

    def micro_gap(self):
        r = MICRO.get(self.st['micro'])
        return random.uniform(*r) if r else 1e12

    def start_quiet(self):
        self.say('quiet_on', voice=False)
        self.st['quiet_until'] = time.time() + 3600; self.was_quiet = True; self.save_later(); self.log('quiet on')
        self.voice.stop()

    def end_quiet(self):
        self.st['quiet_until'] = 0.0; self.was_quiet = False; self.save_later()
        self.say('quiet_off'); self.log('quiet off')

    def toggle_hidden(self):
        if self.user_hidden or self.hide_pending or not self.isVisible():
            self.hide_pending = False
            self.user_hidden = False; self.fs_hidden = False
            self.apply_visibility()
            if self.isVisible():
                self.say('unhide', voice=False)
            return
        if not self.tray_ok:
            # 托盘图标不在（或拿不准）：绝不完全藏起来，不然就找不回她了。改成躲到屏幕边。
            side = self.nearest_side()
            self.apply_peek(side)
            self.save_position()
            self.show_bubble('托盘图标出不来，我先躲到屏幕边上啦～鼠标靠过来我就探头')
            self.log('hide -> peek (no tray)', side)
            return
        self.show_bubble('我在右下角等你哦～')
        if self.tray:
            self.tray.showMessage('我在这儿～', '点右下角托盘里的我就能叫我出来；没看到的话，点任务栏右边的 ^ 找找。',
                                  self.tray_icon, 5000)
        self.hide_pending = True
        QTimer.singleShot(1400, self._do_hide)            # 先让她把话说完再藏

    def _do_hide(self):
        if not self.hide_pending:
            return
        self.hide_pending = False
        self.user_hidden = True
        self.apply_visibility()

    def toggle_autostart(self, on):
        try:
            r = P.autostart_set(on); self.log('autostart', on, r)
            if r == 'legacy_removed':
                self.show_bubble('顺手把旧版的开机自启清掉啦，以后开机只会叫醒现在的我～')
        except Exception as ex:
            self.log('autostart failed', type(ex).__name__)
            self.show_bubble('开机自启这次没设置成功……可能是安全软件拦了一下～')

    def open_panel(self):
        if self.panel is None:
            self.panel = TimerPanel(self)
        self.panel.refresh()
        r = self.sprite_rect()
        g = self.screen_of(r.center()).availableGeometry()
        self.panel.adjustSize()
        x = r.left() - self.panel.width() - 10
        if x < g.left(): x = r.right() + 10
        self.panel.move(max(g.left(), min(x, g.right() - self.panel.width())), max(g.top(), r.top() + 40))
        self.panel.show(); self.panel.raise_()

    def export_log(self):
        """导出给作者看的诊断文件（可以分享的那份）：设置只导出固定字段，屏幕名换成 screen_1/screen_2，
        不含路径、文件名、按键或个人内容。完整的崩溃记录只留在本机，不会放进这里。"""
        name = time.strftime('ZhangguiPet-诊断-%Y%m%d-%H%M%S.txt')
        try:
            screens = QGuiApplication.screens()
            smap = screen_map([s.name() for s in screens])
            scr = [f'{smap.get(s.name(), "screen_?")} {s.geometry().getRect()} avail={s.availableGeometry().getRect()} '
                   f'dpr={s.devicePixelRatio()}' for s in screens]
            text = (f'掌柜台桌宠 v{VERSION} 诊断信息（不含文件名、路径、按键或个人内容；屏幕名已换成编号）\n'
                    f'系统: {P.system_summary()}  Qt {qVersion()}  设置保存方式: {P.CONF_KIND}\n屏幕:\n  ' + '\n  '.join(scr) + '\n'
                    f'设置: {json.dumps(diag_settings(self.st, smap), ensure_ascii=False)}\n'
                    f'精灵缓存: {len(self.sp.cache)} 帧 {self.sp.bytes / 2**20:.1f}MB  语音包: {len(self.voice.ids)} 句\n\n最近日志:\n'
                    + redact_text('\n'.join(self.log.ring), smap) + '\n')
        except Exception as e:
            text = (f'掌柜台桌宠 v{VERSION}（诊断信息收集出错 {type(e).__name__}）\n'
                    + redact_text('\n'.join(self.log.ring), {}) + '\n')
        import tempfile
        for d in [x for x in (self.conf, tempfile.gettempdir()) if x]:
            path = os.path.join(d, name)
            if P.write_text_safely(path, text, self.log):
                self.log('export log ok', P.CONF_KIND if d == self.conf else 'temp')
                self.show_bubble('诊断日志导出好了，我把文件夹打开给你～')
                if ENV('ZHANGGUI_PET_NO_OPEN') != '1':
                    try:
                        QDesktopServices.openUrl(QUrl.fromLocalFile(d))
                    except Exception:
                        pass
                return path
        self.log('export log failed')
        try:
            QGuiApplication.clipboard().setText(text)
            self.show_bubble('诊断日志没能存成文件，我把它复制到剪贴板啦，粘贴发给作者就好～')
        except Exception:
            self.show_bubble('诊断日志这次没能导出来……可能是安全软件拦了一下～')
        return None

    def show_about(self):
        from PySide6.QtWidgets import QMessageBox
        if getattr(self, 'about_box', None) is None:
            box = QMessageBox()
            box.setWindowTitle('关于 掌柜台桌宠')
            box.setWindowIcon(self.icon)
            box.setIconPixmap(self.icon.pixmap(64, 64))
            box.setTextFormat(Qt.RichText)
            box.setTextInteractionFlags(Qt.TextBrowserInteraction)
            box.setText(ABOUT_HTML.format(v=VERSION))
            for lab in box.findChildren(QLabel):
                lab.setOpenExternalLinks(True)
            box.setStandardButtons(QMessageBox.Ok)
            box.setWindowModality(Qt.NonModal)
            box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            self.about_box = box
        self.about_box.show(); self.about_box.raise_(); self.about_box.activateWindow()
        self.log('about')

    # ---------- 托盘 ----------
    def setup_tray(self):
        avail = QSystemTrayIcon.isSystemTrayAvailable() and ENV('ZHANGGUI_PET_SIM_NO_TRAY') != '1'
        self.log('tray available', avail, 'integrity', hex(self.il) if self.il else '?', 'icon_null', self.tray_icon.isNull())
        if not avail:
            self.log('no system tray; right-click her for the menu')
            return
        self.tray = QSystemTrayIcon(self.tray_icon, self)
        self.tray.setToolTip(f'掌柜台桌宠 v{VERSION}\n{CREDIT}\n单击：显示/藏起来　右键：设置')
        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(lambda: self.fill_menu(self.tray_menu))
        self.fill_menu(self.tray_menu)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()
        self.tray_ok = self.tray.isVisible() and not self.low_integrity()
        self.log('tray show', 'visible', self.tray.isVisible(), 'ok', self.tray_ok)
        QTimer.singleShot(1500, self.check_tray)

    def low_integrity(self):
        return self.il is not None and self.il < 0x2000

    def check_tray(self):
        """托盘真的加上了吗？Windows 上加成功后能拿到图标位置；低完整性进程加不上（系统直接拒绝）。"""
        if not self.tray:
            return
        g = self.tray.geometry()
        vis = self.tray.isVisible()
        ok = vis and not self.low_integrity() and (not g.isEmpty() or not P.IS_WIN)
        self.tray_ok = ok
        self.log('tray check', 'visible', vis, 'geom', g.getRect(), 'ok', ok)
        # v0.3.9 ilfix：只有真的是低权限、托盘也真的没加上时才提示；同一个程序文件夹只提示一次（记在设置里，不记路径）
        if self.low_integrity() and not ok:
            tag = P.folder_tag()
            if self.st.get('lowil_notice') != tag:
                def note():
                    self.show_bubble(LOWIL_NOTE)
                    self.st['lowil_notice'] = tag
                    self.save_later()
                QTimer.singleShot(18000, note)

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_hidden()

    # ---------- 每秒一次：主动行为 ----------
    def brain_tick(self):
        now = time.time()
        # 第二次启动 -> 叫她出来
        if self.lock.poked():
            self.hide_pending = False
            self.user_hidden = False; self.fs_hidden = False
            self.apply_visibility(); self.ensure_visible(); self.raise_()
            self.say('already_here')
            self.log('second launch -> wake')
        # 全屏躲起来
        if self.st['fullscreen_hide'] and not self.user_hidden:
            try:
                fs = P.fullscreen_on_my_monitor(int(self.winId()))
            except Exception as ex:
                fs = self.fs_hidden                # 这一秒查不出来：保持现状，并记一笔（限频，只记错误类型）
                self.fs_error(ex)
            if fs != self.fs_hidden:
                self.fs_hidden = fs
                self.apply_visibility()
        if self.press_pos is not None:
            self.check_grab()
        # 安静模式到点
        q = self.quiet()
        if self.was_quiet and not q:
            self.was_quiet = False
            self.say('quiet_off', voice=False)
        # 这一秒想说的话先收集起来，只说优先级最高的一句（计时结束 > 回来啦 > 久坐 > 喝水 > 时段问候）
        cands = []
        ev = self.timer.tick()
        if ev:
            if self.fs_hidden:
                self.fs_missed = ev                # 全屏中：不出声、不弹通知，退出全屏后补说一次（只说最后一个）
                self.log('timer event during fullscreen', ev)
            else:
                # 用户自己开的计时，安静模式下也提示（但不出声）
                cands.append(dict(prio=PRIO_TIMER, cat=ev, proactive=False, oneshot=True,
                                  commit=lambda ev=ev: self.timer_notice(ev)))
        self.update_badge()
        if self.panel and self.panel.isVisible():
            self.panel.refresh()
        # 离开 / 回来
        idle = P.idle_seconds()
        if idle is not None:
            if not self.away and idle >= AWAY_SECS:
                self.away, self.away_start = True, now - idle
                if self.anim_timer.isActive():
                    self.anim_timer.setInterval(250)      # 人不在：动画降到 4 帧/秒省电
                self.log('away')
            elif self.away and idle < 3:
                self.away = False
                self.anim_timer.setInterval(int(1000 / self.sp.fps))
                dur = now - self.away_start
                self.session_start = now
                self.last_stand = now
                self.log('back after', int(dur), 's')
                if self.st['return_greet']:
                    h = PL.hour_f()
                    cat = 'return_morning' if (dur > 4 * 3600 and 5 <= h < 11) else ('return_long' if dur > 1800 else 'return_short')
                    cands.append(dict(prio=PRIO_RETURN, cat=cat, proactive=True, oneshot=True))
        active = not self.away
        calm = not self.bubble and not self.dragging and self.press_pos is None   # 不打断正在显示的话、正在进行的操作
        # 提醒（默认关）。被别的话挤掉、或因为安静/隐藏没说出口的，不算已提醒：之后条件满足时再说
        if active and self.st['remind_stand'] and now - self.session_start > self.st['stand_min'] * 60 \
                and now - self.last_stand > self.st['stand_min'] * 60 and calm:
            cands.append(dict(prio=PRIO_STAND, cat='stand', proactive=True, oneshot=False,
                              commit=lambda: setattr(self, 'last_stand', time.time())))
        if active and self.st['remind_water'] and now - self.last_water > self.st['water_min'] * 60 and calm:
            cands.append(dict(prio=PRIO_WATER, cat='water', proactive=True, oneshot=False,
                              commit=lambda: setattr(self, 'last_water', time.time())))
        # 按时段问候：真的说出口了才记“今天这个时段问候过了”
        slot = PL.current_slot()
        if slot and self.st['time_greet'] and active and now - self.t_start > 60:
            key = datetime.date.today().isoformat() + slot
            if key not in self.greeted and calm:
                cands.append(dict(prio=PRIO_SLOT, cat=slot, proactive=True, oneshot=False,
                                  commit=lambda key=key: self.greeted.add(key)))
        # 之前被挤掉的一次性事件（最多一个）：等现在的话说完再补；太久就算了
        pe = self.pending_ev
        if pe is not None:
            if now - pe[3] > PENDING_MAX_SECS:
                self.pending_ev = None
            elif calm or pe[0] == PRIO_TIMER:
                cands.append(dict(prio=pe[0], cat=pe[1], proactive=pe[2], oneshot=True, pending=True,
                                  commit=(lambda c=pe[1]: self.timer_notice(c)) if pe[0] == PRIO_TIMER else None))
        self.run_candidates(cands, now)
        # 深夜打盹
        h = PL.hour_f()
        late = h >= 23.5 or h < 5
        if late and not self.dozing and self.mode == 'idle' and not self.bubble and now - self.last_touch > 120 \
                and self.isVisible() and not self.dragging:
            self.dozing = True
            self.play_expr('smug', hold=1e9)
            self.fx_on.append(('zzz', now + 2, 1e12))
            self.log('doze')
        elif self.dozing and not late:
            self.wake(); self.go_idle()
        # 回到待机一阵子后，释放表情片段的帧（用完就还内存）
        if self.mode == 'idle' and now - self.idle_since > 60:
            self.sp.drop_non_idle()
        # 待机小动作
        if now >= self.next_micro:
            self.next_micro = now + self.micro_gap()
            if self.mode == 'idle' and not self.bubble and not self.dozing and self.isVisible() and not self.away \
                    and now - self.last_touch > 20 and self.press_pos is None:
                ex = random.choices(['smile', 'smug', 'thinking'], [3, 2, 1.5])[0]
                self.play_expr(ex, hold=random.uniform(2.5, 5.0))
                if not self.quiet() and random.random() < 0.15:
                    l = self.brain_strict('murmur')
                    if l: self.show_bubble(l.text)
                self.log('micro', ex)

    def run_candidates(self, cands, now=None):
        """同一秒的主动事件：按优先级只展示一条；没轮上的一次性事件留一个待补（优先级最高的那个）。
        返回说出口的类别（或 None）。"""
        now = now or time.time()
        cands = sorted(cands, key=lambda c: c['prio'])
        shown = None
        for i, c in enumerate(cands):
            if c.get('pending'):
                self.pending_ev = None
            line = self.say(c['cat'], proactive=c['proactive'])
            if line is not None:
                shown = c
                if c.get('commit'):
                    c['commit']()
                rest = [x for x in cands[i + 1:] if x.get('oneshot') and not x.get('pending')]
                if rest:
                    r = rest[0]
                    if self.pending_ev is None or r['prio'] < self.pending_ev[0]:
                        self.pending_ev = (r['prio'], r['cat'], r['proactive'], now)
                        self.log('event deferred', r['cat'])
                break
            # 没说出口（安静模式、藏着、台词都在冷却）：一次性事件就此放弃，条件型提醒下次再试
        return shown['cat'] if shown else None

    def timer_notice(self, ev):
        if ev == 'pomo_focus_end' and self.tray and not self.isVisible() and not self.fs_hidden:
            self.tray.showMessage('掌柜台桌宠', '专注结束啦，辛苦了～', self.tray_icon, 4000)

    def fs_error(self, ex):
        """全屏检测出错：只记错误类型，一分钟最多一条（附上这段时间里错了几次）。"""
        self.fs_err_n += 1
        now = time.time()
        if now - self.fs_err_t >= 60:
            self.log('fullscreen check failed', type(ex).__name__, 'x', self.fs_err_n)
            self.fs_err_t = now; self.fs_err_n = 0

    def greet_on_start(self):
        if not self.st['first_run_done']:
            self.say('first_run')
            QTimer.singleShot(6500, lambda: self.say('first_run_tip'))
            if self.tray:
                self.tray.showMessage('掌柜台桌宠', '我在右下角托盘里～右键可以调大小、静音、开计时器。', self.tray_icon, 6000)
            self.st['first_run_done'] = True
            self.save_later()
        else:
            self.say(PL.start_category(), proactive=True)


def paint_heart(p, x, y, s):
    path = QPainterPath()
    path.moveTo(x, y + s * 0.35)
    path.cubicTo(x - s * 1.1, y - s * 0.45, x - s * 0.45, y - s * 1.0, x, y - s * 0.4)
    path.cubicTo(x + s * 0.45, y - s * 1.0, x + s * 1.1, y - s * 0.45, x, y + s * 0.35)
    p.setPen(QPen(QColor(200, 70, 110), 1.2)); p.setBrush(QColor(255, 130, 170))
    p.drawPath(path)


def settle_scale(u):
    """落定小动作：u 秒时的竖向缩放（分段 smoothstep 插值）；结束返回 None。"""
    if u < 0 or u >= SETTLE_SECS:
        return None
    for (t0, a), (t1, b) in zip(SETTLE_KEYS, SETTLE_KEYS[1:]):
        if u < t1:
            x = (u - t0) / (t1 - t0)
            x = x * x * (3 - 2 * x)
            return a + (b - a) * x
    return None


def squash_y(im, k):
    """以底边（脚底）为锚点把整张图竖向缩放到 k 倍（k<=1），画布大小不变，所以遮罩和点击区域都不受影响。"""
    if k >= 0.9995:
        return im
    out = QImage(im.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(0)
    h = im.height() * k
    p = QPainter(out)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawImage(QRectF(0, im.height() - h, im.width(), h), im)
    p.end()
    return out


def scaled_copy(im, k):
    out = QImage(im.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(0)
    p = QPainter(out)
    p.setOpacity(k)
    p.drawImage(0, 0, im)
    p.end()
    return out


# ======================= 录屏/测试用的命令文件（只在源码运行时有效） =======================
# v0.3.5：不再执行任意 Python（以前是 eval/exec），只认下面这张白名单里的动作；打包后的程序（sys.frozen）完全不读。
# 命令文件每行一条：动作名 [参数...]，例如  pat / poke / scale 0.8 / line pat03 / timer_remaining 3
# 每条命令的结果打印成一行  [cmd->] <repr>（tools/demo_v03.py 用 ast.literal_eval 读回来）。
def dev_cmd_file():
    if getattr(sys, 'frozen', False):
        return None
    return ENV('ZHANGGUI_PET_CMD_FILE') or None


def _dev_line(pet, line_id):
    for _, l in PL.all_lines():
        if l.id == line_id:
            pet.show_bubble(l.text); pet.wake(); pet.play_expr(l.expr)
            return l.id
    raise ValueError('unknown line id')


def _dev_timer_remaining(pet, secs):
    t = pet.timer
    left = max(0.0, float(secs))
    t.acc = max(0.0, t.phase_len() - left) if t.mode == 'pomo' else left
    t.t0 = time.monotonic()
    return round(t.shown(), 1)


def _dev_away_secs(pet, secs):
    global AWAY_SECS
    AWAY_SECS = max(1.0, float(secs))
    return AWAY_SECS


def _dev_go_pos(pet):
    if pet.panel is None:
        pet.open_panel()
    b = pet.panel.b_go
    return b.mapToGlobal(b.rect().center()).toTuple()


DEV_ACTIONS = {
    'pat':             (0, lambda pet: pet.on_click('head')),          # 摸头（等于点一下她的脑袋）
    'poke':            (0, lambda pet: pet.on_click('body')),          # 戳身体
    'scale':           (1, lambda pet, v: pet.set_scale(float(v)) or pet.sp.s),
    'say':             (1, lambda pet, cat: getattr(pet.say(cat), 'id', None)),
    'line':            (1, _dev_line),                                 # 显示指定 id 的台词
    'sprite_rect':     (0, lambda pet: pet.sprite_rect().getRect()),
    'timer_open':      (0, lambda pet: pet.open_panel()),
    'timer_go_pos':    (0, _dev_go_pos),                                # 计时器「开始」按钮中心的屏幕坐标
    'timer_remaining': (1, _dev_timer_remaining),                       # 录屏快进：番茄钟只剩 N 秒
    'timer_panel_close': (0, lambda pet: pet.panel.close() if pet.panel else None),
    'away_secs':       (1, _dev_away_secs),                             # 多久算“离开”
    'recenter':        (0, lambda pet: pet.recenter()),
    'toggle_hidden':   (0, lambda pet: pet.toggle_hidden()),
    'state':           (0, lambda pet: {'visible': pet.isVisible(), 'fs_hidden': pet.fs_hidden, 'user_hidden': pet.user_hidden,
                                        'peek': pet.peek, 'mode': pet.mode, 'bubble': pet.bubble[0] if pet.bubble else None}),
}


def run_dev_command(pet, cmdline):
    """执行一条白名单命令；不认识的、参数个数不对的一律拒绝（返回 ('error', 原因)）。"""
    parts = cmdline.split()
    if not parts:
        return None
    name, args = parts[0], parts[1:]
    spec = DEV_ACTIONS.get(name)
    if spec is None:
        return ('error', 'unknown action')
    if len(args) != spec[0]:
        return ('error', 'bad args')
    try:
        return spec[1](pet, *args)
    except Exception as e:
        return ('error', type(e).__name__)


LOWIL_NOTE = ('这个文件夹被系统标成了“低权限”，托盘图标出不来，设置也只能存在程序旁边～'
              '把 ZhangguiPet 文件夹挪到“下载”或“文档”里再打开我就好啦（这句只说一次）')


def main():
    global _CRASH_DIR, _STARTED
    conf, kind, failed = P.resolve_config_dir()         # 永远不会抛异常；全都写不了就是 (None, 'memory')
    _CRASH_DIR = conf
    log = P.Log(conf)
    log('start', f'v{VERSION}', 'storage', kind, ('fallback from ' + ','.join(failed)) if failed else '')
    P.adopt_portable_settings(conf, kind, log)          # v0.3.9 ilfix：低权限时存在 data\ 里的较新设置接回 AppData
    migrated = P.migrate_legacy_settings(conf, kind, log)   # 旧版设置只读过来一次，旧文件夹不动
    if P.legacy_autostart():
        log('old-version autostart entry present', P.legacy_autostart(), '(left as is; cleaned only when the user toggles autostart)')
    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(P.APP)
    lock = P.SingleInstance(conf, log)
    if not lock.acquire():
        # 已经开着了：叫她出来打招呼，自己退出
        lock.poke()
        log('second instance -> wake')
        return 0
    st = P.Settings(conf, log)
    pet = Pet(conf, log, st, lock)
    pet.show()
    QTimer.singleShot(900, pet.greet_on_start)
    low_il = P.integrity_level() is not None and P.integrity_level() < 0x2000
    if low_il and kind == 'portable':
        st['storage_notice'] = kind                     # 低权限那句提示已经说明了“设置存在程序旁边”，不再重复说一遍
    if kind not in ('appdata', 'env') and st.get('storage_notice') != kind:
        def storage_note():                              # 设置没能存进 AppData：温柔地提一句（不说路径），只提一次
            msg = P.STORAGE_NOTE.get(kind, '设置换了个地方保存啦，可能是安全软件拦了一下～')
            if pet.isVisible():
                pet.show_bubble(msg)
            elif pet.tray:
                pet.tray.showMessage('掌柜台桌宠', msg, pet.tray_icon, 6000)
            st['storage_notice'] = kind
            pet.save_later()
        QTimer.singleShot(14000 if not st['first_run_done'] else 7000, storage_note)
    app.aboutToQuit.connect(lambda: (pet.save_position(), st.save(), log('quit')))
    secs = float(ENV('ZHANGGUI_PET_AUTOQUIT', '0'))
    if secs > 0:
        QTimer.singleShot(int(secs * 1000), app.quit)
    if DEBUG:
        print(f'[debug] window {pet.W}x{pet.height()} at {pet.x()},{pet.y()} sprite {pet.sp.sw}x{pet.sp.sh} '
              f'origin {pet.ox},{pet.oy} conf {conf}', flush=True)
    cmdf = dev_cmd_file()        # 测试用：从文件读白名单命令（只在源码运行 + 设置了环境变量时生效）
    if cmdf:
        log('dev command file enabled (source run only)')
        def poll_cmd():
            if os.path.exists(cmdf):
                try:
                    cmds = open(cmdf, encoding='utf-8').read().split('\n'); os.remove(cmdf)
                except OSError:
                    return
                for c in filter(None, (x.strip() for x in cmds)):
                    print('[cmd]', c, flush=True)
                    print('[cmd->]', repr(run_dev_command(pet, c)), flush=True)
        t = QTimer(app); t.timeout.connect(poll_cmd); t.start(200)
    _STARTED = True
    rc = app.exec()
    lock.release()
    return rc


if __name__ == '__main__':
    try:
        _rc = main()
    except SystemExit:
        raise
    except BaseException:
        _excepthook(*sys.exc_info())
        _rc = 1
    sys.exit(_rc)
