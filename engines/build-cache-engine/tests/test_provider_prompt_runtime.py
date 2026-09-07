"""Production-shaped provider prompt mapping and normalized accounting tests."""

from __future__ import annotations

import base64
import json
import unicodedata

import pytest

from conftest import PROJECT, TENANT, digest
from elmos_build_cache.api import CacheControlPlane, Request, Response
from elmos_build_cache.canonical import canonical_json_text
from elmos_build_cache.cas import ContentAddressableStore
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


# --------------------------------------------------------------------------
# Authenticated, durable, idempotent control-plane chain (BC-15)
#
# These exercise the real ``CacheControlPlane`` routes end to end: routing,
# ownership preflight, the durable idempotency claim/complete cycle and the
# persisted replay record.  No provider is ever called; the provider round
# trip stays NOT_RUN.
# --------------------------------------------------------------------------

# "café résumé" written with combining accents (NFD).  ``canonical_json_bytes``
# NFC-normalises before storage, so a leak of this text would be stored in a
# different byte sequence than the one written here.
NFD_CANARY = "cafe\u0301 re\u0301sume\u0301 CANARYNFDPROMPTBYTES"

PREPARE_PATH = "/cache/provider-prompts/prepare"
USAGE_PATH = "/cache/provider-prompts/usage"
FOREIGN_TENANT = "tenant-foreign"
FOREIGN_PROJECT = "project-foreign"
PRINCIPAL_A = digest("8")
PRINCIPAL_B = digest("b")


def _controller() -> PromptCacheController:
    return PromptCacheController(
        ProviderAdapterRegistry.defaults(),
        policy=ProviderCachePolicy(
            enabled=True,
            enabled_providers=(PromptProvider.OPENAI,),
        ),
    )


def _plane(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    *,
    tenant_id: str = TENANT,
    with_controller: bool = True,
) -> tuple[CacheControlPlane, ParityMetadataRepository]:
    repository = ParityMetadataRepository(store)
    return (
        CacheControlPlane(
            store,
            cas,
            tenant_id,
            clock=clock,
            parity_repository=repository,
            prompt_cache_controller=_controller() if with_controller else None,
        ),
        repository,
    )


def _usage_payload(
    manifest_id: str,
    *,
    project_id: str = PROJECT,
    request_id: str | None = None,
    reason_code: str = "HIT",
    input_tokens: int = 100,
    cached_tokens: int = 90,
) -> dict[str, object]:
    return {
        "project_id": project_id,
        "prompt_manifest_id": manifest_id,
        "provider": "openai",
        "request_id": request_id or digest("9"),
        "reason_code": reason_code,
        "usage": {
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 12,
                "input_tokens_details": {"cached_tokens": cached_tokens},
            }
        },
    }


def _idempotency_rows(store: SqliteMetadataStore, tenant_id: str) -> list[tuple[object, ...]]:
    return [
        tuple(row)
        for row in store.query(
            "SELECT * FROM idempotency_records WHERE tenant_id=?",
            (tenant_id,),
        )
    ]


def _prepare(
    plane: CacheControlPlane,
    *,
    key: str,
    payload: dict[str, object] | None = None,
    principal: str | None = None,
) -> Response:
    return plane.handle(
        Request(
            "POST",
            PREPARE_PATH,
            payload if payload is not None else _prompt_payload(),
            {"Idempotency-Key": key},
            authenticated_principal_digest=principal,
        )
    )


