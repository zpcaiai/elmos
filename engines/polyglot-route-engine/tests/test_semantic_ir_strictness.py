from __future__ import annotations

import base64
import copy
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route.equivalence import (
    canonical_json_bytes,
    sha256_bytes,
    verify_formal_input_closure,
)
from elmos_polyglot_route.identifier_hygiene import (
    alpha_normalize_target,
    identifier_plan_bytes,
    plan_identifiers,
    target_ir_view,
)
from elmos_polyglot_route.models import RouteError, SemanticIR


def _span(start: int, end: int) -> dict[str, Any]:
    return {
        "source_span": {
            "file": "Source.java",
            "start_byte": start,
            "end_byte": end,
        }
    }


def _semantic_ir_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "source_language": "java",
        "source_file": "Source.java",
        "analyzer": "semantic-ir-strictness-test",
        "analyzer_version": "1",
        "functions": [
            {
                "name": "clampPositive",
                "parameters": [
                    {
                        "name": "value",
                        "type": "integer",
                        **_span(18, 23),
                    }
                ],
                "return_type": "integer",
                "body": [
                    {
                        "kind": "if",
                        "condition": {
                            "kind": "binary",
                            "operator": ">",
                            "left": {
                                "kind": "name",
                                "value": "value",
                                **_span(35, 40),
                            },
                            "right": {
                                "kind": "literal",
                                "value": 0,
                                **_span(43, 44),
                            },
                            **_span(35, 44),
                        },
                        "then": [
                            {
                                "kind": "return",
                                "expression": {
                                    "kind": "name",
                                    "value": "value",
                                    **_span(55, 60),
                                },
                                **_span(48, 61),
                            }
                        ],
                        "else": [],
                        **_span(31, 62),
                    },
                    {
                        "kind": "return",
                        "expression": {
                            "kind": "literal",
                            "value": 0,
                            **_span(70, 71),
                        },
                        **_span(63, 72),
                    },
                ],
                **_span(0, 73),
            }
        ],
        "diagnostics": [],
    }


def _mutate(payload: dict[str, Any], case_id: str) -> None:
    function = payload["functions"][0]
    parameter = function["parameters"][0]
    if_statement = function["body"][0]
    binary = if_statement["condition"]
    name = binary["left"]
    literal = binary["right"]
    if case_id == "root-extra":
        payload["attacker_extension"] = True
    elif case_id == "root-missing":
        del payload["analyzer"]
    elif case_id == "root-type":
        payload["source_language"] = 7
    elif case_id == "function-extra":
        function["ignored"] = True
    elif case_id == "function-missing":
        del function["return_type"]
    elif case_id == "function-list-member-type":
        payload["functions"].append("ignored-by-old-parser")
    elif case_id == "parameter-extra":
        parameter["ignored"] = True
    elif case_id == "parameter-missing":
        del parameter["type"]
    elif case_id == "parameter-list-member-type":
        function["parameters"].append("ignored-by-old-parser")
    elif case_id == "if-extra":
        if_statement["ignored"] = True
    elif case_id == "if-missing-else":
        del if_statement["else"]
    elif case_id == "statement-list-member-type":
        function["body"].append("ignored-by-old-parser")
    elif case_id == "branch-list-member-type":
        if_statement["else"].append("ignored-by-old-parser")
    elif case_id == "binary-extra":
        binary["ignored"] = True
    elif case_id == "binary-missing":
        del binary["right"]
    elif case_id == "binary-operator-type":
        binary["operator"] = 7
    elif case_id == "name-extra":
        name["ignored"] = True
    elif case_id == "name-value-type":
        name["value"] = 7
    elif case_id == "literal-extra":
        literal["ignored"] = True
    elif case_id == "literal-value-type":
        literal["value"] = {"ignored": True}
    elif case_id == "span-extra":
        name["source_span"]["ignored"] = True
    elif case_id == "span-missing":
        del name["source_span"]["end_byte"]
    elif case_id == "span-range-type":
        name["source_span"]["start_byte"] = "35"
    elif case_id == "span-null":
        name["source_span"] = None
    elif case_id == "diagnostic-member-type":
        payload["diagnostics"].append(7)
    else:  # pragma: no cover - the parametrization is the closed case set
        raise AssertionError(case_id)


