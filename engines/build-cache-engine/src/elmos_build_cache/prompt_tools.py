"""Safe diagnostics and migration planning for canonical prompt prefixes.

Prompt bytes are deliberately accepted only at the compilation edge.  The
objects returned by this module contain bounded identifiers and digests, never
the segment content that triggered a finding.  This keeps prefix debugging
useful without turning logs or API responses into a second prompt store.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .canonical import digest_of
from .errors import ContractViolation
from .prompt_cache import CompiledPrompt, PromptSegment, SegmentStability


class VolatilityCode(StrEnum):
    TIMESTAMP = "TIMESTAMP"
    UUID = "UUID"
    ABSOLUTE_PATH = "ABSOLUTE_PATH"
    TEMPORARY_PATH = "TEMPORARY_PATH"
    REQUEST_IDENTIFIER = "REQUEST_IDENTIFIER"
    HOST_IDENTIFIER = "HOST_IDENTIFIER"


_VOLATILE_PATTERNS: tuple[tuple[VolatilityCode, re.Pattern[str]], ...] = (
    (
        VolatilityCode.TIMESTAMP,
        re.compile(r"\b\d{4}-\d{2}-\d{2}[T ][0-2]\d:[0-5]\d(?::[0-6]\d(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?\b"),
    ),
    (
        VolatilityCode.UUID,
        re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"),
    ),
    (
        VolatilityCode.TEMPORARY_PATH,
        re.compile(r"(?:^|[\s='\"])(?:/private)?/(?:tmp|var/folders)/[^\s'\"]+"),
    ),
    (
        VolatilityCode.ABSOLUTE_PATH,
        re.compile(r"(?:^|[\s='\"])(?:/[A-Za-z0-9_.-]+){2,}|\b[A-Za-z]:\\(?:[^\\\s]+\\)+[^\\\s]+"),
    ),
    (
        VolatilityCode.REQUEST_IDENTIFIER,
        re.compile(r"(?i)\b(?:request|trace|run|span)[_-]?id\s*[:=]\s*[A-Za-z0-9._:@/+\-]{6,}"),
    ),
    (
        VolatilityCode.HOST_IDENTIFIER,
        re.compile(r"(?i)\b(?:host|hostname|worker)[_-]?(?:id|name)?\s*[:=]\s*[A-Za-z0-9._-]{3,}"),
    ),
)


@dataclass(frozen=True)
class VolatilityFinding:
    segment_id: str
    code: VolatilityCode
    segment_digest: str
    match_digest: str

    def to_dict(self) -> dict[str, str]:
        return {
            "segment_id": self.segment_id,
            "code": self.code.value,
            "segment_digest": self.segment_digest,
            "match_digest": self.match_digest,
        }


def lint_stable_segments(
    prompt: CompiledPrompt,
    *,
    approved: frozenset[tuple[str, VolatilityCode]] = frozenset(),
) -> tuple[VolatilityFinding, ...]:
    """Return deterministic, content-free findings for stable segments.

    Approvals are exact ``(segment_id, code)`` pairs.  A broad global disable
    is intentionally not supported because it would make a later volatile
    field silently cache-stable.
    """

    findings: list[VolatilityFinding] = []
    for segment in prompt.stable_segments:
        for code, pattern in _VOLATILE_PATTERNS:
            if (segment.segment_id, code) in approved:
                continue
            for match in pattern.finditer(segment.content):
                findings.append(
                    VolatilityFinding(
                        segment_id=segment.segment_id,
                        code=code,
                        segment_digest=segment.content_digest,
                        match_digest=digest_of(match.group(0)),
                    )
                )
    return tuple(sorted(findings, key=lambda item: (item.segment_id, item.code, item.match_digest)))


def assert_cache_safe_prefix(
    prompt: CompiledPrompt,
    *,
    approved: frozenset[tuple[str, VolatilityCode]] = frozenset(),
) -> None:
    findings = lint_stable_segments(prompt, approved=approved)
    if findings:
        raise ContractViolation(
            "stable prompt prefix contains unapproved volatile fields",
            findings=[finding.to_dict() for finding in findings],
        )


@dataclass(frozen=True)
class PrefixDifference:
    dimension: str
    previous_digest: str
    current_digest: str
    segment_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "dimension": self.dimension,
            "previous_digest": self.previous_digest,
            "current_digest": self.current_digest,
            "segment_id": self.segment_id,
        }


def first_prefix_difference(
    previous: CompiledPrompt,
    current: CompiledPrompt,
) -> PrefixDifference | None:
    """Explain the first stable-prefix change without returning prompt bytes."""

    previous_identity = previous.identity.document()
    current_identity = current.identity.document()
    for dimension in (
        "tenant_scope_digest",
        "provider",
        "provider_namespace_digest",
        "model",
        "effort_profile",
        "tool_schema_digest",
        "compatibility_digest",
    ):
        before = previous_identity[dimension]
        after = current_identity[dimension]
        if before != after:
            return PrefixDifference(dimension, digest_of(before), digest_of(after))

    maximum = max(len(previous.stable_segments), len(current.stable_segments))
    for index in range(maximum):
        prior_segment = (
            previous.stable_segments[index] if index < len(previous.stable_segments) else None
        )
        next_segment = (
            current.stable_segments[index] if index < len(current.stable_segments) else None
        )
        if prior_segment == next_segment:
            continue
        segment_id = (
            next_segment.segment_id
            if next_segment is not None
            else prior_segment.segment_id
            if prior_segment
            else None
        )
        return PrefixDifference(
            "stable_segment",
            digest_of(None if prior_segment is None else prior_segment.manifest_entry()),
            digest_of(None if next_segment is None else next_segment.manifest_entry()),
            segment_id,
        )
    return None


class PrefixMigrationMode(StrEnum):
    OBSERVE = "OBSERVE"
    WARM_NEW_SERVE_OLD = "WARM_NEW_SERVE_OLD"
    SERVE_NEW_WITH_ROLLBACK = "SERVE_NEW_WITH_ROLLBACK"


@dataclass(frozen=True)
class PrefixMigrationPlan:
    mode: PrefixMigrationMode
    old_cache_key: str
    new_cache_key: str
    old_prefix_digest: str
    new_prefix_digest: str
    changed: bool
    rollback_cache_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "old_cache_key": self.old_cache_key,
            "new_cache_key": self.new_cache_key,
            "old_prefix_digest": self.old_prefix_digest,
            "new_prefix_digest": self.new_prefix_digest,
            "changed": self.changed,
            "rollback_cache_key": self.rollback_cache_key,
        }


def plan_prefix_migration(
    previous: CompiledPrompt,
    current: CompiledPrompt,
    mode: PrefixMigrationMode = PrefixMigrationMode.WARM_NEW_SERVE_OLD,
) -> PrefixMigrationPlan:
    """Create an explicit dual-key migration plan; never overwrite old keys."""

    if mode is PrefixMigrationMode.SERVE_NEW_WITH_ROLLBACK and previous.cache_key == current.cache_key:
        mode = PrefixMigrationMode.OBSERVE
    return PrefixMigrationPlan(
        mode=mode,
        old_cache_key=previous.cache_key,
        new_cache_key=current.cache_key,
        old_prefix_digest=previous.stable_prefix_digest,
        new_prefix_digest=current.stable_prefix_digest,
        changed=previous.stable_prefix_digest != current.stable_prefix_digest,
        rollback_cache_key=previous.cache_key,
    )


def prompt_segment(
    segment_id: str,
    stability: SegmentStability | str,
    ordinal: int,
    content: str,
) -> PromptSegment:
    """Small typed construction seam used by CLI/API parsers."""

    return PromptSegment(segment_id, SegmentStability(stability), ordinal, content)


__all__ = [
    "PrefixDifference",
    "PrefixMigrationMode",
    "PrefixMigrationPlan",
    "VolatilityCode",
    "VolatilityFinding",
    "assert_cache_safe_prefix",
    "first_prefix_difference",
    "lint_stable_segments",
    "plan_prefix_migration",
    "prompt_segment",
]
