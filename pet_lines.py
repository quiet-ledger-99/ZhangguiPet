# -*- coding: utf-8 -*-
"""掌柜台桌宠台词库（v0.3）。改台词只改这个文件。

人设：温柔、会照顾人的邻家大姐姐千金，偶尔元气，被连戳时才有一点点小倔强。
      不说「本小姐」，不傲娇，不居高临下。

每句台词：L(id, 文本, 表情, 权重=1, 冷却秒=180)
  - id 要唯一且不要改：预录语音文件按 id 命名（assets/voice/<id>.wav）。
  - 表情：smile 微笑眨眼 | smug 眯眼温柔笑 | thinking 手指抵下巴 | biz 回眸挥手（闭嘴浅笑）| pout 合扇抵下巴、叉腰小嘴硬
    前三个和待机是同一站姿，切换最顺；biz/pout 是换了姿势的动作，进出有 0.15 秒淡化。
    （v0.3.6 起 biz/pout 的画面换了，名字不变，所以台词 id、语音方案都不用动；挥手最多停 4 秒就回待机。）
  - 冷却：这句说过之后多少秒内不再选它（避免复读）。
"""
import datetime
from collections import namedtuple

Line = namedtuple('Line', 'id text expr w cd')


def L(id, text, expr, w=1.0, cd=180):
    return Line(id, text, expr, w, cd)


