"""Observation-first integration seam for the v1.2 cache parity plane.

The runtime translates real cache decisions into the closed v1.2 outcome
taxonomy.  It may persist content-free observations, but it never turns a
provider-prefix, environment, native-build or partial CAS hit into authority
to skip execution.  Serving switches remain independent and default off.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
import math
from typing import Any, Protocol

from .canonical import digest_of
from .clock import SYSTEM_CLOCK, Clock
from .config import CacheParityConfig, validate_parity_config
from .enums import MissReason
from .errors import ContractViolation, PermissionDenied
from .miss_diagnostics import (
    CacheCohort,
    CacheLayer,
    CacheOutcome,
    CacheOutcomeEvent,
    CacheOutcomeReason,
    UnexpectedMissBudget,
)
from .security import ProvenanceSigner, SignedStatement, require_asymmetric


class CacheOutcomeSink(Protocol):
    def put_cache_outcome(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        event_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]: ...


class ParityServingControl(Protocol):
    """Executable layer wiring, supplied by trusted runtime composition.

    A configuration boolean is not wiring.  A layer may be reported as
    serving only when an actual control can report its state and can latch a
    rollback.  Repository YAML cannot construct one of these controls.
    """

    def is_serving(self) -> bool: ...

    def latch_rollback(self, reason_code: str) -> None: ...


class ServingAuthorizer(Protocol):
    """Fail-closed PEP used by HTTP and other serving entry points."""

    def authorize_serving(self, layer: str, tenant_id: str, project_id: str) -> None: ...

    def latch_rollback(self, reason_code: str) -> None: ...

    def report(self) -> dict[str, Any] | None: ...


SERVING_GATE_KIND = "elmos.cache-parity-serving-gate/v1"
SERVING_GATE_DECISION = "SERVING_AUTHORIZED"
SERVING_GATE_MAX_TTL_SECONDS = 86_400
SERVING_LAYERS: tuple[str, ...] = (
    "provider_prompt",
    "environment_snapshot",
    "affinity",
    "multi_layer_coordinator",
)
_SERVING_PHASES = frozenset(
    {"internal", "canary", "5_percent", "25_percent", "50_percent", "100_percent"}
)


def serving_gate_statement(
    config: CacheParityConfig,
    tenant_id: str,
    project_id: str,
    allowed_layers: Sequence[str],
    *,
    issued_at: float,
    expires_at: float,
) -> dict[str, Any]:
    """Build the exact claims an external gate authority must sign.

    This helper creates no authority: a runtime accepts the statement only
    after an independently injected asymmetric verifier validates the
    signature and every tenant/project/phase/config/time binding.
    """

    layers = tuple(sorted(allowed_layers))
    if not layers or len(set(layers)) != len(layers):
        raise ContractViolation("serving gate requires unique allowed layers")
    unknown = sorted(set(layers) - set(SERVING_LAYERS))
    if unknown:
        raise ContractViolation("serving gate contains unknown layers", layers=unknown)
    if (
        isinstance(issued_at, bool)
        or isinstance(expires_at, bool)
        or not isinstance(issued_at, int | float)
        or not isinstance(expires_at, int | float)
        or not math.isfinite(float(issued_at))
        or not math.isfinite(float(expires_at))
        or expires_at <= issued_at
        or expires_at - issued_at > SERVING_GATE_MAX_TTL_SECONDS
    ):
        raise ContractViolation("serving gate time bounds are invalid")
    return {
        "schema_version": "1.2.0",
        "tenant_id": tenant_id,
        "project_id": project_id,
        "rollout_phase": config.rollout_phase,
        "parity_config_digest": digest_of(asdict(config)),
        "allowed_layers": list(layers),
        "decision": SERVING_GATE_DECISION,
        "issued_at": float(issued_at),
        "expires_at": float(expires_at),
    }


_REASON_MAP: dict[MissReason, tuple[CacheOutcome, CacheOutcomeReason]] = {
    MissReason.NO_ENTRY: (CacheOutcome.NECESSARY_MISS, CacheOutcomeReason.COLD_NO_ENTRY),
    MissReason.SOURCE_DIGEST_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.PROMPT_SEGMENT_CHANGED,
    ),
    MissReason.PUBLIC_INTERFACE_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.PUBLIC_INTERFACE_CHANGED,
    ),
    MissReason.DEPENDENCY_LOCK_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.LOCKFILE_CHANGED,
    ),
    MissReason.RULE_PACK_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.RULE_PACK_CHANGED,
    ),
    MissReason.STAGE_VERSION_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.PREFIX_COMPATIBILITY_CHANGED,
    ),
    MissReason.STAGE_CONTRACT_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.PREFIX_COMPATIBILITY_CHANGED,
    ),
    MissReason.TOOLCHAIN_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.ENVIRONMENT_CHANGED,
    ),
    MissReason.TARGET_PROFILE_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.PREFIX_COMPATIBILITY_CHANGED,
    ),
    MissReason.COMPILER_FLAGS_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.ENVIRONMENT_CHANGED,
    ),
    MissReason.DECLARED_ENVIRONMENT_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.ENVIRONMENT_CHANGED,
    ),
    MissReason.PROMPT_TEMPLATE_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.PROMPT_SEGMENT_CHANGED,
    ),
    MissReason.MODEL_SNAPSHOT_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.MODEL_CHANGED,
    ),
    MissReason.TOOL_OUTPUT_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.PROMPT_SEGMENT_CHANGED,
    ),
    MissReason.FEATURE_FLAG_CHANGED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.PREFIX_COMPATIBILITY_CHANGED,
    ),
    MissReason.SCHEMA_INCOMPATIBLE: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.PREFIX_COMPATIBILITY_CHANGED,
    ),
    MissReason.VALIDATION_TOO_LOW: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.VALIDATION_REQUIREMENT_CHANGED,
    ),
    MissReason.TRUST_NAMESPACE_MISMATCH: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.TRUST_NAMESPACE_MISMATCH,
    ),
    MissReason.TENANT_MISMATCH: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.TENANT_MISMATCH,
    ),
    MissReason.PROVENANCE_INVALID: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.AUTHORIZATION_DENIED,
    ),
    MissReason.ENTRY_EXPIRED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.TTL_EXPIRED,
    ),
    MissReason.ENTRY_REVOKED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.SNAPSHOT_REVOKED,
    ),
    MissReason.ENTRY_QUARANTINED: (
        CacheOutcome.NECESSARY_MISS,
        CacheOutcomeReason.SNAPSHOT_REVOKED,
    ),
    MissReason.ARTIFACT_MISSING: (
        CacheOutcome.UNEXPECTED_MISS,
        CacheOutcomeReason.UNKNOWN_MISS,
    ),
    MissReason.ARTIFACT_CORRUPT: (
        CacheOutcome.UNEXPECTED_MISS,
        CacheOutcomeReason.CORRUPT_OBJECT,
    ),
    MissReason.RESTORE_COST_EXCEEDS_RECOMPUTE: (
        CacheOutcome.BYPASS,
        CacheOutcomeReason.RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE,
    ),
    MissReason.POLICY_BYPASS: (CacheOutcome.BYPASS, CacheOutcomeReason.POLICY_BYPASS),
    MissReason.NONDETERMINISTIC_STAGE: (
        CacheOutcome.BYPASS,
        CacheOutcomeReason.POLICY_BYPASS,
    ),
}


class ParityRuntime:
    """Collect observations and expose requested, wired and serving state."""

    def __init__(
        self,
        config: CacheParityConfig,
        tenant_id: str,
        project_id: str,
        *,
        sink: CacheOutcomeSink | None = None,
        clock: Clock = SYSTEM_CLOCK,
        serving_controls: Mapping[str, ParityServingControl] | None = None,
        serving_gate_receipt: SignedStatement | None = None,
        serving_gate_verifier: ProvenanceSigner | None = None,
    ) -> None:
        validate_parity_config(config)
        controls = dict(serving_controls or {})
        unknown_controls = sorted(set(controls) - set(SERVING_LAYERS))
        if unknown_controls:
            raise ContractViolation(
                "cache parity runtime contains unknown serving controls",
                layers=unknown_controls,
            )
        self.config = config
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.sink = sink
        self.clock = clock
        self._serving_controls = controls
        self._serving_gate_receipt = serving_gate_receipt
        self._serving_gate_verifier = serving_gate_verifier
        self.budget = UnexpectedMissBudget()
        self._outcomes: Counter[str] = Counter()
        self._reasons: Counter[str] = Counter()
        self._events = 0
        self._persistence_errors = 0
        self._last_persistence_error: str | None = None
        self._rollback_latched = False
        self._rollback_reason: str | None = None
        self._rollback_delivery_errors: set[str] = set()
        self._wiring_errors: set[str] = set()

    def _requested_layers(self) -> frozenset[str]:
        requested: set[str] = set()
        if self.config.prompt_cache.enabled and self.config.prompt_cache.mode == "serve":
            requested.add("provider_prompt")
        if self.config.environment_snapshots.enabled:
            requested.add("environment_snapshot")
        if self.config.affinity.enabled:
            requested.add("affinity")
        if self.config.coordinator.enabled:
            requested.add("multi_layer_coordinator")
        return frozenset(requested)

    def _latch_rollback(self, reason_code: str) -> None:
        if self._rollback_latched:
            return
        self._rollback_latched = True
        self._rollback_reason = reason_code
        for layer, control in self._serving_controls.items():
            try:
                control.latch_rollback(reason_code)
            except Exception:  # noqa: BLE001 - rollback remains latched and failure is visible
                self._rollback_delivery_errors.add(layer)

    def latch_rollback(self, reason_code: str) -> None:
        """Public PEP hook for a serving adapter that detects a runtime failure."""

        self._latch_rollback(reason_code)

    def authorize_serving(self, layer: str, tenant_id: str, project_id: str) -> None:
        """Authorize one exact layer only when the effective report says serving.

        Tenant/project mismatch, an unknown layer, absent wiring, invalid or
        expired receipt, observation-only phase and a rollback latch all share
        the same non-authorizing outcome.
        """

        if layer not in SERVING_LAYERS:
            raise ContractViolation("unknown cache parity serving layer", layer=layer)
        report = self.report()
        allowed = (
            tenant_id == self.tenant_id
            and project_id == self.project_id
            and report is not None
            and bool(report["serving"][layer])
        )
        if not allowed:
            state = "PARITY_PLANE_DISABLED" if report is None else "SERVING_NOT_AUTHORIZED"
            if report is not None:
                layer_wiring = report["wiring"]["layers"][layer]
                gate_state = report["serving_gate_receipt"]["status"]
                if layer_wiring == "NOT_WIRED":
                    state = "NOT_WIRED"
                elif gate_state != "VERIFIED":
                    state = str(report["serving_gate_receipt"]["reason_code"])
                elif report["rollback"]["latched"]:
                    state = str(report["rollback"]["reason_code"])
            raise PermissionDenied(
                "cache parity serving is not authorized",
                layer=layer,
                state=state,
            )

    def _serving_gate(self, requested: frozenset[str]) -> tuple[dict[str, Any], frozenset[str]]:
        if not requested:
            return (
                {
                    "required": False,
                    "status": "NOT_REQUIRED",
                    "reason_code": None,
                    "key_id": None,
                    "authorized_layers": [],
                },
                frozenset(),
            )
        if self.config.rollout_phase not in _SERVING_PHASES:
            return (
                {
                    "required": True,
                    "status": "BLOCKED",
                    "reason_code": "NON_SERVING_ROLLOUT_PHASE",
                    "key_id": None,
                    "authorized_layers": [],
                },
                frozenset(),
            )
        receipt = self._serving_gate_receipt
        if receipt is None:
            return (
                {
                    "required": True,
                    "status": "MISSING",
                    "reason_code": "SERVING_GATE_RECEIPT_MISSING",
                    "key_id": None,
                    "authorized_layers": [],
                },
                frozenset(),
            )
        verifier = self._serving_gate_verifier
        if verifier is None:
            return (
                {
                    "required": True,
                    "status": "NOT_WIRED",
                    "reason_code": "SERVING_GATE_VERIFIER_NOT_WIRED",
                    "key_id": None,
                    "authorized_layers": [],
                },
                frozenset(),
            )
        try:
            require_asymmetric(verifier)
            verifier.verify_statement(receipt)
        except Exception:  # noqa: BLE001 - cryptographic failure details stay internal
            return (
                {
                    "required": True,
                    "status": "INVALID",
                    "reason_code": "SERVING_GATE_SIGNATURE_INVALID",
                    "key_id": None,
                    "authorized_layers": [],
                },
                frozenset(),
            )
        expected_keys = {
            "schema_version",
            "tenant_id",
            "project_id",
            "rollout_phase",
            "parity_config_digest",
            "allowed_layers",
            "decision",
            "issued_at",
            "expires_at",
        }
        statement = receipt.statement
        issued_at = statement.get("issued_at")
        expires_at = statement.get("expires_at")
        allowed = statement.get("allowed_layers")
        bindings_valid = (
            receipt.kind == SERVING_GATE_KIND
            and set(statement) == expected_keys
            and statement.get("schema_version") == "1.2.0"
            and statement.get("tenant_id") == self.tenant_id
            and statement.get("project_id") == self.project_id
            and statement.get("rollout_phase") == self.config.rollout_phase
            and statement.get("parity_config_digest") == digest_of(asdict(self.config))
            and statement.get("decision") == SERVING_GATE_DECISION
            and isinstance(allowed, list)
            and all(isinstance(layer, str) for layer in allowed)
            and len(allowed) == len(set(allowed))
            and set(allowed) == set(requested)
            and not isinstance(issued_at, bool)
            and not isinstance(expires_at, bool)
            and isinstance(issued_at, int | float)
            and isinstance(expires_at, int | float)
            and math.isfinite(float(issued_at))
            and math.isfinite(float(expires_at))
            and expires_at > issued_at
            and expires_at - issued_at <= SERVING_GATE_MAX_TTL_SECONDS
        )
        if not bindings_valid:
            return (
                {
                    "required": True,
                    "status": "INVALID",
                    "reason_code": "SERVING_GATE_BINDING_INVALID",
                    "key_id": None,
                    "authorized_layers": [],
                },
                frozenset(),
            )
        assert isinstance(issued_at, int | float) and not isinstance(issued_at, bool)
        assert isinstance(expires_at, int | float) and not isinstance(expires_at, bool)
        assert isinstance(allowed, list)
        now = self.clock.now()
        if now < float(issued_at) - 300 or now >= float(expires_at):
            return (
                {
                    "required": True,
                    "status": "INVALID",
                    "reason_code": "SERVING_GATE_TIME_INVALID",
                    "key_id": None,
                    "authorized_layers": [],
                },
                frozenset(),
            )
        authorized = frozenset(str(layer) for layer in allowed)
        return (
            {
                "required": True,
                "status": "VERIFIED",
                "reason_code": None,
                "key_id": receipt.key_id,
                "authorized_layers": sorted(authorized),
            },
            authorized,
        )

    def observe_action(
        self,
        *,
        node_id: str,
        action_key: str | None,
        hit: bool,
        miss_reasons: Sequence[MissReason] = (),
        cohort: CacheCohort = CacheCohort.DEFAULT,
    ) -> dict[str, Any]:
        if hit:
            event = CacheOutcomeEvent(
                CacheLayer.ACTION,
                CacheOutcome.HIT,
                CacheOutcomeReason.EXACT_RESULT_REUSED,
                True,
                cohort,
            )
        else:
            primary = miss_reasons[0] if miss_reasons else None
            outcome, reason = (
                _REASON_MAP[primary]
                if primary is not None and primary in _REASON_MAP
                else (CacheOutcome.UNEXPECTED_MISS, CacheOutcomeReason.UNKNOWN_MISS)
            )
            event = CacheOutcomeEvent(CacheLayer.ACTION, outcome, reason, True, cohort)

        self.budget.observe(event)
        self._events += 1
        self._outcomes[event.outcome.value] += 1
        self._reasons[event.reason.value] += 1
        request_id = "cache_request_" + digest_of(
            {
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "node_id": node_id,
                "action_key": action_key,
                "observation": self._events,
            }
        ).removeprefix("sha256:")
        event_id = "cache_event_" + digest_of(
            {"request_id": request_id, "diagnostic": event.diagnostic()}
        ).removeprefix("sha256:")
        document: dict[str, Any] = {
            "schema_version": "1.2.0",
            "event_id": event_id,
            "request_id": request_id,
            "layer": "ACTION",
            "outcome": event.outcome.value,
            "reason_code": event.reason.value,
            "eligible": event.eligible,
            "occurred_at": datetime.fromtimestamp(self.clock.now(), tz=UTC).isoformat(),
        }
        if self.sink is not None:
            try:
                self.sink.put_cache_outcome(
                    self.tenant_id,
                    self.project_id,
                    request_id,
                    event_id,
                    document,
                )
            except Exception as exc:  # noqa: BLE001 - observation must not break correct execution
                # Only the exception class is retained: backend messages may
                # contain connection details. A serving parity layer sees the
                # degraded flag and must roll back; the v1.1 correctness path
                # remains usable while telemetry storage is unavailable.
                self._persistence_errors += 1
                self._last_persistence_error = type(exc).__name__
                self._latch_rollback("OBSERVATION_PERSISTENCE_FAILED")
        return document

    def report(self) -> dict[str, Any] | None:
        if not self.config.enabled:
            return None
        requested = self._requested_layers()
        gate, authorized = self._serving_gate(requested)
        if requested and gate["status"] != "VERIFIED":
            self._latch_rollback(str(gate["reason_code"]))
        if requested and self.sink is None:
            self._latch_rollback("OBSERVATION_PERSISTENCE_NOT_WIRED")

        actual: dict[str, bool] = {}
        for layer, control in self._serving_controls.items():
            try:
                state = control.is_serving()
                if not isinstance(state, bool):
                    raise TypeError("serving state must be boolean")
                actual[layer] = state
            except Exception:  # noqa: BLE001 - control failure must fail closed
                actual[layer] = False
                self._wiring_errors.add(layer)
                self._latch_rollback("SERVING_CONTROL_FAILED")
        for layer, state in actual.items():
            if state and layer not in requested & authorized:
                self._latch_rollback("UNAUTHORIZED_SERVING_STATE")

        serving = {
            layer: (
                not self._rollback_latched
                and gate["status"] == "VERIFIED"
                and self.sink is not None
                and layer in requested
                and layer in authorized
                and actual.get(layer, False)
            )
            for layer in SERVING_LAYERS
        }
        return {
            "schema_version": self.config.schema_version,
            "claim_mode": self.config.claim_mode,
            "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
            "external_provider_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "rollout_phase": self.config.rollout_phase,
            "serving_requested": {
                layer: layer in requested for layer in SERVING_LAYERS
            },
            "serving": serving,
            "wiring": {
                "observation_persistence": "WIRED" if self.sink is not None else "NOT_WIRED",
                "serving_gate_verifier": (
                    "WIRED" if self._serving_gate_verifier is not None else "NOT_WIRED"
                ),
                "layers": {
                    layer: "WIRED" if layer in self._serving_controls else "NOT_WIRED"
                    for layer in SERVING_LAYERS
                },
                "requested_not_wired": sorted(requested - set(self._serving_controls)),
                "errors": sorted(self._wiring_errors),
            },
            "serving_gate_receipt": gate,
            "rollback": {
                "latched": self._rollback_latched,
                "reason_code": self._rollback_reason,
                "delivery_errors": sorted(self._rollback_delivery_errors),
            },
            "safety": {
                "automatic_rollback": self.config.automatic_rollback,
                "false_hit_immediate_rollback": self.config.false_hit_immediate_rollback,
                "whole_repository_reinjection": (
                    self.config.context_ledger.whole_repository_reinjection
                ),
                "secret_values_in_environment_snapshot": (
                    self.config.environment_snapshots.embed_secret_values
                ),
            },
            "observations": {
                "events": self._events,
                "outcomes": dict(sorted(self._outcomes.items())),
                "reasons": dict(sorted(self._reasons.items())),
                "unexpected_budget": self.budget.to_dict(),
                "persistence_errors": self._persistence_errors,
                "last_persistence_error": self._last_persistence_error,
            },
            "degraded": (
                self._persistence_errors > 0
                or self._rollback_latched
                or bool(requested - set(self._serving_controls))
                or bool(self._wiring_errors)
                or bool(self._rollback_delivery_errors)
            ),
        }


__all__ = [
    "CacheOutcomeSink",
    "ParityRuntime",
    "ParityServingControl",
    "ServingAuthorizer",
    "SERVING_GATE_DECISION",
    "SERVING_GATE_KIND",
    "SERVING_LAYERS",
    "serving_gate_statement",
]
