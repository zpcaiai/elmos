"""Strict loader for the imported Spring Golden Route Skill catalog."""

from __future__ import annotations

import copy
import hashlib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Mapping

from .canonical import parse_json_strict
from .errors import CatalogValidationError, RequestValidationError

PACKAGE = "elmos-spring-golden-route-commercial-skills"
PACKAGE_VERSION = "2.0.0"
MANIFEST_SCHEMA = "elmos.spring-golden-route.installed-manifest.v2"
CONTRACTS_SCHEMA = "elmos.spring-golden-route.compiled-contracts.v2"
SOURCE_ARCHIVE_SHA256 = "sha256:952dce43681a56dbd3323ef03b334b08d5be980000e9c7ee3f0ac3e3bcd42c4e"
INSTALLED_MANIFEST_SHA256 = "sha256:e2689dfcd95b4cae38bd29b704da028c79703d247cc12e67e019a7da768d51aa"
COMPILED_CONTRACTS_SHA256 = "sha256:adfa6e88204dbf3590417b3a219efee054f4ae0a9ba5e9306571f7071caf9cf4"
EXPECTED_SKILL_COUNT = 196
EXPECTED_FOUNDATION_COUNT = 100
EXPECTED_COMMERCIAL_COUNT = 96
EXPECTED_BATCH_COUNT = 22
EXPECTED_DEPENDENCY_EDGES = 128
EXPECTED_FOUNDATION_CRITICAL_EDGES = 21
EXPECTED_EFFECTIVE_DEPENDENCY_EDGES = 149
EXPECTED_COMMERCIAL_BATCH_EDGES = 24
EXPECTED_FOUNDATION_BATCH_EDGES = 19
EXPECTED_BATCH_EDGES = 43
EXPECTED_FOUNDATION_BATCH_ID_MAP = {
    f"{batch:02d}": f"F{batch:02d}" for batch in range(1, 11)
}
EXPECTED_BATCH_TOPOLOGICAL_ORDER = tuple(
    [f"F{batch:02d}" for batch in range(1, 11)]
    + [str(batch) for batch in range(11, 23)]
)
EXPECTED_FOUNDATION_SKILLS_PER_BATCH = 10
EXPECTED_COMMERCIAL_SKILLS_PER_BATCH = 8
EXPECTED_ARCHIVE_BYTES = 1_228_281
EXPECTED_ARCHIVE_ENTRIES = 596
EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES = 2_127_024
EXPECTED_OUTER_CHECKSUM_ENTRIES = 594
EXPECTED_OUTER_CHECKSUM_SHA256 = "sha256:18a3e8d9ffaa20a6ba4b33b987578fe5323bf497625eed468ebda0612dad50bf"
EXPECTED_FOUNDATION_CHECKSUM_ENTRIES = 130
EXPECTED_INSTALLED_NAMESPACE = "spring-golden-route-commercial-v2"
ARCHIVE_PREFIX = "elmos-spring-golden-route-commercial-skills-v2.0.0/"
EXPECTED_QUARANTINE = (
    "scripts/__pycache__/estimate_quote.cpython-313.pyc",
    "scripts/__pycache__/generate_completion_proof.cpython-313.pyc",
    "scripts/__pycache__/repository_scale.cpython-313.pyc",
    "scripts/__pycache__/validate_benchmark_claim.cpython-313.pyc",
    "tests/__pycache__/test_toolkit.cpython-313.pyc",
)

_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_FOUNDATION_SOURCE_ID_RE = re.compile(r"FOUNDATION-([0-9]{2})-[a-z0-9]+(?:-[a-z0-9]+)*\Z")

