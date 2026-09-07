#!/usr/bin/env python3
"""Exact, digest-bound local implementations for Precision Migration Skills.

Every active generic Skill is bound to a generated, unique Python entrypoint and
an immutable implementation profile.  Shared primitives are intentionally kept
in one reviewed module, but selection happens from the allowlisted profile --
never from request or repository content and never from name heuristics at run
time.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from scripts.precision_migration.contracts import ContractRegistry
from scripts.precision_migration.domain import (
    DomainExecutionError,
    _assets,
    _compare,
    _decision,
    _govern,
    _inspect,
    _model,
    _observe,
    _plan,
    _transform,
    _validate,
    _write,
)
from scripts.precision_migration.runtime import canonical_digest
from scripts.precision_migration.native import execute_native_tools, native_tool_readiness


ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATIONS_PATH = (
    ROOT / "docs" / "precision-migration-b01-44" / "handler-implementations.json"
)
EXPECTED_EXACT_HANDLERS = 536
PROGRAM_OPERATIONS = (
    "verify-inputs",
    "execute-algorithm",
    "execute-native",
    "evaluate-gates",
    "emit-artifact",
)


def _canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class ExactImplementationRegistry:
    """Validate and resolve immutable per-Skill implementation profiles."""

    def __init__(self, payload: dict[str, Any]) -> None:
        if (
            payload.get("schema_version") != 1
            or payload.get("namespace") != "precision-migration-b01-44"
        ):
            raise DomainExecutionError("exact implementation registry identity is invalid")
        implementations = payload.get("implementations")
        if not isinstance(implementations, list) or len(implementations) != EXPECTED_EXACT_HANDLERS:
            raise DomainExecutionError(
                f"exact implementation registry must contain {EXPECTED_EXACT_HANDLERS} handlers"
            )
        self.payload = payload
        self.by_handler: dict[str, dict[str, Any]] = {}
        self.by_skill: dict[str, dict[str, Any]] = {}
        entrypoints: set[str] = set()
        for implementation in implementations:
            if not isinstance(implementation, dict):
                raise DomainExecutionError("exact implementation must be an object")
            checked = dict(implementation)
            observed = checked.pop("implementation_digest", None)
            if observed != _canonical_digest(checked):
                raise DomainExecutionError(
                    f"exact implementation digest mismatch: {implementation.get('skill')}"
                )
            handler_id = implementation.get("handler_id")
            skill = implementation.get("skill")
            entrypoint = implementation.get("handler_entrypoint")
            if not all(isinstance(value, str) and value for value in (handler_id, skill, entrypoint)):
                raise DomainExecutionError("exact implementation identity is invalid")
            if (
                handler_id in self.by_handler
                or skill in self.by_skill
                or entrypoint in entrypoints
            ):
                raise DomainExecutionError("exact implementation identities must be unique")
            if implementation.get("executor") != f"batch-{int(implementation['batch']):02d}":
                raise DomainExecutionError(f"exact executor mismatch: {skill}")
            if implementation.get("schema_version") != 2:
                raise DomainExecutionError(f"exact implementation schema is unsupported: {skill}")
            program = implementation.get("program")
            if (
                not isinstance(program, list)
                or tuple(step.get("op") for step in program if isinstance(step, dict)) != PROGRAM_OPERATIONS
                or len(program) != len(PROGRAM_OPERATIONS)
            ):
                raise DomainExecutionError(f"exact implementation program is invalid: {skill}")
            algorithm = implementation.get("algorithm")
            if algorithm not in ALGORITHM_EXECUTORS:
                raise DomainExecutionError(f"exact implementation algorithm is not allowlisted: {skill}")
            if program[1].get("algorithm") != algorithm:
                raise DomainExecutionError(f"exact implementation program algorithm diverged: {skill}")
            if program[2].get("tools") != implementation.get("native_tools"):
                raise DomainExecutionError(f"exact implementation native plan diverged: {skill}")
            if program[4].get("artifact_name") != implementation.get("artifact_name"):
                raise DomainExecutionError(f"exact implementation artifact plan diverged: {skill}")
            self.by_handler[handler_id] = implementation
            self.by_skill[skill] = implementation
            entrypoints.add(entrypoint)

    @classmethod
    def load(cls, path: Path = IMPLEMENTATIONS_PATH) -> "ExactImplementationRegistry":
        return cls(json.loads(path.read_text(encoding="utf-8")))


_IMPLEMENTATIONS: ExactImplementationRegistry | None = None
_CONTRACTS: ContractRegistry | None = None


def implementations() -> ExactImplementationRegistry:
    global _IMPLEMENTATIONS
    if _IMPLEMENTATIONS is None:
        _IMPLEMENTATIONS = ExactImplementationRegistry.load()
    return _IMPLEMENTATIONS


def contracts() -> ContractRegistry:
    global _CONTRACTS
    if _CONTRACTS is None:
        _CONTRACTS = ContractRegistry.load()
    return _CONTRACTS


def _native_readiness(profile: dict[str, Any]) -> dict[str, Any]:
    tools = profile.get("native_tools", [])
    if not isinstance(tools, list):
        raise DomainExecutionError("native_tools must be a list")
    resolved = [native_tool_readiness(tool) for tool in tools if isinstance(tool, str) and tool]
    return {
        "required_tools": resolved,
        "availability": (
            "NOT_APPLICABLE"
            if not resolved
            else "AVAILABLE"
            if all(item["available"] for item in resolved)
            else "NOT_AVAILABLE"
        ),
        "execution": "NOT_RUN",
    }


def _estimate(payloads: list[Any], contract: dict[str, Any]) -> dict[str, Any]:
    decision = _decision(payloads, contract)
    ranking = decision["ranking"]
    best = float(ranking[0]["score"])
    spread = max(0.05, (1.0 - float(decision["confidence"])) / 2.0)
    return {
        "operation": "estimate",
        "point": round(best, 8),
        "lower": round(max(0.0, best - spread), 8),
        "upper": round(min(1.0, best + spread), 8),
        "confidence": decision["confidence"],
        "ranking": ranking,
    }


def _compiler_adapter(payloads: list[Any], contract: dict[str, Any]) -> dict[str, Any]:
    inspected = _inspect(payloads, contract)
    source = payloads[0].get("source_text", "") if isinstance(payloads[0], dict) else ""
    return {
        "operation": "compiler-adapter",
        "source_inventory": inspected,
        "syntax_markers": {
            "braces": source.count("{") + source.count("}"),
            "parentheses": source.count("(") + source.count(")"),
            "terminators": source.count(";"),
        },
    }


def _sql_semantics(payloads: list[Any], contract: dict[str, Any]) -> dict[str, Any]:
    inspected = _inspect(payloads, contract)
    source = payloads[0].get("source_text", "") if isinstance(payloads[0], dict) else ""
    upper = source.upper()
    keywords = [
        word
        for word in (
            "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP",
            "MERGE", "BEGIN", "COMMIT", "ROLLBACK", "TRIGGER", "PROCEDURE",
        )
        if word in upper
    ]
    return {
        "operation": "sql-semantics",
        "inventory": inspected,
        "statement_keywords": keywords,
        "transactional_tokens_present": any(
            token in keywords for token in ("BEGIN", "COMMIT", "ROLLBACK")
        ),
    }


def _proof_analysis(payloads: list[Any], contract: dict[str, Any]) -> dict[str, Any]:
    validation = _validate(payloads, contract)
    source = payloads[0].get("source_text", "") if isinstance(payloads[0], dict) else ""
    unsafe_tokens = [token for token in ("sorry", "axiom", "admit", "unknown") if token in source.lower()]
    return {
        "operation": "proof-analysis",
        "validation": validation,
        "unsafe_tokens": unsafe_tokens,
        "proof_state": "BLOCKED" if unsafe_tokens or validation["decision"] != "PASS" else "BOUNDED_CHECK_PASSED",
        "formal_proof": "NOT_CLAIMED",
    }


def _test_generation(payloads: list[Any], contract: dict[str, Any]) -> dict[str, Any]:
    validation = _validate(payloads, contract)
    capability = contract["source_skill"]
    return {
        "operation": "test-generation",
        "validation": validation,
        "generated_case": {
            "case_id": f"generated-{capability}",
            "preconditions": contract["inputs"],
            "assertions": contract["validation_gates"],
            "expected_status": "PASS",
        },
    }


Algorithm = Callable[[list[Any], dict[str, Any]], dict[str, Any]]


ALGORITHM_EXECUTORS: dict[str, Algorithm] = {
    "decision": _decision,
    "estimate": _estimate,
    "inspect": _inspect,
    "govern": _govern,
    "model": _model,
    "plan": _plan,
    "transform": _transform,
    "compiler-adapter": _compiler_adapter,
    "sql-semantics": _sql_semantics,
    "test-generation": _test_generation,
    "compare": _compare,
    "validate": _validate,
    "proof-analysis": _proof_analysis,
}


def _contract_digest(fragment: dict[str, Any]) -> str:
    return _canonical_digest(fragment)


def _execute_program(
    profile: dict[str, Any],
    payloads: list[Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Execute the immutable per-Skill program without runtime Batch inference."""
    program = profile["program"]
    verify_step, execute_step, native_step, gate_step, emit_step = program
    expected_fragments = {
        "input_contract_digest": _contract_digest({"inputs": contract["inputs"]}),
        "execution_policy_digest": _contract_digest(contract["execution_policy"]),
        "workflow_digest": _contract_digest({"workflow": contract["workflow"]}),
        "gate_contract_digest": _contract_digest(
            {
                "validation_gates": contract["validation_gates"],
                "definition_of_done": contract["definition_of_done"],
            }
        ),
    }
    if any(verify_step.get(key) != expected_fragments[key] for key in ("input_contract_digest", "execution_policy_digest")):
        raise DomainExecutionError("exact Skill input or execution-policy program digest mismatch")
    if execute_step.get("workflow_digest") != expected_fragments["workflow_digest"]:
        raise DomainExecutionError("exact Skill workflow program digest mismatch")
    if gate_step.get("gate_contract_digest") != expected_fragments["gate_contract_digest"]:
        raise DomainExecutionError("exact Skill gate program digest mismatch")
    if gate_step.get("unresolved_differences") != "block" or gate_step.get("test_weakening") != "forbidden":
        raise DomainExecutionError("exact Skill gate policy is not fail-closed")
    if native_step.get("require_all_when_requested") is not True:
        raise DomainExecutionError("exact Skill native policy must require all declared tools")
    if emit_step.get("media_type") != "application/json" or emit_step.get("write_policy") != "write-once":
        raise DomainExecutionError("exact Skill artifact policy is invalid")
    algorithm = execute_step["algorithm"]
    executor = ALGORITHM_EXECUTORS.get(algorithm)
    if executor is None or algorithm != profile["algorithm"]:
        raise DomainExecutionError("exact Skill program selected an unavailable algorithm")
    result = executor(payloads, contract)
    return {
        "program_version": profile["program_version"],
        "algorithm": algorithm,
        "program_digest": _canonical_digest({"program": program}),
        "capability": contract["source_skill"],
        "domain_result": result,
        "workflow_trace": [
            {"step": index + 1, "instruction": step, "state": "EXECUTED_LOCAL"}
            for index, step in enumerate(contract["workflow"])
        ],
        "declared_outputs": contract["outputs"],
        "validation_gates": contract["validation_gates"],
    }


