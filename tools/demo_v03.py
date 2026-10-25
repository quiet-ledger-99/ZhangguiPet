#!/usr/bin/env python3
"""在独立虚拟屏（Xvfb :79 + picom + stalonetray 托盘 + 假桌面）上录 v0.3 演示：demo_v03.mp4 + demo_v03.png（拼图）。
所有操作都是真实的鼠标事件（xdotool）：托盘右键菜单、滑块、点头/点身体/长按、拖动、贴边、从假桌面拖文件。
只有两处用了测试开关：番茄钟“快进”到最后 3 秒（ZHANGGUI_PET_CMD_FILE），全屏程序用一个标记文件模拟（Linux 上没有 Win32 前台窗口）。
v0.3.5 起命令文件只认白名单动作（见 zhanggui_pet.py 的 DEV_ACTIONS），不再执行 Python 表达式；打包后的 exe 完全不读命令文件。
“离开又回来”是真的：Xvfb 的 XScreenSaver 空闲计时，离开阈值调成 6 秒。"""
import os, sys, time, subprocess, json, shutil, ast
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = ':79'
OUT = os.path.join(ROOT, 'demo_v03')
CONF = '/tmp/qp/democonf'
CMD = '/tmp/qp/democmd'
LOG = '/tmp/qp/demo_pet.log'
FS = '/tmp/qp/demo_fs'
CAP = '/tmp/zg_caption.txt'
env = dict(os.environ, DISPLAY=D)
PY = os.path.join(ROOT, '.venv/bin/python')


def X(*a):
    subprocess.run(['xdotool', *map(str, a)], env=env)


def cap(t):
    open(CAP, 'w', encoding='utf-8').write(t)


def shot(name):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'x11grab', '-video_size', '1280x720', '-i', D,
                    '-frames:v', '1', f'/tmp/qp/demo_{name}.png'], env=env)


def q(action):
    """发一条白名单命令（例如 'sprite_rect'、'timer_remaining 3'），等桌宠回 [cmd->] 结果。"""
    n0 = open(LOG, encoding='utf-8').read().count('[cmd->]')
    open(CMD, 'w').write(action)
    for _ in range(60):
        time.sleep(0.05)
        s = open(LOG, encoding='utf-8').read()
        if s.count('[cmd->]') > n0:
            r = ast.literal_eval(s.rsplit('[cmd->] ', 1)[1].split('\n')[0])
            if isinstance(r, tuple) and r[:1] == ('error',):
                raise RuntimeError(f'{action}: {r[1]}')
            return r
    raise RuntimeError('no reply ' + action)


def sprite():
    return q('sprite_rect')


def drag(x0, y0, x1, y1, steps=24, dt=0.035, hold=0.0):
    X('mousemove', x0, y0); time.sleep(0.15); X('mousedown', 1)
    for i in range(1, steps + 1):
        X('mousemove', int(x0 + (x1 - x0) * i / steps), int(y0 + (y1 - y0) * i / steps)); time.sleep(dt)
    time.sleep(hold); X('mouseup', 1)


T0 = None
def at(t):
    w = t - (time.time() - T0)
    if w > 0: time.sleep(w)


