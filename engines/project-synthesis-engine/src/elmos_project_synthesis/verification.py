from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .insights import verified_generation_insights
from .models import SUPPORTED_PROFILE_TARGETS
from .production_contract import (
    ENV_AUTH_AUDIENCE,
    ENV_AUTH_ISSUER,
    ENV_DATABASE_URL_FILE,
    ENV_JWT_SECRET_FILE,
    ENV_OIDC_JWKS_FILE,
    ENV_OIDC_PRIVATE_KEY_FILE,
    ENV_RUNTIME_STATE_DIR,
    LOCAL_AUDIENCE,
    LOCAL_ISSUER,
)
from .project_graphs import validate_workspace_graphs

LOCAL_TOOLCHAIN_ROOT = Path(
    os.getenv(
        "ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT",
        str(Path.home() / ".local" / "share" / "elmos" / "toolchains"),
    )
).expanduser()

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
    "go": [
        {
            "tool": "go",
            "arguments": ["version"],
            "expected": "Go 1.25.0",
            "pattern": r"\bgo1\.25\.0\b",
            "fallback": str(LOCAL_TOOLCHAIN_ROOT / "go" / "1.25.0" / "bin" / "go"),
        }
    ],
    "kotlin": [
        {
            "tool": "java",
            "arguments": ["-version"],
            "expected": "Java 21",
            "pattern": r'version "21(?:[.\-"]|$)',
            "fallback": "/opt/homebrew/opt/openjdk@21/bin/java",
        },
        {
            "tool": "gradle",
            "arguments": ["--version"],
            "expected": "Gradle 8.14.3",
            "pattern": r"\bGradle 8\.14\.3\b",
            "fallback": str(LOCAL_TOOLCHAIN_ROOT / "gradle" / "8.14.3" / "bin" / "gradle"),
        },
    ],
    "php": [
        {
            "tool": "php",
            "arguments": ["--version"],
            "expected": "PHP 8.4.12",
            "pattern": r"^PHP 8\.4\.12\b",
            "fallback": str(LOCAL_TOOLCHAIN_ROOT / "php" / "8.4.12" / "bin" / "php"),
        }
    ],
    "rust": [
        {
            "tool": "rustc",
            "arguments": ["--version"],
            "expected": "rustc 1.89.0",
            "pattern": r"^rustc 1\.89\.0\b",
            "fallback": str(LOCAL_TOOLCHAIN_ROOT / "rust" / "1.89.0" / "bin" / "rustc"),
        },
        {
            "tool": "cargo",
            "arguments": ["--version"],
            "expected": "cargo 1.89.0",
            "pattern": r"^cargo 1\.89\.0\b",
            "fallback": str(LOCAL_TOOLCHAIN_ROOT / "rust" / "1.89.0" / "bin" / "cargo"),
        },
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


def _gradle_proxy_system_properties() -> list[str]:
    options: list[str] = []
    controlled_proxy = os.environ.get("ELMOS_PROJECT_SYNTHESIS_GRADLE_PROXY")
    # Do not silently translate ambient shell proxy variables into JVM system
    # properties. Gradle does not normally consume them, and doing so made a
    # fast direct Maven Central path crawl until the build timeout. Environments
    # that require a Gradle proxy must opt in through the validated setting.
    if not controlled_proxy:
        return [
            "-Djava.net.useSystemProxies=false",
            "-Dhttp.proxyHost=",
            "-Dhttps.proxyHost=",
        ]
    for protocol in ("http", "https"):
        configured = controlled_proxy
        error_code = f"KOTLIN_{protocol.upper()}_PROXY_INVALID"
        try:
            parsed = urlsplit(configured)
            hostname = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as error:
            raise ValueError(error_code) from error
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or not re.fullmatch(r"[A-Za-z0-9._:-]+", hostname)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(error_code)
        options.extend(
            [
                f"-D{protocol}.proxyHost={hostname}",
                f"-D{protocol}.proxyPort={port}",
            ]
        )
    return options


def _gradle_repository_property() -> list[str]:
    """Return an explicitly reviewed HTTPS Maven repository override."""
    configured = os.environ.get("ELMOS_PROJECT_SYNTHESIS_GRADLE_REPOSITORY", "").strip()
    if not configured:
        return []
    try:
        parsed = urlsplit(configured)
        port = parsed.port
    except ValueError as error:
        raise ValueError("KOTLIN_GRADLE_REPOSITORY_INVALID") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("KOTLIN_GRADLE_REPOSITORY_INVALID")
    return [f"-PelmosMavenRepository={configured.rstrip('/')}"]


def _gradle_user_home() -> Path:
    configured = os.environ.get("ELMOS_PROJECT_SYNTHESIS_GRADLE_USER_HOME", "").strip()
    root = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".cache" / "elmos" / "project-synthesis" / "gradle-user-home"
    )
    if configured and not root.is_absolute():
        raise ValueError("GRADLE_USER_HOME_MUST_BE_ABSOLUTE")
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise ValueError("GRADLE_USER_HOME_UNSAFE")
    else:
        root.mkdir(parents=True, mode=0o700)
    if root.stat().st_mode & 0o077:
        raise ValueError("GRADLE_USER_HOME_PERMISSIONS_UNSAFE")
    return root.resolve(strict=True)