LINES = {
    # ---- 点身体（普通戳）----
    'poke': [
        L('poke01', '嗯？我在呢。', 'smile'),
        L('poke02', '今天也辛苦啦。', 'smug'),
        L('poke03', '记得喝口水哦。', 'smile'),
        L('poke04', '眼睛累了吧？看看远处～', 'thinking'),
        L('poke05', '累了就歇一会儿吧。', 'smug'),
        L('poke06', '别太勉强自己哦。', 'thinking'),
        L('poke07', '慢慢来，不着急。', 'smug'),
        L('poke08', '你已经做得很好了。', 'smile'),
        L('poke09', '坐好久了，起来走走？', 'thinking'),
        L('poke10', '加油！我陪着你～', 'biz', 0.8),
        L('poke11', '有什么要我帮忙记下来的吗？', 'thinking'),
        L('poke12', '我就在旁边，不吵你～', 'smile'),
        L('poke13', '肩膀放松一点，深呼吸——', 'smug'),
        L('poke14', '今天的账本我都替你看着呢。', 'smile', 0.7),
        L('poke15', '嗯嗯，我听着呢。', 'smile'),
    ],
    # ---- 点头（摸头）----
    'pat': [
        L('pat01', '诶……摸头吗？', 'smile', 1, 120),
        L('pat02', '头发会乱的啦……不过没关系。', 'smug', 1, 120),
        L('pat03', '嘿嘿，谢谢你～', 'smile', 1, 120),
        L('pat04', '被你这样摸，有点不好意思呢。', 'smug', 1, 120),
        L('pat05', '帽子要掉啦，轻一点～', 'thinking', 0.8, 120),
    ],
    # ---- 长按：一直摸 ----
    'longpat': [
        L('lpat01', '嗯……好舒服。', 'smug', 1, 60),
        L('lpat02', '再、再摸一会儿也可以哦。', 'smug', 1, 60),
    ],
    'longpat_end': [
        L('lpat_e01', '……好啦，被摸得有点不好意思了～', 'smile', 1, 60),
        L('lpat_e02', '谢谢你，我精神多了！', 'biz', 0.7, 60),
        L('lpat_e03', '头发……我自己理一下就好。', 'thinking', 1, 60),
    ],
    # ---- 连戳（8 秒内第 3 下起）----
    'tease': [
        L('tease01', '好啦好啦，别戳啦～', 'pout', 1, 20),
        L('tease02', '再戳我可要鼓起来了。', 'pout', 1, 20),
        L('tease03', '戳上瘾了吗？真拿你没办法。', 'pout', 1, 20),
    ],
    # ---- 拖动 ----
    'lift': [
        L('lift01', '哇、要带我去哪儿呀？', 'pout', 1, 30),
        L('lift02', '诶诶，慢一点～', 'pout', 1, 30),
        L('lift03', '有点高……你可要拿稳哦。', 'pout', 1, 30),
    ],
    'drop': [
        L('drop01', '好啦，就待这儿吧。', 'smile', 1, 30),
        L('drop02', '这里风景不错嘛～', 'smile', 1, 30),
        L('drop03', '呼……站稳了。', 'smug', 1, 30),
    ],
    'peek': [
        L('peek01', '我先躲一会儿，有事叫我～', 'smug', 1, 60),
        L('peek02', '就露半个身子，不挡你。', 'smile', 1, 60),
    ],
    'peek_found': [
        L('peekf01', '被发现啦～', 'smile', 1, 90),
        L('peekf02', '嗯？找我吗？', 'thinking', 1, 90),
    ],
    # ---- 启动 ----
    'first_run': [
        L('first01', '你好呀，我是文昭。以后就在你桌面上陪你啦，请多关照～', 'smile', 1, 0),
    ],
    'first_run_tip': [
        L('first02', '右键我或者点右下角托盘里的我，就能调大小、静音这些哦。', 'thinking', 1, 0),
    ],
    'start_morning': [L('st_m01', '早上好～今天也一起加油吧！', 'biz'), L('st_m02', '早呀，吃早饭了吗？', 'smile')],
    'start_day': [L('st_d01', '我来啦～有事随时叫我。', 'smile'), L('st_d02', '嗯，今天也请多关照。', 'smug')],
    'start_evening': [L('st_e01', '晚上好，今天辛苦了。', 'smug'), L('st_e02', '晚上还要忙吗？我陪你。', 'smile')],
    'start_night': [L('st_n01', '这么晚还开电脑呀……别熬太久哦。', 'thinking'), L('st_n02', '夜深了，我陪你一会儿，忙完就去睡吧。', 'smug')],
    'already_here': [
        L('here01', '我已经在这儿啦～', 'smile', 1, 0),
        L('here02', '嗯？我一直都在呀。', 'thinking', 1, 0),
    ],
    'recenter': [L('rec01', '我回来啦，刚才跑太远了。', 'smile', 1, 0)],
    'unhide': [L('unhide01', '嗯，我回来了～', 'smile', 1, 0)],
    'quiet_on': [L('quiet01', '好，我安静待一小时，有事点我就好。', 'smug', 1, 0)],
    'quiet_off': [L('quiet02', '我又可以说话啦～', 'smile', 1, 0)],
    'size': [L('size01', '这个大小可以吗？', 'smile', 1, 20)],
    # ---- 按时段主动问候（每个时段每天最多一次）----
    'slot_morning': [L('sl_m01', '早上好！今天也元气满满～', 'biz'), L('sl_m02', '早饭要记得吃哦。', 'smile')],
    'slot_lunch': [L('sl_l01', '到饭点啦，午饭吃了没有呀？', 'thinking'), L('sl_l02', '先去吃饭吧，工作不会跑的。', 'smug')],
    'slot_tea': [L('sl_t01', '下午有点困吧？喝口水、伸个懒腰～', 'smile'), L('sl_t02', '下午茶时间～歇一小会儿？', 'smug')],
    'slot_dinner': [L('sl_d01', '晚饭要好好吃哦。', 'smile'), L('sl_d02', '天快黑啦，今天辛苦了。', 'smug')],
    'slot_late': [L('sl_n01', '这么晚了，早点睡吧。', 'smug'), L('sl_n02', '十一点多啦，收个尾就去休息好不好？', 'thinking')],
    'slot_deep': [L('sl_dp01', '都这个点了，快去睡觉。', 'thinking'), L('sl_dp02', '熬夜对身体不好的……我会担心的。', 'thinking')],
    # ---- 深夜打盹时被点醒 ----
    'sleepy': [
        L('sleepy01', '嗯……还没睡呀？', 'smug', 1, 60),
        L('sleepy02', '我、我没睡着哦……你也快去睡吧。', 'thinking', 1, 60),
        L('sleepy03', '呼……有点困了呢。', 'smug', 1, 60),
    ],
    # ---- 离开又回来（只看“多久没操作”，不监听键盘）----
    'return_short': [
        L('ret01', '回来啦～', 'smile', 1, 60),
        L('ret02', '欢迎回来！', 'biz', 0.7, 60),
        L('ret03', '回来啦，刚才去干嘛了呀？', 'thinking', 1, 60),
    ],
    'return_long': [
        L('retl01', '去了好久呀，回来就好～', 'smug', 1, 60),
        L('retl02', '等你好久啦……没事，我不着急。', 'smile', 1, 60),
    ],
    'return_morning': [L('retm01', '早上好呀，昨晚睡得好吗？', 'smile', 1, 60)],
    # ---- 提醒（默认关）----
    'stand': [
        L('stand01', '坐好久啦，起来走走好不好？', 'thinking', 1, 600),
        L('stand02', '已经连续忙了很久了，站起来伸个懒腰吧～', 'smug', 1, 600),
    ],
    'water': [
        L('water01', '喝口水吧，我等你～', 'smile', 1, 600),
        L('water02', '杯子里的水还有吗？', 'thinking', 1, 600),
    ],
    # ---- 计时器 ----
    'pomo_start': [L('pomo01', '好，开始专注！我安静陪着你。', 'biz', 1, 0)],
    'pomo_focus_end': [
        L('pomo02', '专注结束啦，辛苦了～起来活动一下吧。', 'smile', 1, 0),
        L('pomo03', '一个番茄完成！做得很好哦。', 'biz', 1, 0),
    ],
    'pomo_break_end': [L('pomo04', '休息好了吗？我们继续～', 'smile', 1, 0)],
    'count_30': [L('cnt01', '已经专心半小时啦，很棒哦。', 'smile', 1, 0)],
    'count_120': [L('cnt02', '已经两个小时了……起来动一动好不好？我等你回来。', 'thinking', 1, 0)],
    # ---- 拖文件给她（只看扩展名，绝不打开/移动/删除文件）----
    'drop_hover': [L('dh01', '嗯？要给我看什么？', 'thinking', 1, 15)],
    'drop_exe': [L('dexe01', '这个……我先不碰哦。', 'thinking', 3, 0), L('dexe02', '是程序呀，来路要看清楚哦。', 'thinking', 1, 0)],
    'drop_lnk': [L('dlnk01', '快捷方式呀，我就看看，不乱点～', 'smile', 1, 0)],
    'drop_img': [L('dimg01', '是图片呀～真好看。', 'smile', 1, 0), L('dimg02', '这张我先替你记着～', 'smug', 1, 0)],
    'drop_psd': [L('dpsd01', '在画画吗？好厉害！', 'biz', 1, 0)],
    'drop_doc': [L('ddoc01', '又在写东西呀，辛苦啦。', 'smug', 1, 0)],
    'drop_sheet': [L('dxls01', '表格……是账本吗？我最喜欢看账本了～', 'biz', 1, 0)],
    'drop_ppt': [L('dppt01', '要做汇报吗？一定会顺利的。', 'smile', 1, 0)],
    'drop_pdf': [L('dpdf01', '资料好多，慢慢看，不着急。', 'thinking', 1, 0)],
    'drop_txt': [L('dtxt01', '小笔记吗？我不偷看～', 'smug', 1, 0)],
    'drop_code': [L('dcode01', '在写代码呀，记得多存几次哦。', 'thinking', 1, 0)],
    'drop_music': [L('dmus01', '是歌吗？我也想听～', 'smile', 1, 0)],
    'drop_video': [L('dvid01', '视频呀……是下一期的素材吗？', 'thinking', 1, 0)],
    'drop_zip': [L('dzip01', '压缩包里装的什么呀？我就不拆了～', 'thinking', 1, 0)],
    'drop_font': [L('dfont01', '是字体呀，这个字好看吗？', 'smile', 1, 0)],
    'drop_folder': [L('ddir01', '一整个文件夹？我帮你看着，不乱动～', 'smile', 1, 0)],
    'drop_multi': [L('dmul01', '这么多呀……我一个一个看，都不会弄丢的。', 'thinking', 1, 0)],
    'drop_other': [L('doth01', '这是什么呀？我看不太懂，不过先还给你～', 'thinking', 1, 0)],
    # ---- 待机时偶尔的小声嘀咕（不出声，只有气泡，安静模式下不说）----
    'murmur': [
        L('mur01', '嗯～今天也很平静呢。', 'smug', 1, 900),
        L('mur02', '……你在忙什么呀？', 'thinking', 1, 900),
        L('mur03', '我在这儿，不打扰你。', 'smile', 1, 900),
    ],
    # ---- 星期 / 季节 / 节日（混进点击台词里，权重小）----
    'friday_night': [L('fri01', '周五啦，这周辛苦了！', 'biz', 1, 1800)],
    'weekend': [L('wkd01', '周末也在忙吗？记得留点时间给自己哦。', 'smug', 1, 1800)],
    'season_spring': [L('sea_sp01', '春天到啦，窗外的花开了吗？', 'smile', 1, 1800)],
    'season_summer': [L('sea_su01', '天好热，多喝点水哦。', 'smile', 1, 1800)],
    'season_autumn': [L('sea_au01', '天气转凉了，记得加件衣服哦。', 'smug', 1, 1800)],
    'season_winter': [L('sea_wi01', '好冷呀……手暖和吗？', 'thinking', 1, 1800)],
    'hol_newyear': [L('hol_ny01', '新年快乐！今年也请多关照～', 'biz', 1, 3600)],
    'hol_newyear_eve': [L('hol_nye01', '今年最后一天啦，辛苦你了一整年。', 'smug', 1, 3600)],
    'hol_springfest': [L('hol_sf01', '过年好！新的一年，平平安安～', 'biz', 1, 3600)],
    'hol_springeve': [L('hol_se01', '除夕啦，要和家人好好吃顿饭哦。', 'smile', 1, 3600)],
    'hol_lantern': [L('hol_lt01', '元宵节快乐，吃汤圆了吗？', 'smile', 1, 3600)],
    'hol_valentine': [L('hol_vl01', '今天是情人节呢……嗯，你也要被好好对待哦。', 'smug', 1, 3600)],
    'hol_labor': [L('hol_lb01', '劳动节快乐！今天就别太劳动啦。', 'smile', 1, 3600)],
    'hol_children': [L('hol_ch01', '儿童节快乐～大人也可以过的哦。', 'biz', 1, 3600)],
    'hol_dragonboat': [L('hol_db01', '端午安康，粽子吃甜的还是咸的呀？', 'thinking', 1, 3600)],
    'hol_qixi': [L('hol_qx01', '七夕呢……今晚的星星应该很好看。', 'smug', 1, 3600)],
    'hol_teacher': [L('hol_tc01', '教师节呀，有想感谢的老师吗？', 'thinking', 1, 3600)],
    'hol_midautumn': [L('hol_ma01', '中秋快乐，记得抬头看看月亮～', 'smile', 1, 3600)],
    'hol_national': [L('hol_nt01', '国庆假期，出去玩还是在家歇着呀？', 'smile', 1, 3600)],
    'hol_1024': [L('hol_1024', '今天是程序员节！写代码的人都辛苦啦。', 'biz', 1, 3600)],
    'hol_halloween': [L('hol_hw01', '万圣节……我、我才不怕呢。', 'pout', 1, 3600)],
    'hol_xmas': [L('hol_xm01', '圣诞快乐～今天也暖暖的。', 'smile', 1, 3600)],
}

