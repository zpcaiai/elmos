"""Bounded transports for real OpenAI- and Anthropic-compatible providers."""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import ContractViolation, NotConfigured
from .models import canonical_json
from .providers import JsonProviderAdapter, ProviderCapabilities

TokenProvider = Callable[[str], str]


class LiveProviderError(RuntimeError):
    """A bounded provider failure that never includes the credential value."""

    def __init__(self, provider: str, status_code: int, detail: str) -> None:
        super().__init__(f"{provider} provider request failed ({status_code}): {detail[:500]}")
        self.provider = provider
        self.status_code = status_code
        self.retryable = status_code in {0, 408, 409, 425, 429} or 500 <= status_code < 600


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


@dataclass(frozen=True, slots=True)
class LiveCompletionConfig:
    provider: str
    endpoint: str
    protocol: str
    region: str = "external"
    timeout_seconds: float = 60.0
    max_response_bytes: int = 4_194_304
    max_prompt_chars: int = 32_768
    max_output_tokens: int = 128

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlsplit(self.endpoint)
        if (
            not self.provider
            or self.protocol not in {"openai-responses", "openai-chat", "anthropic-messages"}
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ContractViolation("live provider endpoint/protocol is invalid")
        if (
            self.timeout_seconds <= 0
            or self.timeout_seconds > 300
            or self.max_response_bytes < 1024
            or self.max_response_bytes > 67_108_864
            or self.max_prompt_chars < 1
            or self.max_output_tokens < 1
        ):
            raise ContractViolation("live provider bounds are invalid")


class LiveCompletionTransport:
    """Transforms a bounded prompt into the provider-neutral completion contract."""

    def __init__(
        self,
        config: LiveCompletionConfig,
        token_provider: TokenProvider,
        *,
        opener: Any | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.config = config
        self.token_provider = token_provider
        context = ssl_context or ssl.create_default_context()
        self.opener = opener or urllib.request.build_opener(
            _NoRedirectHandler(), urllib.request.HTTPSHandler(context=context)
        )

    def __call__(self, provider: str, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if provider != self.config.provider:
            raise ContractViolation("live provider identity mismatch")
        model = str(request.get("model", ""))
        context = request.get("context")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", model) or not isinstance(context, Mapping):
            raise ContractViolation("live provider model/context is invalid")
        prompt = context.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > self.config.max_prompt_chars:
            raise ContractViolation("live provider prompt is absent or exceeds the configured limit")
        if request.get("tool_schemas"):
            raise ContractViolation("completion-only live transport rejects tool schemas")
        token = self.token_provider(provider)
        if not token:
            raise NotConfigured("live provider credential lease is unavailable")
        request_body, headers = self._request(model, prompt, token, request.get("idempotency_key"))
        http_request = urllib.request.Request(
            self.config.endpoint,
            data=canonical_json(request_body).encode("utf-8"),
            method="POST",
            headers=headers,
        )
        try:
            response = self.opener.open(http_request, timeout=self.config.timeout_seconds)
            try:
                self._assert_origin(response)
                raw = response.read(self.config.max_response_bytes + 1)
            finally:
                response.close()
        except urllib.error.HTTPError as error:
            detail = error.read(2048).decode("utf-8", errors="replace")
            raise LiveProviderError(provider, error.code, detail) from error
        except urllib.error.URLError as error:
            raise LiveProviderError(provider, 0, str(error.reason)) from error
        if len(raw) > self.config.max_response_bytes:
            raise ContractViolation("live provider response exceeds the configured limit")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ContractViolation("live provider response is not JSON") from error
        if not isinstance(value, Mapping):
            raise ContractViolation("live provider response is not an object")
        text, input_tokens, output_tokens, response_id = self._normalize(value)
        return {
            "kind": "completion",
            "summary": text,
            "provider_text": text,
            "status": "blocked",
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_micros": 0,
            },
            "checkpoint": {
                "provider_response_id": response_id,
                "protocol": self.config.protocol,
            },
        }

    def adapter(self) -> JsonProviderAdapter:
        capabilities = ProviderCapabilities(
            self.config.provider,
            supports_streaming=False,
            supports_tool_calls=False,
            supports_file_edit=False,
            supports_shell=False,
            regions=frozenset({self.config.region}),
            external_network_required=True,
            privacy_classes=frozenset({"public-test"}),
        )
        return JsonProviderAdapter(self.config.provider, self, capabilities=capabilities)

    def _request(
        self,
        model: str,
        prompt: str,
        token: str,
        idempotency_key: Any,
    ) -> tuple[Mapping[str, Any], dict[str, str]]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "elmos-openhands-qualification/1.0",
        }
        if isinstance(idempotency_key, str) and idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if self.config.protocol == "openai-responses":
            headers["Authorization"] = "Bearer " + token
            return {
                "model": model,
                "input": prompt,
                "max_output_tokens": self.config.max_output_tokens,
            }, headers
        if self.config.protocol == "openai-chat":
            headers["Authorization"] = "Bearer " + token
            return {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": self.config.max_output_tokens,
            }, headers
        headers.update(
            {
                "Authorization": "Bearer " + token,
                "x-api-key": token,
                "anthropic-version": "2023-06-01",
            }
        )
        return {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.config.max_output_tokens,
        }, headers

    def _assert_origin(self, response: Any) -> None:
        expected = urllib.parse.urlsplit(self.config.endpoint)
        actual = urllib.parse.urlsplit(str(response.geturl()))
        if (expected.scheme, expected.hostname, expected.port) != (
            actual.scheme,
            actual.hostname,
            actual.port,
        ):
            raise LiveProviderError(self.config.provider, 0, "cross-origin redirect rejected")

    def _normalize(self, value: Mapping[str, Any]) -> tuple[str, int, int, str]:
        usage = value.get("usage")
        usage_map = usage if isinstance(usage, Mapping) else {}
        response_id = str(value.get("id", ""))
        if self.config.protocol == "openai-responses":
            text = value.get("output_text")
            if not isinstance(text, str):
                text = _openai_response_text(value.get("output"))
            input_tokens = _nonnegative_int(usage_map.get("input_tokens"))
            output_tokens = _nonnegative_int(usage_map.get("output_tokens"))
        elif self.config.protocol == "openai-chat":
            text = _openai_chat_text(value.get("choices"))
            input_tokens = _nonnegative_int(usage_map.get("prompt_tokens"))
            output_tokens = _nonnegative_int(usage_map.get("completion_tokens"))
        else:
            text = _anthropic_text(value.get("content"))
            input_tokens = _nonnegative_int(usage_map.get("input_tokens"))
            output_tokens = _nonnegative_int(usage_map.get("output_tokens"))
        if not text.strip() or not response_id:
            raise ContractViolation("live provider response lacks text or response identity")
        return text, input_tokens, output_tokens, response_id


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ContractViolation("live provider usage is invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ContractViolation("live provider usage is invalid") from error
    if result < 0:
        raise ContractViolation("live provider usage is invalid")
    return result


def _openai_response_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if not isinstance(item, Mapping) or not isinstance(item.get("content"), list):
            continue
        for content in item["content"]:
            if isinstance(content, Mapping) and content.get("type") == "output_text":
                parts.append(str(content.get("text", "")))
    return "".join(parts)


def _openai_chat_text(value: Any) -> str:
    if not isinstance(value, list) or not value or not isinstance(value[0], Mapping):
        return ""
    message = value[0].get("message")
    return str(message.get("content", "")) if isinstance(message, Mapping) else ""


def _anthropic_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return "".join(
        str(item.get("text", ""))
        for item in value
        if isinstance(item, Mapping) and item.get("type") == "text"
    )
