#!/usr/bin/env python3
"""Build the deterministic, fail-closed Pricing and Billing runtime binding.

The builder treats the supplied archive and repository sources as data.  It never
imports the pricing engine, invokes a handler, or executes a helper from the source
archive.  The resulting document binds exact source bytes, installed identities,
requirement traceability, and task-owned runtime/test trees without raising any
external-evidence or certification claim.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


ARCHIVE_RELATIVE = PurePosixPath("skills/subskills/elmos-pricing-billing-skills-v1.0.0.zip")
ARCHIVE_SHA256 = "9f7440b69a82a52172a1f62da915d96cfa4e0326dc04a305603c76001c8e88bc"
TRACEABILITY_MEMBER = (
    "elmos-pricing-billing-skills-v1.0.0/manifests/requirements.traceability.csv"
)
INSTALLED_MANIFEST_RELATIVE = PurePosixPath("docs/pricing-billing-skills/installed-manifest.json")
REGISTRY_RELATIVE = PurePosixPath(
    "engines/pricing-billing-engine/src/elmos_pricing_billing/registry.py"
)
REQUIREMENTS_RELATIVE = PurePosixPath(
    "verification-packs/pricing-billing-local-v1/requirements"
)
OUTPUT_RELATIVE = PurePosixPath(
    "verification-packs/pricing-billing-local-v1/runtime-binding.json"
)

MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_TRACEABILITY_BYTES = 512 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_REGISTRY_BYTES = 1024 * 1024
MAX_REQUIREMENT_FILE_BYTES = 512 * 1024
MAX_REQUIREMENT_TOTAL_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_TREE_FILE_BYTES = 4 * 1024 * 1024
MAX_TREE_TOTAL_BYTES = 64 * 1024 * 1024
MAX_TREE_FILES = 20_000

EXACT_SKILLS = (
    "elmos-billing-orchestrator",
    "elmos-pricing-product-model",
    "elmos-plan-catalog-entitlements",
    "elmos-credit-wallet-ledger",
    "elmos-usage-metering",
    "elmos-task-cost-estimation",
    "elmos-quote-budget-guard",
    "elmos-project-pricing-contracts",
    "elmos-subscription-invoicing",
    "elmos-payments-reconciliation",
    "elmos-refunds-disputes",
    "elmos-enterprise-byok",
    "elmos-cost-margin-analytics",
    "elmos-billing-admin-ux",
    "elmos-security-compliance",
    "elmos-billing-observability-ops",
    "elmos-billing-testing-certification",
    "elmos-rollout-migration",
)

EXACT_REQUIREMENTS = tuple(
    f"EB-{skill_number:02d}-{requirement_number:03d}"
    for skill_number in range(1, 19)
    for requirement_number in range(1, 11)
)

SKILL_BY_PREFIX = {
    f"EB-{index:02d}": skill_name
    for index, skill_name in enumerate(EXACT_SKILLS, start=1)
}

IMPLEMENTATION_ALIASES = {
    "DECLARED": "DECLARED",
    "MISSING": "DECLARED",
    "NOT_RUN": "DECLARED",
    "STUB": "DECLARED",
    "PARTIAL": "PARTIAL",
    "LOCAL_CODE_ADDED_UNVERIFIED": "LOCAL_IMPLEMENTED",
    "LOCAL_CODED_UNVERIFIED": "LOCAL_IMPLEMENTED",
    "LOCAL_CODE_IMPLEMENTED": "LOCAL_IMPLEMENTED",
    "LOCAL_IMPLEMENTED": "LOCAL_IMPLEMENTED",
    "IMPLEMENTED": "LOCAL_IMPLEMENTED",
    "IMPLEMENTED_LOCAL_REFERENCE": "LOCAL_IMPLEMENTED",
    "LOCAL_EXECUTED": "LOCAL_EXECUTED",
}
ALLOWED_TEST_EXECUTION = frozenset({"NOT_RUN", "LOCAL_EXECUTED"})
ALLOWED_EXTERNAL_EVIDENCE = frozenset({"NOT_RUN", "LOCAL_EXECUTED"})

EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "cache",
        "caches",
        "venv",
    }
)

RUNTIME_REQUIRED_ROOTS = (
    PurePosixPath("engines/pricing-billing-engine/src"),
)
RUNTIME_OPTIONAL_PATHS = (
    PurePosixPath("engines/pricing-billing-engine/pyproject.toml"),
    PurePosixPath("engines/pricing-billing-engine/uv.lock"),
    PurePosixPath(
        "modules/commercial-operations/src/main/java/io/elmos/commercial/"
        "PricingBillingFinancialRuntime.java"
    ),
    PurePosixPath(
        "modules/commercial-operations/src/main/java/io/elmos/commercial/"
        "PaymentRefundReconciliationRuntime.java"
    ),
    PurePosixPath(
        "modules/persistence/src/main/resources/db/migration/"
        "V65__pricing_billing_financial_core.sql"
    ),
)
TEST_REQUIRED_ROOTS = (
    PurePosixPath("engines/pricing-billing-engine/tests"),
)
TEST_OPTIONAL_PATHS = (
    PurePosixPath("tests/pricing-billing-skills"),
    PurePosixPath("tests/pricing-billing-gate"),
    PurePosixPath(
        "modules/commercial-operations/src/test/java/io/elmos/commercial/"
        "PricingBillingFinancialRuntimeTest.java"
    ),
    PurePosixPath(
        "modules/commercial-operations/src/test/java/io/elmos/commercial/"
        "PaymentRefundReconciliationRuntimeTest.java"
    ),
    PurePosixPath(
        "modules/persistence/src/test/java/io/elmos/persistence/"
        "PricingBillingFinancialCoreMigrationContractTest.java"
    ),
)

REQUIREMENT_ID_PATTERN = re.compile(
    r"^(?:elmos\.pricing-billing\.v1/)?EB-?(?P<skill>[0-9]{2})-(?P<number>[0-9]{3})$"
)


class BindingError(RuntimeError):
    """A deterministic binding precondition failed."""


@dataclass(frozen=True)
class Blob:
    relative_path: str
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def size(self) -> int:
        return len(self.data)


def _lexical_absolute(raw_path: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(raw_path))))


def resolve_repo_root(raw_path: str | os.PathLike[str]) -> Path:
    """Resolve a repository root while rejecting every lexical symlink component."""
    lexical = _lexical_absolute(raw_path)
    try:
        real = lexical.resolve(strict=True)
    except OSError as exc:
        raise BindingError(f"repository root is unavailable: {lexical}") from exc
    if lexical != real:
        raise BindingError(f"repository root contains a symlink: {lexical}")
    try:
        mode = lexical.stat(follow_symlinks=False).st_mode
    except OSError as exc:
        raise BindingError(f"cannot stat repository root: {lexical}") from exc
    if not stat.S_ISDIR(mode):
        raise BindingError(f"repository root is not a directory: {lexical}")
    return lexical


def _validated_relative(relative: PurePosixPath | str) -> PurePosixPath:
    value = PurePosixPath(relative)
    if value.is_absolute() or not value.parts or any(part in {"", ".", ".."} for part in value.parts):
        raise BindingError(f"unsafe repository-relative path: {value}")
    return value


def _lexical_child(root: Path, relative: PurePosixPath | str) -> Path:
    safe_relative = _validated_relative(relative)
    return root.joinpath(*safe_relative.parts)


def _safe_existing_path(
    root: Path,
    relative: PurePosixPath | str,
    *,
    expected_directory: bool,
) -> Path:
    path = _lexical_child(root, relative)
    try:
        real = path.resolve(strict=True)
    except OSError as exc:
        raise BindingError(f"required path is unavailable: {PurePosixPath(relative)}") from exc
    if real != path:
        raise BindingError(f"controlled path contains a symlink: {PurePosixPath(relative)}")
    try:
        mode = path.stat(follow_symlinks=False).st_mode
    except OSError as exc:
        raise BindingError(f"cannot stat controlled path: {PurePosixPath(relative)}") from exc
    expected = stat.S_ISDIR(mode) if expected_directory else stat.S_ISREG(mode)
    if not expected:
        kind = "directory" if expected_directory else "regular file"
        raise BindingError(f"controlled path is not a {kind}: {PurePosixPath(relative)}")
    try:
        real.relative_to(root)
    except ValueError as exc:
        raise BindingError(f"controlled path escapes repository: {PurePosixPath(relative)}") from exc
    return path


def _optional_kind(root: Path, relative: PurePosixPath) -> str | None:
    """Return file/directory/None; reject a symlink even for an optional path."""
    path = _lexical_child(root, relative)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BindingError(f"cannot stat optional controlled path: {relative}") from exc
    if stat.S_ISLNK(mode):
        raise BindingError(f"optional controlled path is a symlink: {relative}")
    real = path.resolve(strict=True)
    if real != path:
        raise BindingError(f"optional controlled path contains a symlink: {relative}")
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    raise BindingError(f"optional controlled path has unsupported type: {relative}")


def _read_regular_file(root: Path, relative: PurePosixPath | str, maximum_bytes: int) -> Blob:
    safe_relative = _validated_relative(relative)
    path = _safe_existing_path(root, safe_relative, expected_directory=False)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BindingError(f"cannot open controlled file: {safe_relative}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise BindingError(f"controlled input is not regular: {safe_relative}")
        if metadata.st_size > maximum_bytes:
            raise BindingError(
                f"controlled input exceeds {maximum_bytes} bytes: {safe_relative}"
            )
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > maximum_bytes:
            raise BindingError(
                f"controlled input exceeds {maximum_bytes} bytes: {safe_relative}"
            )
        after = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise BindingError(f"controlled input changed while reading: {safe_relative}")
    finally:
        os.close(descriptor)
    return Blob(safe_relative.as_posix(), data)


def _decode_json(blob: Blob) -> Mapping[str, Any]:
    try:
        value = json.loads(blob.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BindingError(f"invalid UTF-8 JSON: {blob.relative_path}") from exc
    if not isinstance(value, dict):
        raise BindingError(f"JSON root must be an object: {blob.relative_path}")
    return value


def _text_list(value: Any, field: str, source: str) -> list[str]:
    if isinstance(value, str):
        items: Iterable[Any] = (value,)
    elif isinstance(value, list):
        items = value
    else:
        raise BindingError(f"{source}: {field} must be a string or non-empty list")
    normalized: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise BindingError(f"{source}: {field} contains a blank/non-string item")
        normalized.append(item.strip())
    if not normalized:
        raise BindingError(f"{source}: {field} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise BindingError(f"{source}: {field} contains duplicates")
    return sorted(normalized)


def _state(value: Any, field: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BindingError(f"{source}: {field} must be a non-blank string")
    return value.strip().upper()


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _canonical_requirement_id(value: Any, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BindingError(f"{source} has a blank/non-string requirement id")
    match = REQUIREMENT_ID_PATTERN.fullmatch(value.strip())
    if match is None:
        raise BindingError(f"{source} has an unknown requirement id: {value!r}")
    canonical = f"EB-{match.group('skill')}-{match.group('number')}"
    if canonical not in EXACT_REQUIREMENTS:
        raise BindingError(f"{source} has an out-of-range requirement id: {value!r}")
    return canonical


def _validate_archive(root: Path) -> Blob:
    archive = _read_regular_file(root, ARCHIVE_RELATIVE, MAX_ARCHIVE_BYTES)
    if archive.sha256 != ARCHIVE_SHA256:
        raise BindingError(
            f"source archive digest mismatch: expected {ARCHIVE_SHA256}, got {archive.sha256}"
        )
    return archive


def _archive_requirements(archive: Blob) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    try:
        with zipfile.ZipFile(io.BytesIO(archive.data)) as package:
            info = package.getinfo(TRACEABILITY_MEMBER)
            if info.is_dir() or info.file_size > MAX_TRACEABILITY_BYTES:
                raise BindingError("archive traceability CSV exceeds its safety limit")
            with package.open(info, "r") as stream:
                raw = stream.read(MAX_TRACEABILITY_BYTES + 1)
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise BindingError("archive traceability CSV is unavailable") from exc
    if len(raw) > MAX_TRACEABILITY_BYTES or len(raw) != info.file_size:
        raise BindingError("archive traceability CSV exceeds its safety limit")
    try:
        rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        requirements: dict[str, dict[str, str]] = {}
        for index, row in enumerate(rows, start=2):
            requirement_id = _canonical_requirement_id(
                row["requirement_id"], f"{TRACEABILITY_MEMBER}:{index}"
            )
            if requirement_id in requirements:
                raise BindingError(
                    f"archive traceability duplicate requirement id: {requirement_id}"
                )
            priority = row["priority"].strip().upper()
            if priority not in {"P0", "P1"}:
                raise BindingError("archive traceability priority drift")
            expected_skill = SKILL_BY_PREFIX[requirement_id[:5]]
            if row["skill"].strip() != expected_skill:
                raise BindingError(
                    f"archive traceability skill drift for {requirement_id}"
                )
            batch = row["batch"].strip()
            statement = row["statement"].strip()
            if re.fullmatch(r"B(?:0[0-9]|[1-4][0-9]|5[0-3])", batch) is None:
                raise BindingError(f"archive traceability batch drift for {requirement_id}")
            if not statement:
                raise BindingError(f"archive traceability statement is blank for {requirement_id}")
            requirements[requirement_id] = {
                "priority": priority,
                "skill": expected_skill,
                "batch": batch,
                "statement": statement,
            }
    except (KeyError, UnicodeDecodeError, csv.Error) as exc:
        raise BindingError("archive traceability CSV is malformed") from exc
    if set(requirements) != set(EXACT_REQUIREMENTS):
        raise BindingError("archive traceability requirement identity drift")
    priority_counts = {
        "P0": sum(value["priority"] == "P0" for value in requirements.values()),
        "P1": sum(value["priority"] == "P1" for value in requirements.values()),
    }
    if priority_counts != {"P0": 108, "P1": 72}:
        raise BindingError(f"archive traceability priority count drift: {priority_counts}")
    return requirements, {
        "member": TRACEABILITY_MEMBER,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "requirementCount": len(requirements),
        "priorityCounts": priority_counts,
    }


def _validate_installed_manifest(root: Path) -> tuple[Blob, Mapping[str, Any]]:
    blob = _read_regular_file(root, INSTALLED_MANIFEST_RELATIVE, MAX_JSON_BYTES)
    document = _decode_json(blob)
    raw_skills = document.get("skills")
    if not isinstance(raw_skills, list):
        raise BindingError("installed manifest skills must be a list")
    names: list[str] = []
    for index, item in enumerate(raw_skills):
        if not isinstance(item, dict):
            raise BindingError(f"installed manifest skill {index} must be an object")
        name = item.get("installed_name", item.get("name"))
        if not isinstance(name, str) or not name.strip():
            raise BindingError(f"installed manifest skill {index} has no exact name")
        names.append(name.strip())
    if len(names) != len(set(names)):
        raise BindingError("installed manifest contains duplicate skill names")
    if set(names) != set(EXACT_SKILLS) or len(names) != len(EXACT_SKILLS):
        raise BindingError("installed manifest does not contain the exact 18 pricing/billing skills")
    return blob, document


def _validate_registry(root: Path) -> Blob:
    blob = _read_regular_file(root, REGISTRY_RELATIVE, MAX_REGISTRY_BYTES)
    try:
        tree = ast.parse(blob.data.decode("utf-8"), filename=blob.relative_path)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise BindingError("runtime registry is not valid UTF-8 Python source") from exc
    registry_names: set[str] = set()

    def add_literals(node: ast.AST) -> None:
        registry_names.update(
            child.value
            for child in ast.walk(node)
            if isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and child.value.startswith("elmos-")
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value.startswith("elmos-")
                ):
                    registry_names.add(key.value)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            target_names = {
                child.id
                for target in targets
                for child in ast.walk(target)
                if isinstance(child, ast.Name)
            }
            if node.value is not None and any(
                marker in name.upper()
                for name in target_names
                for marker in ("SKILL", "HANDLER", "REGISTRY")
            ):
                add_literals(node.value)
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg in {"name", "skill", "skill_name", "handler_name"}:
                    add_literals(keyword.value)

    if not registry_names:
        all_literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        registry_names = set(EXACT_SKILLS).intersection(all_literals)
    if registry_names != set(EXACT_SKILLS):
        missing = sorted(set(EXACT_SKILLS) - registry_names)
        unexpected = sorted(registry_names - set(EXACT_SKILLS))
        raise BindingError(
            f"runtime registry skill drift; missing={missing}, unexpected={unexpected}"
        )
    return blob


def _validate_mapping_namespace(document: Mapping[str, Any], source: str) -> None:
    for key in ("namespace", "package_namespace", "packageNamespace"):
        value = document.get(key)
        if value is not None and value != "elmos.pricing-billing.v1":
            raise BindingError(f"{source}: {key} namespace drift: {value!r}")


def _explicit_texts(
    mapping: Mapping[str, Any],
    keys: Sequence[str],
    field: str,
    source: str,
) -> list[str]:
    values: list[str] = []
    for key in keys:
        if key in mapping:
            values.extend(_text_list(mapping[key], field, f"{source}:{key}"))
    return sorted(set(values))


def _document_artifacts(document: Mapping[str, Any], kind: str, source: str) -> list[str]:
    if kind == "symbols":
        keys = ("implementation_artifacts", "source_path", "source_paths")
    elif kind == "tests":
        keys = ("test_artifacts", "test_path", "test_paths")
    else:  # pragma: no cover - internal programming error
        raise AssertionError(f"unknown artifact kind: {kind}")
    values = _explicit_texts(document, keys, kind, source)
    artifacts = document.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, dict):
            raise BindingError(f"{source}: artifacts must be an object")
        artifact_keys = (
            ("implementation", "runtime", "sources", "symbols")
            if kind == "symbols"
            else ("tests", "test")
        )
        values.extend(_explicit_texts(artifacts, artifact_keys, kind, f"{source}:artifacts"))
    return sorted(set(values))


def _normalize_candidates(
    candidates: Sequence[tuple[str, Any]],
    field: str,
    source: str,
    *,
    aliases: Mapping[str, str] | None = None,
    allowed: frozenset[str] | None = None,
    conservative: bool = False,
) -> str | None:
    normalized: list[str] = []
    for label, raw in candidates:
        value = _state(raw, field, f"{source}:{label}")
        if aliases is not None:
            canonical = aliases.get(value)
            if canonical is None:
                raise BindingError(
                    f"{source}:{label} {field} exceeds the local ceiling or is unknown: {value}"
                )
            value = canonical
        if allowed is not None and value not in allowed:
            raise BindingError(f"{source}:{label} {field} exceeds the allowed ceiling: {value}")
        normalized.append(value)
    if not normalized:
        return None
    if conservative:
        if "NOT_RUN" in normalized:
            return "NOT_RUN"
        if "LOCAL_EXECUTED" in normalized:
            return "LOCAL_EXECUTED"
    unique = set(normalized)
    if len(unique) != 1:
        raise BindingError(f"{source}: conflicting explicit {field} states: {sorted(unique)}")
    return normalized[0]


def _implementation_candidates(mapping: Mapping[str, Any]) -> list[tuple[str, Any]]:
    candidates = [
        (key, mapping[key])
        for key in ("implementationState", "implementation_state")
        if key in mapping
    ]
    raw_implementation = mapping.get("implementation")
    if isinstance(raw_implementation, str):
        state_like = raw_implementation.strip().upper()
        if state_like in IMPLEMENTATION_ALIASES or re.fullmatch(r"[A-Z][A-Z0-9_]*", state_like):
            candidates.append(("implementation", raw_implementation))
    return candidates


def _document_states(document: Mapping[str, Any], source: str) -> dict[str, str | None]:
    evidence = document.get("evidence_state", {})
    if not isinstance(evidence, dict):
        raise BindingError(f"{source}: evidence_state must be an object when present")

    implementation_candidates = _implementation_candidates(document)
    implementation_candidates.extend(_implementation_candidates(evidence))
    test_candidates = [
        (f"document.{key}", document[key])
        for key in ("testExecution", "test_execution")
        if key in document
    ]
    test_candidates.extend(
        (f"evidence_state.{key}", evidence[key])
        for key in ("testExecution", "test_execution", "local_tests")
        if key in evidence
    )
    external_candidates = [
        (f"document.{key}", document[key])
        for key in ("externalEvidence", "external_evidence")
        if key in document
    ]
    external_candidates.extend(
        (f"evidence_state.{key}", evidence[key])
        for key in (
            "externalEvidence",
            "external_evidence",
            "provider_sandbox",
            "bank_or_settlement_file",
            "provider_bank_tax_runtime",
            "postgresql_migration",
            "independent_verification",
        )
        if key in evidence
    )
    certification_candidates = [
        (f"document.{key}", document[key])
        for key in ("certification",)
        if key in document
    ]
    certification_candidates.extend(
        (f"evidence_state.{key}", evidence[key])
        for key in ("certification", "production_certification")
        if key in evidence
    )
    return {
        "implementation": _normalize_candidates(
            implementation_candidates,
            "implementation",
            source,
            aliases=IMPLEMENTATION_ALIASES,
        ),
        "testExecution": _normalize_candidates(
            test_candidates,
            "testExecution",
            source,
            allowed=ALLOWED_TEST_EXECUTION,
        ),
        "externalEvidence": _normalize_candidates(
            external_candidates,
            "externalEvidence",
            source,
            allowed=ALLOWED_EXTERNAL_EVIDENCE,
            conservative=True,
        ),
        "certification": _normalize_candidates(
            certification_candidates,
            "certification",
            source,
            allowed=frozenset({"NOT_CERTIFIED"}),
        ),
    }


def _entry_state(
    raw: Mapping[str, Any],
    document_state: str | None,
    field: str,
    source: str,
) -> str:
    if field == "implementation":
        candidates = _implementation_candidates(raw)
        value = _normalize_candidates(
            candidates,
            field,
            source,
            aliases=IMPLEMENTATION_ALIASES,
        )
    else:
        keys = {
            "testExecution": ("testExecution", "test_execution"),
            "externalEvidence": ("externalEvidence", "external_evidence"),
            "certification": ("certification",),
        }[field]
        candidates = [(key, raw[key]) for key in keys if key in raw]
        allowed = {
            "testExecution": ALLOWED_TEST_EXECUTION,
            "externalEvidence": ALLOWED_EXTERNAL_EVIDENCE,
            "certification": frozenset({"NOT_CERTIFIED"}),
        }[field]
        value = _normalize_candidates(
            candidates,
            field,
            source,
            allowed=allowed,
            conservative=field == "externalEvidence",
        )
    resolved = value if value is not None else document_state
    if resolved is None:
        raise BindingError(f"{source}: no explicit {field} state is bound")
    return resolved


def _load_requirement_bindings(
    root: Path,
    archive_requirements: Mapping[str, Mapping[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    directory = _safe_existing_path(root, REQUIREMENTS_RELATIVE, expected_directory=True)
    entries: dict[str, dict[str, Any]] = {}
    source_files: list[dict[str, Any]] = []
    total_bytes = 0
    try:
        children = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise BindingError("cannot enumerate requirement mappings") from exc
    json_files = [child for child in children if child.name.endswith(".json")]
    if not json_files:
        raise BindingError("no requirement mapping JSON files found")
    for child in children:
        relative = PurePosixPath(child.relative_to(root).as_posix())
        if child.name.startswith("."):
            continue
        if child.suffix != ".json":
            raise BindingError(f"unexpected file in requirement mapping directory: {relative}")
        blob = _read_regular_file(root, relative, MAX_REQUIREMENT_FILE_BYTES)
        total_bytes += blob.size
        if total_bytes > MAX_REQUIREMENT_TOTAL_BYTES:
            raise BindingError("aggregate requirement mapping bytes exceed safety limit")
        document = _decode_json(blob)
        _validate_mapping_namespace(document, relative.as_posix())
        raw_requirements = document.get("requirements")
        if not isinstance(raw_requirements, list) or not raw_requirements:
            raise BindingError(f"{relative}: requirements must be a non-empty list")
        document_states = _document_states(document, relative.as_posix())
        document_symbols = _document_artifacts(
            document, "symbols", relative.as_posix()
        )
        document_tests = _document_artifacts(document, "tests", relative.as_posix())
        for index, raw in enumerate(raw_requirements):
            source = f"{relative}:requirements[{index}]"
            if not isinstance(raw, dict):
                raise BindingError(f"{source} must be an object")
            requirement_id = _canonical_requirement_id(
                _first(raw, "id", "requirement_id", "requirementId"), source
            )
            if requirement_id in entries:
                raise BindingError(f"duplicate requirement id: {requirement_id}")
            expected_canonical = f"elmos.pricing-billing.v1/{requirement_id}"
            declared_canonical = _first(raw, "canonical_id", "canonicalId")
            if declared_canonical is not None:
                canonical_requirement = _canonical_requirement_id(
                    declared_canonical, f"{source}:canonical_id"
                )
                if canonical_requirement != requirement_id:
                    raise BindingError(
                        f"{source} canonical id drift: {declared_canonical!r}"
                    )
            source_requirement = archive_requirements[requirement_id]
            priority = source_requirement["priority"]
            declared_priority = raw.get("priority")
            if declared_priority is not None and (
                _state(declared_priority, "priority", source) != priority
            ):
                raise BindingError(f"{source} priority differs from the pinned archive")
            symbols = _explicit_texts(
                raw,
                (
                    "symbols",
                    "symbol",
                    "source_symbol",
                    "source_symbols",
                    "implementation_symbol",
                    "implementation_symbols",
                ),
                "symbols",
                source,
            )
            if raw.get("implementation") is not None and not _implementation_candidates(raw):
                symbols.extend(
                    _text_list(raw["implementation"], "symbols", f"{source}:implementation")
                )
            tests = _explicit_texts(
                raw,
                (
                    "tests",
                    "test",
                    "test_symbol",
                    "test_symbols",
                    "local_test_node_id",
                    "local_test_node_ids",
                ),
                "tests",
                source,
            )
            symbols = sorted(set(symbols + document_symbols))
            tests = sorted(set(tests + document_tests))
            if not symbols:
                raise BindingError(
                    f"{source}: symbols require an explicit entry value or document artifact"
                )
            if not tests:
                raise BindingError(
                    f"{source}: tests require an explicit entry value or document artifact"
                )

            implementation = _entry_state(
                raw, document_states["implementation"], "implementation", source
            )
            test_execution = _entry_state(
                raw, document_states["testExecution"], "testExecution", source
            )
            external_evidence = _entry_state(
                raw, document_states["externalEvidence"], "externalEvidence", source
            )
            certification = _entry_state(
                raw, document_states["certification"], "certification", source
            )

            prefix = requirement_id[:5]
            skill_name = SKILL_BY_PREFIX[prefix]
            declared_skill = _first(raw, "skill", "owner_skill", "ownerSkill")
            if declared_skill is not None and declared_skill != skill_name:
                raise BindingError(f"{source} skill owner drift: {declared_skill!r}")
            declared_statement = _first(raw, "source_statement", "sourceStatement", "statement")
            if declared_statement is not None and declared_statement != source_requirement["statement"]:
                raise BindingError(f"{source} statement differs from the pinned archive")
            entries[requirement_id] = {
                "id": requirement_id,
                "canonicalId": expected_canonical,
                "skill": skill_name,
                "sourceBatch": source_requirement["batch"],
                "sourceStatement": source_requirement["statement"],
                "priority": priority,
                "symbols": symbols,
                "tests": tests,
                "implementation": implementation,
                "testExecution": test_execution,
                "externalEvidence": external_evidence,
                "certification": certification,
                "mappingSource": relative.as_posix(),
            }
        source_files.append(
            {
                "path": blob.relative_path,
                "size": blob.size,
                "sha256": blob.sha256,
            }
        )

    missing = sorted(set(EXACT_REQUIREMENTS) - set(entries))
    if missing:
        raise BindingError(f"missing exact pricing/billing requirements: {missing}")
    if len(entries) != 180:
        raise BindingError(f"requirement count must be exactly 180, got {len(entries)}")
    priorities = {"P0": 0, "P1": 0}
    for value in entries.values():
        priorities[value["priority"]] += 1
    if priorities != {"P0": 108, "P1": 72}:
        raise BindingError(f"requirement priority drift: {priorities}")
    return [entries[key] for key in EXACT_REQUIREMENTS], source_files


def _skip_tree_name(name: str) -> bool:
    return name in EXCLUDED_DIRECTORY_NAMES or name.endswith(".pyc") or name.endswith(".pyo")


def _collect_directory(root: Path, relative: PurePosixPath) -> list[Blob]:
    directory = _safe_existing_path(root, relative, expected_directory=True)
    blobs: list[Blob] = []

    def visit(current: Path) -> None:
        try:
            entries = sorted(os.scandir(current), key=lambda item: item.name)
        except OSError as exc:
            raise BindingError(f"cannot enumerate task-owned tree: {current.relative_to(root)}") from exc
        for entry in entries:
            if _skip_tree_name(entry.name):
                continue
            entry_relative = PurePosixPath(Path(entry.path).relative_to(root).as_posix())
            if entry.is_symlink():
                raise BindingError(f"task-owned tree contains a symlink: {entry_relative}")
            if entry.is_dir(follow_symlinks=False):
                visit(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                blobs.append(_read_regular_file(root, entry_relative, MAX_TREE_FILE_BYTES))
            else:
                raise BindingError(f"task-owned tree contains a special file: {entry_relative}")

    visit(directory)
    return blobs


def _tree_binding(
    root: Path,
    required_roots: Sequence[PurePosixPath],
    optional_paths: Sequence[PurePosixPath],
) -> dict[str, Any]:
    blobs_by_path: dict[str, Blob] = {}
    roots: list[str] = []
    for relative in required_roots:
        roots.append(relative.as_posix())
        for blob in _collect_directory(root, relative):
            blobs_by_path[blob.relative_path] = blob
    for relative in optional_paths:
        kind = _optional_kind(root, relative)
        if kind is None:
            continue
        roots.append(relative.as_posix())
        if kind == "directory":
            for blob in _collect_directory(root, relative):
                blobs_by_path[blob.relative_path] = blob
        else:
            blob = _read_regular_file(root, relative, MAX_TREE_FILE_BYTES)
            blobs_by_path[blob.relative_path] = blob
    if not blobs_by_path:
        raise BindingError("task-owned tree contains no controlled files")
    if len(blobs_by_path) > MAX_TREE_FILES:
        raise BindingError("task-owned tree contains too many files")
    total_bytes = sum(blob.size for blob in blobs_by_path.values())
    if total_bytes > MAX_TREE_TOTAL_BYTES:
        raise BindingError("task-owned tree exceeds aggregate byte limit")

    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for path in sorted(blobs_by_path):
        blob = blobs_by_path[path]
        encoded_path = path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(blob.size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(blob.sha256))
        files.append({"path": path, "size": blob.size, "sha256": blob.sha256})
    return {
        "algorithm": "sha256-path-size-content-v1",
        "roots": sorted(set(roots)),
        "fileCount": len(files),
        "byteCount": total_bytes,
        "sha256": digest.hexdigest(),
        "files": files,
        "exclusions": sorted(EXCLUDED_DIRECTORY_NAMES | {"*.pyc", "*.pyo"}),
    }


def build_document(repo_root: Path) -> dict[str, Any]:
    archive = _validate_archive(repo_root)
    archive_requirements, traceability_catalog = _archive_requirements(archive)
    installed_manifest, _ = _validate_installed_manifest(repo_root)
    registry = _validate_registry(repo_root)
    requirements, requirement_sources = _load_requirement_bindings(
        repo_root,
        archive_requirements,
    )
    runtime_tree = _tree_binding(repo_root, RUNTIME_REQUIRED_ROOTS, RUNTIME_OPTIONAL_PATHS)
    test_tree = _tree_binding(repo_root, TEST_REQUIRED_ROOTS, TEST_OPTIONAL_PATHS)

    implementation_counts: dict[str, int] = {}
    test_counts: dict[str, int] = {}
    external_counts: dict[str, int] = {}
    for requirement in requirements:
        implementation_counts[requirement["implementation"]] = (
            implementation_counts.get(requirement["implementation"], 0) + 1
        )
        test_counts[requirement["testExecution"]] = test_counts.get(
            requirement["testExecution"], 0
        ) + 1
        external_counts[requirement["externalEvidence"]] = external_counts.get(
            requirement["externalEvidence"], 0
        ) + 1

    return {
        "schemaVersion": 1,
        "packageNamespace": "elmos.pricing-billing.v1",
        "sourceArchive": {
            "path": archive.relative_path,
            "size": archive.size,
            "sha256": archive.sha256,
            "identityClaimOnly": True,
            "traceabilityCatalog": traceability_catalog,
        },
        "installedManifest": {
            "path": installed_manifest.relative_path,
            "size": installed_manifest.size,
            "sha256": installed_manifest.sha256,
        },
        "runtimeRegistry": {
            "path": registry.relative_path,
            "size": registry.size,
            "sha256": registry.sha256,
            "skillCount": len(EXACT_SKILLS),
            "skills": list(EXACT_SKILLS),
            "inspection": "AST_LITERAL_SCAN_ONLY_NO_IMPORT_OR_EXECUTION",
        },
        "requirementTraceability": {
            "requirementCount": 180,
            "priorityCounts": {"P0": 108, "P1": 72},
            "sourceFiles": requirement_sources,
            "implementationCounts": dict(sorted(implementation_counts.items())),
            "testExecutionCounts": dict(sorted(test_counts.items())),
            "externalEvidenceCounts": dict(sorted(external_counts.items())),
            "bindings": requirements,
        },
        "taskOwnedTrees": {
            "runtime": runtime_tree,
            "tests": test_tree,
        },
        "claimCeiling": {
            "maximumLocalState": "LOCAL_EXECUTED",
            "externalProviderBankTaxAccountingEvidence": "NOT_RUN_UNLESS_EXPLICITLY_BOUND_PER_REQUIREMENT",
            "certification": "NOT_CERTIFIED",
        },
        "nonClaims": [
            "The builder did not import or execute a runtime handler.",
            "The builder did not execute any source-archive helper, installer, validator, or workflow.",
            "Byte identity and local code/test bindings do not prove provider, bank, tax, accounting, production, or independent evidence.",
            "No requirement in this document is certified.",
        ],
    }


def render_binding(repo_root: Path) -> bytes:
    document = build_document(repo_root)
    return (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _validate_output_parent(root: Path) -> Path:
    return _safe_existing_path(root, OUTPUT_RELATIVE.parent, expected_directory=True)


def _atomic_write(root: Path, data: bytes) -> None:
    if len(data) > MAX_OUTPUT_BYTES:
        raise BindingError("rendered runtime binding exceeds output safety limit")
    parent = _validate_output_parent(root)
    target = _lexical_child(root, OUTPUT_RELATIVE)
    kind = _optional_kind(root, OUTPUT_RELATIVE)
    if kind is not None and kind != "file":
        raise BindingError("runtime binding output exists but is not a regular file")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".runtime-binding.", suffix=".tmp", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target)
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_binding(repo_root: Path) -> bytes:
    rendered = render_binding(repo_root)
    _atomic_write(repo_root, rendered)
    return rendered


def check_binding(repo_root: Path) -> bool:
    expected = render_binding(repo_root)
    try:
        actual = _read_regular_file(repo_root, OUTPUT_RELATIVE, MAX_OUTPUT_BYTES).data
    except BindingError as exc:
        if "unavailable" in str(exc):
            return False
        raise
    return actual == expected


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, help="lexical, non-symlink repository root")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="atomically write the canonical binding")
    action.add_argument("--check", action="store_true", help="require byte-exact canonical binding")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        root = resolve_repo_root(arguments.repo_root)
        if arguments.write:
            rendered = write_binding(root)
            print(f"wrote {OUTPUT_RELATIVE} ({len(rendered)} bytes)")
            return 0
        if check_binding(root):
            print(f"runtime binding is current: {OUTPUT_RELATIVE}")
            return 0
        print(f"runtime binding is stale or missing: {OUTPUT_RELATIVE}", file=sys.stderr)
        return 1
    except (BindingError, OSError, ValueError) as exc:
        print(f"pricing/billing runtime binding error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