# 农历节日的公历日期（2026–2030，手动查表；过期后只是不触发，不影响别的功能）
LUNAR = {
    'hol_springfest': ['2026-02-17', '2027-02-06', '2028-01-26', '2029-02-13', '2030-02-03'],
    'hol_springeve': ['2026-02-16', '2027-02-05', '2028-01-25', '2029-02-12', '2030-02-02'],
    'hol_lantern': ['2026-03-03', '2027-02-20', '2028-02-09', '2029-02-27', '2030-02-17'],
    'hol_dragonboat': ['2026-06-19', '2027-06-09', '2028-05-28', '2029-06-16', '2030-06-05'],
    'hol_qixi': ['2026-08-19', '2027-08-08', '2028-08-26', '2029-08-16', '2030-08-05'],
    'hol_midautumn': ['2026-09-25', '2027-09-15', '2028-10-03', '2029-09-22', '2030-09-12'],
}
SOLAR = {  # (月, 起日, 止日)
    'hol_newyear': (1, 1, 1), 'hol_valentine': (2, 14, 14), 'hol_labor': (5, 1, 3), 'hol_children': (6, 1, 1),
    'hol_teacher': (9, 10, 10), 'hol_national': (10, 1, 7), 'hol_1024': (10, 24, 24), 'hol_halloween': (10, 31, 31),
    'hol_xmas': (12, 24, 25), 'hol_newyear_eve': (12, 31, 31),
}

