"""Execution Authority Kernel tests.

Named after the acceptance gates and negative tests in
``skills/execution-authority-kernel/acceptance.yaml`` plus the four non-negotiable invariants in
its SKILL.md, so a failing test names the contract clause it broke.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from elmos_autonomy_kernel.adapters.memory import FixedClock, InMemoryLeaseStore
from elmos_autonomy_kernel.authority import (
    ALLOWED_SUBJECTS,
    CHECK_ORDER,
    AttestedTokenSource,
    AuthorityDecision,
    AuthorityRequest,
    ExecutionAuthority,
    Reason,
    handle,
    mint,
)
from elmos_autonomy_kernel.contracts import SkillResult, Status, digest
from elmos_autonomy_kernel.errors import KernelError
from elmos_autonomy_kernel.registry import dispatch

POLICY_HASH = "sha256:" + "b" * 64
ISSUED_AT = "2026-01-01T00:00:00.000000Z"


@pytest.fixture()
def environment() -> dict:
    return {
        "environmentId": "env-1",
        "workspaceId": "ws-1",
        "policySnapshotHash": POLICY_HASH,
        "subject": "environment",
        "ttlSeconds": 900,
        "grantedTools": ["fs.read", "fs.write", "shell.exec"],
        "pathScopes": ["src", "docs"],
        "networkScopes": ["registry.internal:443"],
        "secretBindings": ["binding.npm"],
    }


@pytest.fixture()
def profile() -> dict:
    return {
        "permissionProfileId": "profile-standard",
        "tools": ["fs.read", "fs.write"],
        "pathScopes": ["src/pkg"],
        "networkScopes": [],
        "secretBindings": [],
    }


@pytest.fixture()
def authority(environment: dict, profile: dict, clock: FixedClock) -> ExecutionAuthority:
    return mint(environment, profile, now=clock.now(), fencing_token=1)


@pytest.fixture()
def held(leases: InMemoryLeaseStore) -> InMemoryLeaseStore:
    leases.acquire("ws-1", "worker-a", ttl_seconds=600)
    return leases


def _request(**overrides) -> AuthorityRequest:
    base = {
        "environment_id": "env-1",
        "workspace_id": "ws-1",
        "tool_id": "fs.read",
        "effect": "read",
        "fencing_token": 1,
        "policy_snapshot_hash": POLICY_HASH,
    }
    base.update(overrides)
    return AuthorityRequest(**base)


def _handle_request(**overrides) -> dict:
    body = {
        "environment": {
            "environmentId": "env-1", "workspaceId": "ws-1", "policySnapshotHash": POLICY_HASH,
            "subject": "environment", "ttlSeconds": 900,
            "grantedTools": ["fs.read", "fs.write"], "pathScopes": ["src"],
            "networkScopes": [], "secretBindings": [],
        },
        "permission_profile": {
            "permissionProfileId": "profile-standard", "tools": ["fs.read", "fs.write"],
            "pathScopes": ["src"],
        },
        "fencing_token": 1,
        "issued_at": ISSUED_AT,
    }
    body.update(overrides)
    return body


# --- positive gates ----------------------------------------------------------


def test_gate_authority_snapshot_complete(authority: ExecutionAuthority) -> None:
    """`authority-snapshot-complete`: the frozen snapshot names every dimension it binds."""

    snapshot = authority.snapshot()
    payload = snapshot["authority"]
    for key in (
        "environmentId", "workspaceId", "permissionProfileId", "policySnapshotHash",
        "fencingToken", "allowedTools", "pathScopes", "networkScopes", "secretBindings",
        "issuedAt", "expiresAt", "subject",
    ):
        assert key in payload, key
    assert snapshot["digest"] == digest(payload)


def test_gate_scope_least_privilege(authority: ExecutionAuthority, environment: dict) -> None:
    """`scope-least-privilege`: minting narrows to the profile, never to the ceiling."""

    assert sorted(authority.allowed_tools) == ["fs.read", "fs.write"]
    assert "shell.exec" in environment["grantedTools"]
    assert "shell.exec" not in authority.allowed_tools
    assert authority.path_scopes == ("src/pkg",)
    assert authority.network_scopes == ()
    assert authority.secret_bindings == ()


def test_gate_fencing_current(authority: ExecutionAuthority, clock: FixedClock,
                              held: InMemoryLeaseStore) -> None:
    """`fencing-current`: a write is allowed only while the token is the live one."""

    decision = authority.authorize(
        _request(tool_id="fs.write", effect="write", paths=("src/pkg/a.py",)),
        clock=clock, token_source=held)
    assert decision.allowed is True
    assert decision.code == ""


def test_gate_audit_written() -> None:
    """`audit-written`: every mint emits an audit event carrying its own content address."""

    outputs = handle(_handle_request())
    audit = outputs["audit_event"]
    for key in ("environmentId", "workspaceId", "permissionProfileId", "policySnapshotHash",
                "fencingToken", "authorityDigest", "recordedAt", "digest", "idempotencyKey"):
        assert key in audit, key


# --- negative tests ----------------------------------------------------------


def test_negative_malformed_input_is_rejected() -> None:
    """An unknown request field is refused rather than ignored."""

    with pytest.raises(KernelError) as excinfo:
        handle(_handle_request(surprise={"widen": True}))
    assert excinfo.value.code == "UNKNOWN_FIELD"

    with pytest.raises(KernelError) as missing:
        body = _handle_request()
        del body["permission_profile"]
        handle(body)
    assert missing.value.code == "MISSING_REQUIRED_INPUT"


def test_negative_stale_snapshot_is_rejected(authority: ExecutionAuthority,
                                             clock: FixedClock) -> None:
    """A request justified by a different policy snapshot is stale authority, not a refresh."""

    decision = authority.authorize(
        _request(policy_snapshot_hash="sha256:" + "c" * 64), clock=clock)
    assert decision.allowed is False
    assert decision.code == "AUTHORITY_STALE"


def test_negative_unauthorized_tool_is_denied(authority: ExecutionAuthority,
                                              clock: FixedClock) -> None:
    """A tool outside the allow-list is denied; an unknown tool is never guessed at."""

    decision = authority.authorize(_request(tool_id="shell.exec"), clock=clock)
    assert decision.allowed is False
    assert decision.code == "TOOL_DENIED"
    with pytest.raises(KernelError) as excinfo:
        decision.raise_for_denial()
    assert excinfo.value.code == "TOOL_DENIED"


def test_negative_interrupted_is_not_success() -> None:
    """An interrupted outcome can never be rendered as success."""

    error = KernelError(code="FENCING_REJECTED", message="lease moved mid-write",
                        interrupted=True)
    result = SkillResult.failure("execution-authority-kernel", error,
                                 status=Status.INTERRUPTED)
    assert result.status is Status.INTERRUPTED
    assert result.succeeded is False


def test_negative_partial_is_not_success() -> None:
    """A partial outcome can never be rendered as success either."""

    error = KernelError(code="PARTIAL", message="some scopes resolved", partial=True)
    result = SkillResult.failure("execution-authority-kernel", error, status=Status.PARTIAL)
    assert result.status is Status.PARTIAL
    assert result.succeeded is False


def test_negative_duplicate_side_effect_is_prevented() -> None:
    """Two identical mints produce one idempotency key, so a redelivery is not a second grant."""

    first = handle(_handle_request())
    second = handle(_handle_request())
    assert first["audit_event"]["idempotencyKey"] == second["audit_event"]["idempotencyKey"]
    assert first == second

    different = handle(_handle_request(fencing_token=2))
    assert (different["audit_event"]["idempotencyKey"]
            != first["audit_event"]["idempotencyKey"])


def test_negative_stale_fencing_token_is_rejected(authority: ExecutionAuthority,
                                                  clock: FixedClock,
                                                  held: InMemoryLeaseStore) -> None:
    """A token the lease store has moved past is rejected, for reads and writes alike."""

    clock.advance(700)
    held.acquire("ws-1", "worker-b", ttl_seconds=600)
    decision = authority.authorize(
        _request(tool_id="fs.write", effect="write", paths=("src/pkg/a.py",)),
        clock=clock, token_source=held)
    assert decision.allowed is False
    assert decision.code == "FENCING_REJECTED"


def test_negative_stale_fencing_token_mismatch(authority: ExecutionAuthority,
                                               clock: FixedClock) -> None:
    """A request presenting a token the authority was not minted with is rejected."""

    decision = authority.authorize(_request(fencing_token=7), clock=clock)
    assert decision.allowed is False
    assert decision.code == "FENCING_REJECTED"


def test_negative_prompt_injection_cannot_expand_authority(environment: dict, profile: dict,
                                                           authority: ExecutionAuthority,
                                                           clock: FixedClock) -> None:
    """Three escalation vectors, all refused by construction rather than by judgement."""

    # 1. A profile (data, possibly repo-supplied) asking for more than the environment grants.
    greedy = dict(profile, tools=["fs.read", "net.exfiltrate"])
    with pytest.raises(KernelError) as escalation:
        mint(environment, greedy, now=clock.now(), fencing_token=1)
    assert escalation.value.code == "SCOPE_ESCALATION_ATTEMPT"

    # 2. A profile reaching outside the environment's path ceiling.
    outside = dict(profile, pathScopes=["/etc"])
    with pytest.raises(KernelError):
        mint(environment, outside, now=clock.now(), fencing_token=1)

    # 3. derive() cannot widen, no matter what asks it to.
    with pytest.raises(KernelError) as widened:
        authority.derive(allowed_tools=frozenset({"fs.read", "shell.exec"}))
    assert widened.value.code == "AUTHORITY_SCOPE_MISMATCH"

    # 4. A request claiming conversational provenance is refused outright.
    decision = authority.authorize(_request(authority_source="conversation"), clock=clock)
    assert decision.allowed is False
    assert decision.code == "THREAD_GLOBAL_AUTHORITY_FORBIDDEN"


# --- non-negotiable invariants ----------------------------------------------


def test_invariant_i1_thread_global_authority_forbidden(clock: FixedClock) -> None:
    """I1: authority can never be bound to a conversation, thread or session."""

    for subject in ("conversation", "thread", "session", "anything-else"):
        with pytest.raises(KernelError) as excinfo:
            ExecutionAuthority(
                environment_id="env-1", workspace_id="ws-1",
                permission_profile_id="profile-standard", policy_snapshot_hash=POLICY_HASH,
                fencing_token=1, allowed_tools=frozenset({"fs.read"}), path_scopes=("src",),
                network_scopes=(), secret_bindings=(), issued_at=clock.now(),
                expires_at=clock.now() + timedelta(seconds=60), subject=subject,
            )
        assert excinfo.value.code == "THREAD_GLOBAL_AUTHORITY_FORBIDDEN"
    assert ALLOWED_SUBJECTS == ("environment", "workspace")


def test_invariant_i2_unknown_denies(authority: ExecutionAuthority, clock: FixedClock,
                                     held: InMemoryLeaseStore) -> None:
    """I2: an unrecognised permission denies instead of falling through."""

    unknown_effect = authority.authorize(_request(effect="mutate"), clock=clock,
                                         token_source=held)
    assert unknown_effect.allowed is False
    assert unknown_effect.code == "AUTHORITY_DENIED"

    # The authority grants no network scope at all, so every destination is denied.
    network = authority.authorize(
        _request(network_destinations=("registry.internal:443",)), clock=clock,
        token_source=held)
    assert network.allowed is False
    assert network.code == "NETWORK_SCOPE_DENIED"

    secret = authority.authorize(_request(secret_bindings=("binding.npm",)), clock=clock,
                                 token_source=held)
    assert secret.allowed is False
    assert secret.code == "SECRET_BINDING_DENIED"


def test_invariant_i3_model_switch_cannot_change_permissions() -> None:
    """I3: authority has no model dimension, and a request cannot smuggle one in."""

    assert "model" not in handle(_handle_request())["execution_authority"]
    with pytest.raises(KernelError) as excinfo:
        AuthorityRequest.from_mapping(
            {"toolId": "fs.read", "fencingToken": 1, "model": "some-bigger-model"},
            default_environment_id="env-1", default_workspace_id="ws-1",
            default_policy_snapshot_hash=POLICY_HASH)
    assert excinfo.value.code == "UNKNOWN_FIELD"


def test_invariant_i4_old_worker_authority_dies_with_the_lease(
        authority: ExecutionAuthority, clock: FixedClock, held: InMemoryLeaseStore) -> None:
    """I4: once the lease moves on, the old worker's authority stops authorising writes."""

    write = _request(tool_id="fs.write", effect="write", paths=("src/pkg/a.py",))
    assert authority.authorize(write, clock=clock, token_source=held).allowed is True
    clock.advance(700)  # worker-a stalls past its lease
    held.acquire("ws-1", "worker-b", ttl_seconds=600)
    after = authority.authorize(write, clock=clock, token_source=held)
    assert after.allowed is False
    assert after.code == "FENCING_REJECTED"


