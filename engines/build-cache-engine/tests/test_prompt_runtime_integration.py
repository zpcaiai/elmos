"""Server-owned prompt assembly invariants and persistence-safe projections."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from conftest import digest
from elmos_build_cache.canonical import canonical_json_text
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.prompt_cache import (
    PromptCompiler,
    PromptIdentity,
    PromptProvider,
    SegmentStability,
)
from elmos_build_cache.prompt_runtime import (
    SEMANTIC_PROMPT_ORDER,
    CanonicalPromptAssembler,
    CanonicalPromptInputs,
    ContextPromptFragment,
    CurrentPromptTurn,
    StablePromptSections,
)


def identity() -> PromptIdentity:
    return PromptIdentity(
        tenant_scope_digest=digest("1"),
        provider=PromptProvider.OPENAI,
        provider_namespace_digest=digest("2"),
        model="model-v1",
        effort_profile="high",
        tool_schema_digest=digest("3"),
        compatibility_digest=digest("4"),
    )


def stable_sections() -> StablePromptSections:
    return StablePromptSections(
        system="SYSTEM-CANARY API_KEY=never-persist-system",
        safety="SAFETY-CANARY never-persist-safety",
        tools="TOOLS-CANARY never-persist-tools",
        schema="SCHEMA-CANARY never-persist-schema",
        skills="SKILLS-CANARY never-persist-skills",
        repository="REPOSITORY-CANARY never-persist-repository",
    )


def fragment(sequence: int, event: str, content: str) -> ContextPromptFragment:
    return ContextPromptFragment(
        sequence=sequence,
        event_id=event,
        repository_snapshot_digest=digest("5"),
        event_digest=digest(chr(ord("a") + sequence - 1)),
        content=content,
    )


def inputs(
    *,
    context: tuple[ContextPromptFragment, ...] | None = None,
    turn_id: str = "turn-1",
    turn: str = "CURRENT-TURN-CANARY never-persist-turn",
) -> CanonicalPromptInputs:
    return CanonicalPromptInputs(
        identity=identity(),
        stable=stable_sections(),
        context=context or (fragment(1, "event-1", "CONTEXT-CANARY never-persist-context"),),
        current_turn=CurrentPromptTurn(turn_id=turn_id, content=turn),
    )


def test_canonical_assembler_enforces_exact_semantic_stability_order() -> None:
    assembly = CanonicalPromptAssembler().assemble(inputs())

    assert [section.value for section in SEMANTIC_PROMPT_ORDER] == [
        "system",
        "safety",
        "tools",
        "schema",
        "skills",
        "repository",
        "cache-boundary",
        "context",
        "current-turn",
    ]
    assert [section.semantic_section.value for section in assembly.sections] == [
        "system",
        "safety",
        "tools",
        "schema",
        "skills",
        "repository",
        "cache-boundary",
        "context",
        "current-turn",
    ]
    assert [section.stability for section in assembly.sections] == [
        *([SegmentStability.STABLE] * 7),
        SegmentStability.APPEND_ONLY,
        SegmentStability.VOLATILE,
    ]
    assert [segment.segment_id for segment in assembly.compiled.segments] == [
        "semantic-system",
        "semantic-safety",
        "semantic-tools",
        "semantic-schema",
        "semantic-skills",
        "semantic-repository",
        "semantic-cache-boundary",
        "context-000000000001-event-1",
        "current-turn",
    ]


def test_turn_changes_never_move_stable_prefix_or_enter_stable_bytes() -> None:
    assembler = CanonicalPromptAssembler()
    first = assembler.assemble(inputs())
    second = assembler.assemble(
        inputs(turn_id="turn-2", turn="DIFFERENT-TURN-CANARY never-persist-turn")
    )

    assert first.compiled.stable_prefix_digest == second.compiled.stable_prefix_digest
    assert first.compiled.cache_key == second.compiled.cache_key
    assert first.compiled.stable_text == second.compiled.stable_text
    assert first.compiled.full_prompt_digest != second.compiled.full_prompt_digest
    assert first.assembly_digest != second.assembly_digest
    assert "CURRENT-TURN-CANARY" not in first.compiled.stable_text
    assert "DIFFERENT-TURN-CANARY" not in second.compiled.stable_text


def test_context_extension_is_append_only_without_rewriting_stable_prefix() -> None:
    assembler = CanonicalPromptAssembler()
    first = assembler.assemble(inputs())
    extended_context = (
        *inputs().context,
        fragment(2, "event-2", "SECOND-CONTEXT-CANARY never-persist-context"),
    )
    second = assembler.assemble(inputs(context=extended_context, turn_id="turn-2"))

    PromptCompiler.assert_append_only_successor(first.compiled, second.compiled)
    assert first.compiled.stable_prefix_digest == second.compiled.stable_prefix_digest
    assert second.compiled.append_segments[: len(first.compiled.append_segments)] == (
        first.compiled.append_segments
    )
    assert first.compiled.append_prefix_digest != second.compiled.append_prefix_digest


def test_manifest_restart_serialization_is_deterministic_and_content_free() -> None:
    first = CanonicalPromptAssembler().assemble(inputs())
    restarted = CanonicalPromptAssembler(PromptCompiler()).assemble(inputs())

    assert first.assembly_digest == restarted.assembly_digest
    assert canonical_json_text(first.manifest()) == canonical_json_text(restarted.manifest())
    rendered = json.dumps(first.manifest(), sort_keys=True)
    for forbidden in (
        "SYSTEM-CANARY",
        "never-persist-system",
        "CONTEXT-CANARY",
        "never-persist-context",
        "CURRENT-TURN-CANARY",
        "never-persist-turn",
        "API_KEY",
    ):
        assert forbidden not in rendered
    assert first.manifest()["semantic_order"] == [section.value for section in SEMANTIC_PROMPT_ORDER]
    assert all(section["content_digest"].startswith("sha256:") for section in first.manifest()["sections"])


def test_closed_typed_inputs_reject_reordering_duplicates_and_cross_snapshot() -> None:
    assembler = CanonicalPromptAssembler()
    with pytest.raises(ContractViolation, match="closed typed inputs"):
        assembler.assemble({"identity": identity()})  # type: ignore[arg-type]

    reversed_context = (
        fragment(2, "event-2", "later"),
        fragment(1, "event-1", "earlier"),
    )
    with pytest.raises(ContractViolation, match="strict append order"):
        inputs(context=reversed_context)

    duplicate_event = (
        fragment(1, "event-1", "first"),
        fragment(2, "event-1", "second"),
    )
    with pytest.raises(ContractViolation, match="duplicate event"):
        inputs(context=duplicate_event)

    foreign_snapshot = replace(fragment(2, "event-2", "foreign"), repository_snapshot_digest=digest("6"))
    with pytest.raises(ContractViolation, match="snapshot boundaries"):
        inputs(context=(fragment(1, "event-1", "local"), foreign_snapshot))
