#!/usr/bin/env python3
"""Import and integrate the immutable Batch 81-95 slightly-strict test package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "elmos-batch81-95-slightly-strict-test-skills"
PACKAGE_ROOT = ROOT / PACKAGE_NAME
LANGUAGE_PACKAGE = ROOT / "elmos-language-packs-batch81-95-complete"
LANGUAGE_INSTALL_MANIFEST = ROOT / "docs/language-packs-batch81-95/installed-manifest.json"
RUNTIME_ROOT = ROOT / "agent-skills/runtime"
CODEX_SKILL_ROOT = ROOT / ".agents/skills"
SUITE_ROOT = ROOT / "test-suites/batch81-95-language-packs-slightly-strict"
INSTALL_MANIFEST = ROOT / "docs/test-suite-b81-95/source-install-manifest.json"
SKILL_GENERATOR = Path(
    "/Users/stephen/.codex/skills/.system/skill-creator/scripts/generate_openai_yaml.py"
)
SOURCE_ZIP = Path("/Users/stephen/Downloads/elmos-language-packs-batch81-95-complete.zip")
EXPECTED_SOURCE_ZIP_SHA256 = "4c3de1f268c3c0b98e6fc500240618d58d5255df5e75f5c00ff9f8211565d13d"
EXPECTED_FILES = 104
EXPECTED_TEST_SKILLS = 40
EXPECTED_CASES = 640
EXPECTED_SOURCE_SKILLS = 180
EXPECTED_IDS = [f"PG{number:03d}" for number in range(223, 403)]
EXPECTED_TEST_IDS = [f"T{number:03d}" for number in range(81, 121)]
EXPECTED_SEVERITIES = {"critical": 170, "high": 400, "medium": 70}
SUITE_ID = "batch81-95-language-packs-slightly-strict"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"Package path escapes its root: {relative}") from exc
    return path


def copy_exact(source: Path, destination: Path) -> None:
    if destination.exists():
        if destination.is_file() and sha256_file(destination) == sha256_file(source):
            return
        raise SystemExit(f"Refusing to overwrite different destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def load_generator() -> ModuleType:
    if not SKILL_GENERATOR.is_file():
        raise SystemExit(f"Skill interface generator is missing: {SKILL_GENERATOR}")
    spec = importlib.util.spec_from_file_location("batch81_95_test_interface_generator", SKILL_GENERATOR)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load Skill interface generator: {SKILL_GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_source_skill(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise SystemExit(f"Source test Skill frontmatter is invalid: {path}")
    frontmatter, body = text[4:].split("\n---\n", 1)
    metadata: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, body


def normalized_skill_text(
    source_path: Path,
    entry: dict[str, Any],
    generator: ModuleType,
) -> str:
    metadata, body = parse_source_skill(source_path)
    name = entry["name"]
    title = entry["title"]
    description = (
        f"Run the exact ELMOS Batch 81-95 slightly-strict {title} tests with "
        "fail-closed native evidence. Use when validating the assigned Language Pack scope."
    )
    batch = "cross" if entry.get("batch") is None else str(entry["batch"])
    lines = [
        "---",
        f"name: {name}",
        f"description: {generator.yaml_quote(description)}",
        "metadata:",
        f"  source_package: {generator.yaml_quote(PACKAGE_NAME)}",
        f"  source_id: {generator.yaml_quote(entry['id'])}",
        f"  source_name: {generator.yaml_quote(name)}",
        f"  source_sha256: {generator.yaml_quote('sha256:' + sha256_file(source_path))}",
        f"  source_kind: {generator.yaml_quote(entry['kind'])}",
        f"  source_batch: {generator.yaml_quote(batch)}",
        f"  source_version: {generator.yaml_quote(metadata.get('version', '1.0.0'))}",
        f"  source_status: {generator.yaml_quote('test-ready-not-run')}",
        "---",
        "",
        body.rstrip(),
        "",
    ]
    return "\n".join(lines)


def expected_interface(name: str, generator: ModuleType) -> str:
    return "\n".join(
        [
            "interface:",
            f"  display_name: {generator.yaml_quote(generator.format_display_name(name))}",
            "  short_description: "
            + generator.yaml_quote("Run this ELMOS Batch 81-95 test Skill with evidence"),
            "  default_prompt: "
            + generator.yaml_quote(
                f"Use ${name} to run its exact Batch 81-95 test scope with fail-closed evidence."
            ),
            "",
        ]
    )


def install_interface(skill_dir: Path, name: str, generator: ModuleType) -> None:
    interface = skill_dir / "agents/openai.yaml"
    expected = expected_interface(name, generator)
    if interface.exists():
        if interface.is_file() and interface.read_text(encoding="utf-8") == expected:
            return
        raise SystemExit(f"Refusing to overwrite different test Skill interface: {interface}")
    result = generator.write_openai_yaml(
        skill_dir,
        name,
        [
            "short_description=Run this ELMOS Batch 81-95 test Skill with evidence",
            "default_prompt="
            + f"Use ${name} to run its exact Batch 81-95 test scope with fail-closed evidence.",
        ],
    )
    if result is None or interface.read_text(encoding="utf-8") != expected:
        raise SystemExit(f"Test Skill interface generation failed: {name}")


def read_sha256s(source: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in (source / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split(None, 1)
        relative = relative.strip().lstrip("*")
        if relative in entries or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SystemExit(f"Invalid SHA256SUMS entry: {relative}")
        entries[relative] = digest
    return entries


def validate_file_inventory(source: Path) -> dict[str, dict[str, Any]]:
    package_manifest = load_json(source / "package-manifest.json")
    if package_manifest.get("package") != PACKAGE_NAME:
        raise SystemExit("Test package file-manifest identity is invalid")
    files = package_manifest.get("files")
    if not isinstance(files, list) or len(files) != EXPECTED_FILES:
        raise SystemExit(f"Test package must contain exactly {EXPECTED_FILES} manifest-owned files")
    sha_entries = read_sha256s(source)
    inventory: dict[str, dict[str, Any]] = {}
    for entry in files:
        relative = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(relative, str) or not relative or relative in inventory:
            raise SystemExit(f"Invalid or duplicate file-manifest path: {relative!r}")
        path = safe_path(source, relative)
        if not path.is_file():
            raise SystemExit(f"Test package file is missing: {relative}")
        digest = sha256_file(path)
        if path.stat().st_size != entry.get("size_bytes") or digest != entry.get("sha256"):
            raise SystemExit(f"Test package file size/digest mismatch: {relative}")
        if sha_entries.get(relative) != digest:
            raise SystemExit(f"SHA256SUMS differs from package-manifest: {relative}")
        inventory[relative] = entry
    if set(sha_entries) != set(inventory):
        raise SystemExit("SHA256SUMS and package-manifest file sets differ")
    return inventory


def validate_language_binding(source: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    target = load_json(source / "references/TARGET_MANIFEST.json")
    current_target = load_json(LANGUAGE_PACKAGE / "index.json")
    if target != current_target:
        raise SystemExit("Test TARGET_MANIFEST differs from the current canonical Language Pack index")
    installed = load_json(LANGUAGE_INSTALL_MANIFEST)
    if (
        target.get("package") != "elmos-language-packs-batch81-95-complete"
        or target.get("engine") != "elmos.language-packs"
        or target.get("skill_count") != EXPECTED_SOURCE_SKILLS
        or target.get("skill_id_range") != ["PG223", "PG402"]
        or installed.get("source_id_namespace") != "package-local-language-pack"
        or installed.get("skill_count") != EXPECTED_SOURCE_SKILLS
    ):
        raise SystemExit("Language Pack target/install identity is invalid")
    target_skills = target.get("skills")
    installed_skills = installed.get("skills")
    if not isinstance(target_skills, list) or not isinstance(installed_skills, list):
        raise SystemExit("Language Pack target/install Skill inventory is missing")
    installed_by_id = {entry.get("source_id"): entry for entry in installed_skills}
    if [entry.get("id") for entry in target_skills] != EXPECTED_IDS:
        raise SystemExit("Language Pack target IDs must be contiguous package-local PG223-PG402")
    for entry in target_skills:
        binding = installed_by_id.get(entry["id"])
        if (
            not isinstance(binding, dict)
            or binding.get("source_name") != entry.get("name")
            or binding.get("source_path") != entry.get("path")
            or binding.get("batch") != entry.get("batch")
        ):
            raise SystemExit(f"Language Pack installed binding is stale: {entry['id']}")
        source_skill = LANGUAGE_PACKAGE / entry["path"]
        if binding.get("source_sha256") != "sha256:" + sha256_file(source_skill):
            raise SystemExit(f"Language Pack source digest is stale: {entry['id']}")
    return target, installed


def validate_source(
    source: Path,
    *,
    require_source_zip: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    inventory = validate_file_inventory(source)
    manifest = load_json(source / "manifest.json")
    if (
        manifest.get("package") != PACKAGE_NAME
        or manifest.get("version") != "1.0.0"
        or manifest.get("test_skill_count") != EXPECTED_TEST_SKILLS
        or manifest.get("case_count") != EXPECTED_CASES
        or manifest.get("source_skill_count") != EXPECTED_SOURCE_SKILLS
        or manifest.get("test_skill_range") != "T081-T120"
        or manifest.get("source_skill_range") != "PG223-PG402"
        or manifest.get("release_policy") != "non-compensating"
    ):
        raise SystemExit("Test package manifest identity or exact counts are invalid")
    if manifest.get("source_package_sha256") != EXPECTED_SOURCE_ZIP_SHA256:
        raise SystemExit("Test package source ZIP digest declaration is invalid")
    if require_source_zip:
        if not SOURCE_ZIP.is_file() or sha256_file(SOURCE_ZIP) != EXPECTED_SOURCE_ZIP_SHA256:
            raise SystemExit("Declared Language Pack source ZIP is missing or has the wrong digest")

    test_skills = manifest.get("test_skills")
    if not isinstance(test_skills, list) or len(test_skills) != EXPECTED_TEST_SKILLS:
        raise SystemExit("Test Skill inventory must contain exactly 40 entries")
    if [entry.get("id") for entry in test_skills] != EXPECTED_TEST_IDS:
        raise SystemExit("Test Skill IDs must be contiguous T081-T120")
    names: set[str] = set()
    owned_case_ids: list[str] = []
    for entry in test_skills:
        name = entry.get("name")
        if not isinstance(name, str) or not name or len(name) > 64 or name in names:
            raise SystemExit(f"Invalid or duplicate test Skill name: {name!r}")
        names.add(name)
        skill_relative = f"agent-skills/runtime/{name}/SKILL.md"
        cases_relative = f"agent-skills/runtime/{name}/cases.json"
        if skill_relative not in inventory or cases_relative not in inventory:
            raise SystemExit(f"Test Skill assets are absent from the file manifest: {name}")
        metadata, _ = parse_source_skill(source / skill_relative)
        if metadata.get("id") != entry.get("id") or metadata.get("name") != name:
            raise SystemExit(f"Test Skill frontmatter/manifest mismatch: {name}")
        case_ids = entry.get("case_ids")
        expected_owned_cases = 26 if entry.get("kind") == "batch" else 10
        if not isinstance(case_ids, list) or len(case_ids) != expected_owned_cases:
            raise SystemExit(f"Test Skill case ownership is incomplete: {name}")
        owned_case_ids.extend(case_ids)

    cases = load_json(source / "CASE_CATALOG.json")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CASES:
        raise SystemExit("CASE_CATALOG.json must contain exactly 640 cases")
    expected_case_ids = [f"CASE-{number:04d}" for number in range(1, 641)]
    if [case.get("id") for case in cases] != expected_case_ids:
        raise SystemExit("Case IDs must be contiguous CASE-0001 through CASE-0640")
    if sorted(owned_case_ids) != expected_case_ids:
        raise SystemExit("Test Skill ownership must exactly cover all 640 cases")
    skill_by_id = {entry["id"]: entry for entry in test_skills}
    cases_by_id = {case["id"]: case for case in cases}
    for entry in test_skills:
        skill_cases = load_json(
            source / "agent-skills/runtime" / entry["name"] / "cases.json"
        )
        expected_skill_cases = [cases_by_id[case_id] for case_id in entry["case_ids"]]
        if skill_cases != expected_skill_cases:
            raise SystemExit(
                f"Test Skill cases.json does not match CASE_CATALOG.json: {entry['name']}"
            )
    severity_counts = Counter(case.get("severity") for case in cases)
    if dict(severity_counts) != EXPECTED_SEVERITIES:
        raise SystemExit(f"Case severity counts are invalid: {dict(severity_counts)}")
    for case in cases:
        owner = skill_by_id.get(case.get("test_skill_id"))
        if owner is None or case["id"] not in owner["case_ids"]:
            raise SystemExit(f"Case owner is invalid: {case['id']}")
        targets = case.get("target_skills")
        if not isinstance(targets, list) or not targets or any(target not in EXPECTED_IDS for target in targets):
            raise SystemExit(f"Case target identity is invalid: {case['id']}")
        if not isinstance(case.get("required_evidence"), list) or not case["required_evidence"]:
            raise SystemExit(f"Case evidence contract is missing: {case['id']}")
        if not isinstance(case.get("anti_fraud"), list) or not case["anti_fraud"]:
            raise SystemExit(f"Case anti-fraud contract is missing: {case['id']}")

    target, _ = validate_language_binding(source)
    target_by_id = {entry["id"]: entry for entry in target["skills"]}
    with (source / "COVERAGE_MATRIX.csv").open(encoding="utf-8-sig", newline="") as handle:
        coverage_rows = list(csv.DictReader(handle))
    if len(coverage_rows) != EXPECTED_SOURCE_SKILLS or [
        row.get("source_skill_id") for row in coverage_rows
    ] != EXPECTED_IDS:
        raise SystemExit("Coverage matrix must preserve 180 ordered package-local source IDs")
    cases_by_id = {case["id"]: case for case in cases}
    for row in coverage_rows:
        target_entry = target_by_id[row["source_skill_id"]]
        direct_case = cases_by_id.get(row.get("direct_case_id"))
        related = sum(
            row["source_skill_id"] in case["target_skills"]
            and case["id"] != row["direct_case_id"]
            for case in cases
        )
        if (
            row.get("source_skill_name") != target_entry.get("name")
            or int(row.get("batch", 0)) != target_entry.get("batch")
            or not isinstance(direct_case, dict)
            or direct_case.get("category") != "source-skill-direct"
            or direct_case.get("target_skills") != [row["source_skill_id"]]
            or int(row.get("related_case_count", 0)) != related
        ):
            raise SystemExit(f"Coverage binding is invalid: {row['source_skill_id']}")
    return manifest, test_skills, cases


def result_record(
    case: dict[str, Any],
    target_manifest_digest: str,
    language_install_digest: str,
) -> dict[str, Any]:
    return {
        "case_id": case["id"],
        "test_skill_id": case["test_skill_id"],
        "batch": case.get("batch"),
        "severity": case["severity"].upper(),
        "target_skills": case["target_skills"],
        "source_case_digest": canonical_digest(case),
        "target_manifest_digest": target_manifest_digest,
        "language_install_manifest_digest": language_install_digest,
        "status": "NOT_RUN",
        "evidence_complete": False,
        "deterministic_repeat_runs": 0,
        "source_digest": None,
        "environment_digest": None,
        "fixture_digest": None,
        "artifact_digest": None,
        "started_at": None,
        "finished_at": None,
        "execution_kind": None,
        "replay_command": None,
        "executor": None,
        "verifier": None,
        "authorization_refs": [],
        "evidence": [],
        "findings": [],
        "flaky": False,
        "quarantined": False,
        "reason": "No authorized native case execution and independent verification evidence has been supplied.",
    }


def build_suite(source: Path, destination: Path) -> None:
    manifest, test_skills, cases = validate_source(source, require_source_zip=False)
    target, language_install = validate_language_binding(source)
    target_digest = "sha256:" + sha256_file(source / "references/TARGET_MANIFEST.json")
    language_install_digest = "sha256:" + sha256_file(LANGUAGE_INSTALL_MANIFEST)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "cases").mkdir()
    shutil.copy2(source / "CASE_CATALOG.json", destination / "cases/catalog.json")
    shutil.copy2(source / "COVERAGE_MATRIX.csv", destination / "coverage-matrix.csv")
    shutil.copy2(source / "references/STRICTNESS_PROFILE.json", destination / "strictness-profile.json")
    shutil.copy2(source / "references/TARGET_MANIFEST.json", destination / "target-manifest.json")

    installed_by_id = {entry["source_id"]: entry for entry in language_install["skills"]}
    with (source / "COVERAGE_MATRIX.csv").open(encoding="utf-8-sig", newline="") as handle:
        source_coverage = list(csv.DictReader(handle))
    coverage_rows = []
    for row in source_coverage:
        binding = installed_by_id[row["source_skill_id"]]
        coverage_rows.append(
            {
                "source_id": row["source_skill_id"],
                "source_key": binding["source_key"],
                "source_name": row["source_skill_name"],
                "source_batch": int(row["batch"]),
                "source_sha256": binding["source_sha256"],
                "installed_alias": binding["installed_name"],
                "installed_sha256": binding["installed_sha256"],
                "direct_case_id": row["direct_case_id"],
                "related_case_count": int(row["related_case_count"]),
                "test_skill_id": row["test_skill_id"],
            }
        )
    coverage = {
        "schema_version": "1.0",
        "suite_id": SUITE_ID,
        "source_namespace": "package-local-language-pack",
        "source_skill_count": EXPECTED_SOURCE_SKILLS,
        "direct_coverage_edges": EXPECTED_SOURCE_SKILLS,
        "total_target_edges": sum(len(case["target_skills"]) for case in cases),
        "rows": coverage_rows,
    }
    (destination / "coverage-matrix.json").write_text(dump_json(coverage), encoding="utf-8")

    result_catalog = {
        "schema_version": "elmos.batch81-95-test-results.v1",
        "suite_id": SUITE_ID,
        "run_id": "batch81-95-initial-not-run",
        "result_count": EXPECTED_CASES,
        "target_manifest_digest": target_digest,
        "language_install_manifest_digest": language_install_digest,
        "results": [
            result_record(case, target_digest, language_install_digest) for case in cases
        ],
    }
    (destination / "results").mkdir()
    (destination / "results/catalog.json").write_text(dump_json(result_catalog), encoding="utf-8")
    (destination / "evidence").mkdir()
    (destination / "evidence/README.md").write_text(
        "# External evidence\n\nNo native, vendor, hardware, production, or independent evidence is checked in.\n",
        encoding="utf-8",
    )

    suite = {
        "schema_version": "1.0",
        "suite_id": SUITE_ID,
        "version": "1.0.0",
        "batches": list(range(81, 96)),
        "source_namespace": "package-local-language-pack",
        "source_id_range": ["PG223", "PG402"],
        "source_skill_count": EXPECTED_SOURCE_SKILLS,
        "test_skill_count": EXPECTED_TEST_SKILLS,
        "case_count": EXPECTED_CASES,
        "direct_coverage_edges": EXPECTED_SOURCE_SKILLS,
        "total_target_edges": coverage["total_target_edges"],
        "authority": "supplemental-design-and-local-engineering-only",
        "replaces_batch1_37_strict_suite": False,
        "certification_authority": False,
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
        "source_evaluator_authoritative": False,
        "source_evaluator_note": "The supplied evaluator does not enforce exact 640-result completeness or fail-closed NOT_RUN records.",
        "source_package": "../../elmos-batch81-95-slightly-strict-test-skills",
        "case_catalog": "cases/catalog.json",
        "coverage_matrix": "coverage-matrix.json",
        "source_coverage_matrix": "coverage-matrix.csv",
        "target_manifest": "target-manifest.json",
        "strictness_profile": "strictness-profile.json",
        "result_catalog": "results/catalog.json",
        "control_manifest": "control-manifest.json",
        "gate": "../../scripts/test-suite/run_batch81_95_language_pack_gate.py",
        "default_decision": "BLOCKED",
        "field_evidence_status": "NOT_RUN",
        "source_test_skill_range": [test_skills[0]["id"], test_skills[-1]["id"]],
        "source_test_package_manifest_digest": "sha256:" + sha256_file(source / "manifest.json"),
        "source_file_manifest_digest": "sha256:" + sha256_file(source / "package-manifest.json"),
        "target_manifest_digest": target_digest,
        "language_install_manifest_digest": language_install_digest,
        "declared_source_zip_sha256": manifest["source_package_sha256"],
    }
    (destination / "suite.json").write_text(dump_json(suite), encoding="utf-8")
    controlled_files = {}
    for relative in (
        "suite.json",
        "cases/catalog.json",
        "coverage-matrix.csv",
        "coverage-matrix.json",
        "strictness-profile.json",
        "target-manifest.json",
    ):
        controlled_files[relative] = "sha256:" + sha256_file(destination / relative)
    controls = {
        "manifest_version": 1,
        "suite_id": SUITE_ID,
        "source_test_package": {
            "package": PACKAGE_NAME,
            "manifest_sha256": "sha256:" + sha256_file(source / "manifest.json"),
            "file_manifest_sha256": "sha256:" + sha256_file(source / "package-manifest.json"),
            "sha256s_sha256": "sha256:" + sha256_file(source / "SHA256SUMS.txt"),
            "declared_source_zip_sha256": EXPECTED_SOURCE_ZIP_SHA256,
        },
        "language_package": {
            "package": target["package"],
            "namespace": "package-local-language-pack",
            "target_manifest_sha256": target_digest,
            "install_manifest_sha256": language_install_digest,
        },
        "controlled_files": controlled_files,
    }
    (destination / "control-manifest.json").write_text(dump_json(controls), encoding="utf-8")


def suite_definitions_match(source: Path) -> bool:
    if not SUITE_ROOT.is_dir():
        return False
    with tempfile.TemporaryDirectory() as temporary:
        expected = Path(temporary) / "suite"
        build_suite(source, expected)
        ignored = {"results/catalog.json"}
        expected_files = {
            path.relative_to(expected).as_posix(): sha256_file(path)
            for path in expected.rglob("*")
            if path.is_file() and path.relative_to(expected).as_posix() not in ignored
        }
        installed_files = {
            path.relative_to(SUITE_ROOT).as_posix(): sha256_file(path)
            for path in SUITE_ROOT.rglob("*")
            if path.is_file()
            and path.relative_to(SUITE_ROOT).as_posix() not in ignored
            and not path.relative_to(SUITE_ROOT).as_posix().startswith("evidence/")
        }
        expected_files = {
            key: value for key, value in expected_files.items() if not key.startswith("evidence/")
        }
        return installed_files == expected_files


def legacy_suite_is_replaceable() -> bool:
    try:
        suite = load_json(SUITE_ROOT / "suite.json")
        results = load_json(SUITE_ROOT / "results/catalog.json").get("results", [])
        return (
            suite.get("suite_id") == "batch81-95-language-packs-slightly-strict-supplemental"
            and suite.get("case_count") == 120
            and len(results) == 120
            and all(result.get("status") == "NOT_RUN" for result in results)
        )
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        return False


def install_suite(source: Path) -> bool:
    if suite_definitions_match(source):
        return False
    if SUITE_ROOT.exists() and not legacy_suite_is_replaceable():
        raise SystemExit(
            "Refusing to replace Batch 81-95 suite because it is not the known 120-case all-NOT_RUN design"
        )
    replaced = SUITE_ROOT.exists()
    if replaced:
        shutil.rmtree(SUITE_ROOT)
    with tempfile.TemporaryDirectory() as temporary:
        generated = Path(temporary) / "suite"
        build_suite(source, generated)
        shutil.copytree(generated, SUITE_ROOT)
    return replaced


def expected_install_manifest(
    source: Path,
    test_skills: list[dict[str, Any]],
    generator: ModuleType,
) -> dict[str, Any]:
    installed = []
    for entry in test_skills:
        name = entry["name"]
        source_skill = source / f"agent-skills/runtime/{name}/SKILL.md"
        source_cases = source / f"agent-skills/runtime/{name}/cases.json"
        runtime_skill = RUNTIME_ROOT / name / "SKILL.md"
        runtime_cases = RUNTIME_ROOT / name / "cases.json"
        runtime_interface = runtime_skill.parent / "agents/openai.yaml"
        codex_skill = CODEX_SKILL_ROOT / name / "SKILL.md"
        codex_cases = CODEX_SKILL_ROOT / name / "cases.json"
        codex_interface = codex_skill.parent / "agents/openai.yaml"
        interface_digest = "sha256:" + hashlib.sha256(
            expected_interface(name, generator).encode("utf-8")
        ).hexdigest()
        installed.append(
            {
                "source_id": entry["id"],
                "source_name": name,
                "source_kind": entry["kind"],
                "source_batch": entry.get("batch"),
                "source_skill_path": source_skill.relative_to(source).as_posix(),
                "source_skill_sha256": "sha256:" + sha256_file(source_skill),
                "source_cases_path": source_cases.relative_to(source).as_posix(),
                "source_cases_sha256": "sha256:" + sha256_file(source_cases),
                "runtime_skill_path": runtime_skill.relative_to(ROOT).as_posix(),
                "runtime_skill_sha256": "sha256:" + sha256_file(runtime_skill),
                "runtime_cases_path": runtime_cases.relative_to(ROOT).as_posix(),
                "runtime_cases_sha256": "sha256:" + sha256_file(runtime_cases),
                "runtime_interface_path": runtime_interface.relative_to(ROOT).as_posix(),
                "runtime_interface_sha256": interface_digest,
                "codex_skill_path": codex_skill.relative_to(ROOT).as_posix(),
                "codex_skill_sha256": "sha256:" + sha256_file(codex_skill),
                "codex_cases_path": codex_cases.relative_to(ROOT).as_posix(),
                "codex_cases_sha256": "sha256:" + sha256_file(codex_cases),
                "codex_interface_path": codex_interface.relative_to(ROOT).as_posix(),
                "codex_interface_sha256": interface_digest,
            }
        )
    return {
        "manifest_version": 1,
        "package": PACKAGE_NAME,
        "canonical_package": PACKAGE_ROOT.relative_to(ROOT).as_posix(),
        "file_count": EXPECTED_FILES,
        "file_manifest_sha256": "sha256:" + sha256_file(source / "package-manifest.json"),
        "sha256s_sha256": "sha256:" + sha256_file(source / "SHA256SUMS.txt"),
        "package_manifest_sha256": "sha256:" + sha256_file(source / "manifest.json"),
        "declared_source_zip_sha256": EXPECTED_SOURCE_ZIP_SHA256,
        "source_zip_verified_at_import": True,
        "source_namespace": "package-local-language-pack",
        "source_skills": EXPECTED_SOURCE_SKILLS,
        "test_skills": EXPECTED_TEST_SKILLS,
        "cases": EXPECTED_CASES,
        "initial_result_status": "NOT_RUN",
        "source_evaluator_authoritative": False,
        "certification_authority": False,
        "maximum_repository_decision": "READY_FOR_EXTERNAL_GATE",
        "installed_skills": installed,
    }


def install(source: Path) -> None:
    inventory = validate_file_inventory(source)
    _, test_skills, _ = validate_source(source, require_source_zip=True)
    generator = load_generator()
    for extra in ("package-manifest.json", "SHA256SUMS.txt", "VALIDATION_REPORT.json"):
        copy_exact(source / extra, PACKAGE_ROOT / extra)
    for relative in sorted(inventory):
        copy_exact(source / relative, PACKAGE_ROOT / relative)
    for entry in test_skills:
        name = entry["name"]
        source_skill = source / f"agent-skills/runtime/{name}/SKILL.md"
        source_cases = source / f"agent-skills/runtime/{name}/cases.json"
        normalized = normalized_skill_text(source_skill, entry, generator)
        for root in (RUNTIME_ROOT, CODEX_SKILL_ROOT):
            skill_dir = root / name
            skill = skill_dir / "SKILL.md"
            if skill.exists():
                if skill.read_text(encoding="utf-8") != normalized:
                    raise SystemExit(f"Refusing to overwrite different normalized test Skill: {skill}")
            else:
                skill_dir.mkdir(parents=True, exist_ok=True)
                skill.write_text(normalized, encoding="utf-8")
            copy_exact(source_cases, skill_dir / "cases.json")
            install_interface(skill_dir, name, generator)
    replaced = install_suite(source)
    expected = expected_install_manifest(source, test_skills, generator)
    if INSTALL_MANIFEST.exists():
        if load_json(INSTALL_MANIFEST) != expected:
            raise SystemExit(f"Refusing to overwrite different install manifest: {INSTALL_MANIFEST}")
    else:
        INSTALL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        INSTALL_MANIFEST.write_text(dump_json(expected), encoding="utf-8")
    verify_install(PACKAGE_ROOT)
    print(
        json.dumps(
            {
                "status": "imported-and-verified",
                "files": EXPECTED_FILES,
                "source_skills": EXPECTED_SOURCE_SKILLS,
                "test_skills": EXPECTED_TEST_SKILLS,
                "cases": EXPECTED_CASES,
                "legacy_120_case_not_run_suite_replaced": replaced,
            },
            sort_keys=True,
        )
    )


def verify_install(source: Path = PACKAGE_ROOT) -> None:
    _, test_skills, _ = validate_source(source, require_source_zip=False)
    generator = load_generator()
    if not suite_definitions_match(source):
        raise SystemExit("Integrated Batch 81-95 suite definitions differ from the canonical test package")
    results = load_json(SUITE_ROOT / "results/catalog.json").get("results", [])
    if len(results) != EXPECTED_CASES or [result.get("case_id") for result in results] != [
        f"CASE-{number:04d}" for number in range(1, 641)
    ]:
        raise SystemExit("Integrated Batch 81-95 result set is incomplete or reordered")
    for entry in test_skills:
        name = entry["name"]
        source_skill = source / f"agent-skills/runtime/{name}/SKILL.md"
        source_cases = source / f"agent-skills/runtime/{name}/cases.json"
        normalized = normalized_skill_text(source_skill, entry, generator)
        for root in (RUNTIME_ROOT, CODEX_SKILL_ROOT):
            skill_dir = root / name
            skill = skill_dir / "SKILL.md"
            cases = skill_dir / "cases.json"
            interface = skill_dir / "agents/openai.yaml"
            if not skill.is_file() or skill.read_text(encoding="utf-8") != normalized:
                raise SystemExit(f"Normalized test Skill is missing or changed: {skill}")
            if not cases.is_file() or sha256_file(cases) != sha256_file(source_cases):
                raise SystemExit(f"Installed test Skill cases are missing or changed: {cases}")
            if not interface.is_file() or interface.read_text(encoding="utf-8") != expected_interface(
                name, generator
            ):
                raise SystemExit(f"Installed test Skill interface is missing or changed: {interface}")
    expected = expected_install_manifest(source, test_skills, generator)
    if not INSTALL_MANIFEST.is_file() or load_json(INSTALL_MANIFEST) != expected:
        raise SystemExit("Batch 81-95 test-package install manifest is missing or changed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=None, help="Source test distribution")
    parser.add_argument("--check", action="store_true", help="Verify the imported integration")
    args = parser.parse_args()
    if args.check:
        verify_install()
        print(
            json.dumps(
                {
                    "status": "verified",
                    "files": EXPECTED_FILES,
                    "source_skills": EXPECTED_SOURCE_SKILLS,
                    "test_skills": EXPECTED_TEST_SKILLS,
                    "cases": EXPECTED_CASES,
                },
                sort_keys=True,
            )
        )
        return 0
    source = (
        args.source
        if args.source is not None
        else Path("/Users/stephen/Downloads") / PACKAGE_NAME
    ).resolve()
    install(source)
    return 0


if __name__ == "__main__":
    sys.exit(main())
