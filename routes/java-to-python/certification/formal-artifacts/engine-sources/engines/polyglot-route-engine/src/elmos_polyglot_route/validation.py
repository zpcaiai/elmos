from __future__ import annotations

import base64
import hashlib
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


def _run(command: list[str], cwd: Path, *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["NO_COLOR"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-4_000:]
        raise RouteError(f"TARGET_VALIDATION_FAILED:{command[0]}:{detail}")
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


def _java_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    owner: str = "Migrated",
) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "java") for value in case["args"])
        expected = _expected(case["expected"], "java")
        call = f"{owner}.{function.name}({args})"
        actual = f"actual{index}"
        # `!=` on String is a reference comparison in Java, so a correct
        # string-returning route could still be reported as a behaviour
        # failure (or, with interned literals, a wrong one reported as a
        # pass). Objects.equals is the value comparison the other three
        # harnesses already perform.
        condition = (
            f"!java.util.Objects.equals({actual}, {expected})"
            if function.return_type == "string"
            else f"{actual} != {expected}"
        )
        checks.extend(
            [
                f"        var {actual} = {call};",
                f'        if ({condition}) throw new AssertionError("case {index}");',
                '        System.out.println("ELMOS_OBSERVATION\\t'
                f'{index}\\tb64\\t" + java.util.Base64.getEncoder().encodeToString('
                f"String.valueOf({actual}).getBytes(java.nio.charset.StandardCharsets.UTF_8)));",
            ]
        )
    return (
        "public final class RouteHarness {\n"
        "    public static void main(String[] args) {\n" + "\n".join(checks) + "\n    }\n}\n"
    )


def _csharp_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    owner: str = "Migrated",
) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "csharp") for value in case["args"])
        expected = _expected(case["expected"], "csharp")
        actual = f"actual{index}"
        checks.extend(
            [
                f"var {actual} = {owner}.{function.name}({args});",
                f'if ({actual} != {expected}) throw new Exception("case {index}");',
                'Console.WriteLine("ELMOS_OBSERVATION\\t'
                f'{index}\\tb64\\t" + Convert.ToBase64String('
                f"System.Text.Encoding.UTF8.GetBytes(Convert.ToString({actual}, "
                "System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));",
            ]
        )
    return "\n".join(checks) + "\n"


def _python_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    module: str = "migrated",
) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "python") for value in case["args"])
        actual = f"actual_{index}"
        checks.extend(
            [
                f"{actual} = {module}.{function.name}({args})",
                f"assert {actual} == {_expected(case['expected'], 'python')}",
                f'print("ELMOS_OBSERVATION\\tjson\\t" + json.dumps('
                f'{{"case_id": {index}, "value": {actual}}}, sort_keys=True, separators=(",", ":")))',
            ]
        )
    return f"import json\nimport {module}\n" + "\n".join(checks) + "\n"


def _typescript_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    module_path: str = "./migrated.js",
) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "typescript") for value in case["args"])
        expected = _expected(case["expected"], "typescript")
        # Built from the function name directly. An earlier revision templated
        # the literal name `calculate` and then string-replaced it, which also
        # rewrote any occurrence of "calculate" inside a string argument or
        # expected value -- silently changing what the behaviour case asserts.
        actual = f"actual{index}"
        checks.extend(
            [
                f"const {actual} = {function.name}({args});",
                f'if ({actual} !== {expected}) throw new Error("case {index}");',
                f'console.log("ELMOS_OBSERVATION\\tjson\\t" + JSON.stringify({{case_id: {index}, value: {actual}}}));',
            ]
        )
    return "import { " + function.name + f' }} from "{module_path}";\n' + "\n".join(checks) + "\n"


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
        actual = f"actual{index}"
        checks.extend(
            [
                f"    {actual} := {function.name}({args})",
                f'    if {actual} != {expected} {{ panic("case {index}") }}',
                f'    fmt.Printf("ELMOS_OBSERVATION\\t{index}\\tb64\\t%s\\n", '
                f"base64.StdEncoding.EncodeToString([]byte(fmt.Sprint({actual}))))",
            ]
        )
    return (
        'package main\n\nimport (\n    "encoding/base64"\n    "fmt"\n)\n\nfunc main() {\n' + "\n".join(checks) + "\n}\n"
    )


def _rust_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    include_file: str = "migrated.rs",
) -> str:
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
        actual = f"actual_{index}"
        checks.extend(
            [
                f"    let {actual} = {function.name}({args});",
                f'    assert!({actual} == {expected}, "case {index}");',
                f'    println!("ELMOS_OBSERVATION\\t{index}\\trust-debug\\t{{:?}}", {actual});',
            ]
        )
    return f'include!("{include_file}");\n\nfn main() {{\n' + "\n".join(checks) + "\n}\n"


