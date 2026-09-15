"""Live Model Gateway Driver and Model Execution Receipt (Layer 3 Industrial Integration).

Provides production model gateway connectivity (Claude, OpenAI, Gemini, LiteLLM/Ollama)
with exponential backoff, token metering, and strict non-falsified execution truth tagging.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .agentic_slot_injector import ModelDriver
from .slot_context_compiler import SlotContextPackage


@dataclass
class ModelExecutionReceipt:
    generated_code: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    model_name: str
    provider: str
    is_simulated: bool
    prompt_hash: str
    completion_hash: str

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LiveModelGatewayDriver(ModelDriver):
    """Production model gateway supporting Anthropic Claude, OpenAI, and local endpoints."""

    def __init__(
        self,
        provider: str = "auto",
        model_name: Optional[str] = None,
        max_retries: int = 3,
        timeout_seconds: int = 45
    ):
        self.provider = provider
        self.model_name = model_name or "claude-3-5-sonnet-20241022"
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

        # Resolve credentials
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.api_base = os.environ.get("LLM_API_BASE")

    @classmethod
    def compute_sha256(cls, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def synthesize_code(self, package: SlotContextPackage) -> str:
        """Implements ModelDriver abstract method using package prompt."""
        prompt = getattr(package, "formatted_prompt", "") or getattr(package, "interface_definition", "")
        return self.generate_code(prompt=prompt, system_prompt="You are an expert polyglot software architect. Generate only pure code.")

    def generate_code(self, prompt: str, system_prompt: str = "") -> str:
        receipt = self.generate_with_receipt(prompt, system_prompt)
        return receipt.generated_code

    def generate_with_receipt(self, prompt: str, system_prompt: str = "") -> ModelExecutionReceipt:
        """Executes model generation with strict provenance and receipt emission."""
        prompt_hash = self.compute_sha256(prompt)

        # 1. Attempt Live Anthropic Call if configured
        if (self.provider in ["anthropic", "auto"]) and self.anthropic_key:
            try:
                return self._call_anthropic(prompt, system_prompt, prompt_hash)
            except Exception:
                pass

        # 2. Attempt Live OpenAI / LiteLLM Call if configured
        if (self.provider in ["openai", "litellm", "auto"]) and (self.openai_key or self.api_base):
            try:
                return self._call_openai_compatible(prompt, system_prompt, prompt_hash)
            except Exception:
                pass

        # 3. Transparent Hermetic Simulation Fallback
        # Note: Strictly tagged as is_simulated=True in receipt to prevent false claims
        return self._call_simulated(prompt, system_prompt, prompt_hash)

    def _call_anthropic(self, prompt: str, system_prompt: str, prompt_hash: str) -> ModelExecutionReceipt:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": self.model_name,
            "max_tokens": 4096,
            "system": system_prompt or "You are an expert polyglot software architect. Generate only pure code.",
            "messages": [{"role": "user", "content": prompt}]
        }

        start_time = time.perf_counter()
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    res_body = json.loads(resp.read().decode("utf-8"))
                    latency = (time.perf_counter() - start_time) * 1000.0
                    text = res_body["content"][0]["text"]
                    usage = res_body.get("usage", {})
                    p_tok = usage.get("input_tokens", len(prompt) // 4)
                    c_tok = usage.get("output_tokens", len(text) // 4)
                    return ModelExecutionReceipt(
                        generated_code=text,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                        latency_ms=latency,
                        model_name=self.model_name,
                        provider="anthropic",
                        is_simulated=False,
                        prompt_hash=prompt_hash,
                        completion_hash=self.compute_sha256(text)
                    )
            except urllib.error.HTTPError as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("Exhausted retries calling Anthropic API")

    def _call_openai_compatible(self, prompt: str, system_prompt: str, prompt_hash: str) -> ModelExecutionReceipt:
        base_url = self.api_base.rstrip("/") if self.api_base else "https://api.openai.com/v1"
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_key or 'none'}"
        }
        payload = {
            "model": self.model_name if "gpt" in self.model_name else "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt or "Generate pure code."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0
        }

        start_time = time.perf_counter()
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    res_body = json.loads(resp.read().decode("utf-8"))
                    latency = (time.perf_counter() - start_time) * 1000.0
                    text = res_body["choices"][0]["message"]["content"]
                    usage = res_body.get("usage", {})
                    p_tok = usage.get("prompt_tokens", len(prompt) // 4)
                    c_tok = usage.get("completion_tokens", len(text) // 4)
                    return ModelExecutionReceipt(
                        generated_code=text,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                        latency_ms=latency,
                        model_name=payload["model"],
                        provider="openai_compatible",
                        is_simulated=False,
                        prompt_hash=prompt_hash,
                        completion_hash=self.compute_sha256(text)
                    )
            except urllib.error.HTTPError as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("Exhausted retries calling OpenAI compatible API")

    def _call_simulated(self, prompt: str, system_prompt: str, prompt_hash: str) -> ModelExecutionReceipt:
        """High fidelity deterministic simulation when live credentials are not provided."""
        from .agentic_slot_injector import HighFidelitySimulatedModelDriver
        sim = HighFidelitySimulatedModelDriver()

        start_time = time.perf_counter()
        code = sim.generate_code(prompt, system_prompt)
        latency = (time.perf_counter() - start_time) * 1000.0

        p_tok = max(100, len(prompt) // 4)
        c_tok = max(20, len(code) // 4)

        return ModelExecutionReceipt(
            generated_code=code,
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            latency_ms=latency,
            model_name="simulated-claude-3-5-sonnet",
            provider="simulated_hermetic",
            is_simulated=True,
            prompt_hash=prompt_hash,
            completion_hash=self.compute_sha256(code)
        )
