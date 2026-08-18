from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .emitter import EmittedFile
from .models import Function, Language, RouteError
from .toolchains import exact_toolchain

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _run(
    command: list[str],
    cwd: Path,
    *,
    timeout: int = 180,
    failure_code: str = "TARGET_VALIDATION_FAILED",
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["NO_COLOR"] = "1"
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        code = "SOURCE_VALIDATION_TIMEOUT" if failure_code.startswith("SOURCE_") else "TARGET_VALIDATION_TIMEOUT"
        raise RouteError(f"{code}:{command[0]}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-4_000:]
        raise RouteError(f"{failure_code}:{command[0]}:{detail}")
    return completed


def _argument(value: object, language: Language) -> str:
    if isinstance(value, bool):
        if language == "python":
            return "True" if value else "False"
        if language == "objc":
            return "YES" if value else "NO"
        return "true" if value else "false"
    if isinstance(value, str):
        encoded = json.dumps(value, ensure_ascii=False)
        if language == "objc":
            return f"@{encoded}"
        if language == "rust":
            return f"{encoded}.to_string()"
        return encoded
    return str(value)


def _expected(value: object, language: Language) -> str:
    return _argument(value, language)


def _java_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "java") for value in case["args"])
        expected = _expected(case["expected"], "java")
        call = f"Migrated.{function.name}({args})"
        # `!=` on String is a reference comparison in Java, so a correct
        # string-returning route could still be reported as a behaviour
        # failure (or, with interned literals, a wrong one reported as a
        # pass). Objects.equals is the value comparison the other three
        # harnesses already perform.
        condition = (
            f"!java.util.Objects.equals({call}, {expected})"
            if function.return_type == "string"
            else f"{call} != {expected}"
        )
        checks.append(f'        if ({condition}) throw new AssertionError("case {index}");')
    return (
        "public final class RouteHarness {\n"
        "    public static void main(String[] args) {\n" + "\n".join(checks) + "\n    }\n}\n"
    )


def _csharp_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "csharp") for value in case["args"])
        expected = _expected(case["expected"], "csharp")
        checks.append(f'if (Migrated.{function.name}({args}) != {expected}) throw new Exception("case {index}");')
    return "\n".join(checks) + "\n"


def _python_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks = []
    for case in cases:
        args = ", ".join(_argument(value, "python") for value in case["args"])
        checks.append(f"assert migrated.{function.name}({args}) == {_expected(case['expected'], 'python')}")
    return "import migrated\n" + "\n".join(checks) + "\n"


def _typescript_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "typescript") for value in case["args"])
        expected = _expected(case["expected"], "typescript")
        # Built from the function name directly. An earlier revision templated
        # the literal name `calculate` and then string-replaced it, which also
        # rewrote any occurrence of "calculate" inside a string argument or
        # expected value -- silently changing what the behaviour case asserts.
        checks.append(f'if ({function.name}({args}) !== {expected}) throw new Error("case {index}");')
    return "import { " + function.name + ' } from "./migrated.js";\n' + "\n".join(checks) + "\n"


def _cpp_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "cpp") for value in case["args"])
        expected = _expected(case["expected"], "cpp")
        checks.append(f"    if ({function.name}({args}) != {expected}) return {index + 1};")
    return '#include "migrated.cpp"\n\nint main() {\n' + "\n".join(checks) + "\n    return 0;\n}\n"


def _objc_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "objc") for value in case["args"])
        expected = _expected(case["expected"], "objc")
        # NSString is a pointer, so the harness compares by value too --
        # the same reason the emitter rewrites `==` on NSString.
        condition = (
            f"![{function.name}({args}) isEqualToString:{expected}]"
            if function.return_type == "string"
            else f"{function.name}({args}) != {expected}"
        )
        checks.append(f"    if ({condition}) return {index + 1};")
    return (
        '#import <Foundation/Foundation.h>\n#import "migrated.m"\n\n'
        "int main() {\n" + "\n".join(checks) + "\n    return 0;\n}\n"
    )


def _swift_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "swift") for value in case["args"])
        expected = _expected(case["expected"], "swift")
        checks.append(f"if {function.name}({args}) != {expected} {{ exit({index + 1}) }}")
    return "import Foundation\n\n" + "\n".join(checks) + "\n"


def _go_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "go") for value in case["args"])
        expected = _expected(case["expected"], "go")
        checks.append(f'    if {function.name}({args}) != {expected} {{ panic("case {index}") }}')
    return "package main\n\nfunc main() {\n" + "\n".join(checks) + "\n}\n"


