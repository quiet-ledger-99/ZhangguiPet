#!/usr/bin/env python3
"""录屏用的假桌面：渐变壁纸 + 几个图标，记录收到的点击（验证桌宠透明处点击穿透）。
v0.3：图标可以按住拖出去，发出真实的文件拖放（XDND），用来测试“把文件拖给她”。
图标对应 /tmp/zg_demo_files/ 下的空白测试文件（自动创建）。"""
import os, sys
from PySide6.QtCore import Qt, QMimeData, QUrl, QPoint
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QFont, QDrag, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

FILES_DIR = '/tmp/zg_demo_files'
ICONS = [('此电脑', None), ('回收站', None), ('账本.xlsx', 'xlsx'), ('Day2素材.mp4', 'mp4'),
         ('setup.exe', 'exe'), ('合照.png', 'png'), ('歌单.mp3', 'mp3')]


class D(QWidget):
    def __init__(s, log):
        super().__init__(None, Qt.FramelessWindowHint)
        s.log = open(log, 'w'); s.hits = []; s.press = None; s.caption = ''
        from PySide6.QtCore import QTimer
        s.t = QTimer(s); s.t.timeout.connect(s.read_caption); s.t.start(250)
        os.makedirs(FILES_DIR, exist_ok=True)
        for name, ext in ICONS:
            if ext:
                open(os.path.join(FILES_DIR, name), 'a').close()

    def icon_rect(s, i):
        return (30, 24 + i * 88, 56, 56)

    def paintEvent(s, e):
        p = QPainter(s); g = QLinearGradient(0, 0, s.width(), s.height())
        g.setColorAt(0, QColor(120, 170, 230)); g.setColorAt(1, QColor(250, 200, 220)); p.fillRect(s.rect(), g)
        f = QFont(); f.setFamilies(['Noto Sans CJK SC']); f.setPixelSize(13); p.setFont(f)
        for i, (t, ext) in enumerate(ICONS):
            x, y, w, h = s.icon_rect(i)
            p.setBrush(QColor(255, 255, 255, 200)); p.setPen(Qt.NoPen); p.drawRoundedRect(x, y, w, h, 10, 10)
            if ext:
                p.setPen(QColor(60, 80, 160)); p.drawText(x, y, w, h, Qt.AlignCenter, '.' + ext)
            p.setPen(QColor(30, 40, 80)); p.drawText(x - 24, y + 58, w + 48, 20, Qt.AlignCenter, t)
        if s.caption:
            f2 = QFont(); f2.setFamilies(['Noto Sans CJK SC']); f2.setPixelSize(22); f2.setBold(True); p.setFont(f2)
            w = p.fontMetrics().horizontalAdvance(s.caption) + 36
            p.setPen(Qt.NoPen); p.setBrush(QColor(20, 30, 70, 200)); p.drawRoundedRect(140, 16, w, 42, 12, 12)
            p.setPen(QColor(255, 255, 255)); p.drawText(140, 16, w, 42, Qt.AlignCenter, s.caption)
            p.setFont(f)
        p.setPen(QColor(30, 40, 80))
        for (x, y) in s.hits:
            p.setBrush(QColor(255, 80, 80)); p.drawEllipse(x - 6, y - 6, 12, 12)
            p.drawText(x + 10, y + 5, '桌面收到点击')

    def read_caption(s):
        try:
            c = open('/tmp/zg_caption.txt', encoding='utf-8').read().strip()
        except OSError:
            c = ''
        if c != s.caption:
            s.caption = c; s.update()

    def which(s, pt):
        for i, (t, ext) in enumerate(ICONS):
            x, y, w, h = s.icon_rect(i)
            if x <= pt.x() < x + w and y <= pt.y() < y + h:
                return i
        return None

    def mousePressEvent(s, e):
        pt = e.position().toPoint()
        i = s.which(pt)
        if i is not None and ICONS[i][1]:
            s.press = (pt, i); return
        s.hits.append((pt.x(), pt.y())); print(f'desktop click {pt.x()} {pt.y()}', file=s.log, flush=True); s.update()

    def mouseMoveEvent(s, e):
        if not s.press or (e.position().toPoint() - s.press[0]).manhattanLength() < 8:
            return
        name = ICONS[s.press[1]][0]; s.press = None
        md = QMimeData(); md.setUrls([QUrl.fromLocalFile(os.path.join(FILES_DIR, name))])
        dr = QDrag(s); dr.setMimeData(md)
        pm = QPixmap(56, 56); pm.fill(QColor(255, 255, 255, 220)); dr.setPixmap(pm); dr.setHotSpot(QPoint(28, 28))
        act = dr.exec(Qt.CopyAction | Qt.MoveAction | Qt.LinkAction, Qt.MoveAction)
        print(f'drag {name} result={act} exists={os.path.exists(os.path.join(FILES_DIR, name))}', file=s.log, flush=True)

    def mouseReleaseEvent(s, e):
        s.press = None


a = QApplication(sys.argv); d = D(sys.argv[1]); d.setGeometry(0, 0, 1280, 720); d.show(); a.exec()
