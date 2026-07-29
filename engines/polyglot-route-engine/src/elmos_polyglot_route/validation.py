from __future__ import annotations

import json
import os
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
        return "true" if value else "false"
    return json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value)


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
        checks.append(
            f'if (calculate({args}) !== {expected}) throw new Error("case {index}");'.replace(
                "calculate", function.name
            )
        )
    return "import { " + function.name + ' } from "./migrated.js";\n' + "\n".join(checks) + "\n"


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
    resolved = path.expanduser().resolve()
    if resolved == Path.home() or resolved == REPOSITORY_ROOT or len(resolved.parts) < 4:
        raise RouteError("OUTPUT_PATH_TOO_BROAD")
    if resolved.exists() and resolved.is_symlink():
        raise RouteError("OUTPUT_SYMLINK_REJECTED")
    return resolved


def temporary_output() -> Path:
    return Path(tempfile.mkdtemp(prefix="elmos-polyglot-route-"))
