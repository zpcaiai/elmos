#!/usr/bin/env python3
"""Generate replayable, self-attested P0 evidence for one clean Git SHA.

The collector is provider-free and never signs, certifies, deploys, or calls a
remote service. Its maximum decision is READY_FOR_TRUSTED_SIGNING.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EvidenceFailure(RuntimeError):
    """A stable current-SHA evidence failure."""


def _run(command: list[str], cwd: Path, *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "UV_OFFLINE": "1"},
    )


def _git(repository: Path, *arguments: str) -> str:
    completed = _run(["git", *arguments], repository)
    if completed.returncode != 0:
        raise EvidenceFailure(f"GIT_COMMAND_FAILED:{arguments[0]}")
    return completed.stdout.strip()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_atomic(path: Path, value: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _clean_status(repository: Path) -> tuple[bool, str]:
    status = _git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    return not status, status


def _check_plan(repository: Path) -> list[tuple[str, list[str], Path, int]]:
    engine = repository / "engines" / "project-synthesis-engine"
    uv = shutil.which("uv")
    if uv is None:
        return []
    return [
        (
            "p0-scope-contract",
            [sys.executable, "scripts/operations/validate_project_synthesis_p0_scope.py"],
            repository,
            60,
        ),
        (
            "engine-tests",
            [
                uv,
                "run",
                "--offline",
                "--frozen",
                "--project",
                str(engine),
                "pytest",
            ],
            engine,
            1200,
        ),
        (
            "ruff",
            [uv, "run", "--offline", "--frozen", "--project", str(engine), "ruff", "check", "src", "tests", "scripts"],
            engine,
            300,
        ),
        (
            "mypy",
            [uv, "run", "--offline", "--frozen", "--project", str(engine), "mypy", "src"],
            engine,
            300,
        ),
        ("exact-toolchain-acceptance", [uv, "run", "--offline", "--frozen", "--project", str(engine), "python", "scripts/run_acceptance.py", "--require-all-toolchains"], engine, 2400),
        ("production-matrix", [uv, "run", "--offline", "--frozen", "--project", str(engine), "python", "scripts/run_production_matrix.py"], engine, 3600),
        ("p0-operational-contracts", [sys.executable, "-m", "unittest", "discover", "-s", "tests/production-readiness", "-p", "test_project_synthesis_p0_launch_gate.py"], repository, 300),
        ("runner-production-contract", [sys.executable, "-m", "unittest", "discover", "-s", "deploy/local-runner/tests", "-p", "test_*.py"], repository, 300),
        ("vercel-deployment-waiter-contract", [sys.executable, "-m", "unittest", "discover", "-s", "tests/production-readiness", "-p", "test_vercel_deployment_waiter.py"], repository, 300),
        ("batch33-cloud-gate", [uv, "run", "--offline", "--with", "jsonschema>=4.23", "--with", "pyyaml", "python", "scripts/batch33/run_cloud_gate.py", "cloud-packs/elmos-project-generation-cloud-run-handoff"], repository, 300),
        ("web-console-offline-install", [shutil.which("pnpm") or "pnpm", "--dir", "apps/web-console", "install", "--offline", "--frozen-lockfile", "--ignore-scripts"], repository, 900),
        ("web-console-check", [shutil.which("pnpm") or "pnpm", "--dir", "apps/web-console", "check"], repository, 1800),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--auth-profile",
        choices=("jwt", "oidc", "all"),
        default="all",
        help="Bind this local evidence to JWT, OIDC, or the complete frozen authentication scope",
    )
    parser.add_argument("--skip-local-checks", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repository = args.repository.expanduser().resolve(strict=True)
    if _git(repository, "rev-parse", "--show-toplevel") != str(repository):
        raise EvidenceFailure("REPOSITORY_ROOT_MISMATCH")
    output = args.output.expanduser().resolve(strict=False)
    if output == repository or output.is_relative_to(repository):
        raise EvidenceFailure("EVIDENCE_OUTPUT_MUST_BE_OUTSIDE_SOURCE_REPOSITORY")
    if output.exists() and (output.is_symlink() or not output.is_dir() or any(output.iterdir())):
        raise EvidenceFailure("EVIDENCE_OUTPUT_MUST_BE_NEW_OR_EMPTY_DIRECTORY")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)

    clean_before, status_before = _clean_status(repository)
    if not clean_before:
        raise EvidenceFailure("SOURCE_WORKTREE_NOT_CLEAN")
    commit_sha = _git(repository, "rev-parse", "HEAD")
    tree_sha = _git(repository, "rev-parse", "HEAD^{tree}")

    engine_source = repository / "engines" / "project-synthesis-engine" / "src"
    sys.path.insert(0, str(engine_source))
    from elmos_project_synthesis.models import p0_scope_payload
    from elmos_project_synthesis.supply_chain import (
        build_python_lock_sbom,
        canonical_json,
        sbom_is_complete,
        sbom_status,
    )

    scope = p0_scope_payload()
    scope_path = repository / "docs" / "project-synthesis" / "p0-launch-scope-v1.json"
    if json.loads(scope_path.read_text(encoding="utf-8")) != scope:
        raise EvidenceFailure("P0_SCOPE_RUNTIME_DRIFT")
    sbom = build_python_lock_sbom(repository / "engines" / "project-synthesis-engine")
    sbom_path = output / "project-synthesis-engine.sbom.cdx.json"
    _write_atomic(sbom_path, _json_bytes(sbom))
    provider_observation_path = (
        repository / "docs" / "project-synthesis" / "provider-observation-2026-09-04.json"
    )
    provider_observation = json.loads(provider_observation_path.read_text(encoding="utf-8"))
    if not isinstance(provider_observation, dict):
        raise EvidenceFailure("MANAGED_PROVIDER_OBSERVATION_INVALID")
    provider_assessment = provider_observation.get("assessment")
    provider_details = provider_observation.get("observation")
    provider_boundaries = provider_observation.get("boundaries")
    if (
        not isinstance(provider_assessment, dict)
        or not isinstance(provider_details, dict)
        or not isinstance(provider_boundaries, dict)
        or provider_assessment.get("compatibility") != "ALGORITHM_MISMATCH"
        or provider_assessment.get("required_jwk_algorithm") != "RS256"
        or provider_details.get("jwk_algorithm") != "EdDSA"
    ):
        raise EvidenceFailure("MANAGED_PROVIDER_OBSERVATION_INVALID")
    if not sbom_is_complete(sbom):
        raise EvidenceFailure("ENGINE_DEPENDENCY_INVENTORY_OR_INTEGRITY_INCOMPLETE")

    blockers: list[str] = []
    checks: list[dict[str, Any]] = []
    if args.skip_local_checks:
        blockers.append("LOCAL_CHECKS_NOT_RUN")
    else:
        plan = _check_plan(repository)
        if not plan:
            blockers.append("EXACT_UV_TOOLCHAIN_NOT_AVAILABLE")
        for identifier, command, check_cwd, timeout in plan:
            try:
                completed = _run(command, check_cwd, timeout=timeout)
                output_text = completed.stdout + completed.stderr
                status = "PASSED" if completed.returncode == 0 else "FAILED"
                exit_code: int | None = completed.returncode
            except subprocess.TimeoutExpired as error:
                stdout = error.stdout if isinstance(error.stdout, str) else ""
                stderr = error.stderr if isinstance(error.stderr, str) else ""
                output_text = f"COMMAND_TIMEOUT:{timeout}s\n{stdout}{stderr}"
                status = "FAILED"
                exit_code = None
            except OSError as error:
                output_text = f"COMMAND_EXECUTION_FAILED:{type(error).__name__}"
                status = "FAILED"
                exit_code = None
            log_path = output / f"{identifier}.log"
            _write_atomic(log_path, output_text.encode("utf-8"))
            checks.append(
                {
                    "id": identifier,
                    "command": command,
                    "cwd": str(check_cwd),
                    "timeout_seconds": timeout,
                    "status": status,
                    "exit_code": exit_code,
                    "log": {
                        "path": log_path.name,
                        "sha256": _sha256(log_path.read_bytes()),
                        "byte_count": log_path.stat().st_size,
                    },
                }
            )
            if status != "PASSED":
                blockers.append(f"LOCAL_CHECK_FAILED:{identifier}")

    clean_after, status_after = _clean_status(repository)
    if not clean_after:
        blockers.append("SOURCE_WORKTREE_CHANGED_DURING_COLLECTION")
    commit_sha_after = _git(repository, "rev-parse", "HEAD")
    tree_sha_after = _git(repository, "rev-parse", "HEAD^{tree}")
    if commit_sha_after != commit_sha or tree_sha_after != tree_sha:
        blockers.append("SOURCE_REVISION_CHANGED_DURING_COLLECTION")
    if args.auth_profile in {"oidc", "all"}:
        blockers.append("MANAGED_OIDC_ALGORITHM_MISMATCH:required=RS256:observed=EdDSA")
    blockers.append("RELEASE_SIGNATURE_NOT_VERIFIED")
    blockers = sorted(set(blockers))
    local_passed = bool(checks) and all(check["status"] == "PASSED" for check in checks)
    result = {
        "schema_version": "1.0.0",
        "kind": "elmos.project-synthesis.current-sha-evidence",
        "collected_at": datetime.now(UTC).isoformat(),
        "source_revision": {
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "commit_sha_after": commit_sha_after,
            "tree_sha_after": tree_sha_after,
            "worktree_clean_before": clean_before,
            "worktree_clean_after": clean_after,
            "status_before": status_before,
            "status_after": status_after,
        },
        "scope": {
            "id": scope["scope_id"],
            "path": scope_path.relative_to(repository).as_posix(),
            "sha256": _sha256(canonical_json(scope)),
            "status": "FROZEN",
            "qualification_auth_profile": args.auth_profile,
        },
        "transitive_dependency_sbom": {
            "path": sbom_path.name,
            "sha256": _sha256(sbom_path.read_bytes()),
            "transitive_inventory_status": sbom_status(sbom, "elmos:transitive-inventory-status"),
            "artifact_integrity_status": sbom_status(sbom, "elmos:artifact-integrity-status"),
            "dependency_graph_status": sbom_status(sbom, "elmos:dependency-graph-status"),
            "release_input_status": "INVENTORY_AND_INTEGRITY_COMPLETE",
            "component_count": len(sbom["components"]),
        },
        "managed_provider_compatibility": {
            "profile": args.auth_profile,
            "status": (
                "NOT_APPLICABLE_INDEPENDENT_JWT_PROFILE"
                if args.auth_profile == "jwt"
                else "ALGORITHM_MISMATCH"
            ),
            "observation": {
                "path": provider_observation_path.relative_to(repository).as_posix(),
                "sha256": _sha256(provider_observation_path.read_bytes()),
                "evidence_class": provider_boundaries["evidence_class"],
                "raw_provider_receipt_status": provider_boundaries["raw_provider_receipt_status"],
            },
        },
        "local_checks": {
            "status": "PASSED" if local_passed else "NOT_RUN" if not checks else "FAILED",
            "evidence_class": "LOCAL_ENGINEERING_SELF_ATTESTED",
            "checks": checks,
        },
        "replay": {
            "source_commit": commit_sha,
            "commands": [check["command"] for check in checks],
            "dependency_resolution": "UV_AND_PNPM_OFFLINE_FROZEN",
            "network_isolation": "NOT_ENFORCED",
        },
        "decision": "READY_FOR_TRUSTED_SIGNING" if blockers == ["RELEASE_SIGNATURE_NOT_VERIFIED"] else "BLOCKED",
        "blockers": blockers,
        "signature_status": "NOT_RUN",
        "trusted_root_status": "NOT_RUN",
        "production_delivery_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "production_ready": False,
        "certified": False,
    }
    receipt_path = output / "current-sha-evidence.json"
    _write_atomic(receipt_path, _json_bytes(result))
    print(
        json.dumps(
            {
                "status": result["decision"],
                "source_commit": commit_sha,
                "receipt": str(receipt_path),
                "receipt_sha256": _sha256(receipt_path.read_bytes()),
                "production_ready": False,
                "certified": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not blockers or blockers == ["RELEASE_SIGNATURE_NOT_VERIFIED"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, EvidenceFailure) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2) from error
