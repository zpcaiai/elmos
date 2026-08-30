#!/usr/bin/env python3
"""Create or verify the Foundry's deterministic local qualification receipt.

This utility treats the source archive as opaque bytes.  It never imports,
extracts, or executes archive content.  Its receipt records bounded local
engineering evidence only and cannot issue a production certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, cast, Iterable, Sequence


SCHEMA_VERSION = "elmos.knowledge-skill-model-foundry.qualification.v2"
PACKAGE_ID = "elmos-knowledge-skill-model-foundry-v3.0.0"
PACKAGE_VERSION = "3.0.0"
EXPECTED_ARCHIVE_SHA256 = (
    "e29673a598756deff422e8dd7f36b2826e9c1aaff6df22db2c0699b0857ee0e4"
)
EXPECTED_ARCHIVE_BYTES = 16_668_810
LOCAL_SEMANTIC_SKILLS = frozenset(
    {
        "artifact-identity-and-hashing",
        "artifact-normalization",
        "capability-dependency-graph",
        "complexity-risk-cost-latency-routing",
        "dataset-contract-and-schema",
        "dataset-quarantine-management",
        "environment-owned-authority",
        "evidence-aggregation-and-completeness",
        "experience-episode-capture",
        "health-warmup-and-readiness",
        "hierarchical-skill-registry",
        "least-privilege-tool-authorization",
        "model-version-pinning-determinism",
        "package-conformance-validator",
        "progressive-skill-disclosure",
        "provenance-and-lineage-capture",
        "sensitive-data-and-secret-detection",
        "skill-activation-router",
        "skill-dependency-resolver",
        "tamper-evident-audit-log",
        "task-canonicalization-and-normalization",
        "tenant-memory-isolation-and-replay",
        "tool-call-schema-and-policy-check",
        "typed-skill-contract",
        "uncertainty-and-abstention-evaluation",
        "workspace-attachment-ownership-fencing",
    }
)

ARCHIVE_PATH = Path("skills/subskills/elmos-knowledge-skill-model-foundry-v3.0.0.zip")
ENGINE_ROOT = Path("engines/knowledge-skill-model-foundry-engine")
CATALOG_PATH = ENGINE_ROOT / "catalog/compiled-catalog.json"
PACKAGE_REPORT_PATH = ENGINE_ROOT / "catalog/package-report.json"
ENGINE_RECEIPT_PATH = ENGINE_ROOT / "qualification/local-qualification.json"
DOCS_ROOT = Path("docs/knowledge-skill-model-foundry")
DOCS_RECEIPT_PATH = DOCS_ROOT / "QUALIFICATION_RECEIPT.json"
ROOT_TESTS = Path("tests/knowledge-skill-model-foundry-skills")
IMPORTER_PATH = Path("tooling/integrate_knowledge_skill_model_foundry_skills.py")
QUALIFIER_PATH = Path("tooling/qualify_knowledge_skill_model_foundry.py")

IMPLEMENTATION_ROOTS = (
    Path("AGENTS.md"),
    Path("Makefile"),
    ENGINE_ROOT,
    DOCS_ROOT,
    ROOT_TESTS,
    IMPORTER_PATH,
    QUALIFIER_PATH,
)
EXCLUDED_PATHS = frozenset(
    {
        CATALOG_PATH,
        PACKAGE_REPORT_PATH,
        ENGINE_RECEIPT_PATH,
        DOCS_RECEIPT_PATH,
    }
)
TRANSIENT_NAMES = frozenset({"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"})
TRANSIENT_SUFFIXES = (".pyc", ".pyo")

ENGINE_SOURCE = "engines/knowledge-skill-model-foundry-engine/src"
ENGINE_PACKAGE = f"{ENGINE_SOURCE}/elmos_foundry"
ENGINE_TESTS = "engines/knowledge-skill-model-foundry-engine/tests"
ROOT_TESTS_TEXT = ROOT_TESTS.as_posix()
LOCAL_CHECK_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "direct_zip_importer_check",
        "command": [
            "uv",
            "run",
            "--quiet",
            "--with",
            "pyyaml==6.0.2",
            "--with",
            "jsonschema==4.25.1",
            "python",
            IMPORTER_PATH.as_posix(),
            "--check",
        ],
        "environment": {"PYTHONDONTWRITEBYTECODE": "1"},
        "timeout_seconds": 300,
    },
    {
        "id": "ruff_static_analysis",
        "command": [
            "uv",
            "run",
            "--quiet",
            "--with",
            "ruff==0.12.10",
            "ruff",
            "check",
            IMPORTER_PATH.as_posix(),
            QUALIFIER_PATH.as_posix(),
            ENGINE_SOURCE,
            ENGINE_TESTS,
            ROOT_TESTS_TEXT,
        ],
        "environment": {},
        "timeout_seconds": 180,
    },
    {
        "id": "strict_mypy",
        "command": [
            "uv",
            "run",
            "--quiet",
            "--with",
            "mypy==1.17.1",
            "mypy",
            "--strict",
            ENGINE_PACKAGE,
            QUALIFIER_PATH.as_posix(),
        ],
        "environment": {"PYTHONPATH": ENGINE_SOURCE},
        "timeout_seconds": 300,
    },
    {
        "id": "python_compileall",
        "command": [
            "uv",
            "run",
            "--quiet",
            "python",
            "-m",
            "compileall",
            "-q",
            ENGINE_PACKAGE,
            IMPORTER_PATH.as_posix(),
            QUALIFIER_PATH.as_posix(),
        ],
        "environment": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ENGINE_SOURCE},
        "timeout_seconds": 180,
    },
    {
        "id": "engine_unittest_suite",
        "command": [
            "uv",
            "run",
            "--quiet",
            "--with",
            "pyyaml==6.0.2",
            "--with",
            "jsonschema==4.25.1",
            "python",
            "-m",
            "unittest",
            "discover",
            "-s",
            ENGINE_TESTS,
            "-p",
            "test_*.py",
        ],
        "environment": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ENGINE_SOURCE},
        "timeout_seconds": 300,
    },
    {
        "id": "repository_integration_unittest_suite",
        "command": [
            "uv",
            "run",
            "--quiet",
            "--with",
            "pyyaml==6.0.2",
            "--with",
            "jsonschema==4.25.1",
            "python",
            "-m",
            "unittest",
            "discover",
            "-s",
            ROOT_TESTS_TEXT,
            "-p",
            "test_*.py",
        ],
        "environment": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ENGINE_SOURCE},
        "timeout_seconds": 300,
    },
)


class QualificationError(RuntimeError):
    """Raised when qualification inputs or receipts fail closed."""


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationError(f"invalid JSON input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise QualificationError(f"JSON input must be an object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise QualificationError(message)


def _is_transient(relative: Path) -> bool:
    return any(part in TRANSIENT_NAMES for part in relative.parts) or relative.name.endswith(
        TRANSIENT_SUFFIXES
    )


def implementation_files(repo_root: Path) -> tuple[Path, ...]:
    """Return the exact, normalized set of implementation files to bind."""

    files: set[Path] = set()
    resolved_root = repo_root.resolve()
    for relative_root in IMPLEMENTATION_ROOTS:
        absolute = repo_root / relative_root
        if not absolute.exists():
            raise QualificationError(f"required implementation path is absent: {relative_root}")
        if absolute.is_symlink():
            raise QualificationError(f"qualification root must not be a symlink: {relative_root}")
        candidates: Iterable[Path] = (absolute,) if absolute.is_file() else absolute.rglob("*")
        for candidate in candidates:
            relative = candidate.relative_to(repo_root)
            if relative in EXCLUDED_PATHS or _is_transient(relative):
                continue
            if candidate.is_symlink():
                raise QualificationError(f"symlink is forbidden in qualification scope: {relative}")
            if candidate.is_dir():
                continue
            if not candidate.is_file():
                raise QualificationError(f"special file is forbidden in qualification scope: {relative}")
            try:
                candidate.resolve().relative_to(resolved_root)
            except ValueError as exc:
                raise QualificationError(f"implementation path escapes repository: {relative}") from exc
            files.add(relative)
    if not files:
        raise QualificationError("implementation qualification scope is empty")
    return tuple(sorted(files, key=lambda path: path.as_posix().encode("utf-8")))


def implementation_tree(repo_root: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for relative in implementation_files(repo_root):
        sha256, size = _sha256_file(repo_root / relative)
        entries.append({"path": relative.as_posix(), "sha256": sha256, "bytes": size})
    encoded = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "file_count": len(entries),
        "roots": [path.as_posix() for path in IMPLEMENTATION_ROOTS],
        "exclusions": sorted(path.as_posix() for path in EXCLUDED_PATHS),
        "transient_exclusions": sorted(TRANSIENT_NAMES) + list(TRANSIENT_SUFFIXES),
    }


def _baseline_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    commit = result.stdout.strip().lower()
    return commit if len(commit) == 40 and all(char in "0123456789abcdef" for char in commit) else None


def recorded_local_checks() -> list[dict[str, Any]]:
    """Return the deterministic evidence declarations populated only by --write."""

    return [
        {
            "id": spec["id"],
            "command": list(spec["command"]),
            "environment": dict(spec["environment"]),
            "timeout_seconds": spec["timeout_seconds"],
            "status": "PASS",
        }
        for spec in LOCAL_CHECK_SPECS
    ]


def run_local_checks(repo_root: Path) -> list[dict[str, Any]]:
    """Actually execute the allowlisted, repository-owned local checks."""

    for spec in LOCAL_CHECK_SPECS:
        environment = {**os.environ, "LC_ALL": "C", **spec["environment"]}
        try:
            result = subprocess.run(
                spec["command"],
                cwd=repo_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=spec["timeout_seconds"],
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise QualificationError(f"local check could not run ({spec['id']}): {exc}") from exc
        if result.returncode != 0:
            output = (result.stdout + "\n" + result.stderr).strip()
            tail = output[-4_000:] if output else "no output"
            raise QualificationError(
                f"local check failed ({spec['id']}, exit {result.returncode}): {tail}"
            )
    return recorded_local_checks()


def _qualification_inputs(receipt: dict[str, Any]) -> dict[str, Any]:
    """Select every content binding that must remain stable while checks run."""

    return {
        "source_archive": receipt["source_archive"],
        "baseline_commit": receipt["baseline_commit"],
        "generated_artifacts": receipt["generated_artifacts"],
        "implementation_tree": receipt["implementation_tree"],
    }


def _validate_catalog_and_report(
    catalog: dict[str, Any], report: dict[str, Any], archive_sha256: str
) -> None:
    package = report.get("package")
    _require(isinstance(package, dict), "package report package is absent")
    package = cast(dict[str, Any], package)
    _require(package.get("id") == PACKAGE_ID, "package report package id drift")
    _require(package.get("version") == PACKAGE_VERSION, "package report version drift")
    _require(package.get("archive_sha256") == archive_sha256, "package report archive digest drift")
    _require(report.get("source_execution") == "NEVER_EXECUTED", "source execution boundary drift")
    _require(report.get("external_evidence_status") == "NOT_RUN", "external evidence overclaim")
    _require(report.get("certification_status") == "NOT_CERTIFIED", "certification overclaim")
    _require(
        report.get("capability_states") == {"LOCAL": 26, "PREPARE_ONLY": 1_284},
        "package report capability-state distribution drift",
    )

    catalog_package = catalog.get("package")
    _require(isinstance(catalog_package, dict), "compiled catalog package is absent")
    catalog_package = cast(dict[str, Any], catalog_package)
    _require(catalog_package.get("id") == PACKAGE_ID, "compiled catalog package id drift")
    _require(catalog_package.get("version") == PACKAGE_VERSION, "compiled catalog version drift")
    _require(catalog_package.get("archive_sha256") == archive_sha256, "catalog archive digest drift")
    atomic = catalog.get("atomic_skills")
    meta = catalog.get("meta_skills")
    pipelines = catalog.get("pipelines")
    _require(isinstance(atomic, list) and len(atomic) == 1_310, "atomic Skill count drift")
    _require(isinstance(meta, list) and len(meta) == 41, "Meta-Skill count drift")
    _require(isinstance(pipelines, list) and len(pipelines) == 14, "pipeline count drift")
    atomic = cast(list[Any], atomic)
    pipelines = cast(list[Any], pipelines)
    local_names = {
        str(row.get("name"))
        for row in atomic
        if isinstance(row, dict) and row.get("capability_state") == "LOCAL"
    }
    _require(
        local_names == LOCAL_SEMANTIC_SKILLS,
        "compiled LOCAL Skill set does not match the exact semantic implementation set",
    )
    _require(
        all(
            isinstance(row, dict)
            and row.get("capability_state")
            == ("LOCAL" if row.get("name") in LOCAL_SEMANTIC_SKILLS else "PREPARE_ONLY")
            and row.get("semantic_handler_binding")
            == (
                f"local.{str(row.get('name'))}"
                if row.get("name") in LOCAL_SEMANTIC_SKILLS
                else "UNBOUND"
            )
            and row.get("external_evidence_status") == "NOT_RUN"
            and row.get("certification_status") == "NOT_CERTIFIED"
            for row in atomic
        ),
        "compiled atomic Skill capability or evidence boundary drift",
    )
    _require(
        all(isinstance(row, dict) and row.get("execution_mode") == "PREPARE_ONLY" for row in pipelines),
        "compiled pipeline execution boundary drift",
    )


def build_receipt(repo_root: Path) -> dict[str, Any]:
    """Build a deterministic receipt after all bounded checks pass."""

    repo_root = repo_root.resolve()
    archive = repo_root / ARCHIVE_PATH
    catalog_path = repo_root / CATALOG_PATH
    report_path = repo_root / PACKAGE_REPORT_PATH
    for path in (archive, catalog_path, report_path):
        if not path.is_file() or path.is_symlink():
            raise QualificationError(f"required regular input is absent or unsafe: {path}")

    archive_sha256, archive_bytes = _sha256_file(archive)
    _require(archive_sha256 == EXPECTED_ARCHIVE_SHA256, "source archive SHA-256 mismatch")
    _require(archive_bytes == EXPECTED_ARCHIVE_BYTES, "source archive byte-size mismatch")
    catalog_sha256, catalog_bytes = _sha256_file(catalog_path)
    report_sha256, report_bytes = _sha256_file(report_path)
    catalog = _read_json(catalog_path)
    report = _read_json(report_path)
    _validate_catalog_and_report(catalog, report, archive_sha256)
    tree = implementation_tree(repo_root)

    return {
        "schema_version": SCHEMA_VERSION,
        "package": {"id": PACKAGE_ID, "version": PACKAGE_VERSION},
        "source_archive": {
            "path": ARCHIVE_PATH.as_posix(),
            "sha256": archive_sha256,
            "bytes": archive_bytes,
            "execution": "NEVER_EXECUTED",
            "handling": "OPAQUE_BYTES_ONLY",
        },
        "baseline_commit": _baseline_commit(repo_root),
        "generated_artifacts": {
            "compiled_catalog": {
                "path": CATALOG_PATH.as_posix(),
                "sha256": catalog_sha256,
                "bytes": catalog_bytes,
            },
            "package_report": {
                "path": PACKAGE_REPORT_PATH.as_posix(),
                "sha256": report_sha256,
                "bytes": report_bytes,
            },
        },
        "implementation_tree": tree,
        "local_qualification": {
            "state": "READY_FOR_EXTERNAL_GATE",
            "maximum_state": "READY_FOR_EXTERNAL_GATE",
            "applies_to": "BOUNDED_LOCAL_ENGINEERING_IMPLEMENTATION_ONLY",
            "capability_scope": {
                "compiled_contracts_validated": 1_310,
                "exact_local_semantic_handlers_exercised": 26,
                "prepare_only_skills": 1_284,
            },
            "evidence_status": "LOCAL_EXECUTED_SELF_ATTESTED",
            "evidence_capture": "EXECUTED_BY_WRITE_MODE_ONLY",
            "checks": recorded_local_checks(),
        },
        "evidence_boundaries": {
            "external": "NOT_RUN",
            "customer": "NOT_RUN",
            "independent": "NOT_RUN",
            "native_runtime": "NOT_RUN",
            "provider": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
        "side_effects": {
            "authorized": False,
            "performed": False,
            "source_archive_content_executed": False,
        },
    }


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_receipts(repo_root: Path, receipt: dict[str, Any]) -> None:
    payload = _canonical_bytes(receipt)
    staged: list[tuple[Path, Path]] = []
    try:
        for relative in (ENGINE_RECEIPT_PATH, DOCS_RECEIPT_PATH):
            target = repo_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            temporary.chmod(0o644)
            staged.append((temporary, target))
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, _target in staged:
            temporary.unlink(missing_ok=True)


def verify_receipts(repo_root: Path, expected: dict[str, Any]) -> None:
    expected_bytes = _canonical_bytes(expected)
    observed: list[bytes] = []
    for relative in (ENGINE_RECEIPT_PATH, DOCS_RECEIPT_PATH):
        path = repo_root / relative
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise QualificationError(f"qualification receipt is absent: {relative}") from exc
        if payload != expected_bytes:
            raise QualificationError(f"qualification receipt is stale or mismatched: {relative}")
        observed.append(payload)
    if observed[0] != observed[1]:
        raise QualificationError("dual qualification receipts are not byte-identical")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true", help="atomically write both receipts")
    modes.add_argument("--check", action="store_true", help="fail on input or receipt drift")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    try:
        if args.write:
            before = build_receipt(repo_root)
            run_local_checks(repo_root)
            receipt = build_receipt(repo_root)
            if _qualification_inputs(before) != _qualification_inputs(receipt):
                raise QualificationError("qualification inputs drifted while local checks were running")
            write_receipts(repo_root, receipt)
            verify_receipts(repo_root, build_receipt(repo_root))
            mode = "WRITE"
        else:
            receipt = build_receipt(repo_root)
            verify_receipts(repo_root, receipt)
            mode = "CHECK"
    except QualificationError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": mode,
                "qualification_state": receipt["local_qualification"]["state"],
                "implementation_tree_sha256": receipt["implementation_tree"]["sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
