"""Production-shaped provider prompt mapping and normalized accounting tests."""

from __future__ import annotations

import pytest

from conftest import PROJECT, TENANT, digest
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.errors import ContractViolation, IdempotencyConflict, NotFound
from elmos_build_cache.parity_api import ParityApiService
from elmos_build_cache.parity_store import ParityMetadataRepository
from elmos_build_cache.prompt_cache import (
    PromptCacheController,
    PromptProvider,
    ProviderAdapterRegistry,
    ProviderCachePolicy,
)


def _service(
    store: SqliteMetadataStore,
    clock: ManualClock,
    *,
    tenant_id: str = TENANT,
) -> tuple[ParityApiService, ParityMetadataRepository, PromptCacheController]:
    repository = ParityMetadataRepository(store)
    controller = PromptCacheController(
        ProviderAdapterRegistry.defaults(),
        policy=ProviderCachePolicy(
            enabled=True,
            enabled_providers=(PromptProvider.OPENAI,),
        ),
    )
    return (
        ParityApiService(
            tenant_id=tenant_id,
            store=store,
            repository=repository,
            clock=clock,
            prompt_cache_controller=controller,
        ),
        repository,
        controller,
    )


def _prompt_payload() -> dict[str, object]:
    return {
        "project_id": PROJECT,
        "identity": {
            "provider": "openai",
            "provider_namespace_digest": digest("2"),
            "model": "gpt-5.6",
            "effort_profile": "high",
            "tool_schema_digest": digest("3"),
            "compatibility_digest": digest("4"),
        },
        "segments": [
            {
                "segment_id": "system-policy",
                "stability": "stable",
                "ordinal": 0,
                "content": "Stable system policy",
            },
            {
                "segment_id": "turn-request",
                "stability": "volatile",
                "ordinal": 0,
                "content": "Implement the cache",
            },
        ],
        "request_class": "DETERMINISTIC_CONVERSION",
        "cache_mode": "AUTOMATIC",
        "ttl_class": "provider-default",
    }


def test_prepare_maps_through_pinned_profile_and_persists_only_manifest(
    store: SqliteMetadataStore,
    clock: ManualClock,
) -> None:
    service, repository, _ = _service(store, clock)

    result = service.prepare_provider_prompt(_prompt_payload())

    assert result.status == 200
    provider_request = result.body["provider_request"]
    assert provider_request["provider"] == "openai"
    assert provider_request["payload"]["input"].endswith("Implement the cache")
    assert provider_request["payload"]["prompt_cache_key"] == provider_request["cache_key"]
    assert result.body["provider_execution_performed"] is False
    manifest = result.body["manifest"]
    stored = repository.get_prompt_manifest(TENANT, PROJECT, manifest["manifest_id"])
    assert stored == manifest
    assert "Stable system policy" not in repr(stored)
    assert "Implement the cache" not in repr(stored)


def test_usage_is_normalized_deduplicated_and_explainable(
    store: SqliteMetadataStore,
    clock: ManualClock,
) -> None:
    service, repository, _ = _service(store, clock)
    prepared = service.prepare_provider_prompt(_prompt_payload()).body
    request_id = digest("9")
    payload = {
        "project_id": PROJECT,
        "prompt_manifest_id": prepared["manifest"]["manifest_id"],
        "provider": "openai",
        "request_id": request_id,
        "reason_code": "HIT",
        "usage": {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 12,
                "input_tokens_details": {"cached_tokens": 90},
            }
        },
    }

    first = service.record_provider_usage(payload)
    replay = service.record_provider_usage(payload)

    assert first.body == replay.body
    assert first.body["observation"]["total_input_tokens"] == 100
    assert first.body["observation"]["processed_input_tokens"] == 10
    assert first.body["observation"]["cache_read_tokens"] == 90
    outcomes = repository.list_cache_outcomes(TENANT, PROJECT, request_id)
    assert len(outcomes) == 1
    assert outcomes[0]["outcome"] == "HIT"
    assert outcomes[0]["reason_code"] == "PROMPT_PREFIX_REUSED"

    changed = dict(payload)
    changed["usage"] = {
        "usage": {
            "input_tokens": 101,
            "output_tokens": 12,
            "input_tokens_details": {"cached_tokens": 90},
        }
    }
    with pytest.raises(IdempotencyConflict):
        service.record_provider_usage(changed)


def test_usage_reason_must_match_provider_counter_and_scope(
    store: SqliteMetadataStore,
    clock: ManualClock,
) -> None:
    service, _, _ = _service(store, clock)
    prepared = service.prepare_provider_prompt(_prompt_payload()).body
    payload = {
        "project_id": PROJECT,
        "prompt_manifest_id": prepared["manifest"]["manifest_id"],
        "provider": "openai",
        "request_id": digest("a"),
        "reason_code": "COLD_PREFIX",
        "usage": {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 12,
                "input_tokens_details": {"cached_tokens": 90},
            }
        },
    }
    with pytest.raises(ContractViolation):
        service.record_provider_usage(payload)

    foreign, _, _ = _service(store, clock, tenant_id="tenant-foreign")
    with pytest.raises(NotFound):
        foreign.record_provider_usage(
            {
                **payload,
                "project_id": "project-foreign",
                "reason_code": "HIT",
            }
        )


def test_unwired_provider_controller_fails_closed(
    store: SqliteMetadataStore,
    clock: ManualClock,
) -> None:
    service = ParityApiService(
        tenant_id=TENANT,
        store=store,
        repository=ParityMetadataRepository(store),
        clock=clock,
    )

    from elmos_build_cache.errors import RemoteUnavailable

    with pytest.raises(RemoteUnavailable):
        service.prepare_provider_prompt(_prompt_payload())