#: The command timeout when neither the caller nor the environment sets one.
_DEFAULT_COMMAND_TIMEOUT_SECONDS = 300

#: One retry, and only for a fetch failure. See `_is_transient_dependency_fetch`.
_MAX_TRANSIENT_DEPENDENCY_RETRIES = 1
_TRANSIENT_DEPENDENCY_RETRY_BACKOFF_SECONDS = 2.0

#: Matched case-insensitively against the failed attempt's combined output.
#: Deliberately narrow: these are the tool saying it could not GET a package,
#: which is the only failure re-running an identical locked resolution can fix.
_TRANSIENT_DEPENDENCY_FETCH_MARKERS = (
    "failed to fetch",
    "failed to download",
    "error sending request",
    "connection reset by peer",
    "temporary failure in name resolution",
)


def _go_module_cache_roots(cwd: Path) -> tuple[Path, Path]:
    configured_gomod = os.getenv("ELMOS_PROJECT_SYNTHESIS_GOMODCACHE", "").strip()
    configured_gocache = os.getenv("ELMOS_PROJECT_SYNTHESIS_GOCACHE", "").strip()
    gomod_cache = Path(configured_gomod) if configured_gomod else (cwd / ".elmos-go-cache" / "mod")
    go_cache = Path(configured_gocache) if configured_gocache else (cwd / ".elmos-go-cache" / "build")
    if not gomod_cache.is_absolute() or gomod_cache.is_symlink():
        raise ValueError("GO_CACHE_PATH_UNSAFE")
    if not go_cache.is_absolute() or go_cache.is_symlink():
        raise ValueError("GO_CACHE_PATH_UNSAFE")
    for cache_path in (gomod_cache, go_cache):
        cache_path.mkdir(parents=True, mode=0o700, exist_ok=True)
        cache_path.chmod(0o700)
        if cache_path.stat().st_mode & 0o077:
            raise ValueError("GO_CACHE_PERMISSIONS_UNSAFE")
    return gomod_cache, go_cache


def _configured_command_timeout_seconds() -> int:
    """The default timeout, from the environment when it is set.

    Only the DEFAULT. A caller that passes `timeout_seconds=` explicitly has
    made a per-command decision and keeps it. The value is NOT range-checked
    here -- `_run` holds the single 30..900 gate so a configured value and a
    passed value fail closed identically.
    """

    configured = os.getenv("ELMOS_PROJECT_SYNTHESIS_COMMAND_TIMEOUT_SECONDS", "").strip()
    if not configured:
        return _DEFAULT_COMMAND_TIMEOUT_SECONDS
    try:
        return int(configured)
    except ValueError:
        raise ValueError("COMMAND_TIMEOUT_NOT_AN_INTEGER") from None


def _is_locked_dependency_sync(command: list[str]) -> bool:
    """`uv sync --locked` and nothing else.

    `--locked` means "resolve exactly the committed lockfile or fail"; running
    it a second time cannot install anything different, which is what makes a
    retry safe here and unsafe almost everywhere else.
    """

    return (
        len(command) >= 3
        and Path(command[0]).name in {"uv", "uv.exe"}
        and command[1] == "sync"
        and "--locked" in command
    )


