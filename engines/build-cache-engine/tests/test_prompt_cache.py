from __future__ import annotations

import json
from dataclasses import replace

import pytest

from elmos_build_cache.errors import ContractViolation, IdempotencyConflict, Unsupported
from elmos_build_cache.prompt_cache import (
    AnthropicPromptCacheAdapter,
    CapabilityState,
    PromptCacheController,
    PromptCompiler,
    PromptIdentity,
    PromptProvider,
    PromptRequestClass,
    PromptSegment,
    ProviderAdapterRegistry,
    ProviderCacheMode,
    ProviderCachePolicy,
    ProviderCacheReason,
    ProviderCircuitBreaker,
    ProviderPromptCacheAdapter,
    RetryAccountingLedger,
    SegmentStability,
    SelfHostedPromptCacheAdapter,
    SelfHostedRuntimeProfile,
)


def d(character: str) -> str:
    return "sha256:" + character * 64


def identity(provider: PromptProvider = PromptProvider.OPENAI, **changes: object) -> PromptIdentity:
    values: dict[str, object] = {
        "tenant_scope_digest": d("1"),
        "provider": provider,
        "provider_namespace_digest": d("2"),
        "model": "model-v1",
        "effort_profile": "high",
        "tool_schema_digest": d("3"),
        "compatibility_digest": d("4"),
    }
    values.update(changes)
    return PromptIdentity(**values)  # type: ignore[arg-type]


def segments(volatile: str = "task", append: str = "read:a") -> tuple[PromptSegment, ...]:
    return (
        PromptSegment("turn", SegmentStability.VOLATILE, 0, volatile),
        PromptSegment("policy", SegmentStability.STABLE, 0, "policy\r\ntext"),
        PromptSegment("tools", SegmentStability.STABLE, 1, "tools"),
        PromptSegment("ledger-1", SegmentStability.APPEND_ONLY, 0, append),
    )


def test_compiler_enforces_stable_append_volatile_order_and_is_deterministic() -> None:
    compiler = PromptCompiler()
    first = compiler.compile(identity(), segments())
    second = compiler.compile(identity(), reversed(segments()))

    assert [item.segment_id for item in first.segments] == [
        "policy",
        "tools",
        "ledger-1",
        "turn",
    ]
    assert first == second
    assert first.stable_text == "policy\ntext\n\ntools"
    assert first.rendered_text.startswith(first.stable_text)


def test_volatile_changes_do_not_move_the_stable_prefix_or_cache_key() -> None:
    compiler = PromptCompiler()
    first = compiler.compile(identity(), segments(volatile="task-a"))
    second = compiler.compile(identity(), segments(volatile="task-b"))

    assert first.stable_prefix_digest == second.stable_prefix_digest
    assert first.cache_key == second.cache_key
    assert first.full_prompt_digest != second.full_prompt_digest


def test_every_identity_boundary_partitions_the_cache_key() -> None:
    compiler = PromptCompiler()
    baseline = compiler.compile(identity(), segments()).cache_key
    changes = (
        {"tenant_scope_digest": d("a")},
        {"provider_namespace_digest": d("b")},
        {"model": "model-v2"},
        {"effort_profile": "medium"},
        {"tool_schema_digest": d("c")},
        {"compatibility_digest": d("d")},
    )
    assert all(compiler.compile(identity(**change), segments()).cache_key != baseline for change in changes)


def test_duplicate_segment_identity_or_ordinal_fails_closed() -> None:
    compiler = PromptCompiler()
    duplicate_id = (
        PromptSegment("same", SegmentStability.STABLE, 0, "a"),
        PromptSegment("same", SegmentStability.VOLATILE, 0, "b"),
    )
    with pytest.raises(ContractViolation, match="duplicate prompt segment"):
        compiler.compile(identity(), duplicate_id)

    duplicate_position = (
        PromptSegment("a", SegmentStability.STABLE, 0, "a"),
        PromptSegment("b", SegmentStability.STABLE, 0, "b"),
    )
    with pytest.raises(ContractViolation, match="ambiguous prompt segment ordinal"):
        compiler.compile(identity(), duplicate_position)