def _rust_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks = []
    for index, case in enumerate(cases):
        rendered_args = []
        for value, parameter in zip(case["args"], function.parameters, strict=True):
            if parameter.type == "number" and isinstance(value, int) and not isinstance(value, bool):
                rendered_args.append(f"{value}.0")
            else:
                rendered_args.append(_argument(value, "rust"))
        args = ", ".join(rendered_args)
        expected_value = case["expected"]
        expected = (
            f"{expected_value}.0"
            if (
                function.return_type == "number"
                and isinstance(expected_value, int)
                and not isinstance(expected_value, bool)
            )
            else _expected(expected_value, "rust")
        )
        checks.append(f'    assert!({function.name}({args}) == {expected}, "case {index}");')
    return 'include!("migrated.rs");\n\nfn main() {\n' + "\n".join(checks) + "\n}\n"


def _extract_python_function(source: str, function_name: str) -> str:
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise RouteError("SOURCE_VALIDATION_EXTRACTION_FAILED") from error
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function_name:
            start = min([node.lineno, *(item.lineno for item in node.decorator_list)]) - 1
            end = node.end_lineno or node.lineno
            return "".join(lines[start:end])
    raise RouteError("SOURCE_VALIDATION_EXTRACTION_FAILED")


def _extract_braced_function(source: str, function_name: str) -> str:
    matches = list(re.finditer(rf"(?<![A-Za-z0-9_$]){re.escape(function_name)}\s*\(", source))
    if not matches:
        raise RouteError("SOURCE_VALIDATION_EXTRACTION_FAILED")
    match = matches[0]
    start = source.rfind("\n", 0, match.start()) + 1
    opening = source.find("{", match.end())
    if opening < 0:
        raise RouteError("SOURCE_VALIDATION_EXTRACTION_FAILED")
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening
    while index < len(source):
        character = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if character == "\n":
                line_comment = False
        elif block_comment:
            if character == "*" and following == "/":
                block_comment = False
                index += 1
        elif quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character == "/" and following == "/":
            line_comment = True
            index += 1
        elif character == "/" and following == "*":
            block_comment = True
            index += 1
        elif character in {'"', "'"}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
        index += 1
    raise RouteError("SOURCE_VALIDATION_EXTRACTION_FAILED")


def _source_subject(source: Path, language: Language, function: Function) -> EmittedFile:
    content = source.read_text(encoding="utf-8")
    extracted = (
        _extract_python_function(content, function.name)
        if language == "python"
        else _extract_braced_function(content, function.name)
    )
    if language == "python":
        return EmittedFile("migrated.py", extracted.rstrip() + "\n")
    if language == "java":
        return EmittedFile("Migrated.java", f"public final class Migrated {{\n{extracted}\n}}\n")
    if language == "csharp":
        return EmittedFile("Migrated.cs", f"public static class Migrated\n{{\n{extracted}\n}}\n")
    if language == "typescript":
        return EmittedFile("migrated.ts", extracted.rstrip() + "\n")
    if language == "go":
        return EmittedFile("migrated.go", "package main\n\n" + extracted.rstrip() + "\n")
    if language == "rust":
        return EmittedFile("migrated.rs", extracted.rstrip() + "\n")
    if language == "cpp":
        return EmittedFile("migrated.cpp", "#include <cstdint>\n#include <string>\n\n" + extracted.rstrip() + "\n")
    if language == "objc":
        return EmittedFile("migrated.m", "#import <Foundation/Foundation.h>\n\n" + extracted.rstrip() + "\n")
    return EmittedFile("migrated.swift", extracted.rstrip() + "\n")


def validate_source(
    source: Path,
    language: Language,
    function: Function,
    cases: list[dict[str, Any]],
    output: Path,
) -> dict[str, Any]:
    """Execute only the compiler-accepted pure function, not customer top-level code."""
    subject = _source_subject(source, language, function)
    try:
        evidence = validate(subject, language, function, cases, output)
    except RouteError as error:
        reason = str(error)
        if reason.startswith("TARGET_VALIDATION_FAILED:"):
            raise RouteError("SOURCE_VALIDATION_FAILED:" + reason.split(":", 1)[1]) from error
        raise
    return {**evidence, "subject": "SOURCE_DECLARATION_EXTRACT", "status": "PASSED"}


