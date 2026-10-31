# 鱼洗标点（astrbot_plugin_human_punct）

让 AstrBot 的回复**更像真人打字**：发送前清洗标点——句号删掉、逗号变空格。

覆盖两条链路：**普通回复** 与 [astrbot_plugin_proactive_chat](https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat) 的**主动消息**。

## 效果示例

| 清洗前（LLM 原始输出） | 清洗后（实际发出） |
|---|---|
| `主人，这都隔一天没影了，本鱼还以为你把我忘了呢。` | `主人 这都隔一天没影了 本鱼还以为你把我忘了呢` |

## 规则

- `。` 删除：句中降级为空格，句尾直接消失
- `，` `；` → 空格
- `？` `！` **保留**（真人也会打，全删反而假）
- 半角 `.` `,` `;` 同样处理，但有智能保护，**不会误伤**：
  - 版本号 `1.2.6`、千分位 `1,000`、文件名 `main.py`
  - 网址 `www.baidu.com`、`https://example.com/a.html`
  - 例外：`Hello. 然后走了` 这种半角句号后接中文的，照删
- 折叠连排空格、清理行尾悬挂空白、压缩多余空行
- 含 ` ``` ` 代码块的回复整段跳过；清洗后整段为空自动还原原文

## 工作原理

挂在 `on_decorating_result` 事件钩子、`priority=-100`：

- AstrBot 按 priority **降序**执行钩子，本插件垫底——表情包等装饰类插件（meme_manager 是 99999）先跑完，本插件最后统一洗文本，互不打架
- 只修改消息链里的 `Plain` 文本组件，图片/语音/At 等组件原样通过
- proactive_chat 发送前也会派发同一钩子（其源码 `_run_decorating_hooks` 与核心 ResultDecorateStage 对齐），所以主动消息同样被清洗

## 安装

1. 下载 Releases 里的 zip
2. AstrBot WebUI → 插件页 → `➕` → 从文件安装
3. 即装即用，无需配置；需要的话在插件配置里微调开关

要求 AstrBot ≥ 4.x（钩子与 priority 机制为通用特性，开发实测于 v4.29.1）

## 配置项

| 键 | 默认 | 说明 |
|---|---|---|
| `enable` | ✅ | 总开关 |
| `drop_period` | ✅ | 处理句号 `。`/`.` |
| `comma_to_space` | ✅ | 处理逗号 `，`/`,` |
| `semicolon_to_space` | ✅ | 处理分号 `；`/`;` |
| `halfwidth_too` | ✅ | 是否同时处理半角标点（含上述保护逻辑） |
| `skip_code_block` | ✅ | 跳过含 ``` 代码块的回复 |
| `whitespace_collapse` | ✅ | 折叠多余空格/空行 |

保存配置后 AstrBot 自动热重载，无需重启。

## 许可

MIT

---

由「大肥鱼」编写，饭票监工。单测 17 用例覆盖全部保护场景。
