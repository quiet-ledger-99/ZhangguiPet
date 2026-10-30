# -*- coding: utf-8 -*-
"""“说什么”的大脑。v0.3 只有离线的 LocalBrain（内置台词 + 冷却 + 权重）。

==== 给 v0.4 留的接口（可选的联网聊天 / TTS，默认关） ====
桌宠本体只通过下面两个接口要台词、出声，不关心台词从哪来：
    brain.line(category, ctx, strict=False) -> Line | None   # 同步、立刻返回，永远不能卡住界面
    brain.chat(text, ctx, on_reply)                 # 自由聊天；v0.3 不支持，返回 False
    speaker.speak(line)                             # 有预录语音就放，没有就静默
v0.4 计划新建 pet_online.py（只有用户在设置里填了 key 并打开开关时才 import）：
    class OnlineBrain(LocalBrain):   # 继承：联网失败/超时/没 key 时自动退回 LocalBrain 的台词
        chat(): 在后台线程（concurrent.futures）请求用户自己填的聊天 API，15 秒超时，
                要求模型返回 {"text": ..., "expr": "smile|smug|thinking|biz|pout"}（biz=回眸挥手，pout=合扇小嘴硬），
                回到主线程用 QTimer.singleShot(0, ...) 调 on_reply(Line)。
    class TTSSpeaker(Speaker):       # 有预录语音优先放预录；新台词才调用户自己的 TTS，音频缓存到配置目录
key 存储：Windows DPAPI（CryptProtectData，绑定当前用户）加密后存 %APPDATA%/ZhangguiPet/secrets.bin，
          不进 settings.json、不进日志、不进导出的诊断文件；只发给用户自己填的服务商地址。
"""
import random, time, collections
import pet_lines as PL


class LocalBrain:
    name = 'local'

    def __init__(self, order=None):
        self.used = {}                                # id -> 上次说的时间
        self.recent = collections.deque(maxlen=6)     # 最近说过的 id，尽量不复读
        self.order = list(order or [])                # 录屏用：固定台词顺序（台词 id 列表）

    def pick(self, weighted, strict=False):
        """weighted: {类别: 权重倍数}。按 权重×倍数 加权随机；冷却中的不选，最近说过的尽量不选。
        strict=True（v0.3.5）：冷却中的台词绝对不选——全都在冷却就返回 None（她这次不说话）。
        strict=False（普通点击）：都在冷却时退回“除了刚说的那句都行”，保证点她一定有回应。
        录屏用的固定顺序（order）优先于冷却。"""
        now = time.time()
        if self.order:
            want = self.order[0]
            for cat in weighted:
                for l in PL.LINES.get(cat, []):
                    if l.id == want:
                        self.order.pop(0)
                        return self._mark(l, now)
        pool = [(l, l.w * m) for cat, m in weighted.items() for l in PL.LINES.get(cat, [])]
        if not pool:
            return None
        ready = [(l, w) for l, w in pool if self.ready(l, now)]
        if strict and not ready:
            return None
        fresh = [(l, w) for l, w in ready if l.id not in self.recent]
        if not fresh:
            if strict:
                fresh = [(l, w) for l, w in ready if l.id not in list(self.recent)[-1:]] or ready
            else:
                fresh = [(l, w) for l, w in pool if l.id not in list(self.recent)[-1:]] or pool
        tot = sum(w for _, w in fresh)
        r = random.uniform(0, tot)
        for l, w in fresh:
            r -= w
            if r <= 0:
                return self._mark(l, now)
        return self._mark(fresh[-1][0], now)

    def ready(self, l, now=None):
        """这句冷却好了吗"""
        return (now if now is not None else time.time()) - self.used.get(l.id, -1e9) >= l.cd

    def _mark(self, l, now):
        self.used[l.id] = now
        self.recent.append(l.id)
        return l

    def line(self, category, ctx=None, strict=False):
        if category == 'poke':
            w = {'poke': 1.0}
            for cat, m in PL.context_categories().items():
                w[cat] = m * 0.35          # 应景台词偶尔混进来
            return self.pick(w, strict=strict)
        return self.pick({category: 1.0}, strict=strict)

    def chat(self, text, ctx, on_reply):
        return False                                  # v0.3：离线版没有自由聊天
