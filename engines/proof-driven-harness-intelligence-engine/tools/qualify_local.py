#!/usr/bin/env python3
"""Produce a digest-bound, self-attested local PDHI qualification receipt."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence


ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENGINE_SOURCE = ENGINE_ROOT / "src"
if str(ENGINE_SOURCE) not in sys.path:
    sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_pdhi.canonical import canonical_json_bytes, digest_object  # noqa: E402
from elmos_pdhi.registry import ARCHIVE_SHA256  # noqa: E402
from elmos_pdhi.runtime import RuntimeRegistry  # noqa: E402


DEFAULT_OUTPUT = ENGINE_ROOT / "qualification/local-v1"


class QualificationError(RuntimeError):
    pass


def _executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise QualificationError(f"required qualification executable is unavailable: {name}")
    return str(Path(path).resolve())


def _run(name: str, command: Sequence[str], *, timeout: int = 180) -> Mapping[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(ENGINE_SOURCE)
    started = datetime.now(UTC)
    try:
        completed = subprocess.run(
            tuple(command),
            cwd=REPOSITORY_ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout,
            check=False,
        )
        output = completed.stdout
        return {
            "name": name,
            "command": list(command),
            "exit_code": completed.returncode,
            "started_at": started.isoformat().replace("+00:00", "Z"),
            "duration_seconds": format((datetime.now(UTC) - started).total_seconds(), ".6f"),
            "output": output,
            "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        }
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return {
            "name": name,
            "command": list(command),
            "exit_code": 124,
            "started_at": started.isoformat().replace("+00:00", "Z"),
            "duration_seconds": format((datetime.now(UTC) - started).total_seconds(), ".6f"),
            "output": output + "\nQUALIFICATION_TIMEOUT\n",
            "output_sha256": hashlib.sha256((output + "\nQUALIFICATION_TIMEOUT\n").encode("utf-8")).hexdigest(),
        }


def _artifact_inventory(output_root: Path) -> Mapping[str, str]:
    candidates: list[Path] = []
    for root in (
        REPOSITORY_ROOT / ".agents/skills",
        REPOSITORY_ROOT / "agent-skills/runtime",
        ENGINE_ROOT,
        REPOSITORY_ROOT / "tests/proof-driven-harness-intelligence",
    ):
        if root in (REPOSITORY_ROOT / ".agents/skills", REPOSITORY_ROOT / "agent-skills/runtime"):
            for skill_name in RuntimeRegistry().manifest()["skills"]:
                skill_root = root / skill_name
                if skill_root.exists():
                    candidates.extend(path for path in skill_root.rglob("*") if path.is_file())
        else:
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    candidates.extend(
        (
            REPOSITORY_ROOT / "Makefile.proof-harness-intelligence",
            REPOSITORY_ROOT / "tooling/integrate_proof_driven_harness_intelligence_v1.py",
            REPOSITORY_ROOT / "skills/subskills/sub/elmos-proof-driven-harness-intelligence-v1.0.0.zip",
        )
    )
    inventory: dict[str, str] = {}
    for path in sorted(set(candidates)):
        relative = path.relative_to(REPOSITORY_ROOT)
        if path.is_symlink():
            raise QualificationError(f"qualification artifact cannot be a symlink: {relative}")
        if "__pycache__" in relative.parts or ".pytest_cache" in relative.parts:
            continue
        if output_root == path or output_root in path.parents:
            continue
        inventory[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not inventory:
        raise QualificationError("qualification artifact inventory is empty")
    return inventory


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def qualify(output_root: Path) -> Mapping[str, Any]:
    python = str(Path(sys.executable).resolve())
    pytest = _executable("pytest")
    ruff = _executable("ruff")
    mypy = _executable("mypy")
    commands = (
        (
            "pinned-source-check",
            (
                python,
                str(REPOSITORY_ROOT / "tooling/integrate_proof_driven_harness_intelligence_v1.py"),
                "--archive",
                str(REPOSITORY_ROOT / "skills/subskills/sub/elmos-proof-driven-harness-intelligence-v1.0.0.zip"),
                "--check",
            ),
        ),
        (
            "installation-validation",
            (python, str(ENGINE_ROOT / "tools/validate_installation.py")),
        ),
        (
            "tests",
            (
                pytest,
                "-q",
                str(ENGINE_ROOT / "tests"),
                str(REPOSITORY_ROOT / "tests/proof-driven-harness-intelligence"),
            ),
        ),
        (
            "ruff",
            (
                ruff,
                "check",
                str(ENGINE_ROOT / "src/elmos_pdhi"),
                str(ENGINE_ROOT / "tests"),
                str(REPOSITORY_ROOT / "tests/proof-driven-harness-intelligence"),
                str(ENGINE_ROOT / "tools"),
            ),
        ),
        (
            "mypy-strict",
            (mypy, "--strict", str(ENGINE_ROOT / "src/elmos_pdhi")),
        ),
        (
            "diff-check",
            (_executable("git"), "diff", "--check"),
        ),
    )
    executions = tuple(_run(name, command) for name, command in commands)
    raw_root = output_root / "raw"
    raw_digests: dict[str, str] = {}
    for execution in executions:
        relative = f"{execution['name']}.log"
        content = str(execution["output"]).encode("utf-8")
        _atomic_write(raw_root / relative, content)
        raw_digests[relative] = hashlib.sha256(content).hexdigest()
    inventory = _artifact_inventory(output_root)
    runtime_manifest = RuntimeRegistry().manifest()
    successful = all(execution["exit_code"] == 0 for execution in executions)
    receipt_body = {
        "schema_version": "1.0.0",
        "package": "elmos-proof-driven-harness-intelligence@1.0.0",
        "qualified_at": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "qualification_status": "LOCAL_EXECUTED_SELF_ATTESTED" if successful else "LOCAL_FAILED",
        "readiness": "READY_FOR_EXTERNAL_GATE" if successful else "BLOCKED",
        "archive_sha256": ARCHIVE_SHA256,
        "runtime_manifest_digest": runtime_manifest["manifest_digest"],
        "runtime_counts": runtime_manifest["runtime_counts"],
        "source_task_id_count": 0,
        "source_dependency_edge_count": 0,
        "commands": [
            {
                key: value
                for key, value in execution.items()
                if key != "output"
            }
            for execution in executions
        ],
        "raw_outputs": raw_digests,
        "artifacts": inventory,
        "environment": {
            "python": sys.version,
            "python_executable": python,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "authority": "SELF_ATTESTED_LOCAL_ENGINEERING_ONLY",
        "external_provider_evidence": "NOT_RUN",
        "external_database_evidence": "NOT_RUN",
        "external_sandbox_evidence": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "deployment_evidence": "NOT_RUN",
        "customer_workload_evidence": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    receipt = {
        **receipt_body,
        "qualification_digest": digest_object(receipt_body, domain="pdhi-local-qualification"),
    }
    _atomic_write(output_root / "receipt.json", canonical_json_bytes(receipt) + b"\n")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        receipt = qualify(args.output.resolve())
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error": type(exc).__name__, "message": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["readiness"] == "READY_FOR_EXTERNAL_GATE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
