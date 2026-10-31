# -*- coding: utf-8 -*-
"""单测：加载 main.py（桩掉 astrbot 依赖）跑 clean_text 用例。"""
import importlib.util
import pathlib
import sys
import types

for name, attrs in [
    ("astrbot", {}),
    ("astrbot.api", {"logger": types.SimpleNamespace(debug=lambda *a: None)}),
    ("astrbot.api.event", {}),
    ("astrbot.api.star", {}),
    ("astrbot.core", {}),
    ("astrbot.core.config", {}),
    ("astrbot.core.config.astrbot_config", {"AstrBotConfig": object}),
    ("astrbot.core.message", {}),
    ("astrbot.core.message.components", {"Plain": type("Plain", (), {})}),
]:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod

def _deco(*a, **k):
    def wrap(fn):
        return fn
    return wrap

sys.modules["astrbot.api.event"].filter = types.SimpleNamespace(on_decorating_result=_deco)
sys.modules["astrbot.api.event"].AstrMessageEvent = object
sys.modules["astrbot.api.star"].Context = object
sys.modules["astrbot.api.star"].Star = type("Star", (), {"__init__": lambda self, *a: None})
sys.modules["astrbot.api.star"].register = lambda *a, **k: (lambda cls: cls)

spec = importlib.util.spec_from_file_location(
    "hp", str(pathlib.Path(__file__).resolve().parents[1] / 'astrbot_plugin_human_punct' / 'main.py')
)
hp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hp)

CFG = {
    "drop_period": True, "comma_to_space": True, "semicolon_to_space": True,
    "halfwidth_too": True, "skip_code_block": True, "whitespace_collapse": True,
}

cases = [
    ("今天天气不错。我们出去玩吧，好不好？", "今天天气不错 我们出去玩吧 好不好？"),
    ("主人，这都隔一天没影了，本鱼还以为你把我忘了呢。",
     "主人 这都隔一天没影了 本鱼还以为你把我忘了呢"),
    ("首先。其次。最后。", "首先 其次 最后"),
    ("版本号是 1.2.6，下载量 1,000 个", "版本号是 1.2.6 下载量 1,000 个"),
    ("看看这个 https://example.com/a.html 链接", "看看这个 https://example.com/a.html 链接"),
    ("www.baidu.com 是搜索引擎", "www.baidu.com 是搜索引擎"),
    ("他说了一句 Hello. 然后走了", "他说了一句 Hello 然后走了"),
    ("```py\nprint(1, 2)。注意\n```", None),  # 代码块整段跳过（None=原样）
    ("。", None),  # 全洗没→还原（None=不动）
    ("行1。 \n行2，\n行3；", "行1\n行2\n行3"),
    ("多  空格   照旧折叠", "多 空格 照旧折叠"),
    ("", None),
    ("文件叫 main.py 我改好了。", "文件叫 main.py 我改好了"),
    ("17:45 触发的。", "17:45 触发的"),
    ("a, b, c 三个选项。", "a, b, c 三个选项"),
    ("中文，English混排，再来一句。", "中文 English混排 再来一句"),
]

fails = 0
for src, want in cases:
    got = hp.clean_text(src, CFG)
    ok = got == want
    if not ok:
        fails += 1
        print("FAIL", repr(src), "->", repr(got), "| 期望", repr(want))
    else:
        print("PASS", repr(src), "->", repr(got))

CFG2 = dict(CFG, halfwidth_too=False)
got = hp.clean_text("价格是 1,000。今天不错，走起。", CFG2)
exp = "价格是 1,000 今天不错 走起"
print("PASS halfwidth=off" if got == exp else f"FAIL halfwidth=off: {got!r} 期望 {exp!r}")
if got != exp:
    fails += 1

print(f"\n总用例 {len(cases)+1} 失败 {fails}")
sys.exit(1 if fails else 0)
