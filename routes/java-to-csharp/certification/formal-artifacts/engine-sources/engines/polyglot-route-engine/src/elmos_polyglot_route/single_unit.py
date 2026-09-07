"""Single-declaration emit-only and check-only entry points, no behavior cases required.

`engine.migrate()` is atomic: analyze -> emit -> validate-against-behavior-cases,
in one call, and `validate()` in `validation.py` always requires an independent
behavior-case corpus. That fits this engine's own repository pipeline, but it
does not fit every caller's shape. `modules/lowering` (the Java UIR-based
lowering pipeline) calls emission and static validation as two separate steps
with no behavior-case corpus available at all -- its `StaticValidator`
interface is deliberately syntax/symbol/type-only, not behavioral.

This module exposes the same real, bounded local analyzer and emitter
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
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .emitter import emit
from .identifier_hygiene import plan_identifiers, target_ir_view
from .models import SUPPORTED_LANGUAGES, Language, RouteError
from .source_analyzer import analyze
from .toolchains import (
    ExactToolchain,
    exact_toolchain,
    flutter_build_command,
    sanitized_subprocess_env,
    verify_flutter_build_toolchain,
)
from .validation import (
    _apple_sdk,
    _bounded_process_diagnostic,
    _php_command,
    _toolchain_executable_dirs,
)

SCHEMA_VERSION = "1.0.0"

_SOURCE_EXTENSION: dict[Language, str] = {
    "java": ".java",
    "python": ".py",
    "csharp": ".cs",
    "typescript": ".ts",
    "go": ".go",
    "rust": ".rs",
    "cpp": ".cpp",
    "objc": ".m",
    "swift": ".swift",
    "php": ".php",
    "kotlin": ".kt",
    "react": ".tsx",
    "flutter": ".dart",
    "javascript": ".mjs",
}

_TARGET_FILE: dict[Language, str] = {
    "java": "Migrated.java",
    "python": "migrated.py",
    "csharp": "Migrated.cs",
    "typescript": "migrated.ts",
    "go": "migrated.go",
    "rust": "migrated.rs",
    "cpp": "migrated.cpp",
    "objc": "migrated.m",
    "swift": "migrated.swift",
    "php": "migrated.php",
    "kotlin": "Migrated.kt",
    "react": "migrated.tsx",
    "flutter": "migrated.dart",
    "javascript": "migrated.mjs",
}

_AUXILIARY_COMPILER_LANGUAGES: frozenset[Language] = frozenset(
    {"java", "typescript", "react", "flutter"}
)


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
    if (
        source_language not in SUPPORTED_LANGUAGES
        or target_language not in SUPPORTED_LANGUAGES
    ):
        raise RouteError("UNSUPPORTED_LANGUAGE")
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


def _required_auxiliary(toolchain: ExactToolchain) -> str:
    if toolchain.language not in _AUXILIARY_COMPILER_LANGUAGES:
        raise RouteError(f"STATIC_CHECK_AUXILIARY_NOT_APPLICABLE:{toolchain.language}")
    if toolchain.auxiliary is None:
        raise RouteError(f"STATIC_CHECK_AUXILIARY_REQUIRED:{toolchain.language}")
    return toolchain.auxiliary


def _run(
    command: list[str],
    cwd: Path,
    *,
    toolchain: ExactToolchain,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run one static compiler in an isolated environment and process group.

    A non-zero compiler result is returned to ``check_only`` so it can produce
    an explicit FAILED report.  Failure to start, timeout, or cleanup failure is
    not a source diagnostic and raises instead.  The fresh session prevents a
    compiler wrapper from leaving a detached helper behind after this bounded
    static check returns.
    """

    if not command or not command[0]:
        raise RouteError("STATIC_CHECK_COMMAND_INVALID")
    executable = Path(command[0])
    executable = executable if executable.is_absolute() else (cwd / executable)
    process: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="elmos-single-unit-check-") as temporary:
            root = Path(temporary)
            home = root / "home"
            scratch = root / "tmp"
            cache = home / ".cache"
            go_cache = cache / "go-build"
            go_path = home / "go"
            nuget_cache = cache / "nuget"
            pub_cache = cache / "dart-pub"
            for directory in (
                home,
                scratch,
                cache,
                go_cache,
                go_path,
                nuget_cache,
                pub_cache,
            ):
                directory.mkdir(mode=0o700)
            environment = sanitized_subprocess_env(
                home=home,
                temp_dir=scratch,
                executable_dirs=(
                    executable.resolve().parent,
                    *_toolchain_executable_dirs(toolchain),
                ),
            )
            environment.update(
                {
                    "DOTNET_CLI_HOME": str(home.resolve()),
                    "NUGET_PACKAGES": str(nuget_cache.resolve()),
                    "GOCACHE": str(go_cache.resolve()),
                    "GOMODCACHE": str((go_path / "pkg" / "mod").resolve()),
                    "GOPATH": str(go_path.resolve()),
                    "PUB_CACHE": str(pub_cache.resolve()),
                    "DART_SUPPRESS_ANALYTICS": "true",
                }
            )
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                start_new_session=os.name == "posix",
                env=environment,
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                else:
                    process.terminate()
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    if os.name == "posix":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        process.kill()
                    process.communicate()
                raise RouteError(
                    f"STATIC_CHECK_PROCESS_FAILED:{Path(command[0]).name}:timeout"
                ) from error
            finally:
                if os.name == "posix" and process is not None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            return subprocess.CompletedProcess(
                command,
                process.returncode,
                stdout,
                stderr,
            )
    except OSError as error:
        raise RouteError(
            f"STATIC_CHECK_PROCESS_FAILED:{Path(command[0]).name}:process"
        ) from error