def test_append_only_successor_rejects_history_rewrite() -> None:
    compiler = PromptCompiler()
    previous = compiler.compile(identity(), segments())
    extended = compiler.compile(
        identity(),
        (
            *segments(volatile="next"),
            PromptSegment("ledger-2", SegmentStability.APPEND_ONLY, 1, "read:b"),
        ),
    )
    compiler.assert_append_only_successor(previous, extended)

    rewritten = compiler.compile(identity(), segments(append="changed"))
    with pytest.raises(ContractViolation, match="history was rewritten"):
        compiler.assert_append_only_successor(previous, rewritten)


def test_registry_has_versioned_profiles_for_all_three_provider_classes() -> None:
    registry = ProviderAdapterRegistry.defaults()
    capabilities = registry.capabilities()
    assert {item["provider"] for item in capabilities} == {"openai", "anthropic", "self-hosted"}
    assert all(item["profile_version"] for item in capabilities)
    states = {item["provider"]: item["state"] for item in capabilities}
    assert states == {
        "openai": "SUPPORTED",
        "anthropic": "SUPPORTED",
        "self-hosted": "DEGRADED",
    }


def test_unmapped_provider_spi_fails_closed_instead_of_emitting_generic_payload() -> None:
    mapped = ProviderAdapterRegistry.defaults().adapter(PromptProvider.OPENAI)
    unmapped = ProviderPromptCacheAdapter(mapped.profile)
    compiled = PromptCompiler().compile(identity(), segments())

    with pytest.raises(Unsupported, match="request mapping is unavailable"):
        unmapped.build_request(compiled)


def test_openai_usage_is_inclusive_and_reconciled_exactly() -> None:
    adapter = ProviderAdapterRegistry.defaults().adapter(PromptProvider.OPENAI)
    usage = adapter.normalize_usage(
        {
            "usage": {
                "input_tokens": 1_000,
                "output_tokens": 100,
                "input_tokens_details": {"cached_tokens": 900},
            }
        }
    )
    assert usage.total_input_tokens == 1_000
    assert usage.processed_input_tokens == 100
    assert usage.cache_read_tokens == 900
    assert usage.cache_write_tokens is None
    assert usage.cache_read_fraction == 0.9


def test_anthropic_usage_is_additive_and_never_double_counted() -> None:
    adapter = ProviderAdapterRegistry.defaults().adapter(PromptProvider.ANTHROPIC)
    assert isinstance(adapter, AnthropicPromptCacheAdapter)
    usage = adapter.normalize_usage(
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 40,
                "cache_read_input_tokens": 800,
                "cache_creation_input_tokens": 100,
            }
        }
    )
    assert usage.total_input_tokens == 1_000
    assert usage.processed_input_tokens == 200
    assert usage.cache_read_tokens == 800
    assert usage.cache_write_tokens == 100


def test_missing_or_impossible_provider_counters_fail_closed() -> None:
    adapter = ProviderAdapterRegistry.defaults().adapter(PromptProvider.OPENAI)
    with pytest.raises(ContractViolation, match="counter is missing"):
        adapter.normalize_usage({"usage": {"input_tokens": 10, "output_tokens": 1}})
    with pytest.raises(ContractViolation, match="cached tokens exceed"):
        adapter.normalize_usage(
            {
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 1,
                    "input_tokens_details": {"cached_tokens": 11},
                }
            }
        )


