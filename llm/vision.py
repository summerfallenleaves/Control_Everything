"""Vision client: screenshot understanding via a multimodal model.

The decision model may be text-only (e.g. DeepSeek V4). The vision client
reads the screenshot with a multimodal model (e.g. qwen3.7-plus) and
produces a short text description that is injected into the decision
context - giving the text-only brain 'eyes'.
"""

from __future__ import annotations

import base64
import io
from typing import Any, Optional

from llm.client import LLMError
from llm.providers import PROVIDER_ANTHROPIC, ProviderConfig


def _image_to_data_url(image, max_width: int = 1280) -> str:
    """Resize a PIL image for token economy and encode as a data URL."""
    w, h = image.size
    if w > max_width:
        image = image.resize((max_width, int(h * max_width / w)))
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


class VisionClient:
    """Reads a screenshot with a multimodal model and describes it."""

    def __init__(self, cfg: ProviderConfig):
        if cfg.provider == PROVIDER_ANTHROPIC:
            raise LLMError("vision via the anthropic provider is not implemented yet")
        try:
            import openai
        except ImportError as e:
            raise LLMError("openai package not installed; `uv add openai`") from e
        kwargs = {}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        # Local endpoints (Ollama etc.) accept any non-empty key.
        self._client = openai.OpenAI(api_key=cfg.api_key or "not-needed", **kwargs)
        self.model = cfg.model
        self._cfg = cfg

    def describe(self, image, goal: str = '', platform: str = '', app: str = '') -> str:
        """Return a concise UI description for the agent."""
        prompt = (
            f'Goal: {goal or "(none)"}{chr(10)}'
            f'Platform: {platform}, app: {app}{chr(10)}'
            'Describe this screen for a GUI agent. Include:' + chr(10) +
            '- page/app title and main content' + chr(10) +
            '- interactive elements (buttons, input fields, links) with approximate positions' + chr(10) +
            '- especially any address bar / search field and what it currently shows' + chr(10) +
            'Answer in under 150 words.'
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
