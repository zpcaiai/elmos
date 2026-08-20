"""Single-declaration emit-only and check-only entry points, no behavior cases required.

`engine.migrate()` is atomic: analyze -> emit -> validate-against-behavior-cases,
in one call, and `validate()` in `validation.py` always requires an independent
behavior-case corpus. That fits this engine's own repository pipeline, but it
does not fit every caller's shape. `modules/lowering` (the Java UIR-based
lowering pipeline) calls emission and static validation as two separate steps
with no behavior-case corpus available at all -- its `StaticValidator`
interface is deliberately syntax/symbol/type-only, not behavioral.

This module exposes the same real, already-certified analyzer and emitter
(`native.analyze`, `emitter.emit`) as two decomposed primitives instead of
reinventing translation logic:

- `emit_only` runs analyze -> emit and stops. No compilation, no execution, no
  behavior cases. Requires only the *source* language's exact toolchain
  (`native.analyze` uses it to parse); needs nothing from the target toolchain.
- `check_only` compiles/type-checks a single already-emitted file with no
  harness and no execution -- a real static check using the *target*
  language's exact toolchain, deliberately narrower than `validation.validate`.

Both fail closed exactly like the rest of this engine: unsupported constructs,
missing/mismatched toolchains, or more than one function in scope raise
`RouteError` rather than returning a degraded success.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .emitter import emit
from .identifier_hygiene import plan_identifiers, target_ir_view
from .models import Language, RouteError
from .native import analyze
from .toolchains import exact_toolchain

SCHEMA_VERSION = "1.0.0"

_SOURCE_EXTENSION: dict[Language, str] = {
    "java": ".java",
    "python": ".py",
    "csharp": ".cs",
    "typescript": ".ts",
}


def emit_only(
    source: Path,
    source_language: Language,
    target_language: Language,
    function_name: str,
    output: Path,
) -> dict[str, Any]:
    """Analyze one real source function and emit its target-language translation.

    Unlike `engine.migrate`, this performs no compilation and no behavior-case
    execution -- it is the emission half only, for callers (like the Lowering
    bridge) that run static validation as a separate step against their own
    already-generated skeleton.
    """
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    ir = analyze(source, source_language, function_name)
    if len(ir.functions) != 1:
        raise RouteError("EXACTLY_ONE_FUNCTION_REQUIRED")
    # The identifier plan is built here rather than left to `emit` so the report
    # can describe the file that was actually written. Several targets refuse the
    # source spelling outright -- a function name is rejected for cpp and objc
    # because their global symbol namespace is open, and for java, csharp and
    # swift because of the runtime function namespace -- so the emitted symbol is
    # frequently not the one that was analyzed. `engine.migrate` already works
    # this way; this entry point reported the source names instead, which made
    # the report disagree with the file next to it. Its consumer is a static
    # validator that resolves symbols by name, so that disagreement was the
    # difference between a symbol it could find and one it could not.
    identifier_plan = plan_identifiers(ir, target_language)
    source_function = ir.functions[0]
    function = target_ir_view(ir, identifier_plan).functions[0]
    emitted = emit(ir, target_language, identifier_plan=identifier_plan)
    output.mkdir(parents=True, exist_ok=True)
    target_path = output / emitted.relative_path
    target_path.write_text(emitted.content, encoding="utf-8")
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.single-unit-emission",
        "status": "EMITTED",
        "scope": "typed-pure-function-v1",
        "source": {
            "path": source.name,
            "language": source_language,
            "analyzer": ir.analyzer,
            "analyzer_version": ir.analyzer_version,
            "function_name": source_function.name,
        },
        "target": {
            "path": emitted.relative_path,
            "language": target_language,
            "function_name": function.name,
            "parameters": [parameter.to_mapping() for parameter in function.parameters],
            "return_type": function.return_type,
        },
        "compiled": False,
        "executed": False,
        "limitations": [
            "This is emission only: no compilation and no behavior-case execution occurred.",
            "Use check_only (or a full assembled-project build) to prove the emitted code compiles.",
        ],
    }
    (output / "emission-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _run(command: list[str], cwd: Path, *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["NO_COLOR"] = "1"
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise RouteError(f"TARGET_VALIDATION_TIMEOUT:{command[0]}") from error


def check_only(target_language: Language, content: str, output: Path) -> dict[str, Any]:
    """Compile/type-check one emitted file alone: no harness, no execution.

    This is the real static check that backs a `StaticValidator` bridge: it
    proves syntax, symbol resolution and typing using the target language's
    own exact-pinned compiler, and nothing more. A behavior-case-driven
    caller should use `validation.validate` instead; this function does not
    run the emitted code.
    """
    toolchain = exact_toolchain(target_language)
    output.mkdir(parents=True, exist_ok=True)
    diagnostics: list[str] = []

    if target_language == "java":
        (output / "Migrated.java").write_text(content, encoding="utf-8")
        assert toolchain.auxiliary is not None
        completed = _run([toolchain.auxiliary, "Migrated.java"], output)
    elif target_language == "python":
        (output / "migrated.py").write_text(content, encoding="utf-8")
        completed = _run([toolchain.executable, "-m", "py_compile", "migrated.py"], output)
    elif target_language == "csharp":
        (output / "Migrated.cs").write_text(content, encoding="utf-8")
        (output / "StaticCheck.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            "<TargetFramework>net10.0</TargetFramework>"
            "<ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable>"
            "<TreatWarningsAsErrors>true</TreatWarningsAsErrors>"
            "</PropertyGroup></Project>\n",
            encoding="utf-8",
        )
        completed = _run([toolchain.executable, "build", "StaticCheck.csproj", "-c", "Release"], output)
    else:
        (output / "migrated.ts").write_text(content, encoding="utf-8")
        (output / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2022",
                        "module": "NodeNext",
                        "moduleResolution": "NodeNext",
                        "strict": True,
                        "noEmit": True,
                    },
                    "include": ["*.ts"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        assert toolchain.auxiliary is not None
        completed = _run([toolchain.auxiliary, "-p", "tsconfig.json"], output)

    passed = completed.returncode == 0
    if not passed:
        diagnostics.append((completed.stderr or completed.stdout).strip()[-4_000:])

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.single-unit-static-check",
        "status": "PASSED" if passed else "FAILED",
        "language": target_language,
        "toolchain_version": toolchain.version,
        "diagnostics": diagnostics,
        "executed": False,
    }
    (output / "check-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
