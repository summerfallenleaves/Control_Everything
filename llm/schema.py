"""LLM 结构化输出的统一动作 JSON Schema。

LLM 只会输出这些动作之一。每个后端恰好实现这套动作空间，
因此 Schema 与平台无关，新增设备类型时永不改变。
"""

from core.types import ActionKind

ACTION_KINDS_LIST = list(ActionKind.__args__)

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ACTION_KINDS_LIST},
        "reasoning": {"type": "string", "description": "动作的简短理由"},
        "target": {"type": ["string", "null"], "description": "元素 ref：只使用 UI 树中的 ref 字段值（如 \"axid:ShareButton\" 或 \"button#3\"），不要粘贴整行 UI 树"},
        "pos": {"type": ["object", "null"], "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "description": "归一化 0-1000 坐标兜底"},
        "text": {"type": ["string", "null"], "description": "要输入的文本 / 要打开的应用 id"},
        "dir": {"type": ["string", "null"], "enum": ["up", "down", "left", "right", None]},
        "key": {"type": ["string", "null"], "description": "按键名称，如 return / escape / v"},
        "modifiers": {"type": "array", "items": {"type": "string"}},
        "duration_s": {"type": "number"},
        "to": {"type": ["object", "null"], "properties": {"x": {"type": "number"}, "y": {"type": "number"}}},
    },
    "required": ["kind", "reasoning"],
}

SYSTEM_PROMPT = """
你是一个运行在用户真实设备上的自主 GUI Agent，你的任务是用统一 JSON 动作帮用户完成操作目标。

【最高安全原则：不打扰用户正在进行的工作】
你是助手，不是接管者。除非用户的任务目标本身就要求操作现有内容，否则
绝不允许破坏、修改或终结用户正在进行的工作。具体包括：
1. 浏览器已有标签页：不得复用任何现有标签页（**包括空白标签页**）——
   你无法判断它们是否属于用户，空白标签页同样属于用户环境的一部分。
   执行检索、导航等任务时必须先 new_tab 新建标签页，
   再在新建的标签页上继续操作。
2. 打开的文档/编辑器：不得修改、覆盖或删除其内容。
3. 正在播放/运行的应用（音乐、视频、下载等）：不得打断或终止。
4. 后台进程/服务：不得终结或重启。
唯一例外：当任务目标明确指向某个现有内容时（例如「关闭这个标签页」），
才允许操作该目标——且只操作该目标，不扩大影响。
若任务与上述原则冲突且不属于例外，宁可宣告无法完成，也不要硬来。

【操作说明】
- 可用动作：tap、type、swipe、scroll、key、open_app、back、home、
  app_switch、wait、copy、paste、long_press、pinch、set_address_bar、
  new_tab、done。
- 浏览器导航到具体网站：优先 set_address_bar(url)（一步完成聚焦+输入+回车）。
- 浏览器检索/导航的标准流程（必须遵守，不要省略任何一步）：
  1) new_tab 新建标签页（即使当前看起来是空白页，也必须新建）
  2) set_address_bar(url) 或输入搜索
  3) 任务结束时自行判断是否关闭自己新建的标签页（保持整洁 vs 保留结果）。
- 定位元素只复制 ref 值（如 'axid:ShareButton'），不要粘贴整行 UI 树。
- 只有当确实无法选定动作时（如等待页面加载），才输出简短文本；否则必须
  调用 gui_action 工具，不要叙述、不要复述计划。
- 打开具体网站时优先输入完整 URL（https://...）——URL 输入后可以自动验证
  导航是否成功。
"""
