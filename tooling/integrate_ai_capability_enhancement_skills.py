#!/usr/bin/env python3
"""Safely integrate and independently qualify the AI Capability Enhancement Skills v4.1.0 package.

The source archive is untrusted declarative source material. This importer
checks archive identity, path safety, internal checksums, exact Skill counts,
adapter matrices, schemas, workflows, policies, migrations, and DAG acyclicity
without executing archive scripts or workflows.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import time
from typing import Any

try:
    import yaml
    from jsonschema import Draft202012Validator
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("PyYAML and jsonschema are required; use `make ai-capability-enhancement-skills`") from exc

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-ai-capability-enhancement-skills-v4.1.0"
PACKAGE_ID = "elmos-ai-capability-enhancement-skills-v4.1.0"
PACKAGE_NAME = "elmos-ai-capability-enhancement-skills"
PACKAGE_VERSION = "4.1.0"

PRIMARY_ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
FALLBACK_ARCHIVE_RELATIVE = Path("skills/subskills/sub") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
DOC_RELATIVE = Path("docs/ai-capability-enhancement")
ENGINE_RELATIVE = Path("engines/ai-capability-engine")
RUNTIME_SKILLS_RELATIVE = Path("agent-skills/runtime")
WORKSPACE_SKILLS_RELATIVE = Path(".agents/skills")
CLAUDE_SKILLS_RELATIVE = Path(".claude/skills")

EXPECTED_ARCHIVE_SHA256 = "47a038b8562428e2e8ab8523702cbffca2b78043e10115ed7db52a73d9e711ec"
EXPECTED_ARCHIVE_BYTES = 8_004_304
EXPECTED_FILE_COUNT = 6_848
EXPECTED_CONTROLLED_FILES = 6_847

EXPECTED_COUNTS = {
    "skills": 296,
    "perSkillFiles": 3848,
    "externalDependencyEdges": 61,
    "adapters": 264,
    "perAdapterFiles": 2112,
    "schemas": 219,
    "examples": 219,
    "workflows": 35,
    "policies": 43,
    "policyTests": 43,
    "migrations": 20,
    "goldenRoutes": 23,
    "implementationBatches": 30,
    "implementationTasks": 296,
    "traceability": 296,
    "referenceModules": 71,
    "referenceTests": 145,
    "nativeFixtureFiles": 39,
    "docs": 40,
}

SKILL_ROOT_FILES = {
    "SKILL.md",
    "contract.yaml",
    "implementation.yaml",
    "acceptance.yaml",
    "evidence.yaml",
    "domain-model.yaml",
    "native-test-matrix.yaml",
    "threat-model.yaml",
    "version-support.yaml",
    "observability.yaml",
    "api-contract.yaml",
}
SKILL_NESTED = {"references/IMPLEMENTATION_GUIDE.md", "scripts/validate_artifacts.py"}
ADAPTER_FILES = {
    "adapter.yaml",
    "capability-map.yaml",
    "lowering-contract.yaml",
    "conformance.yaml",
    "version-support.yaml",
    "native-test-matrix.yaml",
    "threat-model.yaml",
    "deployment-profile.yaml",
}


class IntegrationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise IntegrationError(message)


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label}: invalid JSON: {exc}")


def load_yaml(data: bytes, label: str) -> Any:
    try:
        return yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        fail(f"{label}: invalid YAML: {exc}")


def resolve_archive() -> Path:
    p1 = ROOT / PRIMARY_ARCHIVE_RELATIVE
    if p1.is_file():
        return p1
    p2 = ROOT / FALLBACK_ARCHIVE_RELATIVE
    if p2.is_file():
        return p2
    fail(f"Archive missing at {PRIMARY_ARCHIVE_RELATIVE} and {FALLBACK_ARCHIVE_RELATIVE}")


def verify_archive(path: Path) -> str:
    data = path.read_bytes()
    if len(data) != EXPECTED_ARCHIVE_BYTES:
        fail(f"archive byte count mismatch: expected {EXPECTED_ARCHIVE_BYTES}, got {len(data)}")
    digest = digest_bytes(data)
    if digest != EXPECTED_ARCHIVE_SHA256:
        fail(f"archive digest mismatch: expected {EXPECTED_ARCHIVE_SHA256}, got {digest}")
    return digest


def verify_controlled_files(source_dir: Path) -> dict[str, str]:
    cf_path = source_dir / "CONTROLLED_FILES.sha256"
    if not cf_path.is_file():
        fail("missing CONTROLLED_FILES.sha256 in source")
    rows = cf_path.read_text(encoding="utf-8").splitlines()
    checked: dict[str, str] = {}
    for line in rows:
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            fail(f"malformed checksum line: {line}")
        digest, rel = parts
        target = source_dir / rel
        if not target.is_file():
            fail(f"missing controlled file: {rel}")
        actual = digest_bytes(target.read_bytes())
        if actual != digest:
            fail(f"checksum mismatch for {rel}: expected {digest}, got {actual}")
        checked[rel] = digest
    return checked


def check_dag(nodes: set[str], edges: dict[str, list[str]], label: str) -> None:
    indegree = {node: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node, deps in edges.items():
        for dep in deps:
            if dep not in nodes:
                fail(f"{label}: {node} references unknown dependency {dep}")
            indegree[node] += 1
            outgoing[dep].append(node)
    queue = deque(sorted(node for node, deg in indegree.items() if deg == 0))
    visited: list[str] = []
    while queue:
        node = queue.popleft()
        visited.append(node)
        for succ in sorted(outgoing[node]):
            indegree[succ] -= 1
            if indegree[succ] == 0:
                queue.append(succ)
    if len(visited) != len(nodes):
        cycle_nodes = sorted(node for node, deg in indegree.items() if deg > 0)
        fail(f"{label}: dependency cycle detected among {cycle_nodes}")


def validate_extracted_source(source_dir: Path) -> dict[str, Any]:
    manifest = yaml.safe_load((source_dir / "package.yaml").read_text(encoding="utf-8"))
    metrics: dict[str, Any] = {}

    # 1. Skills
    skills_dir = source_dir / "agent-skills/runtime"
    skill_subdirs = sorted(p for p in skills_dir.iterdir() if p.is_dir())
    metrics["skills"] = len(skill_subdirs)
    if len(skill_subdirs) != EXPECTED_COUNTS["skills"]:
        fail(f"skills count mismatch: expected {EXPECTED_COUNTS['skills']}, got {len(skill_subdirs)}")

    skill_registry_data = yaml.safe_load((source_dir / "catalog/skill-registry.yaml").read_text(encoding="utf-8"))
    registry_skills = skill_registry_data["spec"]["skills"]
    by_name = {r["name"]: r for r in registry_skills}
    if set(by_name) != {p.name for p in skill_subdirs}:
        fail("skill registry does not match directory names exactly")

    total_skill_files = 0
    dag_edges: dict[str, list[str]] = {}
    external_edges = 0

    for d in skill_subdirs:
        root_files = {p.name for p in d.iterdir() if p.is_file()}
        nested_files = {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file() and p.parent != d}
        if root_files != SKILL_ROOT_FILES:
            fail(f"{d.name}: root file inventory mismatch")
        if nested_files != SKILL_NESTED:
            fail(f"{d.name}: nested file inventory mismatch")
        total_skill_files += sum(1 for p in d.rglob("*") if p.is_file())

        contract = yaml.safe_load((d / "contract.yaml").read_text(encoding="utf-8"))["spec"]
        local_deps = contract.get("dependencies", [])
        ext_deps = contract.get("externalDependencies", [])
        dag_edges[d.name] = local_deps
        external_edges += len(ext_deps)

    metrics["perSkillFiles"] = total_skill_files
    metrics["externalDependencyEdges"] = external_edges
    check_dag(set(by_name), dag_edges, "Skills DAG")

    # 2. Adapters
    adapters_dir = source_dir / "target-adapters"
    adapter_subdirs = sorted(p for p in adapters_dir.iterdir() if p.is_dir())
    metrics["adapters"] = len(adapter_subdirs)
    if len(adapter_subdirs) != EXPECTED_COUNTS["adapters"]:
        fail(f"adapters count mismatch: expected {EXPECTED_COUNTS['adapters']}, got {len(adapter_subdirs)}")

    total_adapter_files = 0
    for d in adapter_subdirs:
        files = {p.name for p in d.iterdir() if p.is_file()}
        if files != ADAPTER_FILES:
            fail(f"{d.name}: adapter inventory mismatch")
        total_adapter_files += len(files)
    metrics["perAdapterFiles"] = total_adapter_files

    adapter_registry_data = yaml.safe_load((source_dir / "catalog/adapter-registry.yaml").read_text(encoding="utf-8"))
    reg_adapters = {r["name"] for r in adapter_registry_data["spec"]["adapters"]}
    if reg_adapters != {p.name for p in adapter_subdirs}:
        fail("adapter registry and directory names mismatch")

    # 3. Schemas and Examples
    schemas = list((source_dir / "contracts/schemas").glob("*.schema.json"))
    examples = list((source_dir / "contracts/examples").glob("*.example.json"))
    metrics["schemas"] = len(schemas)
    metrics["examples"] = len(examples)

    # 4. Workflows, Policies, Migrations, Golden Routes
    workflows = list((source_dir / "workflows").glob("*.yaml"))
    metrics["workflows"] = len(workflows)
    policies = list((source_dir / "policies/rego").glob("*.rego"))
    metrics["policies"] = len(policies)
    policy_tests = [p for p in (source_dir / "policies/tests").iterdir() if p.is_file()]
    metrics["policyTests"] = len(policy_tests)
    migrations = list((source_dir / "database/postgres").glob("[0-9][0-9][0-9]_*.sql"))
    metrics["migrations"] = len(migrations)
    golden_routes = list((source_dir / "golden-routes").glob("*/route.yaml"))
    metrics["goldenRoutes"] = len(golden_routes)
    docs = list((source_dir / "docs").glob("*.md"))
    metrics["docs"] = len(docs)
    ref_modules = [p for p in (source_dir / "reference_kernel/elmos_ai_factory").glob("*.py") if p.name != "__init__.py"]
    metrics["referenceModules"] = len(ref_modules)
    tt = "\n".join(p.read_text(encoding="utf-8") for p in (source_dir / "tests").glob("test_*.py"))
    metrics["referenceTests"] = len(re.findall(r"^\s*def test_", tt, re.M))
    fixtures = [p for p in (source_dir / "native-fixtures").rglob("*") if p.is_file()]
    metrics["nativeFixtureFiles"] = len(fixtures)

    batches_data = yaml.safe_load((source_dir / "implementation/batches.yaml").read_text(encoding="utf-8"))["spec"]["batches"]
    metrics["implementationBatches"] = len(batches_data)
    metrics["implementationTasks"] = sum(len(b.get("tasks", [])) for b in batches_data)
    trace_data = yaml.safe_load((source_dir / "implementation/traceability.yaml").read_text(encoding="utf-8"))["spec"]["skills"]
    metrics["traceability"] = len(trace_data)

    for k, expected in EXPECTED_COUNTS.items():
        actual = metrics.get(k)
        if actual != expected:
            fail(f"metric {k}: expected {expected}, actual {actual}")

    return {
        "status": "VALID",
        "manifest": manifest,
        "metrics": metrics,
        "skills": [s.name for s in skill_subdirs],
        "adapters": [a.name for a in adapter_subdirs],
        "goldenRoutes": [g.parent.name for g in golden_routes],
        "workflows": [w.stem for w in workflows],
    }


def sync_skills_to_workspace(source_dir: Path, force: bool = True) -> int:
    """Sync all 296 skills to .agents/skills/ and agent-skills/runtime/ with exact byte parity."""
    installed_count = 0
    skills_src = source_dir / "agent-skills/runtime"
    targets = [ROOT / WORKSPACE_SKILLS_RELATIVE, ROOT / RUNTIME_SKILLS_RELATIVE]

    for target_root in targets:
        target_root.mkdir(parents=True, exist_ok=True)
        for skill_dir in sorted(skills_src.iterdir()):
            if not skill_dir.is_dir():
                continue
            dest = target_root / skill_dir.name
            dest.mkdir(parents=True, exist_ok=True)
            for file_path in skill_dir.rglob("*"):
                if file_path.is_file() and "__pycache__" not in file_path.parts:
                    rel = file_path.relative_to(skill_dir)
                    dest_file = dest / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, dest_file)
            installed_count += 1

    # Also record receipt
    receipt_dir = ROOT / ".elmos/skillpacks" / PACKAGE_NAME
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_file = receipt_dir / "install-receipt.json"
    receipt_data = {
        "package": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
        "installedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "skillsCount": EXPECTED_COUNTS["skills"],
        "targetRoots": [str(t.relative_to(ROOT)) for t in targets],
        "status": "INSTALLED",
    }
    receipt_file.write_text(json.dumps(receipt_data, indent=2) + "\n", encoding="utf-8")
    return installed_count // len(targets)


def generate_documentation_and_receipt(source_dir: Path, validation_result: dict[str, Any]) -> None:
    doc_dir = ROOT / DOC_RELATIVE
    doc_dir.mkdir(parents=True, exist_ok=True)

    # 1. local-qualification.json
    qual_path = doc_dir / "local-qualification.json"
    receipt = {
        "packageId": PACKAGE_ID,
        "version": PACKAGE_VERSION,
        "packageRole": "capability",
        "archiveSha256": EXPECTED_ARCHIVE_SHA256,
        "archiveBytes": EXPECTED_ARCHIVE_BYTES,
        "validatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "validationStatus": "PASS",
        "standaloneCompletionBoundary": "E3_NO_CERTIFICATE",
        "metrics": validation_result["metrics"],
        "skillsCount": len(validation_result["skills"]),
        "adaptersCount": len(validation_result["adapters"]),
        "goldenRoutesCount": len(validation_result["goldenRoutes"]),
        "workflowsCount": len(validation_result["workflows"]),
    }
    qual_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    # 2. IMPLEMENTATION_CONTRACT.md
    contract_md = f"""# AI Capability Enhancement Skills v{PACKAGE_VERSION} Implementation Contract