def _gate_result(
    profile: dict[str, Any],
    request: dict[str, Any],
    program_result: dict[str, Any],
    native_execution: dict[str, Any],
) -> dict[str, Any]:
    losses = request.get("semantic_losses", [])
    unresolved_losses = [
        item
        for item in losses
        if isinstance(item, dict)
        and item.get("classification") in {"UNSUPPORTED", "REQUIRES_ADAPTER", "APPROXIMATE", "UNVERIFIED"}
    ] if isinstance(losses, list) else [{"classification": "INVALID", "scope": "semantic_losses"}]
    domain = program_result["domain_result"]
    domain_failed = (
        domain.get("decision") == "FAIL"
        or domain.get("proof_state") == "BLOCKED"
        or bool(domain.get("failures"))
    )
    native_required = bool(profile["native_tools"])
    native_pending = native_required and native_execution["state"] == "NOT_RUN"
    native_failed = native_execution["requested"] and native_execution["state"] != "PASSED"
    blockers = []
    if unresolved_losses:
        blockers.append("UNRESOLVED_SEMANTIC_LOSS")
    if domain_failed:
        blockers.append("LOCAL_VALIDATION_FAILED")
    if native_pending:
        blockers.append("NATIVE_EXECUTION_NOT_RUN")
    if native_failed:
        blockers.append("NATIVE_EXECUTION_FAILED")
    if native_failed or domain_failed or unresolved_losses:
        status = "FAILED"
    elif native_pending:
        status = "REQUIRES_ADAPTER"
    else:
        status = "CONDITIONALLY_VERIFIED"
    return {
        "status": status,
        "local_program": "PASSED" if not domain_failed else "FAILED",
        "native_execution": native_execution["state"],
        "unresolved_semantic_losses": unresolved_losses,
        "blockers": blockers,
        "release_decision": "BLOCK",
        "independent_verification": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }


