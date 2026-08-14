#!/usr/bin/env python3
"""Task-scoped ELMOS language runtime discovery and provisioning.

The manifest contains versions, profile membership, and evidence boundaries.
This module owns a small allowlist of read-only version probes so repository
data cannot turn the doctor into a generic command runner.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "toolchains" / "runtime-manifest.json"
INSTALLER_PATH = ROOT / "scripts" / "toolchains" / "install_project_synthesis_toolchains.sh"

ACTIVE_POLICIES = frozenset({"managed-or-host", "repository-lock", "host-apple"})
NON_EXECUTING_POLICIES = frozenset(
    {"profile-selected", "container-profile", "vendor-external", "external-service"}
)
INSTALL_POLICIES = ACTIVE_POLICIES | NON_EXECUTING_POLICIES
REQUIRED_PROFILES = frozenset(
    {"core", "synthesis", "routes-macos", "b66-80", "spring-legacy", "frontend-native", "language-packs", "all"}
)
SYNTHESIS_LANGUAGES = frozenset(
    {"java", "python", "csharp", "typescript", "go", "kotlin", "php", "rust"}
)
ROUTE_LANGUAGES = frozenset(
    {
        "java",
        "python",
        "csharp",
        "typescript",
        "javascript",
        "go",
        "rust",
        "cpp",
        "objc",
        "swift",
    }
)
KNOWN_APPLICATION_LANGUAGES = SYNTHESIS_LANGUAGES | ROUTE_LANGUAGES
# Node is shared by the TypeScript synthesis toolchain and the independent
# JavaScript route toolchain.  Its manifest language list is intentionally
# broader than the synthesis product surface, so profile validation must not
# turn runtime availability into a JavaScript Project Synthesis claim.
SYNTHESIS_EXCLUDED_SHARED_LANGUAGES = frozenset({"javascript"})
AUTOMATED_INSTALL_PROFILES = frozenset({"core", "synthesis", "routes-macos", "all"})


@dataclass(frozen=True)
class ProbeCommand:
    executable: str
    arguments: tuple[str, ...]
    path_names: tuple[str, ...] = ()
    candidate_templates: tuple[str, ...] = ()
    executable_env: str | None = None
    home_env: str | None = None
    allow_repository_executable: bool = False


PROBE_COMMANDS: dict[str, ProbeCommand] = {
    "java": ProbeCommand(
        "java",
        ("-version",),
        ("java",),
        (
            "{toolchain_root}/java/21.0.11/bin/java",
            "/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home/bin/java",
            "/opt/homebrew/opt/openjdk@21/bin/java",
            "{home}/.sdkman/candidates/java/21.0.11-tem/bin/java",
            "{home}/.sdkman/candidates/java/current/bin/java",
        ),
        home_env="ELMOS_JAVA21_HOME",
    ),
    "javac": ProbeCommand(
        "javac",
        ("-version",),
        ("javac",),
        (
            "{toolchain_root}/java/21.0.11/bin/javac",
            "/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home/bin/javac",
            "/opt/homebrew/opt/openjdk@21/bin/javac",
            "{home}/.sdkman/candidates/java/21.0.11-tem/bin/javac",
            "{home}/.sdkman/candidates/java/current/bin/javac",
        ),
        home_env="ELMOS_JAVA21_HOME",
    ),
    "maven": ProbeCommand(
        "mvn",
        ("--version",),
        ("mvn",),
        (
            "{toolchain_root}/maven/3.9.10/bin/mvn",
            "/opt/homebrew/bin/mvn",
            "{home}/.sdkman/candidates/maven/3.9.10/bin/mvn",
            "{home}/.sdkman/candidates/maven/current/bin/mvn",
        ),
    ),
    "python314": ProbeCommand(
        "python3.14",
        ("--version",),
        ("python3.14", "python3"),
        (
            "{toolchain_root}/python/3.14.6/bin/python3.14",
            "{repo_root}/engines/python-engine/.venv/bin/python",
            "/opt/homebrew/opt/python@3.14/bin/python3.14",
            "/opt/homebrew/bin/python3",
        ),
        executable_env="ELMOS_PYTHON314",
    ),
    "python312": ProbeCommand(
        "python3.12",
        ("--version",),
        ("python3.12",),
        (
            "{toolchain_root}/python/3.12.12/bin/python3.12",
            "{repo_root}/engines/polyglot-route-engine/.venv/bin/python",
            "{repo_root}/engines/project-synthesis-engine/.venv/bin/python",
            "/opt/homebrew/opt/python@3.12/bin/python3.12",
        ),
        executable_env="ELMOS_PYTHON312",
        allow_repository_executable=True,
    ),
    "uv": ProbeCommand("uv", ("--version",), ("uv",), ("/opt/homebrew/bin/uv",)),
    "dotnet": ProbeCommand(
        "dotnet",
        ("--version",),
        ("dotnet",),
        (
            "{toolchain_root}/dotnet/10.0.301/dotnet",
            "/opt/homebrew/Cellar/dotnet/10.0.301/libexec/dotnet",
            "/opt/homebrew/bin/dotnet",
        ),
        executable_env="ELMOS_DOTNET",
    ),
    "node": ProbeCommand(
        "node",
        ("--version",),
        ("node",),
        ("{toolchain_root}/node/26.0.0/bin/node", "/opt/homebrew/bin/node"),
        executable_env="ELMOS_NODE26",
    ),
    "pnpm": ProbeCommand(
        "pnpm",
        ("--version",),
        ("pnpm",),
        ("{toolchain_root}/node/26.0.0/bin/pnpm", "/opt/homebrew/bin/pnpm"),
        executable_env="ELMOS_PNPM",
    ),
    "tsc": ProbeCommand(
        "tsc",
        ("--version",),
        ("tsc",),
        (
            "{repo_root}/engines/frontend-client-engine/node_modules/.bin/tsc",
            "{repo_root}/apps/web-console/node_modules/.bin/tsc",
        ),
        allow_repository_executable=True,
    ),
    "go": ProbeCommand(
        "go",
        ("version",),
        ("go",),
        ("{toolchain_root}/go/1.25.0/bin/go", "{home}/.local/bin/go"),
        executable_env="ELMOS_GO",
    ),
    "gradle": ProbeCommand(
        "gradle",
        ("--version",),
        ("gradle",),
        ("{toolchain_root}/gradle/8.14.3/bin/gradle", "/opt/homebrew/bin/gradle"),
        executable_env="ELMOS_GRADLE",
    ),
    "php": ProbeCommand(
        "php",
        ("--version",),
        ("php",),
        ("{toolchain_root}/php/8.4.12/bin/php", "/opt/homebrew/bin/php"),
        executable_env="ELMOS_PHP",
    ),
    "php-modules": ProbeCommand(
        "php",
        ("-m",),
        ("php",),
        ("{toolchain_root}/php/8.4.12/bin/php", "/opt/homebrew/bin/php"),
        executable_env="ELMOS_PHP",
    ),
    "rustc": ProbeCommand(
        "rustc",
        ("--version",),
        ("rustc",),
        ("{toolchain_root}/rust/1.89.0/bin/rustc", "{home}/.local/bin/rustc"),
        executable_env="ELMOS_RUSTC",
    ),
    "cargo": ProbeCommand(
        "cargo",
        ("--version",),
        ("cargo",),
        ("{toolchain_root}/rust/1.89.0/bin/cargo", "{home}/.local/bin/cargo"),
        executable_env="ELMOS_CARGO",
    ),
    "rust-components": ProbeCommand(
        "rustup",
        ("component", "list", "--installed"),
        ("rustup",),
        ("{toolchain_root}/rust/1.89.0/bin/rustup", "{home}/.local/bin/rustup"),
        executable_env="ELMOS_RUSTUP",
    ),
    "postgres": ProbeCommand(
        "postgres",
        ("--version",),
        ("postgres",),
        (
            "{toolchain_root}/postgresql/17.5/bin/postgres",
            "/opt/homebrew/opt/postgresql@17/bin/postgres",
        ),
        executable_env="ELMOS_POSTGRES",
    ),
    "psql": ProbeCommand(
        "psql",
        ("--version",),
        ("psql",),
        (
            "{toolchain_root}/postgresql/17.5/bin/psql",
            "/opt/homebrew/opt/postgresql@17/bin/psql",
        ),
        executable_env="ELMOS_PSQL",
    ),
    "xcode": ProbeCommand("xcodebuild", ("-version",), (), ("/usr/bin/xcodebuild",)),
    "macos-sdk": ProbeCommand(
        "xcrun", ("--sdk", "macosx", "--show-sdk-version"), (), ("/usr/bin/xcrun",)
    ),
    "clang": ProbeCommand("xcrun", ("clang", "--version"), (), ("/usr/bin/xcrun",)),
    "swift": ProbeCommand("xcrun", ("swiftc", "--version"), (), ("/usr/bin/xcrun",)),
    "flutter": ProbeCommand("flutter", ("--version",), ("flutter",), ("/opt/homebrew/bin/flutter",)),
    "bash": ProbeCommand("bash", ("--version",), ("bash",), ("/opt/homebrew/bin/bash", "/bin/bash")),
    "zsh": ProbeCommand("zsh", ("--version",), ("zsh",), ("/bin/zsh",)),
    "pwsh": ProbeCommand(
        "pwsh",
        ("-NoLogo", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"),
        ("pwsh",),
        ("/opt/homebrew/bin/pwsh",),
    ),
    "cmake": ProbeCommand("cmake", ("--version",), ("cmake",), ("/opt/homebrew/bin/cmake",)),
    "ninja": ProbeCommand("ninja", ("--version",), ("ninja",), ("/opt/homebrew/bin/ninja",)),
    "docker": ProbeCommand("docker", ("--version",), ("docker",), ("/usr/local/bin/docker",)),
    "docker-compose": ProbeCommand(
        "docker", ("compose", "version"), ("docker",), ("/usr/local/bin/docker",)
    ),
    "terraform": ProbeCommand(
        "terraform", ("version",), ("terraform",), ("/opt/homebrew/bin/terraform",)
    ),
    "kubectl": ProbeCommand(
        "kubectl",
        ("version", "--client", "--output=yaml"),
        ("kubectl",),
        ("/opt/homebrew/bin/kubectl",),
    ),
    "helm": ProbeCommand("helm", ("version", "--short"), ("helm",), ("/opt/homebrew/bin/helm",)),
    "cobc": ProbeCommand("cobc", ("-V",), ("cobc",)),
    "omc": ProbeCommand("omc", ("--version",), ("omc",)),
    "rscript": ProbeCommand("Rscript", ("--version",), ("Rscript",)),
    "salesforce": ProbeCommand("sf", ("--version",), ("sf",)),
    "fpc": ProbeCommand("fpc", ("-iV",), ("fpc",)),
    "erl": ProbeCommand(
        "erl",
        ("-noshell", "-eval", 'io:format("~s", [erlang:system_info(otp_release)]).', "-s", "init", "stop"),
        ("erl",),
        ("/opt/homebrew/bin/erl",),
    ),
    "elixir": ProbeCommand("elixir", ("--version",), ("elixir",)),
    "mix": ProbeCommand("mix", ("--version",), ("mix",)),
    "lua": ProbeCommand("lua", ("-v",), ("lua",), ("/opt/homebrew/bin/lua",)),
    "openresty": ProbeCommand("openresty", ("-V",), ("openresty",)),
}


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """Load one manifest without following a symlinked manifest file."""

    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"RUNTIME_MANIFEST_UNSAFE_OR_MISSING:{candidate}")
    value = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("RUNTIME_MANIFEST_ROOT_MUST_BE_OBJECT")
    return value


def _runtime_index(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    runtimes = manifest.get("runtimes", [])
    if not isinstance(runtimes, list):
        return {}
    return {
        str(runtime.get("id")): runtime
        for runtime in runtimes
        if isinstance(runtime, dict) and isinstance(runtime.get("id"), str)
    }


def _profile_languages(
    manifest: Mapping[str, Any], profile_name: str, *, required_only: bool = True
) -> frozenset[str]:
    profile = manifest.get("profiles", {}).get(profile_name, {})
    identifiers: list[str] = []
    if isinstance(profile, dict):
        required = profile.get("required", [])
        optional = profile.get("optional", [])
        if isinstance(required, list):
            identifiers.extend(str(item) for item in required)
        if not required_only and isinstance(optional, list):
            identifiers.extend(str(item) for item in optional)
    index = _runtime_index(manifest)
    languages: set[str] = set()
    for identifier in identifiers:
        runtime = index.get(identifier, {})
        declared = runtime.get("languages", [])
        if isinstance(declared, list):
            languages.update(str(item) for item in declared)
    return frozenset(languages)


def validate_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Apply fail-closed semantic validation using only the standard library."""

    errors: list[str] = []
    if manifest.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if not isinstance(manifest.get("manifest_id"), str) or not manifest.get("manifest_id"):
        errors.append("manifest_id must be a non-empty string")
    profiles = manifest.get("profiles")
    if not isinstance(profiles, dict):
        errors.append("profiles must be an object")
        profiles = {}
    missing_profiles = sorted(REQUIRED_PROFILES - set(profiles))
    if missing_profiles:
        errors.append(f"missing required profiles: {','.join(missing_profiles)}")

    runtimes = manifest.get("runtimes")
    if not isinstance(runtimes, list) or not runtimes:
        errors.append("runtimes must be a non-empty array")
        runtimes = []
    identifiers: list[str] = []
    for position, runtime in enumerate(runtimes):
        if not isinstance(runtime, dict):
            errors.append(f"runtime[{position}] must be an object")
            continue
        identifier = runtime.get("id")
        if not isinstance(identifier, str) or re.fullmatch(r"[a-z0-9][a-z0-9.-]+", identifier) is None:
            errors.append(f"runtime[{position}] has an invalid id")
            continue
        identifiers.append(identifier)
        policy = runtime.get("install_policy")
        if policy not in INSTALL_POLICIES:
            errors.append(f"runtime {identifier} has unsupported install_policy: {policy}")
        platforms = runtime.get("platforms")
        if not isinstance(platforms, list) or not platforms or not all(isinstance(item, str) for item in platforms):
            errors.append(f"runtime {identifier} must declare platforms")
        languages = runtime.get("languages")
        if not isinstance(languages, list) or not all(isinstance(item, str) and item for item in languages):
            errors.append(f"runtime {identifier} languages must be strings")
        probes = runtime.get("probes", [])
        observations = runtime.get("observational_probes", [])
        if policy in ACTIVE_POLICIES and not isinstance(probes, list):
            errors.append(f"active runtime {identifier} probes must be an array")
        if policy in ACTIVE_POLICIES and not probes:
            errors.append(f"active runtime {identifier} requires at least one probe")
        if policy in NON_EXECUTING_POLICIES and probes:
            errors.append(f"non-executing runtime {identifier} may only use observational_probes")
        for label, declared_probes in (("probes", probes), ("observational_probes", observations)):
            if not isinstance(declared_probes, list):
                errors.append(f"runtime {identifier} {label} must be an array")
                continue
            for probe_position, probe in enumerate(declared_probes):
                if not isinstance(probe, dict):
                    errors.append(f"runtime {identifier} {label}[{probe_position}] must be an object")
                    continue
                probe_id = probe.get("id")
                if probe_id not in PROBE_COMMANDS:
                    errors.append(f"runtime {identifier} uses unallowlisted probe: {probe_id}")
                pattern = probe.get("pattern")
                if not isinstance(pattern, str) or not pattern:
                    errors.append(f"runtime {identifier} probe {probe_id} has no pattern")
                else:
                    try:
                        re.compile(pattern)
                    except re.error as error:
                        errors.append(f"runtime {identifier} probe {probe_id} pattern is invalid: {error}")
                if not isinstance(probe.get("expected"), str) or not probe.get("expected"):
                    errors.append(f"runtime {identifier} probe {probe_id} has no expected value")

    duplicate_ids = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
    if duplicate_ids:
        errors.append(f"duplicate runtime ids: {','.join(duplicate_ids)}")
    known_ids = set(identifiers)
    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            errors.append(f"profile {profile_name} must be an object")
            continue
        required = profile.get("required", [])
        optional = profile.get("optional", [])
        if not isinstance(required, list) or not isinstance(optional, list):
            errors.append(f"profile {profile_name} required/optional must be arrays")
            continue
        missing = sorted((set(required) | set(optional)) - known_ids)
        if missing:
            errors.append(f"profile {profile_name} references unknown runtimes: {','.join(missing)}")
        overlap = sorted(set(required) & set(optional))
        if overlap:
            errors.append(f"profile {profile_name} repeats required runtimes as optional: {','.join(overlap)}")
        external_required = sorted(
            identifier
            for identifier in required
            if _runtime_index(manifest).get(identifier, {}).get("install_policy") in NON_EXECUTING_POLICIES
        )
        if external_required:
            errors.append(
                f"profile {profile_name} cannot require unresolved external runtimes: {','.join(external_required)}"
            )

    synthesis_languages = (
        _profile_languages(manifest, "synthesis") & KNOWN_APPLICATION_LANGUAGES
    ) - SYNTHESIS_EXCLUDED_SHARED_LANGUAGES
    if synthesis_languages != SYNTHESIS_LANGUAGES:
        errors.append(
            "synthesis profile language coverage mismatch: "
            f"expected={','.join(sorted(SYNTHESIS_LANGUAGES))};observed={','.join(sorted(synthesis_languages))}"
        )
    route_languages = _profile_languages(manifest, "routes-macos") & KNOWN_APPLICATION_LANGUAGES
    if route_languages != ROUTE_LANGUAGES:
        errors.append(
            "routes-macos profile language coverage mismatch: "
            f"expected={','.join(sorted(ROUTE_LANGUAGES))};observed={','.join(sorted(route_languages))}"
        )

    bindings = manifest.get("batch_bindings")
    if not isinstance(bindings, dict):
        errors.append("batch_bindings must be an object")
        bindings = {}
    for namespace, expected_numbers in (
        ("b66-80", {str(number) for number in range(66, 81)}),
        ("b81-95", {str(number) for number in range(81, 96)}),
    ):
        declared = bindings.get(namespace)
        if not isinstance(declared, dict):
            errors.append(f"batch_bindings.{namespace} must be an object")
            continue
        if set(declared) != expected_numbers:
            errors.append(
                f"batch_bindings.{namespace} must cover exactly "
                f"{min(expected_numbers)} through {max(expected_numbers)}"
            )
        for batch, runtime_ids in declared.items():
            if not isinstance(runtime_ids, list) or not runtime_ids:
                errors.append(f"batch_bindings.{namespace}.{batch} must be a non-empty array")
                continue
            unknown = sorted(set(runtime_ids) - known_ids)
            if unknown:
                errors.append(
                    f"batch_bindings.{namespace}.{batch} references unknown runtimes: {','.join(unknown)}"
                )
    return errors