# 主动问候的时段：(名字, 开始, 结束)，用「小时+分钟/60」表示
SLOTS = [('slot_morning', 6.5, 9.5), ('slot_lunch', 11.5, 13.0), ('slot_tea', 15.0, 16.0),
         ('slot_dinner', 17.5, 19.0), ('slot_late', 23.0, 24.0), ('slot_deep', 0.5, 4.5)]

DROP_EXT = {
    'drop_exe': 'exe msi bat cmd ps1 scr com vbs jar apk dll sys',
    'drop_lnk': 'lnk url',
    'drop_img': 'png jpg jpeg gif webp bmp heic tif tiff ico avif',
    'drop_psd': 'psd kra clip sai sai2 procreate xcf ai',
    'drop_doc': 'doc docx odt wps rtf pages',
    'drop_sheet': 'xls xlsx csv et ods numbers',
    'drop_ppt': 'ppt pptx key dps odp',
    'drop_pdf': 'pdf epub mobi',
    'drop_txt': 'txt md log',
    'drop_code': 'py js ts tsx jsx c cpp h hpp java go rs cs html css json yaml yml toml sh ipynb lua rb php kt swift',
    'drop_music': 'mp3 flac wav ogg m4a aac opus wma',
    'drop_video': 'mp4 mkv mov avi flv webm wmv m4v',
    'drop_zip': 'zip rar 7z tar gz bz2 xz tgz iso',
    'drop_font': 'ttf otf ttc woff woff2',
}
EXT2CAT = {e: cat for cat, es in DROP_EXT.items() for e in es.split()}