_MANIFEST_KEYS = {
    "archive_code_execution",
    "batch_dependency_edge_count",
    "batch_topological_order",
    "batch_count",
    "canonical_source",
    "certification",
    "commercial_skill_count",
    "commercial_batch_dependencies",
    "commercial_batch_dependency_edge_count",
    "commercial_skill_dependencies",
    "compiled_contracts_path",
    "compiled_contracts_sha256",
    "contract_count",
    "customer_evidence_status",
    "dependency_edge_count",
    "declared_topological_order",
    "effective_dependency_edge_count",
    "external_evidence_status",
    "foundation_checksum_entries",
    "foundation_batch_dependencies",
    "foundation_batch_id_map",
    "foundation_batch_dependency_edge_count",
    "foundation_critical_dependency_edge_count",
    "foundation_critical_skill_dependencies",
    "foundation_skill_count",
    "implementation_state",
    "independent_provenance_attestation_status",
    "installed_namespace",
    "outer_checksum_entries",
    "outer_checksum_sha256",
    "package",
    "package_authored_provenance_records",
    "package_license_status",
    "package_sbom_status",
    "package_signature_status",
    "package_version",
    "quarantined_archive_members",
    "runtime_evidence_status",
    "schema_version",
    "side_effects_authorized",
    "skill_count",
    "skills",
    "source_archive_bytes",
    "source_archive_entries",
    "source_archive_sha256",
    "source_archive_uncompressed_bytes",
    "normalized_foundation_batch_dependencies",
    "topological_order",
}
_SKILL_KEYS = {
    "certification",
    "customer_evidence_status",
    "dependencies",
    "external_evidence_status",
    "implementation_state",
    "installed_name",
    "installed_sha256",
    "interface_sha256",
    "required_outputs",
    "runtime_evidence_status",
    "runtime_path",
    "side_effects_authorized",
    "source_batch",
    "source_contract_path",
    "source_contract_sha256",
    "source_id",
    "source_name",
    "source_origin",
    "source_path",
    "source_sha256",
    "workspace_path",
}
_COMPILED_KEYS = {
    "batch_dependency_edge_count",
    "batch_topological_order",
    "certification",
    "contract_count",
    "contracts",
    "commercial_batch_dependencies",
    "commercial_batch_dependency_edge_count",
    "commercial_skill_dependencies",
    "customer_evidence_status",
    "dependency_edge_count",
    "declared_topological_order",
    "effective_dependency_edge_count",
    "external_evidence_status",
    "foundation_critical_dependency_edge_count",
    "foundation_critical_skill_dependencies",
    "foundation_batch_dependencies",
    "foundation_batch_id_map",
    "foundation_batch_dependency_edge_count",
    "implementation_state",
    "normalized_foundation_batch_dependencies",
    "package",
    "package_version",
    "runtime_evidence_status",
    "schema_version",
    "side_effects_authorized",
    "skill_count",
    "source_archive_sha256",
    "topological_order",
}
_CONTRACT_KEYS = {
    "batch",
    "certification",
    "customer_evidence_status",
    "definition_of_done",
    "dependencies",
    "description",
    "evidence",
    "external_evidence_status",
    "implementation_state",
    "name",
    "origin",
    "permissions",
    "priority",
    "production_claim_boundary",
    "required_outputs",
    "risk",
    "runtime_evidence_status",
    "side_effects_authorized",
    "source_contract_sha256",
    "source_id",
    "source_skill_sha256",
    "stop_conditions",
    "tests",
}
_PERMISSION_KEYS = {
    "default",
    "external_side_effect",
    "network",
    "production",
    "read_repository",
    "write_repository",
}
_EXPECTED_PERMISSIONS = {
    "default": "deny",
    "external_side_effect": "ask",
    "network": "ask",
    "production": "dual-approval-or-policy",
    "read_repository": "allow",
    "write_repository": "ask",
}
_RUNTIME_REGISTRY_KEYS = {
    "binding_state", "bindings", "certification", "control_plane_evidence_status",
    "customer_evidence_status", "dispatcher", "domain_runtime_evidence_status",
    "engine_path", "external_evidence_status", "module_path", "package",
    "package_version", "schema_version", "side_effects_authorized", "skill_count",
    "source_archive_sha256",
}
_RUNTIME_BINDING_KEYS = {
    "binding_state", "certification", "control_plane_evidence_status",
    "customer_evidence_status", "dispatcher", "domain_runtime_evidence_status",
    "engine_path", "external_evidence_status", "module_path", "schema_version",
    "side_effects_authorized", "skill_name", "source_contract_sha256", "source_id",
    "supported_operations",
}
_RUNTIME_BINDING_CONSTANTS = {
    "binding_state": "BOUNDED_LOCAL_CONTROL_PLANE_IMPLEMENTED",
    "certification": "NOT_CERTIFIED",
    "control_plane_evidence_status": "DECLARED",
    "customer_evidence_status": "NOT_RUN",
    "dispatcher": "dispatch_skill",
    "domain_runtime_evidence_status": "NOT_RUN",
    "engine_path": "engines/spring-golden-route-engine",
    "external_evidence_status": "NOT_RUN",
    "module_path": "elmos_spring_golden_route.runtime",
    "side_effects_authorized": False,
}


@dataclass(frozen=True, slots=True)
class SkillContract:
    name: str
    source_id: str
    batch: str
    origin: str
    description: str
    dependencies: tuple[str, ...]
    critical_dependencies: tuple[str, ...]
    effective_dependencies: tuple[str, ...]
    required_outputs: tuple[str, ...]
    source_contract_sha256: str
    source_skill_sha256: str
    data: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        value = _thaw_json(self.data)
        assert isinstance(value, dict)
        return value


@dataclass(frozen=True, slots=True)
class Catalog:
    repository_root: Path
    manifest_path: Path
    contracts_path: Path
    source_archive_sha256: str
    compiled_contracts_sha256: str
    topological_order: tuple[str, ...]
    batch_topological_order: tuple[str, ...]
    foundation_batch_id_map: Mapping[str, str]
    normalized_foundation_batch_dependencies: Mapping[str, tuple[str, ...]]
    batch_dependencies: Mapping[str, tuple[str, ...]]
    contracts: Mapping[str, SkillContract]

    @property
    def skill_count(self) -> int:
        return len(self.contracts)


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


