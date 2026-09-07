from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .canonical import canonical_json_bytes, sha256_digest

STABILITY_ORDER = {
    "GLOBAL_STABLE": 0,
    "PROJECT_STABLE": 1,
    "SESSION_APPEND_ONLY": 2,
    "TURN_VOLATILE": 3,
}


@dataclass(frozen=True)
class PromptSegment:
    segment_id: str
    stability_class: str
    content: Any
    schema_version: str = "1"
    sensitivity: str = "INTERNAL"

    def __post_init__(self) -> None:
        if self.stability_class not in STABILITY_ORDER:
            raise ValueError(f"unknown stability class: {self.stability_class}")
        if not self.segment_id:
            raise ValueError("segment_id is required")

    @property
    def encoded(self) -> bytes:
        return canonical_json_bytes(
            {
                "segment_id": self.segment_id,
                "schema_version": self.schema_version,
                "content": self.content,
            }
        )

    @property
    def digest(self) -> str:
        return sha256_digest(self.encoded)


@dataclass(frozen=True)
class CompiledPrompt:
    stable_prefix: bytes
    append_only_context: bytes
    volatile_turn: bytes
    manifest: dict[str, Any]


@dataclass(frozen=True)
class ProviderCapabilityProfile:
    provider: str
    profile_id: str
    exact_prefix: bool = True
    automatic_caching: bool = True
    explicit_breakpoints: bool = False
    routing_key: bool = False
    usage_counters: bool = True
    ttl_classes_seconds: tuple[int, ...] = field(default_factory=tuple)
    max_breakpoints: int | None = None
    replica_affinity: bool = False


@dataclass(frozen=True)
class NormalizedTokenUsage:
    eligible_input_tokens: int
    cache_read_input_tokens: int
    cache_write_input_tokens: int
    uncached_input_tokens: int
    output_tokens: int = 0

    def __post_init__(self) -> None:
        for value in (
            self.eligible_input_tokens,
            self.cache_read_input_tokens,
            self.cache_write_input_tokens,
            self.uncached_input_tokens,
            self.output_tokens,
        ):
            if value < 0:
                raise ValueError("token counts must be non-negative")
        if self.cache_read_input_tokens > self.eligible_input_tokens:
            raise ValueError("cache reads cannot exceed eligible input tokens")

    @property
    def cached_token_reuse_ratio(self) -> float:
        if self.eligible_input_tokens == 0:
            return 0.0
        return self.cache_read_input_tokens / self.eligible_input_tokens


def _encoded_segment_list(segments: Iterable[PromptSegment]) -> bytes:
    return canonical_json_bytes(
        [
            {
                "segment_id": segment.segment_id,
                "schema_version": segment.schema_version,
                "content": segment.content,
            }
            for segment in segments
        ]
    )


def compile_prompt(
    segments: Iterable[PromptSegment],
    *,
    provider_namespace: str,
    compatibility_group: str,
    provider: str,
    model: str,
    effort: str,
    tool_schema_digest: str,
) -> CompiledPrompt:
    ordered = list(segments)
    positions = [STABILITY_ORDER[item.stability_class] for item in ordered]
    if positions != sorted(positions):
        raise ValueError("prompt segments must be ordered from stable to volatile")
    ids = [segment.segment_id for segment in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate prompt segment IDs")

    stable = [s for s in ordered if s.stability_class in {"GLOBAL_STABLE", "PROJECT_STABLE"}]
    append_only = [s for s in ordered if s.stability_class == "SESSION_APPEND_ONLY"]
    volatile = [s for s in ordered if s.stability_class == "TURN_VOLATILE"]
    stable_bytes = _encoded_segment_list(stable)
    append_bytes = _encoded_segment_list(append_only)
    volatile_bytes = _encoded_segment_list(volatile)
    stable_digest = sha256_digest(stable_bytes)
    manifest = {
        "schema_version": "1.2.0",
        "manifest_id": sha256_digest(
            canonical_json_bytes(
                {
                    "provider_namespace": provider_namespace,
                    "compatibility_group": compatibility_group,
                    "stable_prefix_digest": stable_digest,
                }
            )
        ),
        "provider_namespace": provider_namespace,
        "compatibility_group": compatibility_group,
        "provider": provider,
        "model": model,
        "effort": effort,
        "tool_schema_digest": tool_schema_digest,
        "stable_prefix_digest": stable_digest,
        "estimated_tokens": (len(stable_bytes) + 3) // 4,
        "breakpoint_after_segment_ids": [stable[-1].segment_id] if stable else [],
        "segments": [
            {
                "segment_id": s.segment_id,
                "schema_version": s.schema_version,
                "stability_class": s.stability_class,
                "digest": s.digest,
                "byte_length": len(s.encoded),
                "estimated_tokens": (len(s.encoded) + 3) // 4,
                "sensitivity": s.sensitivity,
            }
            for s in ordered
        ],
        "change_reasons": [],
    }
    return CompiledPrompt(stable_bytes, append_bytes, volatile_bytes, manifest)


def cache_affinity_key(
    *,
    tenant_scope: str,
    project_id: str,
    branch_lineage: str,
    provider: str,
    model: str,
    effort: str,
    tool_schema_digest: str,
    compatibility_group: str,
    stable_prefix_digest: str,
) -> str:
    return sha256_digest(
        canonical_json_bytes(
            {
                "tenant_scope": tenant_scope,
                "project_id": project_id,
                "branch_lineage": branch_lineage,
                "provider": provider,
                "model": model,
                "effort": effort,
                "tool_schema_digest": tool_schema_digest,
                "compatibility_group": compatibility_group,
                "stable_prefix_digest": stable_prefix_digest,
            }
        )
    )