def _platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    if system == "darwin":
        return f"darwin-{machine}"
    if system == "linux":
        return f"linux-{machine}"
    if system == "windows":
        return f"windows-{machine}"
    return f"{system}-{machine}"


def _toolchain_root(manifest: Mapping[str, Any], environ: Mapping[str, str]) -> Path:
    variable = str(manifest.get("toolchain_root_env", "ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT"))
    configured = environ.get(variable, "").strip()
    raw = configured or str(manifest.get("default_toolchain_root", "~/.local/share/elmos/toolchains"))
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute() or candidate == Path("/") or candidate == Path.home():
        raise ValueError(f"RUNTIME_TOOLCHAIN_ROOT_UNSAFE:{candidate}")
    return candidate


def _format_template(template: str, *, toolchain_root: Path) -> Path:
    rendered = template.format(
        toolchain_root=toolchain_root,
        repo_root=ROOT,
        home=Path.home(),
    )
    return Path(rendered).expanduser()


def _candidate_executables(
    spec: ProbeCommand,
    *,
    toolchain_root: Path,
    environ: Mapping[str, str],
) -> list[Path]:
    candidates: list[Path] = []
    if spec.executable_env:
        declared = environ.get(spec.executable_env, "").strip()
        if declared:
            candidates.append(Path(declared).expanduser())
    if spec.home_env:
        declared_home = environ.get(spec.home_env, "").strip()
        if declared_home:
            candidates.append(Path(declared_home).expanduser() / "bin" / spec.executable)
    candidates.extend(
        _format_template(template, toolchain_root=toolchain_root)
        for template in spec.candidate_templates
    )
    search_path = environ.get("PATH", os.defpath)
    for name in spec.path_names or (spec.executable,):
        found = shutil.which(name, path=search_path)
        if found:
            candidates.append(Path(found))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        lexical = str(candidate)
        if lexical in seen:
            continue
        seen.add(lexical)
        try:
            details = candidate.lstat()
            resolved = candidate.resolve(strict=True)
            resolved_details = resolved.stat()
        except OSError:
            continue
        if not (stat.S_ISREG(resolved_details.st_mode) and os.access(resolved, os.X_OK)):
            continue
        if stat.S_IMODE(details.st_mode) & 0o002 or stat.S_IMODE(resolved_details.st_mode) & 0o002:
            continue
        try:
            resolved.relative_to(ROOT)
            inside_repository = True
        except ValueError:
            inside_repository = False
        if inside_repository and not spec.allow_repository_executable:
            continue
        unique.append(candidate)
    return unique