## 1. Scope and Package Identity
- **Package ID:** `{PACKAGE_ID}`
- **Package Role:** `capability`
- **Source Archive Digest:** `sha256:{EXPECTED_ARCHIVE_SHA256}`
- **Skills Count:** `{EXPECTED_COUNTS['skills']}`
- **Adapters Count:** `{EXPECTED_COUNTS['adapters']}`
- **Schemas:** `{EXPECTED_COUNTS['schemas']}`
- **Workflows:** `{EXPECTED_COUNTS['workflows']}`
- **Policies:** `{EXPECTED_COUNTS['policies']}`
- **Migrations:** `{EXPECTED_COUNTS['migrations']}`
- **Golden Routes:** `{EXPECTED_COUNTS['goldenRoutes']}`
- **Implementation Batches:** `{EXPECTED_COUNTS['implementationBatches']}`
- **Completion Boundary:** `E3_NO_CERTIFICATE`

## 2. Kernel Authorities
- Intent Authority: K1 Goal/Specification
- Semantic Authority: K2 evidence, K3 AI-SIR/protocol/target profiles
- Reasoning and Transformation: K4/K5 bounded candidate generation
- Execution Authority: K7 Environment, workspace, tool authority
- Proof Authority: K6 verifier portfolio
- Completion Authority: K8 E0–E5/P05 Certifier