def _typed_observation(text: str, return_type: str) -> object:
    if return_type == "integer":
        return int(text)
    if return_type == "number":
        return float(text)
    if return_type == "boolean":
        if text.lower() not in {"true", "false"}:
            raise RouteError("TARGET_OBSERVATION_BOOLEAN_INVALID")
        return text.lower() == "true"
    if return_type == "string":
        return text
    raise RouteError(f"TARGET_OBSERVATION_TYPE_UNSUPPORTED:{return_type}")


def _observations(
    stdout: str,
    function: Function,
    case_count: int,
) -> list[dict[str, Any]]:
    values: dict[int, dict[str, Any]] = {}
    for line in stdout.splitlines():
        if not line.startswith("ELMOS_OBSERVATION\t"):
            continue
        parts = line.split("\t", 3)
        if len(parts) < 3:
            raise RouteError("TARGET_OBSERVATION_MALFORMED")
        if parts[1] == "json":
            if len(parts) != 3:
                raise RouteError("TARGET_OBSERVATION_MALFORMED")
            try:
                payload = json.loads(parts[2])
            except json.JSONDecodeError as error:
                raise RouteError("TARGET_OBSERVATION_JSON_INVALID") from error
            if not isinstance(payload, dict) or not isinstance(payload.get("case_id"), int):
                raise RouteError("TARGET_OBSERVATION_JSON_INVALID")
            case_id = payload["case_id"]
            value = payload.get("value")
            encoding = "json"
            raw = parts[2]
        else:
            if len(parts) != 4:
                raise RouteError("TARGET_OBSERVATION_MALFORMED")
            try:
                case_id = int(parts[1])
            except ValueError as error:
                raise RouteError("TARGET_OBSERVATION_CASE_ID_INVALID") from error
            encoding = parts[2]
            raw = parts[3]
            if encoding == "b64":
                try:
                    decoded = base64.b64decode(raw, validate=True).decode("utf-8")
                except (ValueError, UnicodeDecodeError) as error:
                    raise RouteError("TARGET_OBSERVATION_BASE64_INVALID") from error
                value = _typed_observation(decoded, function.return_type)
            elif encoding == "rust-debug":
                if function.return_type == "string":
                    try:
                        value = json.loads(raw)
                    except json.JSONDecodeError as error:
                        raise RouteError("TARGET_OBSERVATION_RUST_STRING_INVALID") from error
                else:
                    value = _typed_observation(raw, function.return_type)
            else:
                raise RouteError(f"TARGET_OBSERVATION_ENCODING_UNSUPPORTED:{encoding}")
        if not 0 <= case_id < case_count or case_id in values:
            raise RouteError("TARGET_OBSERVATION_CASE_SET_INVALID")
        values[case_id] = {
            "case_id": case_id,
            "status": "RETURNED",
            "value": value,
            "encoding": encoding,
            "raw": raw,
        }
    if set(values) != set(range(case_count)):
        raise RouteError("TARGET_OBSERVATION_CASE_SET_INCOMPLETE")
    return [values[index] for index in range(case_count)]


def _go_source_harness(
    package_name: str,
    function: Function,
    cases: list[dict[str, Any]],
) -> str:
    checks: list[str] = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "go") for value in case["args"])
        expected = _expected(case["expected"], "go")
        actual = f"actual{index}"
        checks.extend(
            [
                f"    {actual} := {function.name}({args})",
                f'    if {actual} != {expected} {{ t.Fatalf("case {index}") }}',
                f'    fmt.Printf("ELMOS_OBSERVATION\\t{index}\\tb64\\t%s\\n", '
                f"base64.StdEncoding.EncodeToString([]byte(fmt.Sprint({actual}))))",
            ]
        )
    return (
        f"package {package_name}\n\n"
        'import (\n    "encoding/base64"\n    "fmt"\n    "testing"\n)\n\n'
        "func TestElmosSourceBehavior(t *testing.T) {\n" + "\n".join(checks) + "\n}\n"
    )


def _safe_source_name(source: Path) -> str:
    stem = source.stem
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stem):
        raise RouteError("SOURCE_MODULE_NAME_UNSAFE")
    return stem


