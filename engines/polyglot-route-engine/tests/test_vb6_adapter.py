from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import elmos_polyglot_route.validation as validation_module
from elmos_polyglot_route.discovery import Verdict, discover_repository, propose_candidates
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError, SemanticIR
from elmos_polyglot_route.repository import plan_repository
from elmos_polyglot_route.single_unit import check_only
from elmos_polyglot_route.source_analyzer import analyze, inventory_module
from elmos_polyglot_route.toolchains import ExactToolchain
from elmos_polyglot_route.validation import validate, validate_source


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8", newline="\r\n")
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


def test_vb6_source_lifts_typed_pure_module_and_inventory(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "math.bas",
        """Option Explicit
Public Function Calculate(ByVal a As Long, ByVal b As Long) As Long
    Dim total As Long
    total = a + b
    If total > 10& Then
        Calculate = total \\ 2&
        Exit Function
    Else
        Calculate = total
        Exit Function
    End If
End Function
""",
    )

    semantic = analyze(source, "vb6", "calculate")
    assert semantic.source_language == "vb6"
    assert semantic.functions[0].name == "Calculate"
    assert semantic.functions[0].body[-1].kind == "if"
    inventory = inventory_module(source, "vb6")
    assert inventory["enumeration_status"] == "PASSED"
    assert [subject["name"] for subject in inventory["subjects"]] == ["Calculate"]
    assert "VB6_VENDOR_COMPILER_RUNTIME_NOT_RUN" in inventory["diagnostics"]


def test_other_language_ir_emits_vb6_and_relifts_generated_target(tmp_path: Path) -> None:
    emitted = emit(_integer_add_ir(), "vb6")
    assert emitted.relative_path == "migrated.bas"
    assert "Option Explicit" in emitted.content
    assert "As Long" in emitted.content
    assert "ElmosCheckedAdd" in emitted.content

    target = _write(tmp_path / "migrated.bas", emitted.content)
    relifted = analyze(target, "vb6", "add_values", emitted_target=True)
    assert relifted.functions[0].semantic_mapping() == _integer_add_ir().functions[0].semantic_mapping()


@pytest.mark.parametrize(
    ("fragment", "error"),
    [
        ("ByRef value As Long", "VB6_BYREF_PARAMETER_OUTSIDE_CERTIFIED_SUBSET"),
        ("ByVal value As Variant", "VB6_TYPE_OUTSIDE_CERTIFIED_SUBSET"),
    ],
)
def test_vb6_rejects_implicit_or_reference_semantics(
    tmp_path: Path, fragment: str, error: str
) -> None:
    source = _write(
        tmp_path / "unsafe.bas",
        f"Option Explicit\nPublic Function Identity({fragment}) As Long\nIdentity = value\nEnd Function\n",
    )
    with pytest.raises(RouteError, match=error):
        analyze(source, "vb6", "Identity")


