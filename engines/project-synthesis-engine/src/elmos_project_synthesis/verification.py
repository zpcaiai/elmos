from __future__ import annotations

import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

EXACT_TOOLCHAIN_REQUIREMENTS: dict[str, list[dict[str, Any]]] = {
    "python": [
        {
            "tool": "uv",
            "arguments": ["--version"],
            "expected": "uv 0.11.16",
            "pattern": r"^uv 0\.11\.16\b",
            "fallback": "/opt/homebrew/bin/uv",
        },
        {
            "tool": "uv",
            "arguments": ["run", "--python", "3.12", "python", "--version"],
            "expected": "Python 3.12",
            "pattern": r"^Python 3\.12(?:\.|$)",
            "fallback": "/opt/homebrew/bin/uv",
        },
    ],
    "java": [
        {
            "tool": "java",
            "arguments": ["-version"],
            "expected": "Java 21",
            "pattern": r'version "21(?:[.\-"]|$)',
            "fallback": "/opt/homebrew/opt/openjdk@21/bin/java",
        },
        {
            "tool": "mvn",
            "arguments": ["-version"],
            "expected": "Apache Maven 3.9.10",
            "pattern": r"Apache Maven 3\.9\.10\b",
            "fallback": "/opt/homebrew/bin/mvn",
        },
    ],
    "csharp": [
        {
            "tool": "dotnet",
            "arguments": ["--version"],
            "expected": ".NET SDK 10.0.301",
            "pattern": r"^10\.0\.301$",
            "fallback": "/opt/homebrew/bin/dotnet",
        }
    ],
    "typescript": [
        {"tool": "node", "arguments": ["--version"], "expected": "Node 26.0.0", "pattern": r"^v26\.0\.0$"},
        {"tool": "pnpm", "arguments": ["--version"], "expected": "pnpm 10.12.4", "pattern": r"^10\.12\.4$"},
    ],
    "go": [{"tool": "go", "arguments": ["version"], "expected": "Go 1.25.0", "pattern": r"\bgo1\.25\.0\b"}],
    "kotlin": [
        {
            "tool": "java",
            "arguments": ["-version"],
            "expected": "Java 21",
            "pattern": r'version "21(?:[.\-"]|$)',
            "fallback": "/opt/homebrew/opt/openjdk@21/bin/java",
        },
        {"tool": "gradle", "arguments": ["--version"], "expected": "Gradle 8.14.3", "pattern": r"\bGradle 8\.14\.3\b"},
    ],
    "php": [{"tool": "php", "arguments": ["--version"], "expected": "PHP 8.4.12", "pattern": r"^PHP 8\.4\.12\b"}],
    "rust": [
        {"tool": "rustc", "arguments": ["--version"], "expected": "rustc 1.89.0", "pattern": r"^rustc 1\.89\.0\b"},
        {"tool": "cargo", "arguments": ["--version"], "expected": "cargo 1.89.0", "pattern": r"^cargo 1\.89\.0\b"},
    ],
    "postgresql": [
        {
            "tool": "postgres",
            "arguments": ["--version"],
            "expected": "PostgreSQL 17.5",
            "pattern": r"^postgres \(PostgreSQL\) 17\.5(?: \(Homebrew\))?$",
            "fallback": "/opt/homebrew/opt/postgresql@17/bin/postgres",
        }
    ],
}


def _resolve_tool(name: str, fallback: str | None = None) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if fallback and Path(fallback).is_file():
        return fallback
    return None


def _result(
    *,
    language: str,
    kind: str,
    command: list[str],
    status: str,
    exit_code: int | None,
    output: str = "",
) -> dict[str, Any]:
    return {
        "language": language,
        "kind": kind,
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "output": output[-12_000:],
    }


def _run(command: list[str], cwd: Path, *, language: str, kind: str = "build-analysis") -> dict[str, Any]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)  # noqa: S603
    output = completed.stdout + completed.stderr
    return _result(
        language=language,
        kind=kind,
        command=command,
        status="PASSED" if completed.returncode == 0 else "FAILED",
        exit_code=completed.returncode,
        output=output,
    )


def _missing(language: str, tool: str) -> dict[str, Any]:
    return _result(
        language=language,
        kind="toolchain",
        command=[tool],
        status="NOT_RUN",
        exit_code=None,
        output=f"REQUIRED_TOOL_NOT_FOUND:{tool}",
    )


