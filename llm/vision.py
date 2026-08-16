"""视觉客户端：通过多模态模型理解截图。

决策模型可能是纯文本的（例如 DeepSeek V4）。视觉客户端用多模态模型
（例如 qwen3.7-plus）读取截图，产出一段简短的文本描述，注入决策上下文——
给纯文本大脑装上「眼睛」。
"""

from __future__ import annotations

import base64
import io
from typing import Any, Optional

from llm.client import LLMError
from llm.providers import PROVIDER_ANTHROPIC, ProviderConfig


def _image_to_data_url(image, max_width: int = 1280) -> str:
    """为节省 token 缩放 PIL 图片，并编码为 data URL。"""
    w, h = image.size
    if w > max_width:
        image = image.resize((max_width, int(h * max_width / w)))
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


class VisionClient:
    """用多模态模型读取截图并给出描述。"""

    def __init__(self, cfg: ProviderConfig):
        if cfg.provider == PROVIDER_ANTHROPIC:
            raise LLMError("经由 anthropic 供应商的视觉功能尚未实现")
        try:
            import openai
        except ImportError as e:
            raise LLMError("openai 包未安装；`uv add openai`") from e
        kwargs = {}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        # 本地端点（Ollama 等）接受任意非空 key。
        self._client = openai.OpenAI(api_key=cfg.api_key or "not-needed", **kwargs)
        self.model = cfg.model
        self._cfg = cfg

    def describe(self, image, goal: str = '', platform: str = '', app: str = '') -> str:
        """为 Agent 返回一段简明的界面描述。"""
        prompt = (
            f'目标: {goal or "(无)"}{chr(10)}'
            f'平台: {platform}, 应用: {app}{chr(10)}'
            '为 GUI Agent 描述这个屏幕。请包含：' + chr(10) +
            '- 页面/应用标题与主要内容' + chr(10) +
            '- 可交互元素（按钮、输入框、链接）及大致位置' + chr(10) +
            '- 尤其注意地址栏/搜索框及其当前显示内容' + chr(10) +
            '回答不超过 150 词。'
        )
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=1024,
            messages=[{'role': 'user', 'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': _image_to_data_url(image)}},
            ]}],
        )
        return (resp.choices[0].message.content or '').strip()
