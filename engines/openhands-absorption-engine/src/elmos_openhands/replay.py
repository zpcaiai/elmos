"""Checkpoint bundles, safe resume and replay/re-execution coordination."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Mapping, Protocol

from .errors import ContractViolation, CorruptState, NotConfigured
from .firewall import FirewallContext
from .models import Action, ExecutionManifest, Identity, digest_of
from .tools import ToolGateway


class ReplayMode(StrEnum):
    AUDIT_ONLY = "audit_only"
    ISOLATED_REEXECUTION = "isolated_reexecution"


@dataclass(frozen=True, slots=True)
class CheckpointPolicy:
    every_events: int = 1
    every_seconds: float = 60.0
    before_mutation: bool = True
    after_mutation: bool = True

    def __post_init__(self) -> None:
        if self.every_events < 1 or self.every_seconds <= 0:
            raise ContractViolation("checkpoint cadence must be positive")

    def due(self, *, events_since: int, seconds_since: float, mutating: bool = False, phase: str = "after") -> bool:
        if events_since >= self.every_events or seconds_since >= self.every_seconds:
            return True
        return mutating and ((phase == "before" and self.before_mutation) or (phase == "after" and self.after_mutation))


@dataclass(frozen=True, slots=True)
class CheckpointBundle:
    checkpoint_id: str
    identity: Identity
    event_seq: int
    manifest_hash: str
    runtime_state: Mapping[str, Any]
    provider_state: Mapping[str, Any]
    workspace_ref: str | None
    context_fingerprint: str | None
    digest: str

    @classmethod
    def from_row(cls, identity: Identity, row: Mapping[str, Any]) -> "CheckpointBundle":
        if str(row.get("tenant_id")) != identity.tenant_id or str(row.get("run_id")) != identity.run_id or str(row.get("node_id")) != identity.node_id:
            raise CorruptState("checkpoint scope does not match resume identity")
        state = row.get("state")
        if not isinstance(state, Mapping):
            raise CorruptState("checkpoint state is not an object")
        runtime = state.get("runtime", {})
        provider = state.get("provider", {})
        if not isinstance(runtime, Mapping) or not isinstance(provider, Mapping):
            raise CorruptState("checkpoint runtime/provider state is invalid")
        body = {
            "tenant_id": identity.tenant_id,
            "run_id": identity.run_id,
            "node_id": identity.node_id,
            "event_seq": int(row["event_seq"]),
            "manifest_hash": str(row["manifest_hash"]),
            "state": dict(state),
            "workspace_ref": row.get("workspace_ref"),
            "context_fingerprint": row.get("context_fingerprint"),
        }
        if digest_of(body) != str(row.get("digest", "")):
            raise CorruptState("checkpoint digest verification failed")
        return cls(
            str(row["checkpoint_id"]),
            identity,
            int(row["event_seq"]),
            str(row["manifest_hash"]),
            dict(runtime),
            dict(provider),
            None if row.get("workspace_ref") is None else str(row["workspace_ref"]),
            None if row.get("context_fingerprint") is None else str(row["context_fingerprint"]),
            str(row["digest"]),
        )


class ReplayLedger(Protocol):
    def assert_identity(self, identity: Identity) -> Any: ...
    def checkpoints(self, tenant_id: str, run_id: str, *, node_id: str = "root", limit: int = 100, verify: bool = True) -> tuple[dict[str, Any], ...]: ...
    def verify_chain(self, tenant_id: str, run_id: str) -> bool: ...
    def rebuild_projection(self, tenant_id: str, run_id: str) -> dict[str, Any]: ...
    def events(self, tenant_id: str, run_id: str, *, after_seq: int = -1, limit: int = 1000) -> list[Any]: ...
    def append(self, identity: Identity, event_type: str, payload: dict[str, Any], **kwargs: Any) -> Any: ...


class WorkspaceRestorer(Protocol):
    def restore_reference(self, identity: Identity, workspace_ref: str) -> Any: ...


class ProviderResumer(Protocol):
    def resume_state(self, identity: Identity, state: Mapping[str, Any]) -> Any: ...


@dataclass(frozen=True, slots=True)
class ResumeResult:
    checkpoint: CheckpointBundle | None
    projection: Mapping[str, Any]
    reconciled_actions: tuple[str, ...]
    rejected_checkpoints: tuple[str, ...]
    provider_session: Any = None
    workspace: Any = None


class ResumeCoordinator:
    """Restores the newest valid bundle and reconciles ambiguous mutations."""

    def __init__(
        self,
        ledger: ReplayLedger,
        *,
        gateway: ToolGateway | None = None,
        workspace_restorer: WorkspaceRestorer | None = None,
        provider_resumer: ProviderResumer | None = None,
    ) -> None:
        self.ledger = ledger
        self.gateway = gateway
        self.workspace_restorer = workspace_restorer
        self.provider_resumer = provider_resumer

    def resume(
        self,
        identity: Identity,
        manifest: ExecutionManifest,
        *,
        firewall_context: FirewallContext | None = None,
        approval: str | None = None,
    ) -> ResumeResult:
        self.ledger.assert_identity(identity)
        self.ledger.verify_chain(identity.tenant_id, identity.run_id)
        rejected: list[str] = []
        selected: CheckpointBundle | None = None
        workspace: Any = None
        provider_session: Any = None
        for row in self.ledger.checkpoints(identity.tenant_id, identity.run_id, node_id=identity.node_id, limit=100, verify=False):
            checkpoint_id = str(row.get("checkpoint_id", "unknown"))
            try:
                candidate = CheckpointBundle.from_row(identity, row)
                if candidate.manifest_hash != manifest.digest:
                    raise CorruptState("checkpoint manifest is incompatible with resume request")
                candidate_workspace = None
                if candidate.workspace_ref is not None:
                    if self.workspace_restorer is None:
                        raise NotConfigured("checkpoint requires a workspace restorer")
                    candidate_workspace = self.workspace_restorer.restore_reference(identity, candidate.workspace_ref)
                candidate_provider = None
                if candidate.provider_state:
                    if self.provider_resumer is None:
                        raise NotConfigured("checkpoint requires a provider resumer")
                    candidate_provider = self.provider_resumer.resume_state(identity, candidate.provider_state)
            except (CorruptState, NotConfigured, OSError, ValueError):
                rejected.append(checkpoint_id)
                continue
            selected = candidate
            workspace = candidate_workspace
            provider_session = candidate_provider
            break
        reconciled = self.reconcile_unfinished(identity, firewall_context=firewall_context, approval=approval)
        projection = self.ledger.rebuild_projection(identity.tenant_id, identity.run_id)
        self.ledger.append(
            identity,
            "run.resumed",
            {
                "checkpoint_id": None if selected is None else selected.checkpoint_id,
                "rejected_checkpoints": rejected,
                "reconciled_actions": list(reconciled),
                "projection_digest": digest_of(projection),
            },
            idempotency_key="resume:" + digest_of({"manifest": manifest.digest, "checkpoint": None if selected is None else selected.checkpoint_id, "rejected": rejected}),
        )
        return ResumeResult(selected, projection, reconciled, tuple(rejected), provider_session, workspace)

    def reconcile_unfinished(
        self,
        identity: Identity,
        *,
        firewall_context: FirewallContext | None,
        approval: str | None,
    ) -> tuple[str, ...]:
        self.ledger.assert_identity(identity)
        proposed: dict[str, Mapping[str, Any]] = {}
        observed: set[str] = set()
        for event in self.ledger.events(identity.tenant_id, identity.run_id, limit=100_000):
            action_id = str(event.payload.get("action_id", ""))
            if event.event_type == "action.proposed" and action_id:
                proposed[action_id] = event.payload
            elif event.event_type == "tool.observed" and action_id:
                observed.add(action_id)
        unfinished = tuple(sorted(set(proposed) - observed))
        if not unfinished:
            return ()
        if self.gateway is None or firewall_context is None:
            self.ledger.append(
                identity,
                "reconciliation.blocked",
                {"action_ids": list(unfinished), "reason": "gateway_or_policy_context_not_configured"},
                idempotency_key="reconciliation-blocked:" + digest_of(unfinished),
            )
            return ()
        reconciled: list[str] = []
        for action_id in unfinished:
            action = _action_from_payload(proposed[action_id])
            observation = self.gateway.execute(identity, action, firewall_context, approved_by=approval)
            if observation.status.value in {"success", "failure", "blocked", "cancelled"}:
                reconciled.append(action_id)
        return tuple(reconciled)

    def audit_replay(self, identity: Identity) -> Mapping[str, Any]:
        self.ledger.assert_identity(identity)
        self.ledger.verify_chain(identity.tenant_id, identity.run_id)
        projection = self.ledger.rebuild_projection(identity.tenant_id, identity.run_id)
        return {"mode": ReplayMode.AUDIT_ONLY.value, "projection": projection, "digest": digest_of(projection), "side_effects": False}

    def isolated_reexecute(
        self,
        identity: Identity,
        *,
        authorization_ref: str,
        executor: Callable[[tuple[Any, ...]], Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        if not authorization_ref.strip():
            raise ContractViolation("isolated re-execution requires an authorization reference")
        self.ledger.assert_identity(identity)
        events = tuple(self.ledger.events(identity.tenant_id, identity.run_id, limit=100_000))
        result = dict(executor(events))
        body = {
            "mode": ReplayMode.ISOLATED_REEXECUTION.value,
            "authorization_ref": authorization_ref,
            "source_head": None if not events else events[-1].digest,
            "result": result,
        }
        self.ledger.append(
            identity,
            "replay.isolated.completed",
            body,
            idempotency_key="isolated-replay:" + digest_of(body),
        )
        return {**body, "digest": digest_of(body)}


def _action_from_payload(payload: Mapping[str, Any]) -> Action:
    return Action(
        action_id=str(payload["action_id"]),
        tool=str(payload["tool"]),
        args=dict(payload.get("args", {})),
        risk_context=dict(payload.get("risk_context", {})),
        idempotency_key=str(payload["idempotency_key"]),
        read_scope=tuple(payload.get("read_scope", ())),
        write_scope=tuple(payload.get("write_scope", ())),
        expected_side_effects=tuple(payload.get("expected_side_effects", ())),
        required_capabilities=tuple(payload.get("required_capabilities", ())),
        timeout_seconds=float(payload.get("timeout_seconds", 30.0)),
    )