def _is_transient_dependency_fetch(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in _TRANSIENT_DEPENDENCY_FETCH_MARKERS)


def _run(
    command: list[str],
    cwd: Path,
    *,
    language: str,
    kind: str = "build-analysis",
    timeout_seconds: int | None = None,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    if timeout_seconds is None:
        timeout_seconds = _configured_command_timeout_seconds()
    if not 30 <= timeout_seconds <= 900:
        raise ValueError("COMMAND_TIMEOUT_OUT_OF_RANGE")
    effective_command = list(command)
    if language == "kotlin" and effective_command and Path(effective_command[0]).name == "gradle":
        effective_command[1:1] = [
            *_gradle_proxy_system_properties(),
            *_gradle_repository_property(),
        ]
    try:
        process_environment = os.environ.copy()
        process_environment.update(environment or {})
        if language == "go":
            gomod_cache, go_cache = _go_module_cache_roots(cwd)
            process_environment["GOMODCACHE"] = str(gomod_cache)
            process_environment["GOCACHE"] = str(go_cache)
        # An ambient virtualenv from the synthesis engine is never the
        # generated workspace's environment. Let uv/direct workspace tools
        # resolve the generated `.venv` without inheriting a misleading path.
        if language == "python":
            process_environment.pop("VIRTUAL_ENV", None)
            # Use the host trust store for the public PyPI connection. This is
            # the uv-supported path behind managed TLS proxies and avoids
            # rustls `close_notify` failures observed on otherwise valid HTTPS.
            process_environment["UV_NATIVE_TLS"] = "true"
        if language == "kotlin" and not os.environ.get("ELMOS_PROJECT_SYNTHESIS_GRADLE_PROXY"):
            # Gradle may consume ambient shell proxy variables even when no JVM
            # proxy properties were requested. Keep the default Maven Central
            # path direct; an explicitly reviewed Gradle proxy remains opt-in.
            for proxy_name in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            ):
                process_environment.pop(proxy_name, None)
        retry_notes: list[str] = []
        attempt = 0
        while True:
            completed = subprocess.run(  # noqa: S603
                effective_command,
                cwd=cwd,
                env=process_environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
            attempt_output = completed.stdout + completed.stderr
            if (
                completed.returncode == 0
                or attempt >= _MAX_TRANSIENT_DEPENDENCY_RETRIES
                or language != "python"
                or not _is_locked_dependency_sync(effective_command)
                or not _is_transient_dependency_fetch(attempt_output)
            ):
                break
            attempt += 1
            # Kept in the output on purpose: a PASSED result that needed a
            # retry must not look identical to one that succeeded first time.
            retry_notes.append(
                f"TRANSIENT_DEPENDENCY_FETCH_RETRY:{attempt}/"
                f"{_MAX_TRANSIENT_DEPENDENCY_RETRIES}\n{attempt_output}"
            )
            time.sleep(_TRANSIENT_DEPENDENCY_RETRY_BACKOFF_SECONDS)
    except subprocess.TimeoutExpired as error:
        stdout = (
            error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
        )
        stderr = (
            error.stderr.decode("utf-8", errors="replace") if isinstance(error.stderr, bytes) else error.stderr or ""
        )
        return _result(
            language=language,
            kind=kind,
            command=effective_command,
            status="FAILED",
            exit_code=None,
            output=f"COMMAND_TIMEOUT:{timeout_seconds}s\n{stdout}{stderr}",
        )
    output = "".join(retry_notes) + completed.stdout + completed.stderr
    return _result(
        language=language,
        kind=kind,
        command=effective_command,
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


def _python_lock_cache_path(python_workspace: Path) -> Path:
    pyproject = python_workspace / "pyproject.toml"
    digest = hashlib.sha256(pyproject.read_bytes()).hexdigest()
    configured = os.getenv("ELMOS_PROJECT_SYNTHESIS_LOCK_CACHE", "").strip()
    cache_root = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".cache" / "elmos" / "project-synthesis" / "locks"
    )
    if not cache_root.is_absolute() or cache_root.is_symlink():
        raise RuntimeError("PYTHON_LOCK_CACHE_PATH_UNSAFE")
    cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache_root.chmod(0o700)
    resolved = cache_root.resolve(strict=True)
    if resolved.is_symlink():
        raise RuntimeError("PYTHON_LOCK_CACHE_PATH_UNSAFE")
    return resolved / f"{digest}.lock"


def _restore_cached_python_lock(python_workspace: Path) -> bool:
    cached = _python_lock_cache_path(python_workspace)
    if not cached.exists():
        return False
    if cached.is_symlink() or not cached.is_file():
        raise RuntimeError("PYTHON_LOCK_CACHE_ENTRY_UNSAFE")
    details = cached.stat()
    if details.st_size <= 0 or details.st_size > 2_000_000 or details.st_mode & 0o077:
        raise RuntimeError("PYTHON_LOCK_CACHE_ENTRY_UNSAFE")
    (python_workspace / "uv.lock").write_bytes(cached.read_bytes())
    return True


def _store_cached_python_lock(python_workspace: Path) -> None:
    source = python_workspace / "uv.lock"
    if source.is_symlink() or not source.is_file() or not 0 < source.stat().st_size <= 2_000_000:
        raise RuntimeError("GENERATED_PYTHON_LOCK_INVALID")
    cached = _python_lock_cache_path(python_workspace)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=cached.parent,
            prefix=f".{cached.name}.",
            delete=False,
        ) as temporary:
            temporary.write(source.read_bytes())
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, cached)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


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


