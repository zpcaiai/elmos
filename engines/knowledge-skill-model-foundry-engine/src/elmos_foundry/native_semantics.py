"""Exact repository-owned semantic programs for brokered Foundry Skills.

The source package describes contracts but contains no executable runtime.  This
module loads a separately checked-in repository implementation manifest and
turns every entry into an immutable program.  Programs are exact to one Skill,
source digest, workflow, tool set, gate set, dependency set and rollback
strategy.  There is no name inference or fallback program.

Provider effects still cross the host-owned broker boundary.  A successful
broker response must prove that it ran the exact program, in order, with the
exact allowed tools and gates.  This is repository code coverage, not provider
evidence, independent verification or certification.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .canonical import canonical_digest, canonical_value, require_identifier, validate_digest


NATIVE_SEMANTIC_VERSION = "1.0.0"
NATIVE_PROGRAM_SCHEMA_VERSION = "elmos.foundry.native-semantic-program.v1"
NATIVE_MANIFEST_SCHEMA_VERSION = "elmos.foundry.native-semantic-manifest.v1"
NATIVE_TRACE_SCHEMA_VERSION = "elmos.foundry.native-semantic-trace.v1"
NATIVE_PROGRAM_PATH = Path(__file__).with_name("native-semantic-programs.json")


class NativeSemanticError(ValueError):
    """A native program or its execution trace is missing or not exact."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise NativeSemanticError(f"{label} must be a string-keyed object")
    return value


def _exact_mapping(value: Any, label: str, keys: set[str]) -> Mapping[str, Any]:
    result = _mapping(value, label)
    if set(result) != keys:
        raise NativeSemanticError(
            f"{label} keys are not exact; missing={sorted(keys - set(result))}, "
            f"extra={sorted(set(result) - keys)}"
        )
    return result


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise NativeSemanticError(f"{label} must be non-empty canonical text")
    return value


