#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

FRT_EXTERNAL_CHECKS = {
    "real_source_target_builds",
    "device_matrix",
    "independent_holdout",
    "formal_proof",
    "performance",
    "chaos_dr",
    "penetration_test",
    "production_observation",
    "customer_acceptance",
}


def load(path: Path):
    return json.loads(path.read_text())


def has_real_file(path: Path) -> bool:
    for item in path.rglob("*"):
        if (
            item.is_file()
            and item.name.lower() not in {"readme.md", ".gitkeep"}
            and item.stat().st_size > 0
        ):
            return True
    return False


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir")
    args = parser.parse_args()
    pack = Path(args.pack_dir)
    here = Path(__file__).resolve().parent

    if subprocess.run(
        [sys.executable, str(here / "validate_client_pack.py"), str(pack)]
    ).returncode:
        return 1
    if subprocess.run(
        [
            sys.executable,
            str(here / "validate_ui_ir.py"),
            str(pack / "ui-ir" / "model.json"),
        ]
    ).returncode:
        return 1

    manifest = load(pack / "pack.json")
    support = load(pack / "support-matrix.json")
    fingerprint = load(pack / "source-fingerprint" / "fingerprint.json")
    ui_ir = load(pack / "ui-ir" / "model.json")
    acceptance = load(pack / "acceptance" / "acceptance-profile.json")
    evidence = load(pack / "certification" / "evidence.json")
    certification = load(pack / "certification" / "certification.json")
    failures: list[str] = []
    frontend_campaign = None
    frontend_campaign_version = None

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
                str(here / "validate_frontend_formal_route_campaign_v2.py"),
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

    if (
        manifest.get("frontend_formal_route_campaign") is not None
        and frontend_campaign_version is None
    ):
        frontend_campaign_version = 1
        completed = subprocess.run(
            [
                sys.executable,
                str(here / "validate_frontend_formal_route_campaign.py"),
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

    if manifest.get("pack_key") == "frt-g01-g30-platform":
        profile_path = pack / "acceptance" / "external-evidence-profile.json"
        qualification_plan_path = (
            pack / "acceptance" / "external-qualification-plan.json"
        )
        baseline_path = pack / "baselines" / "manifest.json"
        qualification_preflight_path = (
            pack / "certification" / "external-qualification-preflight.json"
        )
        qualification_execution_path = (
            pack / "certification" / "external-qualification-local-execution.json"
        )
        frt_request_path = pack / "certification" / "frt-gate-request.json"
        frt_result_path = pack / "certification" / "frt-gate-result.json"
        for path in (
            profile_path,
            qualification_plan_path,
            baseline_path,
            qualification_preflight_path,
            qualification_execution_path,
            frt_request_path,
            frt_result_path,
        ):
            if not path.is_file():
                failures.append(
                    f"missing FRT evidence-governance contract: {path.relative_to(pack)}"
                )
        if profile_path.is_file():
            external_profile = load(profile_path)
            if set(external_profile.get("checks", {})) != FRT_EXTERNAL_CHECKS:
                failures.append(
                    "FRT external evidence profile check inventory is not exact"
                )
            independence = external_profile.get("independence", {})
            if not all(
                independence.get(key) is True
                for key in (
                    "executor_verifier_principals_must_differ",
                    "executor_verifier_organizations_must_differ",
                    "approver_executor_principals_must_differ",
                    "verifier_approver_principals_must_differ",
                    "all_passed_records_require_three_ed25519_signatures",
                )
            ):
                failures.append(
                    "FRT external evidence independence policy is incomplete"
                )
        if baseline_path.is_file():
            baseline = load(baseline_path)
            if baseline.get("automatic_updates") is not False:
                failures.append("FRT baseline automatic updates must be disabled")
            if baseline.get("candidate_and_approved_roots_are_distinct") is not True:
                failures.append(
                    "FRT baseline candidate and approved roots must remain distinct"
                )
        if qualification_plan_path.is_file() and qualification_preflight_path.is_file():
            qualification_plan = load(qualification_plan_path)
            qualification_preflight = load(qualification_preflight_path)
            encoded_plan = json.dumps(
                qualification_plan,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            plan_digest = "sha256:" + hashlib.sha256(encoded_plan).hexdigest()
            plan_cases = qualification_plan.get("cases")
            preflight_cases = qualification_preflight.get("cases")
            if (
                qualification_plan.get("case_count") != 15
                or not isinstance(plan_cases, list)
                or len(plan_cases) != 15
            ):
                failures.append(
                    "FRT external qualification plan must contain exactly 15 cases"
                )
            if qualification_preflight.get("plan_sha256") != plan_digest:
                failures.append("FRT external qualification preflight is stale")
            if (
                qualification_preflight.get("case_count") != 15
                or not isinstance(preflight_cases, list)
                or len(preflight_cases) != 15
            ):
                failures.append(
                    "FRT external qualification preflight case inventory is incomplete"
                )
            elif any(
                not isinstance(case, dict)
                or case.get("external_state") != "NOT_RUN"
                or case.get("production_operation_authorized") is not False
                or case.get("certification") != "NOT_CERTIFIED"
                for case in preflight_cases
            ):
                failures.append(
                    "FRT external qualification preflight exceeds local authority"
                )
            boundaries = qualification_plan.get("boundaries", {})
            if (
                boundaries.get("local_harness_is_external_evidence") is not False
                or boundaries.get("preflight_can_upgrade_external_state") is not False
            ):
                failures.append(
                    "FRT external qualification plan weakens the external evidence boundary"
                )
        if (
            qualification_plan_path.is_file()
            and qualification_preflight_path.is_file()
            and qualification_execution_path.is_file()
        ):
            qualification_validator = here.parent / "frt" / "external_qualification.py"
            if not qualification_validator.is_file():
                failures.append("missing FRT local qualification execution validator")
            elif subprocess.run(
                [
                    sys.executable,
                    str(qualification_validator),
                    "check-execution",
                    "--plan",
                    str(qualification_plan_path),
                    "--preflight",
                    str(qualification_preflight_path),
                    "--execution",
                    str(qualification_execution_path),
                ]
            ).returncode:
                failures.append(
                    "FRT local qualification execution failed strict validation"
                )
            qualification_plan = load(qualification_plan_path)
            qualification_execution = load(qualification_execution_path)
            execution_cases = qualification_execution.get("cases")
            execution_counts = qualification_execution.get("local_execution_counts")
            if qualification_execution.get("plan_sha256") != canonical_digest(
                qualification_plan
            ):
                failures.append(
                    "FRT local qualification execution is stale against its plan"
                )
            if qualification_execution.get("preflight_sha256") != sha256_file(
                qualification_preflight_path
            ):
                failures.append(
                    "FRT local qualification execution is stale against its preflight"
                )
            if (
                qualification_execution.get("case_count") != 15
                or not isinstance(execution_cases, list)
                or len(execution_cases) != 15
            ):
                failures.append(
                    "FRT local qualification execution must contain exactly 15 cases"
                )
            elif any(
                not isinstance(case, dict)
                or case.get("code_contract_state") != "PASSED_LOCAL_TOOLING"
                or case.get("external_state") != "NOT_RUN"
                or case.get("production_operation_authorized") is not False
                or case.get("certification") != "NOT_CERTIFIED"
                for case in execution_cases
            ):
                failures.append(
                    "FRT local qualification execution exceeds local authority"
                )
            if (
                qualification_execution.get("code_contract_counts")
                != {"PASSED_LOCAL_TOOLING": 15}
                or not isinstance(execution_counts, dict)
                or set(execution_counts)
                - {
                    "BLOCKED_TOOLCHAIN",
                    "READY_FOR_LOCAL_EXECUTION",
                    "REQUIRES_EXTERNAL_AUTHORITY",
                }
                or execution_counts.get("REQUIRES_EXTERNAL_AUTHORITY") != 11
                or execution_counts.get("BLOCKED_TOOLCHAIN", 0)
                + execution_counts.get("READY_FOR_LOCAL_EXECUTION", 0)
                != 4
                or qualification_execution.get("external_state_counts")
                != {"NOT_RUN": 15}
                or qualification_execution.get("production_operation_authorized")
                is not False
                or qualification_execution.get("production_certification")
                != "NOT_CERTIFIED"
            ):
                failures.append(
                    "FRT local qualification execution state inventory is invalid"
                )
        if frt_result_path.is_file():
            frt_result = load(frt_result_path)
            if not frt_request_path.is_file() or frt_result.get(
                "gate_request_sha256"
            ) != sha256_file(frt_request_path):
                failures.append(
                    "FRT gate result is stale or not bound to the current request"
                )
            unsigned_result = {
                key: value
                for key, value in frt_result.items()
                if key != "result_digest"
            }
            if frt_result.get("result_digest") != canonical_digest(unsigned_result):
                failures.append("FRT gate result digest mismatch")
            if (
                frt_result.get("local_ready") is not True
                or frt_result.get("failures") != []
            ):
                failures.append("FRT repository gate is not locally ready")
            if (
                manifest.get("status") == "certified"
                or certification.get("status") == "certified"
            ):
                if frt_result.get("external_checks_complete") is not True:
                    failures.append(
                        "FRT certified status requires all signed external checks"
                    )
                if set(
                    frt_result.get("external_check_states", {})
                ) != FRT_EXTERNAL_CHECKS or any(
                    state != "PASSED"
                    for state in frt_result.get("external_check_states", {}).values()
                ):
                    failures.append(
                        "FRT certified status contains incomplete external states"
                    )
                if not frt_result.get("external_trust_store_sha256"):
                    failures.append(
                        "FRT certified status requires a bound external trust store"
                    )
                if frt_result.get("production_certification") != "CERTIFIED":
                    failures.append(
                        "FRT repository readiness cannot self-issue production certification"
                    )

    requested_certified = (
        manifest.get("status") == "certified"
        or certification.get("status") == "certified"
    )
    if requested_certified:
        if (
            manifest.get("status") != "certified"
            or certification.get("status") != "certified"
        ):
            failures.append("pack and certification statuses must both be certified")
        if not [
            cap
            for cap in support.get("capabilities", [])
            if cap.get("status") == "certified"
        ]:
            failures.append("no certified capabilities")

        metrics = evidence.get("metrics", {})
        thresholds = {
            "source_fingerprint_coverage": 0.95,
            "ui_ir_source_map_coverage": 0.95,
            "target_build_green_rate": 1.0,
            "target_startup_or_launch_rate": 1.0,
            "p0_journey_pass_rate": 1.0,
            "route_contract_pass_rate": 1.0,
            "state_contract_pass_rate": 1.0,
            "form_contract_pass_rate": 1.0,
            "identity_permission_pass_rate": 1.0,
            "visual_pass_rate": 1.0,
            "accessibility_pass_rate": 1.0,
            "i18n_pass_rate": 1.0,
            "browser_matrix_pass_rate": 1.0,
            "representative_workload_pass_rate": 1.0,
            "source_map_coverage": 0.95,
        }
        for key, threshold in thresholds.items():
            if metrics.get(key, 0) < threshold:
                failures.append(f"{key} below {threshold}")

        zero_fields = [
            "critical_unknowns",
            "silent_ui_drops",
            "critical_visual_regressions",
            "critical_accessibility_violations",
            "critical_security_regressions",
            "critical_interaction_regressions",
            "test_integrity_violations",
            "unapproved_baseline_changes",
            "unapproved_dependency_changes",
        ]
        for key in zero_fields:
            if evidence.get(key, 1) != 0:
                failures.append(f"{key} must be zero")

        if fingerprint.get("coverage", 0) < 0.95:
            failures.append("source fingerprint coverage below 0.95")
        if str(fingerprint.get("snapshot_digest", "")).upper() in {"", "UNSET"}:
            failures.append("source fingerprint snapshot digest unset")
        if not any(
            ui_ir.get(group)
            for group in ("routes", "views", "components", "states", "forms")
        ):
            failures.append("UI IR contains no evidence-bearing nodes")
        if not acceptance.get("p0_journeys"):
            failures.append("acceptance profile has no P0 journeys")
        route_matrix = load(pack / "route-matrix.json")
        if not route_matrix.get("tuples"):
            failures.append("route matrix has no exact tuples")
        if not has_real_file(pack / "corpus" / "holdout"):
            failures.append("holdout corpus empty")
        if not has_real_file(pack / "corpus" / "representative-workloads"):
            failures.append("representative workload corpus empty")
        if not has_real_file(pack / "visual-baselines" / "approved"):
            failures.append("approved visual baselines empty")

        references = evidence.get("evidence_refs", []) + certification.get(
            "evidence_refs", []
        )
        if not references:
            failures.append("certification evidence refs empty")
        for reference in references:
            if reference.startswith(("http://", "https://")):
                continue
            if not (pack / reference).is_file():
                failures.append(f"missing evidence ref: {reference}")

        if frontend_campaign is not None:
            if frontend_campaign_version == 2:
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
            else:
                if frontend_campaign.get("formal_ready") is not True:
                    failures.append("frontend formal campaign is not proof-ready")
                if frontend_campaign.get("certification_ready") is not True:
                    failures.append(
                        "frontend formal campaign is not certification-ready"
                    )
                if frontend_campaign.get("external_evidence_status") != "PASSED":
                    failures.append(
                        "frontend formal campaign external evidence is not PASSED"
                    )

    structural_status = "FAILED" if failures else "PASSED"
    certification_decision = (
        ("BLOCKED" if failures else "CERTIFIED")
        if requested_certified
        else "NOT_CERTIFIED"
    )
    local_equivalence_status = (
        frontend_campaign.get("local_equivalence_status", "INCOMPLETE")
        if frontend_campaign is not None
        else "NOT_EVALUATED"
    )
    formal_ready = (
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
        "status": "failed" if failures else "passed",
        "structural_status": structural_status,
        "local_equivalence_status": local_equivalence_status,
        "bounded_proof_profile_ready": bounded_proof_profile_ready,
        "formal_ready": formal_ready,
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
        "certification_decision": certification_decision,
        "pack_status": manifest.get("status"),
        "failures": failures,
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
    result_path = pack / "certification" / "gate-result.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n")

    report = [
        f"# Batch 32 gate: {manifest.get('pack_key')}",
        "",
        f"- Pack status: `{manifest.get('status')}`",
        f"- Structural status: `{structural_status}`",
        f"- Local equivalence status: `{local_equivalence_status}`",
        f"- Bounded proof profile ready: `{str(bounded_proof_profile_ready).lower()}`",
        f"- Formal ready: `{str(formal_ready).lower()}`",
        f"- External evidence status: `{external_evidence_status}`",
        f"- Model/formal ready: `{str(model_formal_ready).lower()}`",
        f"- Browser ready: `{str(browser_ready).lower()}`",
        f"- Native ready: `{str(native_ready).lower()}`",
        f"- Cross-channel runtime ready: `{str(runtime_ready).lower()}`",
        f"- Independent ready: `{str(independent_ready).lower()}`",
        f"- Certification decision: `{certification_decision}`",
        "",
    ]
    if failures:
        report.append("## Failures")
        report.extend(f"- {failure}" for failure in failures)
    else:
        report.append(
            "No structural gate failures were detected; the explicit "
            "certification decision above remains authoritative."
        )
    (pack / "certification" / "gate-report.md").write_text("\n".join(report) + "\n")

    if failures:
        print(
            "\n".join("GATE FAIL: " + failure for failure in failures), file=sys.stderr
        )
        return 2
    print(
        f"GATE PASS: {manifest.get('pack_key')} "
        f"status={manifest.get('status')} decision={certification_decision}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
