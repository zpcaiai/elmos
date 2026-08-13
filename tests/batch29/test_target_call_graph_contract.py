from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas/batch29/module-equivalence-evidence.schema.json"
VALIDATOR_PATH = ROOT / "scripts/batch29/validate_route.py"


def _load_route_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "batch29_target_call_graph_validator", VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _edge_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": schema["$defs"],
            "$ref": "#/$defs/target_call_graph_edge",
        }
    )


def _javascript_semantic_document() -> dict[str, Any]:
    return {
        "functions": [
            {
                "name": "divide",
                "parameters": [
                    {"name": "left", "type": "integer"},
                    {"name": "right", "type": "integer"},
                ],
                "return_type": "integer",
                "body": [
                    {
                        "kind": "return",
                        "expression": {
                            "kind": "binary",
                            "operator": "/",
                            "left": {"kind": "name", "value": "left"},
                            "right": {"kind": "name", "value": "right"},
                        },
                    }
                ],
            }
        ]
    }


def _javascript_edges() -> list[dict[str, str]]:
    edges = [
        {
            "caller": "divide",
            "canonical_caller": "divide",
            "callee": "_elmosRequireSafeInteger",
            "callee_kind": "exact-generated-helper",
            "canonical_domain": "integer",
            "canonical_operator": "guard",
            "normalization_rule": "javascript.parameter.integer.exact",
            "guard_scope": "signature-parameter",
            "guard_subject": "left",
            "canonical_guard_subject": "left",
        },
        {
            "caller": "divide",
            "canonical_caller": "divide",
            "callee": "_elmosRequireSafeInteger",
            "callee_kind": "exact-generated-helper",
            "canonical_domain": "integer",
            "canonical_operator": "guard",
            "normalization_rule": "javascript.parameter.integer.exact",
            "guard_scope": "signature-parameter",
            "guard_subject": "right",
            "canonical_guard_subject": "right",
        },
        {
            "caller": "divide",
            "canonical_caller": "divide",
            "callee": "_elmosRequireSafeInteger",
            "callee_kind": "exact-generated-helper",
            "canonical_domain": "integer",
            "canonical_operator": "guard",
            "normalization_rule": "javascript.return.integer.safe-integer",
            "guard_scope": "signature-return",
            "guard_subject": "return",
            "canonical_guard_subject": "return",
        },
        {
            "caller": "divide",
            "canonical_caller": "divide",
            "callee": "_elmosRequireSafeInteger",
            "callee_kind": "exact-generated-helper",
            "canonical_domain": "integer",
            "canonical_operator": "/",
            "normalization_rule": "javascript.integer./.safe-integer",
            "guard_scope": "arithmetic-result",
            "guard_subject": "/",
        },
        {
            "caller": "divide",
            "canonical_caller": "divide",
            "callee": "_elmosRequireNonZero",
            "callee_kind": "exact-generated-helper",
            "canonical_domain": "integer",
            "canonical_operator": "/",
            "normalization_rule": "javascript.integer./.truncating-non-zero",
            "guard_scope": "arithmetic-divisor",
            "guard_subject": "/",
        },
    ]
    return sorted(
        edges,
        key=lambda edge: (
            edge["caller"],
            edge["callee"],
            edge["canonical_domain"],
            edge["canonical_operator"],
            edge["guard_scope"],
            edge["guard_subject"],
        ),
    )


def _target_call_graph(edges: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "status": "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS",
        "scope": "profile-functions-to-emitted-callees",
        "edges": edges,
        "helper_internal_calls": {
            "status": "CONTENT_BOUND_NOT_EDGE_ENUMERATED",
            "binding": "verified_generated_helpers-exact-bytes-and-digests",
        },
    }


def _typescript_semantic_documents() -> tuple[dict[str, Any], dict[str, Any]]:
    raw = {
        "source_language": "typescript",
        "functions": [
            {
                "name": "Object",
                "parameters": [
                    {"name": "left", "type": "integer"},
                    {"name": "right", "type": "integer"},
                ],
                "return_type": "integer",
                "body": [
                    {
                        "kind": "return",
                        "expression": {
                            "kind": "binary",
                            "operator": "/",
                            "left": {"kind": "name", "value": "left"},
                            "right": {"kind": "name", "value": "right"},
                        },
                    }
                ],
            },
            {
                "name": "Number",
                "parameters": [
                    {"name": "value", "type": "number"},
                    {"name": "modulus", "type": "number"},
                ],
                "return_type": "number",
                "body": [
                    {
                        "kind": "return",
                        "expression": {
                            "kind": "binary",
                            "operator": "%",
                            "left": {"kind": "name", "value": "value"},
                            "right": {"kind": "name", "value": "modulus"},
                        },
                    }
                ],
            },
        ],
    }
    canonical = copy.deepcopy(raw)
    canonical["functions"][0]["name"] = "elmosUserObject"
    canonical["functions"][1]["name"] = "elmosUserNumber"
    return raw, canonical


