"""Deterministic repository intelligence and contract planning helpers."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .errors import ContractError
from .models import digest, relative_path, require_mapping

LANGUAGES = {
    ".py": "Python", ".java": "Java", ".kt": "Kotlin", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust", ".cs": "C#", ".cpp": "C++",
    ".c": "C", ".h": "C/C++", ".sql": "SQL", ".swift": "Swift", ".dart": "Dart", ".php": "PHP",
}
BUILD_FILES = {"pom.xml": "maven", "build.gradle": "gradle", "build.gradle.kts": "gradle", "package.json": "node", "pyproject.toml": "python", "Cargo.toml": "cargo", "go.mod": "go", "Dockerfile": "docker", "Makefile": "make", "CMakeLists.txt": "cmake"}


def _files(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = snapshot.get("files", [])
    if isinstance(raw, Mapping):
        raw = [{"path": key, "content": value} for key, value in raw.items()]
    if not isinstance(raw, list):
        raise ContractError("INVALID_INPUT", "repository snapshot files must be an array or object")
    result: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            item = {"path": item}
        row = require_mapping(item, "repository_snapshot.files[]")
        path = relative_path(row.get("path"), "repository_snapshot.files[].path")
        content = row.get("content", "")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ContractError("INVALID_INPUT", f"file content must be text: {path}")
        result.append({"path": path, "content": content, "sha256": row.get("sha256", digest(content)), "byte_count": len(content.encode("utf-8"))})
    return sorted(result, key=lambda item: item["path"])


def census(snapshot: Mapping[str, Any], build_files: Any = None, *, snapshot_sha: str | None = None) -> dict[str, Any]:
    files = _files(snapshot)
    if not files:
        raise ContractError("PARTIAL_CENSUS", "repository snapshot contains no files")
    languages: dict[str, int] = defaultdict(int)
    modules: set[str] = set()
    builds: list[dict[str, Any]] = []
    entrypoints: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    for item in files:
        path = item["path"]
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in LANGUAGES:
            languages[LANGUAGES[suffix]] += 1
        parts = path.split("/")
        modules.add(parts[0])
        name = parts[-1]
        if name in BUILD_FILES:
            builds.append({"path": path, "system": BUILD_FILES[name], "evidence": f"{path}:1"})
        content = item["content"]
        for line_number, line in enumerate(content.splitlines(), 1):
            if re.search(r"(?:if __name__\s*==|public static void main|func main\(|@SpringBootApplication|createServer\(|app\.listen\()", line):
                entrypoints.append({"path": path, "line": line_number, "kind": "runtime-entrypoint", "evidence": f"{path}:{line_number}"})
        lowered = path.casefold() + "\n" + content.casefold()
        if any(word in lowered for word in ("password", "secret", "private_key", "apikey")):
            risks.append({"path": path, "category": "secret-surface", "severity": "P1", "evidence": f"{path}:content"})
        if "/migration" in path.casefold() or "flyway" in lowered or "alembic" in lowered:
            risks.append({"path": path, "category": "data-migration", "severity": "P1", "evidence": f"{path}:content"})
        if "generated" in path.casefold() or "vendor" in path.casefold() or "node_modules" in path.casefold():
            risks.append({"path": path, "category": "non-authoritative-source", "severity": "P2", "evidence": f"{path}:path"})
    declared_builds = build_files if isinstance(build_files, list) else builds
    repo_sha = snapshot_sha or snapshot.get("sha256") or digest([{"path": i["path"], "sha256": i["sha256"]} for i in files])
    profile = {"snapshot_sha": repo_sha, "file_count": len(files), "languages": dict(sorted(languages.items())), "modules": sorted(modules), "build_systems": sorted({item["system"] for item in builds}), "partial": not bool(builds), "unknowns": [] if builds else ["build system not found"], "evidence": {"files": [f'{item["path"]}:1' for item in files], "build_files": declared_builds}}
    return {"repository_profile": profile, "module_graph": {"nodes": [{"id": module, "kind": "module"} for module in sorted(modules)], "edges": [], "snapshot_sha": repo_sha}, "build_graph": {"nodes": builds, "edges": [], "snapshot_sha": repo_sha}, "entrypoint_map": entrypoints, "data_flow_map": {"status": "NOT_RUN", "edges": [], "unknowns": ["runtime traces not supplied"]}, "risk_map": {"findings": risks, "unknowns": profile["unknowns"]}}


_DEFINITIONS = [
    (re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)"), "function"),
    (re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|static\s+)*(?:class|interface|enum)\s+([A-Za-z_]\w*)"), "type"),
    (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$]\w*)"), "function"),
    (re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)"), "function"),
    (re.compile(r"^\s*(?:pub\s+)?fn\s+([A-Za-z_]\w*)"), "function"),
]


def semantic_index(snapshot: Mapping[str, Any], previous_index: Mapping[str, Any] | None = None, change_set: Any = None, compiler_metadata: Any = None) -> dict[str, Any]:
    files = _files(snapshot)
    repo_sha = snapshot.get("sha256") or digest([{"path": i["path"], "sha256": i["sha256"]} for i in files])
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    by_name: dict[str, list[str]] = defaultdict(list)
    for item in files:
        path = item["path"]
        if "generated" in path.casefold() or "vendor" in path.casefold():
            continue
        lines = item["content"].splitlines()
        for number, line in enumerate(lines, 1):
            for pattern, kind in _DEFINITIONS:
                match = pattern.search(line)
                if match:
                    name = match.group(1)
                    uri = f"repo://{repo_sha}/{path}#{kind}/{name}:{number}"
                    symbol = {"uri": uri, "name": name, "kind": kind, "path": path, "line": number, "snapshot_sha": repo_sha}
                    symbols.append(symbol)
                    by_name[name].append(uri)
                    break
            if re.search(r"^\s*(?:from\s+\S+\s+import|import\s+|#include\s+|use\s+|require\(|import\s+)", line):
                imports.append({"path": path, "line": number, "text": line.strip()[:300]})
        for symbol in [s for s in symbols if s["path"] == path]:
            body = item["content"]
            for name, targets in by_name.items():
                if name != symbol["name"] and re.search(rf"\b{re.escape(name)}\s*\(", body):
                    for target in targets:
                        calls.append({"from": symbol["uri"], "to": target, "evidence": f"{path}:{symbol['line']}"})
    changed = set()
    if isinstance(change_set, list):
        changed = {relative_path(item.get("path") if isinstance(item, Mapping) else item, "change_set[].path") for item in change_set}
    elif isinstance(change_set, Mapping):
        changed = {relative_path(item, "change_set.path") for item in change_set.get("paths", [])}
    affected = sorted(changed | {edge["from"].split("/", 3)[-1].split("#", 1)[0] for edge in calls if edge["to"].split("/", 3)[-1].split("#", 1)[0] in changed})
    duplicate_names = sorted(name for name, values in by_name.items() if len(values) > 1)
    index = {"version": "2.0.0", "snapshot_sha": repo_sha, "partial": True, "quality": {"parser": "deterministic-line-adapter", "native_compiler_evidence": bool(compiler_metadata), "unknowns": ["full AST/LSP semantics require a language adapter"]}, "symbols": sorted(symbols, key=lambda i: i["uri"]), "imports": imports, "calls": calls, "dependency_graph": {"nodes": sorted({item["path"] for item in files}), "edges": imports}, "test_impact_map": {"changed_paths": sorted(changed), "affected_paths": affected}, "invalidation_set": affected, "symbol_collisions": duplicate_names}
    if duplicate_names:
        index["quality"]["unknowns"].append("symbol collisions require adapter resolution")
    return {"semantic_index": index, "symbol_graph": {"nodes": index["symbols"], "edges": [{"from": edge["from"], "to": edge["to"], "kind": "call"} for edge in calls]}, "call_graph": calls, "dependency_graph": index["dependency_graph"], "test_impact_map": index["test_impact_map"], "invalidation_set": affected}


def compile_ir(index: Mapping[str, Any], task_spec: Mapping[str, Any], source_profile: Mapping[str, Any], target_profile: Mapping[str, Any]) -> dict[str, Any]:
    if not index.get("snapshot_sha"):
        raise ContractError("INDEX_INCONSISTENT", "semantic index must be snapshot-bound")
    nodes = []
    for symbol in index.get("symbols", []):
        if not isinstance(symbol, Mapping):
            continue
        nodes.append({"id": symbol.get("uri"), "kind": symbol.get("kind", "unknown"), "name": symbol.get("name"), "source": {"path": symbol.get("path"), "line": symbol.get("line")}, "semantics": {"preserve": True}})
    ir = {"version": "2.0.0", "snapshot_sha": index["snapshot_sha"], "task_spec_hash": digest(task_spec), "source_profile": dict(source_profile), "target_profile": dict(target_profile), "nodes": nodes, "unknown_semantics": ["provider-specific behavior", "runtime side effects not represented by static index"], "status": "PARTIAL" if index.get("partial") else "COMPILED"}
    return {"semantic_ir": ir, "rule_dsl": {"rules": [{"id": "preserve-public-symbols", "when": "node.kind in [type,function]", "assert": "target.symbol exists"}]}, "mutation_dsl": {"mutations": []}, "scenario_dsl": {"scenarios": []}, "evidence_dsl": {"required": ["source-index", "target-build", "differential-runtime"]}, "source_map": {str(node["id"]): node["source"] for node in nodes}}


def change_graph(task_spec: Mapping[str, Any], snapshot: Mapping[str, Any], patches: Any, lineage: Any, validations: Any) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    task_id = task_spec.get("id") or digest(task_spec)
    nodes.append({"id": f"requirement:{task_id}", "type": "requirement", "status": "DECLARED", "payload": dict(task_spec)})
    patch_items = patches if isinstance(patches, list) else []
    for index, item in enumerate(patch_items):
        value = require_mapping(item, "patches[]")
        node_id = f"patch:{index}:{digest(value)}"
        nodes.append({"id": node_id, "type": "patch", "status": str(value.get("status", "UNVERIFIED")), "payload": value})
        edges.append({"from": f"requirement:{task_id}", "to": node_id, "type": "implements"})
    for index, item in enumerate(validations if isinstance(validations, list) else []):
        value = require_mapping(item, "validation_results[]")
        node_id = f"validation:{index}:{digest(value)}"
        nodes.append({"id": node_id, "type": "validation", "status": str(value.get("status", "NOT_RUN")), "payload": value})
        for patch in [node for node in nodes if node["type"] == "patch"]:
            edges.append({"from": patch["id"], "to": node_id, "type": "validated-by"})
    unverified = [node["id"] for node in nodes if node["type"] != "requirement" and node["status"] not in {"PASS", "PASSED", "ACCEPTED"}]
    graph = {"version": "2.0.0", "snapshot_sha": snapshot.get("sha256") or digest(snapshot), "nodes": nodes, "edges": edges, "acyclic": True, "unverified_nodes": unverified, "lineage": lineage or {}}
    return {"change_graph": graph, "change_node": nodes[-1] if len(nodes) > 1 else nodes[0], "change_edge": edges, "merge_plan": {"status": "BLOCKED" if unverified else "READY_FOR_REVIEW", "required": ["conflict-free", "validation-pass", "acceptance"]}, "revert_plan": {"status": "PLANNED", "dependency_closure": [node["id"] for node in nodes], "testable": bool(nodes)}, "provenance_commit": {"status": "NOT_RUN", "git_execution": False}}


def validation_plan(task_spec: Mapping[str, Any], change_graph_value: Mapping[str, Any], repository_profile: Mapping[str, Any], risk: Mapping[str, Any], test_catalog: Any) -> dict[str, Any]:
    criteria = task_spec.get("acceptance_criteria", task_spec.get("acceptance", []))
    if isinstance(criteria, Mapping):
        criteria = list(criteria)
    if not isinstance(criteria, list):
        criteria = []
    catalog = test_catalog if isinstance(test_catalog, list) else []
    gates: list[dict[str, Any]] = []
    for index, criterion in enumerate(criteria or ["schema-valid"]):
        criterion_id = str(criterion.get("id") if isinstance(criterion, Mapping) else criterion)
        candidates = [item for item in catalog if isinstance(item, Mapping) and criterion_id in str(item.get("criterion", item.get("id", "")))]
        gates.append({"id": f"gate-{index}-{criterion_id}", "criterion": criterion_id, "validator": (candidates[0].get("validator") if candidates else "deterministic-validator"), "status": "NOT_RUN", "evidence_required": True})
    for gate in gates:
        if gate["criterion"] in {"security", "rollback", "deployment-complete"}:
            gate["requires_external_adapter"] = True
    dag = {"version": "2.0.0", "nodes": gates, "edges": [{"from": gates[index - 1]["id"], "to": gates[index]["id"]} for index in range(1, len(gates))], "snapshot_sha": repository_profile.get("snapshot_sha")}
    return {"validation_plan": {"risk": dict(risk), "criterion_count": len(gates)}, "validation_dag": dag, "critical_path": [gate["id"] for gate in gates], "coverage_map": {gate["criterion"]: gate["id"] for gate in gates}, "validation_budget": {"max_nodes": len(gates), "status": "VALID" if gates else "INCOMPLETE"}}


def contract_diff(baseline: Mapping[str, Any], candidate: Mapping[str, Any], consumers: Any, policy: Mapping[str, Any]) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    def walk(left: Any, right: Any, path: str) -> None:
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            for key in sorted(set(left) - set(right)):
                changes.append({"path": f"{path}/{key}", "kind": "removed", "breaking": key in set(left.get("required", [])) or key in {"security", "permissions", "authorization"}})
            for key in sorted(set(right) - set(left)):
                changes.append({"path": f"{path}/{key}", "kind": "added", "breaking": False})
            for key in sorted(set(left) & set(right)):
                walk(left[key], right[key], f"{path}/{key}")
        elif isinstance(left, list) and isinstance(right, list):
            for value in left:
                if value not in right:
                    changes.append({"path": path, "kind": "list-removed", "value": value, "breaking": True})
        elif type(left) is not type(right) or left != right:
            changes.append({"path": path, "kind": "changed", "before": left, "after": right, "breaking": True})
    walk(baseline, candidate, "")
    breaking = [change for change in changes if change["breaking"]]
    unknown_consumers = not isinstance(consumers, list) or not consumers
    status = "BLOCKED" if unknown_consumers and breaking else "COMPATIBLE" if not breaking else "BREAKING"
    return {"compatibility_report": {"status": status, "change_count": len(changes), "policy": dict(policy), "unknown_consumers": unknown_consumers}, "breaking_changes": breaking, "adapter_plan": {"required": bool(breaking), "steps": [f"adapt {item['path']}" for item in breaking]}, "migration_plan": {"rehearsal_required": bool(breaking), "steps": ["expand", "migrate", "contract"] if breaking else []}, "rollback_contract": {"valid": bool(not breaking or policy.get("rollback_required", True)), "steps": ["restore baseline contract", "verify consumers"]}}