def execute_exact_skill(
    request: dict[str, Any],
    entry: dict[str, Any],
    output_dir: Path,
    *,
    evidence_roots: tuple[Path, ...],
    expected_skill: str,
    expected_handler_id: str,
    expected_implementation_digest: str,
    trust_store: Any = None,
    **_: Any,
) -> dict[str, Any]:
    """Execute one exact generated handler after all identity checks pass."""
    if entry.get("kind") != "skill":
        raise DomainExecutionError("exact Skill handler cannot execute an orchestrator")
    if entry.get("skill") != expected_skill or entry.get("handler_id") != expected_handler_id:
        raise DomainExecutionError("exact Skill handler identity mismatch")
    profile = implementations().by_handler.get(expected_handler_id)
    if profile is None:
        raise DomainExecutionError("exact Skill implementation is not allowlisted")
    if (
        profile.get("skill") != expected_skill
        or profile.get("source_skill") != entry.get("source_skill")
        or profile.get("implementation_digest") != expected_implementation_digest
        or profile.get("handler_entrypoint") != entry.get("handler_entrypoint")
    ):
        raise DomainExecutionError("exact Skill profile binding mismatch")
    contract = contracts().by_skill.get(expected_skill)
    if contract is None or contract.get("contract_digest") != profile.get("contract_digest"):
        raise DomainExecutionError("exact Skill contract digest mismatch")
    if request.get("mode") not in contract.get("supported_modes", []):
        raise DomainExecutionError("requested mode is not allowed by the exact Skill contract")
    payloads, observations = _assets(request, evidence_roots)
    batch = int(profile["batch"])
    result = _execute_program(profile, payloads, contract)
    native_execution = execute_native_tools(profile, request, evidence_roots, output_dir, trust_store)
    gate_result = _gate_result(profile, request, result, native_execution)
    body = {
        "schema_version": 1,
        "request_id": request["request_id"],
        "skill": expected_skill,
        "source_skill": profile["source_skill"],
        "batch": batch,
        "handler_id": expected_handler_id,
        "handler_entrypoint": profile["handler_entrypoint"],
        "implementation_digest": expected_implementation_digest,
        "contract_digest": contract["contract_digest"],
        "input_evidence": observations,
        "result": result,
        "gate_result": gate_result,
        "native_readiness": _native_readiness(profile),
        "native_execution": native_execution,
        "execution_scope": "EXACT_CONTRACT_LOCAL",
        "independent_verification": "NOT_RUN",
        "production_execution": "NOT_RUN",
        "limitations": [
            "The exact local contract implementation is not external verification.",
            "Native source/target execution remains NOT_RUN unless separately evidenced.",
        ],
    }
    body["result_digest"] = canonical_digest(body)
    artifact = _write(output_dir / profile["artifact_name"], body)
    failed_native = native_execution["requested"] and native_execution["state"] != "PASSED"
    failed_local = gate_result["local_program"] == "FAILED" or bool(gate_result["unresolved_semantic_losses"])
    return {
        "execution_state": "FAILED" if failed_native or failed_local else "LOCAL_EXECUTED",
        "artifacts": [artifact],
        "exit_code": 4 if failed_native or failed_local else 0,
    }


Handler = Callable[..., dict[str, Any]]