def test_request_telemetry_cannot_contain_prompt_or_secret_material() -> None:
    raw = "customer source\nAPI_KEY=top-secret-value"
    compiled = PromptCompiler().compile(
        identity(),
        (PromptSegment("policy", SegmentStability.STABLE, 0, raw),),
    )
    request = ProviderAdapterRegistry.defaults().adapter(PromptProvider.OPENAI).build_request(compiled)
    assert request.payload["input"] == raw

    rendered_telemetry = json.dumps(request.telemetry(), sort_keys=True)
    rendered_manifest = json.dumps(compiled.manifest(), sort_keys=True)
    assert raw not in rendered_telemetry
    assert "top-secret-value" not in rendered_telemetry
    assert raw not in rendered_manifest
    assert "top-secret-value" not in rendered_manifest


def test_openai_profile_maps_current_routing_key_retention_and_usage_contract() -> None:
    adapter = ProviderAdapterRegistry.defaults().adapter(PromptProvider.OPENAI)
    compiled = PromptCompiler().compile(identity(), segments())

    request = adapter.build_request(compiled, ttl_class="24h")

    assert request.payload["prompt_cache_key"] == compiled.cache_key
    assert request.payload["prompt_cache_retention"] == "24h"
    assert request.ttl_class == "24h"
    assert adapter.profile.api_contract_version == "openai-responses-2026-08-20"
    assert adapter.profile.profile_digest.startswith("sha256:")


def test_observe_mode_does_not_send_provider_cache_controls() -> None:
    registry = ProviderAdapterRegistry.defaults()
    openai_prompt = PromptCompiler().compile(identity(), segments())
    openai = registry.adapter(PromptProvider.OPENAI).build_request(
        openai_prompt,
        cache_mode=ProviderCacheMode.OBSERVE,
    )
    anthropic_prompt = PromptCompiler().compile(
        identity(PromptProvider.ANTHROPIC),
        segments(),
    )
    anthropic = registry.adapter(PromptProvider.ANTHROPIC).build_request(
        anthropic_prompt,
        cache_mode=ProviderCacheMode.OBSERVE,
    )

    assert "prompt_cache_key" not in openai.payload
    assert "cache_control" not in anthropic.payload["messages"][0]["content"][0]


def test_anthropic_explicit_long_ttl_maps_to_content_breakpoint() -> None:
    compiled = PromptCompiler().compile(identity(PromptProvider.ANTHROPIC), segments())
    request = ProviderAdapterRegistry.defaults().adapter(PromptProvider.ANTHROPIC).build_request(
        compiled,
        cache_mode=ProviderCacheMode.EXPLICIT,
        ttl_class="1h",
    )

    control = request.payload["messages"][0]["content"][0]["cache_control"]
    assert control == {"type": "ephemeral", "ttl": "1h"}


def test_unknown_ttl_or_unsupported_explicit_mode_fails_closed() -> None:
    compiled = PromptCompiler().compile(identity(), segments())
    adapter = ProviderAdapterRegistry.defaults().adapter(PromptProvider.OPENAI)

    with pytest.raises(Unsupported, match="TTL class is not supported"):
        adapter.build_request(compiled, ttl_class="1h")
    with pytest.raises(Unsupported, match="does not support explicit"):
        adapter.build_request(compiled, cache_mode=ProviderCacheMode.EXPLICIT)


def test_normalized_observation_is_content_free_and_exactly_attributed() -> None:
    raw = "customer source API_KEY=top-secret-value"
    compiled = PromptCompiler().compile(
        identity(),
        (PromptSegment("policy", SegmentStability.STABLE, 0, raw),),
    )
    adapter = ProviderAdapterRegistry.defaults().adapter(PromptProvider.OPENAI)
    request = adapter.build_request(compiled)
    usage = adapter.normalize_usage(
        {
            "usage": {
                "input_tokens": 1_000,
                "output_tokens": 10,
                "input_tokens_details": {"cached_tokens": 900},
            }
        }
    )
    observation = adapter.observation(
        prompt=compiled,
        request=request,
        usage=usage,
        reason=ProviderCacheReason.HIT,
        request_id=d("f"),
    )

    encoded = json.dumps(observation.telemetry(), sort_keys=True)
    assert raw not in encoded
    assert "top-secret-value" not in encoded
    assert observation.usage.cache_read_tokens == 900
    assert observation.reason is ProviderCacheReason.HIT


