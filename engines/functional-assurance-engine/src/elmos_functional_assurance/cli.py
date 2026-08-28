"""Command Line Interface for Functional Assurance & Certification Engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .domain import FunctionalAssuranceContext
from .kernel import FunctionalAssuranceKernel
from .workflows import CertificationWorkflowRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Elmos Functional Assurance & Certification CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate a specific skill")
    eval_parser.add_argument("--skill", required=True, help="Skill name")
    eval_parser.add_argument("--tenant-id", default="TENANT_CLI_01")
    eval_parser.add_argument("--project-id", default="PROJECT_CLI_01")
    eval_parser.add_argument("--candidate-digest", default="sha256:" + "0" * 64)
    eval_parser.add_argument("--payload", help="JSON payload string")
    eval_parser.add_argument("--payload-file", help="Path to JSON payload file")

    # certify command
    cert_parser = subparsers.add_parser("certify", help="Run full certification campaign")
    cert_parser.add_argument("--candidate-digest", required=True)
    cert_parser.add_argument("--tenant-id", default="TENANT_CLI_01")
    cert_parser.add_argument("--project-id", default="PROJECT_CLI_01")
    cert_parser.add_argument("--assurance-level", default="E4")
    cert_parser.add_argument("--sector", choices=["AVIATION", "MEDICAL", "AUTOMOTIVE", "RAIL", "FINANCIAL"])
    cert_parser.add_argument("--output", help="Output JSON file for certificate")

    # verify-certificate command
    verify_parser = subparsers.add_parser("verify-certificate", help="Verify a certificate record")
    verify_parser.add_argument("--cert-file", required=True, help="Path to certificate JSON file")

    args = parser.parse_args(argv)
    kernel = FunctionalAssuranceKernel()

    if args.command == "evaluate":
        payload: dict[str, Any] = {}
        if args.payload:
            payload = json.loads(args.payload)
        elif args.payload_file:
            payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))

        context = FunctionalAssuranceContext(
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            execution_epoch="EPOCH_CLI",
            fencing_token=1,
            candidate_digest=args.candidate_digest,
            base_evidence_receipt="BASE_EVIDENCE_CLI_OK",
            authority_digest="AUTH_CLI_OK",
        )
        res = kernel.dispatch(args.skill, payload, context)
        print(json.dumps(res, indent=2))
        return 0 if res.get("decision") != "NON_CONFORMING" else 1

    if args.command == "certify":
        context = FunctionalAssuranceContext(
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            execution_epoch="EPOCH_CLI",
            fencing_token=1,
            candidate_digest=args.candidate_digest,
            base_evidence_receipt="BASE_EVIDENCE_CLI_OK",
            authority_digest="AUTH_CLI_OK",
        )
        runner = CertificationWorkflowRunner(kernel)
        res = runner.run_full_certification_campaign(
            context,
            target_assurance_level=args.assurance_level,
            sector=args.sector,
        )
        output_json = json.dumps(res, indent=2)
        if args.output:
            Path(args.output).write_text(output_json, encoding="utf-8")
        print(output_json)
        return 0

    if args.command == "verify-certificate":
        cert_data = json.loads(Path(args.cert_file).read_text(encoding="utf-8"))
        res = kernel.verify_certificate_record(cert_data)
        print(json.dumps(res, indent=2))
        return 0 if res.get("signature_valid") else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
