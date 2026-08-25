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
MANIFEST_SCHEMA = "elmos.spring-golden-route.installed-manifest.v1"
CONTRACTS_SCHEMA = "elmos.spring-golden-route.compiled-contracts.v1"
SOURCE_ARCHIVE_SHA256 = "sha256:952dce43681a56dbd3323ef03b334b08d5be980000e9c7ee3f0ac3e3bcd42c4e"
EXPECTED_SKILL_COUNT = 196
EXPECTED_FOUNDATION_COUNT = 100
EXPECTED_COMMERCIAL_COUNT = 96
EXPECTED_BATCH_COUNT = 22
EXPECTED_DEPENDENCY_EDGES = 128
EXPECTED_FOUNDATION_CRITICAL_EDGES = 21
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

_MANIFEST_KEYS = {
    "archive_code_execution",
    "batch_count",
    "canonical_source",
    "certification",
    "commercial_skill_count",
    "compiled_contracts_path",
    "compiled_contracts_sha256",
    "contract_count",
    "customer_evidence_status",
    "dependency_edge_count",
    "external_evidence_status",
    "foundation_checksum_entries",
    "foundation_critical_dependency_edge_count",
    "foundation_skill_count",
    "implementation_state",
    "installed_namespace",
    "outer_checksum_entries",
    "outer_checksum_sha256",
    "package",
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
    "certification",
    "contract_count",
    "contracts",
    "customer_evidence_status",
    "dependency_edge_count",
    "external_evidence_status",
    "foundation_critical_dependency_edge_count",
    "implementation_state",
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


@dataclass(frozen=True, slots=True)
class SkillContract:
    name: str
    source_id: str
    batch: str
    origin: str
    description: str
    dependencies: tuple[str, ...]
    required_outputs: tuple[str, ...]
    source_contract_sha256: str
    source_skill_sha256: str
    data: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return copy.deepcopy(dict(self.data))


@dataclass(frozen=True, slots=True)
class Catalog:
    repository_root: Path
    manifest_path: Path
    contracts_path: Path
    source_archive_sha256: str
    compiled_contracts_sha256: str
    topological_order: tuple[str, ...]
    contracts: Mapping[str, SkillContract]

    @property
    def skill_count(self) -> int:
        return len(self.contracts)


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
    try:
        value = parse_json_strict(
            path.read_bytes(),
            max_bytes=2_000_000,
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
        compiled["foundation_critical_dependency_edge_count"],
        EXPECTED_FOUNDATION_CRITICAL_EDGES,
        "compiled.foundation_critical_dependency_edge_count",
    )

    compiled_digest = _sha256(contracts_path)
    if _digest(manifest["compiled_contracts_sha256"], "manifest.compiled_contracts_sha256") != compiled_digest:
        _fail("compiled contracts digest does not match the manifest")
    expected_contracts_path = "docs/spring-golden-route-commercial-skills/compiled-contracts.json"
    if manifest["compiled_contracts_path"] != expected_contracts_path:
        _fail("compiled contracts path is not canonical")

    topological_order = _string_list(manifest["topological_order"], "manifest.topological_order")
    compiled_order = _string_list(compiled["topological_order"], "compiled.topological_order")
    if topological_order != compiled_order or len(topological_order) != EXPECTED_SKILL_COUNT:
        _fail("topological orders do not identify the same 196 Skills")

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
        batches.add(batch)
        dependencies = _string_list(contract["dependencies"], f"compiled.contracts[{index}].dependencies")
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
            "source_id": contract["source_id"],
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
            source_id=_string(contract["source_id"], f"compiled.contracts[{index}].source_id"),
            batch=batch,
            origin=origin,
            description=_string(contract["description"], f"compiled.contracts[{index}].description"),
            dependencies=tuple(dependencies),
            required_outputs=tuple(required_outputs),
            source_contract_sha256=source_contract_sha256,
            source_skill_sha256=source_skill_sha256,
            data=MappingProxyType(copy.deepcopy(contract)),
        )

    if origins != {"foundation": EXPECTED_FOUNDATION_COUNT, "commercial-extension": EXPECTED_COMMERCIAL_COUNT}:
        _fail("foundation/commercial Skill totals are invalid", actual=origins)
    if len(batches) != EXPECTED_BATCH_COUNT:
        _fail("batch total is invalid", actual=len(batches))
    if set(topological_order) != set(contracts) or set(skills) != set(contracts):
        _fail("catalog name sets do not match the topological order")
    edge_count = sum(len(contract.dependencies) for contract in contracts.values())
    if edge_count != EXPECTED_DEPENDENCY_EDGES:
        _fail("derived dependency edge count is invalid", actual=edge_count)
    positions = {name: index for index, name in enumerate(topological_order)}
    for name, contract in contracts.items():
        for dependency in contract.dependencies:
            if dependency not in positions:
                _fail("dependency names an unknown Skill", name=name, dependency=dependency)
            if positions[dependency] >= positions[name]:
                _fail("topological order violates dependency DAG", name=name, dependency=dependency)

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
            for suffix in (
                Path("SKILL.md"),
                Path("agents/openai.yaml"),
                Path("references/contract.json"),
                Path("schemas/skill-contract.schema.json"),
            ):
                if (runtime_skill.parent / suffix).read_bytes() != (workspace_skill.parent / suffix).read_bytes():
                    _fail("dual-root installed Skill drift", name=name, path=str(suffix))

    return Catalog(
        repository_root=root,
        manifest_path=manifest_path,
        contracts_path=contracts_path,
        source_archive_sha256=SOURCE_ARCHIVE_SHA256,
        compiled_contracts_sha256=compiled_digest,
        topological_order=tuple(topological_order),
        contracts=MappingProxyType(contracts),
    )
