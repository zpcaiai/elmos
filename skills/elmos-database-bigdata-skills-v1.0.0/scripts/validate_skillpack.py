#!/usr/bin/env python3
"""Validate structure, schemas, selectors, dependency graph and checksums."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import py_compile
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

try:
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover - explicit dependency diagnostic
    raise SystemExit("jsonschema is required to run the full validator: python3 -m pip install jsonschema") from exc

ROOT = Path(__file__).resolve().parents[1]
SAFE_SKILL = re.compile(r"^elmos-[a-z0-9][a-z0-9-]*$")
TASK_ID = re.compile(r"\*\*([A-Z][A-Z0-9]*-\d{3})\*\*")
REQUIRED_SKILL_SECTIONS = [
    "## 目标",
    "## 适用触发条件",
    "## 输入",
    "## 执行流程",
    "## 强制决策规则",
    "## 必需产物",
    "## 验收标准",
    "## 失败、降级与恢复",
    "## 完成检查表",
]
EXCLUDED_FROM_MANIFEST = {"MANIFEST.json", "VALIDATION-REPORT.md"}


@dataclass
class Result:
    checks: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def check(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.errors.append(message)

    def warn(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.warnings.append(message)


def load_json(path: Path, result: Result) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result.errors.append(f"Cannot parse JSON {path}: {exc}")
        return {}
    result.checks += 1
    if not isinstance(data, dict):
        result.errors.append(f"Expected JSON object: {path}")
        return {}
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_frontmatter(path: Path, result: Result) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        result.errors.append(f"Cannot read {path}: {exc}")
        return {}
    result.checks += 1
    if not text.startswith("---\n"):
        result.errors.append(f"Missing frontmatter: {path}")
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        result.errors.append(f"Unterminated frontmatter: {path}")
        return {}
    meta: Dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            result.errors.append(f"Unsupported frontmatter line in {path}: {line}")
            continue
        key, raw = line.split(":", 1)
        key, raw = key.strip(), raw.strip()
        try:
            value = json.loads(raw) if raw.startswith("[") else raw.strip('"\'')
        except json.JSONDecodeError as exc:
            result.errors.append(f"Invalid frontmatter JSON list in {path}: {exc}")
            value = None
        meta[key] = value
    return meta


def topological_check(graph: Mapping[str, Sequence[str]], result: Result) -> None:
    visiting: Set[str] = set()
    visited: Set[str] = set()

    def visit(name: str, trail: List[str]) -> None:
        if name in visited:
            return
        if name in visiting:
            result.errors.append("Dependency cycle: " + " -> ".join(trail + [name]))
            return
        visiting.add(name)
        for dep in graph.get(name, []):
            visit(dep, trail + [name])
        visiting.remove(name)
        visited.add(name)

    for name in graph:
        visit(name, [])
    result.checks += 1


def expand(requested: Iterable[str], graph: Mapping[str, Sequence[str]]) -> Set[str]:
    expanded: Set[str] = set()

    def visit(name: str) -> None:
        if name in expanded:
            return
        expanded.add(name)
        for dep in graph[name]:
            visit(dep)

    for item in requested:
        visit(item)
    return expanded


def validate_skills(root: Path, manifest: Dict[str, Any], result: Result) -> Dict[str, List[str]]:
    skills_root = root / "skills"
    directories = sorted(p for p in skills_root.iterdir() if p.is_dir()) if skills_root.is_dir() else []
    expected_count = manifest.get("skill_count", 46)
    result.check(len(directories) == expected_count == 46, f"Expected 46 skills, found {len(directories)}; manifest={expected_count}")
    graph: Dict[str, List[str]] = {}
    task_locations: Dict[str, Path] = {}
    group_count: Counter[str] = Counter()

    for directory in directories:
        result.check(bool(SAFE_SKILL.fullmatch(directory.name)), f"Unsafe skill directory name: {directory.name}")
        skill_md = directory / "SKILL.md"
        result.check(skill_md.is_file(), f"Missing SKILL.md: {directory}")
        if not skill_md.is_file():
            continue
        meta = parse_frontmatter(skill_md, result)
        for key in ("name", "description", "version", "group", "dependencies", "triggers", "outputs"):
            result.check(key in meta, f"Missing frontmatter key '{key}' in {skill_md}")
        result.check(meta.get("name") == directory.name, f"Skill name mismatch in {skill_md}")
        result.check(meta.get("version") == manifest.get("package_version", "1.0.0"), f"Version mismatch in {skill_md}")
        dependencies = meta.get("dependencies", [])
        result.check(isinstance(dependencies, list) and all(isinstance(x, str) for x in dependencies), f"Invalid dependencies in {skill_md}")
        graph[directory.name] = list(dependencies) if isinstance(dependencies, list) else []
        group_count[str(meta.get("group"))] += 1
        text = skill_md.read_text(encoding="utf-8")
        for section in REQUIRED_SKILL_SECTIONS:
            result.check(section in text, f"Missing section '{section}' in {skill_md}")
        ids = TASK_ID.findall(text)
        result.check(len(ids) >= 6, f"Too few stable task IDs in {skill_md}")
        for task_id in ids:
            if task_id in task_locations:
                result.errors.append(f"Duplicate task ID {task_id}: {task_locations[task_id]} and {skill_md}")
            else:
                task_locations[task_id] = skill_md

    known = set(graph)
    for name, deps in graph.items():
        missing = sorted(set(deps) - known)
        result.check(not missing, f"Skill {name} has missing dependencies: {missing}")
    topological_check(graph, result)
    result.check(dict(sorted(group_count.items())) == manifest.get("group_counts"), "Manifest group_counts do not match skill frontmatter")
    manifest_skills = {item.get("name") for item in manifest.get("skills", []) if isinstance(item, dict)}
    result.check(manifest_skills == known, "Manifest skill list differs from skills directory")
    result.notes.append(f"Validated {len(graph)} skills, {len(task_locations)} globally unique task IDs and an acyclic dependency graph.")
    return graph


def validate_profiles(root: Path, graph: Mapping[str, Sequence[str]], manifest: Dict[str, Any], result: Result) -> None:
    profiles: Dict[str, Dict[str, Any]] = {}
    for path in sorted((root / "profiles").glob("*.json")):
        data = load_json(path, result)
        name = path.stem
        result.check(data.get("profile") == name, f"Profile name mismatch: {path}")
        declared = data.get("skills", [])
        result.check(isinstance(declared, list) and all(isinstance(x, str) for x in declared), f"Invalid skills list: {path}")
        unknown = sorted(set(declared) - set(graph)) if isinstance(declared, list) else []
        result.check(not unknown, f"Unknown skills in profile {name}: {unknown}")
        if not unknown and isinstance(declared, list):
            expanded = expand(declared, graph)
            result.check(set(declared).issubset(expanded), f"Profile expansion failed: {name}")
        profiles[name] = data
    result.check(len(profiles) == manifest.get("profile_count") == 10, f"Expected 10 profiles, found {len(profiles)}")
    result.check(set(profiles.get("full", {}).get("skills", [])) == set(graph), "Full profile must declare all skills")
    result.check(set(profiles) == set(manifest.get("profiles", {})), "Manifest profile list differs from profiles directory")
    result.notes.append(f"Validated {len(profiles)} install profiles and dependency expansion inputs.")


def validate_catalogs(root: Path, graph: Mapping[str, Sequence[str]], result: Result) -> Set[str]:
    catalog_root = root / "catalog"
    database = load_json(catalog_root / "database-capabilities.json", result)
    technologies = database.get("technologies", [])
    result.check(isinstance(technologies, list) and len(technologies) >= 25, "Technology catalog must contain at least 25 entries")
    technology_ids = [item.get("id") for item in technologies if isinstance(item, dict)]
    result.check(len(technology_ids) == len(set(technology_ids)), "Duplicate technology IDs")
    for item in technologies:
        if not isinstance(item, dict):
            result.errors.append("Technology entry is not an object")
            continue
        for key in ("id", "name", "technology_kind", "roles", "data_models", "deployments", "heuristic_scores_0_to_5", "official_docs", "adapter_status", "score_warning"):
            result.check(key in item, f"Technology {item.get('id')} missing {key}")
        scores = item.get("heuristic_scores_0_to_5", {})
        result.check(all(isinstance(v, (int, float)) and 0 <= v <= 5 for v in scores.values()), f"Technology scores out of range: {item.get('id')}")
        result.check(item.get("adapter_status") in {"catalog-only", "reference-generator", "verified-adapter"}, f"Invalid adapter status: {item.get('id')}")

    architecture = load_json(catalog_root / "architecture-patterns.json", result)
    patterns = architecture.get("patterns", [])
    pattern_ids = [item.get("id") for item in patterns if isinstance(item, dict)]
    result.check(len(pattern_ids) == len(set(pattern_ids)) and len(pattern_ids) >= 9, "Architecture pattern IDs must be unique")

    templates_data = load_json(catalog_root / "project-templates.json", result)
    templates = templates_data.get("templates", [])
    template_ids = [item.get("id") for item in templates if isinstance(item, dict)]
    result.check(len(templates) == 10, f"Expected 10 project templates, found {len(templates)}")
    result.check(len(template_ids) == len(set(template_ids)), "Duplicate template IDs")
    for item in templates:
        result.check(item.get("skill") in graph, f"Template references unknown skill: {item}")
        unknown_patterns = sorted(set(item.get("primary_patterns", [])) - set(pattern_ids))
        result.check(not unknown_patterns, f"Template {item.get('id')} references unknown patterns: {unknown_patterns}")

    rules = load_json(catalog_root / "selection-rules.json", result)
    result.check(bool(rules.get("hard_constraint_order")), "Selection rules missing hard constraint order")
    weights = rules.get("default_soft_weights", {})
    for role, role_weights in weights.items():
        if isinstance(role_weights, dict):
            result.warn(abs(sum(role_weights.values()) - 1.0) < 1e-9, f"Soft weights for {role} do not sum to 1.0")

    adapters_data = load_json(catalog_root / "technology-adapters.json", result)
    adapters = adapters_data.get("adapters", [])
    adapter_roles = [item.get("role") for item in adapters if isinstance(item, dict)]
    result.check(len(adapter_roles) == len(set(adapter_roles)) and len(adapter_roles) >= 10, "Technology adapter roles must be unique")
    result.notes.append(f"Validated {len(technologies)} technology seeds, {len(pattern_ids)} patterns and {len(templates)} templates.")
    return set(technology_ids)


def validate_schemas(root: Path, result: Result) -> Dict[str, Dict[str, Any]]:
    schemas: Dict[str, Dict[str, Any]] = {}
    paths = sorted((root / "schemas").glob("*.schema.json"))
    result.check(len(paths) == 7, f"Expected 7 JSON Schemas, found {len(paths)}")
    for path in paths:
        schema = load_json(path, result)
        try:
            Draft202012Validator.check_schema(schema)
            result.checks += 1
        except Exception as exc:
            result.errors.append(f"Invalid JSON Schema {path}: {exc}")
        schemas[path.name] = schema
    result.notes.append(f"Validated {len(paths)} Draft 2020-12 schemas.")
    return schemas


def validate_instance(instance: Any, schema: Dict[str, Any], label: str, result: Result) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda e: list(e.absolute_path))
    result.check(not errors, f"Schema validation failed for {label}: {errors[0].message if errors else ''}")


def run_tool(command: List[str], result: Result) -> Dict[str, Any]:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    result.check(completed.returncode == 0, f"Tool failed ({' '.join(command)}): {completed.stderr.strip()}")
    if completed.returncode != 0:
        return {}
    try:
        output = json.loads(completed.stdout)
        result.checks += 1
        return output
    except json.JSONDecodeError as exc:
        result.errors.append(f"Tool emitted invalid JSON ({' '.join(command)}): {exc}")
        return {}


def validate_examples(root: Path, schemas: Mapping[str, Dict[str, Any]], technology_ids: Set[str], result: Result) -> None:
    mapping = {
        "requirements.json": "workload-requirements.schema.json",
        "database-decision.json": "database-decision.schema.json",
        "architecture-decision.json": "architecture-pattern-decision.schema.json",
        "cost-and-eta.json": "cost-and-eta.schema.json",
    }
    example_dirs = sorted(path for path in (root / "examples").iterdir() if path.is_dir())
    result.check(len(example_dirs) == 3, f"Expected 3 examples, found {len(example_dirs)}")
    architecture_catalog = load_json(root / "catalog" / "architecture-patterns.json", result)
    pattern_ids = {item["id"] for item in architecture_catalog.get("patterns", [])}

    for directory in example_dirs:
        loaded: Dict[str, Dict[str, Any]] = {}
        for filename, schema_name in mapping.items():
            path = directory / filename
            result.check(path.is_file(), f"Missing example artifact: {path}")
            if path.is_file():
                loaded[filename] = load_json(path, result)
                validate_instance(loaded[filename], schemas[schema_name], f"{directory.name}/{filename}", result)
        for role in loaded.get("database-decision.json", {}).get("roles", []):
            selected = role.get("selected", [])
            result.check(all(item in technology_ids for item in selected), f"Unknown selected technology in {directory.name}: {selected}")
        architecture = loaded.get("architecture-decision.json", {})
        chosen_patterns = {architecture.get("primary_pattern")} | set(architecture.get("secondary_patterns", [])) | set(architecture.get("overlays", []))
        result.check(chosen_patterns <= pattern_ids, f"Unknown architecture pattern in {directory.name}: {chosen_patterns - pattern_ids}")
        eta = loaded.get("cost-and-eta.json", {})
        for field in ("system_autonomous_runtime", "human_equivalent_effort", "human_in_the_loop_delay"):
            values = eta.get(field, {})
            result.check(values.get("min", 0) <= values.get("likely", 0) <= values.get("max", 0), f"Invalid ETA ordering in {directory.name}/{field}")

        requirements = directory / "requirements.json"
        generated_db = run_tool([sys.executable, str(root / "tools" / "database_selector.py"), str(requirements)], result)
        generated_arch = run_tool([sys.executable, str(root / "tools" / "architecture_selector.py"), str(requirements)], result)
        generated_eta = run_tool([sys.executable, str(root / "tools" / "plan_estimator.py"), str(requirements)], result)
        result.check(generated_db == loaded.get("database-decision.json"), f"Stale database selector output: {directory.name}")
        result.check(generated_arch == loaded.get("architecture-decision.json"), f"Stale architecture selector output: {directory.name}")
        result.check(generated_eta == loaded.get("cost-and-eta.json"), f"Stale ETA output: {directory.name}")
    result.notes.append(f"Validated {len(example_dirs)} runnable examples and deterministic selector outputs.")


def validate_python(root: Path, result: Result) -> None:
    paths = sorted((root / "tools").glob("*.py")) + sorted((root / "scripts").glob("*.py"))
    for path in paths:
        try:
            py_compile.compile(str(path), doraise=True)
            result.checks += 1
        except py_compile.PyCompileError as exc:
            result.errors.append(f"Python compile failed: {path}: {exc}")
    with tempfile.TemporaryDirectory(prefix="elmos-validator-") as temp:
        completed = subprocess.run(
            [sys.executable, str(root / "scripts" / "install_skillpack.py"), "install", "--target", "custom", "--dest", temp, "--profile", "database", "--dry-run"],
            text=True,
            capture_output=True,
            check=False,
        )
        result.check(completed.returncode == 0, f"Installer dry-run failed: {completed.stderr.strip()}")
    result.notes.append(f"Compiled {len(paths)} Python tools/scripts and passed installer dry-run.")


def validate_manifest(root: Path, manifest: Dict[str, Any], result: Result) -> None:
    checksums = manifest.get("checksums_sha256", {})
    result.check(isinstance(checksums, dict) and bool(checksums), "Manifest has no checksums")
    for rel, expected in checksums.items():
        path = root / rel
        result.check(path.is_file(), f"Manifest file missing: {rel}")
        if path.is_file():
            result.check(sha256_file(path) == expected, f"Checksum mismatch: {rel}")

    actual_files: Set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        if rel.as_posix() in EXCLUDED_FROM_MANIFEST or "__pycache__" in rel.parts or path.suffix == ".pyc":
            continue
        actual_files.add(rel.as_posix())
    result.check(actual_files == set(checksums), f"Manifest file set mismatch; unlisted={sorted(actual_files-set(checksums))}, missing={sorted(set(checksums)-actual_files)}")
    result.notes.append(f"Verified {len(checksums)} SHA-256 file checksums.")


def validate_no_symlinks(root: Path, result: Result) -> None:
    symlinks = [path for path in root.rglob("*") if path.is_symlink()]
    result.check(not symlinks, f"Package contains symlinks: {symlinks}")


def render_report(result: Result) -> str:
    status = "PASS" if not result.errors else "FAIL"
    lines = [
        "# Elmos Database & Big Data Skills Validation Report",
        "",
        f"- Status: **{status}**",
        f"- Checks executed: **{result.checks}**",
        f"- Errors: **{len(result.errors)}**",
        f"- Warnings: **{len(result.warnings)}**",
        "",
        "## Validated areas",
        "",
    ]
    lines.extend(f"- {note}" for note in result.notes)
    if result.warnings:
        lines += ["", "## Warnings", ""] + [f"- {item}" for item in result.warnings]
    if result.errors:
        lines += ["", "## Errors", ""] + [f"- {item}" for item in result.errors]
    lines += [
        "",
        "## Trust boundary",
        "",
        "Passing this package validator proves internal consistency of the skills, schemas, examples, scripts and checksums. It does not certify any catalog technology, cloud provider, connector or generated target repository for production. Those require project-specific integration, security, migration, performance, recovery and end-to-end evidence.",
        "",
    ]
    return "\n".join(lines)


def run(root: Path, report_path: Path | None = None) -> Result:
    result = Result()
    required = [
        "README.md", "ARCHITECTURE.md", "SKILL_INDEX.md", "INSTALL.md", "TASKS.md",
        "CHANGELOG.md", "REFERENCES.md", "MANIFEST.json",
        "scripts/install_skillpack.py", "scripts/build_manifest.py",
        "tools/database_selector.py", "tools/architecture_selector.py", "tools/plan_estimator.py",
    ]
    for rel in required:
        result.check((root / rel).is_file(), f"Missing required file: {rel}")
    validate_no_symlinks(root, result)
    manifest = load_json(root / "MANIFEST.json", result)
    result.check(manifest.get("package") == "elmos-database-bigdata-skills", "Unexpected package name in manifest")
    result.check(manifest.get("package_version") == "1.0.0", "Unexpected package version in manifest")
    graph = validate_skills(root, manifest, result)
    validate_profiles(root, graph, manifest, result)
    technology_ids = validate_catalogs(root, graph, result)
    schemas = validate_schemas(root, result)
    validate_examples(root, schemas, technology_ids, result)
    validate_python(root, result)
    validate_manifest(root, manifest, result)
    if report_path:
        report_path.write_text(render_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    report = args.report.resolve() if args.report else None
    result = run(root, report)
    if args.json:
        print(json.dumps({
            "status": "PASS" if not result.errors else "FAIL",
            "checks": result.checks,
            "errors": result.errors,
            "warnings": result.warnings,
            "notes": result.notes,
        }, ensure_ascii=False, indent=2))
    else:
        print(render_report(result))
    return 0 if not result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
