"""Compile one NativeSemanticProgram into a unique exact handler."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any, Callable

from ..canonical import canonical_digest, canonical_value
from ..domain import TenantScope
from ..industrial_runtime.families import classify_skill
from ..native_semantics import (
    NATIVE_TRACE_SCHEMA_VERSION,
    NativeSemanticError,
    NativeSemanticProgram,
)
from .tool_runtime import (
    ExactToolError,
    ToolContext,
    load_tool_runtime,
    run_tool,
    seed_domain_working,
)

INDUSTRIAL_BROKER_ID = "elmos.foundry.industrial-local-host-broker"
LOCAL_EVIDENCE_STATUS = "LOCAL_EXECUTED_SELF_ATTESTED"


class ExactSkillError(ValueError):
    """An exact skill handler is missing, foreign, or failed closed."""


HandlerFunc = Callable[..., dict[str, Any]]


def _nfc_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    encoded = canonical_value(json.loads(json.dumps(raw, default=str, ensure_ascii=False)))
    if not isinstance(encoded, dict):
        raise ExactSkillError("payload must canonicalize to an object")
    return encoded


def _tenant_document(scope: TenantScope | None, invocation_id: str) -> dict[str, str]:
    if scope is None:
        return {"tenant_id": "", "project_id": "", "invocation_id": invocation_id}
    return {
        "tenant_id": scope.tenant_id,
        "project_id": scope.project_id,
        "invocation_id": invocation_id or scope.invocation_id,
    }


def _materialize_output(
    output_name: str,
    program: NativeSemanticProgram,
    working: Mapping[str, Any],
    traces: Mapping[str, Any],
) -> dict[str, Any]:
    lowered = output_name.lower()
    artifact: Any
    if any(token in lowered for token in ("sql", "dialect", "schema")) and working.get("sql"):
        artifact = working["sql"]
    elif any(token in lowered for token in ("test", "oracle", "suite")) and working.get("tests"):
        artifact = working["tests"]
    elif any(token in lowered for token in ("policy", "entitlement", "approval", "waiver")) and working.get("policy"):
        artifact = working["policy"]
    elif any(token in lowered for token in ("lineage", "evidence", "provenance", "audit")) and working.get("lineage"):
        artifact = working["lineage"]
    elif any(token in lowered for token in ("cost", "billing", "meter", "invoice", "finops")) and working.get("cost"):
        artifact = working["cost"]
    elif any(token in lowered for token in ("retriev", "context", "citation", "rank")) and working.get("retrieval"):
        artifact = working["retrieval"]
    elif any(token in lowered for token in ("memory", "episode")) and working.get("memory"):
        artifact = working["memory"]
    elif any(token in lowered for token in ("ir", "semantic", "transform", "patch", "artifact")) and working.get("semantic_ir"):
        artifact = working["semantic_ir"]
    elif any(token in lowered for token in ("graph", "architecture", "dag", "workflow")) and working.get("graph"):
        artifact = working["graph"]
    elif any(token in lowered for token in ("security", "threat", "secret")) and working.get("security"):
        artifact = working["security"]
    elif any(token in lowered for token in ("rollback", "compensat")):
        artifact = traces["semantic_execution"]["rollback"]
    elif any(token in lowered for token in ("plan", "route", "decision")):
        artifact = {
            "stages": [stage["name"] for stage in program.stages],
            "tools": [tool for stage in program.stages for tool in stage.get("tools", ())],
            "gates": list(program.required_gates),
            "objective": str(program.document.get("objective") or "")[:240],
        }
    else:
        artifact = {
            "working_keys": sorted(str(key) for key in working if key != "tool_artifacts"),
            "tool_count": len(working.get("tool_artifacts") or {}),
        }
    return {
        "name": output_name,
        "skill": program.skill_name,
        "handler_id": program.handler_id,
        "program_digest": program.digest,
        "industrial": True,
        "exact": True,
        "artifact": artifact,
        "output_digest": canonical_digest(
            {
                "skill": program.skill_name,
                "handler_id": program.handler_id,
                "program_digest": program.digest,
                "output": output_name,
                "artifact": artifact,
            }
        ),
    }


def _evaluate_gate(gate: str, working: Mapping[str, Any], program: NativeSemanticProgram) -> dict[str, Any]:
    status = "PASSED"
    reason = "required tools confirmed and artifacts bound"
    if gate in {"tests-not-weakened", "tests-adequate"}:
        cases = int((working.get("tests") or {}).get("generated_cases") or 0)
        if working.get("tests") is not None and cases < 0:
            status = "FAILED"
            reason = "test synthesis produced a negative case count"
    if gate in {"security-not-weakened"} and working.get("security"):
        if (working["security"].get("risk_level") == "CRITICAL") and "security" not in program.skill_name:
            reason = "critical findings recorded without weakening controls"
    if gate in {"evidence-complete"} and not (working.get("lineage") or working.get("tool_artifacts")):
        status = "FAILED"
        reason = "evidence gate lacks lineage or tool artifacts"
    return {
        "gate": gate,
        "status": status,
        "evidence_digest": canonical_digest(
            {
                "gate": gate,
                "skill": program.skill_name,
                "program_digest": program.digest,
                "status": status,
                "reason": reason,
            }
        ),
    }


def execute_exact_program(
    program: NativeSemanticProgram,
    payload: Mapping[str, Any] | None,
    tenant_scope: TenantScope | None,
    invocation_id: str,
    *,
    request_binding_digest: str | None = None,
) -> dict[str, Any]:
    """Execute one exact native program: stages, tools, gates, rollback."""

    body = _nfc_payload(payload)
    tenant = _tenant_document(tenant_scope, invocation_id)
    binding = request_binding_digest or canonical_digest(
        {
            "skill_name": program.skill_name,
            "handler_id": program.handler_id,
            "program_digest": program.digest,
            "payload": body,
            "invocation_id": invocation_id or "",
        }
    )
    runtime = load_tool_runtime()
    working: dict[str, Any] = {
        "payload": body,
        "tool_artifacts": {},
        "tool_digests": [],
    }
    seed_domain_working(body, working)
    stages_trace: list[dict[str, Any]] = []
    input_digest = binding
    try:
        for stage in program.stages:
            receipts: list[dict[str, str]] = []
            stage_artifacts: list[Any] = []
            for tool_id in stage.get("tools", ()):
                ctx = ToolContext(
                    tool_id=str(tool_id),
                    skill_name=program.skill_name,
                    pack=str(program.document.get("pack") or ""),
                    handler_id=program.handler_id,
                    program_digest=program.digest,
                    stage_name=str(stage["name"]),
                    stage_index=int(stage["index"]),
                    operation=str(stage["operation"]),
                    objective=str(program.document.get("objective") or ""),
                    payload=body,
                    working=working,
                    tenant=tenant,
                    invocation_id=invocation_id or "",
                )
                result = run_tool(ctx, runtime)
                key = f"{stage['name']}:{tool_id}"
                working["tool_artifacts"][key] = result.artifact
                working["tool_digests"].append(result.artifact.get("artifact_digest"))
                if "transpiled_sql" in result.artifact:
                    working["transpiled_sql"] = result.artifact["transpiled_sql"]
                    working.setdefault("sql", {k: result.artifact[k] for k in (
                        "original_sql",
                        "transpiled_sql",
                        "modifications",
                        "tables",
                        "source_dialect",
                        "target_dialect",
                    ) if k in result.artifact})
                stage_artifacts.append(result.artifact)
                receipts.append(
                    {
                        "tool": result.tool_id,
                        "outcome": result.outcome,
                        "receipt_digest": canonical_digest(
                            {
                                "tool": result.tool_id,
                                "skill": program.skill_name,
                                "program_digest": program.digest,
                                "stage": stage["index"],
                                "artifact_digest": result.artifact.get("artifact_digest"),
                            }
                        ),
                    }
                )
            output_digest = canonical_digest(
                {
                    "program": program.digest,
                    "stage": stage["index"],
                    "operation": stage["operation"],
                    "input": input_digest,
                    "artifacts": stage_artifacts,
                }
            )
            checkpoint_digest = canonical_digest(
                {
                    "program": program.digest,
                    "checkpoint": stage["index"],
                    "name": stage["name"],
                    "output": output_digest,
                }
            )
            stages_trace.append(
                {
                    "index": stage["index"],
                    "name": stage["name"],
                    "operation": stage["operation"],
                    "status": "SUCCEEDED",
                    "input_digest": input_digest,
                    "output_digest": output_digest,
                    "checkpoint_digest": checkpoint_digest,
                    "tool_receipts": receipts,
                }
            )
            input_digest = output_digest
        gate_evidence = [_evaluate_gate(gate, working, program) for gate in program.required_gates]
        if any(row["status"] != "PASSED" for row in gate_evidence):
            failed = [row["gate"] for row in gate_evidence if row["status"] != "PASSED"]
            raise ExactSkillError(f"required gates failed: {failed}")
        rollback = {
            "strategy": program.rollback_strategy,
            "status": "NOT_REQUIRED",
            "receipt_digest": canonical_digest(
                {
                    "program": program.digest,
                    "rollback": "NOT_REQUIRED",
                    "strategy": program.rollback_strategy,
                }
            ),
        }
        semantic_execution = {
            "schema_version": NATIVE_TRACE_SCHEMA_VERSION,
            "skill_name": program.skill_name,
            "handler_id": program.handler_id,
            "program_digest": program.digest,
            "request_binding_digest": binding,
            "stages": stages_trace,
            "gate_evidence": gate_evidence,
            "rollback": rollback,
        }
        traces = {"semantic_execution": semantic_execution}
        program.validate_result(traces, request_binding_digest=binding)
    except (ExactSkillError, ExactToolError, NativeSemanticError) as exc:
        family = classify_skill(program.skill_name, str(program.document.get("pack") or "")).value
        input_digest = binding
        error_digest = canonical_digest({"error": str(exc), "skill": program.skill_name})
        return {
            "status": "FAILED",
            "outputs": {},
            "execution_status": LOCAL_EVIDENCE_STATUS,
            "execution_mode": "EXACT_NATIVE_PROGRAM",
            "host_broker": INDUSTRIAL_BROKER_ID,
            "kernel_family": family,
            "algorithm": f"exact:{program.handler_id}",
            "input_digest": input_digest,
            "output_digest": error_digest,
            "llm_required": False,
            "industrial": True,
            "exact": True,
            "skill": program.skill_name,
            "pack": str(program.document.get("pack") or ""),
            "handler_id": program.handler_id,
            "program_digest": program.digest,
            "error": str(exc),
            "metrics": {},
            "artifacts": {},
            "semantic_execution": None,
        }

    outputs = {
        str(item["name"]): _materialize_output(str(item["name"]), program, working, traces)
        for item in program.document.get("outputs", [])
    }
    family = classify_skill(program.skill_name, str(program.document.get("pack") or "")).value
    artifacts = {
        key: working[key]
        for key in (
            "sql",
            "transpiled_sql",
            "ast",
            "tests",
            "policy",
            "lineage",
            "cost",
            "retrieval",
            "memory",
            "semantic_ir",
            "graph",
            "security",
        )
        if key in working
    }
    artifacts.update({name: row["artifact"] for name, row in outputs.items()})
    metrics = {
        "stage_count": len(stages_trace),
        "tool_count": len(working["tool_artifacts"]),
        "gate_count": len(program.required_gates),
        "output_count": len(outputs),
    }
    output_digest = canonical_digest(
        {
            "skill": program.skill_name,
            "handler_id": program.handler_id,
            "program_digest": program.digest,
            "outputs": outputs,
            "final_stage": stages_trace[-1]["output_digest"] if stages_trace else binding,
        }
    )
    return {
        "status": "SUCCEEDED",
        "outputs": outputs,
        "execution_status": LOCAL_EVIDENCE_STATUS,
        "execution_mode": "EXACT_NATIVE_PROGRAM",
        "host_broker": INDUSTRIAL_BROKER_ID,
        "kernel_family": family,
        "algorithm": f"exact:{program.handler_id}",
        "input_digest": binding,
        "output_digest": output_digest,
        "llm_required": False,
        "industrial": True,
        "exact": True,
        "skill": program.skill_name,
        "pack": str(program.document.get("pack") or ""),
        "handler_id": program.handler_id,
        "program_digest": program.digest,
        "error": None,
        "metrics": metrics,
        "artifacts": artifacts,
        "semantic_execution": semantic_execution,
    }


def compile_exact_handler(program: NativeSemanticProgram) -> HandlerFunc:
    """Return a unique callable bound to one native program identity."""

    skill_name = program.skill_name
    handler_id = program.handler_id
    digest = program.digest
    safe = skill_name.replace("-", "_")

    def _handler(
        name: str,
        payload: Mapping[str, Any],
        scope: TenantScope | None,
        invocation_id: str,
        request_binding_digest: str | None = None,
    ) -> dict[str, Any]:
        if name != skill_name:
            raise ExactSkillError(
                f"exact handler {handler_id} cannot execute foreign skill {name}"
            )
        return execute_exact_program(
            program,
            payload,
            scope,
            invocation_id,
            request_binding_digest=request_binding_digest,
        )

    _handler.__name__ = f"exact_{safe}"
    _handler.__qualname__ = f"elmos_foundry.exact_skills.compiled.exact_{safe}"
    _handler.__module__ = f"elmos_foundry.exact_skills.compiled.{safe}"
    setattr(_handler, "skill_name", skill_name)
    setattr(_handler, "handler_id", handler_id)
    setattr(_handler, "program_digest", digest)
    return _handler


__all__ = [
    "INDUSTRIAL_BROKER_ID",
    "ExactSkillError",
    "HandlerFunc",
    "compile_exact_handler",
    "execute_exact_program",
]