# --- path, network and expiry semantics -------------------------------------


def test_path_prefix_confusion_is_rejected(authority: ExecutionAuthority,
                                           clock: FixedClock) -> None:
    """``src/pkg`` must not contain ``src/pkgevil``: containment is component-wise."""

    inside = authority.authorize(_request(paths=("src/pkg/mod.py",)), clock=clock)
    assert inside.allowed is True
    outside = authority.authorize(_request(paths=("src/pkgevil/mod.py",)), clock=clock)
    assert outside.allowed is False
    assert outside.code == "PATH_SCOPE_DENIED"


@pytest.mark.parametrize(
    "path",
    ["src/pkg/../../etc/passwd", "/etc/passwd", "~/.ssh/id_rsa", "..", "src\\pkg\\a.py",
     "src/pkg/../../../root"],
)
def test_path_escapes_are_rejected(authority: ExecutionAuthority, clock: FixedClock,
                                   path: str) -> None:
    """Everything that can be seen textually to leave the scope is refused."""

    decision = authority.authorize(_request(paths=(path,)), clock=clock)
    assert decision.allowed is False
    assert decision.code == "PATH_SCOPE_DENIED"


def test_path_traversal_that_stays_inside_is_allowed(authority: ExecutionAuthority,
                                                     clock: FixedClock) -> None:
    """``..`` is normalised, not banned outright, when the result stays in scope."""

    decision = authority.authorize(_request(paths=("src/pkg/sub/../mod.py",)), clock=clock)
    assert decision.allowed is True


