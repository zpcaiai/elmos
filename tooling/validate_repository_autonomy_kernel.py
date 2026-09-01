"""Validate the supplied autonomy ZIP without executing any package content."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

EXPECTED_SKILLS = {
    "task-spec-delta-compiler", "durable-run-orchestrator", "execution-authority-kernel", "typed-tool-runtime",
    "policy-hook-kernel", "two-phase-secretless-sandbox", "workspace-lease-fencing", "artifact-evidence-protocol",
    "repository-census", "incremental-semantic-index", "semantic-ir-compiler", "changegraph-vcs", "validation-dag",
    "independent-verification-mesh", "evidence-release-gate", "contract-compatibility-engine", "prefix-stable-context-planner",
    "lazy-tool-loader", "model-state-continuity", "multi-agent-worktree-coordinator", "phase-aware-model-router",
    "layered-cache-fabric", "cost-eta-observability", "tiered-security-assurance", "session-time-travel",
    "capability-package-registry", "demonstration-to-skill", "auto-improvement-inbox-and-skill-curator", "agent-arena",
    "repository-model-elo", "repository-gym-golden-routes",
}

EXPECTED_SQL_TABLES = {
    "runs", "steps", "events", "checkpoints", "leases", "artifacts", "evidence", "repository_snapshots",
    "semantic_indices", "change_nodes", "change_edges", "tool_calls", "policy_decisions", "approvals",
    "validations", "findings", "acceptance_decisions", "cache_entries", "cost_events", "capability_packages",
    "adapter_conformance", "eval_runs", "elo_ratings",
    "external_operations", "external_receipts", "outbox_events", "outbox_receipts", "inbox_events", "secret_leases",
    "certification_evidence", "certification_runs", "customer_acceptance",
    # V007, the capability core's stream tables. They carry the autonomy_kernel_
    # prefix on purpose: the control plane already owns autonomy_events,
    # autonomy_artifacts and autonomy_leases, and a schema holding both
    # autonomy_event and autonomy_events is a wrong-table bug waiting for a
    # tired reader. Listed here so the consolidated schema is checked for them
    # too - 001_autonomy_kernel.sql is the union of the migrations, and a
    # database bootstrapped from it must be usable by the whole package.
    "kernel_event", "kernel_kv", "kernel_artifact", "kernel_lease",
    "kernel_lease_watermark",
}

RELEASED_MIGRATION_DIGESTS = {
    "V001__autonomy_run_core.sql": "8e7936cd5099aad191c687d8b90789349745785f9b6d3eb298ecfad7f1e55c61",
    "V002__autonomy_artifact_repository.sql": "dc432a63a20630f986f8b6e1b7520c6373fd00a8821d9d69a379fd6f52df15ce",
    "V003__autonomy_tool_policy_verification.sql": "f92730ada3ad6e0130dced968bf97579f1912e1209b555a30d51dfbdd0926703",
    "V004__autonomy_cache_cost_registry_eval.sql": "55b950131d8cf1ec788b8172a7d23e71ee7bc37168b5dbd5eb318f2dae8f914b",
    # V005 and V006 shipped unpinned. A released migration that nothing pins can
    # drift silently, which is the exact failure the four above exist to catch,
    # so they are pinned now rather than left as a gap that happens to be quiet.
    "V005__autonomy_external_operations_delivery.sql": "c8e128c5b7ffe123d8a7a233401650c1e088c906d8cbc080f5227e7f2517b2c7",
    "V006__autonomy_certification_customer_acceptance.sql": "1374255b304aff84a3731a6a3f924b45bf1f26eb68a8a00c74daf131521ad445",
    "V007__autonomy_kernel_core_streams.sql": "3aff56c3fbba729bfe29ff4edd75cc4dacc7da4a63568dbc1fa83871964ac77a",
}


def validate(archive: Path) -> dict[str, object]:
    if not archive.is_file():
        raise ValueError(f"archive not found: {archive}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        if any(name.startswith("/") or ".." in Path(name).parts for name in names):
            raise ValueError("archive contains an unsafe path")
        root = "elmos-repository-autonomy-kernel-v2.0.0/"
        skill_names = {name[len(root + "skills/"):].split("/", 1)[0] for name in names if name.startswith(root + "skills/") and name.endswith("/SKILL.md")}
        if skill_names != EXPECTED_SKILLS:
            raise ValueError(f"skill inventory mismatch: expected {len(EXPECTED_SKILLS)}, got {len(skill_names)}")
        required = [root + "PACKAGE_MANIFEST.yaml", root + "TASKS.md", root + "reference-kernel/src/elmos_autonomy/state_machine.py"]
        missing = [name for name in required if name not in names]
        if missing:
            raise ValueError(f"required package files missing: {missing}")
        manifest = zf.read(root + "PACKAGE_MANIFEST.yaml").decode("utf-8")
        if "skills: 31" not in manifest or "globalJsonSchemas: 20" not in manifest:
            raise ValueError("manifest counts do not match the package contract")
    package_root = Path(__file__).resolve().parents[1] / "packages" / "repository-autonomy-kernel"
    dispatcher = (package_root / "src" / "elmos_repository_autonomy" / "dispatcher.py").read_text(encoding="utf-8")
    missing_handlers = sorted(f"_handle_{skill.replace('-', '_')}" for skill in EXPECTED_SKILLS if f"def _handle_{skill.replace('-', '_')}" not in dispatcher)
    if missing_handlers:
        raise ValueError(f"repository implementation is missing handlers: {missing_handlers}")
    sql = (package_root / "sql" / "001_autonomy_kernel.sql").read_text(encoding="utf-8")
    missing_tables = sorted(f"autonomy_{table}" for table in EXPECTED_SQL_TABLES if f"create table if not exists autonomy_{table}" not in sql)
    if missing_tables:
        raise ValueError(f"repository migration is missing tables: {missing_tables}")
    for name, expected_digest in RELEASED_MIGRATION_DIGESTS.items():
        observed = hashlib.sha256((package_root / "sql" / "migrations" / name).read_bytes()).hexdigest()
        if observed != expected_digest:
            raise ValueError(f"released migration drifted: {name}")
    asset_requirements = {
        "contracts/openapi/*.yaml": 4,
        "policies/rego/*.rego": 4,
        # 7 since the capability core merged in and brought V007.
        "sql/migrations/V*.sql": 7,
        "deployment/kubernetes/*.yaml": 3,
    }
    for pattern, expected_count in asset_requirements.items():
        actual_count = len(list((package_root / pattern.split("/", 1)[0]).glob("/".join(pattern.split("/")[1:]))))
        if actual_count != expected_count:
            raise ValueError(f"asset inventory mismatch for {pattern}: expected {expected_count}, got {actual_count}")
    return {"archive": str(archive), "sha256": digest, "entry_count": len(names), "skill_count": len(skill_names), "executed_package_code": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", nargs="?", default="skills/subskills/elmos-repository-autonomy-kernel-v2.0.0(1).zip")
    args = parser.parse_args()
    try:
        print(json.dumps(validate(Path(args.archive)), ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "BLOCKED", "code": "PACKAGE_INVALID", "message": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
