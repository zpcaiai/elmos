"""Read-only validation of the attached ETGB source package."""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


EXPECTED_ARCHIVE_SHA256_V11 = "6c95898310e1b9052e5431c7996e1f397b54612084ef70761d9bb5a78760fe1e"
EXPECTED_ARCHIVE_SHA256_V20 = "b11a487b63a0aee7ffb03a247d9439e8c6b9ee19f10c22aca2f7a3dd8bf0072e"
EXPECTED_ARCHIVE_SHA256 = EXPECTED_ARCHIVE_SHA256_V20

PACKAGE_ROOT_NAME_V11 = "elmos-etgb-sota-skills-package-v1.1.0"
PACKAGE_ROOT_NAME_V20 = "elmos-etgb-full-product-assurance-skills-package-v2.0.0"
PACKAGE_ROOT_NAME = PACKAGE_ROOT_NAME_V20

PACKAGE_VERSION_V11 = "1.1.0"
PACKAGE_VERSION_V20 = "2.0.0"
PACKAGE_VERSION = PACKAGE_VERSION_V20

PACKAGE_ID_V11 = "elmos-etgb-sota-skills-package"
PACKAGE_ID_V20 = "elmos-etgb-full-product-assurance-skills-package"
PACKAGE_ID = PACKAGE_ID_V20

SKILL_NAMES_V11 = (
    "etgb-orchestrator",
    "test-case-authoring",
    "spring-modernization-validation",
    "repository-translation-validation",
    "project-generation-validation",
    "sql-dialect-routine-validation",
    "differential-oracle-engine",
    "metamorphic-fuzz-mutation",
    "corpus-governance",
    "release-certification",
    "production-harness-integration",
    "environment-authority-sandbox",
    "checkpoint-resume-recovery",
    "evidence-provenance-ledger",
    "budget-cost-eta-governance",
    "risk-based-test-selection",
    "benchmark-integrity-hidden-tests",
    "observability-failure-triage",
    "performance-scale-certification",
    "statistical-validity-reproducibility",
    "supply-chain-artifact-security",
    "incident-regression-learning",
    "multi-tenant-scheduling-isolation",
    "release-candidate-integrity",
)

SKILL_NAMES_V20 = (
    "etgb-orchestrator",
    "test-case-authoring",
    "spring-modernization-validation",
    "repository-translation-validation",
    "project-generation-validation",
    "sql-dialect-routine-validation",
    "differential-oracle-engine",
    "metamorphic-fuzz-mutation",
    "corpus-governance",
    "release-certification",
    "production-harness-integration",
    "environment-authority-sandbox",
    "checkpoint-resume-recovery",
    "evidence-provenance-ledger",
    "budget-cost-eta-governance",
    "risk-based-test-selection",
    "benchmark-integrity-hidden-tests",
    "observability-failure-triage",
    "performance-scale-certification",
    "statistical-validity-reproducibility",
    "supply-chain-artifact-security",
    "incident-regression-learning",
    "multi-tenant-scheduling-isolation",
    "release-candidate-integrity",
    "identity-access-tenant-validation",
    "platform-control-plane-validation",
    "repository-ingestion-context-validation",
    "multimodal-document-processing-validation",
    "ai-runtime-model-routing-validation",
    "agent-protocol-tooling-validation",
    "rag-memory-knowledge-validation",
    "project-intelligence-validation",
    "online-ide-debug-validation",
    "artifact-document-diagram-validation",
    "collaboration-integrations-validation",
    "billing-entitlements-validation",
    "payment-finance-validation",
    "api-sdk-webhook-validation",
    "storage-search-cache-validation",
    "deployment-operations-validation",
    "security-privacy-compliance-validation",
    "ui-accessibility-localization-validation",
    "analytics-admin-support-validation",
    "notifications-scheduler-validation",
    "ai-solution-factory-validation",
    "data-bigdata-solution-validation",
    "commercial-delivery-certification-validation",
    "product-journey-validation",
    "standards-assurance-validation",
    "full-product-coverage-governance",
)

SKILL_NAMES = SKILL_NAMES_V20
_CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and "\x00" not in name and "//" not in name and not path.is_absolute() and all(part not in {".", ".."} for part in path.parts)



