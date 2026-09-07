#!/usr/bin/env python3
"""Safely install the ChinaDB commercial migration specification Skills.

The canonical package is immutable input.  This integration normalizes its
Skill interfaces and records provenance, but deliberately leaves every Skill
at SPEC_ONLY / NOT_RUN / NOT_CERTIFIED until repository and external evidence
exists.  Source package scripts are never executed by this importer.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import skill_creator_tools


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "chinadb-commercial-migration-skills-v1.0.0"
PACKAGE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
RUNTIME_RELATIVE = Path("agent-skills") / "runtime"
WORKSPACE_RELATIVE = Path(".agents") / "skills"
DOC_RELATIVE = Path("docs") / "chinadb-commercial-migration-skills"
INSTALL_MANIFEST_NAME = "installed-manifest.json"
README_NAME = "README.md"

PACKAGE_NAME = "chinadb-commercial-migration-skills"
PACKAGE_VERSION = "1.0.0"
NAMESPACE = "chinadb-commercial-migration-v1"
EXPECTED_SOURCE_FILE_COUNT = 85
EXPECTED_CHECKSUM_COUNT = 84
EXPECTED_CHECKSUMS_FILE_SHA256 = (
    "c78522c3b2eb6b68f50c8883e9bc3525c91b1534299379ad48a5e5ad1e8287bf"
)
EXPECTED_EXCLUSIONS = ("PolarDB", "PolarDB-X", "TDSQL")

EXPECTED_SKILLS = (
    "00-migration-program-orchestrator",
    "01-estate-inventory-assessment",
    "02-semantic-db-ir",
    "03-rule-mutation-dsl",
    "04-data-movement-cdc",
    "05-ddl-auto-conversion",
    "06-sql-auto-conversion",
    "07-plsql-tsql-conversion",
    "08-application-code-auto-refactor",
    "09-behavior-equivalence-verification",
    "10-performance-equivalence-verification",
    "11-guarded-auto-repair",
    "12-cutover-rollback",
    "13-production-migration-certification",
    "14-security-governance",
    "15-evidence-ledger-reproducibility",
    "16-release-ci-quality-gates",
    "20-source-oracle-adapter",
    "21-source-sqlserver-adapter",
    "22-source-postgresql-adapter",
    "23-source-mysql-adapter",
    "24-source-db2-adapter",
    "25-source-sybase-adapter",
    "30-app-java-spring-adapter",
    "31-app-dotnet-adapter",
    "32-app-python-adapter",
    "33-app-nodejs-adapter",
    "34-app-go-adapter",
    "40-target-dm8",
    "41-target-kingbasees",
    "42-target-opengauss",
    "43-target-tidb",
    "44-target-gbase8s",
    "45-target-gbase8c",
    "46-target-gbase8a",
    "47-target-highgo",
    "48-target-oceanbase-oracle",
    "49-target-oceanbase-mysql",
    "50-target-gaussdb-oracle",
    "51-target-gaussdb-m",
    "52-target-goldendb",
    "60-route-support-matrix",
    "61-fixture-corpus-and-mutation-tests",
    "62-benchmark-lab",
    "63-migration-estimation-commercial-report",
    "64-vendor-native-tool-bridge",
    "65-observability-migration-control-plane",
)
TARGET_SKILLS = tuple(name for name in EXPECTED_SKILLS if re.match(r"^[45]\d-target-", name))
ROUTE_SOURCES = (
    "Oracle",
    "SQL Server",
    "PostgreSQL",
    "MySQL/MariaDB",
    "DB2 LUW",
    "Sybase ASE",
)
ROUTE_TARGETS = (
    "DM8",
    "KingbaseES",
    "openGauss",
    "TiDB",
    "GBase 8s",
    "GBase 8c",
    "GBase 8a",
    "HighGo/HGDB",
    "OceanBase Oracle",
    "OceanBase MySQL",
    "GaussDB Oracle",
    "GaussDB M",
    "GoldenDB",
)
BASELINE_TARGET_IDENTITIES = (
    "DM8",
    "KingbaseES",
    "openGauss",
    "TiDB",
    "GBase 8s",
    "GBase 8c",
    "GBase 8a",
    "HighGo HGDB",
    "OceanBase Oracle mode",
    "OceanBase MySQL mode",
    "GaussDB Oracle-compatible",
    "GaussDB M-compatible",
    "GoldenDB",
)
ROUTE_COLUMNS = (
    "source",
    "target",
    "priority",
    "package_scope",
    "release_condition",
)
REQUIRED_SKILL_SECTIONS = (
    "## Objective",
    "## Inputs",
    "## Required outputs",
    "## Implementation modules / repository contract",
    "## Workflow",
    "## Mandatory tests",
    "## Required evidence",
    "## Definition of Done",
)


class IntegrationError(RuntimeError):
    """A fail-closed package or installation validation error."""


def fail(message: str) -> None:
    raise IntegrationError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(value: bytes) -> str:
    return "sha256:" + sha256_bytes(value)


def alias_for(source_directory: str) -> str:
    alias = f"chinadb-{source_directory}"
    if (
        len(alias) > skill_creator_tools.MAX_SKILL_NAME_LENGTH
        or re.fullmatch(r"[a-z0-9-]+", alias) is None
    ):
        fail(f"invalid deterministic ChinaDB alias: {alias}")
    return alias


def _validate_relative_path(relative: str, label: str) -> PurePosixPath:
    if not relative or "\\" in relative or "\x00" in relative:
        fail(f"invalid {label} path: {relative!r}")
    path = PurePosixPath(relative)
    if path.is_absolute() or str(path) != relative or any(part in {"", ".", ".."} for part in path.parts):
        fail(f"{label} path escapes or is not normalized: {relative}")
    return path


def _assert_inside(root: Path, path: Path, label: str) -> None:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        fail(f"{label} path escapes package root: {path}")


def _source_files(source: Path) -> list[Path]:
    if not source.is_dir() or source.is_symlink():
        fail(f"canonical ChinaDB package must be a real directory: {source}")
    entries = list(source.rglob("*"))
    symlinks = [entry.relative_to(source).as_posix() for entry in entries if entry.is_symlink()]
    if symlinks:
        fail(f"ChinaDB package may not contain symbolic links: {symlinks[:5]}")
    files: list[Path] = []
    for entry in entries:
        if entry.is_file():
            _assert_inside(source, entry, "source file")
            files.append(entry)
        elif not entry.is_dir():
            fail(f"unsupported ChinaDB package entry: {entry}")
    return sorted(files, key=lambda path: path.relative_to(source).as_posix())


def _parse_checksums(source: Path) -> dict[str, str]:
    checksum_path = source / "CHECKSUMS.sha256"
    if not checksum_path.is_file() or checksum_path.is_symlink():
        fail("CHECKSUMS.sha256 is missing or is not a regular file")
    checksum_bytes = checksum_path.read_bytes()
    actual_root_digest = sha256_bytes(checksum_bytes)
    if actual_root_digest != EXPECTED_CHECKSUMS_FILE_SHA256:
        fail(
            "CHECKSUMS.sha256 trusted root digest mismatch: "
            f"expected={EXPECTED_CHECKSUMS_FILE_SHA256} actual={actual_root_digest}"
        )
    try:
        checksum_lines = checksum_bytes.decode("utf-8").splitlines()
    except UnicodeError as exc:
        fail(f"CHECKSUMS.sha256 is not UTF-8: {exc}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(checksum_lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (\S(?:.*\S)?)", line)
        if match is None:
            fail(f"invalid CHECKSUMS.sha256 line {line_number}")
        expected_digest, relative = match.groups()
        _validate_relative_path(relative, "checksum")
        if relative == "CHECKSUMS.sha256" or relative in entries:
            fail(f"duplicate or self-referential checksum path: {relative}")
        checked = source / relative
        if not checked.is_file() or checked.is_symlink():
            fail(f"checksummed file is missing or not regular: {relative}")
        _assert_inside(source, checked, "checksummed file")
        actual_digest = sha256_bytes(checked.read_bytes())
        if actual_digest != expected_digest:
            fail(
                f"checksum mismatch for {relative}: expected={expected_digest} actual={actual_digest}"
            )
        entries[relative] = expected_digest
    if len(entries) != EXPECTED_CHECKSUM_COUNT:
        fail(
            f"CHECKSUMS.sha256 must contain exactly {EXPECTED_CHECKSUM_COUNT} entries; "
            f"found {len(entries)}"
        )
    if list(entries) != sorted(entries):
        fail("CHECKSUMS.sha256 entries must be in deterministic path order")
    return entries


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {label}: {path}: {exc}")


def _validate_skill_source(source: Path, source_directory: str) -> dict[str, Any]:
    path = source / "skills" / source_directory / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        fail(f"canonical Skill unexpectedly contains install frontmatter: {source_directory}")
    title_match = re.match(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    if title_match is None:
        fail(f"canonical Skill lacks a title: {source_directory}")
    if f"- **Skill ID:** `{source_directory}`" not in text:
        fail(f"canonical Skill ID does not match its directory: {source_directory}")
    if "specification only until repository evidence proves otherwise" not in text:
        fail(f"canonical Skill lacks its specification-only boundary: {source_directory}")
    missing = [section for section in REQUIRED_SKILL_SECTIONS if section not in text]
    if missing:
        fail(f"canonical Skill {source_directory} is missing sections: {missing}")
    return {
        "source_directory": source_directory,
        "title": title_match.group(1).strip(),
        "source_path": path.relative_to(source).as_posix(),
        "source_sha256": digest(path.read_bytes()),
    }


def _validate_routes(source: Path) -> list[dict[str, str]]:
    route_path = source / "MIGRATION_ROUTE_MATRIX.csv"
    try:
        with route_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != ROUTE_COLUMNS:
                fail(f"route matrix columns must be exactly {list(ROUTE_COLUMNS)}")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        fail(f"invalid route matrix: {exc}")
    expected_pairs = [(source_name, target) for target in ROUTE_TARGETS for source_name in ROUTE_SOURCES]
    actual_pairs = [(row.get("source"), row.get("target")) for row in rows]
    if len(rows) != 78 or actual_pairs != expected_pairs:
        fail("route matrix must contain the exact ordered 6 source x 13 target routes")
    for row in rows:
        if row.get("package_scope") != "planned_by_skills":
            fail(f"route is not specification-scoped: {row}")
        if row.get("release_condition") != "requires exact version/mode certification":
            fail(f"route lacks the exact-version certification boundary: {row}")
        if row.get("target") in EXPECTED_EXCLUSIONS:
            fail(f"excluded target appears in route matrix: {row.get('target')}")
        if not row.get("priority"):
            fail(f"route priority is empty: {row}")
    return rows


def validate_source(source: Path) -> dict[str, Any]:
    """Validate the immutable source package without executing package code."""

    if source.is_symlink():
        fail(f"canonical ChinaDB package may not be a symbolic link: {source}")
    source = source.resolve()
    files = _source_files(source)
    relative_files = [path.relative_to(source).as_posix() for path in files]
    if len(files) != EXPECTED_SOURCE_FILE_COUNT:
        fail(
            f"ChinaDB package must contain exactly {EXPECTED_SOURCE_FILE_COUNT} files; "
            f"found {len(files)}"
        )
    checksums = _parse_checksums(source)
    expected_files = set(checksums) | {"CHECKSUMS.sha256"}
    if set(relative_files) != expected_files:
        fail(
            "checksum coverage is not exact: "
            f"missing={sorted(expected_files - set(relative_files))} "
            f"extra={sorted(set(relative_files) - expected_files)}"
        )

    manifest = _load_json(source / "PACKAGE_MANIFEST.json", "package manifest")
    if manifest.get("package") != PACKAGE_NAME or manifest.get("version") != PACKAGE_VERSION:
        fail("ChinaDB package identity or version is invalid")
    if manifest.get("excluded_targets") != list(EXPECTED_EXCLUSIONS):
        fail("ChinaDB excluded-target list or order is invalid")
    if manifest.get("skill_count") != len(EXPECTED_SKILLS):
        fail("ChinaDB manifest Skill count is invalid")
    if manifest.get("skills") != list(EXPECTED_SKILLS):
        fail("ChinaDB manifest must preserve the exact ordered Skill inventory")
    if not isinstance(manifest.get("as_of"), str) or not manifest["as_of"]:
        fail("ChinaDB package as_of value is missing")

    skill_files = sorted((source / "skills").glob("*/SKILL.md"))
    skill_directories = [path.parent.name for path in skill_files]
    if len(skill_files) != 47 or set(skill_directories) != set(EXPECTED_SKILLS):
        fail("ChinaDB package must contain exactly the 47 manifest-owned Skill files")
    skills = [_validate_skill_source(source, source_directory) for source_directory in EXPECTED_SKILLS]

    baselines: list[dict[str, Any]] = []
    target_names: list[str] = []
    baseline_paths = sorted((source / "skills").glob("*/capability-baseline.yaml"))
    if len(baseline_paths) != 13:
        fail(f"ChinaDB package must contain exactly 13 target baselines; found {len(baseline_paths)}")
    if [path.parent.name for path in baseline_paths] != list(TARGET_SKILLS):
        fail("ChinaDB target baselines do not match the exact ordered target Skills")
    for path in baseline_paths:
        baseline = _load_json(path, "target capability baseline")
        if not isinstance(baseline, dict) or not isinstance(baseline.get("target"), str):
            fail(f"target baseline lacks a target identity: {path}")
        if baseline.get("status") != "implementation-planning baseline, not runtime proof":
            fail(f"target baseline lacks its planning-only status: {path}")
        target_names.append(baseline["target"])
        baselines.append(
            {
                "source_directory": path.parent.name,
                "target": baseline["target"],
                "source_path": path.relative_to(source).as_posix(),
                "source_sha256": digest(path.read_bytes()),
            }
        )
    if tuple(target_names) != BASELINE_TARGET_IDENTITIES:
        fail("ChinaDB target baseline identities or order are invalid")

    routes = _validate_routes(source)
    implementation = _load_json(source / "IMPLEMENTATION_STATUS.json", "implementation status")
    if not isinstance(implementation, dict) or list(implementation) != list(EXPECTED_SKILLS):
        fail("implementation status must preserve the exact ordered Skill inventory")
    for source_directory in EXPECTED_SKILLS:
        state = implementation.get(source_directory)
        if not isinstance(state, dict):
            fail(f"implementation status is not an object: {source_directory}")
        if state.get("implemented") is not False or state.get("evidence_ids") != []:
            fail(f"Skill must remain unimplemented with empty evidence: {source_directory}")
        if set(state) != {"implemented", "evidence_ids", "note"} or not isinstance(
            state.get("note"), str
        ):
            fail(f"implementation status shape is invalid: {source_directory}")

    aliases = [alias_for(source_directory) for source_directory in EXPECTED_SKILLS]
    if len(set(aliases)) != 47:
        fail("deterministic ChinaDB aliases are not unique")
    inventory = [
        {
            "path": path.relative_to(source).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest(path.read_bytes()),
        }
        for path in files
    ]
    return {
        "source": source,
        "manifest": manifest,
        "checksums": checksums,
        "inventory": inventory,
        "skills": skills,
        "baselines": baselines,
        "routes": routes,
        "aliases": aliases,
    }


def _render_skill(summary: dict[str, Any], skill: dict[str, Any]) -> bytes:
    source_directory = skill["source_directory"]
    alias = alias_for(source_directory)
    source = summary["source"] / skill["source_path"]
    description = (
        f"Use when ELMOS must follow the ChinaDB commercial database-migration specification for "
        f"{skill['title']}. Keep exact directed route and version semantics, require real evidence, "
        "and fail closed on unsupported behavior."
    )
    frontmatter = "\n".join(
        [
            "---",
            f"name: {alias}",
            f"description: {skill_creator_tools.yaml_quote(description)}",
            "metadata:",
            f"  source_package: {skill_creator_tools.yaml_quote(PACKAGE_NAME)}",
            f"  source_version: {skill_creator_tools.yaml_quote(PACKAGE_VERSION)}",
            f"  source_directory: {skill_creator_tools.yaml_quote(source_directory)}",
            f"  source_path: {skill_creator_tools.yaml_quote(skill['source_path'])}",
            f"  source_sha256: {skill_creator_tools.yaml_quote(skill['source_sha256'])}",
            f"  normalized_namespace: {skill_creator_tools.yaml_quote(NAMESPACE)}",
            '  implementation_state: "SPEC_ONLY"',
            '  external_evidence_status: "NOT_RUN"',
            '  production_certification: "NOT_CERTIFIED"',
            "---",
            "",
        ]
    )
    boundary = "\n".join(
        [
            "",
            "## Repository Integration Boundary",
            "",
            f"- Provenance is pinned to `{PACKAGE_NAME}` version `{PACKAGE_VERSION}`, source Skill `{source_directory}`, and the SHA-256 digest in frontmatter.",
            "- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.",
            "- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.",
            "- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.",
            "- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.",
            "- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.",
            "- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.",
            "- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.",
            "",
        ]
    )
    rendered = (
        frontmatter
        + source.read_text(encoding="utf-8").rstrip()
        + "\n"
        + boundary
    )
    return rendered.encode("utf-8")


def _render_interface(alias: str) -> bytes:
    display = skill_creator_tools.format_display_name(alias).replace("Chinadb", "ChinaDB")
    short = "Run this ChinaDB migration Skill with evidence controls"
    prompt = (
        f"Use ${alias} as a SPEC_ONLY ChinaDB migration contract; preserve exact route semantics "
        "and fail closed while real evidence is NOT_RUN."
    )
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


def _tree_digest(trees: dict[str, dict[str, bytes]]) -> str:
    value = hashlib.sha256()
    for alias in sorted(trees):
        for relative in sorted(trees[alias]):
            value.update(alias.encode("utf-8"))
            value.update(b"\0")
            value.update(relative.encode("utf-8"))
            value.update(b"\0")
            value.update(trees[alias][relative])
            value.update(b"\0")
    return "sha256:" + value.hexdigest()


def _source_tree_digest(inventory: list[dict[str, Any]]) -> str:
    value = hashlib.sha256()
    for item in inventory:
        value.update(item["path"].encode("utf-8"))
        value.update(b"\0")
        value.update(item["sha256"].encode("ascii"))
        value.update(b"\0")
        value.update(str(item["bytes"]).encode("ascii"))
        value.update(b"\0")
    return "sha256:" + value.hexdigest()


def _render_readme() -> bytes:
    return f"""# ChinaDB Commercial Migration Skills Integration

