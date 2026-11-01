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

# ---------- v1.1 分段测试 ----------
print("\n=== split_segments ===")
seg_cases = [
    # (输入文本, min, max, 期望段数或校验函数说明)
    ("短文本不分段", 80, 50, 1),                      # 低于触发线 → 原样
    ("嗯 本鱼知道了", 80, 50, 1),
]
for src, mn, mx, want_n in seg_cases:
    segs = hp.split_segments(src, mn, mx)
    ok = len(segs) == want_n
    print(("PASS" if ok else "FAIL"), repr(src), "->", segs)
    if not ok:
        fails += 1

# 长文本：模拟截图里那种 ~100 字回复
long_text = "好 那本鱼现在就趴在这 有事你喊一声 你悠哉悠哉 一起看海 一起聊聊天 主人 你悠哉悠哉 一起看海 一起聊 那本鱼就趴着等你说句话 主人你快点回来 本鱼给你留了半条鱼干 别在外面浪太久 记得按时吃饭 别老熬夜打游戏 熬夜对眼睛不好 对鱼鳍也不好"
segs = hp.split_segments(long_text, 80, 50)
checks = [
    (len(segs) > 1, f"长文应拆多条，实际 {len(segs)} 条"),
    (all(len(s) <= 50 for s in segs), f"每条应 ≤50 字: {[len(s) for s in segs]}"),
    (" ".join(segs).replace("  ", " ").strip() == long_text.strip() or
     sum(len(s) for s in segs) >= len(long_text) - 4 * len(segs),
     "内容不应大量丢失"),
]
for ok, msg in checks:
    print(("PASS" if ok else "FAIL"), msg)
    if not ok:
        fails += 1
for s in segs:
    print("   段:", s)

# 无空格的超长串：硬切不崩
no_space = "鱼" * 200
segs2 = hp.split_segments(no_space, 80, 50)
ok = all(len(s) <= 50 for s in segs2) and "".join(segs2) == no_space
print(("PASS" if ok else "FAIL"), f"无空格长串硬切 {len(segs2)} 段，内容完整")
if not ok:
    fails += 1

# 换行优先
multi = ("第一行内容" + "字" * 20 + "\n" + "第二行内容" + "字" * 20 + "\n" + "第三行" + "字" * 25)
segs3 = hp.split_segments(multi, 40, 50)
ok = len(segs3) >= 2 and all("\n" not in s for s in segs3)
print(("PASS" if ok else "FAIL"), f"换行按行拆: {len(segs3)} 段")
if not ok:
    fails += 1

# ---------- v1.1.1 _pack_lines（主动消息链路打包） ----------
print("\n=== _pack_lines ===")
pack_cases = [
    (["短", "也短"], 80, ["短\n也短"]),                      # 能并则并
    (["一" * 50, "二" * 50], 80, ["一" * 50, "二" * 50]),    # 并不下就分开
    ([], 80, []),
]
for lines, lim, want in pack_cases:
    got = hp._pack_lines(lines, lim)
    ok = got == want
    print(("PASS" if ok else "FAIL"), f"pack {lines[:1]}... -> {len(got)} 组")
    if not ok:
        fails += 1
        print("   got:", got, "want:", want)

# 打包后每组件 ≤80 且信息不丢
segs_long = hp.split_segments(long_text, 80, 50)
packed = hp._pack_lines(segs_long, 80)
ok = all(len(p) <= 80 for p in packed) and sum(len(p) for p in packed) >= len(long_text) - 4 * len(packed)
print(("PASS" if ok else "FAIL"), f"打包 {len(packed)} 组件，均 ≤80 字")
if not ok:
    fails += 1
# 模拟 proactive 分段器：≤80 组件按 \n 拆回多条
import re as _re
unseg = []
for p in packed:
    unseg += _re.findall(r".*?[。？！~…\n]+|.+$", p, _re.DOTALL | _re.MULTILINE)
unseg = [s for s in (x.strip() for x in unseg) if s]
ok = len(unseg) == len(segs_long)
print(("PASS" if ok else "FAIL"), f"proactive \\n 拆回 {len(unseg)} 条（原 {len(segs_long)} 段）")
if not ok:
    fails += 1

print(f"\n总失败 {fails}")
sys.exit(1 if fails else 0)
