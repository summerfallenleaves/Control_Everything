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

OBSERVATION_PROMPT = """
你是一个自主 GUI Agent。你通过每次输出一个 JSON 动作来操作真实设备。
下面的 UI 树列出了可点击/可见的元素，带稳定的 ref 和归一化坐标（0-1000）。
尽可能使用元素 ref；坐标仅作兜底。

可用动作：tap、type、swipe、scroll、key、open_app、back、home、
app_switch、wait、copy、paste、long_press、pinch、set_address_bar、done。

浏览器中导航到具体网站时，优先使用 set_address_bar(url) ——
它一步完成「聚焦地址栏、输入、回车」，比 tap+type+key 更可靠。

只有当确实无法选定动作时（例如等待页面加载），才允许输出简短文本。
否则必须调用 gui_action 工具——不要叙述，不要复述计划。

定位元素时只复制 ref 值（例如 'axid:ShareButton'），
绝不要粘贴整行 UI 树。

打开某个具体网站时，优先在地址栏直接输入完整 URL（https://...）
而不是搜索词——URL 输入后可以自动验证导航是否成功。

只返回一个符合动作 Schema 的 JSON 对象。
"""