def all_lines():
    for cat, ls in LINES.items():
        for l in ls:
            yield cat, l


def hour_f(now=None):
    now = now or datetime.datetime.now()
    return now.hour + now.minute / 60


def current_slot(now=None):
    h = hour_f(now)
    for name, a, b in SLOTS:
        if a <= h < b:
            return name
    return None


def start_category(now=None):
    h = hour_f(now)
    if 5 <= h < 10.5: return 'start_morning'
    if 10.5 <= h < 18: return 'start_day'
    if 18 <= h < 23: return 'start_evening'
    return 'start_night'


def context_categories(now=None):
    """当下应景的类别 -> 权重倍数（混进点击台词池）"""
    now = now or datetime.datetime.now()
    out = {}
    ds = now.strftime('%Y-%m-%d')
    for cat, days in LUNAR.items():
        if ds in days: out[cat] = 3.0
    for cat, (m, d0, d1) in SOLAR.items():
        if now.month == m and d0 <= now.day <= d1: out[cat] = 3.0
    season = {12: 'winter', 1: 'winter', 2: 'winter', 3: 'spring', 4: 'spring', 5: 'spring',
              6: 'summer', 7: 'summer', 8: 'summer'}.get(now.month, 'autumn')
    out['season_' + season] = 0.6
    if now.weekday() == 4 and now.hour >= 17: out['friday_night'] = 1.5
    if now.weekday() >= 5: out['weekend'] = 0.8
    slot = current_slot(now)
    if slot: out[slot] = 2.0
    return out


def check():
    ids = [l.id for _, l in all_lines()]
    dup = {i for i in ids if ids.count(i) > 1}
    assert not dup, dup
    bad = [l for _, l in all_lines() if l.expr not in ('smile', 'smug', 'thinking', 'biz', 'pout')]
    assert not bad, bad
    banned = ['本小姐', '大发慈悲', '老板']
    for _, l in all_lines():
        for b in banned:
            assert b not in l.text, l
    return len(ids)


if __name__ == '__main__':
    print('lines', check())
