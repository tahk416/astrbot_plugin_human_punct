# -*- coding: utf-8 -*-
"""human_punct: 发送前把回复洗得更像真人打字。

标点清洗（v1.0）：
  1. 句号「。」删除（句中变空格，句尾直接没了）；半角「.」仅当
     不属于 URL/版本号/文件名形态时才当句号处理
  2. 逗号「，」变空格；半角「,」保护 1,000 这类千分位
  3. 分号「；」变空格（半角「;」同理保护）
  4. 折叠连排空格、去行尾悬挂空格、压缩多余空行、去整段首尾空白

拟人分段（v1.1 新增）：
  清洗后仍超过 min_chars（默认 80）的长文本，按空格/换行切成多条
  ≤max_chars（默认 50）的短消息，替换消息链——AstrBot 核心的
  respond 阶段会把多个 Plain 组件逐条发送并带 1.5~3.5s 间隔。
  背景：核心自带的"分段回复"只处理 ≤80 字的短文本（>80 直接原样
  发送），而标点清洗又把句号刀口洗没了，长回复会整坨发出。

挂载：on_decorating_result 钩子，priority=-100 排在最后执行——
正常回复走核心 ResultDecorateStage、主动消息走 proactive_chat 的装饰钩子，
两条链路都派发该事件；meme_manager(99999) / AstrNa(1000) 等先装饰完，
本插件最后统一洗文本。

安全边界：含代码块(```)的整段跳过（也不分段）；清洗后整段为空则还原原文。
"""

import re

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import Plain

CODE_FENCE = "```"

# 半角标点挨着这些字符时多半是数字千分位/版本号/域名/标识符，别动
_ALNUM = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
)

_URL_TAIL = re.compile(r"^(com|cn|net|org|edu|gov|io|me|cc|top|xyz|info|jp|us|uk|de|fr|ru|html?|s?htm|php|json|ya?ml|png|jpe?g|gif|webp|mp[34]|pdf|zip|exe)\b", re.I)


def _is_cjk(ch: str) -> bool:
    """常见中日韩汉字 + 常用中文标点（判断语境用）。"""
    if not ch:
        return False
    o = ord(ch)
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x3000 <= o <= 0x303F:
        return True
    return ch in "，。！？；：、（）“”‘’《》【】〈〉「」『』"


def _keep_halfwidth(buf: str, rest: str, mark: str) -> bool:
    """刚遇到半角 mark：buf=其左侧文本，rest=其右侧剩余文本。True=保留。"""
    prev = buf[-1] if buf else ""
    nxt = rest[0] if rest else ""
    if _URL_TAIL.match(rest):  # .com / .html 之类的尾巴
        return True
    if mark == "." and prev and not prev.isdigit():
        # "Hello. 然后走了"：点后是空格+中文 → 中文语境的句号，删
        # 点后紧跟数字（1.2.6）或紧跟英文（main.py）不会命中这条
        probe = rest.lstrip(" \t")
        if probe[:1] and _is_cjk(probe[0]) and rest[:1] in " \t":
            return False
    if prev in _ALNUM or nxt in _ALNUM:  # 1.2.6 / 1,000 / a.exe / main.py
        return True
    if mark == "." and prev and buf[-4:].find("www") != -1:
        return True
    if _is_cjk(prev) and not _is_cjk(nxt):
        # 中文后面跟半角标点再接英文（少见），保守保留
        return True
    return False


def _swap(t: str, half: str) -> str:
    """把文本中该处理位置的半角标点换成空格。"""
    out: list[str] = []
    i = 0
    n = len(t)
    while i < n:
        ch = t[i]
        if ch == half and not _keep_halfwidth("".join(out), t[i + 1 :], half):
            out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def clean_text(text: str, cfg: dict) -> str | None:
    """按配置清洗一段文本。返回 None 表示保留原样不动。"""
    if not text:
        return None
    if cfg.get("skip_code_block", True) and CODE_FENCE in text:
        return None

    halfwidth = bool(cfg.get("halfwidth_too", True))
    t = text

    if cfg.get("drop_period", True):
        t = t.replace("。", " ")
        if halfwidth:
            t = _swap(t, ".")
    if cfg.get("comma_to_space", True):
        t = t.replace("，", " ")
        if halfwidth:
            t = _swap(t, ",")
    if cfg.get("semicolon_to_space", True):
        t = t.replace("；", " ")
        if halfwidth:
            t = _swap(t, ";")

    if cfg.get("whitespace_collapse", True):
        t = re.sub(r"[ \t]{2,}", " ", t)  # 折叠连排空格
        t = re.sub(r"[ \t]+\n", "\n", t)  # 行尾悬挂空格
        t = re.sub(r"\n{3,}", "\n\n", t)  # 压缩空行
    # 每行去首尾空白（真人不打悬挂空格）
    t = "\n".join(ln.strip(" \t") for ln in t.split("\n"))

    if not t.strip() and text.strip():
        # 全洗没了（原文就一个标点）：还原，宁可不洗也别发空气
        return None
    return t


