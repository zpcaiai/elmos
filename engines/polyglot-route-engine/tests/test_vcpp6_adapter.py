from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.discovery import Verdict, discover_repository
from elmos_polyglot_route.models import RouteError, SemanticIR
from elmos_polyglot_route.repository import plan_repository
from elmos_polyglot_route.source_analyzer import analyze, inventory_module


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="ascii", newline="\r\n")
    return path


def _integer_add_ir() -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "python",
            "source_file": "source.py",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "add_values",
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
                                "operator": "+",
                                "left": {"kind": "name", "value": "left"},
                                "right": {"kind": "name", "value": "right"},
                            },
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )


def test_vcpp6_source_lifts_bounded_typed_module_and_inventory(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "pricing.cpp",
        "#include <string>\n"
        "__int64 Calculate(__int64 left, __int64 right) {\n"
        "    __int64 total = left + right;\n"
        "    if (total > 10) {\n"
        "        return total / 2;\n"
        "    } else {\n"
        "        return total;\n"
        "    }\n"
        "}\n",
    )

    semantic = analyze(source, "vcpp6", "Calculate")
    assert semantic.source_language == "vcpp6"
    assert semantic.functions[0].name == "Calculate"
    inventory = inventory_module(source, "vcpp6")
    assert inventory["enumeration_status"] == "PASSED"
    assert [subject["name"] for subject in inventory["subjects"]] == ["Calculate"]
    assert "VCPP6_VENDOR_COMPILER_RUNTIME_NOT_RUN" in inventory["diagnostics"]


def test_other_language_ir_emits_vcpp6_and_relifts_generated_target(tmp_path: Path) -> None:
    emitted = emit(_integer_add_ir(), "vcpp6")
    assert emitted.relative_path == "migrated.cpp"
    assert "__int64" in emitted.content
    assert "ElmosCheckedAdd" in emitted.content
    assert "__builtin" not in emitted.content

    target = _write(tmp_path / "migrated.cpp", emitted.content)
    relifted = analyze(target, "vcpp6", "add_values", emitted_target=True)
    assert relifted.functions[0].semantic_mapping() == _integer_add_ir().functions[0].semantic_mapping()


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (
            "__int64 Identity(__int64 *value) {\nreturn *value;\n}\n",
            "VCPP6_PARAMETER_SHAPE_OUTSIDE_CERTIFIED_SUBSET",
        ),
        (
            "__int64 Allocate(__int64 value) {\nreturn new int(value);\n}\n",
            "VCPP6_CONTROL_OR_EFFECT_SEMANTICS_OUTSIDE_CERTIFIED_SUBSET|VCPP6_UNSUPPORTED",
        ),
        (
            "__int64 Self(__int64 value) {\n__int64 next = next + value;\nreturn next;\n}\n",
            "VCPP6_UNDECLARED_NAME:next",
        ),
    ],
)
def test_vcpp6_rejects_pointer_effect_and_uninitialized_semantics(
    tmp_path: Path, body: str, error: str
) -> None:
    source = _write(tmp_path / "unsafe.cpp", body)
    with pytest.raises(RouteError, match=error):
        analyze(source, "vcpp6", body.split("(", 1)[0].split()[-1])


def test_vcpp6_mfc_com_and_preprocessor_surface_remains_explicit_gap(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "mfc.cpp",
        "#include <afxwin.h>\n__int64 Value(__int64 value) {\nreturn value;\n}\n",
    )
    with pytest.raises(RouteError, match="VCPP6_PREPROCESSOR_DIRECTIVE_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "vcpp6", "Value")


def test_vcpp6_repository_identity_is_distinct_from_modern_cpp(tmp_path: Path) -> None:
    repository = tmp_path / "legacy-vcpp6"
    repository.mkdir()
    _write(
        repository / "Pricing.cpp",
        "__int64 Price(__int64 amount) {\nreturn amount;\n}\n",
    )
    plan = plan_repository(repository, "local:legacy-vcpp6", "vcpp6", "java")
    assert plan["source_file_count"] == 1
    assert plan["language_counts"]["vcpp6"] == 1
    discovery = discover_repository(plan, repository)
    assert discovery["discovered_count"] == 1
    assert discovery["results"][0]["verdict"] == Verdict.READY
    assert discovery["results"][0]["function_name"] == "Price"


def test_vcpp6_records_are_not_silently_lowered() -> None:
    ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "python",
            "source_file": "source.py",
            "analyzer": "test",
            "analyzer_version": "1",
            "records": [{"name": "Point", "fields": [{"name": "x", "type": "integer"}]}],
            "functions": [
                {
                    "name": "origin",
                    "parameters": [{"name": "point", "type": "Point"}],
                    "return_type": "integer",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "member_access",
                                "target": {"kind": "name", "value": "point"},
                                "member": "x",
                            },
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )
    with pytest.raises(RouteError, match="VCPP6_RECORD_LOWERING_OUTSIDE_BOUNDED_PROFILE"):
        emit(ir, "vcpp6")