def validate(
    emitted: EmittedFile,
    language: Language,
    function: Function,
    cases: list[dict[str, Any]],
    output: Path,
) -> dict[str, Any]:
    toolchain = exact_toolchain(language)
    output.mkdir(parents=True, exist_ok=True)
    target = output / emitted.relative_path
    target.write_text(emitted.content, encoding="utf-8")
    commands: list[list[str]] = []
    if language == "java":
        (output / "RouteHarness.java").write_text(_java_harness(function, cases), encoding="utf-8")
        assert toolchain.auxiliary is not None
        commands = [
            [toolchain.auxiliary, "Migrated.java", "RouteHarness.java"],
            [toolchain.executable, "-cp", ".", "RouteHarness"],
        ]
    elif language == "python":
        (output / "route_harness.py").write_text(_python_harness(function, cases), encoding="utf-8")
        commands = [
            [toolchain.executable, "-m", "py_compile", "migrated.py", "route_harness.py"],
            [toolchain.executable, "route_harness.py"],
        ]
    elif language == "csharp":
        (output / "Program.cs").write_text(_csharp_harness(function, cases), encoding="utf-8")
        (output / "RouteHarness.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            "<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>"
            "<ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable>"
            "<TreatWarningsAsErrors>true</TreatWarningsAsErrors>"
            "</PropertyGroup></Project>\n",
            encoding="utf-8",
        )
        commands = [
            [toolchain.executable, "build", "RouteHarness.csproj", "-c", "Release"],
            [
                toolchain.executable,
                "run",
                "--project",
                "RouteHarness.csproj",
                "-c",
                "Release",
                "--no-build",
            ],
        ]
    elif language == "cpp":
        (output / "route_harness.cpp").write_text(_cpp_harness(function, cases), encoding="utf-8")
        commands = [
            [
                toolchain.executable,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-o",
                "route_harness",
                "route_harness.cpp",
            ],
            ["./route_harness"],
        ]
    elif language == "objc":
        (output / "route_harness.m").write_text(_objc_harness(function, cases), encoding="utf-8")
        commands = [
            [
                toolchain.executable,
                "-x",
                "objective-c",
                "-fobjc-arc",
                "-Wall",
                "-Werror",
                "-framework",
                "Foundation",
                "-o",
                "route_harness",
                "route_harness.m",
            ],
            ["./route_harness"],
        ]
    elif language == "swift":
        # The file *must* be called main.swift: Swift only allows top-level
        # statements there, and rejects them ("statements are not allowed at
        # the top level") in any other file name.
        (output / "main.swift").write_text(_swift_harness(function, cases), encoding="utf-8")
        commands = [
            [
                toolchain.executable,
                "-warnings-as-errors",
                "-o",
                "route_harness",
                "migrated.swift",
                "main.swift",
            ],
            ["./route_harness"],
        ]
    elif language == "go":
        (output / "route_harness.go").write_text(_go_harness(function, cases), encoding="utf-8")
        commands = [
            [toolchain.executable, "build", "-o", "route_harness", "migrated.go", "route_harness.go"],
            ["./route_harness"],
        ]
    elif language == "rust":
        (output / "route_harness.rs").write_text(_rust_harness(function, cases), encoding="utf-8")
        commands = [
            [toolchain.executable, "--edition=2021", "-D", "warnings", "-o", "route_harness", "route_harness.rs"],
            ["./route_harness"],
        ]
    else:
        (output / "route_harness.ts").write_text(_typescript_harness(function, cases), encoding="utf-8")
        (output / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2022",
                        "module": "NodeNext",
                        "moduleResolution": "NodeNext",
                        "strict": True,
                        "outDir": "dist",
                    },
                    "include": ["*.ts"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        assert toolchain.auxiliary is not None
        commands = [
            [toolchain.auxiliary, "-p", "tsconfig.json"],
            [toolchain.executable, "dist/route_harness.js"],
        ]
    logs = []
    for command in commands:
        completed = _run(command, output)
        logs.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    return {"status": "PASSED", "language": language, "commands": logs, "case_count": len(cases)}


def safe_output(path: Path) -> Path:
    lexical = Path(os.path.abspath(path.expanduser()))
    current = Path(lexical.anchor)
    for component in lexical.parts[1:]:
        current /= component
        if current.is_symlink():
            raise RouteError("OUTPUT_SYMLINK_REJECTED")
    resolved = lexical.resolve(strict=False)
    if resolved == Path.home() or resolved == REPOSITORY_ROOT or len(resolved.parts) < 4:
        raise RouteError("OUTPUT_PATH_TOO_BROAD")
    return lexical


def temporary_output() -> Path:
    return Path(tempfile.mkdtemp(prefix="elmos-polyglot-route-"))