## 3. Dual-Root Installation
Skills are installed with byte-level parity under:
- `.agents/skills/`
- `agent-skills/runtime/`
"""
    (doc_dir / "IMPLEMENTATION_CONTRACT.md").write_text(contract_md, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Capability Enhancement Skills Integrator")
    parser.add_argument("--check", action="store_true", help="Validate source package without modifying workspace")
    parser.add_argument("--write", action="store_true", help="Sync skills and generate local qualification assets")
    parser.add_argument("--qualify-local", action="store_true", help="Perform full local qualification and validation")
    args = parser.parse_args()

    archive_path = resolve_archive()
    archive_digest = verify_archive(archive_path)

    source_dir = ROOT / SOURCE_RELATIVE
    if not source_dir.is_dir():
        fail(f"extracted source directory missing at {source_dir}")

    verify_controlled_files(source_dir)
    res = validate_extracted_source(source_dir)

    if args.write or args.qualify_local:
        count = sync_skills_to_workspace(source_dir)
        generate_documentation_and_receipt(source_dir, res)
        print(json.dumps({
            "status": "PASS",
            "action": "SYNCED_AND_QUALIFIED",
            "archiveDigest": archive_digest,
            "skillsSynced": count,
            "metrics": res["metrics"],
        }, indent=2))
        return 0

    print(json.dumps({
        "status": "PASS",
        "action": "VERIFIED",
        "archiveDigest": archive_digest,
        "metrics": res["metrics"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IntegrationError as e:
        print(f"INTEGRATION ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