def _write_typescript_static_project(output: Path, *, react: bool) -> None:
    compiler_options: dict[str, object] = {
        "target": "ES2022",
        "module": "NodeNext",
        "moduleResolution": "NodeNext",
        "strict": True,
        "noEmit": True,
    }
    if react:
        compiler_options.update({"jsx": "react-jsx", "types": []})
    (output / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": compiler_options,
                "files": ["migrated.tsx" if react else "migrated.ts"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_flutter_static_project(output: Path) -> None:
    (output / "pubspec.yaml").write_text(
        "name: elmos_single_unit_flutter_check\n"
        "version: 0.0.0\n"
        "publish_to: none\n"
        "environment:\n"
        "  sdk: '>=3.12.1 <3.13.0'\n"
        "dependencies: {}\n",
        encoding="utf-8",
    )
    (output / "analysis_options.yaml").write_text(
        "analyzer:\n"
        "  language:\n"
        "    strict-casts: true\n"
        "    strict-inference: true\n"
        "    strict-raw-types: true\n",
        encoding="utf-8",
    )
    package_directory = output / ".dart_tool"
    package_directory.mkdir(parents=True, exist_ok=True)
    (package_directory / "package_config.json").write_text(
        json.dumps(
            {
                "configVersion": 2,
                "packages": [
                    {
                        "name": "elmos_single_unit_flutter_check",
                        "rootUri": "../",
                        "packageUri": "./",
                        "languageVersion": "3.12",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _static_check_command(
    target_language: Language,
    content: str,
    output: Path,
    toolchain: ExactToolchain,
) -> list[str]:
    try:
        target_name = _TARGET_FILE[target_language]
    except KeyError as error:
        raise RouteError(f"STATIC_CHECK_LANGUAGE_UNSUPPORTED:{target_language}") from error
    (output / target_name).write_text(content, encoding="utf-8")

    if target_language == "java":
        (output / "classes").mkdir(exist_ok=True)
        return [
            _required_auxiliary(toolchain),
            "-Xlint:all",
            "-Werror",
            "-d",
            "classes",
            target_name,
        ]
    if target_language == "python":
        return [toolchain.executable, "-m", "py_compile", target_name]
    if target_language == "csharp":
        (output / "StaticCheck.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            "<TargetFramework>net10.0</TargetFramework>"
            "<ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable>"
            "<TreatWarningsAsErrors>true</TreatWarningsAsErrors>"
            "<EnableDefaultCompileItems>false</EnableDefaultCompileItems>"
            "</PropertyGroup><ItemGroup><Compile Include=\"Migrated.cs\" />"
            "</ItemGroup></Project>\n",
            encoding="utf-8",
        )
        return [
            toolchain.executable,
            "build",
            "StaticCheck.csproj",
            "-c",
            "Release",
            "--nologo",
        ]
    if target_language in {"typescript", "react"}:
        _write_typescript_static_project(output, react=target_language == "react")
        return [
            _required_auxiliary(toolchain),
            "-p",
            "tsconfig.json",
            "--pretty",
            "false",
        ]
    if target_language == "javascript":
        return [toolchain.executable, "--check", target_name]
    if target_language == "go":
        return [
            toolchain.executable,
            "build",
            "-buildmode=archive",
            "-buildvcs=false",
            "-trimpath",
            "-o",
            "migrated.a",
            target_name,
        ]
    if target_language == "rust":
        return [
            toolchain.executable,
            "--edition=2021",
            "-D",
            "warnings",
            "--crate-type",
            "lib",
            "-o",
            "libmigrated.rlib",
            target_name,
        ]
    if target_language == "cpp":
        return [
            toolchain.executable,
            "-std=c++20",
            "-isysroot",
            _apple_sdk(toolchain.profile),
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fsyntax-only",
            target_name,
        ]
    if target_language == "objc":
        return [
            toolchain.executable,
            "-x",
            "objective-c",
            "-std=c17",
            "-isysroot",
            _apple_sdk(toolchain.profile),
            "-fobjc-arc",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fsyntax-only",
            target_name,
        ]
    if target_language == "swift":
        return [
            toolchain.executable,
            "-swift-version",
            "6",
            "-sdk",
            _apple_sdk(toolchain.profile),
            "-warnings-as-errors",
            "-parse-as-library",
            "-typecheck",
            target_name,
        ]
    if target_language == "php":
        return _php_command(toolchain, "-l", target_name)
    if target_language == "kotlin":
        (output / "classes").mkdir(exist_ok=True)
        return [
            toolchain.executable,
            "-Werror",
            "-language-version",
            "2.2",
            "-api-version",
            "2.2",
            "-jvm-target",
            "21",
            "-d",
            "classes",
            target_name,
        ]
    if target_language == "flutter":
        dart = _required_auxiliary(toolchain)
        _write_flutter_static_project(output)
        return flutter_build_command(
            toolchain,
            "--suppress-analytics",
            "analyze",
            "--format=json",
            "--fatal-infos",
            "--fatal-warnings",
            "--packages=.dart_tool/package_config.json",
            "--sdk-path=" + str(Path(dart).resolve().parent.parent),
            target_name,
        )
    raise RouteError(f"STATIC_CHECK_LANGUAGE_UNSUPPORTED:{target_language}")


def check_only(target_language: Language, content: str, output: Path) -> dict[str, Any]:
    """Compile/type-check one emitted file alone: no harness, no execution.

    This is the real static check that backs a `StaticValidator` bridge: it
    proves syntax, symbol resolution and typing using the target language's
    own exact-pinned compiler, and nothing more. A behavior-case-driven
    caller should use `validation.validate` instead; this function does not
    run the emitted code.
    """
    if target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_LANGUAGE")
    toolchain = exact_toolchain(target_language)
    output.mkdir(parents=True, exist_ok=True)
    diagnostics: list[str] = []
    command = _static_check_command(target_language, content, output, toolchain)
    flutter_receipt = (
        verify_flutter_build_toolchain(toolchain)
        if target_language == "flutter"
        else None
    )
    completed = _run(command, output, toolchain=toolchain)

    passed = completed.returncode == 0
    if target_language == "flutter":
        receipt_after = verify_flutter_build_toolchain(toolchain)
        if receipt_after != flutter_receipt:
            raise RouteError("STATIC_CHECK_FLUTTER_BUILD_TOOLCHAIN_CHANGED")
        try:
            analyzer_result = json.loads(completed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RouteError("STATIC_CHECK_FLUTTER_ANALYZER_OUTPUT_INVALID") from error
        analyzer_diagnostics = (
            analyzer_result.get("diagnostics")
            if isinstance(analyzer_result, dict) and analyzer_result.get("version") == 1
            else None
        )
        if not isinstance(analyzer_diagnostics, list):
            raise RouteError("STATIC_CHECK_FLUTTER_ANALYZER_OUTPUT_INVALID")
        if analyzer_diagnostics:
            passed = False
            diagnostics.extend(
                json.dumps(item, ensure_ascii=True, sort_keys=True)[-1_000:]
                for item in analyzer_diagnostics[:20]
            )
    if not passed:
        diagnostics.extend(
            [
                "stdout=" + _bounded_process_diagnostic(completed.stdout, cwd=output),
                "stderr=" + _bounded_process_diagnostic(completed.stderr, cwd=output),
            ]
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.single-unit-static-check",
        "status": "PASSED" if passed else "FAILED",
        "check_scope": "syntax-symbol-type-only",
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
