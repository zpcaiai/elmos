#!/usr/bin/env python3
"""Safely import the Spring Golden Route v2 Skill specification ZIP.

The archive is data, never executable input.  This importer validates its
content-addressed inventory and emits normalized Codex Skill interfaces.  It
does not run the bundled installers, scripts, tests, migrations, or gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import skill_creator_tools
import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-spring-golden-route-commercial-skills-v2.0.0"
ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
# Kept for integration-test/API compatibility: the ZIP is the sole source.
PACKAGE_RELATIVE = ARCHIVE_RELATIVE
RUNTIME_RELATIVE = Path("agent-skills/runtime")
WORKSPACE_RELATIVE = Path(".agents/skills")
DOC_RELATIVE = Path("docs/spring-golden-route-commercial-skills")
RUNTIME_ENGINE_RELATIVE = Path("engines/spring-golden-route-engine")
RUNTIME_MODULE = "elmos_spring_golden_route.runtime"
RUNTIME_DISPATCHER = "dispatch_skill"

PACKAGE_NAME = "elmos-spring-golden-route-commercial-skills"
PACKAGE_VERSION = "2.0.0"
NAMESPACE = "spring-golden-route-commercial-v2"
EXPECTED_ARCHIVE_SHA256 = (
    "952dce43681a56dbd3323ef03b334b08d5be980000e9c7ee3f0ac3e3bcd42c4e"
)
EXPECTED_ARCHIVE_BYTES = 1_228_281
EXPECTED_ARCHIVE_ENTRY_COUNT = 596
EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES = 2_127_024
EXPECTED_MODE_COUNTS = {0o644: 587, 0o755: 9}
EXPECTED_OUTER_CHECKSUM_SHA256 = (
    "18a3e8d9ffaa20a6ba4b33b987578fe5323bf497625eed468ebda0612dad50bf"
)
EXPECTED_OUTER_CHECKSUM_ENTRIES = 594
EXPECTED_FOUNDATION_CHECKSUM_ENTRIES = 130
EXPECTED_SKILLS = 196
EXPECTED_FOUNDATION_SKILLS = 100
EXPECTED_COMMERCIAL_SKILLS = 96
EXPECTED_CONTRACTS = 196
EXPECTED_BATCHES = 22
EXPECTED_DEPENDENCY_EDGES = 128
EXPECTED_FOUNDATION_CRITICAL_EDGES = 21
MAX_ARCHIVE_ENTRY_BYTES = 512 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 4 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100

OUTER_CHECKSUM = "SHA256SUMS.txt"
FOUNDATION_ROOT = "foundation/openrewrite-opencode-v1.0"
FOUNDATION_CHECKSUM = f"{FOUNDATION_ROOT}/SHA256SUMS.txt"
QUARANTINED_SUFFIXES = (".pyc",)
QUARANTINED_PARTS = {"__pycache__"}
EXAMPLE_SCHEMA_PAIRS = {
    "examples/repository-profile.json": "schemas/repository-profile.schema.json",
    "examples/eligibility-report.json": "schemas/eligibility-report.schema.json",
    "examples/target-profile.json": "schemas/target-profile.schema.json",
    "examples/evidence-manifest.json": "schemas/evidence-manifest.schema.json",
    "examples/completion-proof.json": "schemas/completion-proof.schema.json",
    "examples/benchmark-claim-valid.json": "schemas/benchmark-claim.schema.json",
    "examples/benchmark-claim-invalid.json": "schemas/benchmark-claim.schema.json",
    "examples/pricing-quote.json": "schemas/pricing-quote.schema.json",
}


class IntegrationError(RuntimeError):
    """Fail-closed archive or generated-install validation error."""


@dataclass(frozen=True)
class ArchiveRecord:
    archive_name: str
    relative: str
    data: bytes
    size: int
    compressed_size: int
    mode: int
    sha256: str


@dataclass(frozen=True)
class FilePayload:
    data: bytes
    mode: int = 0o644


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrationError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _safe_relative(value: str, label: str) -> PurePosixPath:
    _require(value != "" and "\\" not in value and "\x00" not in value, f"unsafe {label}: {value!r}")
    path = PurePosixPath(value)
    _require(not path.is_absolute(), f"absolute {label}: {value}")
    _require(all(part not in {"", ".", ".."} for part in path.parts), f"escaping {label}: {value}")
    _require(path.as_posix() == value, f"non-canonical {label}: {value}")
    return path


def inspect_archive(
    archive: Path,
    *,
    trusted_sha256: str | None = EXPECTED_ARCHIVE_SHA256,
    expected_entry_count: int | None = EXPECTED_ARCHIVE_ENTRY_COUNT,
    expected_total_bytes: int | None = EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES,
    expected_mode_counts: dict[int, int] | None = EXPECTED_MODE_COUNTS,
    expected_root: str = PACKAGE_DIRECTORY,
    max_entry_bytes: int = MAX_ARCHIVE_ENTRY_BYTES,
    max_total_bytes: int = MAX_ARCHIVE_TOTAL_BYTES,
    max_compression_ratio: int = MAX_COMPRESSION_RATIO,
) -> dict[str, ArchiveRecord]:
    """Read a ZIP only after validating bounded regular-file entries."""

    _require(archive.is_file() and not archive.is_symlink(), f"archive is missing or unsafe: {archive}")
    raw_archive = archive.read_bytes()
    if trusted_sha256 is not None:
        _require(_sha256(raw_archive) == trusted_sha256, "archive SHA-256 mismatch")
    if trusted_sha256 == EXPECTED_ARCHIVE_SHA256:
        _require(len(raw_archive) == EXPECTED_ARCHIVE_BYTES, "archive byte count mismatch")

    records: dict[str, ArchiveRecord] = {}
    folded: set[str] = set()
    total = 0
    modes: Counter[int] = Counter()
    prefix = expected_root + "/"
    try:
        handle = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise IntegrationError(f"invalid ZIP archive: {exc}") from exc
    with handle:
        infos = handle.infolist()
        if expected_entry_count is not None:
            _require(len(infos) == expected_entry_count, "archive entry count mismatch")
        for info in infos:
            _require(not (info.flag_bits & 0x1), f"encrypted ZIP entry: {info.filename}")
            _require(not info.is_dir(), f"directory entry is not allowed: {info.filename}")
            _require(info.filename.startswith(prefix), f"unexpected archive root: {info.filename}")
            _safe_relative(info.filename, "archive path")
            relative = info.filename[len(prefix) :]
            _safe_relative(relative, "archive member")
            _require(relative not in records, f"duplicate ZIP entry: {relative}")
            folded_name = relative.casefold()
            _require(folded_name not in folded, f"case-folded ZIP collision: {relative}")
            folded.add(folded_name)

            unix_mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(unix_mode)
            _require(file_type in {0, stat.S_IFREG}, f"non-regular ZIP entry: {relative}")
            mode = stat.S_IMODE(unix_mode) or 0o644
            _require(mode in {0o644, 0o755}, f"unsafe ZIP mode {oct(mode)}: {relative}")
            _require(0 <= info.file_size <= max_entry_bytes, f"oversized ZIP entry: {relative}")
            if info.file_size:
                _require(info.compress_size > 0, f"invalid compression size: {relative}")
                _require(
                    info.file_size / info.compress_size <= max_compression_ratio,
                    f"excessive compression ratio: {relative}",
                )
            total += info.file_size
            _require(total <= max_total_bytes, "archive exceeds total uncompressed limit")
            try:
                data = handle.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise IntegrationError(f"cannot read ZIP entry {relative}: {exc}") from exc
            _require(len(data) == info.file_size, f"ZIP entry size mismatch: {relative}")
            modes[mode] += 1
            records[relative] = ArchiveRecord(
                archive_name=info.filename,
                relative=relative,
                data=data,
                size=info.file_size,
                compressed_size=info.compress_size,
                mode=mode,
                sha256=_sha256(data),
            )
    if expected_total_bytes is not None:
        _require(total == expected_total_bytes, "archive uncompressed byte count mismatch")
    if expected_mode_counts is not None:
        _require(dict(modes) == expected_mode_counts, "archive file-mode inventory mismatch")
    return records


def _parse_checksums(data: bytes, label: str) -> dict[str, str]:
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise IntegrationError(f"{label} is not UTF-8") from exc
    result: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})\s+\*?(.+)", line)
        _require(match is not None, f"invalid {label} line {number}")
        digest, relative = match.groups()
        _safe_relative(relative, f"{label} path")
        _require(relative not in result, f"duplicate {label} path: {relative}")
        result[relative] = digest
    return result


def _validate_checksums(records: dict[str, ArchiveRecord]) -> tuple[dict[str, str], dict[str, str]]:
    _require(OUTER_CHECKSUM in records and FOUNDATION_CHECKSUM in records, "checksum ledger is missing")
    outer_record = records[OUTER_CHECKSUM]
    _require(outer_record.sha256 == EXPECTED_OUTER_CHECKSUM_SHA256, "outer checksum-ledger digest mismatch")
    outer = _parse_checksums(outer_record.data, "outer checksum ledger")
    _require(len(outer) == EXPECTED_OUTER_CHECKSUM_ENTRIES, "outer checksum entry count mismatch")
    expected_outer = set(records) - {OUTER_CHECKSUM, FOUNDATION_CHECKSUM}
    _require(set(outer) == expected_outer, "outer checksum inventory mismatch")
    for relative, digest in outer.items():
        _require(records[relative].sha256 == digest, f"outer checksum mismatch: {relative}")

    nested = _parse_checksums(records[FOUNDATION_CHECKSUM].data, "foundation checksum ledger")
    _require(len(nested) == EXPECTED_FOUNDATION_CHECKSUM_ENTRIES, "foundation checksum entry count mismatch")
    prefix = FOUNDATION_ROOT + "/"
    actual_nested = {
        relative[len(prefix) :]
        for relative in records
        if relative.startswith(prefix) and relative != FOUNDATION_CHECKSUM
    }
    _require(set(nested) == actual_nested, "foundation checksum inventory mismatch")
    for relative, digest in nested.items():
        _require(records[f"{prefix}{relative}"].sha256 == digest, f"foundation checksum mismatch: {relative}")
    return outer, nested


def _load_json_record(records: dict[str, ArchiveRecord], relative: str) -> Any:
    _require(relative in records, f"missing JSON file: {relative}")
    try:
        return json.loads(records[relative].data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrationError(f"invalid JSON file {relative}: {exc}") from exc


def _frontmatter(data: bytes, relative: str) -> tuple[dict[str, Any], str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntegrationError(f"Skill is not UTF-8: {relative}") from exc
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    _require(match is not None, f"invalid Skill frontmatter: {relative}")
    try:
        value = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise IntegrationError(f"invalid Skill YAML: {relative}: {exc}") from exc
    _require(isinstance(value, dict), f"Skill frontmatter is not an object: {relative}")
    return value, text[match.end() :].lstrip("\n")


def _assert_dag(graph: dict[str, list[str]], known: set[str], label: str) -> list[str]:
    for node, dependencies in graph.items():
        _require(node in known, f"unknown {label} node: {node}")
        _require(isinstance(dependencies, list), f"invalid {label} dependencies: {node}")
        _require(len(dependencies) == len(set(dependencies)), f"duplicate {label} dependency: {node}")
        _require(node not in dependencies, f"self {label} dependency: {node}")
        _require(set(dependencies) <= known, f"unknown {label} dependency: {node}")
    order: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise IntegrationError(f"{label} dependency cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, []):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)
        order.append(node)

    for node in graph:
        visit(node)
    return order


def validate_source(source: Path | dict[str, ArchiveRecord]) -> dict[str, Any]:
    """Validate checksums, Skills, contracts, Schemas, and dependency graphs."""

    records = inspect_archive(source) if isinstance(source, Path) else source
    outer, nested = _validate_checksums(records)
    manifest = _load_json_record(records, "manifest/package.json")
    _require(manifest.get("package") == PACKAGE_NAME, "package identity mismatch")
    _require(manifest.get("version") == PACKAGE_VERSION, "package version mismatch")
    _require(manifest.get("skill_count") == EXPECTED_SKILLS, "declared Skill count mismatch")
    _require(manifest.get("commercial_extension_skill_count") == EXPECTED_COMMERCIAL_SKILLS, "commercial Skill count mismatch")
    _require(manifest.get("batch_count") == EXPECTED_BATCHES, "batch count mismatch")
    skills = manifest.get("skills")
    _require(isinstance(skills, list) and len(skills) == EXPECTED_SKILLS, "Skill manifest inventory mismatch")
    _require(all(isinstance(entry, dict) for entry in skills), "invalid Skill manifest entry")
    names = [entry.get("name") for entry in skills]
    identifiers = [entry.get("id") for entry in skills]
    _require(all(isinstance(name, str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) and len(name) <= 64 for name in names), "invalid Skill name")
    _require(len(set(names)) == EXPECTED_SKILLS and len(set(identifiers)) == EXPECTED_SKILLS, "duplicate Skill name or id")
    origin_counts = Counter(entry.get("origin") for entry in skills)
    _require(origin_counts == {"foundation": EXPECTED_FOUNDATION_SKILLS, "commercial-extension": EXPECTED_COMMERCIAL_SKILLS}, "Skill origin inventory mismatch")

    contract_paths = {relative for relative in records if relative.startswith("contracts/") and relative.endswith(".json")}
    _require(len(contract_paths) == EXPECTED_CONTRACTS, "contract inventory count mismatch")
    contract_schema = _load_json_record(records, "schemas/skill-contract.schema.json")
    try:
        Draft202012Validator.check_schema(contract_schema)
    except SchemaError as exc:
        raise IntegrationError(f"invalid contract Schema: {exc.message}") from exc
    validator = Draft202012Validator(contract_schema)
    skill_records: list[dict[str, Any]] = []
    name_set = set(names)
    for entry in skills:
        name = entry["name"]
        skill_path = entry.get("path")
        _require(skill_path == f"skills/{name}/SKILL.md", f"Skill path mismatch: {name}")
        _require(skill_path in records, f"Skill file missing: {name}")
        frontmatter, body = _frontmatter(records[skill_path].data, skill_path)
        _require(frontmatter.get("name") == name, f"Skill frontmatter name mismatch: {name}")
        _require(isinstance(frontmatter.get("description"), str) and frontmatter["description"].strip(), f"Skill description missing: {name}")
        contract_path = f"contracts/{name}.json"
        _require(contract_path in contract_paths, f"Skill contract missing: {name}")
        contract = _load_json_record(records, contract_path)
        errors = sorted(validator.iter_errors(contract), key=lambda error: list(error.path))
        _require(not errors, f"contract Schema failure {name}: {errors[0].message if errors else ''}")
        for key in (
            "id",
            "name",
            "title",
            "description",
            "batch",
            "batch_slug",
            "priority",
            "risk",
            "path",
            "origin",
            "sources",
        ):
            _require(contract.get(key) == entry.get(key), f"contract/manifest {key} mismatch: {name}")
        dependencies = list(entry.get("dependencies", []))
        outputs = list(entry.get("outputs", []))
        _require(contract.get("dependencies", []) == dependencies, f"contract dependency mismatch: {name}")
        _require(contract.get("outputs", []) == outputs, f"contract output mismatch: {name}")
        skill_records.append(
            {
                "entry": entry,
                "frontmatter": frontmatter,
                "body": body,
                "contract": contract,
                "skill_sha256": records[skill_path].sha256,
                "contract_sha256": records[contract_path].sha256,
                "contract_bytes": records[contract_path].data,
            }
        )

    for example, schema_path in EXAMPLE_SCHEMA_PAIRS.items():
        _require(example in records and schema_path in records, f"required example/schema missing: {example}")
        example_value = _load_json_record(records, example)
        schema_value = _load_json_record(records, schema_path)
        try:
            Draft202012Validator.check_schema(schema_value)
        except SchemaError as exc:
            raise IntegrationError(f"invalid JSON Schema {schema_path}: {exc.message}") from exc
        errors = list(Draft202012Validator(schema_value).iter_errors(example_value))
        # The package labels one fixture semantically invalid, but its published
        # JSON Schema intentionally admits that shape.  Import-time validation
        # therefore checks structure only; the bundled semantic validator is
        # untrusted input and is never treated as certification authority.
        _require(not errors, f"example Schema failure {example}: {errors[0].message if errors else ''}")

    dependency_manifest = _load_json_record(records, "manifest/dependency-graph.json")
    commercial_graph = dependency_manifest.get("skill_dependencies")
    _require(isinstance(commercial_graph, dict), "commercial dependency graph missing")
    manifest_graph = {entry["name"]: list(entry.get("dependencies", [])) for entry in skills}
    commercial_names = {
        entry["name"] for entry in skills if entry.get("origin") == "commercial-extension"
    }
    _require(set(commercial_graph) <= commercial_names, "unknown commercial graph node")
    for entry in skills:
        if entry.get("origin") == "commercial-extension":
            _require(commercial_graph.get(entry["name"], []) == manifest_graph[entry["name"]], f"commercial graph mismatch: {entry['name']}")
    edge_count = sum(len(value) for value in manifest_graph.values())
    _require(edge_count == EXPECTED_DEPENDENCY_EDGES, "manifest dependency edge count mismatch")
    topological_order = _assert_dag(manifest_graph, name_set, "Skill")

    foundation_graph_value = _load_json_record(records, f"{FOUNDATION_ROOT}/manifest/dependency-graph.json")
    foundation_graph = foundation_graph_value.get("critical_skill_dependencies")
    _require(isinstance(foundation_graph, dict), "foundation critical dependency graph missing")
    foundation_edges = sum(len(value) for value in foundation_graph.values())
    _require(foundation_edges == EXPECTED_FOUNDATION_CRITICAL_EDGES, "foundation critical edge count mismatch")
    foundation_known = {entry["name"] for entry in skills if entry.get("origin") == "foundation"}
    _require(set(foundation_graph) <= foundation_known, "unknown foundation graph node")
    _assert_dag({name: list(foundation_graph.get(name, [])) for name in foundation_known}, foundation_known, "foundation Skill")

    commercial_batches = dependency_manifest.get("batch_dependencies")
    _require(isinstance(commercial_batches, dict), "commercial batch graph missing")
    _assert_dag({str(key): list(value) for key, value in commercial_batches.items()}, set(map(str, commercial_batches)), "commercial batch")
    foundation_batches = foundation_graph_value.get("batch_dependencies")
    _require(isinstance(foundation_batches, dict), "foundation batch graph missing")
    _assert_dag({str(key): list(value) for key, value in foundation_batches.items()}, set(map(str, foundation_batches)), "foundation batch")

    return {
        "records": records,
        "outer_checksums": outer,
        "foundation_checksums": nested,
        "manifest": manifest,
        "skills": skill_records,
        "skill_count": len(skills),
        "contract_count": len(contract_paths),
        "dependency_edge_count": edge_count,
        "foundation_critical_dependency_edge_count": foundation_edges,
        "topological_order": topological_order,
    }


def _normalized_skill(record: dict[str, Any]) -> bytes:
    entry = record["entry"]
    source_frontmatter = record["frontmatter"]
    name = entry["name"]
    # Codex Skill descriptions reject ASCII angle brackets. Preserve the
    # source wording while rendering comparison signs as their full-width
    # Unicode equivalents; source bytes and digests remain independently bound.
    description = (
        source_frontmatter["description"].strip().replace("<", "＜").replace(">", "＞")
    )
    description += " Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence."
    metadata = dict(source_frontmatter.get("metadata") or {})
    if source_frontmatter.get("compatibility") is not None:
        metadata["source_compatibility"] = source_frontmatter["compatibility"]
    metadata.update(
        {
            "source_package": PACKAGE_NAME,
            "source_version": PACKAGE_VERSION,
            "source_id": entry["id"],
            "source_name": name,
            "source_path": entry["path"],
            "source_sha256": "sha256:" + record["skill_sha256"],
            "source_contract_sha256": "sha256:" + record["contract_sha256"],
            "source_origin": entry["origin"],
            "installed_namespace": NAMESPACE,
            "implementation_state": "SPECIFICATION_IMPORTED",
            "runtime_evidence_status": "NOT_RUN",
            "customer_evidence_status": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "side_effects_authorized": False,
        }
    )
    if name == "spring-route-orchestrator":
        metadata.update(
            {
                "dependency_graph_role": "entrypoint-with-downstream-successors",
                "runtime_dependency_closure_status": "NOT_IMPLEMENTED",
                "planning_preview_state": "DRAFT_ONLY",
            }
        )
    frontmatter: dict[str, Any] = {"name": name, "description": description}
    if source_frontmatter.get("license") is not None:
        frontmatter["license"] = source_frontmatter["license"]
    frontmatter["metadata"] = metadata
    rendered = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False, width=1000).rstrip()
    binding_lines = [
        "## Repository import binding",
        "",
        f"- Machine contract: `references/contract.json` (`sha256:{record['contract_sha256']}`).",
        "- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.",
        "- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.",
    ]
    if name == "spring-route-orchestrator":
        binding_lines.extend(
            [
                "- The source `dependencies` array records prerequisite order, not a complete executable closure; downstream phase Skills remain visible only in `docs/spring-golden-route-commercial-skills/installed-manifest.json`.",
                "- Until exact runtime dependencies and a typed preview contract are implemented, assessment-only responses must be labeled `DRAFT_ONLY`; required execution outputs remain absent and every execution phase remains `NOT_RUN`.",
            ]
        )
    binding = "\n".join(binding_lines)
    body = record["body"].rstrip()
    return f"---\n{rendered}\n---\n\n{body}\n\n{binding}\n".encode("utf-8")


def _interface(name: str) -> bytes:
    display = skill_creator_tools.format_display_name(name)
    short = "Run this Spring Golden Route v2 Skill safely"
    prompt = f"Use ${name} for its exact imported contract; keep runtime evidence NOT_RUN unless independently executed."
    return (
        "\n".join(
            [
                "interface:",
                f"  display_name: {skill_creator_tools.yaml_quote(display)}",
                f"  short_description: {skill_creator_tools.yaml_quote(short)}",
                f"  default_prompt: {skill_creator_tools.yaml_quote(prompt)}",
                "",
            ]
        )
    ).encode("utf-8")


def _runtime_binding(record: dict[str, Any]) -> bytes:
    entry = record["entry"]
    return _json_bytes(
        {
            "schema_version": "elmos.spring-golden-route.runtime-binding.v1",
            "skill_name": entry["name"],
            "source_id": entry["id"],
            "source_contract_sha256": "sha256:" + record["contract_sha256"],
            "engine_path": RUNTIME_ENGINE_RELATIVE.as_posix(),
            "module_path": RUNTIME_MODULE,
            "dispatcher": RUNTIME_DISPATCHER,
            "supported_operations": ["describe", "plan"],
            "binding_state": "BOUNDED_LOCAL_CONTROL_PLANE_IMPLEMENTED",
            "control_plane_evidence_status": "LOCAL_EXECUTED_SELF_ATTESTED",
            "domain_runtime_evidence_status": "NOT_RUN",
            "customer_evidence_status": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "side_effects_authorized": False,
        }
    )


def build_expected(summary: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    """Build deterministic repository outputs without writing them."""

    del root  # paths are repository-relative by design
    files: dict[Path, FilePayload] = {}
    installed: list[dict[str, Any]] = []
    compiled: list[dict[str, Any]] = []
    runtime_bindings: list[dict[str, Any]] = []
    for record in summary["skills"]:
        entry = record["entry"]
        name = entry["name"]
        skill_bytes = _normalized_skill(record)
        interface_bytes = _interface(name)
        contract_bytes = record["contract_bytes"]
        contract_schema_bytes = summary["records"]["schemas/skill-contract.schema.json"].data
        runtime_binding_bytes = _runtime_binding(record)
        for base in (RUNTIME_RELATIVE, WORKSPACE_RELATIVE):
            skill_root = base / name
            files[skill_root / "SKILL.md"] = FilePayload(skill_bytes)
            files[skill_root / "agents/openai.yaml"] = FilePayload(interface_bytes)
            files[skill_root / "references/contract.json"] = FilePayload(contract_bytes)
            files[skill_root / "schemas/skill-contract.schema.json"] = FilePayload(
                contract_schema_bytes
            )
            files[skill_root / "references/runtime-binding.json"] = FilePayload(
                runtime_binding_bytes
            )
        installed.append(
            {
                "source_id": entry["id"],
                "source_name": name,
                "source_batch": entry["batch"],
                "source_origin": entry["origin"],
                "source_path": entry["path"],
                "source_sha256": "sha256:" + record["skill_sha256"],
                "source_contract_path": f"contracts/{name}.json",
                "source_contract_sha256": "sha256:" + record["contract_sha256"],
                "installed_name": name,
                "runtime_path": (RUNTIME_RELATIVE / name / "SKILL.md").as_posix(),
                "workspace_path": (WORKSPACE_RELATIVE / name / "SKILL.md").as_posix(),
                "installed_sha256": "sha256:" + _sha256(skill_bytes),
                "interface_sha256": "sha256:" + _sha256(interface_bytes),
                "dependencies": list(entry.get("dependencies", [])),
                "required_outputs": list(entry.get("outputs", [])),
                "implementation_state": "SPECIFICATION_IMPORTED",
                "runtime_evidence_status": "NOT_RUN",
                "customer_evidence_status": "NOT_RUN",
                "external_evidence_status": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
                "side_effects_authorized": False,
            }
        )
        compiled.append(
            {
                "source_id": entry["id"],
                "name": name,
                "batch": entry["batch"],
                "origin": entry["origin"],
                "priority": entry["priority"],
                "risk": entry["risk"],
                "description": entry["description"],
                "dependencies": list(entry.get("dependencies", [])),
                "required_outputs": list(entry.get("outputs", [])),
                "permissions": record["contract"].get("permissions", {}),
                "tests": record["contract"].get("tests", []),
                "evidence": record["contract"].get("evidence", []),
                "stop_conditions": record["contract"].get("stop_conditions", []),
                "definition_of_done": record["contract"].get("definition_of_done", []),
                "production_claim_boundary": record["contract"].get("production_claim_boundary"),
                "source_skill_sha256": "sha256:" + record["skill_sha256"],
                "source_contract_sha256": "sha256:" + record["contract_sha256"],
                "implementation_state": "SPECIFICATION_IMPORTED",
                "runtime_evidence_status": "NOT_RUN",
                "customer_evidence_status": "NOT_RUN",
                "external_evidence_status": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
                "side_effects_authorized": False,
            }
        )
        runtime_bindings.append(json.loads(runtime_binding_bytes.decode("utf-8")))

    compiled_value = {
        "schema_version": "elmos.spring-golden-route.compiled-contracts.v1",
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "source_archive_sha256": "sha256:" + EXPECTED_ARCHIVE_SHA256,
        "skill_count": EXPECTED_SKILLS,
        "contract_count": EXPECTED_CONTRACTS,
        "dependency_edge_count": summary["dependency_edge_count"],
        "foundation_critical_dependency_edge_count": summary["foundation_critical_dependency_edge_count"],
        "topological_order": summary["topological_order"],
        "implementation_state": "SPECIFICATION_IMPORTED",
        "runtime_evidence_status": "NOT_RUN",
        "customer_evidence_status": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "side_effects_authorized": False,
        "contracts": compiled,
    }
    compiled_bytes = _json_bytes(compiled_value)
    files[DOC_RELATIVE / "compiled-contracts.json"] = FilePayload(compiled_bytes)

    quarantine = sorted(
        relative
        for relative in summary["records"]
        if relative.endswith(QUARANTINED_SUFFIXES)
        or QUARANTINED_PARTS.intersection(PurePosixPath(relative).parts)
    )
    manifest_value = {
        "schema_version": "elmos.spring-golden-route.installed-manifest.v1",
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "installed_namespace": NAMESPACE,
        "canonical_source": ARCHIVE_RELATIVE.as_posix(),
        "source_archive_sha256": "sha256:" + EXPECTED_ARCHIVE_SHA256,
        "source_archive_bytes": EXPECTED_ARCHIVE_BYTES,
        "source_archive_entries": EXPECTED_ARCHIVE_ENTRY_COUNT,
        "source_archive_uncompressed_bytes": EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES,
        "outer_checksum_sha256": "sha256:" + EXPECTED_OUTER_CHECKSUM_SHA256,
        "outer_checksum_entries": EXPECTED_OUTER_CHECKSUM_ENTRIES,
        "foundation_checksum_entries": EXPECTED_FOUNDATION_CHECKSUM_ENTRIES,
        "skill_count": EXPECTED_SKILLS,
        "foundation_skill_count": EXPECTED_FOUNDATION_SKILLS,
        "commercial_skill_count": EXPECTED_COMMERCIAL_SKILLS,
        "contract_count": EXPECTED_CONTRACTS,
        "batch_count": EXPECTED_BATCHES,
        "dependency_edge_count": summary["dependency_edge_count"],
        "foundation_critical_dependency_edge_count": summary["foundation_critical_dependency_edge_count"],
        "topological_order": summary["topological_order"],
        "compiled_contracts_path": (DOC_RELATIVE / "compiled-contracts.json").as_posix(),
        "compiled_contracts_sha256": "sha256:" + _sha256(compiled_bytes),
        "archive_code_execution": "DENIED",
        "quarantined_archive_members": quarantine,
        "implementation_state": "SPECIFICATION_IMPORTED",
        "runtime_evidence_status": "NOT_RUN",
        "customer_evidence_status": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "side_effects_authorized": False,
        "skills": installed,
    }
    manifest_bytes = _json_bytes(manifest_value)
    files[DOC_RELATIVE / "installed-manifest.json"] = FilePayload(manifest_bytes)
    runtime_registry_value = {
        "schema_version": "elmos.spring-golden-route.runtime-registry.v1",
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "source_archive_sha256": "sha256:" + EXPECTED_ARCHIVE_SHA256,
        "engine_path": RUNTIME_ENGINE_RELATIVE.as_posix(),
        "module_path": RUNTIME_MODULE,
        "dispatcher": RUNTIME_DISPATCHER,
        "skill_count": EXPECTED_SKILLS,
        "binding_state": "BOUNDED_LOCAL_CONTROL_PLANE_IMPLEMENTED",
        "control_plane_evidence_status": "LOCAL_EXECUTED_SELF_ATTESTED",
        "domain_runtime_evidence_status": "NOT_RUN",
        "customer_evidence_status": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "side_effects_authorized": False,
        "bindings": runtime_bindings,
    }
    files[DOC_RELATIVE / "runtime-registry.json"] = FilePayload(
        _json_bytes(runtime_registry_value)
    )
    return {
        "files": files,
        "manifest": manifest_value,
        "compiled_contracts": compiled_value,
        "runtime_registry": runtime_registry_value,
        "skill_names": [entry["installed_name"] for entry in installed],
    }


def _read_tree(root: Path, relative: Path) -> dict[str, bytes]:
    _assert_safe_parent_chain(root, relative)
    base = root / relative
    if not base.exists():
        return {}
    _require(base.is_dir() and not base.is_symlink(), f"unsafe generated directory: {relative}")
    result: dict[str, bytes] = {}
    for path in sorted(base.rglob("*")):
        _require(not path.is_symlink(), f"symlink in generated directory: {path}")
        if path.is_file():
            result[path.relative_to(base).as_posix()] = path.read_bytes()
    return result


def _repository_root(root: Path) -> Path:
    candidate = root.expanduser().absolute()
    _require(
        candidate.exists() and candidate.is_dir() and not candidate.is_symlink(),
        f"repository root is missing or unsafe: {candidate}",
    )
    return candidate


def _assert_safe_parent_chain(root: Path, relative: Path) -> None:
    _require(not relative.is_absolute() and ".." not in relative.parts, f"unsafe destination: {relative}")
    cursor = root
    for part in relative.parts[:-1]:
        cursor /= part
        _require(not cursor.is_symlink(), f"symlink in destination path: {cursor}")
        if cursor.exists():
            _require(cursor.is_dir(), f"non-directory in destination path: {cursor}")


def _preflight(root: Path, expected: dict[str, Any]) -> None:
    files: dict[Path, FilePayload] = expected["files"]
    for name in expected["skill_names"]:
        allowed = {
            "SKILL.md",
            "agents/openai.yaml",
            "references/contract.json",
            "references/runtime-binding.json",
            "schemas/skill-contract.schema.json",
        }
        for base in (RUNTIME_RELATIVE, WORKSPACE_RELATIVE):
            current = _read_tree(root, base / name)
            _require(set(current) <= allowed, f"unmanaged files in destination Skill: {base / name}")
    for relative, payload in files.items():
        _assert_safe_parent_chain(root, relative)
        target = root / relative
        if target.exists() or target.is_symlink():
            _require(target.is_file() and not target.is_symlink(), f"unsafe destination: {relative}")
            _require(target.read_bytes() == payload.data, f"refusing to overwrite different destination: {relative}")
            _require(
                stat.S_IMODE(target.stat().st_mode) == payload.mode,
                f"generated destination mode mismatch: {relative}",
            )


def _write_atomic(path: Path, payload: FilePayload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload.data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, payload.mode)
        try:
            # Publish through an exclusive hard link so a destination created
            # after preflight is never overwritten by a TOCTOU race.
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise IntegrationError(f"destination appeared during write: {path}") from exc
        except OSError as exc:
            raise IntegrationError(f"cannot publish generated destination {path}: {exc}") from exc
        temporary.unlink()
    finally:
        if temporary.exists():
            temporary.unlink()


def write_install(root: Path, expected: dict[str, Any]) -> dict[str, Any]:
    root = _repository_root(root)
    _preflight(root, expected)
    for relative, payload in expected["files"].items():
        target = root / relative
        if not target.exists():
            _assert_safe_parent_chain(root, relative)
            _write_atomic(target, payload)
    return check_install(root, expected)


def check_install(root: Path, expected: dict[str, Any]) -> dict[str, Any]:
    root = _repository_root(root)
    _preflight(root, expected)
    files: dict[Path, FilePayload] = expected["files"]
    missing = [relative.as_posix() for relative in files if not (root / relative).is_file()]
    _require(not missing, f"generated files are missing: {missing[:5]}")
    for name in expected["skill_names"]:
        for base in (RUNTIME_RELATIVE, WORKSPACE_RELATIVE):
            actual = _read_tree(root, base / name)
            _require(
                set(actual)
                == {
                    "SKILL.md",
                    "agents/openai.yaml",
                    "references/contract.json",
                    "references/runtime-binding.json",
                    "schemas/skill-contract.schema.json",
                },
                f"installed Skill inventory mismatch: {base / name}",
            )
        _require(
            _read_tree(root, RUNTIME_RELATIVE / name)
            == _read_tree(root, WORKSPACE_RELATIVE / name),
            f"dual-root Skill mismatch: {name}",
        )
    return {
        "decision": "SPECIFICATION_IMPORTED",
        "skills": len(expected["skill_names"]),
        "contracts": len(expected["compiled_contracts"]["contracts"]),
        "dependency_edges": expected["manifest"]["dependency_edge_count"],
        "runtime_evidence_status": "NOT_RUN",
        "customer_evidence_status": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def integrate(root: Path, *, write: bool) -> dict[str, Any]:
    root = _repository_root(root)
    archive = root / ARCHIVE_RELATIVE
    summary = validate_source(archive)
    expected = build_expected(summary, root)
    return write_install(root, expected) if write else check_install(root, expected)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write missing, collision-free generated files")
    mode.add_argument("--check", action="store_true", help="validate archive and generated files without writing")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = integrate(args.root, write=args.write)
    except IntegrationError as exc:
        print(json.dumps({"decision": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
