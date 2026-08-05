#!/usr/bin/env python3
"""Fail-closed native tool execution for exact Precision Migration handlers.

The command table is code-owned and immutable. Requests may bind an asset index
to a declared tool, but cannot supply executable names, flags, environment
variables, working directories, plugins, project files, or shell fragments.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from scripts.precision_migration.domain import DomainExecutionError
from scripts.precision_migration.trust import request_binding_digest, verify_content_reference


MAX_NATIVE_SOURCE_BYTES = 4 * 1024 * 1024
MAX_NATIVE_OUTPUT_BYTES = 64 * 1024
NATIVE_TIMEOUT_SECONDS = 30


def _path(reference: dict[str, Any]) -> Path:
    uri = reference.get("uri")
    if not isinstance(uri, str):
        raise DomainExecutionError("native asset URI must be a string")
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise DomainExecutionError("native assets must use local file URIs")
    return Path(unquote(parsed.path))


def _python(executable: str, source: Path, output: Path) -> list[str]:
    return [executable, "-m", "py_compile", str(source)]


def _javac(executable: str, source: Path, output: Path) -> list[str]:
    classes = output / "classes"
    classes.mkdir()
    return [executable, "-d", str(classes), str(source)]


def _go(executable: str, source: Path, output: Path) -> list[str]:
    return [executable, "test", str(source)]


def _csc(executable: str, source: Path, output: Path) -> list[str]:
    return [executable, "/nologo", "/target:library", f"/out:{output / 'fixture.dll'}", str(source)]


def _rustc(executable: str, source: Path, output: Path) -> list[str]:
    compiled = output / "libfixture.rlib"
    return [executable, "--crate-type", "lib", str(source), "-o", str(compiled)]


def _tsc(executable: str, source: Path, output: Path) -> list[str]:
    return [executable, "--noEmit", "--pretty", "false", str(source)]


def _node(executable: str, source: Path, output: Path) -> list[str]:
    return [executable, "--check", str(source)]


def _flutter(executable: str, source: Path, output: Path) -> list[str]:
    return [executable, "analyze", "--no-pub", str(source)]


def _lean(executable: str, source: Path, output: Path) -> list[str]:
    return [executable, str(source)]


def _z3(executable: str, source: Path, output: Path) -> list[str]:
    return [executable, "-smt2", str(source)]


Builder = Callable[[str, Path, Path], list[str]]


NATIVE_ADAPTERS: dict[str, tuple[frozenset[str], Builder]] = {
    "python3": (frozenset({".py"}), _python),
    "javac": (frozenset({".java"}), _javac),
    "csc": (frozenset({".cs"}), _csc),
    "go": (frozenset({".go"}), _go),
    "rustc": (frozenset({".rs"}), _rustc),
    "tsc": (frozenset({".ts", ".tsx"}), _tsc),
    "node": (frozenset({".js", ".mjs", ".cjs"}), _node),
    "flutter": (frozenset({".dart"}), _flutter),
    "lean": (frozenset({".lean"}), _lean),
    "z3": (frozenset({".smt2"}), _z3),
}

# These clients cannot perform a meaningful syntax/build check without a real
# project or disposable service. They are explicitly classified so an exact
# Skill returns a typed external-gate obligation instead of silently pretending
# that a client binary invocation is domain validation.
EXTERNAL_NATIVE_ADAPTERS: dict[str, dict[str, Any]] = {
    "sqlplus": {"extensions": frozenset({".sql"}), "provider": "oracle", "gate": "DISPOSABLE_DATABASE"},
    "sqlcmd": {"extensions": frozenset({".sql"}), "provider": "sqlserver", "gate": "DISPOSABLE_DATABASE"},
    "psql": {"extensions": frozenset({".sql"}), "provider": "postgresql", "gate": "DISPOSABLE_DATABASE"},
    "mysql": {"extensions": frozenset({".sql"}), "provider": "mysql", "gate": "DISPOSABLE_DATABASE"},
    "ohpm": {"extensions": frozenset({".ets", ".ts", ".json5"}), "provider": "arkui", "gate": "SIGNED_PROJECT_WORKSPACE"},
}


def native_tool_readiness(tool: str) -> dict[str, Any]:
    if tool in NATIVE_ADAPTERS:
        return {
            "tool": tool,
            "adapter": "LOCAL_ALLOWLISTED",
            "available": shutil.which(tool) is not None,
            "external_gate": None,
        }
    external = EXTERNAL_NATIVE_ADAPTERS.get(tool)
    if external is not None:
        return {
            "tool": tool,
            "adapter": "EXTERNAL_FAIL_CLOSED",
            "available": shutil.which(tool) is not None,
            "external_gate": external["gate"],
        }
    return {"tool": tool, "adapter": "UNSUPPORTED", "available": False, "external_gate": None}


def _external_receipt(
    tool: str,
    request: dict[str, Any],
    evidence_roots: tuple[Path, ...],
    trust_store: Any,
) -> dict[str, Any] | None:
    kind = f"native-tool:{tool}"
    matches = [
        item
        for item in request.get("evidence", [])
        if isinstance(item, dict) and item.get("kind") == kind
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise DomainExecutionError(f"external native evidence must be unique for {tool}")
    evidence = matches[0]
    if evidence.get("state") != "PASS":
        raise DomainExecutionError(f"external native evidence is not PASS for {tool}")
    for field in ("executor", "verifier", "replay_command", "environment_digest"):
        if not isinstance(evidence.get(field), str) or not evidence[field]:
            raise DomainExecutionError(f"external native evidence lacks {field} for {tool}")
    if evidence["executor"] == evidence["verifier"]:
        raise DomainExecutionError(f"external native evidence is self-verified for {tool}")
    if trust_store is None:
        raise DomainExecutionError(f"external native evidence requires a trust store for {tool}")
    try:
        observed = verify_content_reference(evidence, evidence_roots)
        authorization = trust_store.verify_envelope(
            evidence.get("authorization"),
            required_role="evidence-authorizer",
            bindings={
                "record_type": "EVIDENCE_AUTHORIZATION",
                "request_id": request.get("request_id"),
                "skill": request.get("skill"),
                "evidence_kind": kind,
                "artifact_digest": evidence.get("digest"),
                "executor": evidence.get("executor"),
                "verifier": evidence.get("verifier"),
                "request_digest": request_binding_digest(request),
            },
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise DomainExecutionError(f"external native evidence verification failed for {tool}: {exc}") from exc
    return {
        "tool": tool,
        "state": "EXTERNAL_VERIFIED",
        "input_digest": observed["digest"],
        "size_bytes": observed["size_bytes"],
        "executor": evidence["executor"],
        "verifier": evidence["verifier"],
        "replay_command": evidence["replay_command"],
        "environment_digest": evidence["environment_digest"],
        "authorization_record_id": authorization["record_id"],
    }


def _minimal_environment() -> dict[str, str]:
    allowed = ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
    return {key: os.environ[key] for key in allowed if key in os.environ}


def execute_native_tools(
    profile: dict[str, Any],
    request: dict[str, Any],
    evidence_roots: tuple[Path, ...],
    output_dir: Path,
    trust_store: Any = None,
) -> dict[str, Any]:
    parameters = request.get("inputs", {}).get("parameters", {})
    if parameters.get("execute_native") is not True:
        return {"requested": False, "state": "NOT_RUN", "runs": []}
    declared = profile.get("native_tools", [])
    if not isinstance(declared, list) or not declared:
        raise DomainExecutionError("exact Skill has no declared native tool adapter")
    bindings = parameters.get("native_assets")
    if not isinstance(bindings, dict) or set(bindings) != set(declared):
        raise DomainExecutionError("native_assets must bind every and only declared native tool")
    assets = request.get("inputs", {}).get("assets", [])
    native_root = output_dir / "native"
    native_root.mkdir()
    runs: list[dict[str, Any]] = []
    for tool in declared:
        index = bindings.get(tool)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(assets):
            raise DomainExecutionError(f"native asset index is invalid for {tool}")
        reference = assets[index]
        verify_content_reference(reference, evidence_roots)
        source_path = _path(reference)
        content = source_path.read_bytes()
        if len(content) > MAX_NATIVE_SOURCE_BYTES:
            raise DomainExecutionError(f"native asset exceeds size budget for {tool}")
        external = EXTERNAL_NATIVE_ADAPTERS.get(tool)
        if external is not None:
            if source_path.suffix.lower() not in external["extensions"]:
                raise DomainExecutionError(f"native asset extension is not allowlisted for {tool}")
            receipt = _external_receipt(tool, request, evidence_roots, trust_store)
            if receipt is not None:
                runs.append({**receipt, "provider": external["provider"], "gate": external["gate"]})
                continue
            runs.append(
                {
                    "tool": tool,
                    "state": "REQUIRES_EXTERNAL_GATE",
                    "provider": external["provider"],
                    "gate": external["gate"],
                    "input_digest": reference["digest"],
                    "requirements": [
                        "approved disposable environment",
                        "short-lived secret reference or signed project workspace",
                        "source and target build/runtime evidence",
                        "independent verifier distinct from executor",
                        "cleanup and revocation receipt",
                    ],
                }
            )
            continue
        if tool not in NATIVE_ADAPTERS:
            runs.append({"tool": tool, "state": "UNSUPPORTED", "reason": "tool is not present in the code-owned adapter registry"})
            continue
        extensions, builder = NATIVE_ADAPTERS[tool]
        suffix = source_path.suffix.lower()
        if suffix not in extensions:
            raise DomainExecutionError(f"native asset extension is not allowlisted for {tool}")
        executable = shutil.which(tool)
        if executable is None:
            runs.append({"tool": tool, "state": "NOT_AVAILABLE"})
            continue
        tool_root = native_root / tool
        tool_root.mkdir()
        copied = tool_root / ("source" + suffix)
        copied.write_bytes(content)
        command = builder(executable, copied, tool_root)
        completed = subprocess.run(
            command,
            cwd=tool_root,
            env=_minimal_environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=NATIVE_TIMEOUT_SECONDS,
        )
        stdout = completed.stdout[:MAX_NATIVE_OUTPUT_BYTES].decode("utf-8", errors="replace")
        stderr = completed.stderr[:MAX_NATIVE_OUTPUT_BYTES].decode("utf-8", errors="replace")
        runs.append(
            {
                "tool": tool,
                "state": "PASSED" if completed.returncode == 0 else "FAILED",
                "exit_code": completed.returncode,
                "command_shape": [Path(command[0]).name, *command[1:]],
                "stdout": stdout,
                "stderr": stderr,
                "input_digest": reference["digest"],
            }
        )
    state = "PASSED" if runs and all(run["state"] in {"PASSED", "EXTERNAL_VERIFIED"} for run in runs) else "FAILED"
    return {"requested": True, "state": state, "runs": runs}