def _typescript_identifier_functions() -> list[dict[str, Any]]:
    return [
        {
            "raw_symbol": "Object",
            "canonical_symbol": "elmosUserObject",
            "parameters": [
                {
                    "raw_name": "left",
                    "canonical_name": "left",
                    "canonical_type": "integer",
                },
                {
                    "raw_name": "right",
                    "canonical_name": "right",
                    "canonical_type": "integer",
                },
            ],
        },
        {
            "raw_symbol": "Number",
            "canonical_symbol": "elmosUserNumber",
            "parameters": [
                {
                    "raw_name": "value",
                    "canonical_name": "value",
                    "canonical_type": "number",
                },
                {
                    "raw_name": "modulus",
                    "canonical_name": "modulus",
                    "canonical_type": "number",
                },
            ],
        },
    ]


def _typescript_edges() -> list[dict[str, str]]:
    validator = _load_route_validator()
    raw, canonical = _typescript_semantic_documents()
    failures: list[str] = []
    edges = validator._typescript_expected_target_call_graph_edges(
        raw,
        canonical,
        _typescript_identifier_functions(),
        failures,
    )
    assert failures == []
    return sorted(edges, key=validator._target_call_graph_sort_key)


def _validate_typescript_graph(edges: list[dict[str, str]]) -> list[str]:
    validator = _load_route_validator()
    raw, canonical = _typescript_semantic_documents()
    failures: list[str] = []
    validator._validate_target_call_graph(
        target_call_graph=_target_call_graph(edges),
        manifest_symbols=["elmosUserNumber", "elmosUserObject"],
        target_language="typescript",
        raw_target_semantic_document=raw,
        target_semantic_document=canonical,
        identifier_functions=_typescript_identifier_functions(),
        helper_identifiers={
            "_elmosRequireFiniteNumber",
            "_elmosRequireNonZero",
            "_elmosRequireSafeInteger",
        },
        normalizations=[edge["normalization_rule"] for edge in _typescript_edges()],
        failures=failures,
    )
    return failures


def _validate_javascript_graph(edges: list[dict[str, str]]) -> list[str]:
    validator = _load_route_validator()
    failures: list[str] = []
    validator._validate_target_call_graph(
        target_call_graph=_target_call_graph(edges),
        manifest_symbols=["divide"],
        target_language="javascript",
        raw_target_semantic_document=_javascript_semantic_document(),
        target_semantic_document=_javascript_semantic_document(),
        identifier_functions=[
            {
                "raw_symbol": "divide",
                "canonical_symbol": "divide",
                "parameters": [
                    {
                        "raw_name": "left",
                        "canonical_name": "left",
                        "canonical_type": "integer",
                    },
                    {
                        "raw_name": "right",
                        "canonical_name": "right",
                        "canonical_type": "integer",
                    },
                ],
            }
        ],
        helper_identifiers={
            "_elmosRequireSafeInteger",
            "_elmosRequireNonZero",
        },
        normalizations=[edge["normalization_rule"] for edge in _javascript_edges()],
        failures=failures,
    )
    return failures


def test_target_call_graph_schema_distinguishes_guards_and_arithmetic() -> None:
    edge_validator = _edge_validator()
    guard = next(
        edge
        for edge in _javascript_edges()
        if edge["guard_scope"] == "signature-parameter"
    )
    scoped_arithmetic = next(
        edge
        for edge in _javascript_edges()
        if edge["guard_scope"] == "arithmetic-result"
    )
    old_six_field_arithmetic = {
        key: value
        for key, value in scoped_arithmetic.items()
        if key not in {"canonical_caller", "guard_scope", "guard_subject"}
    }

    for edge in (guard, scoped_arithmetic, old_six_field_arithmetic):
        assert list(edge_validator.iter_errors(edge)) == []


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("missing-scope", None),
        ("missing-subject", None),
        ("extra-field", None),
        ("wrong-operator", "+"),
        ("wrong-domain", "decimal"),
        ("arithmetic-masquerading-as-guard", "guard"),
    ],
)
def test_target_call_graph_schema_rejects_malformed_edge(
    mutation: str, value: str | None
) -> None:
    edge_validator = _edge_validator()
    edge = copy.deepcopy(_javascript_edges()[2])
    if mutation == "missing-scope":
        del edge["guard_scope"]
    elif mutation == "missing-subject":
        del edge["guard_subject"]
    elif mutation == "extra-field":
        edge["untrusted"] = "value"
    elif mutation == "wrong-operator":
        assert value is not None
        edge["canonical_operator"] = value
    elif mutation == "wrong-domain":
        assert value is not None
        edge["canonical_domain"] = value
    else:
        edge = copy.deepcopy(_javascript_edges()[1])
        assert value is not None
        edge["canonical_operator"] = value

    assert list(edge_validator.iter_errors(edge)) != []


def test_target_call_graph_validator_accepts_exact_javascript_closure() -> None:
    assert _validate_javascript_graph(_javascript_edges()) == []