def main():
    global T0
    shutil.rmtree(CONF, ignore_errors=True); os.makedirs(CONF)
    json.dump({'pos': {'screen': [0.62, 0.95]}, 'micro': 'off'}, open(CONF + '/settings.json', 'w'))
    for f in (CMD, FS, CAP):
        if os.path.exists(f): os.remove(f)
    cap('')
    subprocess.run(['bash', os.path.join(ROOT, 'tools/env_up.sh')], env=dict(os.environ, D=D))
    pet_env = dict(env, ZHANGGUI_PET_CONFIG_DIR=CONF, ZHANGGUI_PET_DEBUG='1', ZHANGGUI_PET_HOLD='5',
                   ZHANGGUI_PET_CMD_FILE=CMD, ZHANGGUI_PET_NO_AUDIO='1', ZHANGGUI_PET_NO_OPEN='1', ZHANGGUI_PET_SIM_FULLSCREEN_FILE=FS,
                   ZHANGGUI_PET_ORDER='first01,first02,pat03,poke08,lpat01,lpat_e01,lift01,drop01,dexe01,dimg01,pomo01,pomo03,peek02,ret01')
    X('mousemove', 640, 400)
    rec = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'x11grab', '-framerate', '30', '-video_size', '1280x720',
                            '-i', D, '-t', '84', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '22', OUT + '.mp4'], env=env)
    T0 = time.time()
    cap('① 第一次启动：她先打招呼，托盘弹出提示')
    pet = subprocess.Popen([PY, os.path.join(ROOT, 'zhanggui_pet.py')], env=pet_env, stdout=open(LOG, 'w'), stderr=subprocess.STDOUT)
    at(4.0); shot('01_first')
    at(9.0)
    x, y, w, h = sprite()
    cap('② 用鼠标点一下她的脑袋 = 摸头（冒小爱心）')
    X('mousemove', x + w // 2, y + 60); time.sleep(0.2); X('click', 1)
    at(10.2); shot('02_pat')
    at(13.0); cap('③ 点身体 = 戳一下')
    X('mousemove', x + w // 2, y + 280); time.sleep(0.2); X('click', 1)
    at(14.2); shot('03_poke')
    at(17.0); cap('④ 长按头 = 一直摸')
    X('mousemove', x + w // 2, y + 55); time.sleep(0.2); X('mousedown', 1)
    at(18.6); shot('04_longpat')
    at(19.4); X('mouseup', 1)
    at(23.0); cap('⑤ 拎起来会慌（汗滴 + 轻轻摆），放下说一句')
    drag(x + w // 2, y + 300, x + w // 2 - 260, y + 280, steps=30, dt=0.04, hold=0.4)
    at(24.0); shot('05_drag')
    at(28.0); cap('⑥ 托盘右键菜单 → 大小滑块（20%～150%）')
    X('mousemove', 1182, 706); time.sleep(0.2); X('click', 3)
    at(29.5); X('mousemove', 1050, 489)
    at(30.5); X('mousemove', 900, 491); time.sleep(0.2); X('mousemove', 842, 491); time.sleep(0.3)
    X('mousedown', 1)
    for xx in range(842, 803, -3):
        X('mousemove', xx, 491); time.sleep(0.05)
    time.sleep(0.3); shot('06_menu'); X('mouseup', 1)
    at(33.5); X('key', 'Escape'); time.sleep(0.15); X('key', 'Escape')
    at(36.0)
    x, y, w, h = sprite()
    cx, cy = x + w // 2, y + int(h * 0.6)
    cap('⑦ 把文件拖给她：只看扩展名，绝不打开、移动、删除')
    drag(58, 404, cx, cy, steps=26, dt=0.04, hold=0.5)          # setup.exe
    at(38.0); shot('07_exe')
    at(41.5)
    drag(58, 492, cx, cy, steps=26, dt=0.04, hold=0.5)          # 合照.png
    at(44.5); cap('⑧ 计时器：番茄钟 / 正计时（关掉小窗也继续）')
    X('mousemove', 1182, 706); time.sleep(0.2); X('click', 3)
    at(45.6); X('mousemove', 1062, 589); time.sleep(0.25); X('click', 1)
    at(46.8)
    bx, by = q('timer_go_pos')
    X('mousemove', bx, by); time.sleep(0.2); X('click', 1)
    at(49.0); cap('⑧ 计时器（录屏快进到最后 3 秒）')
    q('timer_remaining 3')
    at(52.6); shot('08_timer')
    at(54.0); q('timer_panel_close')
    at(55.0); cap('⑨ 拖到屏幕边：只露半个身子，鼠标靠近再探出来')
    x, y, w, h = sprite()
    drag(x + w // 2, y + int(h * 0.6), 1270, y + int(h * 0.6), steps=26, dt=0.035, hold=0.3)
    time.sleep(0.4); X('mousemove', 700, 380)
    at(59.0); shot('09_peek')
    X('mousemove', 1255, y + int(h * 0.4))
    at(60.5); shot('09b_peekout')
    X('mousemove', 640, 360)
    q('away_secs 6')      # 只在这一段把“离开”阈值调成 6 秒
    at(63.0); cap('⑩ 离开 6 秒（真实空闲检测，实际默认 5 分钟）……')
    at(71.0); cap('⑩ ……动一下鼠标：她说「回来啦」')
    X('mousemove', 600, 330)
    at(72.5); shot('10_return')
    q('away_secs 300')
    at(75.5); cap('⑪ 有全屏程序时自己躲起来（这里用标记文件模拟）')
    open(FS, 'w').close()
    at(78.5); shot('11_fs')
    os.remove(FS)
    at(80.0); cap('⑪ 全屏结束，她回来了')
    at(84.5)
    rec.wait()
    pet.terminate(); pet.wait()
    cap('')
    print(open(LOG, encoding='utf-8').read()[-2500:])
    subprocess.run(['pkill', '-f', f'Xvfb {D}'])
    # 拼图
    from PIL import Image, ImageDraw, ImageFont
    names = ['01_first', '02_pat', '03_poke', '04_longpat', '05_drag', '06_menu', '07_exe', '08_timer', '09_peek',
             '09b_peekout', '10_return', '11_fs']
    ims = [Image.open(f'/tmp/qp/demo_{n}.png').convert('RGB').resize((640, 360)) for n in names]
    sheet = Image.new('RGB', (640 * 4, 360 * 3), 'white')
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % 4) * 640, (i // 4) * 360))
    sheet.save(OUT + '.png')
    print('done', OUT + '.mp4', OUT + '.png')


if __name__ == '__main__':
    main()
