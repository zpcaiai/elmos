"""Stateless turn coordinator with durable recovery semantics."""

from __future__ import annotations

import time
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import BudgetExceeded, ContractViolation, LeaseLost, NotConfigured
from .firewall import FirewallContext
from .gates import CompletionGateEngine
from .ledger import EventLedger, FencedLease
from .models import Budget, CompletionProposal, ExecutionManifest, Identity, Observation, Usage
from .observability import UsageAttribution
from .providers import ProviderAdapter, ProviderRequest, ProviderResponse, ProviderRouter, RouteConstraints
from .tools import ToolGateway
from .tools import CancellationToken
from .workspace import WorkspaceLease


@dataclass(frozen=True, slots=True)
class RuntimeTurnInput:
    identity: Identity
    manifest: ExecutionManifest
    budget: Budget
    context: Mapping[str, Any]
    tool_schemas: tuple[Mapping[str, Any], ...] = ()
    route_constraints: RouteConstraints | None = None
    workspace: WorkspaceLease | None = None
    firewall_context: FirewallContext | None = None
    approval: str | None = None
    checkpoint: Mapping[str, Any] | None = None
    deadline_epoch: float | None = None
    cancellation: CancellationToken | None = None


@dataclass(frozen=True, slots=True)
class RuntimeTurnResult:
    status: str
    event_seq: int
    observation: Observation | None = None
    completion: CompletionProposal | None = None
    checkpoint_id: str | None = None
    usage: Usage = Usage()
    reason: str | None = None


class RuntimeStateProjection:
    """Pure projection; no runtime object stores authoritative history."""

    @staticmethod
    def from_events(ledger: EventLedger, identity: Identity) -> dict[str, Any]:
        ledger.assert_identity(identity)
        return ledger.rebuild_projection(identity.tenant_id, identity.run_id)


