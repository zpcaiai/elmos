#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import sys
import json
from pathlib import Path
from _common import load, real_files, resolve_ref


def validate_certification_corpus(pack, corpus_key, failures):
    path = pack / "corpus" / corpus_key / "manifest.json"
    if not path.is_file():
        failures.append(f"{corpus_key} corpus manifest missing")
        return
    try:
        manifest = load(path)
    except Exception as e:
        failures.append(f"{corpus_key} corpus manifest invalid: {e}")
        return
    if manifest.get("status") != "passed":
        failures.append(f"{corpus_key} corpus status must be passed")
    for field in ("source_digest", "dataset_digest"):
        value = manifest.get(field)
        if (
            not isinstance(value, str)
            or not value.startswith("sha256:")
            or value == "sha256:TODO"
        ):
            failures.append(f"{corpus_key} corpus {field} missing")
    refs = manifest.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        failures.append(f"{corpus_key} corpus evidence_refs empty")
    else:
        for ref in refs:
            if not resolve_ref(pack, ref):
                failures.append(f"{corpus_key} corpus missing evidence ref: {ref}")


def main():
    pack = Path(sys.argv[1])
    failures = []
    formal_campaign = None
    frontend_campaign = None
    frontend_campaign_version = None
    if subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("validate_verification_pack.py")),
            str(pack),
        ]
    ).returncode:
        failures.append("verification pack validation failed")
    try:
        manifest = load(pack / "pack.json")
        profile = load(pack / "validation-profile.json")
        oracles = load(pack / "oracle-registry.json")
        proof = load(pack / "solver/proof.json")
        assurance = load(pack / "assurance/assurance-case.json")
        evidence = load(pack / "certification/evidence.json")
        cert = load(pack / "certification/certification.json")
    except Exception as e:
        print(f"GATE FAIL: cannot load pack: {e}", file=sys.stderr)
        return 2
    requested_certified = (
        manifest.get("status") == "certified" or cert.get("status") == "certified"
    )
    if manifest.get("status") != cert.get("status"):
        failures.append("pack and certification status mismatch")
    if manifest.get("formal_route_campaign") is not None:
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("validate_formal_route_campaign.py")),
                str(pack),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            formal_campaign = json.loads(completed.stdout.strip().splitlines()[-1])
        except Exception:
            formal_campaign = {
                "status": "invalid",
                "formal_ready": False,
                "errors": ["formal route validator emitted invalid JSON"],
            }
        if completed.returncode or formal_campaign.get("status") != "valid":
            details = formal_campaign.get("errors") or [
                completed.stderr.strip() or "unknown formal route validation error"
            ]
            failures.extend(
                f"formal route campaign invalid: {detail}" for detail in details
            )
        elif requested_certified:
            if formal_campaign.get("formal_ready") is not True:
                failures.append("formal route campaign is not proof-ready")
            if formal_campaign.get("certification_ready") is not True:
                failures.append("formal route campaign is not certification-ready")
            if formal_campaign.get("independent_verification_status") != "PASSED":
                failures.append(
                    "formal route campaign independent verification is not PASSED"
                )
    if (
        manifest.get("frontend_formal_route_campaign") is not None
        and manifest.get("frontend_formal_route_campaign_v2") is not None
    ):
        failures.append(
            "frontend v1 and v2 campaign declarations are mutually exclusive"
        )
    if manifest.get("frontend_formal_route_campaign_v2") is not None:
        frontend_campaign_version = 2
        completed = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).with_name(
                        "validate_frontend_formal_route_campaign_v2.py"
                    )
                ),
                str(pack),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            frontend_campaign = json.loads(completed.stdout.strip().splitlines()[-1])
        except Exception:
            frontend_campaign = {
                "status": "invalid",
                "structural_status": "FAILED",
                "model_formal_ready": False,
                "browser_ready": False,
                "native_ready": False,
                "runtime_ready": False,
                "independent_ready": False,
                "certification_ready": False,
                "errors": ["frontend v2 formal validator emitted invalid JSON"],
            }
        if completed.returncode or frontend_campaign.get("status") != "valid":
            details = frontend_campaign.get("errors") or [
                completed.stderr.strip()
                or "unknown frontend v2 formal validation error"
            ]
            failures.extend(
                f"frontend v2 formal route campaign invalid: {detail}"
                for detail in details
            )
        elif requested_certified:
            for field in (
                "model_formal_ready",
                "formal_ready",
                "browser_ready",
                "native_ready",
                "runtime_ready",
                "independent_ready",
                "certification_ready",
            ):
                if frontend_campaign.get(field) is not True:
                    failures.append(f"frontend v2 campaign {field} is not true")
    if (
        manifest.get("frontend_formal_route_campaign") is not None
        and frontend_campaign_version is None
    ):
        frontend_campaign_version = 1
        completed = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).with_name(
                        "validate_frontend_formal_route_campaign.py"
                    )
                ),
                str(pack),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            frontend_campaign = json.loads(completed.stdout.strip().splitlines()[-1])
        except Exception:
            frontend_campaign = {
                "status": "invalid",
                "structural_status": "FAILED",
                "local_equivalence_status": "INCOMPLETE",
                "bounded_proof_profile_ready": False,
                "formal_ready": False,
                "external_evidence_status": "NOT_RUN",
                "certification_ready": False,
                "errors": ["frontend formal validator emitted invalid JSON"],
            }
        if completed.returncode or frontend_campaign.get("status") != "valid":
            details = frontend_campaign.get("errors") or [
                completed.stderr.strip() or "unknown frontend formal validation error"
            ]
            failures.extend(
                f"frontend formal route campaign invalid: {detail}"
                for detail in details
            )
        elif requested_certified:
            if frontend_campaign.get("formal_ready") is not True:
                failures.append("frontend formal route campaign is not proof-ready")
            if frontend_campaign.get("certification_ready") is not True:
                failures.append(
                    "frontend formal route campaign is not certification-ready"
                )
            if frontend_campaign.get("external_evidence_status") != "PASSED":
                failures.append(
                    "frontend formal route campaign external evidence is not PASSED"
                )
    if requested_certified and formal_campaign is None and frontend_campaign is None:
        failures.append("certified pack must declare a strict formal route campaign")
    metrics = {}
    metrics.update(evidence.get("metrics", {}))
    metrics.update(cert.get("metrics", {}))
    thresholds = {
        "property_pass_rate": 1.0,
        "metamorphic_pass_rate": 1.0,
        "mutation_score": 0.80,
        "fuzz_campaign_pass_rate": 1.0,
        "model_transition_coverage": 0.95,
        "p0_contract_pass_rate": 1.0,
        "data_money_invariant_pass_rate": 1.0,
        "security_property_pass_rate": 1.0,
        "query_equivalence_pass_rate": 1.0,
        "numeric_verification_pass_rate": 1.0,
        "counterexample_replay_pass_rate": 1.0,
        "representative_workload_pass_rate": 1.0,
        "source_map_coverage": 0.95,
        "evidence_trace_coverage": 0.95,
        "assurance_claim_support_rate": 1.0,
    }
    if requested_certified:
        for k, t in thresholds.items():
            if float(metrics.get(k, 0)) < t:
                failures.append(f"{k} below {t}")
        zero = [
            "critical_unknown_obligations",
            "unresolved_oracle_conflicts",
            "surviving_critical_mutants",
            "critical_fuzz_crashes",
            "unreplayed_counterexamples",
            "security_property_violations",
            "money_invariant_violations",
            "forbidden_concurrency_outcomes",
            "race_deadlock_liveness_violations",
            "query_equivalence_failures",
            "numeric_precision_regressions",
            "invalid_or_unknown_required_proofs",
            "unsupported_p0_claims",
            "test_integrity_violations",
            "unapproved_oracle_changes",
            "unapproved_tolerance_changes",
        ]
        z = {}
        z.update(evidence.get("zero_tolerance", {}))
        z.update(cert.get("zero_tolerance", {}))
        for k in zero:
            if z.get(k, 1) != 0:
                failures.append(f"{k} must be zero")
        p0_claim_ids = {
            x.get("claim_id")
            for x in profile.get("claims", [])
            if x.get("criticality") == "P0"
        }
        property_claims = {}
        for property_path in (
            sorted((pack / "properties").rglob("*.json"))
            if (pack / "properties").is_dir()
            else []
        ):
            try:
                property_spec = load(property_path)
            except Exception as e:
                failures.append(f"cannot load property spec {property_path}: {e}")
                continue
            property_id = property_spec.get("property_id")
            if property_id in property_claims:
                failures.append(f"duplicate property_id: {property_id}")
            property_claims[property_id] = property_spec.get("claim_id")
        proof_property_id = proof.get("property_id")
        if proof_property_id not in property_claims:
            failures.append(
                f"proof references unknown property_id: {proof_property_id}"
            )
        elif (
            proof.get("status")
            in {"disproved", "unknown", "timeout", "unsupported", "invalid"}
            and property_claims[proof_property_id] in p0_claim_ids
        ):
            failures.append("required P0 proof is not resolved")
        for corpus_key in ("negative", "holdout", "representative-workloads"):
            if not real_files(pack / "corpus" / corpus_key):
                failures.append(f"{corpus_key} corpus empty")
            validate_certification_corpus(pack, corpus_key, failures)
        for claim in assurance.get("claims", []):
            if claim.get("status") != "supported":
                failures.append(
                    f"assurance claim {claim.get('claim_id')} is not fully supported"
                )
        if not assurance.get("approvals"):
            failures.append("assurance case approvals empty")
        if oracles.get("conflicts"):
            failures.append("oracle conflicts remain")
        refs = (
            evidence.get("evidence_refs", [])
            + cert.get("evidence_refs", [])
            + assurance.get("evidence", [])
            + proof.get("evidence_refs", [])
        )
        if not refs:
            failures.append("certification evidence refs empty")
        for ref in refs:
            if not resolve_ref(pack, ref):
                failures.append(f"missing evidence ref: {ref}")
    status = "failed" if failures else "passed"
    decision = (
        ("BLOCKED" if failures else "CERTIFIED")
        if requested_certified
        else "NOT_CERTIFIED"
    )
    structural_status = "FAILED" if failures else "PASSED"
    local_equivalence_status = (
        frontend_campaign.get("local_equivalence_status", "NOT_EVALUATED")
        if frontend_campaign is not None
        else "NOT_EVALUATED"
    )
    frontend_formal_ready = (
        frontend_campaign.get("formal_ready") is True
        if frontend_campaign is not None
        else False
    )
    bounded_proof_profile_ready = (
        frontend_campaign.get("bounded_proof_profile_ready") is True
        if frontend_campaign is not None
        else False
    )
    external_evidence_status = (
        frontend_campaign.get("external_evidence_status", "NOT_RUN")
        if frontend_campaign is not None
        else "NOT_RUN"
    )
    model_formal_ready = (
        frontend_campaign.get("model_formal_ready") is True
        if frontend_campaign_version == 2 and frontend_campaign is not None
        else False
    )
    browser_ready = (
        frontend_campaign.get("browser_ready") is True
        if frontend_campaign_version == 2 and frontend_campaign is not None
        else False
    )
    native_ready = (
        frontend_campaign.get("native_ready") is True
        if frontend_campaign_version == 2 and frontend_campaign is not None
        else False
    )
    runtime_ready = (
        frontend_campaign.get("runtime_ready") is True
        if frontend_campaign_version == 2 and frontend_campaign is not None
        else False
    )
    independent_ready = (
        frontend_campaign.get("independent_ready") is True
        if frontend_campaign_version == 2 and frontend_campaign is not None
        else False
    )
    result = {
        "schema_version": 1,
        "pack_key": manifest.get("pack_key"),
        "status": status,
        "structural_gate_status": status,
        "structural_status": structural_status,
        "local_equivalence_status": local_equivalence_status,
        "bounded_proof_profile_ready": bounded_proof_profile_ready,
        "formal_ready": frontend_formal_ready,
        "external_evidence_status": external_evidence_status,
        "frontend_formal_contract_version": frontend_campaign_version,
        "model_formal_ready": model_formal_ready,
        "browser_ready": browser_ready,
        "native_ready": native_ready,
        "runtime_ready": runtime_ready,
        "independent_ready": independent_ready,
        "certification_ready": (
            frontend_campaign.get("certification_ready") is True
            if frontend_campaign is not None
            else False
        ),
        "certification_requested": requested_certified,
        "certification_decision": decision,
        "pack_status": manifest.get("status"),
        "failures": failures,
    }
    if formal_campaign is not None:
        result["formal_route_campaign"] = {
            key: formal_campaign.get(key)
            for key in (
                "status",
                "campaign_key",
                "formal_ready",
                "certification_ready",
                "independent_verification_status",
                "route_count",
                "required_obligation_count",
                "unresolved_required_obligation_ids",
                "composition_count",
                "proved_composition_count",
            )
        }
    if frontend_campaign is not None:
        result["frontend_formal_route_campaign"] = {
            key: frontend_campaign.get(key)
            for key in (
                "status",
                "campaign_key",
                "route_count",
                "profile_count",
                "structural_status",
                "local_equivalence_status",
                "bounded_proof_profile_ready",
                "formal_ready",
                "external_evidence_status",
                "certification_ready",
                "proved_route_count",
                "proved_under_assumptions_route_count",
                "native_route_count",
                "native_applicable_route_count",
                "native_passed_route_count",
                "model_formal_ready",
                "browser_ready",
                "native_ready",
                "runtime_ready",
                "independent_ready",
                "block_count",
                "scenario_count",
            )
        }
    (pack / "certification/gate-result.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    lines = [
        f"# Batch 35 gate: {manifest.get('pack_key')}",
        "",
        f"- Pack status: `{manifest.get('status')}`",
        f"- Structural status: `{structural_status}`",
        f"- Local equivalence status: `{local_equivalence_status}`",
        f"- Bounded proof profile ready: `{str(bounded_proof_profile_ready).lower()}`",
        f"- Formal ready: `{str(frontend_formal_ready).lower()}`",
        f"- External evidence status: `{external_evidence_status}`",
        f"- Model/formal ready: `{str(model_formal_ready).lower()}`",
        f"- Browser ready: `{str(browser_ready).lower()}`",
        f"- Native ready: `{str(native_ready).lower()}`",
        f"- Cross-channel runtime ready: `{str(runtime_ready).lower()}`",
        f"- Independent ready: `{str(independent_ready).lower()}`",
        f"- Certification decision: `{decision}`",
        "",
    ]
    lines += (
        (["## Failures"] + [f"- {x}" for x in failures])
        if failures
        else (
            ["The exact declared scope is certified."]
            if decision == "CERTIFIED"
            else ["The pack is structurally valid but is not certified."]
        )
    )
    (pack / "certification/gate-report.md").write_text("\n".join(lines) + "\n")
    if failures:
        print("\n".join("GATE FAIL: " + x for x in failures), file=sys.stderr)
        return 2
    print(
        f"GATE PASS: {manifest.get('pack_key')} status={manifest.get('status')} decision={decision}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
