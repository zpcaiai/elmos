"""Exact, authority-bound local runtime for commercial capability handlers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from .artifacts import ContentAddressedArtifactStore, _bind_runtime_artifact_access
from .authority import AuthorityProof, AuthorityVerifier, DenyAllAuthorityVerifier
from .canonical import canonical_json_bytes, digest_object, require_digest, to_jsonable
from .contracts import (
    CapabilityLease,
    Evidence,
    EvidenceStatus,
    HandlerRequest,
    HandlerResult,
    Invocation,
    Outcome,
    PolicyDecision,
    Scope,
    SkillInputContract,
    _mint_handler_request,
    assert_lease_secret_refs,
    utc_now,
    validate_handler_inputs,
)
from .errors import (
    AuthorizationError,
    CommercialRuntimeError,
    ContractError,
    IntegrityError,
    TransitionConflict,
)
from .store import InvocationSnapshot, SQLiteControlPlaneStore, _bind_runtime_writer


@dataclass(frozen=True, slots=True)
class RuntimeReceipt:
    invocation_id: str
    state: str
    outcome: str
    result_digest: str | None
    result: Mapping[str, Any] | None
    replayed: bool
    certification_status: str = "NOT_CERTIFIED"
    external_evidence_status: str = "NOT_RUN"

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_jsonable(self))


def _registry(repository_root: Path | None = None) -> tuple[
    Mapping[str, Callable[[HandlerRequest], HandlerResult]],
    Mapping[str, SkillInputContract],
    str,
    str,
]:
    """Validate exact callable identity, input contracts and pinned manifest."""

    from .kernels import _exact_registry
    from .service import _registry_facts

    EXACT_SKILL_HANDLERS, EXACT_SKILL_INPUT_CONTRACTS = _exact_registry()
    if not isinstance(EXACT_SKILL_HANDLERS, Mapping):
        raise IntegrityError("exact Skill registry is not a mapping", code="REGISTRY_INVALID")
    handlers = dict(EXACT_SKILL_HANDLERS)
    contracts = dict(EXACT_SKILL_INPUT_CONTRACTS)
    if len(handlers) != 85 or set(handlers) != set(contracts):
        raise IntegrityError("exact Skill registry/contract cardinality mismatch", code="REGISTRY_INVALID")
    if len({id(handler) for handler in handlers.values()}) != len(handlers):
        raise IntegrityError("exact Skill handlers must be distinct callables", code="REGISTRY_INVALID")
    for skill_id, handler in handlers.items():
        if not callable(handler) or getattr(handler, "__elmos_exact_skill_id__", None) != skill_id:
            raise IntegrityError("exact Skill callable self-binding mismatch", code="REGISTRY_INVALID")
        if not isinstance(contracts[skill_id], SkillInputContract):
            raise IntegrityError("exact Skill input contract is invalid", code="REGISTRY_INVALID")
    facts = _registry_facts(repository_root)
    if not facts["exact"] or not isinstance(facts["manifest_digest"], str):
        raise IntegrityError("pinned commercial manifest does not match the exact registry", code="REGISTRY_INVALID")
    return (
        MappingProxyType(handlers),
        MappingProxyType(contracts),
        str(facts["registry_digest"]),
        str(facts["manifest_digest"]),
    )


class CommercialCapabilityRuntime:
    """Executes allowlisted pure/local handlers behind host-minted authority.

    The runtime has no generic import, shell, SQL, HTTP, provider or plugin
    dispatcher.  Every call is resolved by exact key from
    the package-private exact registry and runs with bounded JSON values only.
    """

    def __init__(
        self,
        *,
        store: SQLiteControlPlaneStore,
        artifact_store: ContentAddressedArtifactStore,
        authority_verifier: AuthorityVerifier | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self._handlers, self._input_contracts, self._registry_digest, self._manifest_digest = _registry(
            repository_root
        )
        self._store = store
        self._writer = _bind_runtime_writer(store)
        self._artifact_store = artifact_store
        self._artifact_access = _bind_runtime_artifact_access(artifact_store)
        self._authority_verifier: AuthorityVerifier = authority_verifier or DenyAllAuthorityVerifier()

    def request_digest(
        self,
        scope: Scope,
        skill_id: str,
        action: str,
        inputs: Mapping[str, Any],
    ) -> str:
        contract = self._input_contracts.get(skill_id)
        if contract is None:
            raise ContractError("unknown exact Skill input contract", code="UNKNOWN_SKILL")
        frozen_inputs = validate_handler_inputs(
            inputs,
            ephemeral_sensitive_fields=contract.ephemeral_sensitive_fields,
        )
        contract.validate(frozen_inputs, require_all=True)
        input_digest = digest_object(frozen_inputs, domain="invocation-inputs")
        return digest_object(
            {
                "action": action,
                "input_digest": input_digest,
                "scope_digest": scope.digest,
                "skill_id": skill_id,
            },
            domain="invocation-request",
        )

    def prepare_invocation(
        self,
        *,
        scope: Scope,
        skill_id: str,
        action: str,
        inputs: Mapping[str, Any],
        idempotency_key: str,
        ttl: timedelta = timedelta(minutes=5),
    ) -> Invocation:
        handler = self._handlers.get(skill_id)
        if handler is None or not callable(handler):
            raise ContractError(
                "unknown or non-routable exact Skill",
                code="UNKNOWN_SKILL",
                details={"skill_id": skill_id},
            )
        if not isinstance(action, str) or not action:
            raise ContractError("action is required")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ContractError("idempotency_key is required")
        if not isinstance(ttl, timedelta) or ttl <= timedelta(0) or ttl > timedelta(minutes=15):
            raise ContractError("invocation ttl must be between zero and fifteen minutes")
        contract = self._input_contracts[skill_id]
        frozen_inputs = validate_handler_inputs(
            inputs,
            ephemeral_sensitive_fields=contract.ephemeral_sensitive_fields,
        )
        contract.validate(frozen_inputs, require_all=True)
        request_digest = self.request_digest(scope, skill_id, action, frozen_inputs)
        invocation_key_digest = digest_object(
            {
                "action": action,
                "actor_id": scope.actor_id,
                "idempotency_key": idempotency_key,
                "project_id": scope.project_id,
                "skill_id": skill_id,
                "tenant_id": scope.tenant_id,
            },
            domain="invocation-key",
        )
        issued_at = utc_now()
        return Invocation(
            invocation_id="inv-" + invocation_key_digest.removeprefix("sha256:")[:32],
            scope=scope,
            skill_id=skill_id,
            action=action,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            issued_at=issued_at,
            expires_at=issued_at + ttl,
        )

    def execute(
        self,
        invocation: Invocation,
        *,
        inputs: Mapping[str, Any],
        decision: PolicyDecision,
        lease: CapabilityLease,
        authority_proof: AuthorityProof | None,
    ) -> RuntimeReceipt:
        handler = self._handlers.get(invocation.skill_id)
        if handler is None or not callable(handler):
            raise ContractError(
                "unknown or non-routable exact Skill",
                code="UNKNOWN_SKILL",
                details={"skill_id": invocation.skill_id},
            )
        contract = self._input_contracts[invocation.skill_id]
        frozen_inputs = validate_handler_inputs(
            inputs,
            ephemeral_sensitive_fields=contract.ephemeral_sensitive_fields,
        )
        contract.validate(frozen_inputs, require_all=True)
        actual_request_digest = self.request_digest(
            invocation.scope,
            invocation.skill_id,
            invocation.action,
            frozen_inputs,
        )
        if actual_request_digest != invocation.request_digest:
            raise IntegrityError("execution inputs do not match invocation digest", code="REQUEST_DIGEST_MISMATCH")

        # A valid dataclass is not authority.  Only the injected host verifier
        # can authenticate and authorize the decision + lease envelope.
        self._authority_verifier.verify(invocation, decision, lease, authority_proof)
        assert_lease_secret_refs(
            frozen_inputs,
            lease,
            ephemeral_sensitive_fields=contract.ephemeral_sensitive_fields,
        )
        request = _mint_handler_request(
            invocation=invocation,
            lease=lease,
            inputs=frozen_inputs,
            context={
                "certification_status": "NOT_CERTIFIED",
                "external_evidence_status": "NOT_RUN",
                "runtime_status": "LOCAL_BOUNDED_UNQUALIFIED",
                "registry_digest": self._registry_digest,
                "manifest_digest": self._manifest_digest,
            },
            ephemeral_sensitive_fields=contract.ephemeral_sensitive_fields,
        )
        snapshot = self._writer.begin_invocation(invocation, lease, frozen_inputs)
        if snapshot.state == "COMPLETED":
            return self._receipt(snapshot, replayed=True)
        if snapshot.terminal:
            return self._receipt(snapshot, replayed=True)

        snapshot = self._advance_to_execution(snapshot)
        try:
            result = handler(request)
            if not isinstance(result, HandlerResult):
                raise IntegrityError("exact handler returned a non-contract result", code="HANDLER_RESULT_INVALID")
            result = self._bind_and_persist_local_evidence(invocation, decision, lease, result)
            if snapshot.state == "EXECUTING":
                self._writer.append_checkpoint(
                    invocation.scope,
                    invocation.invocation_id,
                    {"handler_result_digest": result.digest, "handler_status": result.status.value},
                    event_id=f"{invocation.invocation_id}:handler:{snapshot.sequence}",
                )
                snapshot = self._writer.transition_invocation(
                    invocation.scope,
                    invocation.invocation_id,
                    expected_sequence=snapshot.sequence,
                    expected_state="EXECUTING",
                    new_state="PERSISTING",
                )
            if snapshot.state != "PERSISTING":
                raise TransitionConflict("invocation is not in a persistable state")
            snapshot = self._writer.commit_result(
                invocation.scope,
                invocation.invocation_id,
                expected_sequence=snapshot.sequence,
                result=result,
            )
            return self._receipt(snapshot, replayed=False)
        except CommercialRuntimeError:
            self._mark_failed_if_possible(invocation.scope, invocation.invocation_id)
            raise
        except Exception as exc:
            self._mark_failed_if_possible(invocation.scope, invocation.invocation_id)
            raise CommercialRuntimeError("exact handler execution failed", code="HANDLER_EXECUTION_FAILED") from exc

    def read_artifact(
        self,
        invocation: Invocation,
        *,
        digest: str,
        decision: PolicyDecision,
        lease: CapabilityLease,
        authority_proof: AuthorityProof | None,
    ) -> bytes:
        """Read an invocation-owned artifact after fresh authority verification."""

        require_digest(digest, "artifact digest")
        self._authority_verifier.verify(invocation, decision, lease, authority_proof)
        snapshot = self._store.get_invocation(invocation.scope, invocation.invocation_id)
        persisted_binding = (
            snapshot.skill_id,
            snapshot.action,
            snapshot.idempotency_key,
            snapshot.request_digest,
            snapshot.lease_digest,
        )
        presented_binding = (
            invocation.skill_id,
            invocation.action,
            invocation.idempotency_key,
            invocation.request_digest,
            lease.digest,
        )
        if persisted_binding != presented_binding:
            raise AuthorizationError(
                "artifact read authority does not match the persisted invocation",
                code="ARTIFACT_READ_BINDING_MISMATCH",
            )
        if snapshot.state != "COMPLETED" or snapshot.result is None:
            raise AuthorizationError(
                "artifact reads require a completed invocation",
                code="ARTIFACT_READ_NOT_AUTHORIZED",
            )
        artifacts = snapshot.result.get("artifacts", ())
        owned = isinstance(artifacts, (tuple, list)) and any(
            isinstance(item, Mapping) and item.get("digest") == digest for item in artifacts
        )
        if not owned:
            raise AuthorizationError(
                "artifact is not bound to the authorized invocation",
                code="ARTIFACT_READ_NOT_AUTHORIZED",
            )
        return self._artifact_access.get(invocation.scope, digest)

    def _advance_to_execution(self, snapshot: InvocationSnapshot) -> InvocationSnapshot:
        if snapshot.state == "PENDING":
            snapshot = self._writer.transition_invocation(
                snapshot.scope,
                snapshot.invocation_id,
                expected_sequence=snapshot.sequence,
                expected_state="PENDING",
                new_state="AUTHORIZED",
            )
        if snapshot.state == "AUTHORIZED":
            snapshot = self._writer.transition_invocation(
                snapshot.scope,
                snapshot.invocation_id,
                expected_sequence=snapshot.sequence,
                expected_state="AUTHORIZED",
                new_state="EXECUTING",
            )
        if snapshot.state not in {"EXECUTING", "PERSISTING"}:
            raise TransitionConflict("invocation cannot be executed from its persisted state")
        return snapshot

    def _bind_and_persist_local_evidence(
        self,
        invocation: Invocation,
        decision: PolicyDecision,
        lease: CapabilityLease,
        result: HandlerResult,
    ) -> HandlerResult:
        if result.skill_id != invocation.skill_id:
            raise IntegrityError("handler result Skill identity mismatch", code="RESULT_SKILL_MISMATCH")
        unauthorized_effects = set(result.side_effects) - set(lease.side_effects)
        if unauthorized_effects:
            raise IntegrityError(
                "handler reported effects outside its capability lease",
                code="UNAUTHORIZED_SIDE_EFFECT",
                details={"effects": sorted(unauthorized_effects)},
            )
        for artifact in result.artifacts:
            self._artifact_access.verify(invocation.scope, artifact)
        for evidence in result.evidence:
            if evidence.scope != invocation.scope or evidence.invocation_id != invocation.invocation_id:
                raise IntegrityError("handler evidence scope binding mismatch", code="EVIDENCE_SCOPE_MISMATCH")
            if evidence.authorization_id != decision.decision_id:
                raise IntegrityError("handler evidence authority binding mismatch", code="EVIDENCE_AUTHORITY_MISMATCH")

        artifact = self._artifact_access.put(
            invocation.scope,
            canonical_json_bytes(result.to_dict()),
            media_type="application/vnd.elmos.commercial-handler-result+json",
            kind="handler-result",
            producer_id="elmos-commercial-capability-runtime@2.0.0",
        )
        status_map = {
            Outcome.LOCAL_EXECUTED_SELF_ATTESTED: EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED,
            Outcome.FAILED: EvidenceStatus.FAILED,
            Outcome.UNKNOWN: EvidenceStatus.UNKNOWN,
            Outcome.INCONCLUSIVE: EvidenceStatus.INCONCLUSIVE,
        }
        evidence_status = status_map.get(result.status, EvidenceStatus.NOT_RUN)
        evidence = Evidence(
            evidence_id="ev-" + artifact.digest.removeprefix("sha256:")[:32],
            scope=invocation.scope,
            invocation_id=invocation.invocation_id,
            category="LOCAL_HANDLER_EXECUTION",
            subject_digest=invocation.request_digest,
            content_digest=artifact.digest,
            status=evidence_status,
            producer_id="elmos-commercial-capability-runtime@2.0.0",
            verifier_id=None,
            authorization_id=decision.decision_id,
            produced_at=utc_now(),
            artifact_digests=(artifact.digest,),
            metadata={
                "capability_lease_digest": lease.digest,
                "external_evidence_status": "NOT_RUN",
                "local_evidence_ceiling": "LOCAL_EXECUTED_SELF_ATTESTED",
            },
        )
        return HandlerResult(
            skill_id=result.skill_id,
            status=result.status,
            output=result.output,
            artifacts=(*result.artifacts, artifact),
            evidence=(*result.evidence, evidence),
            unresolved=result.unresolved,
            side_effects=result.side_effects,
            metrics=result.metrics,
        )

    def _mark_failed_if_possible(self, scope: Scope, invocation_id: str) -> None:
        try:
            snapshot = self._store.get_invocation(scope, invocation_id)
        except CommercialRuntimeError:
            return
        if snapshot.state in {"PENDING", "AUTHORIZED", "EXECUTING", "PERSISTING"}:
            try:
                self._writer.transition_invocation(
                    scope,
                    invocation_id,
                    expected_sequence=snapshot.sequence,
                    expected_state=snapshot.state,
                    new_state="FAILED",
                    error_code="HANDLER_EXECUTION_FAILED",
                )
            except CommercialRuntimeError:
                return

    @staticmethod
    def _receipt(snapshot: InvocationSnapshot, *, replayed: bool) -> RuntimeReceipt:
        outcome = "NOT_RUN"
        if snapshot.result is not None:
            value = snapshot.result.get("status")
            if isinstance(value, str):
                outcome = value
        elif snapshot.state in {"DENIED", "FAILED", "BLOCKED"}:
            outcome = snapshot.state
        return RuntimeReceipt(
            invocation_id=snapshot.invocation_id,
            state=snapshot.state,
            outcome=outcome,
            result_digest=snapshot.result_digest,
            result=snapshot.result,
            replayed=replayed,
        )