def test_expiry_is_enforced_against_the_injected_clock(authority: ExecutionAuthority,
                                                       clock: FixedClock) -> None:
    decision = authority.authorize(_request(), clock=clock)
    assert decision.allowed is True
    clock.advance(901)
    expired = authority.authorize(_request(), clock=clock)
    assert expired.allowed is False
    assert expired.code == "AUTHORITY_EXPIRED"


def test_wildcard_network_grants_are_refused(clock: FixedClock) -> None:
    """A grant that is not explicit is not a grant."""

    with pytest.raises(KernelError) as excinfo:
        ExecutionAuthority(
            environment_id="env-1", workspace_id="ws-1",
            permission_profile_id="profile-standard", policy_snapshot_hash=POLICY_HASH,
            fencing_token=1, allowed_tools=frozenset({"net.get"}), path_scopes=(),
            network_scopes=("*.internal:443",), secret_bindings=(), issued_at=clock.now(),
            expires_at=clock.now() + timedelta(seconds=60),
        )
    assert excinfo.value.code == "MALFORMED_INPUT"


def test_write_without_a_verified_token_source_is_denied(authority: ExecutionAuthority,
                                                         clock: FixedClock) -> None:
    """Holding an integer is not holding a lease."""

    decision = authority.authorize(
        _request(tool_id="fs.write", effect="write", paths=("src/pkg/a.py",)), clock=clock)
    assert decision.allowed is False
    assert decision.code == "WRITE_REQUIRES_FENCING"