def _toolchain_environment(language: str) -> dict[str, str]:
    if language == "typescript":
        # Generated starter profiles use only the public npm registry. Pinning
        # it prevents an ambient mirror from stalling deterministic lockfile
        # generation or silently changing the package source.
        return {"npm_config_registry": "https://registry.npmjs.org"}
    if language != "kotlin":
        return {}
    java = _runtime_tool(language, "java")
    if java is None:
        return {}
    java_binary = Path(java).resolve()
    environment = {
        "JAVA_HOME": str(java_binary.parent.parent),
        "PATH": f"{java_binary.parent}{os.pathsep}{os.environ.get('PATH', '')}",
        "GRADLE_USER_HOME": str(_gradle_user_home()),
    }
    return environment


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


_PROXY_ENVIRONMENT_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def _loopback_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment that cannot proxy local acceptance traffic."""
    result = os.environ.copy()
    result.update(environment or {})
    for name in _PROXY_ENVIRONMENT_NAMES:
        result.pop(name, None)
    result["NO_PROXY"] = "127.0.0.1,localhost"
    result["no_proxy"] = "127.0.0.1,localhost"
    return result


#: Same bound the probe has always reported; only *when* it is read changed.
_PROBE_OUTPUT_TAIL_CHARACTERS = 6_000


def _drain_tail(stream: Any, sink: list[str], limit: int) -> None:
    """Read `stream` to EOF, keeping only its last `limit` characters.

    Runs on a thread for the whole life of the probed process so the pipe
    never fills. Appends exactly one element to `sink` when it is done.
    """

    tail = ""
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            tail = (tail + chunk)[-limit:]
    except (OSError, ValueError):
        # The pipe was closed under us while shutting the process down; the
        # tail collected so far is still the right thing to report.
        pass
    sink.append(tail)


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
    requires_integration: bool = False,
    blocking_reason: str | None = None,
    startup_timeout_seconds: int = 30,
    integration_timeout_seconds: int = 120,
) -> dict[str, Any]:
    # The runtime and integration endpoints are loopback-only. An inherited
    # developer/CI proxy can turn a healthy response into a proxy-generated
    # 502 and is an unnecessary egress path for local test credentials.
    env = _loopback_environment(environment)
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    # THE PIPE MUST BE DRAINED WHILE THE CHILD RUNS.
    #
    # An OS pipe holds about 64 KiB. Reading it only after the startup deadline
    # means a service that logs more than that during startup blocks forever
    # inside its own `write`, never reaches the point where it answers
    # /health, and is then reported as a startup FAILURE -- a healthy service
    # that this probe wedged. The reader keeps the same bounded tail the
    # `finally` block used to take, so nothing downstream changes.
    captured_tail: list[str] = []
    reader = threading.Thread(
        target=_drain_tail,
        args=(process.stdout, captured_tail, _PROBE_OUTPUT_TAIL_CHARACTERS),
        daemon=True,
    )
    reader.start()
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
                    timeout=integration_timeout_seconds,
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
        if requires_integration and integration_status == "NOT_RUN" and status == "PASSED":
            # Answering /health is not the evidence a production profile owes.
            # Without this the probe reports PASSED for a target whose tenant
            # isolation scenario never executed, which is how an unregistered
            # target silently earns a green light.
            if blocking_reason is not None:
                status = "NOT_RUN"
                integration_output = f"INTEGRATION_SCENARIO_NOT_RUN:{blocking_reason}"
            else:
                status = "FAILED"
                integration_output = (
                    "INTEGRATION_SCENARIO_REQUIRED_BUT_NOT_EXECUTED:"
                    f"{language}\nNo integration command was declared for this "
                    "target, so the production scenario never ran."
                )
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
        # The child is gone, so the reader sees EOF and finishes. Bounded
        # join: a wedged reader must not wedge the probe in turn.
        reader.join(timeout=5)
        output = captured_tail[0] if captured_tail else ""
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


_HARNESS_DIRECTORIES = {
    "java": "java",
    "csharp": "dotnet",
    "typescript": "typescript",
    "go": "go",
    "kotlin": "kotlin",
    "php": "php",
    "rust": "rust",
}

# The integration scenario runs against the database the harness already
# provisioned and left running, so each entry is the target's own test runner,
# never a second harness invocation. Re-running the harness here would try to
# start a second PostgreSQL on the same data directory.
_HARNESS_INTEGRATION_COMMANDS: dict[str, tuple[str, list[str]]] = {
    "java": ("mvn", ["-B", "test", "-Pintegration"]),
    "go": ("go", ["test", "-tags", "integration", "-count=1", "./..."]),
    "typescript": ("pnpm", ["exec", "node", "--test", "dist/integration.test.js"]),
    # The command-line filter overrides the VSTestTestCaseFilter property the
    # test project sets, which is what keeps a plain `dotnet test` offline.
    "csharp": ("dotnet", ["test", "-c", "Release", "--filter", "Category=Integration"]),
    # A dedicated task rather than `test`, whose JUnit platform config excludes
    # the integration tag so a plain `gradle test` stays database free.
    "kotlin": ("gradle", ["--no-daemon", "--offline", "integrationTest"]),
    # A separate entrypoint from tests/run.php, which stays offline and
    # database free so the standard verification pass needs no server.
    "php": ("php", ["tests/integration.php"]),
    # Rust has no test tags, so the scenario is `#[ignore]`d to keep a plain
    # `cargo test` offline and the harness opts into it explicitly. `--release`
    # matches the profile the workspace runner starts the server with, so the
    # integration run reuses those artifacts instead of rebuilding in debug.
    "rust": (
        "cargo",
        [
            "test",
            "--locked",
            "--release",
            "--test",
            "production_integration",
            "--",
            "--ignored",
        ],
    ),
}


_INTEGRATION_TIMEOUT_SECONDS: dict[str, int] = {
    "rust": 300,
    "kotlin": 300,
    "csharp": 240,
    "java": 240,
}

# Python declares its integration command inline in ``runtime_commands``
# because it also owns the in-memory runtime shape; every other target is
# declared in the table above.
_INLINE_INTEGRATION_LANGUAGES = frozenset({"python"})


def undeclared_integration_targets() -> frozenset[str]:
    """Profile-open targets with no way to run the production scenario.

    A target opened in ``SUPPORTED_PROFILE_TARGETS`` but missing here would
    start the server, answer ``/health`` and never execute the tenant isolation
    scenario. The probe now refuses to call that a pass, and this function
    lets the test suite catch the omission before a run does.
    """
    declared = set(_HARNESS_INTEGRATION_COMMANDS) | _INLINE_INTEGRATION_LANGUAGES
    opened: set[str] = set()
    for (persistence, _auth_mode), languages in SUPPORTED_PROFILE_TARGETS.items():
        if persistence != "in-memory":
            opened |= set(languages)
    return frozenset(opened - declared)


def _language_tool_paths(language: str) -> list[str] | None:
    """Resolve every tool a language declares, or None when one is missing."""
    resolved: list[str] = []
    for requirement in EXACT_TOOLCHAIN_REQUIREMENTS.get(language, []):
        matched, _ = _matching_tool(requirement)
        if matched is None:
            return None
        resolved.append(matched)
    return resolved


def _harness_environment(language: str, tools: list[str]) -> dict[str, str]:
    """PATH and JAVA_HOME the harness needs to launch the target.

    The harness is a plain Python script, so the toolchain it shells out to has
    to be reachable from PATH. Prepending the exact resolved binaries keeps the
    child process on the same versions the toolchain gate matched, instead of
    whatever happens to be first on the ambient PATH.
    """
    directories = [str(Path(tool).resolve().parent) for tool in tools]
    postgres = _resolve_tool("postgres", "/opt/homebrew/opt/postgresql@17/bin/postgres")
    if postgres is not None:
        directories.append(str(Path(postgres).resolve().parent))
    environment = {
        "PATH": os.pathsep.join([*dict.fromkeys(directories), os.environ.get("PATH", "")]),
    }
    java = next((tool for tool in tools if Path(tool).name == "java"), None)
    if java is not None:
        environment["JAVA_HOME"] = str(Path(java).resolve().parent.parent)
    if language == "kotlin":
        environment["GRADLE_USER_HOME"] = str(_gradle_user_home())
    if language == "typescript":
        # pnpm writes its store under HOME; keep it on the ambient one rather
        # than letting a sandboxed HOME break `pnpm install`.
        environment.setdefault("HOME", os.environ.get("HOME", ""))
    return environment


def _harness_runtime_plan(
    root: Path,
    language: str,
    port: int,
    auth_mode: str | None,
) -> dict[str, Any] | None:
    """Drive a PostgreSQL-backed target through its shared runtime harness.

    Python is deliberately excluded: it already has a verified `uv run` launch
    path, and routing it here would change a fixture that is currently green.

    python3 is resolved directly rather than through `_runtime_tool`, because
    that helper is keyed by language and returns None for any language whose
    own toolchain gate has not matched -- which would silently downgrade the
    plan to NOT_RUN for a reason that has nothing to do with the harness.
    """
    directory = _HARNESS_DIRECTORIES.get(language)
    if directory is None:
        return None
    workspace = root / directory
    if not (workspace / "scripts" / "local_runtime.py").is_file():
        return None

    interpreter = _resolve_tool("python3", "/usr/bin/python3")
    tools = _language_tool_paths(language)
    integration = _HARNESS_INTEGRATION_COMMANDS.get(language)
    postgres_ready = _resolve_tool("postgres", "/opt/homebrew/opt/postgresql@17/bin/postgres") is not None

    blocking: str | None = None
    if interpreter is None:
        blocking = "EXACT_TOOLCHAIN_NOT_AVAILABLE:harness:python3"
    elif tools is None:
        blocking = f"EXACT_TOOLCHAIN_NOT_AVAILABLE:{language}"
    elif integration is None:
        blocking = f"HARNESS_INTEGRATION_COMMAND_UNDECLARED:{language}"
    elif not postgres_ready:
        blocking = "EXACT_TOOLCHAIN_NOT_AVAILABLE:postgresql:postgres"

    state = workspace / ".elmos-runtime"
    # The harness writes exactly these paths; the integration runner reads the
    # same ones so it joins the running database instead of provisioning a new
    # one on the same data directory.
    integration_environment = {
        ENV_DATABASE_URL_FILE: str(state / "database-url"),
        ENV_AUTH_ISSUER: LOCAL_ISSUER,
        ENV_AUTH_AUDIENCE: LOCAL_AUDIENCE,
    }
    if auth_mode == "jwt":
        integration_environment[ENV_JWT_SECRET_FILE] = str(state / "jwt-hmac")
    elif auth_mode == "oidc":
        integration_environment[ENV_OIDC_JWKS_FILE] = str(state / "oidc-jwks.json")
        integration_environment[ENV_OIDC_PRIVATE_KEY_FILE] = str(state / "oidc-private-key.pem")

    if blocking is not None:
        return {
            "language": language,
            "cwd": str(workspace),
            "command": [interpreter or "python3", "scripts/local_runtime.py"],
            "environment": {"PORT": str(port), ENV_RUNTIME_STATE_DIR: str(state)},
            "providers": ["postgresql"],
            "port": port,
            # A production profile owes integration evidence. Recording that
            # obligation here -- even on the blocked plan -- stops a probe that
            # merely answered /health from being reported as a pass.
            "requires_integration": True,
            "execution_status": "NOT_RUN",
            "blocking_reason": blocking,
        }

    assert interpreter is not None and tools is not None and integration is not None
    runner_name, runner_arguments = integration
    runner = next((tool for tool in tools if Path(tool).name == runner_name), None) or runner_name
    return {
        "language": language,
        "cwd": str(workspace),
        "command": [interpreter, "scripts/local_runtime.py"],
        "environment": {
            "PORT": str(port),
            "HOST": "127.0.0.1",
            "SERVER_ADDRESS": "127.0.0.1",
            ENV_RUNTIME_STATE_DIR: str(state),
            **_harness_environment(language, tools),
        },
        "providers": ["postgresql"],
        "port": port,
        "startup_timeout_seconds": 180,
        "requires_integration": True,
        "integration_command": [runner, *runner_arguments],
        "integration_environment": integration_environment,
        # Compiled targets build their integration binary as part of this step.
        # On a cold cache that is comfortably slower than an interpreted test
        # run, and a timeout here would look like a scenario failure rather
        # than the build it actually is.
        "integration_timeout_seconds": _INTEGRATION_TIMEOUT_SECONDS.get(language, 120),
        "execution_status": "READY",
    }


def runtime_commands(
    workspace: Path,
    *,
    port_overrides: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    root = workspace.resolve(strict=True)
    applications = _blueprint(root).get("applications", [])
    application_languages = {
        str(application["language"])
        for application in applications
        if isinstance(application, dict) and isinstance(application.get("language"), str)
    }
    overrides = dict(port_overrides or {})
    unknown_languages = set(overrides) - application_languages
    if unknown_languages:
        raise ValueError(f"RUNTIME_PORT_OVERRIDE_LANGUAGE_UNKNOWN:{','.join(sorted(unknown_languages))}")
    for language, override in overrides.items():
        if isinstance(override, bool) or not isinstance(override, int) or not 1024 <= override <= 65535:
            raise ValueError(f"RUNTIME_PORT_OVERRIDE_INVALID:{language}:{override}")
    commands: list[dict[str, Any]] = []
    for application in applications:
        language = application.get("language")
        port = application.get("port")
        if not isinstance(language, str) or not isinstance(port, int):
            continue
        port = overrides.get(language, port)
        if application.get("storage") == "postgresql" and language != "python":
            harness_plan = _harness_runtime_plan(
                root,
                language,
                port,
                application.get("auth_mode") if isinstance(application.get("auth_mode"), str) else None,
            )
            if harness_plan is not None:
                commands.append(harness_plan)
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
                        # A Spring Boot fat jar cold start costs far more than
                        # the 30s default, especially while the other seven
                        # targets are still building. Kotlin already carries a
                        # raised budget for the same JVM startup; java was left
                        # on the default and fails intermittently as a result --
                        # a timeout that looks exactly like a broken target.
                        "startup_timeout_seconds": 120,
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
                    plan["requires_integration"] = True
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
                            "--no-launch-profile",
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
                    "command": [
                        tool,
                        *_gradle_proxy_system_properties(),
                        "--no-daemon",
                        "run",
                    ],
                    "environment": {
                        "PORT": str(port),
                        "HOST": "127.0.0.1",
                        **_toolchain_environment("kotlin"),
                    },
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
    tool = _runtime_tool(language, tool_name)
    if tool is None:
        results.append(_missing(language, tool_name))
        return False
    for arguments in commands:
        command = [tool, *arguments]
        result = _run(
            command,
            cwd,
            language=language,
            timeout_seconds=600 if language in {"kotlin", "rust"} else 300,
            environment=_toolchain_environment(language),
        )
        results.append(result)
        if result["status"] != "PASSED":
            return False
    return True


def verify_workspace(
    workspace: Path,
    *,
    use_ephemeral_runtime_ports: bool = False,
) -> dict[str, Any]:
    root = workspace.resolve(strict=True)
    # Validate all digest-bound generated structure contracts before resolving
    # or executing any native toolchain command.
    validate_workspace_graphs(root)
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
            python_workspace = root / "python"
            venv_bin = python_workspace / ".venv" / ("Scripts" if os.name == "nt" else "bin")
            executable_suffix = ".exe" if os.name == "nt" else ""
            lock_was_cached = _restore_cached_python_lock(python_workspace)
            python_commands = (
                [tool, "lock", "--check"] if lock_was_cached else [tool, "lock"],
                [tool, "sync", "--locked", "--python", "3.12"],
                [str(venv_bin / f"python{executable_suffix}"), "--version"],
                [str(venv_bin / f"pytest{executable_suffix}"), "-m", "not integration"],
                [str(venv_bin / f"ruff{executable_suffix}"), "check", "src", "tests"],
                [str(venv_bin / f"mypy{executable_suffix}"), "src"],
            )
            for index, command in enumerate(python_commands):
                result = _run(command, python_workspace, language="python")
                results.append(result)
                if result["status"] != "PASSED":
                    break
                if index == 0 and not lock_was_cached:
                    _store_cached_python_lock(python_workspace)
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

    rust_production_profile = any(
        isinstance(item, dict) and item.get("language") == "rust" and item.get("storage") == "postgresql"
        for item in applications
    )
    rust_release_arguments = ["--release"] if rust_production_profile else []
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
        "kotlin": ("gradle", [["--no-daemon", "test", "build"]]),
        # Deliberately shape-agnostic: the starter profile names its class
        # src/Store.php while the production profile names it after the
        # entity, so linting a hardcoded path would fail on one of them.
        # tests/run.php requires every class it needs, which makes running it
        # a parse check over the whole workspace -- `php -l` does not follow
        # requires.
        "php": ("php", [["-l", "public/index.php"], ["tests/run.php"]]),
        "rust": (
            "cargo",
            [
                ["fmt", "--check"],
                [
                    "clippy",
                    "--locked",
                    *rust_release_arguments,
                    "--all-targets",
                    "--all-features",
                    "--",
                    "-D",
                    "warnings",
                ],
                ["test", "--locked", *rust_release_arguments, "--all-features"],
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
    runtime_port_overrides: dict[str, int] | None = None
    if use_ephemeral_runtime_ports:
        runtime_port_overrides = {}
        for language in sorted(selected):
            with socket.socket() as port_probe:
                port_probe.bind(("127.0.0.1", 0))
                runtime_port_overrides[language] = int(port_probe.getsockname()[1])
    for plan in runtime_commands(root, port_overrides=runtime_port_overrides):
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
                requires_integration=bool(plan.get("requires_integration", False)),
                blocking_reason=(
                    str(plan["blocking_reason"]) if isinstance(plan.get("blocking_reason"), str) else None
                ),
                startup_timeout_seconds=int(plan.get("startup_timeout_seconds", 30)),
                integration_timeout_seconds=int(plan.get("integration_timeout_seconds", 120)),
            )
        )

    statuses = {str(result["status"]) for result in results}
    status = "FAILED" if "FAILED" in statuses else "PARTIAL" if "NOT_RUN" in statuses else "PASSED"
    tools = {
        name: (_resolve_tool(name) is not None)
        for name in ("java", "mvn", "uv", "dotnet", "node", "pnpm", "go", "gradle", "php", "cargo")
    }
    evidence: dict[str, Any] = {
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
    evidence["insights"] = verified_generation_insights(root, evidence)
    return evidence