def _strings(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise NativeSemanticError(f"{label} must be an array")
    result = tuple(_text(item, label) for item in value)
    if (not result and not allow_empty) or len(result) != len(set(result)):
        raise NativeSemanticError(f"{label} must be non-empty and unique")
    return result


def _plain_digest(value: Mapping[str, Any]) -> str:
    return canonical_digest(value).removeprefix("sha256:")


def _artifact_contract(name: str, direction: str) -> Mapping[str, Any]:
    return {
        "name": name,
        "schema": "elmos.foundry.content-addressed-artifact.v1",
        "direction": direction,
        "required": True,
        "tenant_scoped": True,
        "content_addressed": True,
    }


def build_program_document(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Compile one verified catalog row into its exact executable contract.

    Tool placement follows source order and is fixed in the emitted program.
    Runtime never recomputes placement from a caller-controlled request.
    """

    name = require_identifier(record.get("name"), "skill_name")
    pack = require_identifier(record.get("pack"), "pack")
    version = require_identifier(record.get("version"), "skill_version")
    source_sha256 = _text(record.get("source_sha256"), "source_sha256")
    if len(source_sha256) != 64:
        raise NativeSemanticError("source_sha256 must be a lowercase SHA-256")
    workflow = _strings(record.get("workflow"), "workflow")
    tools = _strings(record.get("allowed_tools"), "allowed_tools")
    inputs = _strings(record.get("inputs"), "inputs")
    outputs = _strings(record.get("outputs"), "outputs")
    gates = _strings(record.get("required_gates"), "required_gates")
    dependencies = _strings(record.get("dependencies"), "dependencies", allow_empty=True)
    invariants = _strings(record.get("invariants"), "invariants")
    rollback = _mapping(record.get("rollback_contract"), "rollback_contract")
    rollback_strategy = _text(rollback.get("strategy"), "rollback_contract.strategy")

    assigned: list[list[str]] = [[] for _ in workflow]
    if len(tools) == 1:
        assigned[0].append(tools[0])
    else:
        last_stage = len(workflow) - 1
        last_tool = len(tools) - 1
        for index, tool in enumerate(tools):
            stage_index = (index * last_stage + last_tool // 2) // last_tool
            assigned[stage_index].append(tool)
    stages = []
    for index, stage_name in enumerate(workflow):
        stages.append(
            {
                "index": index,
                "name": stage_name,
                "operation": f"foundry.skill.{name}.stage.{stage_name}",
                "tools": assigned[index],
                "checkpoint_required": True,
                "input_chain": "REQUEST" if index == 0 else "PREVIOUS_STAGE",
                "failure_transition": "COMPENSATE_AND_BLOCK",
            }
        )
    return {
        "schema_version": NATIVE_PROGRAM_SCHEMA_VERSION,
        "implementation_version": NATIVE_SEMANTIC_VERSION,
        "skill_name": name,
        "handler_id": f"native.{name}",
        "skill_version": version,
        "skill_source_sha256": source_sha256,
        "pack": pack,
        "risk_class": _text(record.get("risk_class"), "risk_class"),
        "objective": _text(record.get("description"), "description"),
        "effect_class": "PRIVILEGED_EXTERNAL",
        "inputs": [_artifact_contract(item, "INPUT") for item in inputs],
        "outputs": [_artifact_contract(item, "OUTPUT") for item in outputs],
        "dependencies": list(dependencies),
        "stages": stages,
        "required_gates": list(gates),
        "invariants": list(invariants),
        "rollback_strategy": rollback_strategy,
        "success_state": "PROVIDER_RECEIPT_VERIFIED",
        "certification_state": "NOT_CERTIFIED",
    }


@dataclass(frozen=True, slots=True)
class NativeSemanticProgram:
    """One immutable, exact, broker-executed semantic program."""

    document: Mapping[str, Any]
    digest: str

    def __post_init__(self) -> None:
        normalized = canonical_value(self.document)
        if not isinstance(normalized, dict):
            raise NativeSemanticError("native program must be an object")
        if _plain_digest(normalized) != self.digest:
            raise NativeSemanticError("native program digest does not match its document")
        object.__setattr__(self, "document", MappingProxyType(normalized))

    @property
    def skill_name(self) -> str:
        return str(self.document["skill_name"])

    @property
    def handler_id(self) -> str:
        return str(self.document["handler_id"])

    @property
    def stages(self) -> tuple[Mapping[str, Any], ...]:
        raw = self.document["stages"]
        if not isinstance(raw, list):
            raise NativeSemanticError("native program stages must be an array")
        return tuple(_mapping(item, "native program stage") for item in raw)

    @property
    def required_gates(self) -> tuple[str, ...]:
        return _strings(self.document["required_gates"], "required_gates")

    @property
    def rollback_strategy(self) -> str:
        return str(self.document["rollback_strategy"])

    def validate_result(
        self,
        result: Mapping[str, Any],
        *,
        request_binding_digest: str,
    ) -> None:
        """Require an exact chained stage, tool, gate and rollback trace."""

        execution = _exact_mapping(
            result.get("semantic_execution"),
            "semantic_execution",
            {
                "schema_version",
                "skill_name",
                "handler_id",
                "program_digest",
                "request_binding_digest",
                "stages",
                "gate_evidence",
                "rollback",
            },
        )
        expected_header = {
            "schema_version": NATIVE_TRACE_SCHEMA_VERSION,
            "skill_name": self.skill_name,
            "handler_id": self.handler_id,
            "program_digest": self.digest,
            "request_binding_digest": request_binding_digest,
        }
        for key, expected in expected_header.items():
            if execution.get(key) != expected:
                raise NativeSemanticError(f"semantic_execution.{key} is not exact")

        raw_stages = execution.get("stages")
        if not isinstance(raw_stages, list) or len(raw_stages) != len(self.stages):
            raise NativeSemanticError("semantic execution stage inventory is not exact")
        expected_input = request_binding_digest
        for expected_stage, raw_stage in zip(self.stages, raw_stages, strict=True):
            stage = _exact_mapping(
                raw_stage,
                "semantic_execution.stage",
                {
                    "index",
                    "name",
                    "operation",
                    "status",
                    "input_digest",
                    "output_digest",
                    "checkpoint_digest",
                    "tool_receipts",
                },
            )
            for key in ("index", "name", "operation"):
                if stage.get(key) != expected_stage.get(key):
                    raise NativeSemanticError(f"semantic stage {key} is not exact")
            if stage.get("status") != "SUCCEEDED":
                raise NativeSemanticError("semantic stage did not succeed")
            if stage.get("input_digest") != expected_input:
                raise NativeSemanticError("semantic stage digest chain is broken")
            output_digest = stage.get("output_digest")
            checkpoint_digest = stage.get("checkpoint_digest")
            validate_digest(output_digest, "semantic stage output_digest")
            validate_digest(checkpoint_digest, "semantic stage checkpoint_digest")
            expected_input = str(output_digest)
            receipts = stage.get("tool_receipts")
            if not isinstance(receipts, list):
                raise NativeSemanticError("semantic stage tool_receipts must be an array")
            expected_tools = tuple(expected_stage.get("tools", ()))
            if len(receipts) != len(expected_tools):
                raise NativeSemanticError("semantic stage tool receipt inventory is not exact")
            observed_tools: list[str] = []
            for raw_receipt in receipts:
                receipt = _exact_mapping(
                    raw_receipt,
                    "semantic stage tool receipt",
                    {"tool", "outcome", "receipt_digest"},
                )
                tool = _text(receipt.get("tool"), "tool receipt tool")
                observed_tools.append(tool)
                if receipt.get("outcome") != "CONFIRMED":
                    raise NativeSemanticError("semantic tool outcome is not confirmed")
                validate_digest(receipt.get("receipt_digest"), "tool receipt digest")
            if tuple(observed_tools) != expected_tools:
                raise NativeSemanticError("semantic stage used unbound or reordered tools")

        raw_gates = execution.get("gate_evidence")
        if not isinstance(raw_gates, list) or len(raw_gates) != len(self.required_gates):
            raise NativeSemanticError("semantic gate evidence inventory is not exact")
        observed_gates: list[str] = []
        for raw_gate in raw_gates:
            gate = _exact_mapping(
                raw_gate,
                "semantic gate evidence",
                {"gate", "status", "evidence_digest"},
            )
            observed_gates.append(_text(gate.get("gate"), "gate"))
            if gate.get("status") != "PASSED":
                raise NativeSemanticError("required semantic gate did not pass")
            validate_digest(gate.get("evidence_digest"), "gate evidence digest")
        if tuple(observed_gates) != self.required_gates:
            raise NativeSemanticError("semantic gate evidence is reordered or foreign")

        rollback = _exact_mapping(
            execution.get("rollback"),
            "semantic rollback",
            {"strategy", "status", "receipt_digest"},
        )
        if rollback.get("strategy") != self.rollback_strategy:
            raise NativeSemanticError("semantic rollback strategy is not exact")
        if rollback.get("status") not in {"NOT_REQUIRED", "REHEARSED", "COMPENSATED"}:
            raise NativeSemanticError("semantic rollback status is unsupported")
        validate_digest(rollback.get("receipt_digest"), "rollback receipt digest")


def _parse_program(raw: Mapping[str, Any]) -> NativeSemanticProgram:
    row = _exact_mapping(raw, "native program row", {"document", "program_digest"})
    document = _mapping(row["document"], "native program document")
    return NativeSemanticProgram(document=document, digest=_text(row["program_digest"], "program_digest"))


@lru_cache(maxsize=1)
def load_native_programs(path: Path = NATIVE_PROGRAM_PATH) -> Mapping[str, NativeSemanticProgram]:
    """Load the exact repository implementation allowlist."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeSemanticError(f"native semantic manifest is unavailable: {exc}") from exc
    root = _exact_mapping(
        raw,
        "native semantic manifest",
        {"schema_version", "implementation_version", "programs"},
    )
    if root["schema_version"] != NATIVE_MANIFEST_SCHEMA_VERSION:
        raise NativeSemanticError("native semantic manifest schema is unsupported")
    if root["implementation_version"] != NATIVE_SEMANTIC_VERSION:
        raise NativeSemanticError("native semantic implementation version is unsupported")
    rows = root["programs"]
    if not isinstance(rows, list) or not rows:
        raise NativeSemanticError("native semantic manifest programs must be non-empty")
    programs: dict[str, NativeSemanticProgram] = {}
    for raw_row in rows:
        program = _parse_program(_mapping(raw_row, "native program row"))
        if program.skill_name in programs:
            raise NativeSemanticError(f"duplicate native semantic program: {program.skill_name}")
        programs[program.skill_name] = program
    return MappingProxyType(programs)


def native_program_for(name: str, record: Mapping[str, Any]) -> NativeSemanticProgram:
    """Resolve one exact program and prove that it matches the catalog row."""

    program = load_native_programs().get(name)
    if program is None:
        raise NativeSemanticError(f"no exact native semantic program exists for {name}")
    expected = build_program_document(record)
    expected_digest = _plain_digest(expected)
    if program.digest != expected_digest or dict(program.document) != dict(expected):
        raise NativeSemanticError(f"native semantic program drift for {name}")
    return program


def build_manifest(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Build deterministic repository implementation source for exact records."""

    rows = []
    names: set[str] = set()
    for record in sorted(records, key=lambda item: str(item.get("name"))):
        document = build_program_document(record)
        name = str(document["skill_name"])
        if name in names:
            raise NativeSemanticError(f"duplicate native semantic input: {name}")
        names.add(name)
        rows.append({"document": document, "program_digest": _plain_digest(document)})
    return {
        "schema_version": NATIVE_MANIFEST_SCHEMA_VERSION,
        "implementation_version": NATIVE_SEMANTIC_VERSION,
        "programs": rows,
    }


__all__ = [
    "NATIVE_MANIFEST_SCHEMA_VERSION",
    "NATIVE_PROGRAM_PATH",
    "NATIVE_PROGRAM_SCHEMA_VERSION",
    "NATIVE_SEMANTIC_VERSION",
    "NATIVE_TRACE_SCHEMA_VERSION",
    "NativeSemanticError",
    "NativeSemanticProgram",
    "build_manifest",
    "build_program_document",
    "load_native_programs",
    "native_program_for",
]
