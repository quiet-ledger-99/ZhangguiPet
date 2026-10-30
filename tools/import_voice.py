#!/usr/bin/env python3
"""把合成好的 <台词id>.mp3/.wav/.ogg 转成桌宠用的 assets/voice/<id>.wav（单声道 24kHz 16-bit，裁掉首尾静音，响度统一）。
用法：python tools/import_voice.py <合成结果文件夹>     需要 ffmpeg 在 PATH 里。只认 voice_plan_pet.json 里有的 id。
这是本机准备可选语音包的工具，主程序不会调用它，也不要 API key。生成的 wav 不必提交进主仓库。"""
import os, sys, json, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = sys.argv[1]
ids = {x['id'] for x in json.load(open(os.path.join(ROOT, 'voice_plan_pet.json'), encoding='utf-8'))['lines']}
dst = os.path.join(ROOT, 'assets', 'voice'); os.makedirs(dst, exist_ok=True)
n = 0
for f in sorted(os.listdir(src)):
    i, ext = os.path.splitext(f)
    if i not in ids or ext.lower() not in ('.mp3', '.wav', '.ogg', '.flac'):
        continue
    af = ('silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,'
          'silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse,loudnorm=I=-18:TP=-2')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', os.path.join(src, f), '-af', af, '-ac', '1', '-ar', '24000',
                    '-sample_fmt', 's16', os.path.join(dst, i + '.wav')], check=True)
    n += 1
missing = sorted(ids - {os.path.splitext(f)[0] for f in os.listdir(dst)})
print(f'导入 {n} 句 -> {dst}；还缺 {len(missing)} 句' + (f'：{", ".join(missing[:12])}…' if missing else ''))
