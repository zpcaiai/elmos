#!/usr/bin/env python3
"""Repository-owned, no-retry probes for supported production model APIs."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


SUPPORTED_PROVIDER_ADAPTERS = {
    "openai-responses-v1",
    "anthropic-messages-2023-06-01",
    "gemini-generate-content-v1beta",
}
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class ProviderAdapterError(ValueError):
    pass


def validate_provider_binding(binding: dict[str, Any]) -> None:
    adapter = binding.get("adapter")
    if isinstance(adapter, str) and adapter.startswith("REQUIRED"):
        return
    if adapter not in SUPPORTED_PROVIDER_ADAPTERS:
        raise ProviderAdapterError(f"unsupported provider adapter: {adapter}")
    for field in ("provider", "model", "credential_env", "probe_input"):
        if not isinstance(binding.get(field), str) or not binding[field]:
            raise ProviderAdapterError(f"provider binding requires {field}")
    expected_provider = {
        "openai-responses-v1": "openai",
        "anthropic-messages-2023-06-01": "anthropic",
        "gemini-generate-content-v1beta": "gemini",
    }[adapter]
    if binding["provider"] != expected_provider:
        raise ProviderAdapterError(
            f"adapter {adapter} requires provider={expected_provider}"
        )
    if len(binding["probe_input"].encode("utf-8")) > 1024:
        raise ProviderAdapterError("provider probe_input exceeds 1 KiB")
    tokens = binding.get("max_output_tokens")
    if not isinstance(tokens, int) or not 1 <= tokens <= 256:
        raise ProviderAdapterError("provider max_output_tokens must be between 1 and 256")


def build_provider_request(
    binding: dict[str, Any], credential: str, request_id: str
) -> urllib.request.Request:
    """Builds one exact provider request; callers must never retry it blindly."""
    validate_provider_binding(binding)
    adapter = binding["adapter"]
    model = binding["model"]
    prompt = binding["probe_input"]
    maximum = binding["max_output_tokens"]
    if not credential or "\n" in credential or "\r" in credential:
        raise ProviderAdapterError("provider credential is empty or malformed")
    if adapter == "openai-responses-v1":
        endpoint = "https://api.openai.com/v1/responses"
        body = {"model": model, "input": prompt, "max_output_tokens": maximum}
        headers = {
            "Authorization": f"Bearer {credential}",
            "X-Client-Request-Id": request_id,
        }
    elif adapter == "anthropic-messages-2023-06-01":
        endpoint = "https://api.anthropic.com/v1/messages"
        body = {
            "model": model,
            "max_tokens": maximum,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"x-api-key": credential, "anthropic-version": "2023-06-01"}
    else:
        encoded_model = urllib.parse.quote(model, safe="-._")
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{encoded_model}:generateContent"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": maximum},
        }
        headers = {"x-goog-api-key": credential}
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, method="POST")
    request.add_header("Accept", "application/json")
    request.add_header("Content-Type", "application/json")
    for name, value in headers.items():
        request.add_header(name, value)
    return request


def execute_provider_probe(
    binding: dict[str, Any],
    output_dir: Path,
    environ: dict[str, str] | None = None,
    opener: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    credential_name = binding["credential_env"]
    credential = env.get(credential_name, "")
    request_id = str(uuid.uuid4())
    try:
        request = build_provider_request(binding, credential, request_id)
        with opener(request, timeout=120) as response:
            status = response.getcode()
            body = response.read(MAX_RESPONSE_BYTES + 1)
            headers = response.headers
    except urllib.error.HTTPError as exc:
        # HTTPError is a known provider rejection only for 4xx other than
        # throttling/timeouts.  5xx/408/429 remain UNKNOWN because the provider
        # might have accepted work before returning an intermediary error.
        status = exc.code
        if status >= 500 or status in {408, 429}:
            return {"status": "UNKNOWN", "reason": f"HTTP_{status}", "attempts": 1}
        return {"status": "FAIL", "reason": f"HTTP_{status}", "attempts": 1}
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        return {
            "status": "UNKNOWN",
            "reason": f"transport outcome uncertain: {type(exc).__name__}",
            "attempts": 1,
        }
    if len(body) > MAX_RESPONSE_BYTES:
        return {"status": "UNKNOWN", "reason": "provider response exceeded 8 MiB", "attempts": 1}
    if status < 200 or status >= 300:
        return {"status": "FAIL", "reason": f"HTTP_{status}", "attempts": 1}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "UNKNOWN", "reason": "provider returned invalid JSON", "attempts": 1}
    if not isinstance(parsed, dict):
        return {"status": "UNKNOWN", "reason": "provider response is not an object", "attempts": 1}
    adapter = binding["adapter"]
    response_id = parsed.get("responseId" if adapter.startswith("gemini-") else "id")
    if not isinstance(response_id, str) or not response_id:
        for header in ("x-request-id", "request-id", "x-goog-request-id"):
            candidate = headers.get(header)
            if candidate:
                response_id = candidate
                break
    if not isinstance(response_id, str) or not response_id:
        return {"status": "UNKNOWN", "reason": "provider request identity missing", "attempts": 1}
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / "provider-runtime-response.json"
    artifact.write_bytes(body)
    return {
        "status": "PASS",
        "adapter": adapter,
        "provider": binding["provider"],
        "model": binding["model"],
        "provider_request_id": response_id,
        "client_request_id": request_id if adapter == "openai-responses-v1" else None,
        "response_artifact": artifact.name,
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "attempts": 1,
    }
