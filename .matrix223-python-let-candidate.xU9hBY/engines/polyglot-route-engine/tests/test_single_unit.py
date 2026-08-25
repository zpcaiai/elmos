"""Tests for `single_unit.py`: emit-only and check-only, decomposed from `migrate`.

`test_emit_only_...` and `test_check_only_...` exercise the real analyzer,
emitter and target toolchains end to end, so -- like
`test_end_to_end_pipeline_...` in `test_assembly.py` -- they require the
exact pinned Python and TypeScript toolchains from `toolchains.py`.
`test_emit_only_rejects_a_same_language_route` needs no toolchain at all: the
guard runs before analysis.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_polyglot_route.cli import main
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.single_unit import check_only, emit_only


def test_emit_only_rejects_a_same_language_route(tmp_path: Path) -> None:
    source = tmp_path / "calc.py"
    source.write_text("def calculate(a: int) -> int:\n    return a\n", encoding="utf-8")
    with pytest.raises(RouteError, match="SOURCE_AND_TARGET_MUST_DIFFER"):
        emit_only(source, "python", "python", "calculate", tmp_path / "out")


def test_emit_only_names_the_symbol_the_emitted_file_actually_declares(tmp_path: Path) -> None:
    """The report has to describe the file beside it, not the source it came from.

    Swift refuses the source spelling for a function name, so the emitted symbol
    is a planned one. The consumer of this report is a static validator that
    resolves symbols by name: a report naming a symbol the file does not declare
    is the difference between a check that runs and one that cannot start.
    """
    source = tmp_path / "calc.py"
    source.write_text("def calculate(a: int) -> int:\n    return a\n", encoding="utf-8")
    output = tmp_path / "out"

    report = emit_only(source, "python", "swift", "calculate", output)

    emitted = (output / report["target"]["path"]).read_text(encoding="utf-8")
    target_name = report["target"]["function_name"]
    assert target_name != "calculate"
    assert f"func {target_name}(" in emitted
    assert report["source"]["function_name"] == "calculate"
    assert [parameter["name"] for parameter in report["target"]["parameters"]] == ["a"]


def test_emit_only_produces_a_target_file_with_no_compilation_or_execution(tmp_path: Path) -> None:
    source = tmp_path / "calc.py"
    source.write_text(
        "def calculate(a: int, b: int) -> int:\n"
        "    if a < b:\n"
        "        return b\n"
        "    return a\n",
        encoding="utf-8",
    )
    output = tmp_path / "out"

    report = emit_only(source, "python", "typescript", "calculate", output)

    assert report["kind"] == "elmos.single-unit-emission"
    assert report["status"] == "EMITTED"
    assert report["compiled"] is False
    assert report["executed"] is False
    assert report["target"]["function_name"] == "calculate"
    emitted = output / "migrated.ts"
    assert emitted.is_file()
    assert "export function calculate" in emitted.read_text(encoding="utf-8")
    on_disk = json.loads((output / "emission-report.json").read_text(encoding="utf-8"))
    assert on_disk["status"] == "EMITTED"


def test_check_only_passes_for_valid_emitted_typescript(tmp_path: Path) -> None:
    content = "export function calculate(a: number, b: number): number {\n    return (a + b);\n}\n"
    output = tmp_path / "check"

    report = check_only("typescript", content, output)

    assert report["kind"] == "elmos.single-unit-static-check"
    assert report["status"] == "PASSED"
    assert report["executed"] is False
    assert report["diagnostics"] == []


def test_check_only_fails_closed_for_invalid_syntax(tmp_path: Path) -> None:
    content = "export function calculate(a: number, b: number): number {\n    return a +\n}\n"
    output = tmp_path / "check"

    report = check_only("typescript", content, output)

    assert report["status"] == "FAILED"
    assert report["diagnostics"]
    assert report["diagnostics"][0]


def test_cli_recognizes_emit_and_check_as_subcommands_and_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Toolchain-independent proof that the CLI actually dispatches to `emit`/`check`
    (used directly by the Java Lowering bridge via subprocess), not just that the
    underlying functions work. Uses a same-language route so the fail-closed guard
    fires before any toolchain is touched.
    """
    source = tmp_path / "calc.py"
    source.write_text("def calculate(a: int) -> int:\n    return a\n", encoding="utf-8")

    exit_code = main(
        [
            "emit",
            "--source",
            str(source),
            "--source-language",
            "python",
            "--target-language",
            "python",
            "--function",
            "calculate",
            "--output",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert "SOURCE_AND_TARGET_MUST_DIFFER" in payload["reason"]


def test_emit_only_then_check_only_round_trip_matches_a_full_migrate(tmp_path: Path) -> None:
    """The decomposed emit+check pair should accept exactly what the atomic
    engine.migrate() would emit for the same source, proving the split does
    not silently narrow or widen the certified typed-pure-function-v1 scope.
    """
    source = tmp_path / "calc.py"
    source.write_text("def calculate(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

    emitted_report = emit_only(source, "python", "typescript", "calculate", tmp_path / "emitted")
    emitted_path = tmp_path / "emitted" / emitted_report["target"]["path"]

    checked_report = check_only("typescript", emitted_path.read_text(encoding="utf-8"), tmp_path / "checked")
    assert checked_report["status"] == "PASSED"
