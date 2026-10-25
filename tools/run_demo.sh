#!/bin/bash
# 在独立的 Xvfb(:77)+picom 上跑桌宠并录屏（Linux）。产物: demo_v02.mp4 / demo_v02.png，日志打印到 stdout
# 时间线：0-2.5s 待机 | 2.5s 点空白处(穿透) | 3.5-5.5s 拖动 | 6s 点她(说话+表情) | 约10-13s 停留在表情 | 13-15s 回到待机
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
D=:77
OUT=${OUT:-demo_v02}
pkill -f "Xvfb $D" 2>/dev/null; sleep 0.5
Xvfb $D -screen 0 1280x720x24 +extension Composite +render -ac -noreset >/tmp/xvfb77.log 2>&1 &
sleep 1.5
DISPLAY=$D picom --backend xrender --no-vsync >/tmp/picom77.log 2>&1 &
PICOM=$!
sleep 1
DISPLAY=$D $PY tools/fake_desktop.py /tmp/desk_clicks.log >/tmp/desk.log 2>&1 &
DESK=$!
sleep 2.5
# 录屏把停留时间缩短到 7 秒（默认 30 秒）
DISPLAY=$D ZHANGGUI_PET_DEBUG=1 ZHANGGUI_PET_HOLD=${ZHANGGUI_PET_HOLD:-7} ZHANGGUI_PET_ORDER=${ZHANGGUI_PET_ORDER:-3} ZHANGGUI_PET_AUTOQUIT=25 $PY zhanggui_pet.py >/tmp/pet.log 2>&1 &
PET=$!
sleep 3
WID=$(DISPLAY=$D xdotool search --name '掌柜台桌宠' | head -1)
DISPLAY=$D xdotool windowmove $WID 760 150
sleep 0.5
eval $(DISPLAY=$D xdotool getwindowgeometry --shell $WID); echo "pet at $X,$Y ${WIDTH}x$HEIGHT"
M() { DISPLAY=$D xdotool "$@"; }
M mousemove 1000 600
ffmpeg -y -loglevel error -f x11grab -framerate 30 -video_size 1280x720 -i $D -t 17 -c:v libx264 -pix_fmt yuv420p -crf 20 $OUT.mp4 &
FF=$!
T0=$(date +%s.%N)
at() { python3 -c "import time,sys; w=$1-(time.time()-$T0); time.sleep(max(0,w))"; }
at 2.1; M mousemove $((X+15)) $((Y+110)); at 2.5; M click 1          # 透明处 -> 穿透到桌面
cx=$((X+170)); cy=$((Y+330))
at 3.3; M mousemove $cx $cy; at 3.5; M mousedown 1                     # 按住衣服拖动
for i in $(seq 1 30); do M mousemove $((cx-i*12)) $((cy+i*1)); sleep 0.05; done
M mouseup 1
eval $(DISPLAY=$D xdotool getwindowgeometry --shell $WID); echo "after drag $X,$Y"
at 5.7; M mousemove $((X+170)) $((Y+330)); at 6.0; M click 1          # 点她
M mousemove 1100 650
at 8.6; ffmpeg -y -loglevel error -f x11grab -video_size 1280x720 -i $D -frames:v 1 $OUT.png
wait $FF
wait $PET
echo '--- pet log'; cat /tmp/pet.log; echo '--- desktop clicks'; cat /tmp/desk_clicks.log
kill $DESK $PICOM; pkill -f "Xvfb $D"