def test_provider_observation_rejects_counter_reason_disagreement() -> None:
    compiled = PromptCompiler().compile(identity(), segments())
    adapter = ProviderAdapterRegistry.defaults().adapter(PromptProvider.OPENAI)
    request = adapter.build_request(compiled)
    usage = adapter.normalize_usage(
        {
            "usage": {
                "input_tokens": 10,
                "output_tokens": 1,
                "input_tokens_details": {"cached_tokens": 0},
            }
        }
    )

    with pytest.raises(ContractViolation, match="positive cache-read"):
        adapter.observation(
            prompt=compiled,
            request=request,
            usage=usage,
            reason=ProviderCacheReason.HIT,
            request_id=d("f"),
        )


def test_policy_kill_switches_fall_back_to_an_ordinary_provider_request() -> None:
    compiled = PromptCompiler().compile(identity(), segments())
    controller = PromptCacheController(ProviderAdapterRegistry.defaults())

    request, reason = controller.prepare(
        compiled,
        PromptRequestClass.DETERMINISTIC_CONVERSION,
    )

    assert request.cache_mode is ProviderCacheMode.OBSERVE
    assert "prompt_cache_key" not in request.payload
    assert reason is ProviderCacheReason.PROVIDER_UNSUPPORTED

    enabled = PromptCacheController(
        ProviderAdapterRegistry.defaults(),
        ProviderCachePolicy(enabled=True, enabled_providers=(PromptProvider.OPENAI,)),
    )
    cached, cached_reason = enabled.prepare(
        compiled,
        PromptRequestClass.DETERMINISTIC_CONVERSION,
    )
    assert cached.cache_mode is ProviderCacheMode.AUTOMATIC
    assert cached.payload["prompt_cache_key"] == compiled.cache_key
    assert cached_reason is ProviderCacheReason.UNKNOWN


@pytest.mark.parametrize(
    "policy",
    [
        ProviderCachePolicy(
            enabled=True,
            enabled_providers=(PromptProvider.ANTHROPIC,),
        ),
        ProviderCachePolicy(
            enabled=True,
            enabled_providers=(PromptProvider.OPENAI,),
            disabled_tenant_scope_digests=(d("1"),),
        ),
        ProviderCachePolicy(
            enabled=True,
            enabled_providers=(PromptProvider.OPENAI,),
            disabled_provider_models=("openai:model-v1",),
        ),
        ProviderCachePolicy(
            enabled=True,
            enabled_providers=(PromptProvider.OPENAI,),
            disabled_request_classes=(PromptRequestClass.REPAIR,),
        ),
    ],
)
def test_each_cache_kill_switch_is_exact_and_content_free(
    policy: ProviderCachePolicy,
) -> None:
    compiled = PromptCompiler().compile(identity(), segments())
    request_class = (
        PromptRequestClass.REPAIR
        if policy.disabled_request_classes
        else PromptRequestClass.DETERMINISTIC_CONVERSION
    )
    request, reason = PromptCacheController(
        ProviderAdapterRegistry.defaults(), policy
    ).prepare(compiled, request_class)
    assert request.cache_mode is ProviderCacheMode.OBSERVE
    assert "prompt_cache_key" not in request.payload
    assert reason is ProviderCacheReason.PROVIDER_UNSUPPORTED