def validate_source(
    source: Path,
    language: Language,
    function: Function,
    cases: list[dict[str, Any]],
    output: Path,
) -> dict[str, Any]:
    """Compile and execute the original source artifact in an isolated folder.

    This is intentionally separate from target validation: re-emitting the
    source IR back into its own language would only test the emitter twice and
    would not be evidence about the original source bytes.
    """

    toolchain = exact_toolchain(language)
    output.mkdir(parents=True, exist_ok=True)
    source_name = _safe_source_name(source)
    copied_source = output / source.name
    copied_source.write_bytes(source.read_bytes())
    commands: list[list[str]]
    if language == "java":
        (output / "RouteHarness.java").write_text(_java_harness(function, cases, owner=source_name), encoding="utf-8")
        assert toolchain.auxiliary is not None
        commands = [
            [toolchain.auxiliary, source.name, "RouteHarness.java"],
            [toolchain.executable, "-cp", ".", "RouteHarness"],
        ]
    elif language == "python":
        (output / "source_harness.py").write_text(
            _python_harness(function, cases, module=source_name), encoding="utf-8"
        )
        commands = [
            [toolchain.executable, "-m", "py_compile", source.name, "source_harness.py"],
            [toolchain.executable, "source_harness.py"],
        ]
    elif language == "csharp":
        (output / "Program.cs").write_text(_csharp_harness(function, cases, owner=source_name), encoding="utf-8")
        (output / "SourceHarness.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            "<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>"
            "<ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable>"
            "<TreatWarningsAsErrors>true</TreatWarningsAsErrors>"
            "</PropertyGroup></Project>\n",
            encoding="utf-8",
        )
        commands = [
            [toolchain.executable, "build", "SourceHarness.csproj", "-c", "Release"],
            [
                toolchain.executable,
                "run",
                "--project",
                "SourceHarness.csproj",
                "-c",
                "Release",
                "--no-build",
            ],
        ]
    elif language == "typescript":
        (output / "source_harness.ts").write_text(
            _typescript_harness(function, cases, module_path=f"./{source_name}.js"),
            encoding="utf-8",
        )
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
            [toolchain.executable, "dist/source_harness.js"],
        ]
    elif language == "go":
        match = re.search(r"(?m)^package\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", source.read_text(encoding="utf-8"))
        if match is None:
            raise RouteError("GO_SOURCE_PACKAGE_REQUIRED")
        (output / "source_behavior_test.go").write_text(
            _go_source_harness(match.group(1), function, cases), encoding="utf-8"
        )
        commands = [
            [
                toolchain.executable,
                "test",
                "-v",
                "-count=1",
                "-run",
                "^TestElmosSourceBehavior$",
                source.name,
                "source_behavior_test.go",
            ]
        ]
    elif language == "rust":
        (output / "source_harness.rs").write_text(
            _rust_harness(function, cases, include_file=source.name), encoding="utf-8"
        )
        commands = [
            [
                toolchain.executable,
                "--edition=2021",
                "-D",
                "warnings",
                "-o",
                "source_harness",
                "source_harness.rs",
            ],
            ["./source_harness"],
        ]
    else:
        raise RouteError(f"SOURCE_RUNTIME_UNSUPPORTED:{language}")
    logs: list[dict[str, Any]] = []
    runtime_stdout = ""
    for index, command in enumerate(commands):
        completed = _run(command, output)
        logs.append(
            {
                "command": command,
                "stdout": completed.stdout[-2_000:],
                "stderr": completed.stderr[-2_000:],
            }
        )
        if index == len(commands) - 1:
            runtime_stdout = completed.stdout
    observations = _observations(runtime_stdout, function, len(cases))
    return {
        "status": "PASSED",
        "role": "source",
        "language": language,
        "artifact_path": source.name,
        "artifact_sha256": "sha256:" + hashlib.sha256(copied_source.read_bytes()).hexdigest(),
        "commands": logs,
        "case_count": len(cases),
        "observations": observations,
    }


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
    runtime_stdout = ""
    for index, command in enumerate(commands):
        completed = _run(command, output)
        logs.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
        if index == len(commands) - 1:
            runtime_stdout = completed.stdout
    observations = (
        _observations(runtime_stdout, function, len(cases))
        if language in {"java", "python", "csharp", "typescript", "go", "rust"}
        else []
    )
    return {
        "status": "PASSED",
        "language": language,
        "commands": logs,
        "case_count": len(cases),
        "observations": observations,
    }


def safe_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == Path.home() or resolved == REPOSITORY_ROOT or len(resolved.parts) < 4:
        raise RouteError("OUTPUT_PATH_TOO_BROAD")
    if resolved.exists() and resolved.is_symlink():
        raise RouteError("OUTPUT_SYMLINK_REJECTED")
    return resolved


def temporary_output() -> Path:
    return Path(tempfile.mkdtemp(prefix="elmos-polyglot-route-"))
