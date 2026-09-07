#!/usr/bin/env python3
"""Generate unique allowlisted handlers for every non-special PM child Skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "docs" / "precision-migration-b01-44" / "executable-contracts.json"
OUTPUT_REGISTRY = ROOT / "docs" / "precision-migration-b01-44" / "handler-implementations.json"
OUTPUT_MODULE = ROOT / "scripts" / "precision_migration" / "generated_handlers.py"
MANIFEST = ROOT / "docs" / "precision-migration-b01-44" / "installed-manifest.json"
OUTPUT_ORCHESTRATORS = ROOT / "docs" / "precision-migration-b01-44" / "orchestrator-implementations.json"
OUTPUT_ORCHESTRATOR_MODULE = ROOT / "scripts" / "precision_migration" / "generated_orchestrators.py"
EXPECTED = 536
EXPECTED_ORCHESTRATORS = 45

ALGORITHM_BY_BATCH = {
    **{batch: "decision" for batch in (1, 4, 36, 40)},
    3: "estimate",
    **{batch: "inspect" for batch in (2, 5, 6, 17, 28, 43)},
    **{batch: "govern" for batch in (7, 44)},
    **{batch: "model" for batch in (8, 9, 10, 19)},
    **{batch: "plan" for batch in (11, 13, 31, 37, 38, 39)},
    **{batch: "transform" for batch in (12, 15, 18, 20, 21, 26, 27)},
    14: "compiler-adapter",
    **{batch: "sql-semantics" for batch in (22, 23, 24, 25)},
    29: "test-generation",
    30: "compare",
    **{batch: "validate" for batch in (32, 33)},
    **{batch: "proof-analysis" for batch in (34, 35)},
}


def canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def function_name(skill: str) -> str:
    return "execute_" + re.sub(r"[^a-z0-9]+", "_", skill.lower()).strip("_")


def declared_artifact(outputs: list[str], source_skill: str) -> str:
    for output in outputs:
        match = re.search(r"`([^`]+)`", output)
        if match:
            return match.group(1)
    return f"{source_skill}-result"


def artifact_name(source_skill: str) -> str:
    safe = re.sub(r"[^a-z0-9-]+", "-", source_skill.lower()).strip("-")
    if not safe:
        raise ValueError("source Skill cannot produce a safe artifact name")
    return f"{safe}-execution.json"


def program(contract: dict[str, Any], algorithm: str, tools: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "op": "verify-inputs",
            "input_contract_digest": canonical_digest({"inputs": contract["inputs"]}),
            "execution_policy_digest": canonical_digest(contract["execution_policy"]),
        },
        {
            "op": "execute-algorithm",
            "algorithm": algorithm,
            "workflow_digest": canonical_digest({"workflow": contract["workflow"]}),
        },
        {
            "op": "execute-native",
            "tools": tools,
            "require_all_when_requested": True,
        },
        {
            "op": "evaluate-gates",
            "gate_contract_digest": canonical_digest(
                {
                    "validation_gates": contract["validation_gates"],
                    "definition_of_done": contract["definition_of_done"],
                }
            ),
            "unresolved_differences": "block",
            "test_weakening": "forbidden",
        },
        {
            "op": "emit-artifact",
            "artifact_name": artifact_name(str(contract["source_skill"])),
            "media_type": "application/json",
            "write_policy": "write-once",
        },
    ]


def native_tools(source_skill: str, batch: int) -> list[str]:
    language_tools = {
        "java": "javac",
        "csharp": "csc",
        "go": "go",
        "rust": "rustc",
        "python": "python3",
        "typescript": "tsc",
    }
    if batch == 14:
        for language, tool in language_tools.items():
            if source_skill.startswith(language + "-"):
                return [tool]
    if batch == 18:
        tools = []
        for token, tool in (
            ("vue", "node"), ("react", "node"), ("wechat", "node"),
            ("arkui", "ohpm"), ("flutter", "flutter"),
        ):
            if token in source_skill and tool not in tools:
                tools.append(tool)
        return tools
    if batch in {19, 20, 21, 22, 23, 24, 25, 26, 27}:
        return [
            tool
            for token, tool in (
                ("oracle", "sqlplus"), ("sqlserver", "sqlcmd"),
                ("mysql", "mysql"), ("postgresql", "psql"),
            )
            if token in source_skill
        ]
    if batch == 34:
        return ["lean"]
    if batch == 35:
        return ["z3"] if any(token in source_skill for token in ("smt", "symbolic", "relational")) else []
    return []


def build_orchestrators() -> tuple[str, str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    children_by_batch: dict[int, list[str]] = {}
    for record in manifest["skills"]:
        if record["kind"] == "skill":
            children_by_batch.setdefault(int(record["batch"]), []).append(str(record["name"]))
    implementations: list[dict[str, Any]] = []
    functions: list[str] = []
    mappings: list[str] = []
    for record in manifest["skills"]:
        if record["kind"] not in {"batch-orchestrator", "global-orchestrator"}:
            continue
        skill = str(record["name"])
        source_skill = str(record["source_name"])
        handler_id = f"orchestrator-dag-v2:{source_skill}"
        function = function_name(skill)
        entrypoint = f"scripts.precision_migration.generated_orchestrators:{function}"
        if record["kind"] == "global-orchestrator":
            nodes = [
                str(item["name"])
                for item in manifest["skills"]
                if item["kind"] == "batch-orchestrator"
            ]
        else:
            nodes = sorted(children_by_batch[int(record["batch"])])
        edges = [{"from": nodes[index], "to": nodes[index + 1]} for index in range(len(nodes) - 1)]
        dag_payload = {"nodes": nodes, "edges": edges}
        implementation = {
            "schema_version": 1,
            "skill": skill,
            "source_skill": source_skill,
            "batch": record["batch"],
            "kind": record["kind"],
            "handler_id": handler_id,
            "handler_entrypoint": entrypoint,
            "function_name": function,
            "nodes": nodes,
            "edges": edges,
            "dag_digest": canonical_digest(dag_payload),
        }
        implementation["implementation_digest"] = canonical_digest(implementation)
        implementations.append(implementation)
        functions.append(
            f"def {function}(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, **kwargs: Any) -> dict[str, Any]:\n"
            "    return execute_orchestrator_dag(\n"
            "        request, entry, output_dir,\n"
            f"        expected_skill={skill!r},\n"
            f"        expected_handler_id={handler_id!r},\n"
            f"        expected_implementation_digest={implementation['implementation_digest']!r},\n"
            "        **kwargs,\n"
            "    )\n"
        )
        mappings.append(f"    {handler_id!r}: {function},")
    implementations.sort(key=lambda item: (-1 if item["batch"] is None else item["batch"], item["skill"]))
    functions.sort()
    mappings.sort()
    if len(implementations) != EXPECTED_ORCHESTRATORS:
        raise ValueError(f"orchestrator inventory mismatch: {len(implementations)}")
    registry = {
        "schema_version": 1,
        "namespace": "precision-migration-b01-44",
        "orchestrator_count": EXPECTED_ORCHESTRATORS,
        "orchestrators": implementations,
    }
    module = (
        "# Generated by tooling/generate_precision_migration_handlers.py. Do not edit.\n"
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n"
        "from scripts.precision_migration.orchestration import Handler, execute_orchestrator_dag\n\n\n"
        + "\n\n".join(functions)
        + "\n\n\nORCHESTRATOR_HANDLERS: dict[str, Handler] = {\n"
        + "\n".join(mappings)
        + "\n}\n"
    )
    return json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", module


def build() -> tuple[str, str, str, str]:
    payload = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    implementations: list[dict[str, Any]] = []
    functions: list[str] = []
    mappings: list[str] = []
    for contract in payload["contracts"]:
        batch = int(contract["batch"])
        source_skill = str(contract["source_skill"])
        if source_skill == "repository-modernization-assessment" or batch in {16, 41, 42}:
            continue
        skill = str(contract["skill"])
        handler_id = f"exact-skill-v4:{source_skill}"
        function = function_name(skill)
        entrypoint = f"scripts.precision_migration.generated_handlers:{function}"
        algorithm = ALGORITHM_BY_BATCH.get(batch)
        if algorithm is None:
            raise ValueError(f"no compiled production algorithm for B{batch:02d}: {source_skill}")
        tools = native_tools(source_skill, batch)
        implementation = {
            "schema_version": 2,
            "skill": skill,
            "source_skill": source_skill,
            "batch": batch,
            "handler_id": handler_id,
            "handler_entrypoint": entrypoint,
            "function_name": function,
            "executor": f"batch-{batch:02d}",
            "capability": source_skill,
            "algorithm": algorithm,
            "artifact_name": artifact_name(source_skill),
            "declared_artifact": declared_artifact(contract["outputs"], source_skill),
            "contract_digest": contract["contract_digest"],
            "supported_modes": contract["supported_modes"],
            "native_tools": tools,
            "program": program(contract, algorithm, tools),
            "program_version": "precision-exact-program-v1",
            "risk_tier": contract["risk_tier"],
        }
        implementation["implementation_digest"] = canonical_digest(implementation)
        implementations.append(implementation)
        functions.append(
            f"def {function}(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, "
            "*, evidence_roots: tuple[Path, ...], **kwargs: Any) -> dict[str, Any]:\n"
            "    return execute_exact_skill(\n"
            "        request, entry, output_dir, evidence_roots=evidence_roots,\n"
            f"        expected_skill={skill!r},\n"
            f"        expected_handler_id={handler_id!r},\n"
            f"        expected_implementation_digest={implementation['implementation_digest']!r},\n"
            "        **kwargs,\n"
            "    )\n"
        )
        mappings.append(f"    {handler_id!r}: {function},")
    implementations.sort(key=lambda item: (item["batch"], item["source_skill"]))
    functions.sort()
    mappings.sort()
    if len(implementations) != EXPECTED or len({item["handler_entrypoint"] for item in implementations}) != EXPECTED:
        raise ValueError(f"exact handler inventory mismatch: {len(implementations)}")
    registry = {
        "schema_version": 1,
        "namespace": "precision-migration-b01-44",
        "implementation_count": EXPECTED,
        "source_contract_registry_digest": "sha256:" + hashlib.sha256(CONTRACTS.read_bytes()).hexdigest(),
        "implementations": implementations,
    }
    registry_text = json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    module_text = (
        "# Generated by tooling/generate_precision_migration_handlers.py. Do not edit.\n"
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n"
        "from scripts.precision_migration.exact import Handler, execute_exact_skill\n\n\n"
        + "\n\n".join(functions)
        + "\n\n\nEXACT_HANDLERS: dict[str, Handler] = {\n"
        + "\n".join(mappings)
        + "\n}\n"
    )
    orchestrators, orchestrator_module = build_orchestrators()
    return registry_text, module_text, orchestrators, orchestrator_module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    registry, module, orchestrators, orchestrator_module = build()
    if args.check:
        failures = []
        if not OUTPUT_REGISTRY.is_file() or OUTPUT_REGISTRY.read_text(encoding="utf-8") != registry:
            failures.append(str(OUTPUT_REGISTRY))
        if not OUTPUT_MODULE.is_file() or OUTPUT_MODULE.read_text(encoding="utf-8") != module:
            failures.append(str(OUTPUT_MODULE))
        if not OUTPUT_ORCHESTRATORS.is_file() or OUTPUT_ORCHESTRATORS.read_text(encoding="utf-8") != orchestrators:
            failures.append(str(OUTPUT_ORCHESTRATORS))
        if not OUTPUT_ORCHESTRATOR_MODULE.is_file() or OUTPUT_ORCHESTRATOR_MODULE.read_text(encoding="utf-8") != orchestrator_module:
            failures.append(str(OUTPUT_ORCHESTRATOR_MODULE))
        if failures:
            raise SystemExit(f"generated exact handlers drifted: {failures}")
    else:
        OUTPUT_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_REGISTRY.write_text(registry, encoding="utf-8")
        OUTPUT_MODULE.write_text(module, encoding="utf-8")
        OUTPUT_ORCHESTRATORS.write_text(orchestrators, encoding="utf-8")
        OUTPUT_ORCHESTRATOR_MODULE.write_text(orchestrator_module, encoding="utf-8")
    print(json.dumps({"status": "PASS", "exact_handlers": EXPECTED, "orchestrators": EXPECTED_ORCHESTRATORS, "mode": "check" if args.check else "generate"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
