#!/usr/bin/env python3
"""把 pet_lines.py 里的全部台词导出成配音计划 voice_plan_pet.json，格式和 Day0 的
tts/day0_v*_plan.json 一样（同一个音色 longxing_v3.1、同样的语速音调），
拿到你电脑上用 Day0 那套合成脚本（tts/tools/synth_plan.py）跑一遍即可。
本脚本不联网、不含任何 key。合成出来的 <id>.mp3 再用 tools/import_voice.py 导入。"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pet_lines as PL

TAG = {'smile': 'shy', 'smug': 'shy', 'thinking': 'curious', 'biz': 'excited', 'pout': 'reluctantly',
       'stretch': 'shy', 'yawn': 'reluctantly', 'nod': 'curious', 'nap': 'shy'}   # v0.3.11 四个动作
INS = {
    'smile': '温柔、会照顾人的邻家大姐姐，声音柔和带笑意，语速适中偏慢，轻声细语，像在身边小声关心你。',
    'smug': '温柔的大姐姐，眯着眼笑，语气放松、软一点，尾音轻轻拖一下，安心感。',
    'thinking': '温柔的大姐姐，带一点关切和好奇，语速稍慢，像歪着头认真问你。',
    'biz': '元气一点的温柔大姐姐，明亮有精神但不吵，句尾微微上扬，给人打气。',
    'pout': '被逗得有点无奈的温柔大姐姐，轻轻鼓着腮小声抱怨，可爱不凶，带一点笑意。',
    'stretch': '刚伸完懒腰的温柔大姐姐，舒展、放松，尾音带一点满足的叹气。',
    'yawn': '深夜有点困的温柔大姐姐，声音放轻、慢一点，带一点哈欠后的鼻音。',
    'nod': '认真听你说话的温柔大姐姐，短促、肯定、语气平稳。',
    'nap': '迷迷糊糊快睡着的温柔大姐姐，声音很轻很慢，像在小声嘟囔。',
}
SKIP = {'murmur'}   # 只有气泡、不出声的类别

lines = []
seen = set()
for cat, l in PL.all_lines():
    if cat in SKIP or l.id in seen:
        continue
    seen.add(l.id)
    lines.append({'id': l.id, 'text': l.text, 'tagged_text': f'[{TAG[l.expr]}]{l.text}', 'instruction': INS[l.expr],
                  'category': cat})
plan = {'voice': 'longxing_v3.1', 'model': 'qwen-audio-3.1-tts-flash',   # 云端 TTS 接口的模型参数（不是命名；本工具不随程序发布）
        'speech_rate': 1.0, 'pitch_rate': 1.05,
        'volume': 70, 'note': '掌柜台桌宠预录语音。合成后得到 <id>.mp3，用 tools/import_voice.py 导入 assets/voice/。',
        'lines': lines}
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'voice_plan_pet.json')
json.dump(plan, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'{len(lines)} 句 -> {out}  （约 {sum(len(x["text"]) for x in lines)} 字）')