def test_semantic_ir_closed_shape_round_trips_without_information_loss() -> None:
    payload = _semantic_ir_payload()

    assert SemanticIR.from_mapping(payload).to_mapping() == payload


@pytest.mark.parametrize(
    "case_id",
    [
        "root-extra",
        "root-missing",
        "root-type",
        "function-extra",
        "function-missing",
        "function-list-member-type",
        "parameter-extra",
        "parameter-missing",
        "parameter-list-member-type",
        "if-extra",
        "if-missing-else",
        "statement-list-member-type",
        "branch-list-member-type",
        "binary-extra",
        "binary-missing",
        "binary-operator-type",
        "name-extra",
        "name-value-type",
        "literal-extra",
        "literal-value-type",
        "span-extra",
        "span-missing",
        "span-range-type",
        "span-null",
        "diagnostic-member-type",
    ],
)
def test_semantic_ir_rejects_recursive_extra_missing_and_wrong_type(case_id: str) -> None:
    payload = _semantic_ir_payload()
    _mutate(payload, case_id)

    with pytest.raises(RouteError):
        SemanticIR.from_mapping(payload)


def _without_source_spans(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_source_spans(item) for key, item in value.items() if key != "source_span"}
    if isinstance(value, list):
        return [_without_source_spans(item) for item in value]
    return value


def _write_reference(root: Path, relative_path: str, content: bytes) -> dict[str, str]:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"path": relative_path, "sha256": sha256_bytes(content)}


def _artifact_binding(
    root: Path,
    *,
    role: str,
    relative_path: str,
    content: bytes,
) -> dict[str, Any]:
    reference = _write_reference(root, relative_path, content)
    return {
        "role": role,
        "path": Path(relative_path).name,
        "sha256": reference["sha256"],
        "byte_count": len(content),
        "content_base64": base64.b64encode(content).decode("ascii"),
        "content_reference": reference,
    }


def _ir_binding(
    root: Path,
    *,
    role: str,
    relative_path: str,
    ir: SemanticIR,
) -> dict[str, Any]:
    semantic_ir = ir.to_mapping()
    reference = _write_reference(root, relative_path, canonical_json_bytes(semantic_ir))
    formal_function = ir.functions[0].semantic_mapping()
    return {
        "role": role,
        "artifact": reference,
        "semantic_ir": semantic_ir,
        "semantic_ir_sha256": sha256_bytes(canonical_json_bytes(semantic_ir)),
        "formal_function": formal_function,
        "formal_function_sha256": sha256_bytes(canonical_json_bytes(formal_function)),
    }