class AgentRuntime:
    def __init__(self, ledger: EventLedger, provider: ProviderAdapter | ProviderRouter, gateway: ToolGateway, gates: CompletionGateEngine | None = None, *, owner: str = "runtime", lease_seconds: float = 60.0, supervisor: Any | None = None, telemetry: Any | None = None) -> None:
        self.ledger = ledger
        self.provider = provider
        self.gateway = gateway
        self.gates = gates
        self.owner = owner
        self.lease_seconds = lease_seconds
        self.supervisor = supervisor
        self.telemetry = telemetry

    def register(self, identity: Identity, manifest: ExecutionManifest) -> None:
        self.ledger.create_run(identity, manifest.digest, "ready")
        self.ledger.append(identity, "run.status", {"status": "ready", "manifest_hash": manifest.digest}, idempotency_key="run-ready:" + manifest.digest)

    def run_turn(self, request: RuntimeTurnInput, *, now: float | None = None) -> RuntimeTurnResult:
        attribution = UsageAttribution(request.identity, request.manifest.provider, request.manifest.model, region=request.manifest.region)
        span = nullcontext() if self.telemetry is None else self.telemetry.span("elmos.agent.turn", attribution, {"elmos.manifest.digest": request.manifest.digest})
        with span:
            result = self._run_turn(request, now=now)
            if self.telemetry is not None:
                self.telemetry.record_usage(attribution, result.usage)
            return result

    def _run_turn(self, request: RuntimeTurnInput, *, now: float | None = None) -> RuntimeTurnResult:
        now = time.time() if now is None else now
        started_at = time.time()
        supervision_state = "blocked"
        self._validate_budget(request.budget)
        if request.deadline_epoch is not None and request.deadline_epoch <= now:
            raise ContractViolation("turn deadline has already elapsed")
        if request.cancellation is not None and request.cancellation.cancelled:
            self.cancel(request.identity, request.cancellation.reason)
            return RuntimeTurnResult("cancelled", self._last_seq(request.identity), reason="CANCELLED")
        if self.supervisor is not None:
            try:
                self.supervisor.before_turn(request.identity, now=now)
            except KeyError:
                deadline = request.deadline_epoch or now + request.budget.max_wall_seconds
                self.supervisor.register(request.identity, deadline_epoch=deadline, now=now)
                self.supervisor.before_turn(request.identity, now=now)
        lease = self.ledger.acquire_lease(request.identity, self.owner, self.lease_seconds, now)
        turn_id = str(request.context.get("turn_id") or self._next_turn_id(request.identity))
        try:
            if self.gates is not None:
                self.gates.hooks.run("pre_run", request.identity, {"turn_id": turn_id, "manifest_hash": request.manifest.digest})
            self.ledger.assert_lease(lease, now)
            self.ledger.append(request.identity, "run.status", {"status": "running"}, idempotency_key=f"turn-running:{request.identity.run_id}:{turn_id}")
            self.ledger.append(request.identity, "agent.turn.started", {"manifest_hash": request.manifest.digest, "turn_id": turn_id}, idempotency_key=f"turn-start:{request.identity.run_id}:{turn_id}")
            projection = RuntimeStateProjection.from_events(self.ledger, request.identity)
            usage_so_far = projection["usage"]
            self._check_budget(request.budget, usage_so_far, len(projection["actions"]), now, now)
            try:
                if self.supervisor is not None:
                    self.supervisor.heartbeat(request.identity, "provider", now=time.time())
                if self.gates is not None:
                    self.gates.hooks.run("pre_provider", request.identity, {"turn_id": turn_id, "provider": self._provider_name()})
                provider_request = ProviderRequest(
                    request.identity,
                    request.manifest.model,
                    dict(request.context),
                    request.tool_schemas,
                    request.checkpoint,
                    f"provider:{request.identity.run_id}:{request.identity.node_id}:{turn_id}",
                )
                with self._span(request, "elmos.provider.decide"):
                    provider_response = self._decide(provider_request, request.route_constraints)
                if self.gates is not None:
                    self.gates.hooks.run("post_provider", request.identity, {"turn_id": turn_id, "provider": provider_response.provider or self._provider_name(), "usage": provider_response.usage.as_dict()})
            except Exception as error:
                self.ledger.append(request.identity, "provider.failed", {"provider": self._provider_name(), "error": str(error)[:500]}, idempotency_key=f"provider-failed:{request.identity.run_id}:{turn_id}")
                self.ledger.append(request.identity, "run.status", {"status": "blocked", "reason": "PROVIDER_FAILURE"}, idempotency_key="provider-blocked:" + request.identity.run_id)
                supervision_state = "blocked"
                return RuntimeTurnResult("blocked", self._last_seq(request.identity), reason="PROVIDER_FAILURE")
            projected_usage = {"input_tokens": int(usage_so_far.get("input_tokens", 0)) + provider_response.usage.input_tokens, "output_tokens": int(usage_so_far.get("output_tokens", 0)) + provider_response.usage.output_tokens, "cost_micros": int(usage_so_far.get("cost_micros", 0)) + provider_response.usage.cost_micros}
            self._check_budget(request.budget, projected_usage, len(projection["actions"]) + (1 if provider_response.action else 0), started_at, time.time())
            if provider_response.usage.input_tokens + usage_so_far["input_tokens"] > request.budget.max_input_tokens or provider_response.usage.output_tokens + usage_so_far["output_tokens"] > request.budget.max_output_tokens:
                raise BudgetExceeded("provider token budget exceeded")
            self.ledger.append(request.identity, "agent.decision", {"kind": "action" if provider_response.action else "completion", "provider": provider_response.provider or self._provider_name(), "turn_id": turn_id}, idempotency_key=f"decision:{request.identity.run_id}:{turn_id}", usage=provider_response.usage)
            if provider_response.completion is not None:
                self.ledger.append(request.identity, "agent.completion.proposed", {"run_id": provider_response.completion.run_id, "summary": provider_response.completion.summary, "claimed_status": provider_response.completion.claimed_status, "test_refs": list(provider_response.completion.test_refs), "turn_id": turn_id}, idempotency_key=f"completion:{request.identity.run_id}:{turn_id}")
                checkpoint = self._checkpoint(request, lease, provider_response.usage, {"phase": "completion-proposed"}, provider_response.provider_checkpoint)
                supervision_state = "waiting"
                return RuntimeTurnResult("completion_proposed", self._last_seq(request.identity), completion=provider_response.completion, checkpoint_id=checkpoint, usage=provider_response.usage)
            action = provider_response.action
            if action is None:
                raise ContractViolation("provider returned no action or completion")
            context = request.firewall_context or FirewallContext(request.identity, allowed_capabilities=frozenset())
            if self.gates is not None:
                self.gates.hooks.run("pre_tool", request.identity, action.as_dict())
            if self.supervisor is not None:
                self.supervisor.heartbeat(request.identity, "tool", now=time.time())
            with self._span(request, "elmos.tool.execute", tool=action.tool):
                observation = self.gateway.execute(request.identity, action, context, approved_by=request.approval, cancellation=request.cancellation)
            if self.gates is not None:
                self.gates.hooks.run("post_tool", request.identity, {"action": action.as_dict(), "observation": observation})
            self.ledger.assert_lease(lease, time.time())
            checkpoint = self._checkpoint(request, lease, provider_response.usage, {"phase": "observation", "action_id": action.action_id, "status": observation.status.value}, provider_response.provider_checkpoint)
            if observation.status.value == "blocked":
                self.ledger.append(request.identity, "run.status", {"status": "blocked"}, idempotency_key=f"run-blocked:{action.idempotency_key}")
                supervision_state = "blocked"
                return RuntimeTurnResult("blocked", self._last_seq(request.identity), observation=observation, checkpoint_id=checkpoint, usage=provider_response.usage)
            if observation.status.value == "cancelled":
                self.ledger.append(request.identity, "run.status", {"status": "cancelled"}, idempotency_key=f"run-cancelled:{action.idempotency_key}")
                supervision_state = "cancelled"
                return RuntimeTurnResult("cancelled", self._last_seq(request.identity), observation=observation, checkpoint_id=checkpoint, usage=provider_response.usage)
            supervision_state = "ready"
            return RuntimeTurnResult("ready", self._last_seq(request.identity), observation=observation, checkpoint_id=checkpoint, usage=provider_response.usage)
        except LeaseLost:
            raise
        except BudgetExceeded as error:
            self.ledger.append(request.identity, "run.status", {"status": "blocked", "reason": error.code}, idempotency_key="budget-blocked:" + request.identity.run_id)
            supervision_state = "blocked"
            return RuntimeTurnResult("blocked", self._last_seq(request.identity), reason=error.code)
        except Exception as error:
            self.ledger.append(request.identity, "runtime.failed", {"error": str(error)[:500]}, idempotency_key=f"runtime-failed:{request.identity.run_id}:{turn_id}")
            self.ledger.append(request.identity, "run.status", {"status": "blocked", "reason": "RUNTIME_FAILURE"}, idempotency_key="runtime-blocked:" + request.identity.run_id)
            if self.gates is not None:
                self.gates.hooks.run("on_failure", request.identity, {"turn_id": turn_id, "error_type": type(error).__name__})
            supervision_state = "blocked"
            return RuntimeTurnResult("blocked", self._last_seq(request.identity), reason="RUNTIME_FAILURE")
        finally:
            self.ledger.release_lease(lease)
            if self.supervisor is not None:
                self.supervisor.complete_turn(request.identity, supervision_state, now=time.time())
            if self.gates is not None:
                self.gates.hooks.run("post_run", request.identity, {"turn_id": turn_id, "state": supervision_state})

    def propose_final(self, identity: Identity, proposal: CompletionProposal, checks: Mapping[str, str], evidence: Mapping[str, Any]) -> Any:
        if self.gates is None:
            raise NotConfigured("completion gates are not configured")
        decision = self.gates.evaluate(identity, proposal, checks, evidence)
        self.ledger.append(identity, "verification.completed", decision.as_dict(), idempotency_key="verification:" + proposal.run_id + ":" + decision.digest)
        status = "succeeded" if decision.status == "pass" else "blocked"
        self.ledger.append(identity, "run.status", {"status": status}, idempotency_key="run-final:" + proposal.run_id + ":" + decision.digest)
        return decision

    def resume(self, identity: Identity, manifest: ExecutionManifest) -> dict[str, Any]:
        run = self.ledger.assert_identity(identity)
        if run.manifest_hash != manifest.digest:
            raise ContractViolation("resume manifest does not match original run")
        self.ledger.verify_chain(identity.tenant_id, identity.run_id)
        checkpoint = self.ledger.latest_checkpoint(identity.tenant_id, identity.run_id, identity.node_id)
        return {"run": run, "checkpoint": checkpoint, "projection": RuntimeStateProjection.from_events(self.ledger, identity)}

    def cancel(self, identity: Identity, reason: str) -> None:
        if not reason:
            raise ContractViolation("cancel reason is required")
        self.ledger.append(identity, "run.status", {"status": "cancelled", "reason": reason[:500]}, idempotency_key="cancel:" + identity.run_id + ":" + reason[:64])

    def _checkpoint(self, request: RuntimeTurnInput, lease: FencedLease, usage: Usage, state: dict[str, Any], provider_checkpoint: Mapping[str, Any] | None = None) -> str:
        checkpoint_state = {"runtime": state, "provider": {"provider": self._provider_name(), "checkpoint": None if provider_checkpoint is None else dict(provider_checkpoint)}, "usage": usage.as_dict()}
        if self.gates is not None:
            self.gates.hooks.run("pre_checkpoint", request.identity, {"state": state, "event_seq": self._last_seq(request.identity)})
        checkpoint_id = self.ledger.save_checkpoint(request.identity, event_seq=self._last_seq(request.identity), manifest_hash=request.manifest.digest, state=checkpoint_state, workspace_ref=None if request.workspace is None else request.workspace.workspace_id, context_fingerprint=str(request.context.get("fingerprint", "")))
        if self.gates is not None:
            self.gates.hooks.run("post_checkpoint", request.identity, {"checkpoint_id": checkpoint_id})
        return checkpoint_id

    def _next_turn(self, identity: Identity) -> int:
        return self._last_seq(identity) + 1

    def _decide(self, request: ProviderRequest, constraints: RouteConstraints | None) -> ProviderResponse:
        if isinstance(self.provider, ProviderRouter):
            return self.provider.call(request, constraints or RouteConstraints())
        return self.provider.decide(request)

    def _provider_name(self) -> str:
        if isinstance(self.provider, ProviderRouter):
            return "provider-router"
        return self.provider.capabilities.provider

    def _span(self, request: RuntimeTurnInput, name: str, *, tool: str | None = None) -> Any:
        if self.telemetry is None:
            return nullcontext()
        attribution = UsageAttribution(request.identity, request.manifest.provider, request.manifest.model, tool, request.manifest.region)
        return self.telemetry.span(name, attribution, {"elmos.manifest.digest": request.manifest.digest})

    def _next_turn_id(self, identity: Identity) -> str:
        self.ledger.assert_identity(identity)
        count = sum(1 for event in self.ledger.events(identity.tenant_id, identity.run_id, limit=100_000) if event.event_type == "agent.turn.started")
        return f"turn-{count}"

    def _last_seq(self, identity: Identity) -> int:
        self.ledger.assert_identity(identity)
        events = self.ledger.events(identity.tenant_id, identity.run_id, limit=100_000)
        return -1 if not events else events[-1].seq

    @staticmethod
    def _validate_budget(budget: Budget) -> None:
        if budget.max_tool_calls == 0:
            raise BudgetExceeded("tool budget is zero")

    @staticmethod
    def _check_budget(budget: Budget, usage: Mapping[str, Any], calls: int, started: float, current: float) -> None:
        if int(usage.get("input_tokens", 0)) > budget.max_input_tokens or int(usage.get("output_tokens", 0)) > budget.max_output_tokens:
            raise BudgetExceeded("budget already exceeded")
        if int(usage.get("cost_micros", 0)) > budget.max_cost_micros:
            raise BudgetExceeded("cost budget exceeded")
        if calls > budget.max_tool_calls:
            raise BudgetExceeded("tool budget exceeded")
        if current - started > budget.max_wall_seconds:
            raise BudgetExceeded("wall-clock budget exceeded")