def test_attested_token_source_refuses_a_foreign_resource() -> None:
    """"No lease here" and "token zero" must not be the same observation."""

    source = AttestedTokenSource(resource_id="ws-1", token=3)
    assert source.current_token("ws-1") == 3
    with pytest.raises(KernelError) as excinfo:
        source.current_token("ws-2")
    assert excinfo.value.code == "FENCING_REJECTED"


# --- derivation --------------------------------------------------------------


def test_derive_narrows_and_records_its_parent(authority: ExecutionAuthority) -> None:
    child = authority.derive(allowed_tools=frozenset({"fs.read"}),
                             path_scopes=("src/pkg/sub",),
                             expires_at=authority.expires_at - timedelta(seconds=60))
    assert sorted(child.allowed_tools) == ["fs.read"]
    assert child.path_scopes == ("src/pkg/sub",)
    assert child.expires_at < authority.expires_at
    assert child.derived_from == authority.digest


@pytest.mark.parametrize(
    "kwargs",
    [
        {"path_scopes": ("src",)},
        {"path_scopes": ("src/pkgevil",)},
        {"network_scopes": ("registry.internal:443",)},
        {"secret_bindings": ("binding.npm",)},
    ],
)
def test_derive_cannot_widen(authority: ExecutionAuthority, kwargs: dict) -> None:
    with pytest.raises(KernelError) as excinfo:
        authority.derive(**kwargs)
    assert excinfo.value.code == "AUTHORITY_SCOPE_MISMATCH"


