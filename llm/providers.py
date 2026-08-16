"""供应商配置：从环境加载按用途区分的完整模型配置。

与裸的模型名不同，供应商配置覆盖了模型**在哪里运行**以及**如何认证**：

    {PURPOSE}_PROVIDER   anthropic | openai（openai 覆盖下方所有 OpenAI
                         兼容端点）
    {PURPOSE}_BASE_URL   API 端点（None = 供应商默认）
    {PURPOSE}_API_KEY    认证密钥
    {PURPOSE}_MODEL      模型标识

PURPOSE 是 DECISION / PLANNING / VISION 之一，因此每个角色都可以指向
完全不同的供应商而无需改代码。

支持的供应商（所有别名都归一化为 provider=openai）：

    别名            供应商            base_url（示例）
    --------------  --------------  -----------------------------------------
    openrouter      OpenRouter      https://openrouter.ai/api/v1
    deepseek        DeepSeek        https://api.deepseek.com
    qwen/dashscope  阿里云 Qwen      https://dashscope.aliyuncs.com/compatible-mode/v1
    glm/zhipu       智谱 GLM        https://open.bigmodel.cn/api/paas/v4
    kimi/moonshot   Moonshot Kimi   https://api.moonshot.cn/v1
    ollama          Ollama（本地）  http://localhost:11434/v1
    vllm / lm_studio / groq / mistral / together / perplexity
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# 项目根在本文件上两级（llm/providers.py -> 项目根/）。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    """无论调用方的工作目录在哪，都加载项目的 .env。"""
    load_dotenv(_PROJECT_ROOT / ".env")

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"

SUPPORTED_PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_OPENAI)

# 归一化到 OpenAI 兼容协议的别名。
OPENAI_COMPATIBLE_ALIASES = frozenset({
    "openai_compatible",
    # 路由 / 聚合
    "openrouter",
    # 提供 OpenAI 兼容端点的供应商
    "deepseek",
    "qwen", "dashscope",
    "glm", "zhipu",
    "kimi", "moonshot",
    "groq", "mistral", "together", "perplexity",
    # 本地 / 自托管
    "ollama", "vllm", "lm_studio",
})

DEFAULT_DECISION_MODEL = "claude-sonnet-4-5"


@dataclass(frozen=True)
class ProviderConfig:
    """一个模型角色的完整配置。"""

    purpose: str  # decision | planning | vision
    provider: str  # 归一化：anthropic | openai
    model: str
    vendor: str = ""  # 原始别名：deepseek / openai / qwen / ...
    api_key: str = ""
    base_url: Optional[str] = None
    thinking: Optional[str] = None  # enabled/disabled/auto（DeepSeek 等）
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
    """从环境加载供应商配置（每次调用可覆盖）。

    读取 {PURPOSE}_PROVIDER / _BASE_URL / _API_KEY / _MODEL。
    当用途专属 key 为空时回落到 ANTHROPIC_API_KEY，
    以兼容旧的 .env 文件。
    """
    _load_env()
    P = purpose.upper()

    provider_name = (provider or os.getenv(f'{P}_PROVIDER') or '')
    if not provider_name:
        # 兼容回退：未配置供应商 -> anthropic
        provider_name = PROVIDER_ANTHROPIC
    provider_name = provider_name.lower().replace('-', '_')
    vendor_name = provider_name
    if provider_name in OPENAI_COMPATIBLE_ALIASES:
        provider_name = PROVIDER_OPENAI
    if provider_name not in SUPPORTED_PROVIDERS:
        raise ValueError(f'不支持的供应商 {provider_name!r}；可用: {SUPPORTED_PROVIDERS}')

    key = api_key or os.getenv(f'{P}_API_KEY') or os.getenv('ANTHROPIC_API_KEY') or ''
    # 密钥检查推迟到客户端构造时进行，而不是配置加载时，
    # 这样没有密钥也能做配置检查。

    model_name = (
        model
        or os.getenv(f'{P}_MODEL')
        or (DEFAULT_DECISION_MODEL if purpose == 'decision' else '')
    )
    if not model_name:
        raise ValueError(f'{P}_MODEL 未设置；见 .env.example')

    thinking_value = thinking or os.getenv(f'{P}_THINKING') or None
    if thinking_value not in (None, 'enabled', 'disabled', 'auto'):
        raise ValueError(f'{P}_THINKING 必须为 enabled/disabled/auto，得到 {thinking_value!r}')

    effort_value = thinking_effort or os.getenv(f'{P}_THINKING_EFFORT') or None
    if effort_value not in (None, 'minimal', 'low', 'medium', 'high', 'max'):
        raise ValueError(
            f'{P}_THINKING_EFFORT 必须为 minimal/low/medium/high/max，得到 {effort_value!r}'
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
