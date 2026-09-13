#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import tomllib
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
import yaml

REQUIRED_SKILL_FILES = {"SKILL.md", "manifest.yaml", "acceptance.yaml", "implementation.yaml", "runbook.md"}
REQUIRED_ROOT = {"README.md", "AGENTS.md", "PLANS.md", "catalog/package.yaml", "catalog/skill-catalog.yaml", "catalog/requirements.json", "catalog/scenarios.json", "catalog/implementation-tasks.json"}

def load(path: Path) -> Any:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))

def cycle(nodes: set[str], edges: list[tuple[str, str]]) -> list[str] | None:
    indegree = {n: 0 for n in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    for a, b in edges:
        if a not in nodes or b not in nodes:
            continue
        indegree[b] += 1
        children[a].append(b)
    queue = deque(sorted(n for n, d in indegree.items() if d == 0))
    seen = []
    while queue:
        n = queue.popleft(); seen.append(n)
        for c in children[n]:
            indegree[c] -= 1
            if indegree[c] == 0: queue.append(c)
    return None if len(seen) == len(nodes) else sorted(n for n, d in indegree.items() if d > 0)

def markdown_links(root: Path) -> list[str]:
    errors = []
    pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for path in root.rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for raw in pattern.findall(text):
            link = raw.split("#", 1)[0].strip()
            if not link or "://" in link or link.startswith(("mailto:", "#", "<")):
                continue
            target = (path.parent / link).resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError:
                errors.append(f"link escapes package: {path.relative_to(root)} -> {raw}")
                continue
            if not target.exists():
                errors.append(f"broken local link: {path.relative_to(root)} -> {raw}")
    return errors

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED_ROOT:
        if not (root / rel).exists(): errors.append(f"missing required file: {rel}")

    package = load(root / "catalog/package.yaml")
    expected = int(package["spec"]["atomicSkillCount"])
    skill_dirs = sorted(p.parent for p in (root / "skills/atomic").rglob("manifest.yaml"))
    if len(skill_dirs) != expected: errors.append(f"atomic Skill count {len(skill_dirs)} != {expected}")

    ids: set[str] = set(); edges: list[tuple[str, str]] = []
    for d in skill_dirs:
        missing = REQUIRED_SKILL_FILES - {p.name for p in d.iterdir() if p.is_file()}
        if missing: errors.append(f"{d.relative_to(root)} missing {sorted(missing)}")
        manifest = load(d / "manifest.yaml")
        acceptance = load(d / "acceptance.yaml")
        implementation = load(d / "implementation.yaml")
        sid = manifest.get("metadata", {}).get("id")
        if not sid: errors.append(f"missing id: {d.relative_to(root)}"); continue
        if sid in ids: errors.append(f"duplicate Skill id: {sid}")
        ids.add(sid)
        spec = manifest.get("spec", {})
        if spec.get("routable") is not False: errors.append(f"{sid}: must be non-routable")
        if not str(spec.get("routeOwnerRef", "")).startswith("binding://"): errors.append(f"{sid}: symbolic routeOwnerRef required")
        if spec.get("compatibility", {}).get("standaloneCompletionBoundary") != "E3": errors.append(f"{sid}: E3 boundary missing")
        if spec.get("authority", {}).get("productionWrite") != "prohibited-in-capability-package": errors.append(f"{sid}: production write must be prohibited")
        if spec.get("authority", {}).get("completionDecision") != "independent-K8-only": errors.append(f"{sid}: K8 completion boundary missing")
        if acceptance.get("spec", {}).get("completion") != "E3-capability-readiness-at-most": errors.append(f"{sid}: acceptance completion boundary missing")
        must_not = set(implementation.get("spec", {}).get("migration", {}).get("mustNotCreate", []))
        expected_forbidden = {"second Goal store", "second AI-SIR owner", "second runtime authority", "second completion authority"}
        if not expected_forbidden.issubset(must_not): errors.append(f"{sid}: canonical duplication guards incomplete")
        for dep in spec.get("dependencies", []): edges.append((dep, sid))
    for dep, sid in edges:
        if dep not in ids: errors.append(f"{sid}: missing local dependency {dep}")
    cyc = cycle(ids, edges)
    if cyc: errors.append(f"Skill dependency cycle: {cyc}")

    catalog = load(root / "catalog/skill-catalog.yaml")
    catalog_ids = {x["id"] for x in catalog["spec"]["skills"]}
    if catalog_ids != ids: errors.append("skill-catalog IDs differ from per-Skill manifests")
    if any(x.get("routable") for x in catalog["spec"]["skills"]): errors.append("catalog contains routable component Skill")

    requirements = load(root / "catalog/requirements.json")
    scenarios = load(root / "catalog/scenarios.json")
    if requirements.get("count") != len(requirements.get("requirements", [])): errors.append("requirements count mismatch")
    if scenarios.get("count") != len(scenarios.get("scenarios", [])): errors.append("scenarios count mismatch")
    req_ids = [x["id"] for x in requirements.get("requirements", [])]
    sc_ids = [x["id"] for x in scenarios.get("scenarios", [])]
    if len(req_ids) != len(set(req_ids)): errors.append("duplicate requirement ID")
    if len(sc_ids) != len(set(sc_ids)): errors.append("duplicate scenario ID")

    task_doc = load(root / "catalog/implementation-tasks.json")
    tasks = task_doc.get("tasks", [])
    task_ids = {x["id"] for x in tasks}
    if task_doc.get("count") != len(tasks) or len(task_ids) != len(tasks): errors.append("implementation task count/ID mismatch")
    task_edges = []
    for task in tasks:
        for dep in task.get("dependsOn", []):
            if dep not in task_ids: errors.append(f"{task['id']}: missing task dependency {dep}")
            else: task_edges.append((dep, task["id"]))
    task_cycle = cycle(task_ids, task_edges)
    if task_cycle: errors.append(f"implementation task cycle: {task_cycle[:20]}")

    batch_doc = load(root / "catalog/implementation-batches.yaml")
    batches = batch_doc["spec"]["batches"]
    batch_ids = {x["id"] for x in batches}
    batch_edges = []
    for batch in batches:
        for dep in batch.get("dependsOn", []):
            if dep not in batch_ids: errors.append(f"{batch['id']}: missing batch dependency {dep}")
            else: batch_edges.append((dep, batch["id"]))
        if any(t not in task_ids for t in batch.get("tasks", [])): errors.append(f"{batch['id']}: unknown task reference")
    batch_cycle = cycle(batch_ids, batch_edges)
    if batch_cycle: errors.append(f"implementation batch cycle: {batch_cycle}")

    codex_dirs = sorted(p.parent for p in (root / ".agents/skills").glob("*/SKILL.md"))
    if len(codex_dirs) != int(package["spec"]["codexWorkflowSkillCount"]): errors.append("Codex Skill count mismatch")
    for d in codex_dirs:
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not fm: errors.append(f"Codex Skill missing YAML frontmatter: {d.name}"); continue
        meta = yaml.safe_load(fm.group(1)) or {}
        if meta.get("name") != d.name: errors.append(f"Codex Skill name/path mismatch: {d.name}")
        if not meta.get("description"): errors.append(f"Codex Skill missing description: {d.name}")

    agent_files = sorted((root / ".codex/agents").glob("*.toml"))
    if len(agent_files) != int(package["spec"]["customAgentCount"]): errors.append("custom agent count mismatch")
    for path in agent_files:
        try: data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc: errors.append(f"invalid TOML {path.name}: {exc}"); continue
        for key in ["name", "description", "developer_instructions"]:
            if not data.get(key): errors.append(f"{path.name}: missing {key}")

    # Secret patterns intentionally target high-signal credentials, not documentation words.
    secret_patterns = [re.compile(r"AKIA[0-9A-Z]{16}"), re.compile(r"sk-[A-Za-z0-9]{32,}"), re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")]
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".zip", ".gz", ".png", ".jpg", ".jpeg"}: continue
        try: text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError: continue
        for pat in secret_patterns:
            if pat.search(text): errors.append(f"possible embedded secret: {path.relative_to(root)}")

    errors.extend(markdown_links(root))
    placeholders = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".yaml", ".yml", ".json", ".toml", ".sql", ".rego", ".py", ".sh"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "REPLACE_FROM_TARGET_ELMOS_REGISTRY" in text or "RELEASE_TIME_" in text:
                placeholders.append(str(path.relative_to(root)))
    if placeholders: warnings.append(f"expected integration/release placeholders in {len(set(placeholders))} files")

    summary = {"status": "PASS" if not errors else "FAIL", "atomicSkills": len(skill_dirs), "codexSkills": len(codex_dirs), "customAgents": len(agent_files), "requirements": len(req_ids), "scenarios": len(sc_ids), "tasks": len(tasks), "errors": errors, "warnings": warnings}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