def _fail(message: str, **details: object) -> None:
    raise CatalogValidationError(message, details=details)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _exact_keys(value: object, expected: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        _fail(
            f"{label} has an invalid field set",
            missing=sorted(expected - actual),
            extra=sorted(actual - expected),
        )
    return value


def _exact_int(value: object, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        _fail(f"{label} must equal {expected}", actual=value)


def _string(value: object, label: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        _fail(f"{label} must be a non-empty bounded string")
    return value


def _string_list(value: object, label: str, *, maximum: int = 512) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        _fail(f"{label} must be a bounded array")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_string(item, f"{label}[{index}]"))
    if len(result) != len(set(result)):
        _fail(f"{label} contains duplicate entries")
    return result


def _dependency_map(value: object, label: str) -> dict[str, list[str]]:
    if not isinstance(value, dict) or len(value) > EXPECTED_SKILL_COUNT:
        _fail(f"{label} must be a bounded dependency object")
    result: dict[str, list[str]] = {}
    for key, dependencies in value.items():
        name = _string(key, f"{label}.key", maximum=64)
        result[name] = _string_list(dependencies, f"{label}.{name}")
    return result


def _foundation_batch_id_map(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    result: dict[str, str] = {}
    for raw, normalized in value.items():
        raw_id = _string(raw, f"{label}.key", maximum=2)
        normalized_id = _string(normalized, f"{label}.{raw_id}", maximum=3)
        if raw_id in result:
            _fail(f"{label} contains a duplicate raw Batch ID", batch=raw_id)
        result[raw_id] = normalized_id
    if result != EXPECTED_FOUNDATION_BATCH_ID_MAP:
        _fail(
            f"{label} must be the exact raw-to-normalized foundation Batch map",
            expected=EXPECTED_FOUNDATION_BATCH_ID_MAP,
            actual=result,
        )
    return result


def _digest(value: object, label: str) -> str:
    digest = _string(value, label, maximum=71)
    if not _DIGEST_RE.fullmatch(digest):
        _fail(f"{label} is not a canonical SHA-256 digest")
    return digest


def _safe_relative(value: object, label: str) -> str:
    text = _string(value, label)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or "\\" in text:
        _fail(f"{label} is not a safe repository-relative path")
    return text


def _load(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        _fail(f"{label} does not exist", path=str(path))
    maximum_bytes = 2_000_000
    if path.stat().st_size > maximum_bytes:
        _fail(f"{label} exceeds the bounded JSON file limit", maximum_bytes=maximum_bytes)
    try:
        with path.open("rb") as stream:
            raw = stream.read(maximum_bytes + 1)
        if len(raw) > maximum_bytes:
            _fail(f"{label} exceeds the bounded JSON file limit", maximum_bytes=maximum_bytes)
        value = parse_json_strict(
            raw,
            max_bytes=maximum_bytes,
            max_depth=24,
            max_items=20_000,
        )
    except (OSError, RequestValidationError) as exc:
        _fail(f"{label} is not strict JSON", reason=str(exc))
    if not isinstance(value, dict):
        _fail(f"{label} must contain an object")
    return value


def _require_boundary(record: Mapping[str, object], label: str) -> None:
    expected = {
        "implementation_state": "SPECIFICATION_IMPORTED",
        "runtime_evidence_status": "NOT_RUN",
        "customer_evidence_status": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "side_effects_authorized": False,
    }
    for key, value in expected.items():
        if record.get(key) != value:
            _fail(f"{label}.{key} weakens the conservative evidence boundary", actual=record.get(key))


def _verify_file(path: Path, expected_digest: str, label: str) -> None:
    if not path.is_file():
        _fail(f"{label} is missing", path=str(path))
    actual = _sha256(path)
    if actual != expected_digest:
        _fail(f"{label} digest mismatch", path=str(path), expected=expected_digest, actual=actual)


def load_catalog(
    repository_root: str | Path,
    *,
    verify_repository_assets: bool = True,
) -> Catalog:
    """Load and fail-closed validate the exact imported v2.0.0 catalog.

    ``verify_repository_assets`` is exposed for isolated negative tests only.
    Production callers and the CLI leave it enabled.
    """

    root = Path(repository_root).expanduser().resolve()
    docs = root / "docs" / "spring-golden-route-commercial-skills"
    manifest_path = docs / "installed-manifest.json"
    contracts_path = docs / "compiled-contracts.json"
    if not manifest_path.is_file() or _sha256(manifest_path) != INSTALLED_MANIFEST_SHA256:
        _fail("installed manifest bytes do not match the pinned importer artifact")
    manifest = _exact_keys(_load(manifest_path, "installed manifest"), _MANIFEST_KEYS, "manifest")
    compiled = _exact_keys(_load(contracts_path, "compiled contracts"), _COMPILED_KEYS, "compiled")

    if manifest["schema_version"] != MANIFEST_SCHEMA:
        _fail("unsupported installed-manifest schema")
    if compiled["schema_version"] != CONTRACTS_SCHEMA:
        _fail("unsupported compiled-contracts schema")
    if manifest["installed_namespace"] != EXPECTED_INSTALLED_NAMESPACE:
        _fail("installed namespace is not the exact v2 namespace")
    if manifest["archive_code_execution"] != "DENIED":
        _fail("archive code execution must remain DENIED")
    for field in (
        "package_license_status",
        "package_signature_status",
        "package_sbom_status",
        "independent_provenance_attestation_status",
    ):
        if manifest[field] != "NOT_PROVIDED":
            _fail("package trust boundary must not be upgraded without exact independent evidence", field=field)
    provenance_records = manifest["package_authored_provenance_records"]
    if not isinstance(provenance_records, list) or len(provenance_records) != 3:
        _fail("package-authored provenance record inventory mismatch")
    provenance_inventory: dict[str, str] = {}
    for index, record in enumerate(provenance_records):
        item = _exact_keys(record, {"path", "sha256"}, f"manifest.package_authored_provenance_records[{index}]")
        path = _safe_relative(item["path"], f"manifest.package_authored_provenance_records[{index}].path")
        digest = _digest(item["sha256"], f"manifest.package_authored_provenance_records[{index}].sha256")
        if path in provenance_inventory:
            _fail("duplicate package-authored provenance record", path=path)
        provenance_inventory[path] = digest
    for label, record in (("manifest", manifest), ("compiled", compiled)):
        if record["package"] != PACKAGE or record["package_version"] != PACKAGE_VERSION:
            _fail(f"{label} package identity mismatch")
        if record["source_archive_sha256"] != SOURCE_ARCHIVE_SHA256:
            _fail(f"{label} source archive digest is not the pinned v2.0.0 digest")
        _require_boundary(record, label)

    _exact_int(manifest["skill_count"], EXPECTED_SKILL_COUNT, "manifest.skill_count")
    _exact_int(manifest["contract_count"], EXPECTED_SKILL_COUNT, "manifest.contract_count")
    _exact_int(manifest["foundation_skill_count"], EXPECTED_FOUNDATION_COUNT, "manifest.foundation_skill_count")
    _exact_int(manifest["commercial_skill_count"], EXPECTED_COMMERCIAL_COUNT, "manifest.commercial_skill_count")
    _exact_int(manifest["batch_count"], EXPECTED_BATCH_COUNT, "manifest.batch_count")
    _exact_int(manifest["dependency_edge_count"], EXPECTED_DEPENDENCY_EDGES, "manifest.dependency_edge_count")
    _exact_int(
        manifest["effective_dependency_edge_count"],
        EXPECTED_EFFECTIVE_DEPENDENCY_EDGES,
        "manifest.effective_dependency_edge_count",
    )
    _exact_int(
        manifest["commercial_batch_dependency_edge_count"],
        EXPECTED_COMMERCIAL_BATCH_EDGES,
        "manifest.commercial_batch_dependency_edge_count",
    )
    _exact_int(
        manifest["foundation_batch_dependency_edge_count"],
        EXPECTED_FOUNDATION_BATCH_EDGES,
        "manifest.foundation_batch_dependency_edge_count",
    )
    _exact_int(manifest["batch_dependency_edge_count"], EXPECTED_BATCH_EDGES, "manifest.batch_dependency_edge_count")
    _exact_int(
        manifest["foundation_critical_dependency_edge_count"],
        EXPECTED_FOUNDATION_CRITICAL_EDGES,
        "manifest.foundation_critical_dependency_edge_count",
    )
    _exact_int(manifest["source_archive_bytes"], EXPECTED_ARCHIVE_BYTES, "manifest.source_archive_bytes")
    _exact_int(manifest["source_archive_entries"], EXPECTED_ARCHIVE_ENTRIES, "manifest.source_archive_entries")
    _exact_int(
        manifest["source_archive_uncompressed_bytes"],
        EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES,
        "manifest.source_archive_uncompressed_bytes",
    )
    _exact_int(
        manifest["outer_checksum_entries"],
        EXPECTED_OUTER_CHECKSUM_ENTRIES,
        "manifest.outer_checksum_entries",
    )
    if manifest["outer_checksum_sha256"] != EXPECTED_OUTER_CHECKSUM_SHA256:
        _fail("outer checksum inventory digest mismatch")
    _exact_int(
        manifest["foundation_checksum_entries"],
        EXPECTED_FOUNDATION_CHECKSUM_ENTRIES,
        "manifest.foundation_checksum_entries",
    )
    if manifest["quarantined_archive_members"] != list(EXPECTED_QUARANTINE):
        _fail("quarantined archive member inventory mismatch")
    _exact_int(compiled["skill_count"], EXPECTED_SKILL_COUNT, "compiled.skill_count")
    _exact_int(compiled["contract_count"], EXPECTED_SKILL_COUNT, "compiled.contract_count")
    _exact_int(compiled["dependency_edge_count"], EXPECTED_DEPENDENCY_EDGES, "compiled.dependency_edge_count")
    _exact_int(
        compiled["effective_dependency_edge_count"],
        EXPECTED_EFFECTIVE_DEPENDENCY_EDGES,
        "compiled.effective_dependency_edge_count",
    )
    _exact_int(
        compiled["commercial_batch_dependency_edge_count"],
        EXPECTED_COMMERCIAL_BATCH_EDGES,
        "compiled.commercial_batch_dependency_edge_count",
    )
    _exact_int(
        compiled["foundation_batch_dependency_edge_count"],
        EXPECTED_FOUNDATION_BATCH_EDGES,
        "compiled.foundation_batch_dependency_edge_count",
    )
    _exact_int(compiled["batch_dependency_edge_count"], EXPECTED_BATCH_EDGES, "compiled.batch_dependency_edge_count")
    _exact_int(
        compiled["foundation_critical_dependency_edge_count"],
        EXPECTED_FOUNDATION_CRITICAL_EDGES,
        "compiled.foundation_critical_dependency_edge_count",
    )

    compiled_digest = _sha256(contracts_path)
    if compiled_digest != COMPILED_CONTRACTS_SHA256:
        _fail("compiled contracts bytes do not match the pinned importer artifact")
    if _digest(manifest["compiled_contracts_sha256"], "manifest.compiled_contracts_sha256") != compiled_digest:
        _fail("compiled contracts digest does not match the manifest")
    expected_contracts_path = "docs/spring-golden-route-commercial-skills/compiled-contracts.json"
    if manifest["compiled_contracts_path"] != expected_contracts_path:
        _fail("compiled contracts path is not canonical")

    runtime_registry_path = docs / "runtime-registry.json"
    runtime_registry = _exact_keys(
        _load(runtime_registry_path, "runtime registry"),
        _RUNTIME_REGISTRY_KEYS,
        "runtime_registry",
    )
    if (
        runtime_registry["schema_version"] != "elmos.spring-golden-route.runtime-registry.v1"
        or runtime_registry["package"] != PACKAGE
        or runtime_registry["package_version"] != PACKAGE_VERSION
        or runtime_registry["skill_count"] != EXPECTED_SKILL_COUNT
        or runtime_registry["source_archive_sha256"] != SOURCE_ARCHIVE_SHA256
    ):
        _fail("runtime registry identity/count binding mismatch")
    for key, expected in _RUNTIME_BINDING_CONSTANTS.items():
        if runtime_registry[key] != expected:
            _fail("runtime registry weakens the bounded static binding", field=key)

    declared_topological_order = _string_list(
        manifest["declared_topological_order"], "manifest.declared_topological_order"
    )
    compiled_declared_order = _string_list(
        compiled["declared_topological_order"], "compiled.declared_topological_order"
    )
    topological_order = _string_list(manifest["topological_order"], "manifest.topological_order")
    compiled_order = _string_list(compiled["topological_order"], "compiled.topological_order")
    batch_topological_order = _string_list(
        manifest["batch_topological_order"], "manifest.batch_topological_order"
    )
    compiled_batch_order = _string_list(
        compiled["batch_topological_order"], "compiled.batch_topological_order"
    )
    if (
        topological_order != compiled_order
        or declared_topological_order != compiled_declared_order
        or batch_topological_order != compiled_batch_order
        or len(topological_order) != EXPECTED_SKILL_COUNT
        or len(declared_topological_order) != EXPECTED_SKILL_COUNT
        or len(batch_topological_order) != EXPECTED_BATCH_COUNT
    ):
        _fail("topological orders do not identify the same 196 Skills")
    if tuple(batch_topological_order) != EXPECTED_BATCH_TOPOLOGICAL_ORDER:
        _fail("Batch topological order is not the exact normalized F01..F10 then 11..22 order")

    commercial_skill_dependencies = _dependency_map(
        manifest["commercial_skill_dependencies"], "manifest.commercial_skill_dependencies"
    )
    foundation_critical_dependencies = _dependency_map(
        manifest["foundation_critical_skill_dependencies"],
        "manifest.foundation_critical_skill_dependencies",
    )
    commercial_batch_dependencies = _dependency_map(
        manifest["commercial_batch_dependencies"], "manifest.commercial_batch_dependencies"
    )
    foundation_batch_id_map = _foundation_batch_id_map(
        manifest["foundation_batch_id_map"], "manifest.foundation_batch_id_map"
    )
    foundation_batch_dependencies = _dependency_map(
        manifest["foundation_batch_dependencies"], "manifest.foundation_batch_dependencies"
    )
    normalized_foundation_batch_dependencies = _dependency_map(
        manifest["normalized_foundation_batch_dependencies"],
        "manifest.normalized_foundation_batch_dependencies",
    )
    graph_pairs = {
        "commercial_skill_dependencies": commercial_skill_dependencies,
        "foundation_critical_skill_dependencies": foundation_critical_dependencies,
        "commercial_batch_dependencies": commercial_batch_dependencies,
        "foundation_batch_id_map": foundation_batch_id_map,
        "foundation_batch_dependencies": foundation_batch_dependencies,
        "normalized_foundation_batch_dependencies": normalized_foundation_batch_dependencies,
    }
    for field, expected in graph_pairs.items():
        if compiled[field] != expected:
            _fail("manifest and compiled dependency graphs disagree", field=field)

    if set(foundation_batch_dependencies) != set(foundation_batch_id_map):
        _fail("raw foundation Batch graph does not cover exact raw Batch IDs 01..10")
    for raw_batch, dependencies in foundation_batch_dependencies.items():
        if any(dependency not in foundation_batch_id_map for dependency in dependencies):
            _fail(
                "raw foundation Batch graph references an unknown raw Batch ID",
                batch=raw_batch,
            )
    derived_normalized_foundation_graph = {
        foundation_batch_id_map[raw_batch]: [
            foundation_batch_id_map[dependency] for dependency in dependencies
        ]
        for raw_batch, dependencies in foundation_batch_dependencies.items()
    }
    if normalized_foundation_batch_dependencies != derived_normalized_foundation_graph:
        _fail("normalized foundation Batch graph is not the exact mapped raw 01..10 graph")

    raw_skills = manifest["skills"]
    raw_contracts = compiled["contracts"]
    if not isinstance(raw_skills, list) or len(raw_skills) != EXPECTED_SKILL_COUNT:
        _fail("manifest.skills must contain exactly 196 entries")
    if not isinstance(raw_contracts, list) or len(raw_contracts) != EXPECTED_SKILL_COUNT:
        _fail("compiled.contracts must contain exactly 196 entries")

    skills: dict[str, dict[str, object]] = {}
    for index, item in enumerate(raw_skills):
        skill = _exact_keys(item, _SKILL_KEYS, f"manifest.skills[{index}]")
        name = _string(skill["installed_name"], f"manifest.skills[{index}].installed_name", maximum=64)
        if not _NAME_RE.fullmatch(name) or name in skills:
            _fail("invalid or duplicate installed Skill name", name=name)
        if skill["source_name"] != name:
            _fail("installed and source Skill names differ", name=name)
        _require_boundary(skill, f"manifest.skills[{index}]")
        _digest(skill["installed_sha256"], f"manifest.skills[{index}].installed_sha256")
        _digest(skill["interface_sha256"], f"manifest.skills[{index}].interface_sha256")
        _digest(skill["source_contract_sha256"], f"manifest.skills[{index}].source_contract_sha256")
        _digest(skill["source_sha256"], f"manifest.skills[{index}].source_sha256")
        _string_list(skill["dependencies"], f"manifest.skills[{index}].dependencies")
        _string_list(skill["required_outputs"], f"manifest.skills[{index}].required_outputs")
        _safe_relative(skill["runtime_path"], f"manifest.skills[{index}].runtime_path")
        _safe_relative(skill["workspace_path"], f"manifest.skills[{index}].workspace_path")
        _safe_relative(skill["source_path"], f"manifest.skills[{index}].source_path")
        _safe_relative(skill["source_contract_path"], f"manifest.skills[{index}].source_contract_path")
        if skill["runtime_path"] != f"agent-skills/runtime/{name}/SKILL.md":
            _fail("non-canonical runtime Skill path", name=name)
        if skill["workspace_path"] != f".agents/skills/{name}/SKILL.md":
            _fail("non-canonical workspace Skill path", name=name)
        skills[name] = skill

    contracts: dict[str, SkillContract] = {}
    origins: dict[str, int] = {"foundation": 0, "commercial-extension": 0}
    batches: set[str] = set()
    for index, item in enumerate(raw_contracts):
        contract = _exact_keys(item, _CONTRACT_KEYS, f"compiled.contracts[{index}]")
        name = _string(contract["name"], f"compiled.contracts[{index}].name", maximum=64)
        if not _NAME_RE.fullmatch(name) or name in contracts or name not in skills:
            _fail("invalid, duplicate, or unmatched compiled Skill name", name=name)
        _require_boundary(contract, f"compiled.contracts[{index}]")
        origin = _string(contract["origin"], f"compiled.contracts[{index}].origin")
        if origin not in origins:
            _fail("unknown Skill origin", name=name, origin=origin)
        origins[origin] += 1
        batch = _string(contract["batch"], f"compiled.contracts[{index}].batch")
        source_id = _string(contract["source_id"], f"compiled.contracts[{index}].source_id")
        if origin == "foundation":
            match = _FOUNDATION_SOURCE_ID_RE.fullmatch(source_id)
            if match is None or match.group(1) not in foundation_batch_id_map:
                _fail("foundation source ID does not carry an exact raw Batch ID", name=name)
            expected_batch = foundation_batch_id_map[match.group(1)]
            if batch != expected_batch:
                _fail(
                    "foundation contract Batch does not match its raw source ID mapping",
                    name=name,
                    source_id=source_id,
                    expected_batch=expected_batch,
                    actual_batch=batch,
                )
        batches.add(batch)
        dependencies = _string_list(contract["dependencies"], f"compiled.contracts[{index}].dependencies")
        critical_dependencies = foundation_critical_dependencies.get(name, [])
        effective_dependencies = dependencies + [
            dependency for dependency in critical_dependencies if dependency not in dependencies
        ]
        required_outputs = _string_list(
            contract["required_outputs"], f"compiled.contracts[{index}].required_outputs"
        )
        for list_field in ("definition_of_done", "evidence", "stop_conditions", "tests"):
            _string_list(contract[list_field], f"compiled.contracts[{index}].{list_field}")
        permissions = _exact_keys(
            contract["permissions"], _PERMISSION_KEYS, f"compiled.contracts[{index}].permissions"
        )
        if permissions != _EXPECTED_PERMISSIONS:
            _fail("compiled Skill permissions weaken the imported deny-by-default policy", name=name)
        source_contract_sha256 = _digest(
            contract["source_contract_sha256"], f"compiled.contracts[{index}].source_contract_sha256"
        )
        source_skill_sha256 = _digest(
            contract["source_skill_sha256"], f"compiled.contracts[{index}].source_skill_sha256"
        )
        skill = skills[name]
        comparisons = {
            "source_id": source_id,
            "source_batch": batch,
            "source_origin": origin,
            "source_contract_sha256": source_contract_sha256,
            "source_sha256": source_skill_sha256,
            "dependencies": dependencies,
            "required_outputs": required_outputs,
        }
        for skill_key, expected in comparisons.items():
            if skill[skill_key] != expected:
                _fail("manifest and compiled contract disagree", name=name, field=skill_key)
        contracts[name] = SkillContract(
            name=name,
            source_id=source_id,
            batch=batch,
            origin=origin,
            description=_string(contract["description"], f"compiled.contracts[{index}].description"),
            dependencies=tuple(dependencies),
            critical_dependencies=tuple(critical_dependencies),
            effective_dependencies=tuple(effective_dependencies),
            required_outputs=tuple(required_outputs),
            source_contract_sha256=source_contract_sha256,
            source_skill_sha256=source_skill_sha256,
            data=_freeze_json(copy.deepcopy(contract)),
        )

    if origins != {"foundation": EXPECTED_FOUNDATION_COUNT, "commercial-extension": EXPECTED_COMMERCIAL_COUNT}:
        _fail("foundation/commercial Skill totals are invalid", actual=origins)
    expected_foundation_batches = set(normalized_foundation_batch_dependencies)
    expected_commercial_batches = set(commercial_batch_dependencies)
    expected_batches = expected_foundation_batches | expected_commercial_batches
    if (
        expected_foundation_batches != set(foundation_batch_id_map.values())
        or expected_foundation_batches & expected_commercial_batches
        or len(expected_batches) != EXPECTED_BATCH_COUNT
        or batches != expected_batches
    ):
        _fail(
            "contract Batch coverage does not match the normalized foundation and commercial graphs",
            actual=sorted(batches),
            expected=sorted(expected_batches),
        )
    batch_counts = {
        batch: sum(1 for contract in contracts.values() if contract.batch == batch)
        for batch in expected_batches
    }
    for batch in expected_foundation_batches:
        if batch_counts[batch] != EXPECTED_FOUNDATION_SKILLS_PER_BATCH:
            _fail("foundation Batch must contain exactly 10 contracts", batch=batch, actual=batch_counts[batch])
    for batch in expected_commercial_batches:
        if batch_counts[batch] != EXPECTED_COMMERCIAL_SKILLS_PER_BATCH:
            _fail("commercial Batch must contain exactly 8 contracts", batch=batch, actual=batch_counts[batch])
    if (
        set(topological_order) != set(contracts)
        or set(declared_topological_order) != set(contracts)
        or set(skills) != set(contracts)
    ):
        _fail("catalog name sets do not match the topological order")
    commercial_names = {name for name, contract in contracts.items() if contract.origin == "commercial-extension"}
    foundation_names = {name for name, contract in contracts.items() if contract.origin == "foundation"}
    if not set(commercial_skill_dependencies).issubset(commercial_names):
        _fail("commercial graph contains a non-commercial dependent")
    if not set(foundation_critical_dependencies).issubset(foundation_names):
        _fail("foundation critical graph contains a non-foundation dependent")
    for name, contract in contracts.items():
        expected_declared = commercial_skill_dependencies.get(name, [])
        if list(contract.dependencies) != expected_declared:
            _fail("compiled declared dependencies differ from the commercial source graph", name=name)
    edge_count = sum(len(dependencies) for dependencies in commercial_skill_dependencies.values())
    if edge_count != EXPECTED_DEPENDENCY_EDGES:
        _fail("derived dependency edge count is invalid", actual=edge_count)
    critical_edge_count = sum(len(dependencies) for dependencies in foundation_critical_dependencies.values())
    if critical_edge_count != EXPECTED_FOUNDATION_CRITICAL_EDGES:
        _fail("derived foundation critical edge count is invalid", actual=critical_edge_count)
    effective_edge_count = sum(len(contract.effective_dependencies) for contract in contracts.values())
    if effective_edge_count != EXPECTED_EFFECTIVE_DEPENDENCY_EDGES:
        _fail("derived effective dependency edge count is invalid", actual=effective_edge_count)
    declared_positions = {name: index for index, name in enumerate(declared_topological_order)}
    positions = {name: index for index, name in enumerate(topological_order)}
    for name, contract in contracts.items():
        for dependency in contract.dependencies:
            if dependency not in declared_positions:
                _fail("dependency names an unknown Skill", name=name, dependency=dependency)
            if declared_positions[dependency] >= declared_positions[name]:
                _fail("declared topological order violates dependency DAG", name=name, dependency=dependency)
        for dependency in contract.effective_dependencies:
            if dependency not in positions or positions[dependency] >= positions[name]:
                _fail("union topological order violates effective dependency DAG", name=name, dependency=dependency)

    batch_dependencies = {
        **normalized_foundation_batch_dependencies,
        **commercial_batch_dependencies,
    }
    if set(batch_dependencies) != set(batch_topological_order):
        _fail("batch dependency graph and topological order name sets differ")
    if sum(len(value) for value in commercial_batch_dependencies.values()) != EXPECTED_COMMERCIAL_BATCH_EDGES:
        _fail("commercial batch edge count drift")
    if sum(len(value) for value in foundation_batch_dependencies.values()) != EXPECTED_FOUNDATION_BATCH_EDGES:
        _fail("foundation batch edge count drift")
    if (
        sum(len(value) for value in normalized_foundation_batch_dependencies.values())
        != EXPECTED_FOUNDATION_BATCH_EDGES
    ):
        _fail("normalized foundation batch edge count drift")
    batch_positions = {name: index for index, name in enumerate(batch_topological_order)}
    for name, dependencies in batch_dependencies.items():
        for dependency in dependencies:
            if dependency not in batch_positions or batch_positions[dependency] >= batch_positions[name]:
                _fail("batch topological order violates dependency DAG", name=name, dependency=dependency)

    raw_bindings = runtime_registry["bindings"]
    if not isinstance(raw_bindings, list) or len(raw_bindings) != EXPECTED_SKILL_COUNT:
        _fail("runtime registry must contain exactly 196 bindings")
    runtime_bindings: dict[str, dict[str, object]] = {}
    for index, item in enumerate(raw_bindings):
        binding = _exact_keys(item, _RUNTIME_BINDING_KEYS, f"runtime_registry.bindings[{index}]")
        name = _string(binding["skill_name"], f"runtime_registry.bindings[{index}].skill_name", maximum=64)
        if name in runtime_bindings or name not in contracts:
            _fail("runtime registry has an unknown or duplicate Skill binding", name=name)
        if binding["schema_version"] != "elmos.spring-golden-route.runtime-binding.v1":
            _fail("runtime Skill binding schema mismatch", name=name)
        for key, expected in _RUNTIME_BINDING_CONSTANTS.items():
            if binding[key] != expected:
                _fail("runtime Skill binding weakens the static evidence boundary", name=name, field=key)
        if (
            binding["supported_operations"] != ["describe", "plan"]
            or binding["source_id"] != contracts[name].source_id
            or binding["source_contract_sha256"] != contracts[name].source_contract_sha256
        ):
            _fail("runtime Skill binding provenance or operation mismatch", name=name)
        runtime_bindings[name] = binding
    if set(runtime_bindings) != set(contracts):
        _fail("runtime binding name set is incomplete")

    if verify_repository_assets:
        canonical_source = _safe_relative(manifest["canonical_source"], "manifest.canonical_source")
        archive_path = root / canonical_source
        _verify_file(archive_path, SOURCE_ARCHIVE_SHA256, "canonical source archive")
        if type(manifest["source_archive_bytes"]) is not int or archive_path.stat().st_size != manifest["source_archive_bytes"]:
            _fail("source archive size does not match the manifest")
        try:
            archive = zipfile.ZipFile(archive_path)
        except (OSError, zipfile.BadZipFile) as exc:
            _fail("canonical source archive is not a readable ZIP", reason=str(exc))
        with archive:
            infos = archive.infolist()
            if len(infos) != EXPECTED_ARCHIVE_ENTRIES:
                _fail("canonical source archive entry count drift", actual=len(infos))
            if sum(info.file_size for info in infos) != EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES:
                _fail("canonical source archive uncompressed byte count drift")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or any(not name.startswith(ARCHIVE_PREFIX) for name in names):
                _fail("canonical source archive member identity drift")
            actual_quarantine = sorted(
                name.removeprefix(ARCHIVE_PREFIX) for name in names if name.endswith(".pyc")
            )
            if actual_quarantine != list(EXPECTED_QUARANTINE):
                _fail("canonical source archive quarantine content drift")
            for path, expected_digest in provenance_inventory.items():
                try:
                    provenance_bytes = archive.read(f"{ARCHIVE_PREFIX}{path}")
                except KeyError as exc:
                    _fail("package-authored provenance record is missing from the pinned ZIP", path=path)
                if _sha256_bytes(provenance_bytes) != expected_digest:
                    _fail("package-authored provenance record digest mismatch", path=path)
            outer_bytes = archive.read(f"{ARCHIVE_PREFIX}SHA256SUMS.txt")
            if _sha256_bytes(outer_bytes) != EXPECTED_OUTER_CHECKSUM_SHA256:
                _fail("canonical source outer checksum file digest drift")
            outer_lines = [line for line in outer_bytes.decode("utf-8").splitlines() if line.strip()]
            if len(outer_lines) != EXPECTED_OUTER_CHECKSUM_ENTRIES:
                _fail("canonical source outer checksum entry count drift")
            foundation_checksum_names = [name for name in names if name.endswith("/SHA256SUMS.txt")]
            if len(foundation_checksum_names) != 2:
                _fail("canonical source checksum inventory shape drift")
            nested_name = next(name for name in foundation_checksum_names if name != f"{ARCHIVE_PREFIX}SHA256SUMS.txt")
            nested_lines = [
                line
                for line in archive.read(nested_name).decode("utf-8").splitlines()
                if line.strip()
            ]
            if len(nested_lines) != EXPECTED_FOUNDATION_CHECKSUM_ENTRIES:
                _fail("canonical source foundation checksum entry count drift")

            graph_members = {
                "commercial": f"{ARCHIVE_PREFIX}manifest/dependency-graph.json",
                "foundation": (
                    f"{ARCHIVE_PREFIX}foundation/openrewrite-opencode-v1.0/"
                    "manifest/dependency-graph.json"
                ),
            }
            source_graphs: dict[str, dict[str, object]] = {}
            for graph_name, member in graph_members.items():
                try:
                    graph_value = parse_json_strict(
                        archive.read(member), max_bytes=262_144, max_depth=24, max_items=4_096
                    )
                except (KeyError, RequestValidationError) as exc:
                    _fail("pinned dependency graph is missing or invalid", graph=graph_name, reason=str(exc))
                if not isinstance(graph_value, dict):
                    _fail("pinned dependency graph must be an object", graph=graph_name)
                source_graphs[graph_name] = graph_value
            if (
                source_graphs["commercial"].get("skill_dependencies")
                != commercial_skill_dependencies
                or source_graphs["commercial"].get("batch_dependencies")
                != commercial_batch_dependencies
                or source_graphs["foundation"].get("critical_skill_dependencies")
                != foundation_critical_dependencies
                or source_graphs["foundation"].get("batch_dependencies")
                != foundation_batch_dependencies
            ):
                _fail("installed dependency graphs differ from the exact pinned ZIP graphs")

            schema_member = f"{ARCHIVE_PREFIX}schemas/skill-contract.schema.json"
            schema_bytes = archive.read(schema_member)
            schema_digest = _sha256_bytes(schema_bytes)
            for name, skill in skills.items():
                source_skill_member = f"{ARCHIVE_PREFIX}{skill['source_path']}"
                source_contract_member = f"{ARCHIVE_PREFIX}{skill['source_contract_path']}"
                try:
                    source_skill_bytes = archive.read(source_skill_member)
                    source_contract_bytes = archive.read(source_contract_member)
                except KeyError as exc:
                    _fail("manifest source record is absent from the pinned archive", name=name, member=str(exc))
                if _sha256_bytes(source_skill_bytes) != skill["source_sha256"]:
                    _fail("manifest source Skill digest disagrees with pinned archive", name=name)
                if _sha256_bytes(source_contract_bytes) != skill["source_contract_sha256"]:
                    _fail("manifest source contract digest disagrees with pinned archive", name=name)
                try:
                    source_contract = parse_json_strict(
                        source_contract_bytes,
                        max_bytes=262_144,
                        max_depth=24,
                        max_items=4_096,
                    )
                except RequestValidationError as exc:
                    _fail("pinned source contract is not strict bounded JSON", name=name, reason=str(exc))
                if not isinstance(source_contract, dict):
                    _fail("pinned source contract must be an object", name=name)
                compiled_contract = contracts[name].as_dict()
                semantic_bindings = {
                    "source_id": source_contract.get("id"),
                    "name": source_contract.get("name"),
                    "description": source_contract.get("description"),
                    "batch": source_contract.get("batch"),
                    "origin": source_contract.get("origin"),
                    "priority": source_contract.get("priority"),
                    "risk": source_contract.get("risk"),
                    "dependencies": source_contract.get("dependencies"),
                    "required_outputs": source_contract.get("outputs"),
                    "permissions": source_contract.get("permissions"),
                    "tests": source_contract.get("tests"),
                    "evidence": source_contract.get("evidence"),
                    "stop_conditions": source_contract.get("stop_conditions"),
                    "definition_of_done": source_contract.get("definition_of_done"),
                    "production_claim_boundary": source_contract.get("production_claim_boundary"),
                }
                for field, expected in semantic_bindings.items():
                    if compiled_contract.get(field) != expected:
                        _fail("compiled contract semantic drift from pinned source", name=name, field=field)

        for name, skill in skills.items():
            runtime_skill = root / str(skill["runtime_path"])
            workspace_skill = root / str(skill["workspace_path"])
            installed_digest = str(skill["installed_sha256"])
            interface_digest = str(skill["interface_sha256"])
            contract_digest = str(skill["source_contract_sha256"])
            for path, label in ((runtime_skill, "runtime Skill"), (workspace_skill, "workspace Skill")):
                _verify_file(path, installed_digest, f"{label} {name}")
                _verify_file(path.parent / "agents" / "openai.yaml", interface_digest, f"{label} interface {name}")
                _verify_file(
                    path.parent / "references" / "contract.json", contract_digest, f"{label} contract {name}"
                )
                _verify_file(
                    path.parent / "schemas" / "skill-contract.schema.json",
                    schema_digest,
                    f"{label} contract schema {name}",
                )
                binding_path = path.parent / "references" / "runtime-binding.json"
                if not binding_path.is_file():
                    _fail("installed runtime binding is missing", name=name, path=str(binding_path))
                binding_data = _load(binding_path, f"installed runtime binding {name}")
                if binding_data != runtime_bindings[name]:
                    _fail("installed runtime binding differs from the exact registry", name=name)
            for suffix in (
                Path("SKILL.md"),
                Path("agents/openai.yaml"),
                Path("references/contract.json"),
                Path("schemas/skill-contract.schema.json"),
                Path("references/runtime-binding.json"),
            ):
                if (runtime_skill.parent / suffix).read_bytes() != (workspace_skill.parent / suffix).read_bytes():
                    _fail("dual-root installed Skill drift", name=name, path=str(suffix))

        runtime_module = root / "engines/spring-golden-route-engine/src/elmos_spring_golden_route/runtime.py"
        if not runtime_module.is_file():
            _fail("runtime registry module path is not installed")

    return Catalog(
        repository_root=root,
        manifest_path=manifest_path,
        contracts_path=contracts_path,
        source_archive_sha256=SOURCE_ARCHIVE_SHA256,
        compiled_contracts_sha256=compiled_digest,
        topological_order=tuple(topological_order),
        batch_topological_order=tuple(batch_topological_order),
        foundation_batch_id_map=MappingProxyType(dict(foundation_batch_id_map)),
        normalized_foundation_batch_dependencies=MappingProxyType(
            {
                batch: tuple(dependencies)
                for batch, dependencies in normalized_foundation_batch_dependencies.items()
            }
        ),
        batch_dependencies=MappingProxyType(
            {batch: tuple(dependencies) for batch, dependencies in batch_dependencies.items()}
        ),
        contracts=MappingProxyType(contracts),
    )
