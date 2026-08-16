"""Provider configuration: full per-purpose model setup from environment.

Unlike a bare model name, a provider config covers WHERE the model runs
and HOW it is authenticated:

    {PURPOSE}_PROVIDER   anthropic | openai (openai covers every OpenAI-
                         compatible endpoint below)
    {PURPOSE}_BASE_URL   API endpoint (None = provider default)
    {PURPOSE}_API_KEY    authentication
    {PURPOSE}_MODEL      model identifier

PURPOSE is one of DECISION / PLANNING / VISION, so each role can point at
a completely different vendor without touching code.

Supported vendors (all aliases normalize to provider=openai):

    alias           vendor          base_url (example)
    --------------  --------------  -----------------------------------------
    openrouter      OpenRouter      https://openrouter.ai/api/v1
    deepseek        DeepSeek        https://api.deepseek.com
    qwen/dashscope  Alibaba Qwen    https://dashscope.aliyuncs.com/compatible-mode/v1
    glm/zhipu       Zhipu GLM       https://open.bigmodel.cn/api/paas/v4
    kimi/moonshot   Moonshot Kimi   https://api.moonshot.cn/v1
    ollama          Ollama (local)  http://localhost:11434/v1
    vllm / lm_studio / groq / mistral / together / perplexity
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Project root is two levels up from this file (llm/providers.py -> project/).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    """Load the project .env regardless of the caller's working directory."""
    load_dotenv(_PROJECT_ROOT / ".env")

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"

SUPPORTED_PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_OPENAI)

# Aliases that resolve to the OpenAI-compatible protocol.
OPENAI_COMPATIBLE_ALIASES = frozenset({
    "openai_compatible",
    # routers / aggregators
    "openrouter",
    # vendors with OpenAI-compatible endpoints
    "deepseek",
    "qwen", "dashscope",
    "glm", "zhipu",
    "kimi", "moonshot",
    "groq", "mistral", "together", "perplexity",
    # local / self-hosted
    "ollama", "vllm", "lm_studio",
})

DEFAULT_DECISION_MODEL = "claude-sonnet-4-5"


@dataclass(frozen=True)
class ProviderConfig:
    """Complete configuration for one model role."""

    purpose: str  # decision | planning | vision
    provider: str  # normalized: anthropic | openai
    model: str
    vendor: str = ""  # original alias: deepseek / openai / qwen / ...
    api_key: str = ""
    base_url: Optional[str] = None
    thinking: Optional[str] = None  # enabled/disabled/auto (DeepSeek & friends)
    thinking_effort: Optional[str] = None  # minimal/low/medium/high

    @property
    def is_anthropic(self) -> bool:
        return self.provider == PROVIDER_ANTHROPIC


def load_provider_config(
    purpose: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    thinking: Optional[str] = None,
    thinking_effort: Optional[str] = None,
) -> ProviderConfig:
    """Load a provider config from environment (overridable per call).

    Reads {PURPOSE}_PROVIDER / _BASE_URL / _API_KEY / _MODEL. Falls back
    to ANTHROPIC_API_KEY for keys when the purpose-specific key is empty,
    keeping old .env files working.
    """
    _load_env()
    P = purpose.upper()

    provider_name = (provider or os.getenv(f'{P}_PROVIDER') or '')
    if not provider_name:
        # legacy fallback: no provider configured -> anthropic
        provider_name = PROVIDER_ANTHROPIC
    provider_name = provider_name.lower().replace('-', '_')
    vendor_name = provider_name
    if provider_name in OPENAI_COMPATIBLE_ALIASES:
        provider_name = PROVIDER_OPENAI
    if provider_name not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported provider {provider_name!r}; use {SUPPORTED_PROVIDERS}")

    key = api_key or os.getenv(f'{P}_API_KEY') or os.getenv('ANTHROPIC_API_KEY') or ''
    # Key enforcement happens at client construction, not config load, so
    # config inspection works without secrets.

    model_name = (
        model
        or os.getenv(f'{P}_MODEL')
        or (DEFAULT_DECISION_MODEL if purpose == 'decision' else '')
    )
    if not model_name:
        raise ValueError(f"{P}_MODEL not set; see .env.example")

    thinking_value = thinking or os.getenv(f'{P}_THINKING') or None
    if thinking_value not in (None, 'enabled', 'disabled', 'auto'):
        raise ValueError(f'{P}_THINKING must be enabled/disabled/auto, got {thinking_value!r}')

    effort_value = thinking_effort or os.getenv(f'{P}_THINKING_EFFORT') or None
    if effort_value not in (None, 'minimal', 'low', 'medium', 'high', 'max'):
        raise ValueError(
            f'{P}_THINKING_EFFORT must be minimal/low/medium/high/max, got {effort_value!r}'
        )

    return ProviderConfig(
        purpose=purpose,
        provider=provider_name,
        vendor=vendor_name,
        model=model_name,
        api_key=key,
        base_url=base_url or os.getenv(f'{P}_BASE_URL') or None,
        thinking=thinking_value,
        thinking_effort=effort_value,
    )
