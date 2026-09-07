"""Durable production composition for multimodal context lifecycle Skills.

The pure functions in :mod:`context` remain usable for bounded local planning.
This bridge adds the tenant-scoped, append-only state and CAS bindings required
by the composed runtime.  Request fields never create authority: policy,
capability observations, restore bindings, and source catalogs come exclusively
from the host-supplied ``RuntimeContext``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, TYPE_CHECKING

from .canonical import canonical_digest, canonical_json, new_id, sha256_bytes, utc_now
from .context import (
    account_multimodal_tokens,
    calculate_context_budget,
    check_codex_capacity_parity,
    checkpoint_and_recover,
    compact_context,
    discover_model_capabilities,
    monitor_context_pressure,
    pack_context,
    rehydrate_context,
    verify_context_integrity,
)
from .errors import ConflictError, IntegrityError, NotFoundError, ValidationError
from .models import TenantContext
from .store import IntakeStore, LocalCasStore

if TYPE_CHECKING:
    from .skill_runtime import RuntimeContext


CONTEXT_LIFECYCLE_SKILLS = frozenset(
    {
        "elmos-codex-context-capacity-parity",
        "elmos-context-budget-manager",
        "elmos-multimodal-token-accounting",
        "elmos-long-context-packing-and-ranking",
        "elmos-context-pressure-monitor",
        "elmos-structured-context-compaction",
        "elmos-context-checkpoint-and-recovery",
        "elmos-context-rehydration",
        "elmos-model-capability-discovery",
        "elmos-context-integrity-and-loss-detection",
    }
)

_PURE_OPERATIONS: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    "elmos-codex-context-capacity-parity": check_codex_capacity_parity,
    "elmos-context-budget-manager": calculate_context_budget,
    "elmos-multimodal-token-accounting": account_multimodal_tokens,
    "elmos-long-context-packing-and-ranking": pack_context,
    "elmos-context-pressure-monitor": monitor_context_pressure,
    "elmos-structured-context-compaction": compact_context,
    "elmos-context-checkpoint-and-recovery": checkpoint_and_recover,
    "elmos-context-rehydration": rehydrate_context,
    "elmos-model-capability-discovery": discover_model_capabilities,
    "elmos-context-integrity-and-loss-detection": verify_context_integrity,
}


def _envelope(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "state": str(result.get("state", "FAILED")),
        "code": str(result.get("code", "CONTEXT_LIFECYCLE_FAILED")),
        "outputs": dict(result.get("outputs", {})),
        "metrics": dict(result.get("metrics", {})),
        "retryable": bool(result.get("retryable", False)),
    }


def _raw_digest(value: Any) -> str:
    return canonical_digest(value)


def _required_text(value: Any, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise ValidationError("CONTEXT_LIFECYCLE_FIELD_INVALID", f"{field} is required")
    return value


class ContextLifecycleBridge:
    """Compose Skills 29-36/39-40 with SQLite, CAS, outbox, and scope gates."""

    def __init__(self, store: IntakeStore, cas: LocalCasStore) -> None:
        self.store = store
        self.cas = cas

    @staticmethod
    def _tenant(ctx: "RuntimeContext") -> TenantContext:
        return TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id)

    @staticmethod
    def _idempotency(ctx: "RuntimeContext", payload: Mapping[str, Any]) -> str:
        key = ctx.idempotency_key or payload.get("idempotency_key")
        return _required_text(key, "idempotency_key", maximum=256)

    @staticmethod
    def _task(ctx: "RuntimeContext", payload: Mapping[str, Any]) -> str:
        value = payload.get("task_id", ctx.request_id)
        return _required_text(value, "task_id", maximum=256)

    @staticmethod
    def _request(ctx: "RuntimeContext", payload: Mapping[str, Any]) -> dict[str, Any]:
        # Only these host-owned mappings may carry authority.  Payload is copied
        # into inputs, where the pure contracts reject authority-shaped fields.
        return {
            "schema_version": "1.0",
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "actor_id": ctx.actor_id,
            "request_id": ctx.request_id,
            "trace_id": ctx.trace_id,
            "idempotency_key": ctx.idempotency_key,
            "inputs": dict(payload),
            "policy": dict(ctx.policy),
            "capabilities": dict(ctx.capabilities),
        }

    def handle(
        self,
        skill_name: str,
        ctx: "RuntimeContext",
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if skill_name not in CONTEXT_LIFECYCLE_SKILLS:
            raise ValidationError("CONTEXT_LIFECYCLE_SKILL_UNSUPPORTED")
        context = self._tenant(ctx)
        self.store.require(context, self.store.READ)
        if {"authorization", "consent", "policy", "capabilities", "permissions", "verified"} & set(payload):
            return _envelope({"state": "BLOCKED", "code": "CONTEXT_AUTHORITY_INPUT_UNTRUSTED", "outputs": {"side_effect_authorized": False}})
        operation = str(payload.get("operation", "execute")).strip().lower().replace("-", "_")
        if operation not in {"history", "list", "diff"}:
            self.store.require(context, self.store.WRITE)
        if skill_name == "elmos-model-capability-discovery":
            return self._capabilities(ctx, payload, operation)
        if skill_name == "elmos-multimodal-token-accounting":
            return self._usage(ctx, payload)
        if skill_name == "elmos-context-pressure-monitor":
            return self._pressure(ctx, payload)
        if skill_name == "elmos-structured-context-compaction":
            return self._compact(ctx, payload)
        if skill_name == "elmos-context-checkpoint-and-recovery":
            return self._checkpoint(ctx, payload, operation)
        if skill_name == "elmos-context-rehydration":
            return self._rehydrate(ctx, payload)
        if skill_name == "elmos-context-integrity-and-loss-detection":
            return self._integrity(ctx, payload)
        return self._record_plan(skill_name, ctx, payload)

    def _call(self, skill: str, ctx: "RuntimeContext", payload: Mapping[str, Any]) -> dict[str, Any]:
        return _PURE_OPERATIONS[skill](self._request(ctx, payload))

    def _record_plan(
        self, skill: str, ctx: "RuntimeContext", payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        result = self._call(skill, ctx, payload)
        if result.get("state") in {"FAILED", "BLOCKED"}:
            return _envelope(result)
        kind = {
            "elmos-codex-context-capacity-parity": "PARITY",
            "elmos-context-budget-manager": "BUDGET",
            "elmos-long-context-packing-and-ranking": "PACKING",
        }[skill]
        key = self._idempotency(ctx, payload)
        task_id = self._task(ctx, payload)
        body = {"skill": skill, "result": result, "request_digest": _raw_digest(dict(payload))}
        digest = _raw_digest(body)
        with self.store.transaction() as connection:
            existing = connection.execute(
                """SELECT record_id,payload_json,payload_digest FROM context_lifecycle_records
                     WHERE tenant_id=? AND project_id=? AND kind=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, kind, key),
            ).fetchone()
            if existing is not None:
                if existing["payload_digest"] != digest:
                    raise ConflictError("CONTEXT_LIFECYCLE_IDEMPOTENCY_CONFLICT")
                replay = json.loads(str(existing["payload_json"]))
                replay["result"]["outputs"]["durable_record_id"] = str(existing["record_id"])
                replay["result"]["outputs"]["idempotent_replay"] = True
                return _envelope(replay["result"])
            record_id = new_id("ctx-record")
            connection.execute(
                """INSERT INTO context_lifecycle_records VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ctx.tenant_id, ctx.project_id, record_id, task_id, kind,
                    ctx.request_id, key, None, canonical_json(body), digest, utc_now(),
                ),
            )
            self.store._event(
                connection, self._tenant(ctx), "context_lifecycle", record_id,
                f"context.{kind.lower()}.recorded", f"context-{kind.lower()}:{key}",
                {"record_id": record_id, "task_id": task_id, "payload_digest": digest},
            )
        result["outputs"]["durable_record_id"] = record_id
        result["outputs"]["idempotent_replay"] = False
        return _envelope(result)

    def _capabilities(
        self, ctx: "RuntimeContext", payload: Mapping[str, Any], operation: str
    ) -> dict[str, Any]:
        if operation in {"history", "list"}:
            provider = _required_text(payload.get("provider"), "provider")
            model_id = _required_text(payload.get("model_id"), "model_id")
            with self.store.read_transaction() as connection:
                rows = connection.execute(
                    """SELECT snapshot_json FROM context_capability_snapshots
                         WHERE tenant_id=? AND project_id=? AND provider=? AND model_id=?
                         ORDER BY version DESC""",
                    (ctx.tenant_id, ctx.project_id, provider, model_id),
                ).fetchall()
            return _envelope({"state": "SUCCEEDED", "code": "MODEL_CAPABILITY_HISTORY_LISTED", "outputs": {"snapshots": [json.loads(str(row[0])) for row in rows]}})
        if operation == "rollback":
            target_id = _required_text(payload.get("snapshot_id"), "snapshot_id")
            key = self._idempotency(ctx, payload)
            with self.store.transaction() as connection:
                row = connection.execute(
                    """SELECT * FROM context_capability_snapshots
                         WHERE tenant_id=? AND project_id=? AND snapshot_id=?""",
                    (ctx.tenant_id, ctx.project_id, target_id),
                ).fetchone()
                if row is None:
                    raise NotFoundError("MODEL_CAPABILITY_SNAPSHOT_NOT_FOUND")
                connection.execute(
                    """INSERT INTO context_capability_heads VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(tenant_id,project_id,provider,model_id) DO UPDATE SET
                         snapshot_id=excluded.snapshot_id, version=excluded.version,
                         updated_at=excluded.updated_at""",
                    (ctx.tenant_id, ctx.project_id, row["provider"], row["model_id"], target_id, row["version"], utc_now()),
                )
                self.store._event(
                    connection, self._tenant(ctx), "context_capability", target_id,
                    "context.capability.rolled_back", f"context-capability-rollback:{key}",
                    {"snapshot_id": target_id, "version": int(row["version"])},
                )
            return _envelope({"state": "SUCCEEDED", "code": "MODEL_CAPABILITY_ROLLED_BACK", "outputs": {"snapshot": json.loads(str(row["snapshot_json"]))}})

        result = self._call("elmos-model-capability-discovery", ctx, payload)
        if result.get("state") != "SUCCEEDED":
            return _envelope(result)
        snapshot = dict(result["outputs"]["snapshot"])
        key = self._idempotency(ctx, payload)
        with self.store.transaction() as connection:
            existing = connection.execute(
                """SELECT snapshot_json,snapshot_digest FROM context_capability_snapshots
                     WHERE tenant_id=? AND project_id=? AND snapshot_id=?""",
                (ctx.tenant_id, ctx.project_id, snapshot["snapshot_id"]),
            ).fetchone()
            digest = _raw_digest(snapshot)
            if existing is not None and existing["snapshot_digest"] != digest:
                raise ConflictError("MODEL_CAPABILITY_SNAPSHOT_CONFLICT")
            head = connection.execute(
                """SELECT snapshot_id FROM context_capability_heads
                     WHERE tenant_id=? AND project_id=? AND provider=? AND model_id=?""",
                (ctx.tenant_id, ctx.project_id, snapshot["provider"], snapshot["model_id"]),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO context_capability_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ctx.tenant_id, ctx.project_id, snapshot["snapshot_id"], snapshot["provider"],
                        snapshot["model_id"], snapshot["version"], canonical_json(snapshot), digest,
                        snapshot["source"], snapshot["trust"], snapshot["observed_at"],
                        snapshot["expires_at"], str(head[0]) if head else None, utc_now(),
                    ),
                )
            connection.execute(
                """INSERT INTO context_capability_heads VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(tenant_id,project_id,provider,model_id) DO UPDATE SET
                     snapshot_id=excluded.snapshot_id,version=excluded.version,updated_at=excluded.updated_at""",
                (ctx.tenant_id, ctx.project_id, snapshot["provider"], snapshot["model_id"], snapshot["snapshot_id"], snapshot["version"], utc_now()),
            )
            self.store._event(
                connection, self._tenant(ctx), "context_capability", snapshot["snapshot_id"],
                "context.capability.observed", f"context-capability:{key}",
                {"snapshot_id": snapshot["snapshot_id"], "snapshot_digest": digest},
            )
        result["outputs"]["durable"] = True
        return _envelope(result)

    def _usage(self, ctx: "RuntimeContext", payload: Mapping[str, Any]) -> dict[str, Any]:
        result = self._call("elmos-multimodal-token-accounting", ctx, payload)
        if result.get("state") in {"FAILED", "BLOCKED"}:
            return _envelope(result)
        estimates = list(result["outputs"]["estimates"])
        trusted = ctx.capabilities.get("context_provider_usage")
        verified_usage = (
            trusted
            if isinstance(trusted, Mapping) and trusted.get("verified") is True
            else None
        )
        verified = verified_usage is not None
        cumulative_input = (
            int(verified_usage.get("cumulative_input_tokens", 0))
            if verified_usage is not None
            else 0
        )
        cumulative_output = (
            int(verified_usage.get("cumulative_output_tokens", 0))
            if verified_usage is not None
            else 0
        )
        cumulative_cost = (
            int(verified_usage.get("cumulative_cost_minor_units", 0))
            if verified_usage is not None
            else 0
        )
        currency = (
            str(verified_usage.get("currency", "XXX"))
            if verified_usage is not None
            else "XXX"
        )
        current_input = int(result["outputs"]["safe_total_tokens"])
        reserved_output = int(payload.get("current_window_output_reserved_tokens", 0))
        if min(current_input, reserved_output, cumulative_input, cumulative_output, cumulative_cost) < 0:
            raise ValidationError("CONTEXT_USAGE_VALUE_INVALID")
        kinds = {str(item["status"]) for item in estimates}
        estimate_kind = "MEASURED_VERIFIED" if kinds == {"MEASURED_VERIFIED"} else "ESTIMATED_UPPER_BOUND" if len(kinds) == 1 else "MIXED_UPPER_BOUND"
        ledger = {
            "current_window": {"input_tokens": current_input, "output_reserved_tokens": reserved_output},
            "cumulative_provider": {
                "input_tokens": cumulative_input, "output_tokens": cumulative_output,
                "cost_minor_units": cumulative_cost, "currency": currency,
                "state": "VERIFIED" if verified else "UNKNOWN",
            },
            "estimates": estimates,
            "accounting_digest": str(result["outputs"]["accounting_digest"]),
        }
        key = self._idempotency(ctx, payload)
        digest = _raw_digest(ledger)
        with self.store.transaction() as connection:
            existing = connection.execute(
                """SELECT usage_id,record_digest,record_json FROM context_usage_ledger
                     WHERE tenant_id=? AND project_id=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, key),
            ).fetchone()
            if existing is not None:
                if existing["record_digest"] != digest:
                    raise ConflictError("CONTEXT_USAGE_IDEMPOTENCY_CONFLICT")
                ledger = json.loads(str(existing["record_json"]))
                usage_id = str(existing["usage_id"])
                replay = True
            else:
                usage_id = new_id("ctx-usage")
                connection.execute(
                    """INSERT INTO context_usage_ledger VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ctx.tenant_id, ctx.project_id, usage_id, self._task(ctx, payload), ctx.request_id,
                        key, payload.get("model_snapshot_id"), str(payload.get("estimator_version", "multimodal-upper-bound-v1")),
                        str(result["outputs"]["accounting_digest"]).removeprefix("sha256:"),
                        current_input, reserved_output, cumulative_input, cumulative_output, cumulative_cost,
                        currency, estimate_kind, canonical_json(ledger), digest, utc_now(),
                    ),
                )
                self.store._event(
                    connection, self._tenant(ctx), "context_usage", usage_id,
                    "context.usage.recorded", f"context-usage:{key}",
                    {"usage_id": usage_id, "record_digest": digest},
                )
                replay = False
        result["outputs"].update({"usage_id": usage_id, "ledger": ledger, "idempotent_replay": replay})
        return _envelope(result)

    def _pressure(self, ctx: "RuntimeContext", payload: Mapping[str, Any]) -> dict[str, Any]:
        key = self._idempotency(ctx, payload)
        task_id = self._task(ctx, payload)
        with self.store.read_transaction() as connection:
            previous = connection.execute(
                """SELECT pressure_id,pressure_state FROM context_pressure_snapshots
                     WHERE tenant_id=? AND project_id=? AND task_id=?
                     ORDER BY created_at DESC, pressure_id DESC LIMIT 1""",
                (ctx.tenant_id, ctx.project_id, task_id),
            ).fetchone()
        effective = dict(payload)
        effective["previous_state"] = str(previous["pressure_state"]) if previous else "NORMAL"
        result = self._call("elmos-context-pressure-monitor", ctx, effective)
        if result.get("state") != "SUCCEEDED":
            return _envelope(result)
        outputs = dict(result["outputs"])
        forecast_horizon = int(payload.get("forecast_horizon", 1))
        forecast_increment = sum(int(payload.get(name, 0)) for name in ("next_turn_tokens", "pending_tool_tokens", "pending_test_log_tokens"))
        forecast_tokens = int(payload["used_tokens"]) + forecast_increment
        pressure_policy = ctx.policy.get("context_pressure", {})
        elevated = float(pressure_policy.get("elevated", 0.65)) if isinstance(pressure_policy, Mapping) else 0.65
        high = float(pressure_policy.get("high", 0.80)) if isinstance(pressure_policy, Mapping) else 0.80
        critical = float(pressure_policy.get("critical", 0.92)) if isinstance(pressure_policy, Mapping) else 0.92
        forecast_ratio = forecast_tokens / int(payload["effective_input_budget"])
        forecast_state = "CRITICAL" if forecast_ratio >= critical else "HIGH" if forecast_ratio >= high else "ELEVATED" if forecast_ratio >= elevated else "NORMAL"
        forecast_action = {"NORMAL": "NONE", "ELEVATED": "PREFETCH_COMPACTION", "HIGH": "COMPACT_AND_DEFER", "CRITICAL": "BLOCK_AND_CHECKPOINT"}[forecast_state]
        snapshot = {
            **outputs,
            "forecast_tokens": forecast_tokens,
            "forecast_horizon": forecast_horizon,
            "forecast_increment_tokens": forecast_increment,
            "forecast_ratio": round(forecast_ratio, 8),
            "forecast_pressure_state": forecast_state,
            "forecast_action": forecast_action,
        }
        digest = _raw_digest(snapshot)
        with self.store.transaction() as connection:
            existing = connection.execute(
                """SELECT pressure_id,snapshot_digest,snapshot_json FROM context_pressure_snapshots
                     WHERE tenant_id=? AND project_id=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, key),
            ).fetchone()
            if existing is not None:
                if existing["snapshot_digest"] != digest:
                    raise ConflictError("CONTEXT_PRESSURE_IDEMPOTENCY_CONFLICT")
                pressure_id, replay = str(existing["pressure_id"]), True
                snapshot = json.loads(str(existing["snapshot_json"]))
            else:
                pressure_id, replay = new_id("ctx-pressure"), False
                connection.execute(
                    """INSERT INTO context_pressure_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ctx.tenant_id, ctx.project_id, pressure_id, task_id, ctx.request_id, key,
                        str(previous["pressure_id"]) if previous else None, effective["previous_state"],
                        outputs["pressure_state"], int(payload["used_tokens"]), int(payload["effective_input_budget"]),
                        forecast_tokens, forecast_horizon, outputs["action"], outputs["policy_version"],
                        canonical_json(snapshot), digest, utc_now(),
                    ),
                )
                self.store._event(
                    connection, self._tenant(ctx), "context_pressure", pressure_id,
                    "context.pressure.action", f"context-pressure:{key}",
                    {"pressure_id": pressure_id, "state": outputs["pressure_state"], "action": outputs["action"], "snapshot_digest": digest},
                )
        result["outputs"].update(snapshot)
        result["outputs"].update({"pressure_id": pressure_id, "idempotent_replay": replay})
        return _envelope(result)

    @staticmethod
    def _facts_from_state(state: Mapping[str, Any]) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        for name in ("goal", "latest_user_request", "constraints", "acceptance_criteria", "todos"):
            facts.append({"fact_id": f"checkpoint.{name}", "type": name, "value": state.get(name), "negated": False, "permission": None, "version": 1, "source_digest": _raw_digest(state.get(name))})
        for index, item in enumerate(state.get("facts", [])):
            if isinstance(item, Mapping):
                facts.append({"fact_id": str(item.get("fact_id", f"fact.{index}")), "type": str(item.get("type", "fact")), "value": item.get("value"), "negated": bool(item.get("negated", False)), "permission": item.get("permission"), "version": item.get("version", 1), "source_digest": item.get("source_digest") or _raw_digest(item)})
        return facts

    def _persist_integrity(
        self, ctx: "RuntimeContext", payload: Mapping[str, Any], result: Mapping[str, Any], *, key_suffix: str = ""
    ) -> str:
        report = dict(result.get("outputs", {}))
        digest = str(report.get("report_digest", "")).removeprefix("sha256:")
        if len(digest) != 64:
            raise IntegrityError("CONTEXT_INTEGRITY_REPORT_DIGEST_INVALID")
        key = self._idempotency(ctx, payload) + key_suffix
        with self.store.transaction() as connection:
            existing = connection.execute(
                """SELECT report_id,report_digest FROM context_integrity_reports
                     WHERE tenant_id=? AND project_id=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, key),
            ).fetchone()
            if existing is not None:
                if existing["report_digest"] != digest:
                    raise ConflictError("CONTEXT_INTEGRITY_IDEMPOTENCY_CONFLICT")
                return str(existing["report_id"])
            report_id = new_id("ctx-integrity")
            passed = bool(report.get("passed"))
            connection.execute(
                """INSERT INTO context_integrity_reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ctx.tenant_id, ctx.project_id, report_id, self._task(ctx, payload), ctx.request_id, key, payload.get("checkpoint_id"), int(passed), int(passed), canonical_json(report), digest, utc_now()),
            )
            self.store._event(
                connection, self._tenant(ctx), "context_integrity", report_id,
                "context.integrity.passed" if passed else "context.integrity.failed",
                f"context-integrity:{key}",
                {"report_id": report_id, "passed": passed, "report_digest": digest, "side_effect_authorized": passed},
            )
        return report_id

    def _integrity(self, ctx: "RuntimeContext", payload: Mapping[str, Any]) -> dict[str, Any]:
        result = self._call("elmos-context-integrity-and-loss-detection", ctx, payload)
        report_id = self._persist_integrity(ctx, payload, result)
        result["outputs"]["report_id"] = report_id
        result["outputs"]["side_effect_authorized"] = bool(result["outputs"].get("passed"))
        return _envelope(result)

    def _compact(self, ctx: "RuntimeContext", payload: Mapping[str, Any]) -> dict[str, Any]:
        state = payload.get("state")
        if not isinstance(state, Mapping):
            raise ValidationError("CONTEXT_COMPACTION_STATE_REQUIRED")
        raw_history = payload.get("raw_history", state)
        raw = canonical_json(raw_history).encode("utf-8")
        raw_digest = self.cas.put_bytes(ctx.tenant_id, raw)
        effective = dict(payload)
        effective["source_history_digest"] = "sha256:" + _raw_digest(state)
        result = self._call("elmos-structured-context-compaction", ctx, effective)
        if result.get("state") != "SUCCEEDED":
            return _envelope(result)
        checkpoint = dict(result["outputs"]["checkpoint"])
        compactor = ctx.capabilities.get("context_compactor")
        trusted_compactor = compactor if isinstance(compactor, Mapping) and compactor.get("verified") is True else {}
        checkpoint["compaction_metadata"] = {
            "algorithm": str(trusted_compactor.get("algorithm", "structured-dedupe-v1")),
            "model_id": trusted_compactor.get("model_id"),
            "model_version": trusted_compactor.get("model_version"),
            "template_version": str(trusted_compactor.get("template_version", "structured-checkpoint-v1")),
            "input_history_digest": raw_digest,
            "output_checkpoint_digest": checkpoint["checkpoint_digest"],
            "input_tokens": payload.get("input_tokens") if isinstance(payload.get("input_tokens"), int) else None,
            "output_tokens": payload.get("output_tokens") if isinstance(payload.get("output_tokens"), int) else None,
            "token_savings": (
                int(payload["input_tokens"]) - int(payload["output_tokens"])
                if isinstance(payload.get("input_tokens"), int) and isinstance(payload.get("output_tokens"), int)
                else None
            ),
            "token_accounting_state": "PROVIDED_UNVERIFIED" if "input_tokens" in payload or "output_tokens" in payload else "NOT_MEASURED",
        }
        # Rebind the structured document after adding durable composition metadata.
        checkpoint.pop("checkpoint_digest", None)
        checkpoint["checkpoint_digest"] = "sha256:" + _raw_digest(checkpoint)
        before = self._facts_from_state(state)
        after = self._facts_from_state(checkpoint)
        integrity_payload = {**payload, "before": before, "after": after}
        integrity = self._call("elmos-context-integrity-and-loss-detection", ctx, integrity_payload)
        report_id = self._persist_integrity(ctx, integrity_payload, integrity, key_suffix=":compaction")
        if integrity.get("state") != "SUCCEEDED":
            return _envelope({"state": "BLOCKED", "code": "CONTEXT_COMPACTION_INTEGRITY_FAILED", "outputs": {"raw_history_digest": raw_digest, "integrity_report_id": report_id, "original_unchanged": True}})
        key = self._idempotency(ctx, payload)
        task_id = self._task(ctx, payload)
        package_version = _required_text(payload.get("package_version", "context-v1"), "package_version")
        checkpoint_id = new_id("ctx-checkpoint")
        checkpoint_digest = str(checkpoint["checkpoint_digest"]).removeprefix("sha256:")
        effect_cursor = _raw_digest(payload.get("side_effect_cursor", []))
        cost_cursor = _raw_digest(payload.get("cost_cursor", {}))
        rollback_id = payload.get("rollback_checkpoint_id")
        with self.store.transaction() as connection:
            existing = connection.execute(
                """SELECT * FROM context_checkpoints WHERE tenant_id=? AND project_id=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, key),
            ).fetchone()
            if existing is not None:
                if existing["checkpoint_digest"] != checkpoint_digest or existing["raw_history_digest"] != raw_digest:
                    raise ConflictError("CONTEXT_CHECKPOINT_IDEMPOTENCY_CONFLICT")
                checkpoint_id, replay = str(existing["checkpoint_id"]), True
            else:
                connection.execute(
                    """INSERT INTO context_checkpoints VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (ctx.tenant_id, ctx.project_id, checkpoint_id, task_id, ctx.request_id, key, package_version, payload.get("model_snapshot_id"), raw_digest, len(raw), canonical_json(checkpoint), checkpoint_digest, report_id, rollback_id, effect_cursor, cost_cursor, utc_now()),
                )
                self.store._event(
                    connection, self._tenant(ctx), "context_checkpoint", checkpoint_id,
                    "context.checkpoint.created", f"context-checkpoint:{key}",
                    {"checkpoint_id": checkpoint_id, "checkpoint_digest": checkpoint_digest, "raw_history_digest": raw_digest, "integrity_report_id": report_id},
                )
                replay = False
        result["outputs"]["checkpoint"] = checkpoint
        result["outputs"].update({"checkpoint_id": checkpoint_id, "raw_history_digest": raw_digest, "raw_history_bytes": len(raw), "integrity_report_id": report_id, "rollback_checkpoint_id": rollback_id, "idempotent_replay": replay})
        return _envelope(result)

    def _checkpoint(self, ctx: "RuntimeContext", payload: Mapping[str, Any], operation: str) -> dict[str, Any]:
        if operation in {"list", "history"}:
            with self.store.read_transaction() as connection:
                rows = connection.execute(
                    """SELECT checkpoint_id,task_id,package_version,checkpoint_digest,raw_history_digest,
                              integrity_report_id,rollback_checkpoint_id,created_at
                         FROM context_checkpoints WHERE tenant_id=? AND project_id=?
                         ORDER BY created_at DESC,checkpoint_id DESC""",
                    (ctx.tenant_id, ctx.project_id),
                ).fetchall()
            return _envelope({"state": "SUCCEEDED", "code": "CONTEXT_CHECKPOINTS_LISTED", "outputs": {"checkpoints": [dict(row) for row in rows]}})
        if operation == "diff":
            left = self._load_checkpoint(ctx, _required_text(payload.get("left_checkpoint_id"), "left_checkpoint_id"))
            right = self._load_checkpoint(ctx, _required_text(payload.get("right_checkpoint_id"), "right_checkpoint_id"))
            left_payload, right_payload = json.loads(str(left["checkpoint_json"])), json.loads(str(right["checkpoint_json"]))
            keys = sorted(set(left_payload) | set(right_payload))
            changes = [{"field": key, "before": left_payload.get(key), "after": right_payload.get(key)} for key in keys if left_payload.get(key) != right_payload.get(key)]
            return _envelope({"state": "SUCCEEDED", "code": "CONTEXT_CHECKPOINTS_DIFFED", "outputs": {"changes": changes, "diff_digest": _raw_digest(changes)}})
        if operation == "create":
            # The structured compaction path is the authoritative creator.
            state = payload.get("state") or payload.get("payload")
            if not isinstance(state, Mapping):
                raise ValidationError("CONTEXT_CHECKPOINT_STATE_REQUIRED")
            return self._compact(ctx, {**payload, "state": state})
        if operation not in {"restore", "rollback"}:
            # Existing public execute/run operations keep create semantics.
            state = payload.get("state") or payload.get("payload")
            if isinstance(state, Mapping):
                return self._compact(ctx, {**payload, "state": state})
            raise ValidationError("CONTEXT_CHECKPOINT_OPERATION_UNSUPPORTED")
        checkpoint_id = _required_text(payload.get("checkpoint_id"), "checkpoint_id")
        row = self._load_checkpoint(ctx, checkpoint_id)
        restore_binding = ctx.capabilities.get("checkpoint_restore_binding")
        required_binding = {
            "authorized": True,
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "checkpoint_id": checkpoint_id,
            "restore_request_id": ctx.request_id,
            "operation": operation,
        }
        if not isinstance(restore_binding, Mapping) or any(
            restore_binding.get(field) != value for field, value in required_binding.items()
        ):
            return _envelope({"state": "BLOCKED", "code": "CHECKPOINT_RESTORE_AUTHORIZATION_REQUIRED", "outputs": {"restored": False}})
        report = self._load_integrity(ctx, str(row["integrity_report_id"]))
        if not bool(report["passed"]) or not bool(report["side_effect_authorized"]):
            return _envelope({"state": "BLOCKED", "code": "CONTEXT_RESTORE_INTEGRITY_REQUIRED", "outputs": {"restored": False, "integrity_report_id": row["integrity_report_id"]}})
        key = self._idempotency(ctx, payload)
        result_body = {
            "restored": True,
            "checkpoint_id": checkpoint_id,
            "checkpoint": json.loads(str(row["checkpoint_json"])),
            "raw_history_digest": str(row["raw_history_digest"]),
            "effects_to_skip_cursor_digest": str(row["side_effect_cursor_digest"]),
            "cost_to_skip_cursor_digest": str(row["cost_cursor_digest"]),
            "rollback": operation == "rollback",
        }
        digest = _raw_digest(result_body)
        with self.store.transaction() as connection:
            existing = connection.execute(
                """SELECT * FROM context_recovery_attempts
                     WHERE tenant_id=? AND project_id=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, key),
            ).fetchone()
            if existing is not None:
                if existing["result_digest"] != digest:
                    raise ConflictError("CONTEXT_RECOVERY_IDEMPOTENCY_CONFLICT")
                attempt_id, replay = str(existing["attempt_id"]), True
                result_body = json.loads(str(existing["result_json"]))
            else:
                attempt_id, replay = new_id("ctx-recovery"), False
                connection.execute(
                    """INSERT INTO context_recovery_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (ctx.tenant_id, ctx.project_id, attempt_id, checkpoint_id, ctx.request_id, key, "RESTORED", row["side_effect_cursor_digest"], row["cost_cursor_digest"], canonical_json(result_body), digest, utc_now()),
                )
                self.store._event(
                    connection, self._tenant(ctx), "context_recovery", attempt_id,
                    "context.checkpoint.rolled_back" if operation == "rollback" else "context.checkpoint.restored",
                    f"context-recovery:{key}",
                    {"attempt_id": attempt_id, "checkpoint_id": checkpoint_id, "result_digest": digest, "duplicate_effects": False, "duplicate_cost": False},
                )
        result_body.update({"attempt_id": attempt_id, "idempotent_replay": replay, "duplicate_effects": False, "duplicate_cost": False})
        return _envelope({"state": "SUCCEEDED", "code": "CONTEXT_CHECKPOINT_ROLLED_BACK" if operation == "rollback" else "CONTEXT_CHECKPOINT_RESTORED", "outputs": result_body})

    def _load_checkpoint(self, ctx: "RuntimeContext", checkpoint_id: str) -> Any:
        with self.store.read_transaction() as connection:
            row = connection.execute(
                """SELECT * FROM context_checkpoints
                     WHERE tenant_id=? AND project_id=? AND checkpoint_id=?""",
                (ctx.tenant_id, ctx.project_id, checkpoint_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("CONTEXT_CHECKPOINT_NOT_FOUND")
        return row

    def _load_integrity(self, ctx: "RuntimeContext", report_id: str) -> Any:
        with self.store.read_transaction() as connection:
            row = connection.execute(
                """SELECT * FROM context_integrity_reports
                     WHERE tenant_id=? AND project_id=? AND report_id=?""",
                (ctx.tenant_id, ctx.project_id, report_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("CONTEXT_INTEGRITY_REPORT_NOT_FOUND")
        return row

    def _rehydrate(self, ctx: "RuntimeContext", payload: Mapping[str, Any]) -> dict[str, Any]:
        catalog = ctx.capabilities.get("rehydration_catalog")
        if not isinstance(catalog, Mapping):
            return _envelope({"state": "BLOCKED", "code": "REHYDRATION_CATALOG_UNAVAILABLE", "outputs": {"loaded": []}})
        sources = catalog.get("sources", [])
        if not isinstance(sources, list):
            raise ValidationError("REHYDRATION_CATALOG_INVALID")
        package_version = payload.get("package_version")
        descriptor_binding = {
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "package_version": package_version,
            "sources": sources,
            "max_tokens": catalog.get("max_tokens"),
        }
        claimed_catalog_digest = str(catalog.get("catalog_digest", "")).removeprefix("sha256:")
        if (
            catalog.get("verified") is not True
            or catalog.get("tenant_id") != ctx.tenant_id
            or catalog.get("project_id") != ctx.project_id
            or catalog.get("package_version") != package_version
            or claimed_catalog_digest != _raw_digest(descriptor_binding)
        ):
            return _envelope({"state": "BLOCKED", "code": "REHYDRATION_CATALOG_DIGEST_MISMATCH", "outputs": {"loaded": []}})
        materialized: list[dict[str, Any]] = []
        for source in sources:
            if not isinstance(source, Mapping):
                raise ValidationError("REHYDRATION_CATALOG_INVALID")
            digest = _required_text(source.get("content_digest"), "content_digest")
            raw_digest = digest.removeprefix("sha256:")
            expected_bytes = int(source.get("byte_count", -1))
            if expected_bytes < 0:
                raise ValidationError("REHYDRATION_SOURCE_BYTE_COUNT_REQUIRED")
            if source.get("tenant_id", ctx.tenant_id) != ctx.tenant_id or source.get("project_id", ctx.project_id) != ctx.project_id:
                raise IntegrityError("REHYDRATION_SOURCE_SCOPE_MISMATCH")
            if source.get("package_version", package_version) != package_version:
                raise IntegrityError("REHYDRATION_SOURCE_VERSION_MISMATCH")
            if not isinstance(source.get("anchor"), Mapping) or not source.get("anchor"):
                raise IntegrityError("REHYDRATION_SOURCE_ANCHOR_MISSING")
            data = self.cas.read_bytes(ctx.tenant_id, raw_digest, maximum_bytes=8 * 1024 * 1024, expected_size=expected_bytes)
            try:
                content = data.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise IntegrityError("REHYDRATION_SOURCE_ENCODING_INVALID") from exc
            if sha256_bytes(data) != raw_digest:
                raise IntegrityError("REHYDRATION_HASH_MISMATCH")
            materialized.append({**dict(source), "content": content, "content_digest": "sha256:" + raw_digest})
        binding = {
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "package_version": catalog.get("package_version"),
            "sources": materialized,
            "max_tokens": catalog.get("max_tokens"),
        }
        internal_catalog = {**binding, "verified": catalog.get("verified") is True, "catalog_digest": "sha256:" + _raw_digest(binding)}
        request = self._request(ctx, payload)
        request["capabilities"] = {**dict(ctx.capabilities), "rehydration_catalog": internal_catalog}
        result = rehydrate_context(request)
        if result.get("state") in {"FAILED", "BLOCKED"}:
            return _envelope(result)
        body = {"sources": [{key: value for key, value in item.items() if key != "content"} for item in result["outputs"]["loaded"]], "load_digest": result["outputs"]["load_digest"]}
        key = self._idempotency(ctx, payload)
        digest = _raw_digest(body)
        with self.store.transaction() as connection:
            existing = connection.execute(
                """SELECT record_id,payload_digest FROM context_lifecycle_records
                     WHERE tenant_id=? AND project_id=? AND kind='REHYDRATION' AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, key),
            ).fetchone()
            if existing is not None:
                if existing["payload_digest"] != digest:
                    raise ConflictError("REHYDRATION_IDEMPOTENCY_CONFLICT")
                record_id, replay = str(existing["record_id"]), True
            else:
                record_id, replay = new_id("ctx-record"), False
                connection.execute(
                    """INSERT INTO context_lifecycle_records VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (ctx.tenant_id, ctx.project_id, record_id, self._task(ctx, payload), "REHYDRATION", ctx.request_id, key, None, canonical_json(body), digest, utc_now()),
                )
                self.store._event(
                    connection, self._tenant(ctx), "context_lifecycle", record_id,
                    "context.rehydration.recorded", f"context-rehydration:{key}",
                    {"record_id": record_id, "payload_digest": digest},
                )
        result["outputs"].update({"durable_record_id": record_id, "idempotent_replay": replay, "source_storage": "TENANT_CAS"})
        return _envelope(result)

    def side_effect_authorized(
        self, ctx: "RuntimeContext", *, task_id: str, report_id: str | None = None
    ) -> bool:
        """Fail-closed authorization query used before high-risk side effects."""
        with self.store.read_transaction() as connection:
            if report_id is None:
                row = connection.execute(
                    """SELECT passed,side_effect_authorized FROM context_integrity_reports
                         WHERE tenant_id=? AND project_id=? AND task_id=?
                         ORDER BY created_at DESC,report_id DESC LIMIT 1""",
                    (ctx.tenant_id, ctx.project_id, task_id),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT passed,side_effect_authorized FROM context_integrity_reports
                         WHERE tenant_id=? AND project_id=? AND task_id=? AND report_id=?""",
                    (ctx.tenant_id, ctx.project_id, task_id, report_id),
                ).fetchone()
        return bool(row and row["passed"] and row["side_effect_authorized"])
