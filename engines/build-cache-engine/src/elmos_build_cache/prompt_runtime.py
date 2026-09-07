"""Server-owned canonical prompt assembly over the deterministic compiler.

Raw prompt material exists only in the transient typed request and the returned
``CompiledPrompt`` needed by an in-process provider adapter.  Every manifest or
explanation produced here contains only closed identifiers, byte counts and
digests; this module has no persistence or provider/network capability.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .canonical import digest_of, require_digest, sha256_bytes
from .errors import ContractViolation
from .prompt_cache import (
    CompiledPrompt,
    PromptCompiler,
    PromptIdentity,
    PromptSegment,
    SegmentStability,
)
from .prompt_tools import assert_cache_safe_prefix

PROMPT_RUNTIME_SCHEMA_VERSION = "1.0.0"
MAX_TRANSIENT_SECTION_BYTES = 1 * 1024 * 1024

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}$")


class SemanticPromptSection(StrEnum):
    SYSTEM = "system"
    SAFETY = "safety"
    TOOLS = "tools"
    SCHEMA = "schema"
    SKILLS = "skills"
    REPOSITORY = "repository"
    CACHE_BOUNDARY = "cache-boundary"
    CONTEXT = "context"
    CURRENT_TURN = "current-turn"


SEMANTIC_PROMPT_ORDER = tuple(SemanticPromptSection)


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded identifier", field=field)
    return value


def _transient_text(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be text", field=field)
    normalized = unicodedata.normalize(
        "NFC",
        value.replace("\r\n", "\n").replace("\r", "\n"),
    )
    size = len(normalized.encode("utf-8"))
    if not normalized.strip() or size > MAX_TRANSIENT_SECTION_BYTES:
        raise ContractViolation(
            f"{field} must be non-blank and within the transient byte limit",
            field=field,
            maximum_bytes=MAX_TRANSIENT_SECTION_BYTES,
        )
    return normalized


@dataclass(frozen=True)
class StablePromptSections:
    """The fixed, server-owned stable sections and cache boundary marker."""

    system: str
    safety: str
    tools: str
    schema: str
    skills: str
    repository: str
    cache_boundary: str = "elmos-cache-boundary/v1.2"

    def __post_init__(self) -> None:
        for section in SEMANTIC_PROMPT_ORDER[:7]:
            field = section.value.replace("-", "_")
            object.__setattr__(self, field, _transient_text(getattr(self, field), field))

    def ordered(self) -> tuple[tuple[SemanticPromptSection, str], ...]:
        return tuple(
            (section, getattr(self, section.value.replace("-", "_")))
            for section in SEMANTIC_PROMPT_ORDER[:7]
        )


@dataclass(frozen=True)
class ContextPromptFragment:
    """One append-only ledger projection held transiently for prompt assembly."""

    sequence: int
    event_id: str
    repository_snapshot_digest: str
    event_digest: str
    content: str

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise ContractViolation("context sequence must be a positive integer")
        object.__setattr__(self, "event_id", _identifier(self.event_id, "event_id"))
        object.__setattr__(
            self,
            "repository_snapshot_digest",
            require_digest(self.repository_snapshot_digest),
        )
        object.__setattr__(self, "event_digest", require_digest(self.event_digest))
        object.__setattr__(self, "content", _transient_text(self.content, "context content"))

    @property
    def content_digest(self) -> str:
        return sha256_bytes(self.content.encode("utf-8"))

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "repository_snapshot_digest": self.repository_snapshot_digest,
            "event_digest": self.event_digest,
            "content_digest": self.content_digest,
            "content_bytes": len(self.content.encode("utf-8")),
        }


@dataclass(frozen=True)
class CurrentPromptTurn:
    turn_id: str
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "turn_id", _identifier(self.turn_id, "turn_id"))
        object.__setattr__(self, "content", _transient_text(self.content, "current turn"))


@dataclass(frozen=True)
class CanonicalPromptInputs:
    """Closed typed input; mappings and caller-selected order are not accepted."""

    identity: PromptIdentity
    stable: StablePromptSections
    context: tuple[ContextPromptFragment, ...]
    current_turn: CurrentPromptTurn

    def __post_init__(self) -> None:
        if not isinstance(self.identity, PromptIdentity):
            raise ContractViolation("canonical prompt identity has an invalid type")
        if not isinstance(self.stable, StablePromptSections):
            raise ContractViolation("canonical stable sections have an invalid type")
        fragments = tuple(self.context)
        if any(not isinstance(item, ContextPromptFragment) for item in fragments):
            raise ContractViolation("canonical context must contain typed fragments")
        if not isinstance(self.current_turn, CurrentPromptTurn):
            raise ContractViolation("canonical current turn has an invalid type")
        sequences = [item.sequence for item in fragments]
        event_ids = [item.event_id for item in fragments]
        snapshots = {item.repository_snapshot_digest for item in fragments}
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ContractViolation("context fragments must use a strict append order")
        if len(event_ids) != len(set(event_ids)):
            raise ContractViolation("context fragments contain duplicate event identities")
        if len(snapshots) > 1:
            raise ContractViolation("context fragments cross repository snapshot boundaries")
        object.__setattr__(self, "context", fragments)


@dataclass(frozen=True)
class PromptSectionExplanation:
    semantic_section: SemanticPromptSection
    stability: SegmentStability
    ordinal: int
    segment_id: str
    content_digest: str
    content_bytes: int
    source_event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_section": self.semantic_section.value,
            "stability": self.stability.value,
            "ordinal": self.ordinal,
            "segment_id": self.segment_id,
            "content_digest": self.content_digest,
            "content_bytes": self.content_bytes,
            "source_event_id": self.source_event_id,
        }


@dataclass(frozen=True)
class CanonicalPromptAssembly:
    """Transient compiled bytes plus a content-free explainable projection."""

    compiled: CompiledPrompt
    sections: tuple[PromptSectionExplanation, ...]

    def _manifest_body(self) -> dict[str, Any]:
        return {
            "schema_version": PROMPT_RUNTIME_SCHEMA_VERSION,
            "kind": "elmos.canonical-prompt-assembly/v1",
            "semantic_order": [section.value for section in SEMANTIC_PROMPT_ORDER],
            "compiled_prompt": self.compiled.manifest(),
            "sections": [section.to_dict() for section in self.sections],
        }

    @property
    def assembly_digest(self) -> str:
        return digest_of(self._manifest_body())

    def manifest(self) -> dict[str, Any]:
        """Return the only representation suitable for durable metadata."""

        return {**self._manifest_body(), "assembly_digest": self.assembly_digest}


class CanonicalPromptAssembler:
    """Enforce the semantic layout before delegating digest work to PromptCompiler."""

    def __init__(self, compiler: PromptCompiler | None = None) -> None:
        self.compiler = compiler or PromptCompiler()
        if not isinstance(self.compiler, PromptCompiler):
            raise ContractViolation("canonical prompt assembler requires PromptCompiler")

    def assemble(self, inputs: CanonicalPromptInputs) -> CanonicalPromptAssembly:
        if not isinstance(inputs, CanonicalPromptInputs):
            raise ContractViolation("canonical prompt assembly requires closed typed inputs")
        segments: list[PromptSegment] = []
        explanations: list[PromptSectionExplanation] = []

        for ordinal, (section, content) in enumerate(inputs.stable.ordered()):
            segment = PromptSegment(
                segment_id=f"semantic-{section.value}",
                stability=SegmentStability.STABLE,
                ordinal=ordinal,
                content=content,
            )
            segments.append(segment)
            explanations.append(self._explain(section, segment))

        for fragment in inputs.context:
            segment = PromptSegment(
                segment_id=f"context-{fragment.sequence:012d}-{fragment.event_id}",
                stability=SegmentStability.APPEND_ONLY,
                ordinal=fragment.sequence,
                content=fragment.content,
            )
            segments.append(segment)
            explanations.append(
                self._explain(
                    SemanticPromptSection.CONTEXT,
                    segment,
                    source_event_id=fragment.event_id,
                )
            )

        current = PromptSegment(
            segment_id="current-turn",
            stability=SegmentStability.VOLATILE,
            ordinal=0,
            content=inputs.current_turn.content,
        )
        segments.append(current)
        explanations.append(self._explain(SemanticPromptSection.CURRENT_TURN, current))
        compiled = self.compiler.compile(inputs.identity, segments)
        # The assembler is the canonical entry point; callers must not be able
        # to bypass the stable-prefix volatility linter by invoking it through
        # a lower-level compiler seam.
        assert_cache_safe_prefix(compiled)
        return CanonicalPromptAssembly(compiled=compiled, sections=tuple(explanations))

    @staticmethod
    def _explain(
        semantic_section: SemanticPromptSection,
        segment: PromptSegment,
        *,
        source_event_id: str | None = None,
    ) -> PromptSectionExplanation:
        return PromptSectionExplanation(
            semantic_section=semantic_section,
            stability=segment.stability,
            ordinal=segment.ordinal,
            segment_id=segment.segment_id,
            content_digest=segment.content_digest,
            content_bytes=len(segment.content.encode("utf-8")),
            source_event_id=source_event_id,
        )


__all__ = [
    "CanonicalPromptAssembler",
    "CanonicalPromptAssembly",
    "CanonicalPromptInputs",
    "ContextPromptFragment",
    "CurrentPromptTurn",
    "PROMPT_RUNTIME_SCHEMA_VERSION",
    "PromptSectionExplanation",
    "SEMANTIC_PROMPT_ORDER",
    "SemanticPromptSection",
    "StablePromptSections",
]
