#!/usr/bin/env python3
"""Validate the Elmos Project Intelligence Skills Package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
from collections import defaultdict

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required. Run: python3 -m pip install -r scripts/requirements.txt") from exc

try:
    import jsonschema
except ImportError:  # optional; basic JSON parsing still runs
    jsonschema = None

REQUIRED_ROOT = [
    "README.md", "INSTALL.md", "SKILLS_INDEX.md", "skillpack.yaml", "AGENTS.md", "CLAUDE.md",
    "docs", "batches", "backlog", "schemas", "contracts", "templates", "examples", "skills",
]
BATCH_ORDER = [
    "BATCH-00-product-and-reference-architecture",
    "BATCH-01-ingestion-and-parsing",
    "BATCH-02-graphs-and-evidence",
    "BATCH-03-code-reader-and-explanation",
    "BATCH-04-architecture-flow-data",
    "BATCH-05-diagram-platform",
    "BATCH-06-documents-presentations-reports",
    "BATCH-07-search-impact-governance-analysis",
    "BATCH-08-cache-versioning-git",
    "BATCH-09-collaboration-and-connectors",
    "BATCH-10-scale-and-observability",
    "BATCH-11-testing-conversion-estimation",
    "BATCH-12-deployment-and-certification",
    "BATCH-13-commercialization",
    "BATCH-14-online-debug-and-learning",
]


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("missing YAML frontmatter")
    return yaml.safe_load(parts[1])


def extract_dependencies(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"## 依赖技能\n\n(.*?)(?:\n## |\Z)", text, re.S)
    if not match:
        return []
    return re.findall(r"^\s*-\s+`([^`]+)`", match.group(1), re.M)


def validate(root: Path, strict_jsonschema: bool = False) -> list[str]:
    errors: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED_ROOT:
        if not (root / rel).exists():
            errors.append(f"missing required path: {rel}")

    try:
        manifest = yaml.safe_load((root / "skillpack.yaml").read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse skillpack.yaml: {exc}"]

    expected_count = int(manifest.get("skill_count", 0))
    skill_dirs = sorted(d for d in (root / "skills").iterdir() if d.is_dir()) if (root / "skills").exists() else []
    if len(skill_dirs) != expected_count:
        errors.append(f"skill count mismatch: manifest={expected_count}, directories={len(skill_dirs)}")

    names: dict[str, Path] = {}
    dependencies: dict[str, list[str]] = {}
    batches: dict[str, str] = {}
    for directory in skill_dirs:
        skill_file = directory / "SKILL.md"
        for required in [skill_file, directory / "references/module-spec.md", directory / "references/usage.md", directory / "agents/openai.yaml"]:
            if not required.is_file():
                errors.append(f"missing skill file: {required.relative_to(root)}")
        if not skill_file.is_file():
            continue
        try:
            fm = parse_frontmatter(skill_file)
        except Exception as exc:
            errors.append(f"invalid frontmatter {skill_file.relative_to(root)}: {exc}")
            continue
        name = fm.get("name")
        description = fm.get("description")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", name):
            errors.append(f"invalid skill name in {directory.name}: {name!r}")
            continue
        if name in names:
            errors.append(f"duplicate skill name: {name}")
        names[name] = directory
        if not isinstance(description, str) or len(description.strip()) < 20:
            errors.append(f"missing/short description: {name}")
        metadata = fm.get("metadata", {})
        batch = metadata.get("batch")
        if batch not in BATCH_ORDER:
            errors.append(f"unknown batch for {name}: {batch}")
        batches[name] = batch
        deps = extract_dependencies(skill_file)
        dependencies[name] = deps
        # Ensure SKILL.md is actionable, not a title-only placeholder.
        body = skill_file.read_text(encoding="utf-8")
        for heading in ["## 目标", "## 输入", "## 必须输出", "## 执行流程", "## 完成定义", "## 验证"]:
            if heading not in body:
                errors.append(f"{name} missing heading: {heading}")

    for name, deps in dependencies.items():
        for dep in deps:
            if dep not in names:
                errors.append(f"{name} depends on missing skill {dep}")

    # Dependency cycles and forward-batch dependencies.
    state: dict[str, int] = {}
    stack: list[str] = []
    batch_index = {b: i for i, b in enumerate(BATCH_ORDER)}

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for dep in dependencies.get(node, []):
            if dep not in names:
                continue
            if batch_index[batches[dep]] > batch_index[batches[node]]:
                errors.append(f"forward batch dependency: {node} ({batches[node]}) -> {dep} ({batches[dep]})")
            if state.get(dep) == 1:
                cycle = " -> ".join(stack[stack.index(dep):] + [dep])
                errors.append(f"dependency cycle: {cycle}")
            elif state.get(dep) != 2:
                visit(dep)
        stack.pop()
        state[node] = 2

    for name in names:
        if not state.get(name):
            visit(name)

    profiles = manifest.get("profiles", {})
    for profile, requested in profiles.items():
        if not isinstance(requested, list) or not requested:
            errors.append(f"empty/invalid profile: {profile}")
            continue
        unknown = [name for name in requested if name not in names]
        if unknown:
            errors.append(f"profile {profile} references unknown skills: {unknown}")

    # Batches: exactly one file each and no unknown batch files.
    batch_files = {p.stem for p in (root / "batches").glob("BATCH-*.md")}
    for batch in BATCH_ORDER:
        if batch not in batch_files:
            errors.append(f"missing batch file: batches/{batch}.md")
    for extra in sorted(batch_files - set(BATCH_ORDER)):
        warnings.append(f"unknown batch file: {extra}")

    # Machine-readable backlogs.
    try:
        epics_doc = yaml.safe_load((root / "backlog/epics.yaml").read_text(encoding="utf-8"))
        tasks_doc = yaml.safe_load((root / "backlog/tasks.yaml").read_text(encoding="utf-8"))
        ac_doc = yaml.safe_load((root / "backlog/acceptance-scenarios.yaml").read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"backlog YAML parse failed: {exc}")
        epics_doc, tasks_doc, ac_doc = {"epics": []}, {"tasks": []}, {"scenarios": []}

    epics = epics_doc.get("epics", [])
    tasks = tasks_doc.get("tasks", [])
    scenarios = ac_doc.get("scenarios", [])
    if len(epics) != expected_count:
        errors.append(f"epic count mismatch: {len(epics)} != {expected_count}")
    if len(tasks) != int(tasks_doc.get("task_count", -1)):
        errors.append("tasks.yaml task_count mismatch")
    if len(scenarios) != int(ac_doc.get("scenario_count", -1)):
        errors.append("acceptance-scenarios.yaml scenario_count mismatch")
    if len(tasks) != 500:
        errors.append(f"expected 500 tasks, found {len(tasks)}")
    if len(scenarios) != 248:
        errors.append(f"expected 248 acceptance scenarios, found {len(scenarios)}")

    task_ids = [t.get("id") for t in tasks]
    ac_ids = [a.get("id") for a in scenarios]
    epic_ids = [e.get("id") for e in epics]
    for label, values in [("task", task_ids), ("acceptance", ac_ids), ("epic", epic_ids)]:
        if len(values) != len(set(values)):
            errors.append(f"duplicate {label} IDs")

    for t in tasks:
        if t.get("skill") not in names:
            errors.append(f"task {t.get('id')} references unknown skill {t.get('skill')}")
        if t.get("batch") != batches.get(t.get("skill")):
            errors.append(f"task {t.get('id')} batch does not match skill metadata")
    for a in scenarios:
        if a.get("skill") not in names:
            errors.append(f"AC {a.get('id')} references unknown skill {a.get('skill')}")
        if a.get("batch") != batches.get(a.get("skill")):
            errors.append(f"AC {a.get('id')} batch does not match skill metadata")

    # Traceability CSV.
    trace_path = root / "backlog/traceability.csv"
    try:
        rows = list(csv.DictReader(trace_path.open(encoding="utf-8-sig")))
        for row in rows:
            if row.get("epic_id") not in set(epic_ids):
                errors.append(f"traceability references unknown epic: {row.get('epic_id')}")
            if row.get("task_id") not in set(task_ids):
                errors.append(f"traceability references unknown task: {row.get('task_id')}")
            if row.get("acceptance_id") not in set(ac_ids):
                errors.append(f"traceability references unknown AC: {row.get('acceptance_id')}")
    except Exception as exc:
        errors.append(f"traceability.csv parse failed: {exc}")

    # Parse all JSON and YAML files, excluding intentionally non-YAML markdown.
    for path in sorted(root.rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid JSON {path.relative_to(root)}: {exc}")
    for path in sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml")):
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid YAML {path.relative_to(root)}: {exc}")

    # Validate examples against schemas when jsonschema is present.
    schema_example_pairs = [
        ("schemas/project-manifest.schema.json", "examples/sample-project-manifest.json"),
        ("schemas/evidence.schema.json", "examples/sample-evidence-bundle.json"),
        ("schemas/diagram-spec.schema.json", "examples/sample-diagram-spec.json"),
        ("schemas/analysis-job.schema.json", "examples/sample-analysis-job.json"),
        ("schemas/estimate.schema.json", "examples/sample-estimate.json"),
        ("schemas/conversion-mapping.schema.json", "examples/sample-conversion-mapping.json"),
        ("schemas/debug-session.schema.json", "examples/sample-debug-session.json"),
        ("schemas/debug-event.schema.json", "examples/sample-debug-event.json"),
        ("schemas/debug-replay-bundle.schema.json", "examples/sample-debug-replay-bundle.json"),
        ("schemas/debug-learning-mission.schema.json", "examples/sample-debug-learning-mission.json"),
    ]
    if jsonschema is None:
        msg = "jsonschema not installed; skipped schema-instance validation"
        if strict_jsonschema:
            errors.append(msg)
        else:
            warnings.append(msg)
    else:
        for schema_rel, example_rel in schema_example_pairs:
            try:
                schema = json.loads((root / schema_rel).read_text(encoding="utf-8"))
                instance = json.loads((root / example_rel).read_text(encoding="utf-8"))
                jsonschema.Draft202012Validator(schema).validate(instance)
            except Exception as exc:
                errors.append(f"schema validation failed {example_rel} against {schema_rel}: {exc}")

    # Ensure README paths and scripts exist.
    for rel in ["scripts/install_skillpack.py", "scripts/list_skills.py", "scripts/package_skillpack.py", "tests/test_skillpack.py"]:
        if not (root / rel).is_file():
            errors.append(f"missing executable/test: {rel}")

    print(json.dumps({
        "root": str(root),
        "skills": len(names),
        "epics": len(epics),
        "tasks": len(tasks),
        "acceptance_scenarios": len(scenarios),
        "batches": len(batch_files),
        "jsonschema_enabled": jsonschema is not None,
        "warnings": warnings,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }, ensure_ascii=False, indent=2))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict-jsonschema", action="store_true")
    args = parser.parse_args()
    errors = validate(args.root.resolve(), args.strict_jsonschema)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