def test_derive_cannot_extend_expiry(authority: ExecutionAuthority) -> None:
    with pytest.raises(KernelError) as excinfo:
        authority.derive(expires_at=authority.expires_at + timedelta(seconds=1))
    assert excinfo.value.code == "AUTHORITY_SCOPE_MISMATCH"


# --- explainability, determinism and tamper detection ------------------------


def test_every_decision_explains_every_check(authority: ExecutionAuthority,
                                             clock: FixedClock) -> None:
    """An allow that cannot be explained is a bug; so is a denial that hides the rest."""

    decision = authority.authorize(_request(), clock=clock)
    assert tuple(reason.check for reason in decision.reasons) == CHECK_ORDER
    assert all(reason.detail for reason in decision.reasons)

    broken = authority.authorize(
        _request(tool_id="shell.exec", paths=("/etc/passwd",),
                 authority_source="conversation"), clock=clock)
    assert [reason.code for reason in broken.denials] == [
        "THREAD_GLOBAL_AUTHORITY_FORBIDDEN", "TOOL_DENIED", "PATH_SCOPE_DENIED",
    ]


def test_an_incomplete_decision_trace_is_refused() -> None:
    """The wrong answer is rejected, not just the right one accepted."""

    with pytest.raises(KernelError) as excinfo:
        AuthorityDecision(
            allowed=True,
            reasons=(Reason(check=CHECK_ORDER[0], outcome="pass", detail="only check"),),
            authority_digest="sha256:" + "0" * 64,
            request_digest="sha256:" + "1" * 64,
            decided_at="2026-01-01T00:00:00.000000Z",
        )
    assert excinfo.value.code == "AUTHORITY_DENIED"


def test_a_decision_cannot_disagree_with_its_trace(authority: ExecutionAuthority,
                                                   clock: FixedClock) -> None:
    denied = authority.authorize(_request(tool_id="shell.exec"), clock=clock)
    with pytest.raises(KernelError):
        AuthorityDecision(
            allowed=True, reasons=denied.reasons,
            authority_digest=denied.authority_digest, request_digest=denied.request_digest,
            decided_at=denied.decided_at,
        )


def test_mutating_the_snapshot_breaks_its_digest(authority: ExecutionAuthority) -> None:
    snapshot = authority.snapshot()
    tampered = dict(snapshot["authority"])
    tampered["allowedTools"] = sorted(set(tampered["allowedTools"]) | {"shell.exec"})
    assert digest(tampered) != snapshot["digest"]


def test_minting_is_deterministic(environment: dict, profile: dict) -> None:
    first = mint(environment, profile, now=datetime(2026, 1, 1, tzinfo=UTC), fencing_token=1)
    second = mint(environment, profile, now=datetime(2026, 1, 1, tzinfo=UTC), fencing_token=1)
    assert first.digest == second.digest


# --- registry ---------------------------------------------------------------


def test_registry_round_trip() -> None:
    result = dispatch("execution-authority-kernel", _handle_request(
        tool_request={"toolId": "fs.write", "effect": "write", "paths": ["src/a.py"],
                      "fencingToken": 1}))
    assert result.status is Status.SUCCEEDED
    assert result.outputs["authorization_decision"]["decision"]["allowed"] is True


def test_registry_round_trip_reports_a_denial_without_raising() -> None:
    """A denial is a successful decision; the trace is the product and must survive."""

    result = dispatch("execution-authority-kernel", _handle_request(
        tool_request={"toolId": "shell.exec", "effect": "read", "fencingToken": 1}))
    assert result.status is Status.SUCCEEDED
    decision = result.outputs["authorization_decision"]["decision"]
    assert decision["allowed"] is False
    assert decision["code"] == "TOOL_DENIED"


def test_registry_normalises_a_failure_into_the_envelope() -> None:
    result = dispatch("execution-authority-kernel", {"nonsense": True})
    assert result.status is Status.FAILED
    assert result.error is not None
    assert result.error["code"] in ("UNKNOWN_FIELD", "MISSING_REQUIRED_INPUT")
