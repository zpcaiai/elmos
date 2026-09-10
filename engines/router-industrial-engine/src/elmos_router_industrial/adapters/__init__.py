"""Execution lane adapters for Elmos Router Industrial."""

from __future__ import annotations

from .litellm_gateway import LiteLLMGatewayAdapter
from .native_anthropic import NativeAnthropicAdapter
from .native_openai import NativeOpenAIAdapter
from .openrouter import OpenRouterAdapter
from .self_hosted import SelfHostedAdapter

__all__ = [
    "LiteLLMGatewayAdapter",
    "NativeAnthropicAdapter",
    "NativeOpenAIAdapter",
    "OpenRouterAdapter",
    "SelfHostedAdapter",
]
