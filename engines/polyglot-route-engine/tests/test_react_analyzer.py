from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from elmos_polyglot_route import react_analyzer
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import (
    plan_identifiers,
    target_function_view,
)
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.source_analyzer import analyze, inventory_module

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "react"


def test_development_fixture_uses_real_node_typescript_and_react_closures() -> None:
    semantic = analyze(FIXTURES / "development" / "clamp.tsx", "react", "clamp")

    assert semantic.source_language == "react"
    assert semantic.analyzer == "ELMOS React/TSX typed-pure source analyzer"
    assert semantic.analyzer_version.startswith(
        "TypeScript 5.9.2 / Node 26.0.0 / React 19.2.7 / React DOM 19.2.7;"
    )
    assert "analyzer-sha256=" in semantic.analyzer_version
    assert "dependency-profile-sha256=" in semantic.analyzer_version
    function = semantic.functions[0]
    assert function.name == "clamp"
    assert [parameter.type for parameter in function.parameters] == ["number", "number", "number"]
    assert [statement.kind for statement in function.body] == ["if", "if", "return"]
    assert function.source_span is not None
    assert function.source_span.file == "clamp.tsx"
    assert function.source_span.start_byte == 0
    assert function.source_span.end_byte == len(
        (FIXTURES / "development" / "clamp.tsx").read_bytes()
    ) - 1
    assert semantic.diagnostics == ()


def test_independent_holdout_fixture_lifts_without_development_specific_defaults() -> None:
    semantic = analyze(FIXTURES / "holdout" / "adjust.tsx", "react", "adjust")

    function = semantic.functions[0]
    assert [parameter.type for parameter in function.parameters] == ["number", "boolean"]
    assert function.return_type == "number"
    assert [statement.kind for statement in function.body] == ["if", "return"]
    condition = function.body[0].condition
    assert condition is not None
    assert condition.operator == "&&"


@pytest.mark.parametrize(
    ("fixture", "function_name", "error"),
    [
        ("component.tsx", "Counter", "REACT_COMPONENT_SEMANTICS_UNSUPPORTED:Counter"),
        ("effect.tsx", "readValue", "REACT_HOOK_SEMANTICS_UNSUPPORTED:useEffect"),
        ("hook-global.tsx", "readCount", "REACT_HOOK_SEMANTICS_UNSUPPORTED:useState"),
        ("hook.tsx", "Counter", "REACT_IMPORT_BOUND_SEMANTICS_UNSUPPORTED:ImportDeclaration"),
        ("jsx.tsx", "renderLabel", "REACT_UI_SEMANTICS_UNSUPPORTED:JsxElement"),
        ("side-effect.tsx", "report", "REACT_ROUTE_PROFILE_UNSUPPORTED:ExpressionStatement"),
    ],
)
def test_negative_corpus_fails_closed(fixture: str, function_name: str, error: str) -> None:
    with pytest.raises(RouteError, match=re.escape(error)):
        analyze(FIXTURES / "negative" / fixture, "react", function_name)


def test_react_dependency_receipt_is_exact_and_content_addressed() -> None:
    receipt = react_analyzer._dependency_receipt()

    assert [(entry["name"], entry["version"]) for entry in receipt] == [
        ("react", "19.2.7"),
        ("react-dom", "19.2.7"),
        ("@types/react", "19.1.10"),
        ("@types/react-dom", "19.1.7"),
        ("typescript", "5.9.2"),
    ]
    assert all(len(str(entry["sha256"])) == 64 for entry in receipt)
    assert len(react_analyzer._profile_digest(receipt)) == 64


def test_react_and_react_dom_runtime_entries_are_really_imported() -> None:
    toolchain = react_analyzer.exact_toolchain("react")
    receipt = react_analyzer.verify_react_runtime_import(toolchain)

    assert receipt["status"] == "PASSED"
    assert receipt["versions"] == {"react": "19.2.7", "react-dom": "19.2.7"}
    assert receipt["browser_execution_status"] == "NOT_RUN"
    assert receipt["certification_status"] == "NOT_CERTIFIED"

    tampered = dict(receipt)
    tampered["versions"] = {"react": "19.2.7", "react-dom": "0.0.0"}
    with pytest.raises(RouteError, match="REACT_RUNTIME_RECEIPT_DIGEST_INVALID"):
        react_analyzer.validate_react_runtime_receipt(toolchain, tampered)

    self_consistent = dict(receipt)
    self_consistent["stdout"] = '{"react":"0.0.0","react-dom":"19.2.7"}\n'
    self_consistent["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            react_analyzer._runtime_probe_digest_payload(self_consistent),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    with pytest.raises(RouteError, match="REACT_RUNTIME_RECEIPT_STDOUT_INVALID"):
        react_analyzer.validate_react_runtime_receipt(toolchain, self_consistent)


def test_ts_and_tsx_module_inventory_is_compiler_backed(tmp_path: Path) -> None:
    source = tmp_path / "helper.ts"
    source.write_text("export function helper(value: number): number { return value; }\n", encoding="utf-8")

    semantic = analyze(source, "react", "helper")
    inventory = inventory_module(source, "react")

    assert semantic.functions[0].name == "helper"
    assert inventory["source_language"] == "react"
    assert inventory["enumeration_status"] == "PASSED"
    assert inventory["subjects"] == [
        {
            "name": "helper",
            "qualified_name": "helper",
            "occurrence": 1,
            "declaration_kind": "FunctionDeclaration",
            "analyzable": True,
            "signature": {
                "parameters": [{"name": "value", "source_type": "number"}],
                "source_return_type": "number",
                "storage": "file-scope",
                "visibility": "exported",
            },
            "source_span": {
                "file": "helper.ts",
                "start_byte": 0,
                "end_byte": len(source.read_bytes()) - 1,
            },
        }
    ]


def test_generated_pure_tsx_target_is_reanalyzed_by_the_same_exact_frontend(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tsx"
    source.write_text(
        "export function migrated(value: number): number { return value + 1; }\n",
        encoding="utf-8",
    )
    source_ir = analyze(source, "react", "migrated")
    identifier_plan = plan_identifiers(source_ir, "react")
    target_function_name = target_function_view(
        source_ir,
        source_ir.functions[0],
        identifier_plan,
    ).name
    target = tmp_path / "migrated.tsx"
    target.write_text(
        emit(source_ir, "react", identifier_plan=identifier_plan).content,
        encoding="utf-8",
    )

    semantic = analyze(
        target,
        "react",
        target_function_name,
        emitted_target=True,
    )
    inventory = inventory_module(target, "react", emitted_target=True)

    assert semantic.source_language == "react"
    assert semantic.functions[0].name == target_function_name
    assert inventory["source_language"] == "react"
    assert inventory["enumeration_status"] == "PASSED"
