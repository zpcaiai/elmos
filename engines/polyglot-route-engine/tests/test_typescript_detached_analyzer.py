from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import elmos_polyglot_route.native as native
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.toolchains import (
    ExactToolchain,
    exact_toolchain,
    sanitized_subprocess_env,
    typescript_parser_receipt,
)

ENGINE_ROOT = Path(__file__).resolve().parents[1]
ANALYZER = ENGINE_ROOT / "native" / "typescript" / "analyzer.mjs"
SAFE_INTEGER_HELPER = (
    "function _elmosRequireSafeInteger(value: number): number {\n"
    "  if (!Number.isSafeInteger(value)) {\n"
    "    throw new RangeError(`ELMOS_INTEGER_NOT_SAFE:${value}`);\n"
    "  }\n"
    "  return Object.is(value, -0) ? 0 : value;\n"
    "}\n"
)
FINITE_NUMBER_HELPER = (
    "function _elmosRequireFiniteNumber(value: number): number {\n"
    '  if (typeof value !== "number" || !Number.isFinite(value)) {\n'
    '    throw new TypeError("ELMOS_NUMBER_NOT_FINITE");\n'
    "  }\n"
    "  return value;\n"
    "}\n"
)


def _source(name: str = "calculate") -> str:
    return f"export function {name}(left: number, right: number): number {{ return left + right; }}\n"


def _emitted_integer_to_number(name: str = "identity") -> str:
    return (
        SAFE_INTEGER_HELPER + FINITE_NUMBER_HELPER + f"export function {name}(value: number): number {{\n"
        "  value = _elmosRequireSafeInteger(value);\n"
        "  return _elmosRequireFiniteNumber(value);\n"
        "}\n"
    )


def _emitted_nested_integer() -> str:
    return (
        SAFE_INTEGER_HELPER + "export function sum3(a: number, b: number, c: number): number {\n"
        "  a = _elmosRequireSafeInteger(a);\n"
        "  b = _elmosRequireSafeInteger(b);\n"
        "  c = _elmosRequireSafeInteger(c);\n"
        "  return _elmosRequireSafeInteger("
        "_elmosRequireSafeInteger(_elmosRequireSafeInteger(a + b) + c));\n"
        "}\n"
    )


def _emitted_integer_arithmetic_to_number() -> str:
    return (
        SAFE_INTEGER_HELPER + FINITE_NUMBER_HELPER + "export function widenSum(left: number, right: number): number {\n"
        "  left = _elmosRequireSafeInteger(left);\n"
        "  right = _elmosRequireSafeInteger(right);\n"
        "  return _elmosRequireFiniteNumber(_elmosRequireSafeInteger(left + right));\n"
        "}\n"
    )


def _emitted_nested_number() -> str:
    return (
        FINITE_NUMBER_HELPER + "export function price(a: number, b: number, c: number): number {\n"
        "  return _elmosRequireFiniteNumber("
        "_elmosRequireFiniteNumber(_elmosRequireFiniteNumber(a + b) + c));\n"
        "}\n"
    )


def _emitted_mixed_branch() -> str:
    return (
        SAFE_INTEGER_HELPER + FINITE_NUMBER_HELPER + "export function mixed(count: number, price: number): number {\n"
        "  count = _elmosRequireSafeInteger(count);\n"
        "  if (count > 0) {\n"
        "    return _elmosRequireFiniteNumber(_elmosRequireFiniteNumber(count + price));\n"
        "  }\n"
        "  return _elmosRequireFiniteNumber(_elmosRequireFiniteNumber(price + 1.5));\n"
        "}\n"
    )


def _synthetic_receipt(parser: Path) -> dict[str, str | int]:
    metadata = parser.lstat()
    content = parser.read_bytes()
    return {
        "schema_version": 1,
        "path": str(parser),
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "mode": f"{metadata.st_mode & 0o7777:04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
        "compiler_root": str(parser.parent),
        "compiler_closure_sha256": "c" * 64,
        "compiler_closure_file_count": 6,
        "compiler_closure_bytes": len(content) + 5,
        "semantic_soundness": "NOT_RUN",
    }