def test_prepare_and_usage_route_through_the_authenticated_idempotent_chain(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    plane, repository = _plane(store, cas, clock)

    prepared = _prepare(plane, key="prepare-chain-1")

    assert prepared.status == 200
    body = prepared.json()
    provider_request = body["provider_request"]
    assert provider_request["provider"] == "openai"
    assert provider_request["cache_mode"] == "AUTOMATIC"
    assert provider_request["payload_retained"] is False
    assert provider_request["payload_digest"].startswith("sha256:")
    assert "payload" not in provider_request
    assert body["provider_execution_performed"] is False
    manifest_id = body["manifest"]["manifest_id"]
    assert repository.get_prompt_manifest(TENANT, PROJECT, manifest_id) == body["manifest"]

    recorded = plane.handle(
        Request(
            "POST",
            USAGE_PATH,
            _usage_payload(manifest_id),
            {"Idempotency-Key": "usage-chain-1"},
        )
    )

    assert recorded.status == 201
    usage_body = recorded.json()
    assert usage_body["observation"]["cache_read_tokens"] == 90
    assert usage_body["observation"]["processed_input_tokens"] == 10
    assert usage_body["outcome"]["outcome"] == "HIT"
    assert usage_body["provider_execution_performed"] is False
    assert len(repository.list_cache_outcomes(TENANT, PROJECT, digest("9"))) == 1


def test_both_provider_routes_require_a_global_idempotency_key(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    plane, _ = _plane(store, cas, clock)
    prepared = _prepare(plane, key="prepare-required-key")
    manifest_id = prepared.json()["manifest"]["manifest_id"]

    for path, payload in (
        (PREPARE_PATH, _prompt_payload()),
        (USAGE_PATH, _usage_payload(manifest_id)),
    ):
        response = plane.handle(Request("POST", path, payload))
        assert response.status == 400
        assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_usage_replay_returns_the_stored_response_without_re_executing(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    plane, repository = _plane(store, cas, clock)
    manifest_id = _prepare(plane, key="prepare-replay").json()["manifest"]["manifest_id"]
    payload = _usage_payload(manifest_id)
    request = Request("POST", USAGE_PATH, payload, {"Idempotency-Key": "usage-replay"})

    first = plane.handle(request)
    assert first.status == 201
    recorded_at = first.json()["outcome"]["occurred_at"]

    # A re-execution could not produce this body again: the clock has moved,
    # so a fresh outcome document would carry a different ``occurred_at``.
    clock.advance(3_600)
    replay = plane.handle(request)

    assert replay.status == first.status
    assert replay.json() == first.json()
    assert replay.json()["outcome"]["occurred_at"] == recorded_at
    assert replay.headers is not None
    assert replay.headers["Idempotent-Replay"] == "true"
    assert len(repository.list_cache_outcomes(TENANT, PROJECT, digest("9"))) == 1


def test_prepare_replay_is_byte_identical_to_the_durable_record(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    plane, _ = _plane(store, cas, clock)
    request = Request(
        "POST",
        PREPARE_PATH,
        _prompt_payload(),
        {"Idempotency-Key": "prepare-replay-identity"},
    )

    first = plane.handle(request)
    replay = plane.handle(request)

    assert first.status == replay.status == 200
    assert first.json() == replay.json()
    stored = store.query_one(
        "SELECT response FROM idempotency_records WHERE tenant_id=? AND idempotency_key=?",
        (TENANT, "prepare-replay-identity"),
    )
    assert stored is not None
    envelope = json.loads(str(stored[0]))
    # The response the caller saw and the record kept for replay are the same
    # bytes; that identity is what makes the content-free projection binding.
    assert envelope["body"]["value"] == first.json()


def test_prepare_drift_on_a_used_key_is_refused_without_overwriting(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    plane, _ = _plane(store, cas, clock)
    path = PREPARE_PATH
    key = "drift-prepare"
    drifted = {**_prompt_payload(), "ttl_class": "24h"}
    original = plane.handle(
        Request("POST", path, _prompt_payload(), {"Idempotency-Key": key})
    )
    assert original.status == 200

    conflict = plane.handle(Request("POST", path, drifted, {"Idempotency-Key": key}))

    assert conflict.status == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    # The refusal must not hand the drifted caller the stored response.
    assert "manifest" not in conflict.json()
    assert "provider_request" not in conflict.json()

    replay = plane.handle(
        Request("POST", path, _prompt_payload(), {"Idempotency-Key": key})
    )
    assert replay.json() == original.json()


def test_usage_drift_on_a_used_key_is_refused_without_overwriting(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    plane, repository = _plane(store, cas, clock)
    manifest_id = _prepare(plane, key="prepare-usage-drift").json()["manifest"]["manifest_id"]
    payload = _usage_payload(manifest_id)
    original = plane.handle(
        Request("POST", USAGE_PATH, payload, {"Idempotency-Key": "usage-drift"})
    )
    assert original.status == 201

    drifted = _usage_payload(manifest_id, input_tokens=101)
    conflict = plane.handle(
        Request("POST", USAGE_PATH, drifted, {"Idempotency-Key": "usage-drift"})
    )

    assert conflict.status == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert "observation" not in conflict.json()
    replay = plane.handle(
        Request("POST", USAGE_PATH, payload, {"Idempotency-Key": "usage-drift"})
    )
    assert replay.json() == original.json()
    assert replay.json()["observation"]["total_input_tokens"] == 100
    assert len(repository.list_cache_outcomes(TENANT, PROJECT, digest("9"))) == 1


def _foreign_project(store: SqliteMetadataStore) -> None:
    with store.transaction():
        store.ensure_project(FOREIGN_TENANT, FOREIGN_PROJECT)


def test_project_ownership_is_preflighted_before_the_global_idempotency_claim(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    """Ownership must be decided before any durable idempotency state exists.

    Two observations pin the ordering, and both flip if the preflight is moved
    after :meth:`MetadataStore.claim_idempotent`:

    1. a refused request must leave no ``idempotency_records`` row at all --
       with the order swapped the claim is committed first and the refusal is
       then published as that key's COMPLETE response, so the caller's own key
       is burned by a request that was never allowed to run;
    2. probing a project this tenant does not own must answer identically
       whether or not the supplied key is already in use -- with the order
       swapped the already-used key answers IDEMPOTENCY_CONFLICT (the request
       fingerprint differs) while the unused key answers NOT_FOUND, and that
       difference alone tells the caller which keys exist.
    """

    _foreign_project(store)
    plane, _ = _plane(store, cas, clock, tenant_id=FOREIGN_TENANT)
    own = {**_prompt_payload(), "project_id": FOREIGN_PROJECT}
    probe = _prompt_payload()  # project-test belongs to tenant-test

    assert _prepare(plane, key="kept-key", payload=own).status == 200

    reused = _prepare(plane, key="kept-key", payload=probe)
    fresh = _prepare(plane, key="never-used-key", payload=probe)

    assert reused.status == fresh.status == 404
    assert reused.json() == fresh.json() == {
        "code": "NOT_FOUND",
        "message": "project does not exist",
        "details": {"project_id": PROJECT},
    }
    assert (
        store.query_one(
            "SELECT COUNT(*) FROM idempotency_records"
            " WHERE tenant_id=? AND idempotency_key=?",
            (FOREIGN_TENANT, "never-used-key"),
        )[0]
        == 0
    )
    # The key the refused probe reused is still the successful record, not a
    # stored 404, so a legitimate replay still works.
    assert _prepare(plane, key="kept-key", payload=own).status == 200


def test_a_refused_project_is_indistinguishable_from_one_that_never_existed(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    _foreign_project(store)
    plane, _ = _plane(store, cas, clock, tenant_id=FOREIGN_TENANT)

    unowned = _prepare(plane, key="unowned", payload=_prompt_payload())
    absent = _prepare(
        plane,
        key="absent",
        payload={**_prompt_payload(), "project_id": PROJECT},
    )
    nonexistent = _prepare(
        plane,
        key="nonexistent",
        payload={**_prompt_payload(), "project_id": "project-never-created"},
    )

    assert unowned.json() == absent.json()
    assert nonexistent.status == unowned.status == 404
    assert nonexistent.json()["code"] == unowned.json()["code"]
    assert nonexistent.json()["message"] == unowned.json()["message"]


def test_a_foreign_tenant_can_neither_replay_read_nor_detect_another_key(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    _foreign_project(store)
    owner, owner_repository = _plane(store, cas, clock)
    foreign, _ = _plane(store, cas, clock, tenant_id=FOREIGN_TENANT)
    manifest_id = _prepare(owner, key="owner-prepare").json()["manifest"]["manifest_id"]
    stored = owner.handle(
        Request(
            "POST",
            USAGE_PATH,
            _usage_payload(manifest_id),
            {"Idempotency-Key": "shared-key"},
        )
    )
    assert stored.status == 201
    owner_rows = _idempotency_rows(store, TENANT)

    stolen = foreign.handle(
        Request(
            "POST",
            USAGE_PATH,
            _usage_payload(manifest_id),
            {"Idempotency-Key": "shared-key"},
        )
    )

    assert stolen.status == 404
    assert stolen.json()["code"] == "NOT_FOUND"
    assert "observation" not in stolen.json()
    assert "outcome" not in stolen.json()
    # No read of, and no write to, the owner's durable record.
    assert _idempotency_rows(store, TENANT) == owner_rows
    assert _idempotency_rows(store, FOREIGN_TENANT) == []
    assert len(owner_repository.list_cache_outcomes(TENANT, PROJECT, digest("9"))) == 1
    assert owner_repository.list_cache_outcomes(FOREIGN_TENANT, FOREIGN_PROJECT, digest("9")) == ()
    # The owner's replay is untouched by the foreign attempt.
    replayed = owner.handle(
        Request(
            "POST",
            USAGE_PATH,
            _usage_payload(manifest_id),
            {"Idempotency-Key": "shared-key"},
        )
    )
    assert replayed.json() == stored.json()


def test_a_foreign_principal_can_neither_replay_nor_read_another_key(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    plane, repository = _plane(store, cas, clock)
    first = _prepare(plane, key="principal-key", principal=PRINCIPAL_A)
    assert first.status == 200

    stolen = _prepare(plane, key="principal-key", principal=PRINCIPAL_B)

    assert stolen.status == 409
    assert stolen.json()["code"] == "IDEMPOTENCY_CONFLICT"
    # The refusal carries none of the first principal's stored response, and
    # is exactly the vocabulary an ordinary body drift produces, so it reveals
    # nothing about whose key it is.
    assert set(stolen.json()) == {"code", "message", "details"}
    assert "manifest" not in json.dumps(stolen.json())
    drift = _prepare(
        plane,
        key="principal-key",
        payload={**_prompt_payload(), "ttl_class": "24h"},
        principal=PRINCIPAL_A,
    )
    assert drift.status == stolen.status
    assert drift.json()["code"] == stolen.json()["code"]
    assert drift.json()["message"] == stolen.json()["message"]
    # The second principal did not re-execute the operation either.
    manifest_id = first.json()["manifest"]["manifest_id"]
    assert repository.get_prompt_manifest(TENANT, PROJECT, manifest_id) is not None
    assert _prepare(plane, key="principal-key", principal=PRINCIPAL_A).json() == first.json()


def test_both_provider_routes_fail_closed_without_a_prompt_cache_controller(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    wired, _ = _plane(store, cas, clock)
    manifest_id = _prepare(wired, key="wired-prepare").json()["manifest"]["manifest_id"]
    unwired, _ = _plane(store, cas, clock, with_controller=False)

    assert unwired.prompt_cache_controller is None
    for path, payload, key in (
        (PREPARE_PATH, _prompt_payload(), "unwired-prepare"),
        (USAGE_PATH, _usage_payload(manifest_id), "unwired-usage"),
    ):
        response = unwired.handle(
            Request("POST", path, payload, {"Idempotency-Key": key})
        )
        assert response.status == 503
        assert response.json()["code"] == "REMOTE_UNAVAILABLE"
        assert "provider prompt cache controller" in response.json()["message"]


def test_counter_mismatches_are_refused_rather_than_silently_recorded(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    plane, repository = _plane(store, cas, clock)
    manifest_id = _prepare(plane, key="counter-prepare").json()["manifest"]["manifest_id"]

    # A cache-read counter that contradicts the declared reason code.
    reason_mismatch = plane.handle(
        Request(
            "POST",
            USAGE_PATH,
            _usage_payload(manifest_id, request_id=digest("c"), reason_code="COLD_PREFIX"),
            {"Idempotency-Key": "counter-reason"},
        )
    )
    # A cache-read counter that cannot be true under inclusive accounting.
    accounting_mismatch = plane.handle(
        Request(
            "POST",
            USAGE_PATH,
            _usage_payload(
                manifest_id,
                request_id=digest("d"),
                input_tokens=100,
                cached_tokens=150,
            ),
            {"Idempotency-Key": "counter-accounting"},
        )
    )

    for response in (reason_mismatch, accounting_mismatch):
        assert response.status == 422
        assert response.json()["code"] == "CONTRACT_VIOLATION"
    assert repository.list_cache_outcomes(TENANT, PROJECT, digest("c")) == ()
    assert repository.list_cache_outcomes(TENANT, PROJECT, digest("d")) == ()


def test_no_raw_prompt_bytes_reach_the_durable_idempotency_record(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    """Scan the persisted row for the prompt's actual bytes, in any encoding.

    A field-name check would pass against a record that merely renamed the
    payload, so this searches every stored column for the canary text itself,
    plus its hex and base64 encodings (the durable envelope base64-encodes
    binary bodies).  The in-process service result is asserted first as a
    positive control: it proves these exact bytes really do flow through the
    prepare path, so their absence downstream is a property of the control
    plane and not of an unused fixture.
    """

    stable_canary = "Stable system policy CANARYSTABLEPROMPTBYTES"
    volatile_canary = "Implement the cache CANARYVOLATILEPROMPTBYTES"
    payload = _prompt_payload()
    segments = payload["segments"]
    assert isinstance(segments, list)
    segments[0] = {**segments[0], "content": stable_canary}
    segments[1] = {**segments[1], "content": volatile_canary}

    repository = ParityMetadataRepository(store)
    service = ParityApiService(
        tenant_id=TENANT,
        store=store,
        repository=repository,
        clock=clock,
        prompt_cache_controller=_controller(),
    )
    in_process = service.prepare_provider_prompt(payload).body
    assert stable_canary in json.dumps(in_process, sort_keys=True)
    assert volatile_canary in json.dumps(in_process, sort_keys=True)

    plane, _ = _plane(store, cas, clock)
    response = plane.handle(
        Request("POST", PREPARE_PATH, payload, {"Idempotency-Key": "prompt-safety"})
    )
    assert response.status == 200

    # A rejected request is persisted too: ``handle`` stores any response under
    # 500 into the durable record, so a validator that echoes caller text turns
    # a 422 into a durable copy of the prompt.  Drive both rejection paths that
    # take a caller-supplied string -- a closed-vocabulary field and an
    # unexpected key name -- with the prompt itself as the offending value.
    enum_canary = "CANARYENUMPROMPTBYTES " + volatile_canary
    key_canary = "CANARYUNKNOWNKEYPROMPTBYTES_" + stable_canary.replace(" ", "_")

    rejected_enum = plane.handle(
        Request(
            "POST",
            PREPARE_PATH,
            {**payload, "request_class": enum_canary},
            {"Idempotency-Key": "prompt-safety-enum"},
        )
    )
    assert rejected_enum.status == 422

    bad_segments = [dict(segment) for segment in segments]
    bad_segments[0] = {**bad_segments[0], key_canary: "x"}
    rejected_key = plane.handle(
        Request(
            "POST",
            PREPARE_PATH,
            {**payload, "segments": bad_segments},
            {"Idempotency-Key": "prompt-safety-key"},
        )
    )
    assert rejected_key.status == 422

    # Both refusals must still be diagnosable: the caller learns which field
    # failed and what the server would have accepted, without the server
    # repeating anything the caller sent.
    enum_body = rejected_enum.json()
    assert enum_body["details"]["field"] == "request_class"
    assert enum_body["details"]["permitted"]
    key_body = rejected_key.json()
    assert key_body["details"]["field"].startswith("segments[0]")
    assert key_body["details"]["unknown_count"] == 1

    # Scan EVERY row the whole sequence wrote -- the 200 and both 422s.
    rows = _idempotency_rows(store, TENANT)
    assert len(rows) >= 3
    persisted = "\x00".join(str(column) for row in rows for column in row)
    # ``canonical_json_bytes`` NFC-normalises before storage, so a leak written
    # in NFD would be stored in NFC and a raw-substring scan would miss it.
    # Normalise the haystack the same way the writer does and compare both
    # forms of every needle.
    persisted_nfc = unicodedata.normalize("NFC", persisted)
    canaries = (stable_canary, volatile_canary, enum_canary, key_canary, NFD_CANARY)
    for canary in canaries:
        for form in {canary, unicodedata.normalize("NFC", canary)}:
            raw = form.encode("utf-8")
            for encoded in (
                form,
                raw.hex(),
                base64.b64encode(raw).decode("ascii"),
                base64.b64encode(raw).decode("ascii").rstrip("="),
                base64.urlsafe_b64encode(raw).decode("ascii"),
                base64.urlsafe_b64encode(raw).decode("ascii").rstrip("="),
            ):
                assert encoded not in persisted
                assert encoded not in persisted_nfc
    # The same scan applied to bytes that do carry the prompt finds it -- so a
    # clean result above is the control plane stripping, not a broken scan.
    in_process_text = json.dumps(in_process, sort_keys=True)
    assert stable_canary in in_process_text
    assert volatile_canary in in_process_text
    # The NFD needle is proven live against the writer's own encoder rather than
    # ``json.dumps``, which escapes non-ASCII and would make the check vacuous.
    assert unicodedata.normalize("NFC", NFD_CANARY) in unicodedata.normalize(
        "NFC", canonical_json_text({"probe": NFD_CANARY})
    )
    assert "sha256:" in persisted


def test_an_nfd_canary_would_be_caught_by_the_normalising_scan(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    """The NFC-normalising scan is not vacuous: prove it catches a real leak.

    A scan that normalises can only be trusted if a leak written in the other
    form actually trips it.  Persist the NFD canary through the ordinary
    idempotency path with a route that legitimately echoes it, then run the same
    two-form scan and require a match.
    """

    plane, _ = _plane(store, cas, clock)
    payload = _prompt_payload()
    segments = payload["segments"]
    assert isinstance(segments, list)
    segments[1] = {**segments[1], "content": NFD_CANARY}
    response = plane.handle(
        Request("POST", PREPARE_PATH, payload, {"Idempotency-Key": "nfd-probe"})
    )
    assert response.status == 200

    rows = _idempotency_rows(store, TENANT)
    persisted = "\x00".join(str(column) for row in rows for column in row)
    haystacks = (persisted, unicodedata.normalize("NFC", persisted))
    needles = {NFD_CANARY, unicodedata.normalize("NFC", NFD_CANARY)}
    # The prompt itself is stripped, so the canary must NOT be there -- but the
    # scan machinery is proven live by finding it in the canonical encoding of
    # the same text, which is what the writer would have produced had it leaked.
    leaked = canonical_json_text({"content": NFD_CANARY})
    assert any(needle in leaked for needle in needles)
    for haystack in haystacks:
        for needle in needles:
            assert needle not in haystack