This directory records the repository installation of `{PACKAGE_NAME}` version `{PACKAGE_VERSION}`.

- Canonical source: `{PACKAGE_RELATIVE.as_posix()}/`
- Installed aliases: 47 exact `chinadb-<source-directory>` names in both `agent-skills/runtime/` and `.agents/skills/`
- Target planning baselines: 13, copied byte-for-byte into their target Skill directories
- Planned directed routes: 78
- Excluded targets: PolarDB, PolarDB-X, TDSQL
- Current state: `SPEC_ONLY` / external evidence `NOT_RUN` / production certification `NOT_CERTIFIED`

Static package validation and installation are engineering evidence only. They do not prove SQL, procedural, DDL, data, CDC, application, performance, cutover, rollback, security, or production behavior. Exact source and target database execution plus the conservative Batch 31 gate remain required.

Verify the canonical package, both installation roots, all copied baselines, interfaces, provenance, digests, and drift with:

```sh
python3 tooling/integrate_chinadb_commercial_migration_skills.py --check
```
""".encode("utf-8")


def build_expected(source: Path) -> dict[str, Any]:
    summary = validate_source(source)
    readme_bytes = _render_readme()
    baseline_by_skill = {item["source_directory"]: item for item in summary["baselines"]}
    trees: dict[str, dict[str, bytes]] = {}
    records: list[dict[str, Any]] = []
    for skill in summary["skills"]:
        source_directory = skill["source_directory"]
        alias = alias_for(source_directory)
        tree = {
            "SKILL.md": _render_skill(summary, skill),
            "agents/openai.yaml": _render_interface(alias),
        }
        baseline_record: dict[str, Any] | None = None
        if source_directory in baseline_by_skill:
            baseline = baseline_by_skill[source_directory]
            baseline_bytes = (summary["source"] / baseline["source_path"]).read_bytes()
            tree["capability-baseline.yaml"] = baseline_bytes
            baseline_record = {
                "target": baseline["target"],
                "source_path": baseline["source_path"],
                "source_sha256": baseline["source_sha256"],
                "runtime_path": (
                    RUNTIME_RELATIVE / alias / "capability-baseline.yaml"
                ).as_posix(),
                "runtime_sha256": digest(baseline_bytes),
                "workspace_path": (
                    WORKSPACE_RELATIVE / alias / "capability-baseline.yaml"
                ).as_posix(),
                "workspace_sha256": digest(baseline_bytes),
            }
        trees[alias] = tree
        records.append(
            {
                "source_directory": source_directory,
                "source_title": skill["title"],
                "source_path": (PACKAGE_RELATIVE / skill["source_path"]).as_posix(),
                "source_sha256": skill["source_sha256"],
                "installed_alias": alias,
                "runtime_skill_path": (RUNTIME_RELATIVE / alias / "SKILL.md").as_posix(),
                "runtime_skill_sha256": digest(tree["SKILL.md"]),
                "runtime_interface_path": (
                    RUNTIME_RELATIVE / alias / "agents" / "openai.yaml"
                ).as_posix(),
                "runtime_interface_sha256": digest(tree["agents/openai.yaml"]),
                "workspace_skill_path": (
                    WORKSPACE_RELATIVE / alias / "SKILL.md"
                ).as_posix(),
                "workspace_skill_sha256": digest(tree["SKILL.md"]),
                "workspace_interface_path": (
                    WORKSPACE_RELATIVE / alias / "agents" / "openai.yaml"
                ).as_posix(),
                "workspace_interface_sha256": digest(tree["agents/openai.yaml"]),
                "installed_tree_sha256": _tree_digest({alias: tree}),
                "target_baseline": baseline_record,
                "implemented": False,
                "evidence_ids": [],
                "implementation_state": "SPEC_ONLY",
                "external_evidence_status": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
            }
        )

    source_inventory = [
        {
            **item,
            "path": (PACKAGE_RELATIVE / item["path"]).as_posix(),
        }
        for item in summary["inventory"]
    ]
    source_by_name = {Path(item["path"]).name: item for item in source_inventory}
    tree_digest = _tree_digest(trees)
    manifest = {
        "schema_version": "1.0",
        "namespace": NAMESPACE,
        "source_package": PACKAGE_NAME,
        "source_version": PACKAGE_VERSION,
        "source_path": PACKAGE_RELATIVE.as_posix(),
        "source_file_count": EXPECTED_SOURCE_FILE_COUNT,
        "source_checksum_entry_count": EXPECTED_CHECKSUM_COUNT,
        "source_checksum_coverage": {
            "exact": True,
            "covered_files": EXPECTED_CHECKSUM_COUNT,
            "self_excluded_file": "CHECKSUMS.sha256",
        },
        "source_tree_sha256": _source_tree_digest(summary["inventory"]),
        "source_checksums_sha256": source_by_name["CHECKSUMS.sha256"]["sha256"],
        "source_package_manifest_sha256": source_by_name["PACKAGE_MANIFEST.json"]["sha256"],
        "source_implementation_status_sha256": source_by_name["IMPLEMENTATION_STATUS.json"][
            "sha256"
        ],
        "source_route_matrix_sha256": source_by_name["MIGRATION_ROUTE_MATRIX.csv"]["sha256"],
        "integration_readme_path": (DOC_RELATIVE / README_NAME).as_posix(),
        "integration_readme_sha256": digest(readme_bytes),
        "source_files": source_inventory,
        "excluded_targets": list(EXPECTED_EXCLUSIONS),
        "skill_count": 47,
        "target_baseline_count": 13,
        "directed_route_count": 78,
        "runtime_root": RUNTIME_RELATIVE.as_posix(),
        "workspace_root": WORKSPACE_RELATIVE.as_posix(),
        "runtime_tree_sha256": tree_digest,
        "workspace_tree_sha256": tree_digest,
        "dual_root_byte_identical": True,
        "implementation_state": "SPEC_ONLY",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "maximum_installation_claim": "SPECIFICATION_INSTALLED",
        "skills": records,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return {
        "summary": summary,
        "trees": trees,
        "manifest": manifest,
        "manifest_bytes": manifest_bytes,
        "readme_bytes": readme_bytes,
    }


def _read_tree(root: Path) -> dict[str, bytes]:
    if not root.is_dir() or root.is_symlink():
        fail(f"installed Skill is missing or not a real directory: {root}")
    values: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            fail(f"installed Skill may not contain symbolic links: {path}")
        if path.is_file():
            try:
                path.resolve(strict=True).relative_to(root.resolve(strict=True))
            except (OSError, ValueError):
                fail(f"installed Skill path escapes its root: {path}")
            values[path.relative_to(root).as_posix()] = path.read_bytes()
        elif not path.is_dir():
            fail(f"unsupported installed Skill entry: {path}")
    return values


def _prefixed_entries(root: Path) -> set[str]:
    if not root.exists():
        return set()
    if not root.is_dir() or root.is_symlink():
        fail(f"installation root is not a real directory: {root}")
    return {path.name for path in root.iterdir() if path.name.startswith("chinadb-")}


def check_install(repository_root: Path = ROOT, source: Path | None = None) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    source = source if source is not None else repository_root / PACKAGE_RELATIVE
    expected = build_expected(source)
    aliases = set(expected["trees"])
    failures: list[str] = []
    for relative_root, label in (
        (RUNTIME_RELATIVE, "runtime"),
        (WORKSPACE_RELATIVE, "workspace"),
    ):
        install_root = repository_root / relative_root
        try:
            actual_aliases = _prefixed_entries(install_root)
        except IntegrationError as exc:
            failures.append(f"{label}-root:{exc}")
            actual_aliases = set()
        if actual_aliases != aliases:
            failures.append(
                f"{label}-aliases:missing={sorted(aliases - actual_aliases)}:"
                f"extra={sorted(actual_aliases - aliases)}"
            )
        for alias in sorted(aliases & actual_aliases):
            try:
                actual = _read_tree(install_root / alias)
            except IntegrationError as exc:
                failures.append(f"{label}:{alias}:{exc}")
                continue
            if actual != expected["trees"][alias]:
                missing = sorted(set(expected["trees"][alias]) - set(actual))
                extra = sorted(set(actual) - set(expected["trees"][alias]))
                changed = sorted(
                    path
                    for path in set(actual) & set(expected["trees"][alias])
                    if actual[path] != expected["trees"][alias][path]
                )
                failures.append(
                    f"{label}:{alias}:missing={missing}:extra={extra}:changed={changed}"
                )

    doc_root = repository_root / DOC_RELATIVE
    expected_doc_files = {INSTALL_MANIFEST_NAME, README_NAME}
    if not doc_root.is_dir() or doc_root.is_symlink():
        failures.append("docs-root")
    else:
        doc_entries = {
            path.relative_to(doc_root).as_posix()
            for path in doc_root.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        if any(path.is_symlink() for path in doc_root.rglob("*")):
            failures.append("docs-symlink")
        if doc_entries != expected_doc_files:
            failures.append(
                f"docs-files:missing={sorted(expected_doc_files - doc_entries)}:"
                f"extra={sorted(doc_entries - expected_doc_files)}"
            )
        manifest_path = doc_root / INSTALL_MANIFEST_NAME
        readme_path = doc_root / README_NAME
        if not manifest_path.is_file() or manifest_path.read_bytes() != expected["manifest_bytes"]:
            failures.append("installed-manifest")
        if not readme_path.is_file() or readme_path.read_bytes() != expected["readme_bytes"]:
            failures.append("integration-readme")
    if failures:
        fail(f"ChinaDB installation drifted: {failures[:12]} ({len(failures)} total)")
    return expected


def _previous_ownership(
    repository_root: Path,
    expected: dict[str, Any],
) -> tuple[set[str], set[str]]:
    aliases = set(expected["trees"])
    manifest_path = repository_root / DOC_RELATIVE / INSTALL_MANIFEST_NAME
    if not manifest_path.exists():
        return set(), set()
    if not manifest_path.is_file() or manifest_path.is_symlink():
        fail(f"installed manifest is not a regular owned file: {manifest_path}")
    if manifest_path.read_bytes() != expected["manifest_bytes"]:
        fail("previous ChinaDB manifest does not match the trusted generated manifest")
    previous = _load_json(manifest_path, "previous ChinaDB installed manifest")
    if (
        not isinstance(previous, dict)
        or previous.get("namespace") != NAMESPACE
        or previous.get("source_package") != PACKAGE_NAME
        or previous.get("source_version") != PACKAGE_VERSION
    ):
        fail(f"refusing to replace foreign installed manifest: {manifest_path}")
    records = previous.get("skills")
    if not isinstance(records, list):
        fail("previous ChinaDB installed manifest has no owned Skill list")
    runtime_owned: set[str] = set()
    workspace_owned: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("installed_alias"), str):
            fail("previous ChinaDB installed manifest has an invalid Skill record")
        alias = record["installed_alias"]
        if alias not in aliases:
            fail(f"previous ChinaDB manifest claims an unexpected alias: {alias}")
        if record.get("runtime_skill_path") != (RUNTIME_RELATIVE / alias / "SKILL.md").as_posix():
            fail(f"previous ChinaDB runtime ownership path is invalid: {alias}")
        if record.get("workspace_skill_path") != (
            WORKSPACE_RELATIVE / alias / "SKILL.md"
        ).as_posix():
            fail(f"previous ChinaDB workspace ownership path is invalid: {alias}")
        runtime_owned.add(alias)
        workspace_owned.add(alias)
    if runtime_owned != aliases or workspace_owned != aliases:
        fail("previous ChinaDB manifest does not own the exact expected aliases")

    readme_path = repository_root / DOC_RELATIVE / README_NAME
    if (
        not readme_path.is_file()
        or readme_path.is_symlink()
        or readme_path.read_bytes() != expected["readme_bytes"]
    ):
        fail("previous ChinaDB integration README has drifted; refusing replacement")
    for relative_root, label in (
        (RUNTIME_RELATIVE, "Runtime"),
        (WORKSPACE_RELATIVE, "workspace"),
    ):
        for alias in sorted(aliases):
            destination = repository_root / relative_root / alias
            try:
                actual_tree = _read_tree(destination)
            except IntegrationError as exc:
                fail(
                    f"previous owned {label} Skill cannot be verified: {alias}: {exc}"
                )
            if actual_tree != expected["trees"][alias]:
                fail(
                    f"previous owned {label} Skill has drifted; refusing replacement: {alias}"
                )
    return runtime_owned, workspace_owned


def _write_tree(destination: Path, values: dict[str, bytes]) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for relative, content in sorted(values.items()):
        _validate_relative_path(relative, "installed")
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def write_install(repository_root: Path = ROOT, source: Path | None = None) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    source = source if source is not None else repository_root / PACKAGE_RELATIVE
    expected = build_expected(source)
    aliases = set(expected["trees"])
    runtime_owned, workspace_owned = _previous_ownership(repository_root, expected)
    manifest_exists = (repository_root / DOC_RELATIVE / INSTALL_MANIFEST_NAME).exists()

    doc_root = repository_root / DOC_RELATIVE
    if doc_root.exists():
        if not doc_root.is_dir() or doc_root.is_symlink():
            fail(f"refusing to overwrite unowned documentation path: {doc_root}")
        doc_symlinks = [
            path.relative_to(doc_root).as_posix() for path in doc_root.rglob("*") if path.is_symlink()
        ]
        if doc_symlinks:
            fail(f"refusing to follow ChinaDB documentation symlinks: {doc_symlinks}")
        existing_docs = {
            path.relative_to(doc_root).as_posix()
            for path in doc_root.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        allowed_docs = {INSTALL_MANIFEST_NAME, README_NAME} if manifest_exists else set()
        if not existing_docs.issubset(allowed_docs):
            fail(f"refusing to overwrite unowned ChinaDB documentation: {sorted(existing_docs)}")

    for relative_root, owned, label in (
        (RUNTIME_RELATIVE, runtime_owned, "Runtime"),
        (WORKSPACE_RELATIVE, workspace_owned, "workspace"),
    ):
        install_root = repository_root / relative_root
        existing_prefixed = _prefixed_entries(install_root)
        unexpected = existing_prefixed - aliases
        if unexpected:
            fail(f"refusing to remove unowned {label} ChinaDB aliases: {sorted(unexpected)}")
        for alias in sorted(aliases):
            destination = install_root / alias
            if destination.exists() or destination.is_symlink():
                if alias not in owned:
                    fail(f"refusing to overwrite unowned {label} Skill: {destination}")
                if destination.is_symlink() or not destination.is_dir():
                    fail(f"owned {label} Skill is not a real directory: {destination}")

    # All collision checks complete before any repository mutation.
    for relative_root in (RUNTIME_RELATIVE, WORKSPACE_RELATIVE):
        install_root = repository_root / relative_root
        install_root.mkdir(parents=True, exist_ok=True)
        for alias in sorted(aliases):
            destination = install_root / alias
            if destination.exists():
                shutil.rmtree(destination)
            _write_tree(destination, expected["trees"][alias])

    doc_root.mkdir(parents=True, exist_ok=True)
    (doc_root / README_NAME).write_bytes(expected["readme_bytes"])
    # Write the ownership manifest last so an interrupted first install cannot
    # claim paths that were never fully materialized.
    (doc_root / INSTALL_MANIFEST_NAME).write_bytes(expected["manifest_bytes"])
    return check_install(repository_root, source)


def _result(expected: dict[str, Any], mode: str) -> dict[str, Any]:
    manifest = expected["manifest"]
    return {
        "status": "PASS",
        "mode": mode,
        "package": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
        "source_files": manifest["source_file_count"],
        "checksum_entries": manifest["source_checksum_entry_count"],
        "skills": manifest["skill_count"],
        "target_baselines": manifest["target_baseline_count"],
        "directed_routes": manifest["directed_route_count"],
        "runtime_skills": manifest["skill_count"],
        "workspace_skills": manifest["skill_count"],
        "implementation_state": manifest["implementation_state"],
        "external_evidence": manifest["external_evidence_status"],
        "production_certification": manifest["production_certification"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="install the validated specification")
    mode.add_argument("--check", action="store_true", help="fail on source or installation drift")
    args = parser.parse_args(argv)
    try:
        expected = write_install() if args.write else check_install()
    except IntegrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(_result(expected, "write" if args.write else "check"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