def _synthetic_toolchain(receipt: dict[str, str | int]) -> ExactToolchain:
    return ExactToolchain(
        language="typescript",
        version="5.9.2 / Node 26.0.0",
        executable="/fixed/node",
        auxiliary="/fixed/tsc",
        profile=(
            "typescript-toolchain-closure-schema=v1",
            "typescript-language-version=5.9.2",
            f"typescript-package-root={receipt['compiler_root']}",
            f"typescript-closure-sha256={receipt['compiler_closure_sha256']}",
            f"typescript-closure-file-count={receipt['compiler_closure_file_count']}",
            f"typescript-closure-bytes={receipt['compiler_closure_bytes']}",
            f"typescript-parser-sha256={receipt['sha256']}",
            "typescript-compiler-runtime-semantic-soundness=NOT_RUN",
            f"node-closure-sha256={'d' * 64}",
            "node-closure-component-count=25",
            "node-closure-edge-count=49",
            "node-closure-system-edge-count=43",
        ),
        executable_sha256="a" * 64,
        auxiliary_sha256="b" * 64,
    )


def _synthetic_analyzer_inputs(tmp_path: Path) -> tuple[Path, Path, dict[str, str | int], ExactToolchain]:
    compiler_root = tmp_path / "compiler"
    compiler_root.mkdir(mode=0o700)
    parser = compiler_root / "typescript.js"
    parser.write_text("export const version = '5.9.2';\n", encoding="utf-8")
    parser.chmod(0o600)
    source = tmp_path / "source.ts"
    source.write_text(_source(), encoding="utf-8")
    receipt = _synthetic_receipt(parser)
    return source, parser, receipt, _synthetic_toolchain(receipt)


