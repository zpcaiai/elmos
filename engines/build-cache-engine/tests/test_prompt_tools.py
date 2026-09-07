from __future__ import annotations

import pytest

from elmos_build_cache.canonical import digest_of
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.prompt_cache import (
    PromptCompiler,
    PromptIdentity,
    PromptProvider,
    PromptSegment,
    SegmentStability,
)
from elmos_build_cache.prompt_tools import (
    PrefixMigrationMode,
    VolatilityCode,
    assert_cache_safe_prefix,
    first_prefix_difference,
    lint_stable_segments,
    plan_prefix_migration,
)


def _identity(**changes: object) -> PromptIdentity:
    values: dict[str, object] = {
        "tenant_scope_digest": digest_of("tenant"),
        "provider": PromptProvider.OPENAI,
        "provider_namespace_digest": digest_of("account"),
        "model": "gpt-test",
        "effort_profile": "high",
        "tool_schema_digest": digest_of("tools"),
        "compatibility_digest": digest_of("prompt-v1"),
    }
    values.update(changes)
    return PromptIdentity(**values)  # type: ignore[arg-type]


def _compile(stable: str, identity: PromptIdentity | None = None):  # type: ignore[no-untyped-def]
    return PromptCompiler().compile(
        identity or _identity(),
        (
            PromptSegment("policy", SegmentStability.STABLE, 0, stable),
            PromptSegment("history", SegmentStability.APPEND_ONLY, 0, "read a.py"),
            PromptSegment("task", SegmentStability.VOLATILE, 0, "change b.py"),
        ),
    )


def test_linter_reports_digests_and_never_echoes_matching_content() -> None:
    prompt = _compile("generated at 2026-08-20T12:30:00Z under /private/tmp/job-123")

    findings = lint_stable_segments(prompt)

    assert {item.code for item in findings} == {
        VolatilityCode.TIMESTAMP,
        VolatilityCode.TEMPORARY_PATH,
        VolatilityCode.ABSOLUTE_PATH,
    }
    rendered = repr([item.to_dict() for item in findings])
    assert "2026-08-20" not in rendered
    assert "/private/tmp" not in rendered
    assert all(item.segment_digest == prompt.stable_segments[0].content_digest for item in findings)


def test_linter_approval_is_exact_and_assertion_fails_closed() -> None:
    prompt = _compile("request_id=req-123456")

    with pytest.raises(ContractViolation, match="unapproved volatile"):
        assert_cache_safe_prefix(prompt)

    assert_cache_safe_prefix(
        prompt,
        approved=frozenset({("policy", VolatilityCode.REQUEST_IDENTIFIER)}),
    )


def test_prefix_diff_uses_fixed_identity_order_and_no_prompt_bytes() -> None:
    previous = _compile("stable policy")
    current = _compile("stable policy", _identity(model="gpt-other"))

    difference = first_prefix_difference(previous, current)

    assert difference is not None
    assert difference.dimension == "model"
    assert "gpt-other" not in repr(difference.to_dict())


def test_prefix_diff_finds_first_stable_segment_change() -> None:
    previous = _compile("policy one")
    current = _compile("policy two")

    difference = first_prefix_difference(previous, current)

    assert difference is not None
    assert difference.dimension == "stable_segment"
    assert difference.segment_id == "policy"
    assert "policy one" not in repr(difference.to_dict())
    assert "policy two" not in repr(difference.to_dict())


def test_prefix_migration_keeps_the_old_key_as_rollback() -> None:
    previous = _compile("policy one")
    current = _compile("policy two")

    plan = plan_prefix_migration(previous, current)

    assert plan.mode is PrefixMigrationMode.WARM_NEW_SERVE_OLD
    assert plan.changed
    assert plan.rollback_cache_key == previous.cache_key
    assert plan.old_cache_key != plan.new_cache_key


def test_unchanged_serve_migration_collapses_to_observe() -> None:
    previous = _compile("policy")
    current = _compile("policy")

    plan = plan_prefix_migration(
        previous,
        current,
        PrefixMigrationMode.SERVE_NEW_WITH_ROLLBACK,
    )

    assert plan.mode is PrefixMigrationMode.OBSERVE
    assert not plan.changed