def test_vb6_rejects_ambiguous_numeric_and_string_operators(tmp_path: Path) -> None:
    integer_division = _write(
        tmp_path / "division.bas",
        "Option Explicit\nPublic Function Divide(ByVal a As Long, ByVal b As Long) As Long\n"
        "Divide = a / b\nEnd Function\n",
    )
    with pytest.raises(RouteError, match="VB6_FLOAT_DIVISION_ON_INTEGERS_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(integer_division, "vb6", "Divide")

    string_plus = _write(
        tmp_path / "strings.bas",
        "Option Explicit\nPublic Function JoinText(ByVal a As String, ByVal b As String) As String\n"
        "JoinText = a + b\nEnd Function\n",
    )
    with pytest.raises(RouteError, match="VB6_PLUS_STRING_COERCION_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(string_plus, "vb6", "JoinText")


def test_vb6_forms_com_and_cross_function_calls_remain_explicit_gaps(tmp_path: Path) -> None:
    form = _write(tmp_path / "Form1.frm", "VERSION 5.00\nBegin VB.Form Form1\nEnd\n")
    with pytest.raises(RouteError, match="VB6_MODULE_KIND_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(form, "vb6", "Anything")

    module = _write(
        tmp_path / "calls.bas",
        "Option Explicit\nPublic Function First(ByVal value As Long) As Long\n"
        "First = Second(value)\nEnd Function\n"
        "Public Function Second(ByVal value As Long) As Long\nSecond = value\nEnd Function\n",
    )
    with pytest.raises(RouteError, match="VB6_CROSS_FUNCTION_CALL_REQUIRES_MODULE_IR"):
        analyze(module, "vb6", "First")


def test_vb6_candidate_discovery_accepts_ansi_source() -> None:
    source = (
        "Option Explicit\r\n' caf\u00e9\r\n"
        "Public Function Price(ByVal amount As Double) As Double\r\n"
    ).encode("cp1252")
    assert propose_candidates(source, "vb6") == ["Price"]


def test_vb6_repository_inventory_and_discovery_are_wired(tmp_path: Path) -> None:
    repository = tmp_path / "legacy-vb6"
    repository.mkdir()
    _write(
        repository / "Pricing.bas",
        "Option Explicit\n"
        "Public Function Price(ByVal amount As Double) As Double\n"
        "    Price = amount\n"
        "End Function\n",
    )

    plan = plan_repository(repository, "local:legacy-vb6", "vb6", "java")
    assert plan["source_file_count"] == 1
    assert plan["work_units"][0]["source_path"] == "Pricing.bas"

    discovery = discover_repository(plan, repository)
    assert discovery["discovered_count"] == 1
    assert discovery["results"][0]["verdict"] == Verdict.READY
    assert discovery["results"][0]["function_name"] == "Price"


def test_vb6_static_check_requires_governed_windows_vendor_runtime(tmp_path: Path) -> None:
    with pytest.raises(
        RouteError,
        match="EXACT_TOOLCHAIN_PLATFORM_MISMATCH:vb6|VB6_VENDOR_COMPILER_RUNTIME_REQUIRED",
    ):
        check_only("vb6", "Option Explicit\n", tmp_path / "out")


@pytest.mark.parametrize("source_role", [False, True])
def test_vb6_vendor_harness_compiles_runs_and_reads_digestible_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_role: bool,
) -> None:
    function = _integer_add_ir().functions[0]
    emitted = emit(_integer_add_ir(), "vb6")
    toolchain = ExactToolchain(
        language="vb6",
        version="Microsoft Visual Basic 6.0 SP6 / test",
        executable=str(tmp_path / "VB6.EXE"),
        auxiliary=str(tmp_path / "MSVBVM60.DLL"),
        profile=("vb6-binding-evidence=GOVERNED_EXTERNAL_SELF_ATTESTED",),
        executable_sha256="a" * 64,
        auxiliary_sha256="b" * 64,
    )
    calls: list[list[str]] = []

    def run(
        command: list[str],
        cwd: Path,
        *,
        timeout: int = 600,
        executable_dirs: tuple[Path, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        del timeout, executable_dirs
        calls.append(command)
        if "/Make" in command:
            (cwd / "elmos-route-harness.exe").write_bytes(b"MZ-compiled")
        else:
            (cwd / "observations.tsv").write_text(
                "ELMOS_OBSERVATION\t0\ti64-dec\t5\n",
                encoding="ascii",
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(validation_module, "exact_toolchain", lambda language: toolchain)
    monkeypatch.setattr(validation_module, "_run", run)
    output = tmp_path / ("source" if source_role else "target")
    if source_role:
        subject = tmp_path / "Subject.bas"
        subject.write_text(emitted.content, encoding="ascii")
        report = validate_source(
            subject,
            "vb6",
            function,
            [{"args": [2, 3], "expected": 5}],
            output,
        )
        assert report["role"] == "source"
    else:
        report = validate(
            emitted,
            "vb6",
            function,
            [{"args": [2, 3], "expected": 5}],
            output,
        )

    assert report["status"] == "PASSED"
    assert report["observations"][0]["value"] == 5
    assert calls[0][0] == toolchain.executable
    assert calls[0][1:3] == ["/Make", "elmos-route-harness.vbp"]
    assert calls[1] == ["./elmos-route-harness.exe"]
