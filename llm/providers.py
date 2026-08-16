"""Provider configuration: full per-purpose model setup from environment.

Unlike a bare model name, a provider config covers WHERE the model runs
and HOW it is authenticated:

    {PURPOSE}_PROVIDER   anthropic | openai (openai also covers OpenAI-
                         compatible endpoints: DeepSeek, Moonshot, Qwen,
                         Ollama, vLLM, LM Studio, ...)
    {PURPOSE}_BASE_URL   API endpoint (None = provider default)
    {PURPOSE}_API_KEY    authentication
    {PURPOSE}_MODEL      model identifier

PURPOSE is one of DECISION / PLANNING / VISION, so each role can point at
a completely different vendor without touching code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"

SUPPORTED_PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_OPENAI)

DEFAULT_DECISION_MODEL = "claude-sonnet-4-5"


@dataclass(frozen=True)
class ProviderConfig:
    """Complete configuration for one model role."""

    purpose: str  # decision | planning | vision
    provider: str  # anthropic | openai
    model: str
    api_key: str = ""
    base_url: Optional[str] = None

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
) -> ProviderConfig:
    """Load a provider config from environment (overridable per call).

    Reads {PURPOSE}_PROVIDER / _BASE_URL / _API_KEY / _MODEL. Falls back
    to ANTHROPIC_API_KEY for keys when the purpose-specific key is empty,
    keeping old .env files working.
    """
    load_dotenv()
    P = purpose.upper()

    provider_name = (provider or os.getenv(f'{P}_PROVIDER') or '')
    if not provider_name:
        # legacy fallback: no provider configured -> anthropic
        provider_name = PROVIDER_ANTHROPIC
    provider_name = provider_name.lower().replace('-', '_')
    if provider_name in ('openai_compatible', 'ollama', 'vllm', 'lm_studio', 'deepseek', 'moonshot', 'qwen', 'zhipu', 'dashscope'):
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

    return ProviderConfig(
        purpose=purpose,
        provider=provider_name,
        model=model_name,
        api_key=key,
        base_url=base_url or os.getenv(f'{P}_BASE_URL') or None,
    )
