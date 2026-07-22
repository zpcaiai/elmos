#!/usr/bin/env python3
"""Import and verify the immutable Batch 66-80 slightly-strict test package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "elmos-codex-skills-batch66-80-slightly-strict-tests"
PACKAGE_ROOT = ROOT / PACKAGE_NAME
RUNTIME_ROOT = ROOT / "agent-skills" / "runtime"
CODEX_SKILL_ROOT = ROOT / ".agents" / "skills"
SUITE_ROOT = ROOT / "test-suites" / "batch66-80-slightly-strict"
INSTALL_MANIFEST = ROOT / "docs" / "test-suite-b66-80" / "source-install-manifest.json"
SKILL_GENERATOR = Path(
    "/Users/stephen/.codex/skills/.system/skill-creator/scripts/generate_openai_yaml.py"
)
EXPECTED_FILES = 544
EXPECTED_TEST_SKILLS = 35
EXPECTED_CASES = 450
EXPECTED_SOURCE_SKILLS = 195
EXPECTED_IDS = [f"PG{number:03d}" for number in range(223, 418)]
INTEGRATED_PREFIXES = (
    "docs/test-suite-b66-80/",
    "schemas/test-suite-b66-80/",
    "scripts/test-suite-b66-80/",
    "templates/test-suite-b66-80/",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def load_generator() -> ModuleType:
    if not SKILL_GENERATOR.is_file():
        raise SystemExit(f"Skill interface generator is missing: {SKILL_GENERATOR}")
    spec = importlib.util.spec_from_file_location("batch66_80_test_interface_generator", SKILL_GENERATOR)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load Skill interface generator: {SKILL_GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_interface(name: str, generator: ModuleType) -> str:
    return "\n".join(
        [
            "interface:",
            f"  display_name: {generator.yaml_quote(generator.format_display_name(name))}",
            "  short_description: "
            + generator.yaml_quote("Run this ELMOS Batch 66-80 test Skill with evidence"),
            "  default_prompt: "
            + generator.yaml_quote(
                f"Use ${name} to run the exact Batch 66-80 test scope with fail-closed evidence."
            ),
            "",
        ]
    )


def read_file_inventory(source: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest_path = source / "FILE_MANIFEST.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Source FILE_MANIFEST.json is missing: {source}")
    manifest = load_json(manifest_path)
    if manifest.get("package") != PACKAGE_NAME:
        raise SystemExit("Test package identity is invalid")
    entries = manifest.get("files")
    if manifest.get("file_count") != EXPECTED_FILES or not isinstance(entries, list):
        raise SystemExit(f"Test package must declare exactly {EXPECTED_FILES} files")
    by_path: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("Test package file inventory contains a non-object")
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative or relative in by_path:
            raise SystemExit(f"Invalid or duplicate test-package file path: {relative!r}")
        path = safe_path(source, relative)
        if not path.is_file():
            raise SystemExit(f"Test package file is missing: {relative}")
        if path.stat().st_size != entry.get("size_bytes"):
            raise SystemExit(f"Test package file size mismatch: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            raise SystemExit(f"Test package file digest mismatch: {relative}")
        by_path[relative] = entry
    if len(by_path) != EXPECTED_FILES:
        raise SystemExit(f"Test package must contain {EXPECTED_FILES} unique manifest entries")
    return manifest, by_path


def read_source_hashes(source: Path) -> list[dict[str, str]]:
    with (source / "SOURCE_SKILL_HASHES.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != EXPECTED_SOURCE_SKILLS:
        raise SystemExit("SOURCE_SKILL_HASHES.csv must contain exactly 195 rows")
    if [row.get("id") for row in rows] != EXPECTED_IDS:
        raise SystemExit("SOURCE_SKILL_HASHES.csv must cover contiguous PG223-PG417")
    names = [row.get("name") for row in rows]
    if len(set(names)) != EXPECTED_SOURCE_SKILLS:
        raise SystemExit("SOURCE_SKILL_HASHES.csv contains duplicate source Skill names")
    for row in rows:
        path_text = row.get("path")
        digest = row.get("source_sha256")
        if not isinstance(path_text, str) or not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
            raise SystemExit(f"Invalid source Skill hash row: {row.get('id')}")
        runtime_path = safe_path(ROOT, path_text)
        if not runtime_path.is_file() or sha256_file(runtime_path) != digest:
            raise SystemExit(f"Current Runtime Skill differs from supplied source hash: {row['id']}")
    return rows


def validate_source(source: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    _, inventory = read_file_inventory(source)
    package_manifest = load_json(source / "manifest.json")
    if package_manifest.get("package") != PACKAGE_NAME:
        raise SystemExit("manifest.json package identity is invalid")
    if package_manifest.get("test_skill_count") != EXPECTED_TEST_SKILLS:
        raise SystemExit("manifest.json must declare exactly 35 test Skills")
    if package_manifest.get("case_count") != EXPECTED_CASES:
        raise SystemExit("manifest.json must declare exactly 450 cases")
    if package_manifest.get("source_skill_count") != EXPECTED_SOURCE_SKILLS:
        raise SystemExit("manifest.json must declare exactly 195 source Skills")
    if package_manifest.get("batches") != list(range(66, 81)):
        raise SystemExit("manifest.json must cover exactly Batch 66-80")
    skills = package_manifest.get("skills")
    if not isinstance(skills, list) or len(skills) != EXPECTED_TEST_SKILLS:
        raise SystemExit("manifest.json Skill inventory is incomplete")
    names: set[str] = set()
    codes: set[str] = set()
    for skill in skills:
        name = skill.get("name")
        code = skill.get("code")
        relative = skill.get("path")
        if (
            not isinstance(name, str)
            or not isinstance(code, str)
            or not isinstance(relative, str)
            or name in names
            or code in codes
            or len(name) > 64
        ):
            raise SystemExit(f"Invalid or duplicate test Skill entry: {skill!r}")
        if relative not in inventory or not (source / relative).is_file():
            raise SystemExit(f"Test Skill is absent from FILE_MANIFEST.json: {name}")
        names.add(name)
        codes.add(code)
    source_rows = read_source_hashes(source)
    suite = load_json(source / "test-suites/batch66-80-slightly-strict/suite.json")
    if (
        suite.get("suite_id") != "batch66-80-slightly-strict"
        or suite.get("test_skill_count") != EXPECTED_TEST_SKILLS
        or suite.get("case_count") != EXPECTED_CASES
        or suite.get("source_skill_count") != EXPECTED_SOURCE_SKILLS
    ):
        raise SystemExit("Source suite identity or exact counts are invalid")
    return package_manifest, skills, source_rows


def copy_exact(source: Path, destination: Path) -> None:
    if destination.exists():
        if destination.is_file() and sha256_file(destination) == sha256_file(source):
            return
        raise SystemExit(f"Refusing to overwrite different destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def legacy_suite_is_replaceable() -> bool:
    try:
        suite = load_json(SUITE_ROOT / "suite.json")
        results = load_json(SUITE_ROOT / "results" / "catalog.json").get("results", [])
        return (
            suite.get("suite_id") == "batch66-80-slightly-strict-supplemental"
            and suite.get("case_count") == 120
            and len(results) == 120
            and all(result.get("status") == "NOT_RUN" for result in results)
        )
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        return False


def suite_definitions_match_source(source: Path) -> bool:
    source_suite = source / "test-suites" / "batch66-80-slightly-strict"
    if not SUITE_ROOT.is_dir():
        return False
    mutable = ("results/", "evidence/")
    source_files = {
        path.relative_to(source_suite).as_posix(): sha256_file(path)
        for path in source_suite.rglob("*")
        if path.is_file()
        and not path.relative_to(source_suite).as_posix().startswith(mutable)
        and path.relative_to(source_suite).as_posix() != "release-gate.json"
    }
    installed_files = {
        path.relative_to(SUITE_ROOT).as_posix(): sha256_file(path)
        for path in SUITE_ROOT.rglob("*")
        if path.is_file()
        and not path.relative_to(SUITE_ROOT).as_posix().startswith(mutable)
        and path.relative_to(SUITE_ROOT).as_posix() != "release-gate.json"
    }
    return source_files == installed_files


def result_file_set_matches_source(source: Path) -> bool:
    source_results = source / "test-suites" / "batch66-80-slightly-strict" / "results"
    return {path.name for path in source_results.glob("*.json")} == {
        path.name for path in (SUITE_ROOT / "results").glob("*.json")
    }


def install_suite(source: Path) -> bool:
    source_suite = source / "test-suites" / "batch66-80-slightly-strict"
    if suite_definitions_match_source(source) and result_file_set_matches_source(source):
        return False
    replaced_legacy = False
    if SUITE_ROOT.exists():
        if not legacy_suite_is_replaceable():
            raise SystemExit(
                "Refusing to replace Batch 66-80 suite because it is not the known 120-case all-NOT_RUN design"
            )
        shutil.rmtree(SUITE_ROOT)
        replaced_legacy = True
    shutil.copytree(source_suite, SUITE_ROOT)
    return replaced_legacy


def install_interface(skill_dir: Path, name: str, generator: ModuleType) -> None:
    interface = skill_dir / "agents" / "openai.yaml"
    expected = expected_interface(name, generator)
    if interface.exists():
        if interface.is_file() and interface.read_text(encoding="utf-8") == expected:
            return
        raise SystemExit(f"Refusing to overwrite different test Skill interface: {interface}")
    result = generator.write_openai_yaml(
        skill_dir,
        name,
        [
            "short_description=Run this ELMOS Batch 66-80 test Skill with evidence",
            "default_prompt="
            + f"Use ${name} to run the exact Batch 66-80 test scope with fail-closed evidence.",
        ],
    )
    if result is None or interface.read_text(encoding="utf-8") != expected:
        raise SystemExit(f"Test Skill interface generation failed: {name}")


def expected_install_manifest(
    source: Path,
    package_manifest: dict[str, Any],
    skills: list[dict[str, Any]],
    generator: ModuleType,
) -> dict[str, Any]:
    installed_skills = []
    for skill in skills:
        name = skill["name"]
        source_skill = source / skill["path"]
        installed_skill = RUNTIME_ROOT / name / "SKILL.md"
        interface = installed_skill.parent / "agents" / "openai.yaml"
        codex_skill = CODEX_SKILL_ROOT / name / "SKILL.md"
        codex_interface = codex_skill.parent / "agents" / "openai.yaml"
        installed_skills.append(
            {
                "batch": skill["batch"],
                "code": skill["code"],
                "name": name,
                "source_path": skill["path"],
                "source_sha256": "sha256:" + sha256_file(source_skill),
                "installed_path": installed_skill.relative_to(ROOT).as_posix(),
                "installed_sha256": "sha256:" + sha256_file(installed_skill),
                "interface_path": interface.relative_to(ROOT).as_posix(),
                "interface_sha256": "sha256:"
                + hashlib.sha256(expected_interface(name, generator).encode("utf-8")).hexdigest(),
                "codex_skill_path": codex_skill.relative_to(ROOT).as_posix(),
                "codex_skill_sha256": "sha256:" + sha256_file(codex_skill),
                "codex_interface_path": codex_interface.relative_to(ROOT).as_posix(),
                "codex_interface_sha256": "sha256:"
                + hashlib.sha256(expected_interface(name, generator).encode("utf-8")).hexdigest(),
            }
        )
    return {
        "manifest_version": 2,
        "package": PACKAGE_NAME,
        "canonical_package": PACKAGE_ROOT.relative_to(ROOT).as_posix(),
        "file_manifest_sha256": "sha256:" + sha256_file(source / "FILE_MANIFEST.json"),
        "package_manifest_sha256": "sha256:" + sha256_file(source / "manifest.json"),
        "source_skill_hashes_sha256": "sha256:" + sha256_file(source / "SOURCE_SKILL_HASHES.csv"),
        "source_package": package_manifest["source_package"],
        "source_skills": EXPECTED_SOURCE_SKILLS,
        "test_skills": EXPECTED_TEST_SKILLS,
        "cases": EXPECTED_CASES,
        "initial_result_status": "not-run",
        "certification_authority": False,
        "maximum_repository_decision": "READY_FOR_EXTERNAL_GATE",
        "installed_skills": installed_skills,
    }


def install(source: Path) -> None:
    file_manifest, inventory = read_file_inventory(source)
    package_manifest, skills, _ = validate_source(source)
    generator = load_generator()
    copy_exact(source / "FILE_MANIFEST.json", PACKAGE_ROOT / "FILE_MANIFEST.json")
    for relative in sorted(inventory):
        copy_exact(source / relative, PACKAGE_ROOT / relative)
    for skill in skills:
        name = skill["name"]
        installed_skill = RUNTIME_ROOT / name / "SKILL.md"
        copy_exact(source / skill["path"], installed_skill)
        install_interface(installed_skill.parent, name, generator)
        codex_skill = CODEX_SKILL_ROOT / name / "SKILL.md"
        copy_exact(source / skill["path"], codex_skill)
        install_interface(codex_skill.parent, name, generator)
    for relative in sorted(inventory):
        if relative.startswith(INTEGRATED_PREFIXES):
            copy_exact(source / relative, ROOT / relative)
    replaced_legacy = install_suite(source)
    expected = expected_install_manifest(source, package_manifest, skills, generator)
    if INSTALL_MANIFEST.exists():
        current = load_json(INSTALL_MANIFEST)
        if current == expected:
            pass
        elif current.get("manifest_version") == 1 and current.get("package") == PACKAGE_NAME:
            INSTALL_MANIFEST.write_text(dump_json(expected), encoding="utf-8")
        else:
            raise SystemExit(f"Refusing to overwrite different install manifest: {INSTALL_MANIFEST}")
    else:
        INSTALL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        INSTALL_MANIFEST.write_text(dump_json(expected), encoding="utf-8")
    verify_install(PACKAGE_ROOT)
    result = {
        "status": "imported-and-verified",
        "files": file_manifest["file_count"],
        "source_skills": EXPECTED_SOURCE_SKILLS,
        "test_skills": EXPECTED_TEST_SKILLS,
        "cases": EXPECTED_CASES,
        "legacy_120_case_not_run_suite_replaced": replaced_legacy,
    }
    print(json.dumps(result, sort_keys=True))


def verify_integrated_files(source: Path, inventory: dict[str, dict[str, Any]]) -> None:
    for relative, entry in inventory.items():
        if relative.startswith(INTEGRATED_PREFIXES):
            installed = ROOT / relative
            if (
                not installed.is_file()
                or installed.stat().st_size != entry["size_bytes"]
                or sha256_file(installed) != entry["sha256"]
            ):
                raise SystemExit(f"Integrated test asset is missing or changed: {relative}")


def verify_install(source: Path = PACKAGE_ROOT) -> None:
    package_manifest, skills, _ = validate_source(source)
    _, inventory = read_file_inventory(source)
    generator = load_generator()
    verify_integrated_files(source, inventory)
    if not suite_definitions_match_source(source):
        raise SystemExit("Integrated Batch 66-80 suite definitions differ from the canonical test package")
    if not result_file_set_matches_source(source):
        raise SystemExit("Integrated Batch 66-80 result file set is incomplete or contains extras")
    for skill in skills:
        name = skill["name"]
        canonical = source / skill["path"]
        installed = RUNTIME_ROOT / name / "SKILL.md"
        interface = installed.parent / "agents" / "openai.yaml"
        codex_skill = CODEX_SKILL_ROOT / name / "SKILL.md"
        codex_interface = codex_skill.parent / "agents" / "openai.yaml"
        if not installed.is_file() or sha256_file(installed) != sha256_file(canonical):
            raise SystemExit(f"Installed test Skill is missing or changed: {name}")
        if not interface.is_file() or interface.read_text(encoding="utf-8") != expected_interface(
            name, generator
        ):
            raise SystemExit(f"Installed test Skill interface is missing or changed: {name}")
        if not codex_skill.is_file() or sha256_file(codex_skill) != sha256_file(canonical):
            raise SystemExit(f"Repository Codex test Skill is missing or changed: {name}")
        if (
            not codex_interface.is_file()
            or codex_interface.read_text(encoding="utf-8") != expected_interface(name, generator)
        ):
            raise SystemExit(f"Repository Codex test Skill interface is missing or changed: {name}")
    expected = expected_install_manifest(source, package_manifest, skills, generator)
    if not INSTALL_MANIFEST.is_file() or load_json(INSTALL_MANIFEST) != expected:
        raise SystemExit("Batch 66-80 test-package install manifest is missing or changed")


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