def test_target_call_graph_validator_rebuilds_exact_typescript_guards() -> None:
    edges = _typescript_edges()
    assert len(edges) == 8
    assert _validate_typescript_graph(edges) == []
    assert all(list(_edge_validator().iter_errors(edge)) == [] for edge in edges)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-parameter",
        "missing-return",
        "missing-arithmetic-result",
        "missing-divisor",
        "forged-callee",
        "forged-rule",
        "forged-domain",
        "forged-canonical-caller",
        "duplicate",
    ],
)
def test_target_call_graph_validator_rejects_typescript_delete_forge_or_duplicate(
    mutation: str,
) -> None:
    edges = copy.deepcopy(_typescript_edges())
    if mutation == "missing-parameter":
        edges = [
            edge
            for edge in edges
            if not (
                edge["caller"] == "Object"
                and edge.get("guard_scope") == "signature-parameter"
                and edge.get("guard_subject") == "left"
            )
        ]
    elif mutation == "missing-return":
        edges = [
            edge
            for edge in edges
            if not (
                edge["caller"] == "Number"
                and edge.get("guard_scope") == "signature-return"
            )
        ]
    elif mutation == "missing-arithmetic-result":
        edges = [
            edge
            for edge in edges
            if not (
                edge["caller"] == "Number"
                and edge.get("guard_scope") == "arithmetic-result"
            )
        ]
    elif mutation == "missing-divisor":
        edges = [
            edge
            for edge in edges
            if not (
                edge["caller"] == "Object"
                and edge.get("guard_scope") == "arithmetic-divisor"
            )
        ]
    elif mutation == "duplicate":
        edges.append(copy.deepcopy(edges[0]))
    else:
        edge = next(
            item
            for item in edges
            if item.get("guard_scope") == "arithmetic-result"
            and item["caller"] == "Number"
        )
        if mutation == "forged-callee":
            edge["callee"] = "_elmosRequireSafeInteger"
        elif mutation == "forged-rule":
            edge["normalization_rule"] = "typescript.number.%.safe-integer"
        elif mutation == "forged-domain":
            edge["canonical_domain"] = "integer"
        else:
            edge["canonical_caller"] = "Number"
    validator = _load_route_validator()
    edges.sort(key=validator._target_call_graph_sort_key)
    failures = _validate_typescript_graph(edges)
    assert any(
        "TypeScript target call graph" in failure
        or "duplicate edges" in failure
        or "detached" in failure
        for failure in failures
    ), failures


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    [
        ("missing-scope", "keys are invalid"),
        ("missing-subject", "keys are invalid"),
        ("extra-field", "keys are invalid"),
        ("wrong-operator", "keys are invalid"),
        ("wrong-domain", "missing exact edge"),
        ("duplicate", "contains duplicate edges"),
        ("missing-parameter", "missing exact edge divide:signature-parameter:left"),
        ("missing-return", "missing exact edge divide:signature-return:return"),
        ("arithmetic-masquerading-as-guard", "keys are invalid"),
    ],
)
def test_target_call_graph_validator_rejects_incomplete_or_forged_edges(
    mutation: str, diagnostic: str
) -> None:
    edges = copy.deepcopy(_javascript_edges())
    if mutation == "missing-scope":
        del edges[2]["guard_scope"]
    elif mutation == "missing-subject":
        del edges[2]["guard_subject"]
    elif mutation == "extra-field":
        edges[2]["untrusted"] = "value"
    elif mutation == "wrong-operator":
        edges[2]["canonical_operator"] = "+"
    elif mutation == "wrong-domain":
        edges[2]["canonical_domain"] = "number"
    elif mutation == "duplicate":
        edges.append(copy.deepcopy(edges[2]))
        edges.sort(
            key=lambda edge: (
                edge["caller"],
                edge["callee"],
                edge["canonical_domain"],
                edge["canonical_operator"],
                edge.get("guard_scope", "operator"),
                edge.get("guard_subject", ""),
            )
        )
    elif mutation == "missing-parameter":
        edges = [
            edge
            for edge in edges
            if not (
                edge.get("guard_scope") == "signature-parameter"
                and edge.get("guard_subject") == "left"
            )
        ]
    elif mutation == "missing-return":
        edges = [
            edge for edge in edges if edge.get("guard_scope") != "signature-return"
        ]
    else:
        arithmetic = next(
            edge for edge in edges if edge.get("guard_scope") == "arithmetic-result"
        )
        arithmetic["canonical_operator"] = "guard"

    failures = _validate_javascript_graph(edges)
    assert any(diagnostic in failure for failure in failures), failures


def test_target_call_graph_validator_keeps_legacy_six_field_arithmetic_edge() -> None:
    validator = _load_route_validator()
    edge = {
        "caller": "calculate",
        "callee": "elmos_checked_add",
        "callee_kind": "exact-generated-helper",
        "canonical_domain": "integer",
        "canonical_operator": "+",
        "normalization_rule": "cpp.integer.+.call:elmos_checked_add",
    }
    failures: list[str] = []
    validator._validate_target_call_graph(
        target_call_graph=_target_call_graph([edge]),
        manifest_symbols=["calculate"],
        target_language="cpp",
        raw_target_semantic_document={},
        target_semantic_document={},
        identifier_functions=[],
        helper_identifiers={"elmos_checked_add"},
        normalizations=[edge["normalization_rule"]],
        failures=failures,
    )
    assert failures == []