def _probe_environment(candidate: Path, environ: Mapping[str, str]) -> dict[str, str]:
    allowed_path_parts = [str(candidate.resolve().parent)]
    for part in environ.get("PATH", os.defpath).split(os.pathsep):
        if part and Path(part).is_absolute() and part not in allowed_path_parts:
            allowed_path_parts.append(part)
    result = dict(environ)
    result.update(
        {
            "PATH": os.pathsep.join(allowed_path_parts),
            "LANG": "C",
            "LC_ALL": "C",
            "TZ": "UTC",
            "NO_COLOR": "1",
            "CLICOLOR": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        }
    )
    for variable in (
        "JAVA_TOOL_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "MAVEN_OPTS",
        "NODE_OPTIONS",
        "RUSTC_WRAPPER",
        "RUSTFLAGS",
        "BASH_ENV",
        "ENV",
        "PROMPT_COMMAND",
    ):
        result.pop(variable, None)
    return result


def _run_probe(
    probe: Mapping[str, Any],
    *,
    toolchain_root: Path,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    probe_id = str(probe.get("id", ""))
    spec = PROBE_COMMANDS[probe_id]
    pattern = str(probe["pattern"])
    observations: list[dict[str, Any]] = []
    candidates = _candidate_executables(spec, toolchain_root=toolchain_root, environ=environ)
    for candidate in candidates:
        command = [str(candidate), *spec.arguments]
        try:
            completed = subprocess.run(  # noqa: S603
                command,
                cwd=ROOT,
                env=_probe_environment(candidate, environ),
                text=True,
                capture_output=True,
                check=False,
                timeout=15,
            )
            output = (completed.stdout + completed.stderr).strip()[:16_384]
            matched = completed.returncode == 0 and re.search(pattern, output) is not None
            observations.append(
                {
                    "command": command,
                    "exit_code": completed.returncode,
                    "matched": matched,
                    "output": output,
                }
            )
            if matched:
                return {
                    "id": probe_id,
                    "expected": probe["expected"],
                    "status": "READY",
                    "selected_executable": str(candidate),
                    "observations": observations,
                }
        except (OSError, subprocess.TimeoutExpired) as error:
            observations.append(
                {
                    "command": command,
                    "exit_code": None,
                    "matched": False,
                    "output": f"{type(error).__name__}:{error}",
                }
            )
    return {
        "id": probe_id,
        "expected": probe.get("expected"),
        "status": "VERSION_MISMATCH" if observations else "NOT_INSTALLED",
        "selected_executable": None,
        "observations": observations,
    }


def _platform_applies(platforms: Sequence[str], platform_key: str) -> bool:
    return "any" in platforms or platform_key in platforms


def _runtime_result(
    runtime: Mapping[str, Any],
    *,
    required: bool,
    platform_key: str,
    toolchain_root: Path,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    policy = str(runtime["install_policy"])
    platforms = [str(item) for item in runtime.get("platforms", [])]
    base = {
        "id": runtime["id"],
        "display_name": runtime["display_name"],
        "languages": runtime.get("languages", []),
        "version": runtime["version"],
        "required": required,
        "install_policy": policy,
        "notes": runtime.get("notes"),
    }
    if not _platform_applies(platforms, platform_key):
        return {
            **base,
            "status": "NOT_APPLICABLE",
            "blocking_reason": f"PLATFORM_NOT_APPLICABLE:{platform_key}",
            "probes": [],
        }
    if policy in NON_EXECUTING_POLICIES:
        observational = [
            _run_probe(probe, toolchain_root=toolchain_root, environ=environ)
            for probe in runtime.get("observational_probes", [])
        ]
        return {
            **base,
            "status": "NOT_RUN",
            "blocking_reason": f"EXACT_TARGET_PROFILE_REQUIRED:{policy}",
            "probes": [],
            "observational_probes": observational,
            "observed_available": bool(observational)
            and all(result["status"] == "READY" for result in observational),
        }
    probe_results = [
        _run_probe(probe, toolchain_root=toolchain_root, environ=environ)
        for probe in runtime.get("probes", [])
    ]
    ready = bool(probe_results) and all(result["status"] == "READY" for result in probe_results)
    if ready:
        status = "READY"
        reason = None
    elif any(result["status"] == "VERSION_MISMATCH" for result in probe_results):
        status = "VERSION_MISMATCH"
        reason = "EXACT_VERSION_NOT_AVAILABLE"
    else:
        status = "NOT_INSTALLED"
        reason = "REQUIRED_TOOL_NOT_FOUND"
    return {**base, "status": status, "blocking_reason": reason, "probes": probe_results}


def doctor(
    manifest: Mapping[str, Any],
    profile: str,
    platform_key: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a read-only, evidence-bounded runtime status report."""

    errors = validate_manifest(manifest)
    if errors:
        raise ValueError("RUNTIME_MANIFEST_INVALID:" + "|".join(errors))
    profiles = manifest["profiles"]
    if profile not in profiles:
        raise ValueError(f"RUNTIME_PROFILE_UNKNOWN:{profile}")
    effective_platform = platform_key or _platform_key()
    profile_definition = profiles[profile]
    allowed_platforms = [str(item) for item in profile_definition.get("platforms", ["any"])]
    observed_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if not _platform_applies(allowed_platforms, effective_platform):
        return {
            "schema_version": "1.0.0",
            "manifest_id": manifest["manifest_id"],
            "profile": profile,
            "platform": effective_platform,
            "observed_at": observed_at,
            "status": "NOT_APPLICABLE",
            "claim_ceiling": "NOT_RUN",
            "summary": {"READY": 0, "NOT_APPLICABLE": 1},
            "runtimes": [],
            "claim_boundary": manifest["claim_boundary"],
        }
    effective_environ = dict(os.environ if environ is None else environ)
    toolchain_root = _toolchain_root(manifest, effective_environ)
    index = _runtime_index(manifest)
    required_ids = [str(item) for item in profile_definition["required"]]
    optional_ids = [str(item) for item in profile_definition["optional"]]
    runtime_results = [
        _runtime_result(
            index[identifier],
            required=identifier in required_ids,
            platform_key=effective_platform,
            toolchain_root=toolchain_root,
            environ=effective_environ,
        )
        for identifier in [*required_ids, *optional_ids]
    ]
    required_failures = [
        result for result in runtime_results if result["required"] and result["status"] != "READY"
    ]
    optional_gaps = [
        result for result in runtime_results if not result["required"] and result["status"] != "READY"
    ]
    if required_failures:
        overall = "BLOCKED"
    elif not required_ids and optional_gaps:
        overall = "NOT_RUN"
    elif optional_gaps:
        overall = "PARTIAL"
    else:
        overall = "READY"
    summary: dict[str, int] = {}
    for result in runtime_results:
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    return {
        "schema_version": "1.0.0",
        "manifest_id": manifest["manifest_id"],
        "profile": profile,
        "platform": effective_platform,
        "toolchain_root": str(toolchain_root),
        "observed_at": observed_at,
        "status": overall,
        "claim_ceiling": "TOOLCHAIN_READY" if overall in {"READY", "PARTIAL"} else "NOT_RUN",
        "summary": summary,
        "runtimes": runtime_results,
        "claim_boundary": manifest["claim_boundary"],
    }


def _matching_executable_for_probe(
    manifest: Mapping[str, Any],
    runtime_id: str,
    probe_id: str,
    environ: Mapping[str, str],
) -> Path | None:
    runtime = _runtime_index(manifest)[runtime_id]
    probe = next((item for item in runtime.get("probes", []) if item.get("id") == probe_id), None)
    if probe is None:
        return None
    result = _run_probe(probe, toolchain_root=_toolchain_root(manifest, environ), environ=environ)
    selected = result.get("selected_executable")
    return Path(selected) if result.get("status") == "READY" and isinstance(selected, str) else None


def _java_home(manifest: Mapping[str, Any], environ: Mapping[str, str]) -> Path | None:
    configured = environ.get("ELMOS_JAVA21_HOME", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if (candidate / "bin" / "java").is_file():
            return candidate
    java = _matching_executable_for_probe(manifest, "java-21", "java", environ)
    if java is None:
        return None
    resolved = java.resolve()
    if resolved.parent.name == "bin":
        return resolved.parent.parent
    return None


def _selected_python(
    manifest: Mapping[str, Any], profile: str, environ: Mapping[str, str]
) -> Path | None:
    profile_ids = set(manifest["profiles"][profile]["required"])
    if "python-3.12.12" in profile_ids and "python-3.14.6" not in profile_ids:
        return _matching_executable_for_probe(manifest, "python-3.12.12", "python312", environ)
    if "python-3.14.6" in profile_ids and "python-3.12.12" not in profile_ids:
        return _matching_executable_for_probe(manifest, "python-3.14.6", "python314", environ)
    return None


def _existing_directories(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        text = str(path)
        if text in seen or not path.is_dir():
            continue
        seen.add(text)
        result.append(path)
    return result


def render_env(
    manifest: Mapping[str, Any],
    profile: str,
    shell: str = "posix",
    environ: Mapping[str, str] | None = None,
) -> str:
    """Render an activation fragment without mutating the caller's shell."""

    errors = validate_manifest(manifest)
    if errors:
        raise ValueError("RUNTIME_MANIFEST_INVALID:" + "|".join(errors))
    if profile not in manifest["profiles"]:
        raise ValueError(f"RUNTIME_PROFILE_UNKNOWN:{profile}")
    if shell != "posix":
        raise ValueError(f"RUNTIME_SHELL_UNSUPPORTED:{shell}")
    effective_environ = dict(os.environ if environ is None else environ)
    root = _toolchain_root(manifest, effective_environ)
    selected_ids = set(manifest["profiles"][profile]["required"])
    candidates: list[Path] = []
    if "go-1.25.0" in selected_ids:
        candidates.append(root / "go" / "1.25.0" / "bin")
    if "kotlin-2.2.20" in selected_ids:
        candidates.append(root / "gradle" / "8.14.3" / "bin")
    if "php-8.4.12" in selected_ids:
        candidates.append(root / "php" / "8.4.12" / "bin")
    if "rust-1.89.0" in selected_ids:
        candidates.append(root / "rust" / "1.89.0" / "bin")
    if "maven-3.9.10" in selected_ids:
        candidates.append(root / "maven" / "3.9.10" / "bin")
    if "postgresql-17.5" in selected_ids:
        candidates.extend((root / "postgresql" / "17.5" / "bin", Path("/opt/homebrew/opt/postgresql@17/bin")))
    if "node-26.0.0" in selected_ids:
        candidates.append(root / "node" / "26.0.0" / "bin")
    java_home = _java_home(manifest, effective_environ) if "java-21" in selected_ids else None
    if java_home is not None:
        candidates.insert(0, java_home / "bin")
    path_entries = _existing_directories(candidates)
    lines = [
        "# Generated by scripts/toolchains/runtime_environment.py; source this output in a POSIX shell.",
        f"export ELMOS_RUNTIME_PROFILE={shlex.quote(profile)}",
        f"export ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT={shlex.quote(str(root))}",
    ]
    if java_home is not None:
        lines.append(f"export JAVA_HOME={shlex.quote(str(java_home))}")
    python = _selected_python(manifest, profile, effective_environ)
    if python is not None:
        lines.append(f"export UV_PYTHON={shlex.quote(str(python))}")
    dotnet_root = Path("/opt/homebrew/Cellar/dotnet/10.0.301/libexec")
    if "dotnet-sdk-10.0.301" in selected_ids and dotnet_root.is_dir():
        lines.append(f"export DOTNET_ROOT={shlex.quote(str(dotnet_root))}")
    lines.extend(
        (
            "export DOTNET_CLI_TELEMETRY_OPTOUT=1",
            "export PYTHONNOUSERSITE=1",
        )
    )
    if "kotlin-2.2.20" in selected_ids:
        gradle_home = Path.home() / ".cache" / "elmos" / "gradle" / "8.14.3"
        lines.append(f"export GRADLE_USER_HOME={shlex.quote(str(gradle_home))}")
    if path_entries:
        prefix = os.pathsep.join(shlex.quote(str(item)) for item in path_entries)
        lines.append(f"export PATH={prefix}:\"$PATH\"")
    if {"python-3.12.12", "python-3.14.6"}.issubset(selected_ids):
        lines.append("# Python 3.12.12 and 3.14.6 are both required; select one per command with uv --python.")
    return "\n".join(lines) + "\n"


def _required_runtime_failures(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        runtime
        for runtime in report.get("runtimes", [])
        if isinstance(runtime, dict) and runtime.get("required") and runtime.get("status") != "READY"
    ]


def _install_steps(profile: str) -> list[list[str]]:
    steps: list[list[str]] = []
    if profile in {"synthesis", "routes-macos", "all"}:
        steps.append([str(INSTALLER_PATH)])
        steps.append(
            [
                "uv",
                "--directory",
                str(ROOT / "engines" / "polyglot-route-engine"),
                "sync",
                "--locked",
                "--python",
                "3.12.12",
            ]
        )
    if profile in {"core", "all"}:
        steps.append(
            [
                "uv",
                "--directory",
                str(ROOT / "engines" / "python-engine"),
                "sync",
                "--locked",
                "--python",
                "3.14.6",
            ]
        )
    if profile in {"routes-macos", "all"}:
        steps.append(
            [
                "pnpm",
                "--dir",
                str(ROOT / "engines" / "frontend-client-engine"),
                "install",
                "--frozen-lockfile",
            ]
        )
    return steps


def _run_install(
    manifest: Mapping[str, Any],
    profile: str,
    *,
    dry_run: bool,
    environ: Mapping[str, str],
) -> tuple[int, dict[str, Any]]:
    if profile not in AUTOMATED_INSTALL_PROFILES:
        return 2, {
            "status": "NOT_RUN",
            "profile": profile,
            "blocking_reason": "EXACT_TARGET_PROFILE_REQUIRED",
            "message": (
                "Select an exact language, platform, version, license, and authorized target "
                "before provisioning this profile."
            ),
        }
    root = _toolchain_root(manifest, environ)
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        return 2, {
            "status": "BLOCKED",
            "profile": profile,
            "blocking_reason": f"RUNTIME_TOOLCHAIN_ROOT_UNSAFE:{root}",
        }
    steps = _install_steps(profile)
    plan = {
        "status": "DRY_RUN" if dry_run else "RUNNING",
        "profile": profile,
        "toolchain_root": str(root),
        "steps": steps,
    }
    if dry_run:
        return 0, plan
    root.parent.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(root.parent).free
    if not root.exists() and free_bytes < 4 * 1024**3:
        return 2, {
            **plan,
            "status": "BLOCKED",
            "blocking_reason": "INSUFFICIENT_DISK_SPACE_FOR_TOOLCHAIN_INSTALL",
            "free_bytes": free_bytes,
            "required_free_bytes": 4 * 1024**3,
        }
    effective_env = dict(environ)
    effective_env.setdefault("ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT", str(root))
    executed: list[dict[str, Any]] = []
    for step in steps:
        executable = Path(step[0]) if os.path.sep in step[0] else None
        if executable is not None and (not executable.is_file() or not os.access(executable, os.X_OK)):
            return 2, {
                **plan,
                "status": "BLOCKED",
                "blocking_reason": f"INSTALLER_NOT_AVAILABLE:{step[0]}",
                "executed": executed,
            }
        try:
            completed = subprocess.run(  # noqa: S603
                step,
                cwd=ROOT,
                env=effective_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=1800,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return 1, {
                **plan,
                "status": "FAILED",
                "blocking_reason": f"INSTALL_STEP_ERROR:{type(error).__name__}",
                "executed": executed,
            }
        record = {
            "command": step,
            "exit_code": completed.returncode,
            "output": (completed.stdout + completed.stderr).strip()[-16_384:],
        }
        executed.append(record)
        if completed.returncode != 0:
            return 1, {
                **plan,
                "status": "FAILED",
                "blocking_reason": f"INSTALL_STEP_FAILED:{step[0]}",
                "executed": executed,
            }
    report = doctor(manifest, profile, environ=effective_env)
    failures = _required_runtime_failures(report)
    return (0 if not failures else 1), {
        **plan,
        "status": "READY" if not failures else "BLOCKED",
        "executed": executed,
        "doctor": report,
    }


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    destination = path.expanduser()
    if not destination.is_absolute():
        destination = (ROOT / destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as temporary:
            json.dump(value, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _print_human_report(report: Mapping[str, Any]) -> None:
    print(
        f"profile={report.get('profile')} platform={report.get('platform', '-')} "
        f"status={report.get('status')} claim_ceiling={report.get('claim_ceiling', 'NOT_RUN')}"
    )
    for runtime in report.get("runtimes", []):
        if not isinstance(runtime, dict):
            continue
        marker = "required" if runtime.get("required") else "optional"
        observed = ""
        if runtime.get("observed_available"):
            observed = " observed_available=true"
        print(
            f"{runtime.get('status', 'UNKNOWN'):18} {marker:8} "
            f"{runtime.get('id')} ({runtime.get('version')}){observed}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser(
        "validate", help="Validate structure, profiles, probes, and Batch coverage."
    )
    validate_parser.add_argument("--manifest", type=Path, default=argparse.SUPPRESS)

    doctor_parser = subparsers.add_parser("doctor", help="Run read-only version and availability probes.")
    doctor_parser.add_argument("--manifest", type=Path, default=argparse.SUPPRESS)
    doctor_parser.add_argument("--profile", default="all")
    doctor_parser.add_argument("--platform")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.add_argument("--strict", action="store_true")
    doctor_parser.add_argument("--output", type=Path)

    env_parser = subparsers.add_parser("env", help="Render a POSIX activation fragment.")
    env_parser.add_argument("--manifest", type=Path, default=argparse.SUPPRESS)
    env_parser.add_argument("--profile", default="synthesis")
    env_parser.add_argument("--shell", default="posix", choices=("posix",))

    install_parser = subparsers.add_parser("install", help="Provision the safe automated subset for one profile.")
    install_parser.add_argument("--manifest", type=Path, default=argparse.SUPPRESS)
    install_parser.add_argument("--profile", default="synthesis")
    install_parser.add_argument("--dry-run", action="store_true")
    install_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        errors = validate_manifest(manifest)
        if args.command == "validate":
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 1
            print(
                f"runtime manifest valid: {len(manifest['runtimes'])} runtimes, "
                f"{len(manifest['profiles'])} profiles, Batch 66-95 bindings complete"
            )
            return 0
        if errors:
            raise ValueError("RUNTIME_MANIFEST_INVALID:" + "|".join(errors))
        if args.command == "doctor":
            report = doctor(manifest, args.profile, args.platform)
            if args.output:
                _write_json_atomic(args.output, report)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                _print_human_report(report)
            if args.strict and report["status"] not in {"READY", "PARTIAL"}:
                return 1
            if args.strict and _required_runtime_failures(report):
                return 1
            return 0
        if args.command == "env":
            print(render_env(manifest, args.profile, args.shell), end="")
            return 0
        if args.command == "install":
            code, report = _run_install(
                manifest,
                args.profile,
                dry_run=bool(args.dry_run),
                environ=dict(os.environ),
            )
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(
                    f"profile={report.get('profile')} status={report.get('status')} "
                    f"reason={report.get('blocking_reason', '-') }"
                )
                for step in report.get("steps", []):
                    print("step:", shlex.join(step))
            return code
        raise AssertionError(f"unhandled command: {args.command}")
    except (ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