def split_segments(text: str, min_chars: int, max_chars: int) -> list[str]:
    """清洗后的长文本按换行/空格切成多条 ≤max_chars 的短消息。

    返回段数 <=1 表示不需要（或无法）分段，调用方保持原样。
    """
    if len(text) <= min_chars:
        return [text]

    pieces: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) <= max_chars:
            pieces.append(line)
            continue
        buf = ""
        for word in line.split(" "):
            cand = word if not buf else f"{buf} {word}"
            if len(cand) <= max_chars:
                buf = cand
                continue
            if buf:
                pieces.append(buf)
            # 单个词就超长（无空格可切）：硬切
            while len(word) > max_chars:
                pieces.append(word[:max_chars])
                word = word[max_chars:]
            buf = word
        if buf:
            pieces.append(buf)

    # 合并末尾过碎的短段（避免"…了 然"这种单字尾巴）
    merged: list[str] = []
    for p in pieces:
        if merged and len(p) < 6 and len(merged[-1]) + len(p) + 1 <= max_chars:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged


def _pack_lines(lines: list[str], pack_limit: int) -> list[str]:
    """把短行打包成 ≤pack_limit 的组件，行间用 \\n 连接。

    目的：两条发送链路都会按 \\n 再拆回去——
    · 普通回复：核心 respond 逐 Plain 组件分条发送（组件内 ≤80 字还会被它的
      分段正则按 \\n 拆开），每条一个气泡；
    · 主动消息：proactive_chat 的分段器对 ≤80 字组件按 \\n 拆分，组件数变多
      → 触发它的"分段连发"模式，逐条发送带间隔。
    直接把每行做成一个组件反而不行：两条链路都会把多个 Plain 合并成一条消息。
    """
    packs: list[str] = []
    buf = ""
    for ln in lines:
        if not buf:
            buf = ln
            continue
        cand = f"{buf}\n{ln}"
        if len(cand) <= pack_limit:
            buf = cand
        else:
            packs.append(buf)
            buf = ln
    if buf:
        packs.append(buf)
    return packs


@register(
    "astrbot_plugin_human_punct",
    "大肥鱼",
    "发送前清洗标点更像真人：去句号、逗号变空格",
    "1.1.1",
    "local",
)
class HumanPunct(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    def _cfg(self) -> dict:
        return {
            "drop_period": bool(self.config.get("drop_period", True)),
            "comma_to_space": bool(self.config.get("comma_to_space", True)),
            "semicolon_to_space": bool(self.config.get("semicolon_to_space", True)),
            "halfwidth_too": bool(self.config.get("halfwidth_too", True)),
            "skip_code_block": bool(self.config.get("skip_code_block", True)),
            "whitespace_collapse": bool(self.config.get("whitespace_collapse", True)),
        }

    @property
    def _segment_cfg(self) -> tuple[bool, int, int]:
        enable = bool(self.config.get("segment_enable", True))
        try:
            min_chars = int(self.config.get("segment_min_chars", 80))
            max_chars = int(self.config.get("segment_max_chars", 50))
        except (TypeError, ValueError):
            min_chars, max_chars = 80, 50
        min_chars = max(20, min_chars)
        max_chars = max(10, min(max_chars, min_chars))  # 段长不能超过触发线
        # 打包上限固定 80：两条发送链路对"组件内再拆分"的阈值都是 80
        return enable, min_chars, max_chars

    @filter.on_decorating_result(priority=-100)
    async def humanize_before_send(self, event: AstrMessageEvent):
        if not bool(self.config.get("enable", True)):
            return
        result = event.get_result()
        if not result or not result.chain:
            return

        cfg = self._cfg()
        seg_on, seg_min, seg_max = self._segment_cfg
        # 主动消息链路（proactive_chat 伪事件）会把整条链一次发出，只有它自己的
        # 分段器把组件数变多才逐条连发；而它的分段正则认 \n、核心 respond 逐组件
        # 分条发送。所以：主动事件 → 打包成 ≤80 字多行组件（被 \n 拆开）；
        # 普通回复 → 每段一个组件（被 respond 逐条发）。
        is_proactive = type(event).__name__ == "ProactiveMessageEvent"
        cleaned_n = 0
        split_n = 0
        new_chain: list = []
        for comp in result.chain:
            if isinstance(comp, Plain) and comp.text:
                new = clean_text(comp.text, cfg)
                if new is None:
                    new_chain.append(comp)
                    continue
                if new != comp.text:
                    cleaned_n += 1
                if seg_on and len(new) > seg_min:
                    segs = split_segments(new, seg_min, seg_max)
                    if len(segs) > 1:
                        if is_proactive:
                            new_chain.extend(Plain(p) for p in _pack_lines(segs, 80))
                        else:
                            new_chain.extend(Plain(s) for s in segs)
                        split_n += 1
                        continue
                comp.text = new
                new_chain.append(comp)
            else:
                new_chain.append(comp)

        if split_n:
            result.chain = new_chain
        if cleaned_n or split_n:
            logger.debug(
                f"[human_punct] 清洗 {cleaned_n} 段，长文打包 {split_n} 组分条发喵"
            )
