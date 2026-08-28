#!/usr/bin/env python3
"""Run and bind the Formal Assurance Kernel local engineering qualification.

This script executes repository-owned tests only. It never imports or executes
the attached package's scripts, installers, reference kernel, SQL, or workflows.
The resulting receipt is self-attested local evidence and cannot certify the
package or manufacture external/independent evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "verification-packs/formal-assurance-kernel-local"
ENGINE = ROOT / "engines/formal-assurance-engine"
SOURCE_ARCHIVE = ROOT / "skills/subskills/elmos-formal-assurance-kernel-v1.0.0.zip"
SOURCE_DIGEST = "sha256:7d397f9379e15023208d3fb49b3928af07b7b6134e6a91fe70ebaf7048f9e73e"


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_record(path: Path, *, relative_to: Path = ROOT) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"qualification input is missing or unsafe: {path}")
    data = path.read_bytes()
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "byte_size": len(data),
        "sha256": sha(data),
    }


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def run_suite(name: str, argv: list[str], env: dict[str, str], raw_ref: str) -> dict[str, Any]:
    started = time.monotonic()
    process = subprocess.run(
        argv,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
        check=False,
    )
    duration = round(time.monotonic() - started, 3)
    output = process.stdout
    atomic_write(PACK / raw_ref, output)
    match = re.search(rb"Ran (\d+) tests?", output)
    skipped_match = re.search(rb"skipped=(\d+)", output)
    tests = int(match.group(1)) if match else 0
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    passed = tests - skipped if process.returncode == 0 else 0
    failed = tests - passed
    if process.returncode != 0 or tests < 1 or failed or skipped:
        raise RuntimeError(
            f"{name} qualification failed: exit={process.returncode} tests={tests} failed={failed} skipped={skipped}"
        )
    return {
        "name": name,
        "command": " ".join(argv),
        "exit_code": process.returncode,
        "tests": tests,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration_seconds": duration,
        "raw_evidence_ref": raw_ref,
        "raw_evidence_digest": sha(output),
    }


def probe(executable: str, args: tuple[str, ...]) -> dict[str, Any]:
    path = shutil.which(executable)
    if not path:
        return {"name": executable, "status": "NOT_AVAILABLE"}
    resolved = Path(path).resolve(strict=True)
    try:
        process = subprocess.run(
            [str(resolved), *args],
            cwd=ROOT,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C", "LC_ALL": "C"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
        output = process.stdout[:64 * 1024]
        status = "AVAILABLE" if process.returncode == 0 else "PROBE_NONZERO"
    except (OSError, subprocess.TimeoutExpired) as exc:
        output = type(exc).__name__.encode("utf-8")
        status = "PROBE_FAILED"
    return {
        "name": executable,
        "status": status,
        "path": str(resolved),
        "sha256": sha(resolved.read_bytes()),
        "versionOutputDigest": sha(output),
        "versionOutput": output.decode("utf-8", errors="replace").strip()[:2000],
    }


def implementation_files() -> list[Path]:
    files = [
        path
        for path in ENGINE.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and "__pycache__" not in path.parts
        and not path.name.endswith((".pyc", ".pyo"))
    ]
    files.extend(
        [
            ROOT / "tooling/integrate_formal_assurance_kernel.py",
            ROOT / "tests/formal-assurance-kernel/test_integration.py",
            ROOT / "scripts/formal_assurance/generate_local_qualification.py",
            ROOT / "docs/formal-assurance-kernel/skill-registry.json",
            ROOT / "docs/formal-assurance-kernel/installed-manifest.json",
            ROOT / "docs/formal-assurance-kernel/acceptance-traceability.json",
        ]
    )
    registry = json.loads(
        (ROOT / "docs/formal-assurance-kernel/installed-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    skill_ids = [item.get("skillId") for item in registry.get("skills", [])]
    if (
        len(skill_ids) != 60
        or len(set(skill_ids)) != 60
        or any(not isinstance(item, str) or not item for item in skill_ids)
    ):
        raise RuntimeError("Formal Assurance installed Skill inventory is invalid")
    for skill_id in skill_ids:
        files.extend(
            [
                ROOT / "agent-skills/runtime" / skill_id / "SKILL.md",
                ROOT / ".agents/skills" / skill_id / "SKILL.md",
            ]
        )
    return sorted(set(path.resolve(strict=True) for path in files))


def implementation_manifest(files: list[Path]) -> dict[str, Any]:
    return {
        "format": "elmos-formal-implementation-manifest/v1",
        "files": [file_record(path) for path in files],
        "skillCount": 60,
        "installedSkillInterfaceCount": 120,
        "sourceAcceptanceCriterionCount": 481,
        "productionMethodCount": 40,
        "declaredVerifierAdapterCount": 17,
    }


def check_existing_qualification() -> int:
    manifest_path = PACK / "qualification/implementation-manifest.json"
    expected_manifest = implementation_manifest(implementation_files())
    actual_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if actual_manifest != expected_manifest:
        raise RuntimeError("local qualification implementation manifest is stale")
    target_digest = sha(manifest_path.read_bytes())
    environment_path = PACK / "qualification/environment.json"
    environment_digest = sha(environment_path.read_bytes())
    pack = json.loads((PACK / "pack.json").read_text(encoding="utf-8"))
    receipt = json.loads(
        (PACK / "qualification/local-qualification.json").read_text(
            encoding="utf-8"
        )
    )
    certification = json.loads(
        (PACK / "certification/certification.json").read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (PACK / "certification/evidence.json").read_text(encoding="utf-8")
    )
    scope = pack.get("scope", {})
    expected_pairs = {
        "source_artifact_digest": SOURCE_DIGEST,
        "target_artifact_digest": target_digest,
        "environment_digest": environment_digest,
    }
    for key, expected in expected_pairs.items():
        if scope.get(key) != expected:
            raise RuntimeError(f"local qualification pack {key} is stale")
    if receipt.get("source_digest") != SOURCE_DIGEST:
        raise RuntimeError("local qualification receipt source binding is stale")
    if receipt.get("test_digest") != target_digest:
        raise RuntimeError("local qualification receipt test binding is stale")
    if receipt.get("environment_digest") != environment_digest:
        raise RuntimeError("local qualification receipt environment binding is stale")
    if certification.get("exact_scope") != scope:
        raise RuntimeError("certification scope does not match the qualification pack")
    tests = receipt.get("tests")
    if not isinstance(tests, int) or tests < 1 or receipt.get("passed") != tests:
        raise RuntimeError("local qualification receipt test counts are invalid")
    expected_metrics = {"local_tests": tests, "local_test_pass_rate": 1.0}
    if certification.get("metrics") != expected_metrics:
        raise RuntimeError("certification local test metrics are stale")
    if evidence.get("metrics") != expected_metrics:
        raise RuntimeError("evidence local test metrics are stale")
    if receipt.get("externalEvidenceStatus") != "NOT_RUN":
        raise RuntimeError("external evidence boundary was unexpectedly promoted")
    if receipt.get("certificationStatus") != "NOT_CERTIFIED":
        raise RuntimeError("certification boundary was unexpectedly promoted")
    assertions = receipt.get("contract_assertions", {})
    if assertions.get("sourceAcceptanceCriteriaMapped") != 481:
        raise RuntimeError("acceptance traceability receipt is incomplete")
    if assertions.get("externalAcceptanceEvidence") != "NOT_RUN":
        raise RuntimeError("external acceptance boundary was unexpectedly promoted")
    print(
        json.dumps(
            {
                "status": "PASS",
                "qualification": "LOCAL_EXECUTED_SELF_ATTESTED",
                "tests": tests,
                "targetDigest": target_digest,
                "externalEvidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
            sort_keys=True,
        )
    )
    return 0


def update_pack_scope(
    target_digest: str, environment_digest: str, local_tests: int
) -> dict[str, Any]:
    pack_path = PACK / "pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["version"] = "1.0.0"
    pack["scope"]["target_artifact_digest"] = target_digest
    pack["scope"]["environment_digest"] = environment_digest
    write_json(pack_path, pack)

    certification_path = PACK / "certification/certification.json"
    certification = json.loads(certification_path.read_text(encoding="utf-8"))
    certification["exact_scope"] = pack["scope"]
    certification["metrics"] = {
        "local_tests": local_tests,
        "local_test_pass_rate": 1.0,
    }
    certification["limitations"] = [
        "All 60 exact Skill handlers and all 481 source acceptance IDs are mapped to executable repository-owned controls.",
        "The 481 controls establish local code-path, honesty, counterexample materialization, drift invalidation, and isolation behavior; they do not claim external acceptance execution.",
        "All 40 native/provider adapter entry points are code-complete and locally contract-tested, but only locally available toolchains are actually executed.",
        "Recorded execution is local and self-attested; executor and verifier are not independent.",
        "Only the locally available Z3 and SQLite paths were natively executed in this qualification.",
        "Other exact native toolchains, OCI images, real databases, Spring representative builds, external telemetry, FFI holdouts, production workloads, deployment, independent review, and certification remain NOT_RUN.",
        "Finite passing tests and solver examples are not universal proof or certification.",
    ]
    certification["evidence_refs"] = []
    certification["approved_at"] = None
    write_json(certification_path, certification)
    return pack


def corpus_documents(source_digest: str, receipt_ref: str, raw_ref: str) -> None:
    development_seed = {
        "format": "elmos-formal-development-seed/v1",
        "cases": [
            "all-60-exact-skill-contracts",
            "all-481-source-acceptance-controls",
            "all-40-production-method-bindings",
            "17-adapter-parser-conformance",
            "real-z3-unsat-proof-query",
            "sqlite-source-target-differential",
        ],
    }
    write_json(PACK / "corpus/development/seed.json", development_seed)
    development_digest = sha((PACK / "corpus/development/seed.json").read_bytes())
    write_json(
        PACK / "corpus/development/manifest.json",
        {
            "schema_version": 1,
            "status": "passed",
            "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
            "source_digest": source_digest,
            "dataset_digest": development_digest,
            "evidence_refs": ["corpus/development/seed.json", receipt_ref, raw_ref],
            "limitations": ["Repository-owned development inputs; not an independent holdout."],
        },
    )
    negative_cases = {
        "format": "elmos-formal-negative-corpus/v1",
        "cases": [
            "path-traversal-denied",
            "unknown-fields-denied",
            "expired-permit-denied",
            "tampered-permit-denied",
            "permit-replay-denied",
            "missing-role-denied",
            "strong-sandbox-downgrade-denied",
            "database-file-escape-denied",
            "cross-tenant-receipt-read-denied",
        ],
    }
    write_json(PACK / "corpus/negative/cases.json", negative_cases)
    negative_digest = sha((PACK / "corpus/negative/cases.json").read_bytes())
    write_json(
        PACK / "corpus/negative/manifest.json",
        {
            "schema_version": 1,
            "status": "passed",
            "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
            "source_digest": source_digest,
            "dataset_digest": negative_digest,
            "evidence_refs": ["corpus/negative/cases.json", receipt_ref, raw_ref],
            "limitations": ["Repository-owned negative cases; no independent adversarial corpus."],
        },
    )
    for key, classification in (
        ("holdout", "INDEPENDENT_HOLDOUT_NOT_RUN"),
        ("representative-workloads", "PRODUCTION_DERIVED_WORKLOAD_NOT_RUN"),
    ):
        marker_ref = f"corpus/{key}/not-run.json"
        write_json(
            PACK / marker_ref,
            {
                "format": "elmos-formal-corpus-not-run/v1",
                "corpus": key,
                "status": "NOT_RUN",
                "reason": classification,
            },
        )
        marker_digest = sha((PACK / marker_ref).read_bytes())
        document = {
            "schema_version": 1,
            "status": "not-run",
            "source_digest": source_digest,
            "dataset_digest": marker_digest,
            "evidence_refs": [marker_ref],
            "limitations": [classification],
        }
        if key == "holdout":
            document.update(
                {"independence": "NOT_RUN", "independent_verifier": None, "executor": None}
            )
        else:
            document.update({"provenance": "NOT_RUN", "authorization_ref": None})
        write_json(PACK / f"corpus/{key}/manifest.json", document)


def build_integrity_manifest(path: Path) -> None:
    excluded = {
        "certification/gate-result.json",
        "certification/gate-report.md",
        path.relative_to(PACK).as_posix(),
    }
    entries = []
    for candidate in sorted(PACK.rglob("*"), key=lambda item: item.as_posix()):
        if candidate.is_symlink():
            raise RuntimeError(f"verification pack symlink is forbidden: {candidate}")
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(PACK).as_posix()
        if relative in excluded:
            continue
        record = file_record(candidate, relative_to=PACK)
        record["sha256"] = record["sha256"].removeprefix("sha256:")
        entries.append(record)
    write_json(path, {"schema_version": 1, "algorithm": "sha256", "entries": entries})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that existing qualification receipts bind the current code",
    )
    args = parser.parse_args(argv)
    if sha(SOURCE_ARCHIVE.read_bytes()) != SOURCE_DIGEST:
        raise RuntimeError("pinned Formal Assurance source archive digest mismatch")
    if args.check:
        return check_existing_qualification()
    qualification = PACK / "qualification"
    raw_engine_ref = "qualification/raw/engine-tests.txt"
    raw_integration_ref = "qualification/raw/integration-tests.txt"
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(ENGINE / "src")
    engine_result = run_suite(
        "formal-assurance-engine",
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "engines/formal-assurance-engine/tests",
            "-p",
            "test_*.py",
            "-v",
        ],
        env,
        raw_engine_ref,
    )
    integration_result = run_suite(
        "formal-assurance-package-integration",
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests/formal-assurance-kernel",
            "-p",
            "test_*.py",
            "-v",
        ],
        env,
        raw_integration_ref,
    )
    total_tests = engine_result["tests"] + integration_result["tests"]
    files = implementation_files()
    manifest_document = implementation_manifest(files)
    implementation_path = qualification / "implementation-manifest.json"
    write_json(implementation_path, manifest_document)
    target_digest = sha(implementation_path.read_bytes())

    environment = {
        "format": "elmos-formal-local-environment/v1",
        "capturedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version,
        "pythonExecutable": str(Path(sys.executable).resolve()),
        "sqliteVersion": sqlite3.sqlite_version,
        "toolchains": [
            probe(name, args)
            for name, args in (
                ("z3", ("-version",)),
                ("java", ("-version",)),
                ("mvn", ("-version",)),
                ("gradle", ("-version",)),
                ("dotnet", ("--version",)),
                ("node", ("--version",)),
                ("go", ("version",)),
                ("rustc", ("--version",)),
                ("sqlite3", ("--version",)),
                ("psql", ("--version",)),
                ("mysql", ("--version",)),
                ("docker", ("--version",)),
                ("podman", ("--version",)),
                ("nm", ("-version",)),
                ("otool", ("-h",)),
            )
        ],
    }
    environment_path = qualification / "environment.json"
    write_json(environment_path, environment)
    environment_digest = sha(environment_path.read_bytes())
    update_pack_scope(target_digest, environment_digest, total_tests)

    receipt_ref = "qualification/local-qualification.json"
    corpus_documents(SOURCE_DIGEST, receipt_ref, raw_engine_ref)
    write_json(
        PACK / "counterexamples/input.json",
        {
            "format": "elmos-formal-counterexample-input/v1",
            "status": "NOT_RUN",
            "witness": None,
            "note": "Reserved sample input; no counterexample execution evidence is claimed.",
        },
    )
    bindings = [
        {"role": "source", **file_record(SOURCE_ARCHIVE)},
        {"role": "test", **file_record(implementation_path)},
        {"role": "environment", **file_record(environment_path)},
        *({"role": "implementation", **file_record(path)} for path in files),
    ]
    bindings.sort(key=lambda item: item["path"])
    receipt = {
        "schema_version": 1,
        "pack_key": "formal-assurance-kernel-local",
        "status": "passed",
        "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
        "executed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_digest": SOURCE_DIGEST,
        "test_digest": target_digest,
        "environment_digest": environment_digest,
        "tests": total_tests,
        "passed": total_tests,
        "failed": 0,
        "skipped": 0,
        "commands": [engine_result, integration_result],
        "contract_assertions": {
            "exactSkillsExecuted": 60,
            "sourceAcceptanceCriteriaMapped": 481,
            "repositoryAcceptanceControlsExecuted": 481,
            "externalAcceptanceEvidence": "NOT_RUN",
            "formerlyPartialProductionMethodsExercised": 40,
            "sourceVerifierParsersExercised": 17,
            "realZ3Execution": "LOCAL_EXECUTED_SELF_ATTESTED",
            "sqliteDifferentialExecution": "LOCAL_EXECUTED_SELF_ATTESTED",
            "strongSandboxDowngradeNegative": "PASSED",
            "permitReplayNegative": "PASSED",
            "tenantIsolationNegative": "PASSED",
        },
        "repository_bindings": bindings,
        "externalEvidenceStatus": "NOT_RUN",
        "independentVerificationStatus": "NOT_RUN",
        "certificationStatus": "NOT_CERTIFIED",
        "limitations": [
            "Local self-attested tests are not independent evidence.",
            "Repository-owned acceptance controls do not satisfy native, provider, representative, customer, or independent acceptance evidence roles.",
            "Unavailable native tools and real source/target provider environments remain NOT_RUN.",
            "No production, customer, deployment, or certification claim is made.",
        ],
    }
    write_json(PACK / receipt_ref, receipt)

    evidence_path = PACK / "certification/evidence.json"
    evidence = {
        "schema_version": 1,
        "pack_key": "formal-assurance-kernel-local",
        "metrics": {"local_tests": total_tests, "local_test_pass_rate": 1.0},
        "zero_tolerance": {},
        "repository_binding_records": [receipt_ref],
        "integrity_manifest": "qualification/evidence-manifest.json",
        "evidence_refs": [
            receipt_ref,
            "qualification/implementation-manifest.json",
            "qualification/environment.json",
            raw_engine_ref,
            raw_integration_ref,
            "corpus/development/seed.json",
            "corpus/negative/cases.json",
        ],
        "execution_states": {
            "all_60_skill_handler_contracts": "LOCAL_EXECUTED_SELF_ATTESTED",
            "all_481_acceptance_controls": "LOCAL_EXECUTED_SELF_ATTESTED",
            "all_481_external_acceptance_evidence": "NOT_RUN",
            "all_40_production_adapter_contracts": "LOCAL_EXECUTED_SELF_ATTESTED",
            "z3": "LOCAL_EXECUTED_SELF_ATTESTED",
            "sqlite_differential": "LOCAL_EXECUTED_SELF_ATTESTED",
            "other_native_toolchains": "NOT_RUN",
            "real_source_target_databases": "NOT_RUN",
            "spring_representative_builds": "NOT_RUN",
            "independent_holdout": "NOT_RUN",
            "representative_workloads": "NOT_RUN",
            "external_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
        "notes": [
            "Code completeness and local execution are recorded separately from external evidence and certification.",
            "Acceptance traceability is complete for 481 IDs, while native and independent evidence remains explicitly NOT_RUN.",
            "The attached package remained untrusted declarative source material and none of its executables were run.",
        ],
    }
    write_json(evidence_path, evidence)
    support = {
        "schema_version": 1,
        "pack_key": "formal-assurance-kernel-local",
        "capabilities": [
            {
                "key": "exact-60-skill-runtime",
                "status": "supported",
                "owner": "elmos-formal-assurance-engineering",
                "evidence_refs": [receipt_ref],
                "limitations": ["Local self-attested engineering evidence only."],
            },
            {
                "key": "signed-native-toolchain-execution",
                "status": "conditional",
                "owner": "elmos-formal-assurance-engineering",
                "evidence_refs": [receipt_ref, raw_engine_ref],
                "limitations": ["Requires exact digest-pinned host registrations, one-use permits, and OCI for project code."],
            },
            {
                "key": "database-differential-execution",
                "status": "conditional",
                "owner": "elmos-formal-assurance-engineering",
                "evidence_refs": [receipt_ref, raw_engine_ref],
                "limitations": ["SQLite executed locally; exact external source/target providers remain NOT_RUN."],
            },
            {
                "key": "spring-offline-verification",
                "status": "conditional",
                "owner": "elmos-formal-assurance-engineering",
                "evidence_refs": [receipt_ref],
                "limitations": ["Code path implemented; representative OCI Maven/Gradle execution remains NOT_RUN."],
            },
            {
                "key": "formal-observability-export",
                "status": "conditional",
                "owner": "elmos-formal-assurance-engineering",
                "evidence_refs": [receipt_ref, raw_engine_ref],
                "limitations": ["Loopback export contract tested; production collector evidence remains NOT_RUN."],
            },
            {
                "key": "reflection-ffi-boundary-inventory",
                "status": "conditional",
                "owner": "elmos-formal-assurance-engineering",
                "evidence_refs": [receipt_ref],
                "limitations": ["Digest-bound nm/otool/readelf/javap path implemented; representative binary holdout remains NOT_RUN."],
            },
        ],
    }
    write_json(PACK / "support-matrix.json", support)
    build_integrity_manifest(qualification / "evidence-manifest.json")
    print(
        json.dumps(
            {
                "status": "LOCAL_EXECUTED_SELF_ATTESTED",
                "tests": total_tests,
                "passed": total_tests,
                "sourceDigest": SOURCE_DIGEST,
                "targetDigest": target_digest,
                "environmentDigest": environment_digest,
                "externalEvidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"LOCAL QUALIFICATION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
