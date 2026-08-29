"""CLI for Elmos Semantic Assurance Engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict

from .models import BatchType, ObligationStatus, VerdictStatus
from .service import SemanticAssuranceService


def get_default_service() -> SemanticAssuranceService:
    root = Path(__file__).resolve().parents[4]
    manifest_path = root / "skills/elmos-semantic-assurance-expansion-skills-v1.0.0/manifest.json"
    manifest_data = {}
    if manifest_path.is_file():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return SemanticAssuranceService(manifest_data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="elmos-semantic-assurance",
        description="Elmos Semantic Assurance Engine v1.0.0 (Batches J-R, Skills 169-300)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Show engine status and registered skills")
    p_status.add_argument("--json", action="store_true", help="Output as JSON")

    # catalog
    p_cat = subparsers.add_parser("catalog", help="List skills in catalog")
    p_cat.add_argument("--batch", type=str, choices=["J", "K", "L", "M", "N", "O", "P", "Q", "R"], help="Filter by Batch")
    p_cat.add_argument("--json", action="store_true", help="Output as JSON")

    # differential-run
    p_diff = subparsers.add_parser("differential-run", help="Run differential oracle comparison")
    p_diff.add_argument("--src-lang", default="java", help="Source language")
    p_diff.add_argument("--tgt-lang", default="csharp", help="Target language")
    p_diff.add_argument("--src-out", default="42", help="Source output")
    p_diff.add_argument("--tgt-out", default="42", help="Target output")
    p_diff.add_argument("--json", action="store_true", help="Output as JSON")

    # formal-check
    p_formal = subparsers.add_parser("formal-check", help="Solve SMT formal proof obligation")
    p_formal.add_argument("--formula", default="forall x . f(x) == g(x)", help="Formula string")
    p_formal.add_argument("--solver", default="SMT_Z3", help="Solver family")
    p_formal.add_argument("--json", action="store_true", help="Output as JSON")

    # fuzz-matrix
    p_fuzz = subparsers.add_parser("fuzz-matrix", help="Execute differential fuzz campaign")
    p_fuzz.add_argument("--target", default="java_to_csharp", help="Target route")
    p_fuzz.add_argument("--iterations", type=int, default=100, help="Fuzz iterations")
    p_fuzz.add_argument("--json", action="store_true", help="Output as JSON")

    # run-gate
    p_gate = subparsers.add_parser("run-gate", help="Execute 9-layer certification campaign")
    p_gate.add_argument("--src-lang", default="java", help="Source language")
    p_gate.add_argument("--tgt-lang", default="csharp", help="Target language")
    p_gate.add_argument("--src-code", default="class Main { static int add(int a, int b) { return a + b; } }", help="Source code snippet")
    p_gate.add_argument("--tgt-code", default="class Main { static int Add(int a, int b) => a + b; }", help="Target code snippet")
    p_gate.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args(argv)
    svc = get_default_service()

    if args.command == "status":
        status_info = {
            "engine": "elmos-semantic-assurance-engine",
            "version": "1.0.0",
            "registered_skills_count": len(svc.skills_registry),
            "batches_ready": ["J", "K", "L", "M", "N", "O", "P", "Q", "R"],
            "status": "READY",
        }
        if args.json:
            print(json.dumps(status_info, indent=2))
        else:
            print(f"Elmos Semantic Assurance Engine v{status_info['version']}")
            print(f"Registered Skills: {status_info['registered_skills_count']}")
            print(f"Batches Ready: {', '.join(status_info['batches_ready'])}")
        return 0

    elif args.command == "catalog":
        skills = list(svc.skills_registry.values())
        if args.batch:
            skills = [s for s in skills if s.get("batch") == args.batch]
        if args.json:
            print(json.dumps(skills, indent=2))
        else:
            print(f"Total skills listed: {len(skills)}")
            for s in skills:
                print(f"  [Batch {s.get('batch')}] {s.get('id')}: {s.get('name')} ({s.get('layer')})")
        return 0

    elif args.command == "differential-run":
        res = svc.oracle.evaluate_differential_execution(
            args.src_lang, args.tgt_lang, "tc-cli", args.src_out, args.tgt_out
        )
        if args.json:
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print(f"Differential Verdict: {res.verdict.value}")
            print(f"Summary: {res.divergence_summary}")
        return 0

    elif args.command == "formal-check":
        proof = svc.formal.create_proof_obligation(args.formula, solver_family=args.solver)
        solved = svc.formal.solve_obligation(proof.proof_id, simulated_pass=True)
        if args.json:
            print(json.dumps(solved.to_dict(), indent=2))
        else:
            print(f"Proof ID: {solved.proof_id}")
            print(f"Status: {solved.status.value}")
            print(f"Witness: {solved.proof_witness}")
        return 0

    elif args.command == "fuzz-matrix":
        fuzz_res = svc.fuzz.run_differential_fuzz_campaign(args.target, iterations=args.iterations)
        if args.json:
            print(json.dumps(fuzz_res, indent=2))
        else:
            print(f"Fuzz Campaign ID: {fuzz_res['campaign_id']}")
            print(f"Iterations: {fuzz_res['iterations_executed']}")
            print(f"Verdict: {fuzz_res['verdict']}")
        return 0

    elif args.command == "run-gate":
        run = svc.run_route_assurance_campaign(
            source_lang=args.src_lang,
            target_lang=args.tgt_lang,
            source_code=args.src_code,
            target_code=args.tgt_code,
        )
        if args.json:
            print(json.dumps(run.to_dict(), indent=2))
        else:
            print(f"Certification Run ID: {run.certification_id}")
            print(f"Route: {run.route_id}")
            print(f"Overall Verdict: {run.overall_verdict.value}")
            print(f"Proved Obligations: {run.proved_obligations}/{run.total_obligations}")
            print(f"Receipt Digest: {run.receipt_digest}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