def test_typescript_analyzer_uses_exact_private_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _parser, receipt, toolchain = _synthetic_analyzer_inputs(tmp_path)
    monkeypatch.setattr(native, "typescript_parser_receipt", lambda: receipt)
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)

    def run(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
        assert command[0] == toolchain.executable
        assert command[1:] == [
            str(cwd / "assets" / "analyzer.mjs"),
            str(cwd / "assets" / "typescript.js"),
            str(cwd / "source" / source.name),
            "calculate",
        ]
        assert timeout == 120
        assert cwd.stat().st_mode & 0o777 == 0o700
        assert {item.name for item in cwd.iterdir()} == {"assets", "source"}
        assert {item.name for item in (cwd / "assets").iterdir()} == {"analyzer.mjs", "typescript.js"}
        assert {item.name for item in (cwd / "source").iterdir()} == {source.name}
        for path in (cwd / "assets").iterdir():
            assert path.stat().st_mode & 0o777 == 0o600
        assert (cwd / "source" / source.name).stat().st_mode & 0o777 == 0o600
        return {"analyzer_version": "5.9.2", "functions": [], "diagnostics": []}

    monkeypatch.setattr(native, "_run", run)
    result = native._run_trusted_typescript_analyzer(toolchain, source, "calculate")

    assert "typescript-closure=" + "c" * 64 in result["analyzer_version"]
    assert "node-closure=" + "d" * 64 in result["analyzer_version"]


@pytest.mark.parametrize(
    "tamper",
    [
        "snapshot-analyzer",
        "snapshot-parser",
        "snapshot-source",
        "snapshot-pathset",
        "live-analyzer",
        "live-source",
        "live-parser",
    ],
)
def test_typescript_analyzer_fails_closed_on_snapshot_or_live_input_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    source, parser, receipt, toolchain = _synthetic_analyzer_inputs(tmp_path)
    if tamper == "live-analyzer":
        analyzer = tmp_path / "analyzer.mjs"
        analyzer.write_bytes(ANALYZER.read_bytes())
        analyzer.chmod(0o600)
        monkeypatch.setattr(native, "_TYPESCRIPT_ANALYZER", analyzer)
        monkeypatch.setattr(native, "_TYPESCRIPT_ANALYZER_SHA256", hashlib.sha256(analyzer.read_bytes()).hexdigest())
        monkeypatch.setattr(native, "_TYPESCRIPT_ANALYZER_BYTES", analyzer.stat().st_size)
    monkeypatch.setattr(native, "typescript_parser_receipt", lambda: receipt)
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)

    def run(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
        if tamper.startswith("snapshot-") and tamper != "snapshot-pathset":
            relative = {
                "snapshot-analyzer": Path("assets/analyzer.mjs"),
                "snapshot-parser": Path("assets/typescript.js"),
                "snapshot-source": Path(f"source/{source.name}"),
            }[tamper]
            (cwd / relative).write_text("forged\n", encoding="utf-8")
        elif tamper == "snapshot-pathset":
            (cwd / "extra").write_text("forged\n", encoding="utf-8")
        elif tamper == "live-analyzer":
            native._TYPESCRIPT_ANALYZER.write_text("forged\n", encoding="utf-8")
        elif tamper == "live-source":
            source.write_text(_source("forged"), encoding="utf-8")
        else:
            parser.write_text("export const version = 'forged';\n", encoding="utf-8")
        return {"analyzer_version": "5.9.2"}

    monkeypatch.setattr(native, "_run", run)
    expected = (
        "TYPESCRIPT_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION"
        if tamper.startswith("snapshot-")
        else "TYPESCRIPT_ANALYZER_INPUT_CHANGED_DURING_EXECUTION"
    )
    with pytest.raises(RouteError, match=f"^{expected}$"):
        native._run_trusted_typescript_analyzer(toolchain, source, "calculate")


def test_typescript_analyzer_rejects_missing_analyzer_parser_and_symlink_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, parser, receipt, _toolchain = _synthetic_analyzer_inputs(tmp_path)
    missing = tmp_path / "missing-analyzer.mjs"
    monkeypatch.setattr(native, "_TYPESCRIPT_ANALYZER", missing)
    with pytest.raises(RouteError, match="^TYPESCRIPT_ANALYZER_SOURCE_UNSAFE$"):
        native._typescript_analyzer_inputs(source, receipt)

    monkeypatch.setattr(native, "_TYPESCRIPT_ANALYZER", ANALYZER)
    parser.unlink()
    with pytest.raises(RouteError, match="^TYPESCRIPT_ANALYZER_PARSER_INPUT_UNSAFE$"):
        native._typescript_analyzer_inputs(source, receipt)

    parser.write_text("export const version = '5.9.2';\n", encoding="utf-8")
    parser.chmod(0o600)
    receipt = _synthetic_receipt(parser)
    source.unlink()
    with pytest.raises(RouteError, match="^TYPESCRIPT_ANALYZER_SOURCE_INPUT_UNSAFE$"):
        native._typescript_analyzer_inputs(source, receipt)

    source.write_text(_source(), encoding="utf-8")
    symlink = tmp_path / "source-link.ts"
    symlink.symlink_to(source)
    with pytest.raises(RouteError, match="^TYPESCRIPT_ANALYZER_SOURCE_INPUT_UNSAFE$"):
        native._typescript_analyzer_inputs(symlink, receipt)


def test_typescript_emitted_guards_are_typed_per_arithmetic_node(tmp_path: Path) -> None:
    toolchain = exact_toolchain("typescript")
    receipt = typescript_parser_receipt()
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    home.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    env = sanitized_subprocess_env(
        home=home,
        temp_dir=scratch,
        executable_dirs=(Path(toolchain.executable).parent,),
    )

    def run(
        content: str,
        filename: str,
        selector: str,
        *,
        inventory: bool = False,
        emitted: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        source = tmp_path / filename
        source.write_text(content, encoding="utf-8")
        return subprocess.run(
            [
                toolchain.executable,
                str(ANALYZER),
                str(receipt["path"]),
                str(source),
                "--inventory" if inventory else selector,
                *([] if inventory or not emitted else ["--emitted-target"]),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

    valid_sources = {
        "integer-identity-widening.ts": (
            _emitted_integer_to_number(),
            "identity",
            ["integer"],
            "number",
        ),
        "nested-integer.ts": (_emitted_nested_integer(), "sum3", ["integer", "integer", "integer"], "integer"),
        "integer-arithmetic-widening.ts": (
            _emitted_integer_arithmetic_to_number(),
            "widenSum",
            ["integer", "integer"],
            "number",
        ),
        "nested-number.ts": (_emitted_nested_number(), "price", ["number", "number", "number"], "number"),
        "mixed-branch.ts": (_emitted_mixed_branch(), "mixed", ["integer", "number"], "number"),
    }
    for filename, (content, selector, parameter_types, return_type) in valid_sources.items():
        completed = run(content, filename, selector)
        assert completed.returncode == 0, completed.stderr
        lifted = json.loads(completed.stdout)["functions"][0]
        assert [item["type"] for item in lifted["parameters"]] == parameter_types
        assert lifted["return_type"] == return_type

    literal_sources = {
        "source-negative-integer.ts": (
            "export function negativeInteger(): number { return -7; }\n",
            "negativeInteger",
            -7,
        ),
        "source-negative-number.ts": (
            "export function negativeNumber(): number { return -1.5; }\n",
            "negativeNumber",
            -1.5,
        ),
        "emitted-negative-integer.ts": (
            SAFE_INTEGER_HELPER + "export function negativeInteger(): number { "
            "return _elmosRequireSafeInteger(-7); }\n",
            "negativeInteger",
            -7,
        ),
        "emitted-negative-number.ts": (
            FINITE_NUMBER_HELPER + "export function negativeNumber(): number { "
            "return _elmosRequireFiniteNumber(-1.5); }\n",
            "negativeNumber",
            -1.5,
        ),
        "emitted-negative-integer-arithmetic.ts": (
            SAFE_INTEGER_HELPER + "export function offset(value: number): number {\n"
            "  value = _elmosRequireSafeInteger(value);\n"
            "  return _elmosRequireSafeInteger(_elmosRequireSafeInteger(value + -2));\n"
            "}\n",
            "offset",
            None,
        ),
        "emitted-negative-number-arithmetic.ts": (
            FINITE_NUMBER_HELPER + "export function offset(value: number): number {\n"
            "  return _elmosRequireFiniteNumber("
            "_elmosRequireFiniteNumber(value + -1.5));\n"
            "}\n",
            "offset",
            None,
        ),
    }
    for filename, (content, selector, expected_literal) in literal_sources.items():
        completed = run(content, filename, selector, emitted=filename.startswith("emitted-"))
        assert completed.returncode == 0, completed.stderr
        lifted = json.loads(completed.stdout)["functions"][0]
        if expected_literal is not None:
            assert lifted["body"][0]["expression"] == {
                "kind": "literal",
                "value": expected_literal,
            }

    inventory = run(_emitted_nested_number(), "number-inventory.ts", "", inventory=True)
    assert inventory.returncode == 0, inventory.stderr
    finite_subject = next(
        item for item in json.loads(inventory.stdout)["subjects"] if item["name"] == "_elmosRequireFiniteNumber"
    )
    assert finite_subject["analyzable"] is True
    assert finite_subject["signature"] == {
        "parameters": [{"name": "value", "source_type": "number"}],
        "source_return_type": "number",
        "visibility": "internal",
        "storage": "file-scope",
    }

    invalid_sources = {
        "discarded.ts": (
            _emitted_integer_to_number().replace(
                "value = _elmosRequireSafeInteger(value);",
                "_elmosRequireSafeInteger(value);",
            ),
            "identity",
            "TYPESCRIPT_EMITTED_PARAMETER_GUARD_ASSIGNMENT_REQUIRED",
        ),
        "cross-assigned.ts": (
            _emitted_integer_to_number().replace(
                "value = _elmosRequireSafeInteger(value);",
                "value = _elmosRequireSafeInteger(other);",
            ),
            "identity",
            "TYPESCRIPT_EMITTED_PARAMETER_GUARD_ASSIGNMENT_INVALID",
        ),
        "inner-guard-removed.ts": (
            _emitted_nested_integer().replace(
                "_elmosRequireSafeInteger(_elmosRequireSafeInteger(a + b) + c)",
                "_elmosRequireSafeInteger((a + b) + c)",
            ),
            "sum3",
            "TYPESCRIPT_EMITTED_ARITHMETIC_GUARD_MISSING:+:integer",
        ),
        "number-inner-guard-removed.ts": (
            _emitted_nested_number().replace(
                "_elmosRequireFiniteNumber(_elmosRequireFiniteNumber(a + b) + c)",
                "_elmosRequireFiniteNumber((a + b) + c)",
            ),
            "price",
            "TYPESCRIPT_EMITTED_ARITHMETIC_GUARD_MISSING:+:number",
        ),
        "number-outer-guard-removed.ts": (
            FINITE_NUMBER_HELPER + "export function price(a: number, b: number): number { "
            "return _elmosRequireFiniteNumber(a + b); }\n",
            "price",
            "TYPESCRIPT_EMITTED_ARITHMETIC_GUARD_MISSING:+:number",
        ),
        "number-return-guard-missing.ts": (
            "export function widen(value: number): number { return value; }\n",
            "widen",
            "TYPESCRIPT_EMITTED_RETURN_GUARD_MISSING",
        ),
        "number-return-guard-type-mismatch.ts": (
            FINITE_NUMBER_HELPER + "export function invalid(value: string): number { "
            "return _elmosRequireFiniteNumber(value); }\n",
            "invalid",
            "TYPESCRIPT_EMITTED_GUARD_TYPE_MISMATCH:_elmosRequireFiniteNumber:string",
        ),
        "helper-source-tampered.ts": (
            _emitted_nested_number().replace("Number.isFinite(value)", "Number.isNaN(value)"),
            "price",
            "TYPESCRIPT_EMITTED_HELPER_SOURCE_MISMATCH:_elmosRequireFiniteNumber",
        ),
    }
    for name, (content, selector, expected_reason) in invalid_sources.items():
        completed = run(content, name, selector)
        assert completed.returncode != 0
        assert completed.stdout == ""
        assert expected_reason in completed.stderr

    invalid_literals = {
        "source-negative-zero.ts": (
            "export function negativeZero(): number { return -0.0; }\n",
            "negativeZero",
            "TYPESCRIPT_NEGATIVE_ZERO_LITERAL_UNSUPPORTED",
            False,
        ),
        "source-unary-non-literal.ts": (
            "export function negate(value: number): number { return -value; }\n",
            "negate",
            "TYPESCRIPT_UNARY_MINUS_LITERAL_REQUIRED",
            False,
        ),
        "emitted-negative-zero.ts": (
            SAFE_INTEGER_HELPER + "export function negativeZero(): number { return _elmosRequireSafeInteger(-0); }\n",
            "negativeZero",
            "TYPESCRIPT_NEGATIVE_ZERO_LITERAL_UNSUPPORTED",
            True,
        ),
        "emitted-unary-non-literal.ts": (
            FINITE_NUMBER_HELPER + "export function negate(value: number): number { "
            "return _elmosRequireFiniteNumber(-value); }\n",
            "negate",
            "TYPESCRIPT_UNARY_MINUS_LITERAL_REQUIRED",
            True,
        ),
    }
    for filename, (content, selector, expected_reason, emitted) in invalid_literals.items():
        completed = run(content, filename, selector, emitted=emitted)
        assert completed.returncode != 0
        assert completed.stdout == ""
        assert expected_reason in completed.stderr


def test_detached_captured_typescript_source_inventory_and_target_relift(
    tmp_path: Path,
) -> None:
    captured = tmp_path / "captured" / "engines" / "polyglot-route-engine"
    captured_src = captured / "src"
    captured_native = captured / "native" / "typescript"
    shutil.copytree(
        ENGINE_ROOT / "src" / "elmos_polyglot_route",
        captured_src / "elmos_polyglot_route",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(ENGINE_ROOT / "native" / "typescript", captured_native)
    assert not (tmp_path / "captured" / "engines" / "frontend-client-engine").exists()

    source = tmp_path / "source.ts"
    target = tmp_path / "target.ts"
    source.write_text(_source(), encoding="utf-8")
    target.write_text(_emitted_integer_to_number(), encoding="utf-8")
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    home.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "TMPDIR": str(scratch),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "PYTHONPATH": str(captured_src),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    script = """
import json
from pathlib import Path
from elmos_polyglot_route import native

source = Path(__import__('sys').argv[1])
target = Path(__import__('sys').argv[2])
inventory = native.inventory_module(source, 'typescript')
named = native.analyze(source, 'typescript', 'calculate')
relift = native.analyze(target, 'typescript', 'identity', emitted_target=True)
print(json.dumps({
    'native_file': native.__file__,
    'inventory_status': inventory['enumeration_status'],
    'inventory_names': [item['name'] for item in inventory['subjects']],
    'inventory_version': inventory['analyzer_version'],
    'named_parameter_types': [item.type for item in named.functions[0].parameters],
    'named_return_type': named.functions[0].return_type,
    'relift_parameter_types': [item.type for item in relift.functions[0].parameters],
    'relift_return_type': relift.functions[0].return_type,
    'relift_version': relift.analyzer_version,
}, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(source), str(target)],
        cwd=captured,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert Path(result["native_file"]).is_relative_to(captured_src)
    assert result["inventory_status"] == "PASSED"
    assert "calculate" in result["inventory_names"]
    assert result["named_parameter_types"] == ["number", "number"]
    assert result["named_return_type"] == "number"
    assert result["relift_parameter_types"] == ["integer"]
    assert result["relift_return_type"] == "number"
    for key in ("inventory_version", "relift_version"):
        assert "typescript-parser=" in result[key]
        assert "typescript-closure=" in result[key]
        assert "node-closure=" in result[key]
