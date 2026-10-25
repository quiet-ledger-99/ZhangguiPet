#!/bin/bash
# 起一个独立虚拟桌面：Xvfb + picom（透明合成）+ stalonetray（系统托盘）+ 假桌面
D=${D:-:78}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY=${PY:-$ROOT/.venv/bin/python}
pkill -f "Xvfb $D" 2>/dev/null; sleep 0.5
Xvfb $D -screen 0 1280x720x24 +extension Composite +extension MIT-SCREEN-SAVER +render -ac -noreset >/tmp/xvfb${D#:}.log 2>&1 &
sleep 1.5
DISPLAY=$D picom --backend xrender --no-vsync >/tmp/picom${D#:}.log 2>&1 &
sleep 0.5
DISPLAY=$D "$PY" "$ROOT/tools/fake_desktop.py" /tmp/desk_clicks${D#:}.log >/tmp/desk${D#:}.log 2>&1 &
sleep 1.5
DISPLAY=$D stalonetray --geometry 4x1-0-0 --icon-size 28 --kludges force_icons_size -bg '#1f2a48' --window-type dock --skip-taskbar >/tmp/tray${D#:}.log 2>&1 &
sleep 1
echo up $D
