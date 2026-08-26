#!/usr/bin/env python3
"""Fail-closed repository readiness gate for the ELMOS pricing/billing pack.

The gate trusts neither request metadata nor self-declared evidence. It binds the
request to the pinned source ZIP, derives the exact requirement catalog from the
ZIP's traceability CSV, verifies the independently installed manifest, and
checks every PASS record against real repository-confined evidence bytes.

This is a preparation gate only. Its maximum decision is
READY_FOR_EXTERNAL_GATE; it cannot certify, approve production, or manufacture
customer, accounting, tax, payment, bank, or disaster-recovery evidence.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import csv
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import zipfile
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "elmos.pricing-billing.repository-gate.v1"
REQUEST_SCHEMA_VERSION = "1.0"
MAXIMUM_DECISION = "READY_FOR_EXTERNAL_GATE"
BLOCKED_DECISION = "BLOCKED"

ARCHIVE_RELATIVE = Path("skills/subskills/elmos-pricing-billing-skills-v1.0.0.zip")
INSTALLED_MANIFEST_RELATIVE = Path(
    "docs/pricing-billing-skills/installed-manifest.json"
)
RUNTIME_BINDING_RELATIVE = Path(
    "verification-packs/pricing-billing-local-v1/runtime-binding.json"
)
ARCHIVE_SHA256 = "9f7440b69a82a52172a1f62da915d96cfa4e0326dc04a305603c76001c8e88bc"
ARCHIVE_BYTES = 246_184
INSTALLED_MANIFEST_SHA256 = (
    "d245daf9580e1268a7d46b15398fc9770b4af85c4b21497d9d018321fb09e009"
)
INSTALLED_MANIFEST_BYTES = 60_745
TRACEABILITY_MEMBER = (
    "elmos-pricing-billing-skills-v1.0.0/manifests/requirements.traceability.csv"
)
TRACEABILITY_SHA256 = "906ea58cc9829c6f9e88aea8190127963185296aa82f93fbbd8941af96ab8bdc"
TRACEABILITY_BYTES = 23_018
EXPECTED_REQUIREMENT_IDS = tuple(
    f"EB-{group:02d}-{number:03d}" for group in range(1, 19) for number in range(1, 11)
)
EXPECTED_SKILL_COUNT = 18
EXPECTED_REQUIREMENT_COUNT = 180
EXPECTED_SKILLS = (
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
EXPECTED_SKILL_BY_PREFIX = {
    f"EB-{index:02d}": skill for index, skill in enumerate(EXPECTED_SKILLS, start=1)
}
GATE_RELATIVE = Path("scripts/pricing-billing/run_pricing_billing_gate.py")
ENGINE_RELATIVE = Path("engines/pricing-billing-engine")
BASELINE_RELATIVES = (
    ARCHIVE_RELATIVE,
    INSTALLED_MANIFEST_RELATIVE,
    RUNTIME_BINDING_RELATIVE,
    GATE_RELATIVE,
    ENGINE_RELATIVE,
)

EVIDENCE_SCHEMA_VERSION = "elmos.pricing-billing.evidence.v1"
TRUST_STORE_SCHEMA_VERSION = "elmos.pricing-billing.trust-store.v1"
REPOSITORY_STATE_SCHEMA_VERSION = "elmos.pricing-billing.repository-state.v1"
MAX_PINNED_FILE_BYTES = 2 * 1024 * 1024
MAX_RUNTIME_BINDING_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_REQUEST_DEPTH = 64
MAX_JSON_NESTING_DEPTH = 512
MAX_REQUEST_NODES = 20_000
MAX_REQUEST_CONTAINER_ITEMS = 4_096
MAX_EVIDENCE_FILE_BYTES = 256 * 1024
MAX_TOTAL_EVIDENCE_BYTES = 4 * 1024 * 1024
MAX_TRUST_STORE_BYTES = 1024 * 1024
MAX_BASELINE_FILE_BYTES = 32 * 1024 * 1024
MAX_BASELINE_TOTAL_BYTES = 256 * 1024 * 1024
MAX_BASELINE_FILES = 10_000
MAX_RUNTIME_BINDING_FILES = 20_000
RSA_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")

RUNTIME_BINDING_IMPLEMENTATION_STATES = frozenset(
    {"DECLARED", "PARTIAL", "LOCAL_IMPLEMENTED", "LOCAL_EXECUTED"}
)
RUNTIME_BINDING_TEST_STATES = frozenset({"NOT_RUN", "LOCAL_EXECUTED"})
RUNTIME_BINDING_RUNTIME_ROOTS = frozenset(
    {
        "engines/pricing-billing-engine/src",
        "engines/pricing-billing-engine/pyproject.toml",
        "engines/pricing-billing-engine/uv.lock",
        "modules/commercial-operations/src/main/java/io/elmos/commercial/"
        "PaymentRefundReconciliationRuntime.java",
        "modules/commercial-operations/src/main/java/io/elmos/commercial/"
        "PricingBillingFinancialRuntime.java",
        "modules/persistence/src/main/resources/db/migration/"
        "V65__pricing_billing_financial_core.sql",
    }
)
RUNTIME_BINDING_TEST_ROOTS = frozenset(
    {
        "engines/pricing-billing-engine/tests",
        "tests/pricing-billing-skills",
        "tests/pricing-billing-gate",
        "modules/commercial-operations/src/test/java/io/elmos/commercial/"
        "PaymentRefundReconciliationRuntimeTest.java",
        "modules/commercial-operations/src/test/java/io/elmos/commercial/"
        "PricingBillingFinancialRuntimeTest.java",
        "modules/persistence/src/test/java/io/elmos/persistence/"
        "PricingBillingFinancialCoreMigrationContractTest.java",
    }
)
RUNTIME_BINDING_NON_CLAIMS = (
    "The builder did not import or execute a runtime handler.",
    "The builder did not execute any source-archive helper, installer, validator, or workflow.",
    "Byte identity and local code/test bindings do not prove provider, bank, tax, "
    "accounting, production, or independent evidence.",
    "No requirement in this document is certified.",
)

VALID_STATUSES = frozenset({"PASS", "FAILED", "BLOCKED", "NOT_RUN", "INCONCLUSIVE"})
KNOWN_FAILURE_STATUSES = frozenset({"FAILED", "BLOCKED", "INCONCLUSIVE"})
APPROVED_EVIDENCE_ROOTS = frozenset(
    {"evidence/pricing-billing", "artifacts/pricing-billing"}
)
RECONCILIATION_DOMAINS = ("provider", "bank", "finance")
EXTERNAL_EVIDENCE_DOMAINS = (
    "customer",
    "accounting",
    "tax",
    "payment",
    "bank",
    "disasterRecovery",
)
SHA256_PATTERN = re.compile(r"(?:sha256:)?([0-9a-f]{64})")
IDENTITY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{1,255}")
GIT_OBJECT_PATTERN = re.compile(r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})")
PROHIBITED_DECISIONS = frozenset(
    {"CERTIFIED", "PRODUCTION_APPROVED", "GA_APPROVED", "APPROVED_FOR_PRODUCTION"}
)
PROHIBITED_TRUE_KEYS = frozenset(
    {
        "certified",
        "productionapproved",
        "productioncertified",
        "gaapproved",
        "certificationapproved",
    }
)


class GateRequestError(ValueError):
    """Raised only for an ambiguous, structurally malformed, or forbidden request."""


class DuplicateJsonKeyError(GateRequestError):
    """Raised when JSON contains a duplicate object key."""


@dataclass(frozen=True)
class VerifiedFile:
    """One regular file read and digest-checked as a single immutable snapshot."""

    path: Path
    content: bytes | None
    sha256: str
    size: int
    device: int
    inode: int


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    principal: str
    roles: frozenset[str]
    modulus: int
    exponent: int


@dataclass
class ByteBudget:
    limit: int
    consumed: int = 0

    def reserve(self, size: int, label: str) -> str | None:
        if size < 0 or self.consumed + size > self.limit:
            return f"{label} exceeds the aggregate evidence byte limit"
        self.consumed += size
        return None


@dataclass
class EvidenceContext:
    trust_keys: dict[str, TrustedKey]
    run_id: str | None
    authorization_id: str | None
    authorization_scope: str | None
    environment_id: str | None
    environment_profile: str | None
    repository_binding: dict[str, str] | None
    budget: ByteBudget
    descriptor_cache: dict[tuple[str, int, str], VerifiedFile]
    path_owners: dict[str, str]
    inode_owners: dict[tuple[int, int], str]
    evidence_id_owners: dict[str, str]


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_excessive_json_nesting(text: str, label: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_NESTING_DEPTH:
                raise GateRequestError(f"{label} exceeds the JSON nesting limit")
        elif character in "]}":
            depth -= 1


def _decode_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise GateRequestError(f"{label} is invalid JSON: {exc}") from exc
    _reject_excessive_json_nesting(text, label)
    try:
        value = json.loads(text, object_pairs_hook=_object_without_duplicates)
    except RecursionError as exc:
        raise GateRequestError(f"{label} exceeds the JSON nesting limit") from exc
    except (json.JSONDecodeError, GateRequestError) as exc:
        raise GateRequestError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise GateRequestError(f"{label} must be a JSON object")
    return value


def load_json_request(path: Path) -> dict[str, Any]:
    return _load_bounded_json_object(
        path,
        "request",
        max_bytes=MAX_REQUEST_BYTES,
    )


def _normalize_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GateRequestError(f"{label}.sha256 must be a lowercase SHA-256 string")
    match = SHA256_PATTERN.fullmatch(value)
    if match is None:
        raise GateRequestError(
            f"{label}.sha256 must be 64 lowercase hex characters, optionally prefixed by sha256:"
        )
    return match.group(1)


def _normalized_relative(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise GateRequestError(f"{label} must be a normalized repository-relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise GateRequestError(f"{label} must be a normalized repository-relative path")
    return path


def _inside_relative(path: PurePosixPath, roots: list[PurePosixPath]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _runtime_file_descriptor(
    raw: Any,
    label: str,
    *,
    allow_extra: bool = False,
) -> tuple[PurePosixPath, int, str]:
    required = {"path", "size", "sha256"}
    if not isinstance(raw, dict) or (
        not required.issubset(raw) if allow_extra else set(raw) != required
    ):
        raise GateRequestError(
            f"{label} must contain only path, size, and sha256"
        )
    relative = _normalized_relative(raw.get("path"), f"{label}.path")
    size = raw.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise GateRequestError(f"{label}.size must be a non-negative integer")
    digest = _normalize_sha256(raw.get("sha256"), label)
    return relative, size, digest


def _runtime_binding_paths(document: dict[str, Any]) -> tuple[PurePosixPath, ...]:
    paths: set[PurePosixPath] = {
        PurePosixPath(RUNTIME_BINDING_RELATIVE.as_posix())
    }
    for key in ("sourceArchive", "installedManifest", "runtimeRegistry"):
        relative, _size, _digest = _runtime_file_descriptor(
            document.get(key), f"runtimeBinding.{key}", allow_extra=True
        )
        paths.add(relative)
    traceability = document.get("requirementTraceability")
    if not isinstance(traceability, dict):
        raise GateRequestError(
            "runtimeBinding.requirementTraceability must be an object"
        )
    sources = traceability.get("sourceFiles")
    if not isinstance(sources, list):
        raise GateRequestError(
            "runtimeBinding requirement sourceFiles must be a list"
        )
    for index, raw in enumerate(sources):
        relative, _size, _digest = _runtime_file_descriptor(
            raw, f"runtimeBinding.requirementTraceability.sourceFiles[{index}]"
        )
        paths.add(relative)
    trees = document.get("taskOwnedTrees")
    if not isinstance(trees, dict):
        raise GateRequestError("runtimeBinding.taskOwnedTrees must be an object")
    for tree_name in ("runtime", "tests"):
        tree = trees.get(tree_name)
        if not isinstance(tree, dict):
            raise GateRequestError(
                f"runtimeBinding.taskOwnedTrees.{tree_name} must be an object"
            )
        files = tree.get("files")
        if not isinstance(files, list):
            raise GateRequestError(
                f"runtimeBinding.taskOwnedTrees.{tree_name}.files must be a list"
            )
        if len(files) > MAX_RUNTIME_BINDING_FILES:
            raise GateRequestError(
                f"runtimeBinding.taskOwnedTrees.{tree_name} has too many files"
            )
        for index, raw in enumerate(files):
            relative, _size, _digest = _runtime_file_descriptor(
                raw,
                f"runtimeBinding.taskOwnedTrees.{tree_name}.files[{index}]",
            )
            paths.add(relative)
    if len(paths) > MAX_RUNTIME_BINDING_FILES:
        raise GateRequestError("runtimeBinding controls too many repository files")
    return tuple(sorted(paths, key=lambda item: item.as_posix()))


def _load_runtime_binding_for_baseline(repository_root: Path) -> dict[str, Any]:
    verified, reasons = _read_stable_regular_file(
        repository_root,
        PurePosixPath(RUNTIME_BINDING_RELATIVE.as_posix()),
        "runtimeBinding baseline",
        max_bytes=MAX_PINNED_FILE_BYTES,
        retain_content=True,
    )
    if verified is None or verified.content is None:
        raise GateRequestError("; ".join(reasons))
    return _decode_json_object(verified.content, "runtimeBinding baseline")


def _requested_evidence_roots(request: dict[str, Any]) -> list[PurePosixPath]:
    values = request.get("approvedEvidenceRoots")
    if not isinstance(values, list) or not values:
        raise GateRequestError("approvedEvidenceRoots must be a non-empty list")
    roots: list[PurePosixPath] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        relative = _normalized_relative(value, f"approvedEvidenceRoots[{index}]")
        rendered = relative.as_posix()
        if rendered in seen:
            raise GateRequestError("approvedEvidenceRoots contains duplicates")
        seen.add(rendered)
        if rendered not in APPROVED_EVIDENCE_ROOTS:
            raise GateRequestError(
                f"approvedEvidenceRoots[{index}] is not repository-approved: {rendered}"
            )
        roots.append(relative)
    return roots


def _open_relative_no_symlinks(repository_root: Path, relative: PurePosixPath) -> int:
    """Open *relative* beneath the repository without following any symlink.

    Every path component is opened relative to an already-open directory file
    descriptor. This removes the lstat/resolve/open race that would otherwise
    allow an evidence path to be replaced after validation but before reading.
    """

    if not relative.parts:
        raise OSError("relative file path is empty")
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW")
    if not all(hasattr(os, name) for name in required_flags):
        raise OSError("platform lacks required no-symlink open support")
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | close_on_exec
    file_flags = (
        os.O_RDONLY | os.O_NOFOLLOW | close_on_exec | getattr(os, "O_NONBLOCK", 0)
    )
    directory_fd = os.open(repository_root, directory_flags)
    try:
        for part in relative.parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return os.open(relative.parts[-1], file_flags, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def _stat_identity(value: os.stat_result) -> tuple[int, ...]:
    """Return mutation-sensitive identity fields, excluding read-updated atime."""

    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_stable_regular_file(
    repository_root: Path,
    relative: PurePosixPath,
    label: str,
    *,
    max_bytes: int,
    retain_content: bool,
    budget: ByteBudget | None = None,
) -> tuple[VerifiedFile | None, list[str]]:
    """Hash one bounded regular file from a stable no-symlink descriptor."""

    try:
        descriptor = _open_relative_no_symlinks(repository_root, relative)
    except OSError as exc:
        return None, [
            f"{label} cannot be opened without symbolic links: "
            f"{relative.as_posix()}: {exc}"
        ]
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None, [f"{label} must be a regular file"]
        if before.st_size > max_bytes:
            return None, [
                f"{label} exceeds the per-file byte limit: "
                f"actual={before.st_size} limit={max_bytes}"
            ]
        if budget is not None:
            budget_reason = budget.reserve(before.st_size, label)
            if budget_reason is not None:
                return None, [budget_reason]
        chunks: list[bytes] | None = [] if retain_content else None
        digest = hashlib.sha256()
        actual_bytes = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            actual_bytes += len(block)
            if actual_bytes > max_bytes:
                return None, [f"{label} grew beyond the per-file byte limit while read"]
            digest.update(block)
            if chunks is not None:
                chunks.append(block)
        after = os.fstat(descriptor)
    except OSError as exc:
        return None, [f"{label} cannot be read from a stable file descriptor: {exc}"]
    finally:
        os.close(descriptor)

    if _stat_identity(before) != _stat_identity(after):
        return None, [f"{label} changed while it was being verified"]
    if actual_bytes != after.st_size:
        return None, [f"{label} byte count changed while it was being verified"]

    # Re-open through the repository root after reading. A rename or component
    # replacement cannot silently bind the verified bytes to a different path.
    try:
        current_descriptor = _open_relative_no_symlinks(repository_root, relative)
    except OSError as exc:
        return None, [
            f"{label} path changed while it was being verified: "
            f"{relative.as_posix()}: {exc}"
        ]
    try:
        current = os.fstat(current_descriptor)
    except OSError as exc:
        return None, [f"{label} path cannot be re-inspected: {exc}"]
    finally:
        os.close(current_descriptor)
    if not stat.S_ISREG(current.st_mode) or _stat_identity(after) != _stat_identity(
        current
    ):
        return None, [f"{label} path changed while it was being verified"]

    return (
        VerifiedFile(
            path=repository_root / Path(*relative.parts),
            content=b"".join(chunks) if chunks is not None else None,
            sha256=digest.hexdigest(),
            size=actual_bytes,
            device=after.st_dev,
            inode=after.st_ino,
        ),
        [],
    )


def _load_bounded_json_object(
    path: Path,
    label: str,
    *,
    max_bytes: int,
) -> dict[str, Any]:
    """Read one external JSON object as a bounded, stable regular-file snapshot."""

    try:
        canonical = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise GateRequestError(f"{label} is unavailable: {exc}") from exc
    anchor = Path(canonical.anchor)
    relative_parts = canonical.relative_to(anchor).parts
    if not relative_parts:
        raise GateRequestError(f"{label} path must name a regular file")
    relative = PurePosixPath(*relative_parts)
    verified, reasons = _read_stable_regular_file(
        anchor,
        relative,
        label,
        max_bytes=max_bytes,
        retain_content=True,
    )
    if verified is None or verified.content is None:
        raise GateRequestError("; ".join(reasons))
    return _decode_json_object(verified.content, label)


def _verify_descriptor(
    descriptor: Any,
    repository_root: Path,
    approved_roots: list[PurePosixPath] | None,
    label: str,
    *,
    exact_path: Path | None = None,
    exact_sha256: str | None = None,
    required_role: str | None = None,
    max_bytes: int = MAX_PINNED_FILE_BYTES,
    retain_content: bool = True,
    budget: ByteBudget | None = None,
    cache: dict[tuple[str, int, str], VerifiedFile] | None = None,
) -> tuple[VerifiedFile | None, list[str]]:
    reasons: list[str] = []
    if not isinstance(descriptor, dict):
        return None, [f"{label} descriptor is required"]
    relative = _normalized_relative(descriptor.get("path"), f"{label}.path")
    declared_sha256 = _normalize_sha256(descriptor.get("sha256"), label)
    declared_bytes = descriptor.get("bytes")
    if (
        not isinstance(declared_bytes, int)
        or isinstance(declared_bytes, bool)
        or declared_bytes < 0
    ):
        reasons.append(f"{label}.bytes must be a non-negative integer")
    cache_key: tuple[str, int, str] | None = None
    if isinstance(declared_bytes, int) and not isinstance(declared_bytes, bool):
        cache_key = (relative.as_posix(), declared_bytes, declared_sha256)
    if required_role is not None and descriptor.get("role") != required_role:
        reasons.append(f"{label}.role must be {required_role}")
    if exact_path is not None and relative.as_posix() != exact_path.as_posix():
        reasons.append(f"{label}.path must be {exact_path.as_posix()}")
    if exact_sha256 is not None and declared_sha256 != exact_sha256:
        reasons.append(f"{label}.sha256 does not bind the pinned source identity")

    if approved_roots is not None and not _inside_relative(relative, approved_roots):
        reasons.append(f"{label} escapes approved repository evidence roots")
        return None, reasons
    if (
        not reasons
        and cache is not None
        and cache_key is not None
        and cache_key in cache
    ):
        return cache[cache_key], []
    verified, snapshot_reasons = _read_stable_regular_file(
        repository_root,
        relative,
        label,
        max_bytes=max_bytes,
        retain_content=retain_content,
        budget=budget,
    )
    reasons.extend(snapshot_reasons)
    if verified is None:
        return None, reasons
    actual_bytes = verified.size
    if isinstance(declared_bytes, int) and not isinstance(declared_bytes, bool):
        if actual_bytes != declared_bytes:
            reasons.append(
                f"{label} byte count mismatch: declared={declared_bytes} actual={actual_bytes}"
            )
    actual_sha256 = verified.sha256
    if actual_sha256 != declared_sha256:
        reasons.append(f"{label} SHA-256 mismatch")
    if not reasons and cache is not None and cache_key is not None:
        cache[cache_key] = VerifiedFile(
            path=verified.path,
            content=None,
            sha256=verified.sha256,
            size=verified.size,
            device=verified.device,
            inode=verified.inode,
        )
    return (
        verified if not reasons else None,
        reasons,
    )


def _load_requirement_catalog_records_bytes(
    raw_archive: bytes,
) -> dict[str, dict[str, str]]:
    try:
        with zipfile.ZipFile(BytesIO(raw_archive)) as handle:
            names = [info.filename for info in handle.infolist()]
            if names.count(TRACEABILITY_MEMBER) != 1:
                raise GateRequestError(
                    "pinned archive must contain exactly one requirements traceability CSV"
                )
            raw = handle.read(TRACEABILITY_MEMBER)
    except GateRequestError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, KeyError) as exc:
        raise GateRequestError(
            f"cannot read pinned requirements traceability CSV: {exc}"
        ) from exc
    try:
        rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    except (UnicodeError, csv.Error) as exc:
        raise GateRequestError(
            f"requirements traceability CSV is invalid: {exc}"
        ) from exc
    identifiers = [row.get("requirement_id") for row in rows]
    if tuple(identifiers) != EXPECTED_REQUIREMENT_IDS:
        raise GateRequestError(
            "pinned requirement catalog is not the exact ordered EB-01-001 through EB-18-010 inventory"
        )
    catalog: dict[str, dict[str, str]] = {}
    for row in rows:
        identifier = row["requirement_id"]
        priority = row.get("priority")
        if priority not in {"P0", "P1"}:
            raise GateRequestError(
                f"invalid pinned priority for {identifier}: {priority}"
            )
        skill = row.get("skill")
        expected_skill = EXPECTED_SKILL_BY_PREFIX[identifier[:5]]
        if skill != expected_skill:
            raise GateRequestError(
                f"invalid pinned Skill owner for {identifier}: {skill}"
            )
        batch = row.get("batch")
        if not isinstance(batch, str) or not batch.strip():
            raise GateRequestError(f"missing pinned source Batch for {identifier}")
        statement = row.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            raise GateRequestError(f"missing pinned source statement for {identifier}")
        catalog[identifier] = {
            "priority": priority,
            "skill": skill,
            "batch": batch,
            "statement": statement,
        }
    if len(catalog) != EXPECTED_REQUIREMENT_COUNT:
        raise GateRequestError(
            "pinned requirement catalog must contain exactly 180 unique IDs"
        )
    return catalog


def _load_requirement_catalog_bytes(raw_archive: bytes) -> dict[str, str]:
    return {
        identifier: record["priority"]
        for identifier, record in _load_requirement_catalog_records_bytes(
            raw_archive
        ).items()
    }


def load_requirement_catalog(archive: Path) -> dict[str, str]:
    """Public test/tooling helper that validates the pinned archive and returns priorities."""

    try:
        content = archive.read_bytes()
    except OSError as exc:
        raise GateRequestError(f"source archive cannot be read: {exc}") from exc
    if hashlib.sha256(content).hexdigest() != ARCHIVE_SHA256:
        raise GateRequestError(
            "source archive SHA-256 does not match the pinned package"
        )
    return _load_requirement_catalog_bytes(content)


def _walk_forbidden_claims(value: Any, path: str = "request") -> None:
    stack: list[tuple[Any, str, int]] = [(value, path, 0)]
    visited = 0
    while stack:
        current, current_path, depth = stack.pop()
        visited += 1
        if visited > MAX_REQUEST_NODES:
            raise GateRequestError(
                f"request exceeds the structural node limit of {MAX_REQUEST_NODES}"
            )
        if depth > MAX_REQUEST_DEPTH:
            raise GateRequestError(
                f"request exceeds the structural depth limit of {MAX_REQUEST_DEPTH}"
            )
        if isinstance(current, dict):
            if len(current) > MAX_REQUEST_CONTAINER_ITEMS:
                raise GateRequestError(
                    "request object exceeds the per-container item limit of "
                    f"{MAX_REQUEST_CONTAINER_ITEMS}"
                )
            for key, child in current.items():
                if not isinstance(key, str):
                    raise GateRequestError(
                        f"{current_path} contains a non-string object key"
                    )
                normalized_key = re.sub(r"[^a-z]", "", key.lower())
                if normalized_key in PROHIBITED_TRUE_KEYS and not (
                    child is False or child is None or child == ""
                ):
                    raise GateRequestError(
                        f"{current_path}.{key} may not request certification "
                        "or production approval"
                    )
                stack.append((child, f"{current_path}.{key}", depth + 1))
        elif isinstance(current, list):
            if len(current) > MAX_REQUEST_CONTAINER_ITEMS:
                raise GateRequestError(
                    "request array exceeds the per-container item limit of "
                    f"{MAX_REQUEST_CONTAINER_ITEMS}"
                )
            for index, child in enumerate(current):
                stack.append((child, f"{current_path}[{index}]", depth + 1))
        elif isinstance(current, str) and current.upper() in PROHIBITED_DECISIONS:
            raise GateRequestError(f"{current_path} may not request {current}")


def _status_record(raw: Any, label: str) -> tuple[str, dict[str, Any]]:
    if isinstance(raw, str):
        status = raw
        record: dict[str, Any] = {"status": raw}
    elif isinstance(raw, dict):
        status = raw.get("status")
        record = raw
    else:
        raise GateRequestError(f"{label} must be a status string or object")
    if not isinstance(status, str) or status not in VALID_STATUSES:
        raise GateRequestError(
            f"{label}.status must be one of {sorted(VALID_STATUSES)}"
        )
    return status, record


def _valid_identity(value: Any) -> bool:
    return isinstance(value, str) and IDENTITY_PATTERN.fullmatch(value) is not None


def _git(repository_root: Path, *arguments: str) -> bytes:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    command = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        *arguments,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=repository_root,
            env=environment,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GateRequestError(f"cannot inspect repository baseline: {exc}") from exc
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise GateRequestError(
            f"repository baseline command failed ({result.returncode}): {message}"
        )
    return result.stdout


def _git_object(value: bytes, label: str) -> str:
    rendered = value.decode("ascii", errors="strict").strip()
    if re.fullmatch(r"[0-9a-f]{40}", rendered):
        return "sha1:" + rendered
    if re.fullmatch(r"[0-9a-f]{64}", rendered):
        return "sha256:" + rendered
    raise GateRequestError(f"{label} is not a supported Git object identity")


def inspect_repository_baseline(repository_root: Path) -> dict[str, str]:
    """Derive a clean, immutable pricing/billing repository baseline."""

    repository_root = repository_root.resolve(strict=True)
    runtime_binding = _load_runtime_binding_for_baseline(repository_root)
    controlled_paths = _runtime_binding_paths(runtime_binding)
    pathspecs = sorted(
        {
            *(path.as_posix() for path in BASELINE_RELATIVES),
            *(path.as_posix() for path in controlled_paths),
        }
    )
    dirty = _git(
        repository_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--",
        *pathspecs,
    )
    if dirty:
        raise GateRequestError(
            "pricing/billing source, manifest, runtime binding, gate, or controlled baseline is not clean"
        )
    tracked = _git(
        repository_root,
        "ls-files",
        "-z",
        "--stage",
        "--",
        *pathspecs,
    )
    entries: list[tuple[str, str]] = []
    for raw_entry in tracked.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            mode, _object_id, stage = metadata.decode("ascii").split()
            relative = raw_path.decode("utf-8")
        except (UnicodeError, ValueError) as exc:
            raise GateRequestError("Git returned an invalid baseline entry") from exc
        if stage != "0" or mode not in {"100644", "100755"}:
            raise GateRequestError(
                f"baseline path must be a stage-0 regular file: {relative}"
            )
        entries.append((relative, mode))
    if len(entries) > MAX_BASELINE_FILES:
        raise GateRequestError("pricing/billing baseline exceeds the file-count limit")
    required_files = {
        ARCHIVE_RELATIVE.as_posix(),
        INSTALLED_MANIFEST_RELATIVE.as_posix(),
        RUNTIME_BINDING_RELATIVE.as_posix(),
        GATE_RELATIVE.as_posix(),
    }
    actual_paths = {path for path, _mode in entries}
    if not required_files.issubset(actual_paths):
        raise GateRequestError(
            "pricing/billing baseline is missing a pinned tracked file"
        )
    engine_prefix = ENGINE_RELATIVE.as_posix() + "/"
    if not any(path.startswith(engine_prefix) for path in actual_paths):
        raise GateRequestError("pricing/billing engine baseline has no tracked files")

    total_budget = ByteBudget(MAX_BASELINE_TOTAL_BYTES)
    scoped_digest = hashlib.sha256(b"elmos.pricing-billing.scoped-worktree.v1\0")
    engine_digest = hashlib.sha256(b"elmos.pricing-billing.engine-tree.v1\0")
    gate_digest: str | None = None
    runtime_binding_digest: str | None = None
    for rendered, mode in sorted(entries):
        relative = _normalized_relative(rendered, "tracked baseline path")
        verified, reasons = _read_stable_regular_file(
            repository_root,
            relative,
            f"baseline.{rendered}",
            max_bytes=MAX_BASELINE_FILE_BYTES,
            retain_content=False,
            budget=total_budget,
        )
        if verified is None:
            raise GateRequestError("; ".join(reasons))
        record = json.dumps(
            {
                "bytes": verified.size,
                "mode": mode,
                "path": rendered,
                "sha256": verified.sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        scoped_digest.update(len(record).to_bytes(8, "big"))
        scoped_digest.update(record)
        if rendered.startswith(engine_prefix):
            engine_digest.update(len(record).to_bytes(8, "big"))
            engine_digest.update(record)
        if rendered == GATE_RELATIVE.as_posix():
            gate_digest = verified.sha256
        if rendered == RUNTIME_BINDING_RELATIVE.as_posix():
            runtime_binding_digest = verified.sha256
    if gate_digest is None:
        raise GateRequestError(
            "pricing/billing gate is absent from the scoped baseline"
        )
    if runtime_binding_digest is None:
        raise GateRequestError(
            "pricing/billing runtime binding is absent from the scoped baseline"
        )

    commit = _git_object(
        _git(repository_root, "rev-parse", "--verify", "HEAD^{commit}"),
        "repository commit",
    )
    tree = _git_object(
        _git(repository_root, "rev-parse", "--verify", "HEAD^{tree}"),
        "repository tree",
    )
    engine_tree = _git_object(
        _git(
            repository_root,
            "rev-parse",
            "--verify",
            f"HEAD:{ENGINE_RELATIVE.as_posix()}",
        ),
        "engine Git tree",
    )
    binding = {
        "repositoryCommit": commit,
        "repositoryTree": tree,
        "engineGitTree": engine_tree,
        "gateSha256": "sha256:" + gate_digest,
        "runtimeBindingSha256": "sha256:" + runtime_binding_digest,
        "engineTreeSha256": "sha256:" + engine_digest.hexdigest(),
        "scopedWorktreeSha256": "sha256:" + scoped_digest.hexdigest(),
    }
    canonical = json.dumps(binding, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return {
        "schemaVersion": REPOSITORY_STATE_SCHEMA_VERSION,
        "status": "PASS",
        **binding,
        "baselineSha256": "sha256:" + hashlib.sha256(canonical).hexdigest(),
    }


def _verify_repository_state(
    raw: Any, repository_root: Path
) -> tuple[dict[str, str] | None, list[str]]:
    status, record = _status_record(raw, "repositoryState")
    if status != "PASS":
        return None, [f"repository baseline is not PASS: {status}"]
    try:
        actual = inspect_repository_baseline(repository_root)
    except GateRequestError as exc:
        return None, [str(exc)]
    reasons: list[str] = []
    expected_keys = set(actual)
    if set(record) != expected_keys:
        reasons.append("repositoryState must contain only the exact baseline fields")
    for key, expected in actual.items():
        if record.get(key) != expected:
            reasons.append(f"repositoryState.{key} does not match the live baseline")
    if reasons:
        return None, reasons
    return actual, []


def _parse_trust_store(raw: Any) -> dict[str, TrustedKey]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise GateRequestError("trust store must be a JSON object")
    if raw.get("schemaVersion") != TRUST_STORE_SCHEMA_VERSION:
        raise GateRequestError(
            f"trust store schemaVersion must be {TRUST_STORE_SCHEMA_VERSION}"
        )
    records = raw.get("keys")
    if not isinstance(records, list) or not records:
        raise GateRequestError("trust store must contain at least one public key")
    if len(records) > 64:
        raise GateRequestError("trust store contains too many public keys")
    keys: dict[str, TrustedKey] = {}
    for index, record in enumerate(records):
        label = f"trust store keys[{index}]"
        if not isinstance(record, dict):
            raise GateRequestError(f"{label} must be an object")
        if set(record) != {
            "algorithm",
            "exponent",
            "keyId",
            "modulus",
            "principal",
            "roles",
            "status",
        }:
            raise GateRequestError(f"{label} must contain the exact public-key fields")
        key_id = record.get("keyId")
        principal = record.get("principal")
        roles = record.get("roles")
        modulus_hex = record.get("modulus")
        exponent = record.get("exponent")
        if not _valid_identity(key_id) or not _valid_identity(principal):
            raise GateRequestError(
                f"{label} keyId and principal must be valid identities"
            )
        if key_id in keys:
            raise GateRequestError(f"duplicate trust-store keyId: {key_id}")
        if record.get("algorithm") != "RS256" or record.get("status") != "ACTIVE":
            raise GateRequestError(f"{label} must be an ACTIVE RS256 public key")
        if (
            not isinstance(roles, list)
            or not roles
            or not all(_valid_identity(role) for role in roles)
        ):
            raise GateRequestError(f"{label}.roles must be unique valid identities")
        if len(roles) != len(set(roles)):
            raise GateRequestError(f"{label}.roles must be unique valid identities")
        if (
            not isinstance(modulus_hex, str)
            or re.fullmatch(r"[0-9a-f]+", modulus_hex) is None
            or len(modulus_hex) % 2 != 0
        ):
            raise GateRequestError(f"{label}.modulus must be lowercase hexadecimal")
        modulus = int(modulus_hex, 16)
        if modulus.bit_length() < 2048 or modulus.bit_length() > 8192:
            raise GateRequestError(f"{label}.modulus must be 2048 through 8192 bits")
        if exponent != 65537:
            raise GateRequestError(f"{label}.exponent must be 65537")
        keys[key_id] = TrustedKey(
            key_id=key_id,
            principal=principal,
            roles=frozenset(roles),
            modulus=modulus,
            exponent=exponent,
        )
    return keys


def load_trust_store(path: Path) -> dict[str, Any]:
    return _load_bounded_json_object(
        path,
        "trust store",
        max_bytes=MAX_TRUST_STORE_BYTES,
    )


def _verify_rsa_sha256(payload: bytes, signature_text: Any, key: TrustedKey) -> bool:
    if not isinstance(signature_text, str):
        return False
    try:
        signature = base64.b64decode(signature_text, validate=True)
    except (ValueError, binascii.Error):
        return False
    width = (key.modulus.bit_length() + 7) // 8
    if len(signature) != width:
        return False
    encoded_integer = int.from_bytes(signature, "big")
    if encoded_integer >= key.modulus:
        return False
    encoded = pow(encoded_integer, key.exponent, key.modulus).to_bytes(width, "big")
    digest_info = RSA_SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(payload).digest()
    padding_size = width - len(digest_info) - 3
    if padding_size < 8:
        return False
    expected = b"\x00\x01" + (b"\xff" * padding_size) + b"\x00" + digest_info
    return hmac.compare_digest(encoded, expected)


def _signing_role(evidence_role: str) -> str:
    if evidence_role == "authorization":
        return "authorization-approver"
    if evidence_role == "environment":
        return "environment-verifier"
    if evidence_role == "requirement":
        return "requirement-verifier"
    if evidence_role.endswith("_reconciliation"):
        return "reconciliation-verifier"
    return "external-evidence-verifier"


def _expected_evidence_binding(
    context: EvidenceContext,
    record: dict[str, Any],
    subject_type: str,
    subject_id: str,
) -> dict[str, Any] | None:
    executor = record.get("executor")
    verifier = record.get("verifier")
    if (
        context.repository_binding is None
        or context.run_id is None
        or context.authorization_id is None
        or context.authorization_scope is None
        or context.environment_id is None
        or context.environment_profile is None
        or not _valid_identity(executor)
        or not _valid_identity(verifier)
    ):
        return None
    repository = context.repository_binding
    return {
        "authorizationId": context.authorization_id,
        "authorizationScope": context.authorization_scope,
        "baselineSha256": repository["baselineSha256"],
        "engineGitTree": repository["engineGitTree"],
        "engineTreeSha256": repository["engineTreeSha256"],
        "environmentId": context.environment_id,
        "environmentProfile": context.environment_profile,
        "executor": executor,
        "gateSha256": repository["gateSha256"],
        "installedManifestSha256": "sha256:" + INSTALLED_MANIFEST_SHA256,
        "outcome": "PASS",
        "repositoryCommit": repository["repositoryCommit"],
        "repositoryTree": repository["repositoryTree"],
        "runId": context.run_id,
        "runtimeBindingSha256": repository["runtimeBindingSha256"],
        "scopedWorktreeSha256": repository["scopedWorktreeSha256"],
        "sourceArchiveSha256": "sha256:" + ARCHIVE_SHA256,
        "subjectId": subject_id,
        "subjectType": subject_type,
        "verifier": verifier,
    }


def _verify_evidence_document(
    content: bytes,
    record: dict[str, Any],
    context: EvidenceContext,
    owner: str,
    subject_type: str,
    subject_id: str,
    evidence_role: str,
) -> list[str]:
    try:
        document = _decode_json_object(content, f"{owner} evidence")
    except GateRequestError as exc:
        return [str(exc)]
    if set(document) != {"binding", "evidenceId", "schemaVersion", "signature"}:
        return [f"{owner} evidence must contain the exact signed-envelope fields"]
    if document.get("schemaVersion") != EVIDENCE_SCHEMA_VERSION:
        return [f"{owner} evidence schemaVersion is invalid"]
    evidence_id = document.get("evidenceId")
    if not _valid_identity(evidence_id):
        return [f"{owner} evidenceId must be a valid unique identity"]
    previous_owner = context.evidence_id_owners.get(evidence_id)
    if previous_owner is not None:
        return [
            f"{owner} reuses evidenceId {evidence_id} already bound to {previous_owner}"
        ]
    expected_binding = _expected_evidence_binding(
        context, record, subject_type, subject_id
    )
    if expected_binding is None:
        return [
            f"{owner} cannot bind evidence until authorization, environment, and repository state verify"
        ]
    binding = document.get("binding")
    if not isinstance(binding, dict) or binding != expected_binding:
        return [
            f"{owner} evidence binding does not match its exact subject and gate context"
        ]
    signature = document.get("signature")
    if not isinstance(signature, dict) or set(signature) != {
        "algorithm",
        "keyId",
        "value",
    }:
        return [f"{owner} evidence signature must contain algorithm, keyId, and value"]
    if signature.get("algorithm") != "RS256":
        return [f"{owner} evidence signature algorithm must be RS256"]
    key_id = signature.get("keyId")
    key = context.trust_keys.get(key_id) if isinstance(key_id, str) else None
    if key is None:
        return [f"{owner} evidence signature key is not operator-trusted"]
    verifier = record.get("verifier")
    if key.principal != verifier:
        return [f"{owner} verifier identity does not match the trusted signing key"]
    required_roles = {"independent-verifier", _signing_role(evidence_role)}
    if not required_roles.issubset(key.roles):
        return [f"{owner} trusted signing key lacks required roles"]
    payload = {
        "binding": binding,
        "evidenceId": evidence_id,
        "schemaVersion": EVIDENCE_SCHEMA_VERSION,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if not _verify_rsa_sha256(canonical, signature.get("value"), key):
        return [f"{owner} evidence signature is invalid"]
    context.evidence_id_owners[evidence_id] = owner
    return []


def _verify_pass_record(
    record: dict[str, Any],
    repository_root: Path,
    evidence_roots: list[PurePosixPath],
    label: str,
    *,
    context: EvidenceContext,
    subject_type: str,
    subject_id: str,
    required_role: str,
) -> list[str]:
    reasons: list[str] = []
    executor = record.get("executor")
    verifier = record.get("verifier")
    if not _valid_identity(executor):
        reasons.append(f"{label}.executor is required for PASS")
    if not _valid_identity(verifier):
        reasons.append(f"{label}.verifier is required for PASS")
    if _valid_identity(executor) and _valid_identity(verifier):
        if executor.casefold() == verifier.casefold():
            reasons.append(f"{label} may not self-verify")
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != 1:
        reasons.append(
            f"{label}.evidence must contain exactly one independently signed document for PASS"
        )
        return reasons
    for index, descriptor in enumerate(evidence):
        descriptor_label = f"{label}.evidence[{index}]"
        if not isinstance(descriptor, dict):
            reasons.append(f"{descriptor_label} descriptor is required")
            continue
        try:
            relative = _normalized_relative(
                descriptor.get("path"), f"{descriptor_label}.path"
            )
        except GateRequestError as exc:
            reasons.append(str(exc))
            continue
        rendered = relative.as_posix()
        previous_owner = context.path_owners.get(rendered)
        if previous_owner is not None:
            reasons.append(
                f"{descriptor_label} reuses evidence path already bound to {previous_owner}"
            )
            continue
        context.path_owners[rendered] = label
        verified, descriptor_reasons = _verify_descriptor(
            descriptor,
            repository_root,
            evidence_roots,
            descriptor_label,
            required_role=required_role,
            max_bytes=MAX_EVIDENCE_FILE_BYTES,
            retain_content=True,
            budget=context.budget,
            cache=context.descriptor_cache,
        )
        reasons.extend(descriptor_reasons)
        if verified is None:
            continue
        inode_key = (verified.device, verified.inode)
        previous_inode_owner = context.inode_owners.get(inode_key)
        if previous_inode_owner is not None:
            reasons.append(
                f"{descriptor_label} reuses evidence inode already bound to {previous_inode_owner}"
            )
            continue
        context.inode_owners[inode_key] = label
        if verified.content is None:
            reasons.append(
                f"{descriptor_label} cached evidence bytes cannot be rebound"
            )
            continue
        reasons.extend(
            _verify_evidence_document(
                verified.content,
                record,
                context,
                label,
                subject_type,
                subject_id,
                required_role,
            )
        )
    return reasons


def _validate_installed_manifest(content: bytes) -> list[str]:
    reasons: list[str] = []
    try:
        value = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object_without_duplicates
        )
    except (UnicodeError, json.JSONDecodeError, GateRequestError) as exc:
        return [f"installed manifest is invalid JSON: {exc}"]
    if not isinstance(value, dict):
        return ["installed manifest must be a JSON object"]
    if value.get("schema_version") != "elmos.pricing-billing.installed-manifest.v1":
        reasons.append("installed manifest schema identity is invalid")
    try:
        source_digest = _normalize_sha256(
            value.get("source_archive_sha256"), "installed manifest source_archive"
        )
    except GateRequestError as exc:
        reasons.append(str(exc))
    else:
        if source_digest != ARCHIVE_SHA256:
            reasons.append(
                "installed manifest is not bound to the pinned source archive"
            )
    if value.get("skill_count") != EXPECTED_SKILL_COUNT:
        reasons.append("installed manifest must declare exactly 18 Skills")
    if value.get("requirement_count") != EXPECTED_REQUIREMENT_COUNT:
        reasons.append("installed manifest must declare exactly 180 requirements")
    if value.get("external_evidence_status") != "NOT_RUN":
        reasons.append(
            "installed manifest external evidence boundary must remain NOT_RUN"
        )
    if value.get("production_certification") != "NOT_CERTIFIED":
        reasons.append(
            "installed manifest production boundary must remain NOT_CERTIFIED"
        )
    namespace = value.get("namespace")
    if (
        not isinstance(namespace, dict)
        or namespace.get("name") != "elmos.pricing-billing.v1"
    ):
        reasons.append("installed manifest namespace must be elmos.pricing-billing.v1")
    package = value.get("package")
    if not isinstance(package, dict):
        reasons.append("installed manifest package identity is required")
    else:
        if package.get("source_archive") != ARCHIVE_RELATIVE.as_posix():
            reasons.append(
                "installed manifest package path is not the pinned source archive"
            )
        try:
            package_digest = _normalize_sha256(
                package.get("source_archive_sha256"),
                "installed manifest package source_archive",
            )
        except GateRequestError as exc:
            reasons.append(str(exc))
        else:
            if package_digest != ARCHIVE_SHA256:
                reasons.append(
                    "installed manifest package is not bound to the pinned source archive"
                )
    skills = value.get("skills")
    if not isinstance(skills, list) or len(skills) != EXPECTED_SKILL_COUNT:
        reasons.append("installed manifest must contain exactly 18 Skill records")
    else:
        requirement_ids: list[Any] = []
        for index, skill in enumerate(skills):
            if not isinstance(skill, dict) or not isinstance(
                skill.get("requirement_ids"), list
            ):
                reasons.append(
                    f"installed manifest Skill record {index} must enumerate requirement_ids"
                )
                continue
            if skill.get("runtime_binding") != RUNTIME_BINDING_RELATIVE.as_posix():
                reasons.append(
                    f"installed manifest Skill record {index} runtime binding is invalid"
                )
            if skill.get("runtime_implementation") != "LOCAL_REFERENCE_BOUND":
                reasons.append(
                    f"installed manifest Skill record {index} local binding state is invalid"
                )
            if skill.get("runtime_evidence") != "NOT_RUN":
                reasons.append(
                    f"installed manifest Skill record {index} runtime evidence must remain NOT_RUN"
                )
            if skill.get("external_evidence") != "NOT_RUN":
                reasons.append(
                    f"installed manifest Skill record {index} external evidence must remain NOT_RUN"
                )
            if skill.get("certification") != "NOT_CERTIFIED":
                reasons.append(
                    f"installed manifest Skill record {index} certification must remain NOT_CERTIFIED"
                )
            requirement_ids.extend(skill["requirement_ids"])
        if tuple(requirement_ids) != EXPECTED_REQUIREMENT_IDS:
            reasons.append(
                "installed manifest must bind the exact ordered 180 requirement IDs"
            )
    if value.get("source_scripts_executed_by_importer") is not False:
        reasons.append(
            "installed manifest must retain the untrusted-source execution boundary"
        )
    status = value.get("status")
    if not isinstance(status, dict):
        reasons.append("installed manifest status boundary is required")
    else:
        expected_status = {
            "certification": "NOT_CERTIFIED",
            "external_evidence": "NOT_RUN",
            "production_ready": False,
            "runtime_binding": RUNTIME_BINDING_RELATIVE.as_posix(),
            "runtime_evidence": "NOT_RUN",
            "runtime_implementation": "LOCAL_REFERENCE_BOUND",
        }
        for key, expected in expected_status.items():
            if status.get(key) != expected:
                reasons.append(
                    f"installed manifest status.{key} must remain {expected!r}"
                )
    return reasons


def _verify_runtime_binding_file(
    raw: Any,
    repository_root: Path,
    label: str,
    budget: ByteBudget,
    *,
    allow_extra: bool = False,
    exact_path: Path | None = None,
    exact_size: int | None = None,
    exact_sha256: str | None = None,
) -> tuple[PurePosixPath | None, list[str]]:
    try:
        relative, size, digest = _runtime_file_descriptor(
            raw,
            label,
            allow_extra=allow_extra,
        )
    except GateRequestError as exc:
        return None, [str(exc)]
    reasons: list[str] = []
    if exact_path is not None and relative.as_posix() != exact_path.as_posix():
        reasons.append(f"{label}.path is not the required repository path")
    if exact_size is not None and size != exact_size:
        reasons.append(f"{label}.size does not match the pinned byte count")
    if exact_sha256 is not None and digest != exact_sha256:
        reasons.append(f"{label}.sha256 does not match the pinned digest")
    verified, file_reasons = _read_stable_regular_file(
        repository_root,
        relative,
        label,
        max_bytes=MAX_BASELINE_FILE_BYTES,
        retain_content=False,
        budget=budget,
    )
    reasons.extend(file_reasons)
    if verified is not None:
        if verified.size != size:
            reasons.append(f"{label}.size does not match the live file")
        if verified.sha256 != digest:
            reasons.append(f"{label}.sha256 does not match the live file")
    return (relative if verified is not None else None), reasons


def _validate_runtime_binding_tree(
    raw: Any,
    repository_root: Path,
    tree_name: str,
    allowed_roots: frozenset[str],
    required_root: str,
    budget: ByteBudget,
) -> list[str]:
    label = f"runtimeBinding.taskOwnedTrees.{tree_name}"
    if not isinstance(raw, dict):
        return [f"{label} must be an object"]
    expected_keys = {
        "algorithm",
        "roots",
        "fileCount",
        "byteCount",
        "sha256",
        "files",
        "exclusions",
    }
    reasons: list[str] = []
    if set(raw) != expected_keys:
        reasons.append(f"{label} must contain only the exact tree-binding fields")
    if raw.get("algorithm") != "sha256-path-size-content-v1":
        reasons.append(f"{label}.algorithm is invalid")
    roots = raw.get("roots")
    if (
        not isinstance(roots, list)
        or not roots
        or not all(isinstance(item, str) for item in roots)
    ):
        return [*reasons, f"{label}.roots must be a non-empty string list"]
    rendered_roots = tuple(roots)
    if rendered_roots != tuple(sorted(set(rendered_roots))):
        reasons.append(f"{label}.roots must be unique and sorted")
    if required_root not in rendered_roots:
        reasons.append(f"{label}.roots is missing required root {required_root}")
    unexpected_roots = sorted(set(rendered_roots) - allowed_roots)
    if unexpected_roots:
        reasons.append(f"{label}.roots contains unapproved paths: {unexpected_roots}")
    try:
        normalized_roots = [
            _normalized_relative(item, f"{label}.roots") for item in rendered_roots
        ]
    except GateRequestError as exc:
        return [*reasons, str(exc)]
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        return [*reasons, f"{label}.files must be a non-empty list"]
    if len(files) > MAX_RUNTIME_BINDING_FILES:
        return [*reasons, f"{label}.files exceeds the file-count limit"]
    digest = hashlib.sha256()
    seen: set[str] = set()
    total_bytes = 0
    ordered_paths: list[str] = []
    for index, record in enumerate(files):
        file_label = f"{label}.files[{index}]"
        try:
            relative, size, sha256 = _runtime_file_descriptor(record, file_label)
        except GateRequestError as exc:
            reasons.append(str(exc))
            continue
        rendered = relative.as_posix()
        ordered_paths.append(rendered)
        if rendered in seen:
            reasons.append(f"{label}.files contains duplicate path {rendered}")
            continue
        seen.add(rendered)
        if not _inside_relative(relative, normalized_roots):
            reasons.append(f"{file_label}.path escapes its declared roots")
        total_bytes += size
        encoded_path = rendered.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(sha256))
        _verified, file_reasons = _verify_runtime_binding_file(
            record,
            repository_root,
            file_label,
            budget,
        )
        reasons.extend(file_reasons)
    if ordered_paths != sorted(ordered_paths):
        reasons.append(f"{label}.files must be sorted by path")
    if raw.get("fileCount") != len(files):
        reasons.append(f"{label}.fileCount is inconsistent")
    if raw.get("byteCount") != total_bytes:
        reasons.append(f"{label}.byteCount is inconsistent")
    try:
        declared_digest = _normalize_sha256(raw.get("sha256"), label)
    except GateRequestError as exc:
        reasons.append(str(exc))
    else:
        if declared_digest != digest.hexdigest():
            reasons.append(f"{label}.sha256 does not match its ordered file records")
    expected_exclusions = tuple(
        sorted(
            {
                ".cache",
                ".mypy_cache",
                ".pytest_cache",
                ".ruff_cache",
                ".venv",
                "*.pyc",
                "*.pyo",
                "__pycache__",
                "cache",
                "caches",
                "venv",
            }
        )
    )
    exclusions = raw.get("exclusions")
    if not isinstance(exclusions, list) or tuple(exclusions) != expected_exclusions:
        reasons.append(f"{label}.exclusions is not the exact fail-closed exclusion set")
    return reasons


def _validate_runtime_binding(
    content: bytes,
    repository_root: Path,
    catalog: dict[str, dict[str, str]],
) -> list[str]:
    try:
        value = _decode_json_object(content, "runtimeBinding")
    except GateRequestError as exc:
        return [str(exc)]
    reasons: list[str] = []
    expected_top_level = {
        "schemaVersion",
        "packageNamespace",
        "sourceArchive",
        "installedManifest",
        "runtimeRegistry",
        "requirementTraceability",
        "taskOwnedTrees",
        "claimCeiling",
        "nonClaims",
    }
    if set(value) != expected_top_level:
        reasons.append("runtimeBinding must contain only the exact binding fields")
    if value.get("schemaVersion") != 1:
        reasons.append("runtimeBinding schemaVersion must be 1")
    if value.get("packageNamespace") != "elmos.pricing-billing.v1":
        reasons.append("runtimeBinding package namespace is invalid")
    budget = ByteBudget(MAX_BASELINE_TOTAL_BYTES)

    source = value.get("sourceArchive")
    if not isinstance(source, dict) or set(source) != {
        "path",
        "size",
        "sha256",
        "identityClaimOnly",
        "traceabilityCatalog",
    }:
        reasons.append("runtimeBinding.sourceArchive fields are invalid")
    else:
        if source.get("identityClaimOnly") is not True:
            reasons.append(
                "runtimeBinding source archive must remain identity-claim-only"
            )
        if source.get("traceabilityCatalog") != {
            "member": TRACEABILITY_MEMBER,
            "priorityCounts": {"P0": 108, "P1": 72},
            "requirementCount": 180,
            "sha256": TRACEABILITY_SHA256,
            "size": TRACEABILITY_BYTES,
        }:
            reasons.append("runtimeBinding traceability catalog identity drifted")
    _source_path, source_reasons = _verify_runtime_binding_file(
        source,
        repository_root,
        "runtimeBinding.sourceArchive",
        budget,
        allow_extra=True,
        exact_path=ARCHIVE_RELATIVE,
        exact_size=ARCHIVE_BYTES,
        exact_sha256=ARCHIVE_SHA256,
    )
    reasons.extend(source_reasons)

    manifest = value.get("installedManifest")
    _manifest_path, manifest_reasons = _verify_runtime_binding_file(
        manifest,
        repository_root,
        "runtimeBinding.installedManifest",
        budget,
        exact_path=INSTALLED_MANIFEST_RELATIVE,
        exact_size=INSTALLED_MANIFEST_BYTES,
        exact_sha256=INSTALLED_MANIFEST_SHA256,
    )
    reasons.extend(manifest_reasons)

    registry = value.get("runtimeRegistry")
    registry_path, registry_reasons = _verify_runtime_binding_file(
        registry,
        repository_root,
        "runtimeBinding.runtimeRegistry",
        budget,
        allow_extra=True,
        exact_path=Path(
            "engines/pricing-billing-engine/src/elmos_pricing_billing/registry.py"
        ),
    )
    reasons.extend(registry_reasons)
    if not isinstance(registry, dict) or set(registry) != {
        "path",
        "size",
        "sha256",
        "skillCount",
        "skills",
        "inspection",
    }:
        reasons.append("runtimeBinding.runtimeRegistry fields are invalid")
    else:
        if registry.get("skillCount") != EXPECTED_SKILL_COUNT:
            reasons.append("runtimeBinding runtime registry must contain 18 Skills")
        if tuple(registry.get("skills", ())) != EXPECTED_SKILLS:
            reasons.append("runtimeBinding runtime registry Skill inventory drifted")
        if registry.get("inspection") != "AST_LITERAL_SCAN_ONLY_NO_IMPORT_OR_EXECUTION":
            reasons.append("runtimeBinding runtime registry inspection boundary is invalid")
    if registry_path is None:
        reasons.append("runtimeBinding runtime registry bytes did not verify")

    traceability = value.get("requirementTraceability")
    source_paths: set[str] = set()
    if not isinstance(traceability, dict):
        reasons.append("runtimeBinding.requirementTraceability must be an object")
    else:
        expected_traceability_keys = {
            "requirementCount",
            "priorityCounts",
            "sourceFiles",
            "implementationCounts",
            "testExecutionCounts",
            "externalEvidenceCounts",
            "bindings",
        }
        if set(traceability) != expected_traceability_keys:
            reasons.append("runtimeBinding requirement traceability fields are invalid")
        if traceability.get("requirementCount") != EXPECTED_REQUIREMENT_COUNT:
            reasons.append("runtimeBinding must contain exactly 180 requirements")
        if traceability.get("priorityCounts") != {"P0": 108, "P1": 72}:
            reasons.append("runtimeBinding requirement priority counts drifted")
        source_files = traceability.get("sourceFiles")
        if not isinstance(source_files, list) or not source_files:
            reasons.append("runtimeBinding requirement source files are required")
        else:
            for index, record in enumerate(source_files):
                label = f"runtimeBinding.requirementTraceability.sourceFiles[{index}]"
                relative, file_reasons = _verify_runtime_binding_file(
                    record,
                    repository_root,
                    label,
                    budget,
                )
                reasons.extend(file_reasons)
                if relative is not None:
                    rendered = relative.as_posix()
                    if not rendered.startswith(
                        "verification-packs/pricing-billing-local-v1/requirements/"
                    ):
                        reasons.append(f"{label}.path is outside the requirement mapping root")
                    source_paths.add(rendered)
        bindings = traceability.get("bindings")
        implementation_counts: Counter[str] = Counter()
        test_counts: Counter[str] = Counter()
        external_counts: Counter[str] = Counter()
        if not isinstance(bindings, list) or len(bindings) != EXPECTED_REQUIREMENT_COUNT:
            reasons.append("runtimeBinding bindings must contain exactly 180 records")
        else:
            for index, (expected_id, record) in enumerate(
                zip(EXPECTED_REQUIREMENT_IDS, bindings, strict=True)
            ):
                label = f"runtimeBinding.requirementTraceability.bindings[{index}]"
                if not isinstance(record, dict):
                    reasons.append(f"{label} must be an object")
                    continue
                expected_keys = {
                    "id",
                    "canonicalId",
                    "skill",
                    "priority",
                    "sourceBatch",
                    "sourceStatement",
                    "symbols",
                    "tests",
                    "implementation",
                    "testExecution",
                    "externalEvidence",
                    "certification",
                    "mappingSource",
                }
                if set(record) != expected_keys:
                    reasons.append(f"{label} fields are invalid")
                if record.get("id") != expected_id:
                    reasons.append(f"{label}.id is not the exact ordered requirement")
                expected_canonical = f"elmos.pricing-billing.v1/{expected_id}"
                if record.get("canonicalId") != expected_canonical:
                    reasons.append(f"{label}.canonicalId is invalid")
                source_record = catalog.get(expected_id, {})
                if record.get("skill") != source_record.get("skill"):
                    reasons.append(f"{label}.skill owner drifted")
                if record.get("priority") != source_record.get("priority"):
                    reasons.append(f"{label}.priority differs from the source archive")
                if record.get("sourceBatch") != source_record.get("batch"):
                    reasons.append(f"{label}.sourceBatch differs from the source archive")
                if record.get("sourceStatement") != source_record.get("statement"):
                    reasons.append(
                        f"{label}.sourceStatement differs from the source archive"
                    )
                for key in ("symbols", "tests"):
                    items = record.get(key)
                    if (
                        not isinstance(items, list)
                        or not items
                        or not all(isinstance(item, str) and item.strip() for item in items)
                    ):
                        reasons.append(f"{label}.{key} must be a non-empty string list")
                implementation = record.get("implementation")
                if implementation not in RUNTIME_BINDING_IMPLEMENTATION_STATES:
                    reasons.append(f"{label}.implementation exceeds the local ceiling")
                elif isinstance(implementation, str):
                    implementation_counts[implementation] += 1
                test_state = record.get("testExecution")
                if test_state not in RUNTIME_BINDING_TEST_STATES:
                    reasons.append(f"{label}.testExecution exceeds the local ceiling")
                elif isinstance(test_state, str):
                    test_counts[test_state] += 1
                external_state = record.get("externalEvidence")
                if external_state != "NOT_RUN":
                    reasons.append(f"{label}.externalEvidence must remain NOT_RUN")
                else:
                    external_counts[external_state] += 1
                if record.get("certification") != "NOT_CERTIFIED":
                    reasons.append(f"{label}.certification must remain NOT_CERTIFIED")
                mapping_source = record.get("mappingSource")
                if mapping_source not in source_paths:
                    reasons.append(f"{label}.mappingSource is not a verified mapping file")
        if traceability.get("implementationCounts") != dict(
            sorted(implementation_counts.items())
        ):
            reasons.append("runtimeBinding implementation counts are inconsistent")
        if traceability.get("testExecutionCounts") != dict(sorted(test_counts.items())):
            reasons.append("runtimeBinding test execution counts are inconsistent")
        if traceability.get("externalEvidenceCounts") != dict(
            sorted(external_counts.items())
        ):
            reasons.append("runtimeBinding external evidence counts are inconsistent")

    trees = value.get("taskOwnedTrees")
    if not isinstance(trees, dict) or set(trees) != {"runtime", "tests"}:
        reasons.append("runtimeBinding.taskOwnedTrees must contain runtime and tests only")
    else:
        reasons.extend(
            _validate_runtime_binding_tree(
                trees.get("runtime"),
                repository_root,
                "runtime",
                RUNTIME_BINDING_RUNTIME_ROOTS,
                "engines/pricing-billing-engine/src",
                budget,
            )
        )
        reasons.extend(
            _validate_runtime_binding_tree(
                trees.get("tests"),
                repository_root,
                "tests",
                RUNTIME_BINDING_TEST_ROOTS,
                "engines/pricing-billing-engine/tests",
                budget,
            )
        )

    if value.get("claimCeiling") != {
        "maximumLocalState": "LOCAL_EXECUTED",
        "externalProviderBankTaxAccountingEvidence": (
            "NOT_RUN_UNLESS_EXPLICITLY_BOUND_PER_REQUIREMENT"
        ),
        "certification": "NOT_CERTIFIED",
    }:
        reasons.append("runtimeBinding claim ceiling is invalid")
    if tuple(value.get("nonClaims", ())) != RUNTIME_BINDING_NON_CLAIMS:
        reasons.append("runtimeBinding non-claims are incomplete or reordered")
    return reasons


def _empty_result(*, malformed: bool, blockers: list[str]) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "decision": BLOCKED_DECISION,
        "maximumDecision": MAXIMUM_DECISION,
        "malformed": malformed,
        "certified": False,
        "productionApproved": False,
        "gaApproved": False,
        "sourceArchiveVerified": False,
        "installedManifestVerified": False,
        "runtimeBindingVerified": False,
        "repositoryBaselineVerified": False,
        "independentTrustConfigured": False,
        "verifiedEvidenceCount": 0,
        "evidenceBytesRead": 0,
        "requirementSummary": {},
        "p0Summary": {},
        "reconciliation": {},
        "externalEvidence": {},
        "blockers": sorted(set(blockers)),
    }


def evaluate(
    request: dict[str, Any],
    repository_root: Path,
    trust_store: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one request without writing repository or evidence state."""

    repository_root = repository_root.resolve(strict=True)
    if request.get("schemaVersion") != REQUEST_SCHEMA_VERSION:
        raise GateRequestError("request schemaVersion must be 1.0")
    if request.get("requestedDecision") != MAXIMUM_DECISION:
        raise GateRequestError(
            f"requestedDecision must be exactly {MAXIMUM_DECISION}; certification is unavailable"
        )
    run_id = request.get("runId")
    if not _valid_identity(run_id):
        raise GateRequestError("runId must be a valid immutable run identity")
    _walk_forbidden_claims(request)
    evidence_roots = _requested_evidence_roots(request)
    blockers: list[str] = []
    trust_keys = _parse_trust_store(trust_store)
    if not trust_keys:
        blockers.append(
            "operator-supplied independent public trust store is required before readiness"
        )

    archive_file, archive_reasons = _verify_descriptor(
        request.get("sourceArchive"),
        repository_root,
        None,
        "sourceArchive",
        exact_path=ARCHIVE_RELATIVE,
        exact_sha256=ARCHIVE_SHA256,
    )
    blockers.extend(archive_reasons)
    catalog: dict[str, str] = {}
    catalog_records: dict[str, dict[str, str]] = {}
    if archive_file is not None and archive_file.content is not None:
        try:
            catalog_records = _load_requirement_catalog_records_bytes(
                archive_file.content
            )
            catalog = {
                identifier: record["priority"]
                for identifier, record in catalog_records.items()
            }
        except GateRequestError as exc:
            blockers.append(str(exc))

    manifest_file, manifest_reasons = _verify_descriptor(
        request.get("installedManifest"),
        repository_root,
        None,
        "installedManifest",
        exact_path=INSTALLED_MANIFEST_RELATIVE,
        exact_sha256=INSTALLED_MANIFEST_SHA256,
    )
    blockers.extend(manifest_reasons)
    manifest_validation_reasons: list[str] = []
    if manifest_file is not None and manifest_file.content is not None:
        manifest_validation_reasons = _validate_installed_manifest(
            manifest_file.content
        )
        blockers.extend(manifest_validation_reasons)

    runtime_binding_file, runtime_binding_reasons = _verify_descriptor(
        request.get("runtimeBinding"),
        repository_root,
        None,
        "runtimeBinding",
        exact_path=RUNTIME_BINDING_RELATIVE,
        max_bytes=MAX_RUNTIME_BINDING_BYTES,
    )
    blockers.extend(runtime_binding_reasons)
    runtime_binding_validation_reasons: list[str] = []
    if runtime_binding_file is not None and runtime_binding_file.content is not None:
        runtime_binding_validation_reasons = _validate_runtime_binding(
            runtime_binding_file.content,
            repository_root,
            catalog_records,
        )
        blockers.extend(runtime_binding_validation_reasons)

    repository_binding, repository_reasons = _verify_repository_state(
        request.get("repositoryState"), repository_root
    )
    blockers.extend(repository_reasons)
    if runtime_binding_file is not None and repository_binding is not None:
        expected_runtime_digest = "sha256:" + runtime_binding_file.sha256
        if repository_binding.get("runtimeBindingSha256") != expected_runtime_digest:
            blockers.append(
                "runtimeBinding does not match the clean repository baseline"
            )

    authorization = request.get("authorization")
    if not isinstance(authorization, dict):
        raise GateRequestError("authorization must be an explicit status object")
    authorization_status, authorization_record = _status_record(
        authorization, "authorization"
    )
    authorization_id = authorization_record.get("authorizationId")
    authorization_scope = authorization_record.get("scope")
    if authorization_status != "PASS":
        blockers.append(f"authorization is not PASS: {authorization_status}")
    else:
        if not _valid_identity(authorization_id):
            blockers.append("authorization.authorizationId is required for PASS")
        if not _valid_identity(authorization_scope):
            blockers.append("authorization.scope is required for PASS")

    environment = request.get("environment")
    if not isinstance(environment, dict):
        raise GateRequestError("environment must be an explicit status object")
    environment_status, environment_record = _status_record(environment, "environment")
    environment_id = environment_record.get("environmentId")
    environment_profile = environment_record.get("profile")
    if environment_status != "PASS":
        blockers.append(f"environment is not PASS: {environment_status}")
    else:
        if not _valid_identity(environment_id):
            blockers.append("environment.environmentId is required for PASS")
        if not _valid_identity(environment_profile):
            blockers.append("environment.profile is required for PASS")

    context = EvidenceContext(
        trust_keys=trust_keys,
        run_id=run_id if isinstance(run_id, str) else None,
        authorization_id=(
            authorization_id
            if authorization_status == "PASS" and _valid_identity(authorization_id)
            else None
        ),
        authorization_scope=(
            authorization_scope
            if authorization_status == "PASS" and _valid_identity(authorization_scope)
            else None
        ),
        environment_id=(
            environment_id
            if environment_status == "PASS" and _valid_identity(environment_id)
            else None
        ),
        environment_profile=(
            environment_profile
            if environment_status == "PASS" and _valid_identity(environment_profile)
            else None
        ),
        repository_binding=repository_binding,
        budget=ByteBudget(MAX_TOTAL_EVIDENCE_BYTES),
        descriptor_cache={},
        path_owners={},
        inode_owners={},
        evidence_id_owners={},
    )

    results = request.get("requirementResults")
    if not isinstance(results, dict):
        raise GateRequestError(
            "requirementResults must be an object keyed by requirement ID"
        )
    if not all(isinstance(identifier, str) for identifier in results):
        raise GateRequestError("requirementResults keys must be strings")
    result_ids = set(results)
    expected_ids = set(catalog) if catalog else set(EXPECTED_REQUIREMENT_IDS)
    for identifier in sorted(expected_ids - result_ids):
        blockers.append(f"requirement result missing: {identifier}")
    for identifier in sorted(result_ids - expected_ids):
        blockers.append(f"unknown requirement result: {identifier}")

    status_counts: Counter[str] = Counter()
    p0_counts: Counter[str] = Counter()
    for identifier in EXPECTED_REQUIREMENT_IDS:
        if identifier not in results or identifier not in catalog:
            continue
        priority = catalog[identifier]
        status, record = _status_record(
            results[identifier], f"requirementResults.{identifier}"
        )
        declared_priority = record.get("priority")
        if declared_priority is not None and declared_priority != priority:
            blockers.append(
                f"requirement priority mismatch: {identifier}: "
                f"expected={priority} declared={declared_priority}"
            )
        status_counts[status] += 1
        if priority == "P0":
            p0_counts[status] += 1
            if status != "PASS":
                blockers.append(f"P0 requirement is not PASS: {identifier}: {status}")
        elif status in KNOWN_FAILURE_STATUSES:
            blockers.append(
                f"P1 requirement has a blocking status: {identifier}: {status}"
            )
        if status == "PASS":
            blockers.extend(
                _verify_pass_record(
                    record,
                    repository_root,
                    evidence_roots,
                    f"requirementResults.{identifier}",
                    context=context,
                    subject_type="requirement",
                    subject_id=identifier,
                    required_role="requirement",
                )
            )

    if authorization_status == "PASS":
        blockers.extend(
            _verify_pass_record(
                authorization_record,
                repository_root,
                evidence_roots,
                "authorization",
                context=context,
                subject_type="authorization",
                subject_id=str(authorization_id),
                required_role="authorization",
            )
        )
    if environment_status == "PASS":
        blockers.extend(
            _verify_pass_record(
                environment_record,
                repository_root,
                evidence_roots,
                "environment",
                context=context,
                subject_type="environment",
                subject_id=str(environment_id),
                required_role="environment",
            )
        )

    reconciliation = request.get("reconciliation")
    if not isinstance(reconciliation, dict):
        raise GateRequestError("reconciliation must be an explicit domain object")
    reconciliation_statuses: dict[str, str] = {}
    for domain in RECONCILIATION_DOMAINS:
        if domain not in reconciliation:
            blockers.append(f"reconciliation status missing: {domain}")
            continue
        status, record = _status_record(
            reconciliation[domain], f"reconciliation.{domain}"
        )
        reconciliation_statuses[domain] = status
        if status != "PASS":
            blockers.append(f"{domain} reconciliation is unreconciled: {status}")
        else:
            blockers.extend(
                _verify_pass_record(
                    record,
                    repository_root,
                    evidence_roots,
                    f"reconciliation.{domain}",
                    context=context,
                    subject_type="reconciliation",
                    subject_id=domain,
                    required_role=f"{domain}_reconciliation",
                )
            )
    for extra in sorted(set(reconciliation) - set(RECONCILIATION_DOMAINS)):
        blockers.append(f"unknown reconciliation domain: {extra}")

    external = request.get("externalEvidence")
    if not isinstance(external, dict):
        raise GateRequestError(
            "externalEvidence must explicitly enumerate external domains"
        )
    external_statuses: dict[str, str] = {}
    for domain in EXTERNAL_EVIDENCE_DOMAINS:
        if domain not in external:
            blockers.append(f"external evidence status missing: {domain}")
            continue
        status, record = _status_record(external[domain], f"externalEvidence.{domain}")
        external_statuses[domain] = status
        if status in KNOWN_FAILURE_STATUSES:
            blockers.append(
                f"external evidence has a blocking status: {domain}: {status}"
            )
        if status == "PASS":
            role = "disaster_recovery" if domain == "disasterRecovery" else domain
            blockers.extend(
                _verify_pass_record(
                    record,
                    repository_root,
                    evidence_roots,
                    f"externalEvidence.{domain}",
                    context=context,
                    subject_type="external",
                    subject_id=domain,
                    required_role=role,
                )
            )
    for extra in sorted(set(external) - set(EXTERNAL_EVIDENCE_DOMAINS)):
        blockers.append(f"unknown external evidence domain: {extra}")

    blockers = sorted(set(blockers))
    decision = MAXIMUM_DECISION if not blockers else BLOCKED_DECISION
    return {
        "schemaVersion": SCHEMA_VERSION,
        "decision": decision,
        "maximumDecision": MAXIMUM_DECISION,
        "malformed": False,
        "certified": False,
        "productionApproved": False,
        "gaApproved": False,
        "sourceArchiveVerified": archive_file is not None and not archive_reasons,
        "installedManifestVerified": manifest_file is not None
        and not manifest_reasons
        and not manifest_validation_reasons,
        "runtimeBindingVerified": runtime_binding_file is not None
        and not runtime_binding_reasons
        and not runtime_binding_validation_reasons,
        "repositoryBaselineVerified": repository_binding is not None
        and not repository_reasons,
        "independentTrustConfigured": bool(trust_keys),
        "verifiedEvidenceCount": len(context.evidence_id_owners),
        "evidenceBytesRead": context.budget.consumed,
        "requirementCatalogCount": len(catalog),
        "requirementSummary": dict(sorted(status_counts.items())),
        "p0Summary": dict(sorted(p0_counts.items())),
        "authorization": authorization_status,
        "environment": environment_status,
        "reconciliation": reconciliation_statuses,
        "externalEvidence": external_statuses,
        "blockers": blockers,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, help="repository readiness request JSON")
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root used for all confined evidence paths",
    )
    parser.add_argument(
        "--trust-store",
        type=Path,
        help=(
            "operator-controlled public trust store; without it readiness is blocked"
        ),
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return exit 3 when the well-formed request is BLOCKED",
    )
    args = parser.parse_args(argv)
    try:
        request = load_json_request(args.request)
        trust_store = load_trust_store(args.trust_store) if args.trust_store else None
        result = evaluate(request, args.repository_root, trust_store)
    except GateRequestError as exc:
        result = _empty_result(malformed=True, blockers=[str(exc)])
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    except OSError as exc:
        result = _empty_result(
            malformed=True, blockers=[f"repository root is unavailable: {exc}"]
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_ready and result["decision"] != MAXIMUM_DECISION:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