def _check_exact_toolchain(
    language: str,
    requirements: list[dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    for requirement in requirements:
        tool_name = str(requirement["tool"])
        tool, observations = _matching_tool(requirement)
        if tool is None and not observations:
            results.append(_missing(language, tool_name))
            return False, results
        arguments = [str(item) for item in requirement["arguments"]]
        expected = str(requirement["expected"])
        matched = tool is not None
        results.append(
            _result(
                language=language,
                kind="toolchain",
                command=[tool or tool_name, *arguments],
                status="PASSED" if matched else "NOT_RUN",
                exit_code=0 if matched else 1,
                output=f"EXPECTED:{expected}\n" + "\n".join(observations),
            )
        )
        if not matched:
            return False, results
    return True, results


def _matching_tool(requirement: dict[str, Any]) -> tuple[str | None, list[str]]:
    tool_name = str(requirement["tool"])
    fallback = str(requirement["fallback"]) if requirement.get("fallback") else None
    candidates = [
        candidate
        for candidate in dict.fromkeys((shutil.which(tool_name), fallback))
        if candidate and Path(candidate).is_file()
    ]
    arguments = [str(item) for item in requirement["arguments"]]
    observations: list[str] = []
    for candidate in candidates:
        completed = subprocess.run(  # noqa: S603
            [candidate, *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        observed = (completed.stdout + completed.stderr).strip()
        observations.append(f"OBSERVED:{candidate}:{observed}")
        if (
            completed.returncode == 0
            and re.search(
                str(requirement["pattern"]),
                observed,
                flags=re.MULTILINE,
            )
            is not None
        ):
            return candidate, observations
    return None, observations


def _runtime_tool(language: str, tool_name: str, fallback: str | None = None) -> str | None:
    requirements = EXACT_TOOLCHAIN_REQUIREMENTS.get(language, [])
    selected: str | None = None
    for requirement in requirements:
        matched, _ = _matching_tool(requirement)
        if matched is None:
            return None
        if str(requirement["tool"]) == tool_name:
            selected = matched
    return selected or _resolve_tool(tool_name, fallback)


def _planned_runtime_tool(
    language: str,
    tool_name: str,
    fallback: str | None = None,
) -> tuple[str, dict[str, str]]:
    tool = _runtime_tool(language, tool_name, fallback)
    if tool is not None:
        return tool, {"execution_status": "READY"}
    return tool_name, {
        "execution_status": "NOT_RUN",
        "blocking_reason": f"EXACT_TOOLCHAIN_NOT_AVAILABLE:{language}:{tool_name}",
    }


def _health_response_matches(
    http_status: int,
    payload: Any,
    *,
    expected_service: str,
) -> bool:
    return (
        http_status == 200
        and isinstance(payload, dict)
        and payload.get("status") == "UP"
        and payload.get("service") == expected_service
    )


def _probe(
    command: list[str],
    cwd: Path,
    port: int,
    *,
    language: str,
    expected_service: str,
    environment: dict[str, str] | None = None,
    integration_command: list[str] | None = None,
    integration_environment: dict[str, str] | None = None,
    startup_timeout_seconds: int = 30,
) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(environment or {})
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    if not 5 <= startup_timeout_seconds <= 180:
        raise ValueError("STARTUP_TIMEOUT_OUT_OF_RANGE")
    deadline = time.monotonic() + startup_timeout_seconds
    status = "FAILED"
    response = ""
    integration_status = "NOT_RUN"
    integration_output = ""
    local_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                request = urllib.request.Request(f"http://127.0.0.1:{port}/health", method="GET")  # noqa: S310
                with local_opener.open(request, timeout=1) as result:
                    response = result.read().decode("utf-8")
                    parsed = json.loads(response)
                    if _health_response_matches(
                        result.status,
                        parsed,
                        expected_service=expected_service,
                    ):
                        status = "PASSED"
                        break
            except (OSError, ValueError, urllib.error.URLError):
                time.sleep(0.25)
        if status == "PASSED" and integration_command:
            integration_env = env.copy()
            integration_env.update(integration_environment or {})
            try:
                completed = subprocess.run(  # noqa: S603
                    integration_command,
                    cwd=cwd,
                    env=integration_env,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=120,
                )
            except subprocess.TimeoutExpired as error:
                timeout_stdout = (
                    error.stdout.decode("utf-8", errors="replace")
                    if isinstance(error.stdout, bytes)
                    else error.stdout or ""
                )
                timeout_stderr = (
                    error.stderr.decode("utf-8", errors="replace")
                    if isinstance(error.stderr, bytes)
                    else error.stderr or ""
                )
                integration_output = f"INTEGRATION_TIMEOUT:{error.timeout}s\n{timeout_stdout}{timeout_stderr}"
                integration_status = "FAILED"
            else:
                integration_output = completed.stdout + completed.stderr
                integration_status = "PASSED" if completed.returncode == 0 else "FAILED"
            if integration_status == "FAILED":
                status = "FAILED"
    finally:
        if process.poll() is None:
            if hasattr(os, "killpg"):
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if hasattr(os, "killpg"):
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
        output = process.stdout.read()[-6_000:] if process.stdout is not None else ""
        if process.stdout is not None:
            process.stdout.close()
    result = _result(
        language=language,
        kind="startup-probe",
        command=command,
        status=status,
        exit_code=0 if status == "PASSED" else 1,
        output=f"{output}\n{integration_output}",
    )
    result.update(
        {
            "port": port,
            "response": response,
            "integration_status": integration_status,
        }
    )
    return result


def _blueprint(workspace: Path) -> dict[str, Any]:
    path = workspace / "requirements" / "project-blueprint.json"
    if not path.is_file():
        raise RuntimeError("PROJECT_BLUEPRINT_REQUIRED")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RuntimeError("PROJECT_BLUEPRINT_INVALID")
    return loaded


def runtime_commands(workspace: Path) -> list[dict[str, Any]]:
    root = workspace.resolve(strict=True)
    commands: list[dict[str, Any]] = []
    for application in _blueprint(root).get("applications", []):
        language = application.get("language")
        port = application.get("port")
        if not isinstance(language, str) or not isinstance(port, int):
            continue
        if language == "java":
            jars = [
                path for path in sorted((root / "java" / "target").glob("*.jar")) if not path.name.endswith(".original")
            ]
            tool, execution = _planned_runtime_tool("java", "java")
            if jars:
                commands.append(
                    {
                        "language": language,
                        "cwd": str(root / "java"),
                        "command": [tool, "-jar", str(jars[0])],
                        "environment": {"PORT": str(port), "SERVER_ADDRESS": "127.0.0.1"},
                        "port": port,
                        **execution,
                    }
                )
        elif language == "python":
            packages = sorted((root / "python" / "src").glob("*/__main__.py"))
            tool, execution = _planned_runtime_tool("python", "uv", "/opt/homebrew/bin/uv")
            if packages:
                storage = application.get("storage")
                auth_mode = application.get("auth_mode")
                state = root / "python" / ".elmos-runtime"
                runtime_arguments = (
                    ["run", "python", "scripts/local_runtime.py"]
                    if storage == "postgresql"
                    else ["run", "python", "-m", packages[0].parent.name]
                )
                plan: dict[str, Any] = {
                    "language": language,
                    "cwd": str(root / "python"),
                    "command": [tool, *runtime_arguments],
                    "environment": {
                        "PORT": str(port),
                        "HOST": "127.0.0.1",
                        "ELMOS_RUNTIME_STATE_DIR": str(state),
                    },
                    "providers": ["postgresql"] if storage == "postgresql" else [],
                    "port": port,
                    **execution,
                }
                if storage == "postgresql":
                    integration_environment = {
                        "ELMOS_DATABASE_URL_FILE": str(state / "database-url"),
                        "ELMOS_AUTH_ISSUER": "https://identity.local.invalid/",
                        "ELMOS_AUTH_AUDIENCE": "generated-api",
                    }
                    if auth_mode == "jwt":
                        integration_environment["ELMOS_JWT_HMAC_SECRET_FILE"] = str(state / "jwt-hmac")
                    elif auth_mode == "oidc":
                        integration_environment["ELMOS_OIDC_JWKS_FILE"] = str(state / "oidc-jwks.json")
                        integration_environment["ELMOS_OIDC_PRIVATE_KEY_FILE"] = str(state / "oidc-private-key.pem")
                    plan["integration_command"] = [
                        tool,
                        "run",
                        "pytest",
                        "-m",
                        "integration",
                    ]
                    plan["integration_environment"] = integration_environment
                commands.append(plan)
        elif language == "csharp":
            projects = sorted((root / "dotnet" / "src").glob("*/*.csproj"))
            tool, execution = _planned_runtime_tool("csharp", "dotnet", "/opt/homebrew/bin/dotnet")
            if projects:
                commands.append(
                    {
                        "language": language,
                        "cwd": str(root / "dotnet"),
                        "command": [
                            tool,
                            "run",
                            "--no-build",
                            "-c",
                            "Release",
                            "--project",
                            str(projects[0]),
                        ],
                        "environment": {"ASPNETCORE_URLS": f"http://127.0.0.1:{port}"},
                        "port": port,
                        **execution,
                    }
                )
        elif language == "typescript":
            tool, execution = _planned_runtime_tool("typescript", "pnpm")
            commands.append(
                {
                    "language": language,
                    "cwd": str(root / "typescript"),
                    "command": [tool, "start"],
                    "environment": {"PORT": str(port), "HOST": "127.0.0.1"},
                    "port": port,
                    **execution,
                }
            )
        elif language == "go":
            tool, execution = _planned_runtime_tool("go", "go")
            commands.append(
                {
                    "language": language,
                    "cwd": str(root / "go"),
                    "command": [tool, "run", "."],
                    "environment": {"PORT": str(port), "HOST": "127.0.0.1"},
                    "port": port,
                    **execution,
                }
            )
        elif language == "kotlin":
            tool, execution = _planned_runtime_tool("kotlin", "gradle")
            commands.append(
                {
                    "language": language,
                    "cwd": str(root / "kotlin"),
                    "command": [tool, "--no-daemon", "run"],
                    "environment": {"PORT": str(port), "HOST": "127.0.0.1"},
                    "port": port,
                    "startup_timeout_seconds": 120,
                    **execution,
                }
            )
        elif language == "php":
            tool, execution = _planned_runtime_tool("php", "php")
            commands.append(
                {
                    "language": language,
                    "cwd": str(root / "php"),
                    "command": [
                        tool,
                        "-S",
                        f"127.0.0.1:{port}",
                        "public/index.php",
                    ],
                    "environment": {"PORT": str(port)},
                    "port": port,
                    **execution,
                }
            )
        elif language == "rust":
            tool, execution = _planned_runtime_tool("rust", "cargo")
            commands.append(
                {
                    "language": language,
                    "cwd": str(root / "rust"),
                    "command": [tool, "run", "--locked"],
                    "environment": {"PORT": str(port), "HOST": "127.0.0.1"},
                    "port": port,
                    **execution,
                }
            )
    return commands


def _run_if_available(
    results: list[dict[str, Any]],
    *,
    language: str,
    tool_name: str,
    commands: list[list[str]],
    cwd: Path,
) -> bool:
    tool = _resolve_tool(tool_name)
    if tool is None:
        results.append(_missing(language, tool_name))
        return False
    for arguments in commands:
        command = [tool, *arguments]
        result = _run(command, cwd, language=language)
        results.append(result)
        if result["status"] != "PASSED":
            return False
    return True


def verify_workspace(workspace: Path) -> dict[str, Any]:
    root = workspace.resolve(strict=True)
    applications = _blueprint(root).get("applications", [])
    selected: set[str] = set()
    for item in applications:
        if not isinstance(item, dict):
            continue
        language = item.get("language")
        if isinstance(language, str):
            selected.add(language)
    results: list[dict[str, Any]] = []
    build_passed: set[str] = set()
    exact_toolchains: dict[str, bool] = {}
    provider_ready: dict[str, bool] = {}
    if any(isinstance(item, dict) and item.get("storage") == "postgresql" for item in applications):
        provider_ready["postgresql"], provider_checks = _check_exact_toolchain(
            "postgresql",
            EXACT_TOOLCHAIN_REQUIREMENTS["postgresql"],
        )
        results.extend(provider_checks)
    for language in sorted(selected):
        exact_toolchains[language], checks = _check_exact_toolchain(
            language,
            EXACT_TOOLCHAIN_REQUIREMENTS.get(language, []),
        )
        results.extend(checks)

    if "java" in selected:
        if exact_toolchains["java"]:
            tool = _resolve_tool("mvn", "/opt/homebrew/bin/mvn")
            assert tool is not None
            result = _run([tool, "-B", "package"], root / "java", language="java")
            results.append(result)
            if result["status"] == "PASSED":
                build_passed.add("java")

    if "python" in selected:
        tool = _resolve_tool("uv", "/opt/homebrew/bin/uv")
        if tool is None:
            results.append(_missing("python", "uv"))
        else:
            python_commands = (
                [tool, "lock"],
                [tool, "sync", "--locked", "--python", "3.12"],
                [tool, "run", "--python", "3.12", "python", "--version"],
                [tool, "run", "pytest", "-m", "not integration"],
                [tool, "run", "ruff", "check", "src", "tests"],
                [tool, "run", "mypy", "src"],
            )
            for command in python_commands:
                result = _run(command, root / "python", language="python")
                results.append(result)
                if result["status"] != "PASSED":
                    break
            else:
                build_passed.add("python")

    if "csharp" in selected:
        if exact_toolchains["csharp"]:
            tool = _resolve_tool("dotnet", "/opt/homebrew/bin/dotnet")
            assert tool is not None
            dotnet_commands = (
                [tool, "restore", "--use-lock-file"],
                [tool, "restore", "--locked-mode"],
                [tool, "test", "--no-restore", "-c", "Release"],
            )
            for command in dotnet_commands:
                result = _run(command, root / "dotnet", language="csharp")
                results.append(result)
                if result["status"] != "PASSED":
                    break
            else:
                build_passed.add("csharp")

    target_commands = {
        "typescript": (
            "pnpm",
            [
                ["install", "--lockfile-only", "--ignore-scripts"],
                ["install", "--frozen-lockfile", "--ignore-scripts"],
                ["check"],
                ["test"],
                ["build"],
            ],
        ),
        "go": ("go", [["vet", "./..."], ["test", "-race", "./..."], ["build", "./..."]]),
        "kotlin": ("gradle", [["--no-daemon", "--write-locks", "test", "build"]]),
        "php": ("php", [["-l", "src/Store.php"], ["-l", "public/index.php"], ["tests/run.php"]]),
        "rust": (
            "cargo",
            [
                ["generate-lockfile"],
                ["fmt", "--check"],
                ["clippy", "--locked", "--all-targets", "--all-features", "--", "-D", "warnings"],
                ["test", "--locked", "--all-features"],
                ["build", "--locked", "--release"],
            ],
        ),
    }
    directory_names = {"typescript": "typescript", "go": "go", "kotlin": "kotlin", "php": "php", "rust": "rust"}
    for language, (tool, tool_commands) in target_commands.items():
        if language not in selected:
            continue
        if not exact_toolchains[language]:
            continue
        if _run_if_available(
            results,
            language=language,
            tool_name=tool,
            commands=tool_commands,
            cwd=root / directory_names[language],
        ):
            build_passed.add(language)

    blueprint = _blueprint(root)
    project = blueprint.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("name"), str):
        raise RuntimeError("PROJECT_BLUEPRINT_NAME_REQUIRED")
    expected_service = str(project["name"])
    for plan in runtime_commands(root):
        language = str(plan["language"])
        if language not in build_passed:
            continue
        providers = plan.get("providers", [])
        if not isinstance(providers, list) or any(
            not provider_ready.get(str(provider), False) for provider in providers
        ):
            continue
        command = list(plan["command"])
        executable = str(command[0])
        executable_name = Path(executable).name
        exact_requirement = next(
            (
                requirement
                for requirement in EXACT_TOOLCHAIN_REQUIREMENTS.get(language, [])
                if str(requirement["tool"]) == executable_name
            ),
            None,
        )
        if exact_requirement is not None:
            exact_executable, _ = _matching_tool(exact_requirement)
            if exact_executable is None:
                results.append(_missing(language, executable_name))
                continue
            command[0] = exact_executable
            executable = exact_executable
        if shutil.which(executable) is None and not Path(executable).is_file():
            results.append(_missing(language, executable))
            continue
        results.append(
            _probe(
                command,
                Path(str(plan["cwd"])),
                int(plan["port"]),
                language=language,
                expected_service=expected_service,
                environment=dict(plan["environment"]),
                integration_command=(
                    list(plan["integration_command"]) if isinstance(plan.get("integration_command"), list) else None
                ),
                integration_environment=(
                    dict(plan["integration_environment"])
                    if isinstance(plan.get("integration_environment"), dict)
                    else None
                ),
                startup_timeout_seconds=int(plan.get("startup_timeout_seconds", 30)),
            )
        )

    statuses = {str(result["status"]) for result in results}
    status = "FAILED" if "FAILED" in statuses else "PARTIAL" if "NOT_RUN" in statuses else "PASSED"
    tools = {
        name: (_resolve_tool(name) is not None)
        for name in ("java", "mvn", "uv", "dotnet", "node", "pnpm", "go", "gradle", "php", "cargo")
    }
    return {
        "schema_version": "1.1.0",
        "status": status,
        "workspace": str(root),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "tools": tools,
            "exact_toolchain_match": exact_toolchains,
        },
        "production_delivery_status": "NOT_RUN",
        "external_certification_status": "NOT_RUN",
        "results": results,
    }