def _checksum_rows(content: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for number, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            continue
        match = _CHECKSUM_LINE.fullmatch(line)
        if not match:
            raise ValueError(f"invalid SHA256SUMS row {number}")
        if match.group(2) in rows:
            raise ValueError(f"duplicate SHA256SUMS path: {match.group(2)}")
        rows[match.group(2)] = match.group(1)
    return rows


def _archive_kind(archive: Path) -> str:
    if zipfile.is_zipfile(archive):
        return "zip"
    if tarfile.is_tarfile(archive):
        return "tar"
    raise ValueError(f"unsupported source archive format: {archive}")


def _archive_members(archive: Path, kind: str) -> tuple[list[str], dict[str, bytes], list[str]]:
    """Read archive members as inert bytes and surface link members separately."""

    names: list[str] = []
    files: dict[str, bytes] = {}
    links: list[str] = []
    if kind == "zip":
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                names.append(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    links.append(info.filename)
                elif not info.is_dir():
                    files[info.filename] = package.read(info)
    else:
        with tarfile.open(archive, mode="r:*") as package:
            for info in package.getmembers():
                names.append(info.name)
                if info.issym() or info.islnk():
                    links.append(info.name)
                elif info.isfile():
                    handle = package.extractfile(info)
                    if handle is None:
                        raise ValueError(f"archive member has no readable payload: {info.name}")
                    files[info.name] = handle.read()
    return names, files, links


def verify_source_package(archive: Path, *, extracted: Path | None = None, expected_archive_sha256: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    archive = archive.resolve(strict=True)
    actual_digest = file_sha256(archive)
    
    # Determine version from archive name or content
    is_v11 = "v1.1.0" in archive.name or actual_digest == EXPECTED_ARCHIVE_SHA256_V11
    package_root_name = PACKAGE_ROOT_NAME_V11 if is_v11 else PACKAGE_ROOT_NAME_V20
    package_version = PACKAGE_VERSION_V11 if is_v11 else PACKAGE_VERSION_V20
    package_id = PACKAGE_ID_V11 if is_v11 else PACKAGE_ID_V20
    skill_names = SKILL_NAMES_V11 if is_v11 else SKILL_NAMES_V20
    expected_digest = expected_archive_sha256 or (EXPECTED_ARCHIVE_SHA256_V11 if is_v11 else EXPECTED_ARCHIVE_SHA256_V20)

    if expected_digest and actual_digest != expected_digest:
        errors.append(f"archive digest mismatch: expected {expected_digest}, got {actual_digest}")
    names: list[str] = []
    checksums: dict[str, str] = {}
    try:
        kind = _archive_kind(archive)
        names, payloads, links = _archive_members(archive, kind)
        duplicate_names = sorted({name for name in names if names.count(name) > 1})
        errors.extend(f"duplicate archive member: {name}" for name in duplicate_names)
        errors.extend(f"unsafe archive member: {name}" for name in names if not _safe_member(name))
        errors.extend(f"link archive member is forbidden: {name}" for name in links)
        prefix = package_root_name + "/"
        if not all(name == package_root_name or name.startswith(prefix) for name in names):
            errors.append("archive contains a member outside the pinned package root")
        relative = {name[len(prefix):]: name for name in payloads if name.startswith(prefix)}
        required = {"PACKAGE_MANIFEST.json", "SHA256SUMS", "skills/manifest.yaml", "suites/suite.yaml", "schemas/test-case.schema.json"}
        errors.extend(f"missing package member: {path}" for path in sorted(required - set(relative)))
        if "SHA256SUMS" in relative:
            try:
                checksums = _checksum_rows(payloads[relative["SHA256SUMS"]].decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                errors.append(str(exc))
        for path, expected in checksums.items():
            archive_name = relative.get(path)
            if archive_name is None:
                errors.append(f"checksum references missing member: {path}")
                continue
            actual = hashlib.sha256(payloads[archive_name]).hexdigest()
            if actual != expected:
                errors.append(f"package checksum mismatch: {path}")
        manifest: dict[str, Any] = {}
        try:
            manifest = json.loads(payloads[relative["PACKAGE_MANIFEST.json"]])
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"invalid PACKAGE_MANIFEST.json: {exc}")
        if manifest:
            if manifest.get("package") != package_id or manifest.get("version") != package_version:
                errors.append("package manifest identity or version mismatch")
            checksum_file_count = len(checksums) - (1 if "PACKAGE_MANIFEST.json" in checksums else 0)
            if manifest.get("file_count") != checksum_file_count:
                errors.append("package manifest file_count does not match SHA256SUMS")
        try:
            skill_manifest = yaml.safe_load(payloads[relative["skills/manifest.yaml"]])
            declared = [item.get("name") for item in skill_manifest.get("skills", [])]
            if tuple(declared) != skill_names:
                errors.append(f"skill registry mismatch: {declared}")
            declared_names = set(declared)
            edges = [(item.get("name"), dependency) for item in skill_manifest.get("skills", []) for dependency in item.get("depends_on", [])]
            errors.extend(f"skill dependency references unknown skill: {owner}->{dependency}" for owner, dependency in edges if dependency not in declared_names)
            graph = {name: [] for name in declared_names}
            for owner, dependency in edges:
                graph[owner].append(dependency)
            visiting: set[str] = set()
            visited: set[str] = set()
            def visit(name: str) -> None:
                if name in visiting:
                    raise ValueError(f"skill dependency cycle at {name}")
                if name in visited:
                    return
                visiting.add(name)
                for dependency in graph[name]:
                    visit(dependency)
                visiting.remove(name)
                visited.add(name)
            for name in graph:
                visit(name)
        except (KeyError, TypeError, AttributeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"invalid skill manifest: {exc}")
    except (OSError, tarfile.TarError, ValueError) as exc:
        errors.append(str(exc))
        relative = {}
    if extracted:
        extracted = extracted.resolve(strict=True)
        for path in checksums:
            local = extracted / path
            if local.is_symlink() or not local.is_file():
                errors.append(f"extracted source missing: {path}")
                continue
            if file_sha256(local) != checksums[path]:
                errors.append(f"extracted source drift: {path}")
        extra = [path.relative_to(extracted).as_posix() for path in extracted.rglob("*") if path.is_file() and not any(part in {".venv", ".pytest_cache", "__pycache__"} or part.endswith(".egg-info") for part in path.relative_to(extracted).parts) and path.relative_to(extracted).as_posix() not in checksums and path.relative_to(extracted).as_posix() != "SHA256SUMS"]
        if extra:
            warnings.append(f"extracted tree has {len(extra)} generated or unmanifested files")
    return {
        "valid": not errors,
        "archive": str(archive),
        "archive_sha256": actual_digest,
        "archive_matches_pin": actual_digest == expected_digest,
        "archive_entries": len(names),
        "checksum_entries": len(checksums),
        "package_version": package_version,
        "skills": list(skill_names),
        "errors": errors,
        "warnings": warnings,
    }