def _formal_fixture(root: Path) -> tuple[dict[str, Any], Path]:
    source_ir = SemanticIR.from_mapping(_semantic_ir_payload())
    plan = plan_identifiers(source_ir, "python")
    raw_target_ir = replace(
        target_ir_view(source_ir, plan),
        source_language="python",
        source_file="migrated.py",
        analyzer="semantic-ir-strictness-target",
        analyzer_version="1",
    )
    normalized_target_ir = alpha_normalize_target(source_ir, raw_target_ir, plan)

    plan_reference = _write_reference(root, "identifier-plan.json", identifier_plan_bytes(plan))
    source_binding = _ir_binding(
        root,
        role="canonical-source-normalized-ir",
        relative_path="source-semantic-ir.json",
        ir=source_ir,
    )
    raw_binding = _ir_binding(
        root,
        role="emitted-target-relift-raw-ir",
        relative_path="target-semantic-ir.raw.json",
        ir=raw_target_ir,
    )
    normalized_binding = _ir_binding(
        root,
        role="emitted-target-relift-normalized-ir",
        relative_path="target-semantic-ir.normalized.json",
        ir=normalized_target_ir,
    )
    payload = {
        "kind": "elmos.formal-equivalence-input",
        "claim_scope": {
            "relation": "canonical-normalized-source-ir-to-target-relift-ir",
            "original_source_bytes_theorem": False,
            "source_compiler_runtime_soundness": "NOT_RUN",
        },
        "source_artifact": _artifact_binding(
            root,
            role="original-source-analyzer-input",
            relative_path="source-runtime/Source.java",
            content=b"final class Source {}\n",
        ),
        "target_artifact": _artifact_binding(
            root,
            role="emitted-target-analyzer-input",
            relative_path="migrated.py",
            content=b"def clampPositive(value: int) -> int:\n    return value\n",
        ),
        "source_normalized_ir": source_binding,
        "target_relift_normalized_ir": normalized_binding,
        "identifier_hygiene": {
            "kind": "elmos.verified-alpha-normalization",
            "policy_id": plan.policy_id,
            "policy_sha256": plan.policy_sha256,
            "plan": plan_reference,
            "plan_digest": plan.digest,
            "unit_namespace": plan.unit_namespace.to_mapping(),
            "unit_namespace_sha256": plan.unit_namespace.digest,
            "source_function_name": source_ir.functions[0].name,
            "target_function_name": raw_target_ir.functions[0].name,
            "raw_target_relift_ir": raw_binding,
            "normalized_target_ir": normalized_binding["artifact"],
        },
    }
    formal_path = root / "formal-input.json"
    formal_path.write_bytes(canonical_json_bytes(payload))
    return payload, formal_path


def _nested_extra(semantic_ir: dict[str, Any]) -> None:
    semantic_ir["functions"][0]["body"][0]["condition"]["left"]["attacker_extension"] = {"claim": "rewritten"}


def _missing_empty_else(semantic_ir: dict[str, Any]) -> None:
    del semantic_ir["functions"][0]["body"][0]["else"]


def _ignored_wrong_type(semantic_ir: dict[str, Any]) -> None:
    semantic_ir["functions"][0]["body"].append("ignored-by-old-parser")


@pytest.mark.parametrize(
    "rewrite",
    [_nested_extra, _missing_empty_else, _ignored_wrong_type],
    ids=["nested-extra", "nested-missing", "nested-wrong-type"],
)
def test_formal_verifier_rejects_self_consistent_semantic_ir_rewrite(
    tmp_path: Path,
    rewrite: Callable[[dict[str, Any]], None],
) -> None:
    payload, formal_path = _formal_fixture(tmp_path)
    original_reference = {
        "path": formal_path.name,
        "sha256": sha256_bytes(formal_path.read_bytes()),
    }
    verify_formal_input_closure(tmp_path, original_reference)

    tampered = copy.deepcopy(payload)
    source_binding = tampered["source_normalized_ir"]
    semantic_ir = source_binding["semantic_ir"]
    rewrite(semantic_ir)
    source_ir_bytes = canonical_json_bytes(semantic_ir)
    source_ir_path = tmp_path / source_binding["artifact"]["path"]
    source_ir_path.write_bytes(source_ir_bytes)
    source_binding["artifact"]["sha256"] = sha256_bytes(source_ir_bytes)
    source_binding["semantic_ir_sha256"] = sha256_bytes(source_ir_bytes)
    formal_function = _without_source_spans(semantic_ir["functions"][0])
    source_binding["formal_function"] = formal_function
    source_binding["formal_function_sha256"] = sha256_bytes(canonical_json_bytes(formal_function))
    formal_path.write_bytes(canonical_json_bytes(tampered))
    tampered_reference = {
        "path": formal_path.name,
        "sha256": sha256_bytes(formal_path.read_bytes()),
    }

    with pytest.raises(RouteError, match="SEMANTIC_IR_"):
        verify_formal_input_closure(tmp_path, tampered_reference)
