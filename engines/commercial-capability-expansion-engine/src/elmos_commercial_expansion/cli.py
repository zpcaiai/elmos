"""CLI for Elmos Commercial Capability Expansion Engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict

from .models import GateLevel, KernelType, TaskContext
from .service import CommercialCapabilityExpansionService


def get_default_service() -> CommercialCapabilityExpansionService:
    root = Path(__file__).resolve().parents[4]
    manifest_path = root / "skills/elmos-commercial-capability-expansion-skills-v2.0.0/manifest.json"
    manifest_data = {}
    if manifest_path.is_file():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return CommercialCapabilityExpansionService(manifest_data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="elmos-commercial-expansion",
        description="Elmos Commercial Capability Expansion Engine v2.0.0",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Show engine status and registered skills")
    p_status.add_argument("--json", action="store_true", help="Output as JSON")

    # catalog
    p_cat = subparsers.add_parser("catalog", help="List all skills in catalog")
    p_cat.add_argument("--kernel", type=str, help="Filter by kernel (e.g. K1-skill-runtime)")
    p_cat.add_argument("--json", action="store_true", help="Output as JSON")

    # dag
    p_dag = subparsers.add_parser("dag", help="Show cross-kernel execution DAG")
    p_dag.add_argument("--json", action="store_true", help="Output as JSON")

    # orchestrate
    p_orch = subparsers.add_parser("orchestrate", help="Run full 8-kernel transformation workflow")
    p_orch.add_argument("--repo-id", default="repo-sample", help="Repository ID")
    p_orch.add_argument("--tenant-id", default="tenant-commercial", help="Tenant ID")
    p_orch.add_argument("--intent", default="Migrate to modern framework", help="Change intent")
    p_orch.add_argument("--files", nargs="+", default=["src/main.py"], help="Target files")
    p_orch.add_argument("--gate", default="E3", choices=["E0", "E1", "E2", "E3", "E4", "E5"], help="Target Gate")
    p_orch.add_argument("--json", action="store_true", help="Output as JSON")

    # provenance
    p_prov = subparsers.add_parser("provenance", help="Generate SLSA provenance attestation")
    p_prov.add_argument("--subject", default="target-artifact", help="Subject artifact name")
    p_prov.add_argument("--digest", default="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", help="Subject SHA-256 digest")
    p_prov.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args(argv)
    svc = get_default_service()

    if args.command == "status":
        status_info = {
            "engine": "elmos-commercial-capability-expansion-engine",
            "version": "2.0.0",
            "registered_skills_count": len(svc.k1.registry),
            "kernels_ready": [k.value for k in KernelType],
            "status": "READY",
        }
        if args.json:
            print(json.dumps(status_info, indent=2))
        else:
            print(f"Elmos Commercial Capability Expansion Engine v{status_info['version']}")
            print(f"Registered Skills: {status_info['registered_skills_count']}")
            print(f"Kernels Ready: {len(status_info['kernels_ready'])}")
        return 0

    elif args.command == "catalog":
        skills = list(svc.k1.registry.values())
        if args.kernel:
            skills = [s for s in skills if s.kernel.value == args.kernel]
        if args.json:
            print(json.dumps([s.to_dict() for s in skills], indent=2))
        else:
            print(f"Total skills listed: {len(skills)}")
            for s in skills:
                print(f"  [{s.kernel.value}] {s.id} ({s.priority.value}): {s.objective[:70]}")
        return 0

    elif args.command == "dag":
        pipeline = [
            "K1-skill-runtime",
            "K2-repository-intelligence",
            "K3-transformation",
            "K4-build-execution",
            "K5-verification",
            "K6-security-governance",
            "K7-database-data",
            "K8-observability-evolution",
        ]
        dag_info = {
            "pipeline": pipeline,
            "acyclic": True,
            "mandatory_flow": "Task -> Policy -> Repository Graph -> Risk/Evidence Plan -> Transformation -> Sandboxed Build/Run -> Verification -> Evidence Bundle -> E0-E5 Decision -> Artifact/Provenance -> Trajectory Dataset",
        }
        if args.json:
            print(json.dumps(dag_info, indent=2))
        else:
            print("Cross-Kernel Pipeline:")
            for i, k in enumerate(pipeline):
                print(f"  {i+1}. {k}")
            print(f"\nMandatory flow: {dag_info['mandatory_flow']}")
        return 0

    elif args.command == "orchestrate":
        gate_map = {
            "E0": GateLevel.E0_INGESTION,
            "E1": GateLevel.E1_SYNTAX_COMPILE,
            "E2": GateLevel.E2_UNIT_INTEGRATION,
            "E3": GateLevel.E3_SECURITY_ISOLATION,
            "E4": GateLevel.E4_DIFFERENTIAL_RUNTIME,
            "E5": GateLevel.E5_FORMAL_PROVENANCE,
        }
        target_gate = gate_map.get(args.gate, GateLevel.E3_SECURITY_ISOLATION)
        ctx = TaskContext(
            tenant_id=args.tenant_id,
            repository_id=args.repo_id,
            objective=args.intent,
        )
        res = svc.run_commercial_workflow(
            context=ctx,
            target_files=args.files,
            change_intent=args.intent,
            target_gate=target_gate,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Orchestration Outcome: {res['status']}")
            print(f"Task ID: {res['task_id']}")
            print(f"Gate Evaluated: {args.gate} -> Passed: {res['gate_decision']['passed']}")
            print(f"SLSA Attestation ID: {res['provenance']['attestation_id']}")
            print(f"Duration: {res['duration_ms']} ms")
        return 0

    elif args.command == "provenance":
        prov = svc.k6.generate_slsa_provenance(
            subject_name=args.subject,
            subject_digest=args.digest,
            materials=[{"uri": "git+repo", "digest": "HEAD"}],
            invocation_params={"builder": "cli"},
        )
        if args.json:
            print(json.dumps(prov.to_dict(), indent=2))
        else:
            print(f"SLSA Provenance Attestation ID: {prov.attestation_id}")
            print(f"Signature: {prov.signature}")
            print(f"Builder ID: {prov.builder_id}")
            print(f"Level: {prov.slsa_level}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