def test_provider_circuit_breaker_disables_only_cache_fields_and_recovers() -> None:
    breaker = ProviderCircuitBreaker(failure_threshold=2, recovery_after_events=3)
    controller = PromptCacheController(
        ProviderAdapterRegistry.defaults(),
        ProviderCachePolicy(enabled=True, enabled_providers=(PromptProvider.OPENAI,)),
        breaker,
    )
    compiled = PromptCompiler().compile(identity(), segments())

    for _ in range(2):
        request, _reason = controller.prepare(
            compiled, PromptRequestClass.DETERMINISTIC_CONVERSION
        )
        assert request.cache_mode is ProviderCacheMode.AUTOMATIC
        controller.record_provider_failure(PromptProvider.OPENAI)

    for _ in range(2):
        fallback, reason = controller.prepare(
            compiled, PromptRequestClass.DETERMINISTIC_CONVERSION
        )
        assert fallback.cache_mode is ProviderCacheMode.OBSERVE
        assert reason is ProviderCacheReason.PROVIDER_OUTAGE

    recovered, reason = controller.prepare(
        compiled, PromptRequestClass.DETERMINISTIC_CONVERSION
    )
    assert recovered.cache_mode is ProviderCacheMode.AUTOMATIC
    assert reason is ProviderCacheReason.UNKNOWN


def test_retry_accounting_is_exactly_once_and_drift_conflicts() -> None:
    compiled = PromptCompiler().compile(identity(), segments())
    adapter = ProviderAdapterRegistry.defaults().adapter(PromptProvider.OPENAI)
    request = adapter.build_request(compiled)
    usage = adapter.normalize_usage(
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 5,
                "input_tokens_details": {"cached_tokens": 90},
            }
        }
    )
    observation = adapter.observation(
        prompt=compiled,
        request=request,
        usage=usage,
        reason=ProviderCacheReason.HIT,
        request_id=d("e"),
    )
    ledger = RetryAccountingLedger()
    assert ledger.record(observation) is True
    assert ledger.record(observation) is False
    assert ledger.totals() == {
        "requests": 1,
        "total_input_tokens": 100,
        "processed_input_tokens": 10,
        "output_tokens": 5,
        "cache_read_tokens": 90,
        "cache_write_tokens": 0,
    }

    changed_usage = replace(usage, output_tokens=6)
    changed = adapter.observation(
        prompt=compiled,
        request=request,
        usage=changed_usage,
        reason=ProviderCacheReason.HIT,
        request_id=d("e"),
    )
    with pytest.raises(IdempotencyConflict, match="retry changed"):
        ledger.record(changed)


def test_self_hosted_cache_requires_exact_runtime_compatibility_and_inventory() -> None:
    degraded = ProviderAdapterRegistry.defaults().adapter(PromptProvider.SELF_HOSTED)
    compiled = PromptCompiler().compile(
        identity(PromptProvider.SELF_HOSTED),
        segments(),
    )
    observe = degraded.build_request(compiled, cache_mode=ProviderCacheMode.OBSERVE)
    assert "prefix_cache_key" not in observe.payload
    with pytest.raises(Unsupported, match="observe mode only"):
        degraded.build_request(compiled, cache_mode=ProviderCacheMode.EXPLICIT)

    runtime = SelfHostedRuntimeProfile(
        replica_id_digest=d("8"),
        tokenizer_digest=d("9"),
        model_build_digest=d("a"),
        block_hash_version="kv-block-v1",
        eviction_epoch=7,
    )
    profile = replace(degraded.profile, state=CapabilityState.SUPPORTED)
    adapter = SelfHostedPromptCacheAdapter(profile, runtime)
    exact = PromptCompiler().compile(
        identity(
            PromptProvider.SELF_HOSTED,
            compatibility_digest=runtime.compatibility_digest,
        ),
        segments(),
    )
    request = adapter.build_request(
        exact,
        cache_mode=ProviderCacheMode.EXPLICIT,
        ttl_class="runtime-default",
    )
    runtime_fields = request.payload["prefix_cache_runtime"]
    assert runtime_fields["replica_id_digest"] == d("8")
    assert runtime_fields["prefix_resident"] is False

    with pytest.raises(ContractViolation, match="does not match"):
        adapter.build_request(
            compiled,
            cache_mode=ProviderCacheMode.EXPLICIT,
            ttl_class="runtime-default",
        )
