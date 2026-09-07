#!/usr/bin/env python3
"""Authoritative fail-closed certification gate for Batch 38-45."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from _common import (
    ValidationError,
    load_json,
    parse_utc,
    require_digest,
    resolve_beneath,
    sha256_file,
    sha256_json,
    validate_evidence_manifest_shape,
    validate_result_shape,
)
from validate_coverage_matrix import validate_coverage
from validate_test_catalog import validate_catalog


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BATCHES = list(range(38, 46))


def add(blockers: list[str], message: str) -> None:
    if message not in blockers:
        blockers.append(message)


def verify_file_binding(
    base: Path,
    allowed_root: Path,
    record: dict[str, Any],
    blockers: list[str],
    label: str,
) -> Path | None:
    try:
        path = resolve_beneath(base, record.get("path", ""))
        path.relative_to(allowed_root)
        require_digest(record.get("sha256"), f"{label}.sha256")
        if path.stat().st_size != record.get("bytes"):
            add(blockers, f"{label}: byte count mismatch")
        if sha256_file(path) != record.get("sha256"):
            add(blockers, f"{label}: digest mismatch")
        return path
    except (ValidationError, ValueError, OSError) as exc:
        add(blockers, f"{label}: invalid file binding: {exc}")
        return None


def verify_control_manifest(
    root: Path,
    suite: dict[str, Any],
    schema_root: Path,
    blockers: list[str],
) -> dict[str, str]:
    paths = {
        "catalog": resolve_beneath(root, suite.get("case_catalog", "")),
        "coverage_matrix": resolve_beneath(root, suite.get("coverage_matrix", "")),
        "strict_profile": resolve_beneath(root, suite.get("profile", "")),
        "release_gate": resolve_beneath(root, suite.get("release_gate", "")),
        "suite": root / "suite.json",
    }
    controls = {name: sha256_file(path) for name, path in paths.items()}
    try:
        manifest = load_json(resolve_beneath(root, suite.get("case_manifest", "")))
    except Exception as exc:  # noqa: BLE001
        add(blockers, f"invalid control manifest: {exc}")
        return controls
    if manifest.get("manifest_version") != 2:
        add(blockers, "control manifest version must be 2")
    if manifest.get("suite_id") != "batch38-45-strict":
        add(blockers, "control manifest suite mismatch")
    if manifest.get("case_count") != 400:
        add(blockers, "control manifest case count mismatch")
    if manifest.get("control_digests") != controls:
        add(blockers, "control manifest digests are stale or tampered")
    schemas = {path.name: sha256_file(path) for path in sorted(schema_root.glob("*.json"))}
    if manifest.get("schema_digests") != schemas:
        add(blockers, "control manifest Schema digests are stale or tampered")
    return controls


def verify_raw_files(
    suite_root: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    case_id: str,
    blockers: list[str],
) -> dict[str, Path]:
    roles: dict[str, Path] = {}
    for index, record in enumerate(manifest.get("files", [])):
        if not isinstance(record, dict):
            continue
        path = verify_file_binding(
            manifest_path.parent,
            suite_root,
            record,
            blockers,
            f"{case_id}: files[{index}]",
        )
        role = record.get("role")
        if path is not None and isinstance(role, str):
            roles[role] = path
    return roles


def verify_evidence(
    suite_root: Path,
    case: dict[str, Any],
    result: dict[str, Any],
    catalog_digest: str,
    now: datetime,
    max_age_days: int,
    blockers: list[str],
) -> tuple[list[str], set[str]]:
    case_id = case["case_id"]
    manifest_digests: list[str] = []
    verifier_ids: set[str] = set()
    aggregate_roles: set[str] = set()
    aggregate_corpora: dict[str, str] = {}
    artifact_bound = False
    environment_bound = False
    for reference in result.get("evidence", []):
        try:
            manifest_path = resolve_beneath(suite_root, reference)
            manifest = load_json(manifest_path)
        except Exception as exc:  # noqa: BLE001
            add(blockers, f"{case_id}: invalid evidence reference {reference}: {exc}")
            continue
        manifest_digests.append(sha256_file(manifest_path))
        for error in validate_evidence_manifest_shape(manifest):
            add(blockers, f"{case_id}: {error}")
        if manifest.get("case_id") != case_id:
            add(blockers, f"{case_id}: evidence case mismatch")
        if manifest.get("case_digest") != sha256_json(case):
            add(blockers, f"{case_id}: evidence case digest mismatch")
        if manifest.get("catalog_digest") != catalog_digest:
            add(blockers, f"{case_id}: evidence catalog digest mismatch")
        if manifest.get("artifact_digest") != result.get("artifact_digest"):
            add(blockers, f"{case_id}: evidence artifact digest mismatch")
        if manifest.get("environment_digest") != result.get("environment_digest"):
            add(blockers, f"{case_id}: evidence environment digest mismatch")
        if manifest.get("execution_kind") != result.get("execution_kind"):
            add(blockers, f"{case_id}: evidence execution kind mismatch")
        if manifest.get("started_at") != result.get("started_at") or manifest.get("finished_at") != result.get("finished_at"):
            add(blockers, f"{case_id}: evidence timestamps differ from result")
        if manifest.get("replay_command") != result.get("replay_command"):
            add(blockers, f"{case_id}: evidence replay command mismatch")
        if set(manifest.get("authorization_refs", [])) != set(result.get("authorization_refs", [])):
            add(blockers, f"{case_id}: authorization references mismatch")
        try:
            finished = parse_utc(manifest.get("finished_at"))
            if finished > now + timedelta(minutes=5):
                add(blockers, f"{case_id}: evidence timestamp is in the future")
            if now - finished > timedelta(days=max_age_days):
                add(blockers, f"{case_id}: stale evidence")
        except ValidationError:
            pass
        executor = manifest.get("executor", {})
        verifier = manifest.get("verifier", {})
        verifier_id = verifier.get("id") if isinstance(verifier, dict) else None
        executor_id = executor.get("id") if isinstance(executor, dict) else None
        if isinstance(verifier_id, str):
            verifier_ids.add(verifier_id)
        roles = verify_raw_files(suite_root, manifest_path, manifest, case_id, blockers)
        aggregate_roles.update(roles)
        artifact = roles.get("artifact-binding")
        environment = roles.get("environment-binding")
        if artifact is not None:
            artifact_bound = sha256_file(artifact) == result.get("artifact_digest")
            if not artifact_bound:
                add(blockers, f"{case_id}: artifact digest is not bound to artifact file")
        if environment is not None:
            environment_bound = sha256_file(environment) == result.get("environment_digest")
            if not environment_bound:
                add(blockers, f"{case_id}: environment digest is not bound to environment file")
        for role, expected in (("execution-result", "passed"), ("verification", "accepted")):
            path = roles.get(role)
            if path is None:
                continue
            try:
                document = load_json(path)
                if document.get("case_id") != case_id or document.get("status") != expected:
                    add(blockers, f"{case_id}: {role} content mismatch")
                if role == "execution-result":
                    if document.get("artifact_digest") != result.get("artifact_digest") or document.get("environment_digest") != result.get("environment_digest"):
                        add(blockers, f"{case_id}: execution result scope mismatch")
                if role == "verification" and document.get("verifier_id") != verifier_id:
                    add(blockers, f"{case_id}: verification identity mismatch")
            except Exception as exc:  # noqa: BLE001
                add(blockers, f"{case_id}: invalid {role} document: {exc}")
        for corpus in manifest.get("corpora", []):
            if not isinstance(corpus, dict):
                continue
            kind = corpus.get("kind")
            try:
                corpus_path = resolve_beneath(manifest_path.parent, corpus.get("manifest_path", ""))
                corpus_path.relative_to(suite_root)
                digest = sha256_file(corpus_path)
                if digest != corpus.get("digest"):
                    add(blockers, f"{case_id}: {kind} corpus digest mismatch")
                aggregate_corpora[str(kind)] = digest
            except (ValidationError, ValueError) as exc:
                add(blockers, f"{case_id}: invalid {kind} corpus binding: {exc}")
            if corpus.get("verifier_id") != verifier_id:
                add(blockers, f"{case_id}: {kind} corpus verifier mismatch")
            try:
                attestation_path = resolve_beneath(manifest_path.parent, corpus.get("attestation_ref", ""))
                attestation_path.relative_to(suite_root)
                if attestation_path not in roles.values():
                    add(blockers, f"{case_id}: {kind} corpus attestation is not raw evidence")
            except (ValidationError, ValueError) as exc:
                add(blockers, f"{case_id}: invalid {kind} corpus attestation: {exc}")
            if kind in {"holdout", "representative"} and corpus.get("authoring_access") is not False:
                add(blockers, f"{case_id}: {kind} corpus authoring access is not denied")
        if executor_id == verifier_id:
            add(blockers, f"{case_id}: executor cannot self-verify")
    missing_roles = sorted(set(case.get("evidence_required", [])) - aggregate_roles)
    if missing_roles:
        add(blockers, f"{case_id}: missing required evidence roles {missing_roles}")
    if not artifact_bound:
        add(blockers, f"{case_id}: no valid artifact binding")
    if not environment_bound:
        add(blockers, f"{case_id}: no valid environment binding")
    if set(aggregate_corpora) != {"development", "holdout", "representative"}:
        add(blockers, f"{case_id}: development, holdout and representative corpora are required")
    if len(set(aggregate_corpora.values())) != len(aggregate_corpora):
        add(blockers, f"{case_id}: corpora are not independent")
    return sorted(manifest_digests), verifier_ids


def verify_external_evidence(
    suite_root: Path,
    release: dict[str, Any],
    profile: dict[str, Any],
    now: datetime,
    blockers: list[str],
) -> tuple[list[dict[str, str]], set[str]]:
    bindings: list[dict[str, str]] = []
    verifier_ids: set[str] = set()
    if release.get("release_gate_version") != 2 or release.get("suite_id") != "batch38-45-strict":
        add(blockers, "release evidence control is malformed")
    if release.get("required_domain_gates") != EXPECTED_BATCHES:
        add(blockers, "release evidence must require domain gates 38 through 45")
    if release.get("zero_tolerance_findings"):
        add(blockers, "release evidence contains zero-tolerance findings")

    organizations: set[str] = set()
    for index, record in enumerate(release.get("design_partner_evidence", [])):
        if not isinstance(record, dict):
            add(blockers, f"design partner {index} is malformed")
            continue
        path = verify_file_binding(suite_root, suite_root, record, blockers, f"design partner {index}")
        organization = record.get("organization_id")
        verifier = record.get("verifier_id")
        if record.get("accepted") is not True or record.get("independent") is not True or not organization or not verifier:
            add(blockers, f"design partner {index} lacks independent acceptance")
        try:
            accepted = parse_utc(record.get("accepted_at"))
            if accepted > now + timedelta(minutes=5):
                add(blockers, f"design partner {index} timestamp is in the future")
        except ValidationError as exc:
            add(blockers, f"design partner {index}: {exc}")
        if path is not None:
            try:
                raw = load_json(path)
                for key in ("evidence_id", "organization_id", "accepted", "independent", "verifier_id"):
                    if raw.get(key) != record.get(key):
                        add(blockers, f"design partner {index}: raw {key} mismatch")
                if raw.get("scope") != "batch38-45-strict":
                    add(blockers, f"design partner {index}: raw scope mismatch")
            except Exception as exc:  # noqa: BLE001
                add(blockers, f"design partner {index}: invalid raw evidence: {exc}")
        if isinstance(organization, str):
            organizations.add(organization)
        if isinstance(verifier, str):
            verifier_ids.add(verifier)
        if path is not None:
            bindings.append({"kind": "design-partner", "id": str(record.get("evidence_id")), "digest": sha256_file(path)})
    required_orgs = profile["thresholds"]["required_design_partner_organizations"]
    if len(organizations) < required_orgs:
        add(blockers, f"design partner organizations {len(organizations)} below {required_orgs}")

    reviews = 0
    for index, record in enumerate(release.get("independent_review_evidence", [])):
        if not isinstance(record, dict):
            add(blockers, f"independent review {index} is malformed")
            continue
        path = verify_file_binding(suite_root, suite_root, record, blockers, f"independent review {index}")
        verifier = record.get("verifier_id")
        if record.get("accepted") is not True or record.get("independent") is not True or not verifier:
            add(blockers, f"independent review {index} lacks independent acceptance")
        if path is not None:
            try:
                raw = load_json(path)
                for key in ("evidence_id", "accepted", "independent", "verifier_id"):
                    if raw.get(key) != record.get(key):
                        add(blockers, f"independent review {index}: raw {key} mismatch")
                if raw.get("scope") != "batch38-45-strict":
                    add(blockers, f"independent review {index}: raw scope mismatch")
            except Exception as exc:  # noqa: BLE001
                add(blockers, f"independent review {index}: invalid raw evidence: {exc}")
            bindings.append({"kind": "independent-review", "id": str(record.get("evidence_id")), "digest": sha256_file(path)})
        reviews += 1
        if isinstance(verifier, str):
            verifier_ids.add(verifier)
    required_reviews = profile["thresholds"]["required_independent_reviews"]
    if reviews < required_reviews:
        add(blockers, f"independent reviews {reviews} below {required_reviews}")

    seen_batches: set[int] = set()
    for index, record in enumerate(release.get("domain_gate_evidence", [])):
        if not isinstance(record, dict):
            add(blockers, f"domain gate {index} is malformed")
            continue
        batch = record.get("batch")
        path = verify_file_binding(suite_root, suite_root, record, blockers, f"domain gate {batch}")
        if batch in seen_batches:
            add(blockers, f"duplicate domain gate Batch {batch}")
        if isinstance(batch, int):
            seen_batches.add(batch)
        if path is not None:
            try:
                gate = load_json(path)
                if gate.get("batch") != batch or gate.get("status") != "CERTIFIED" or gate.get("eligible") is not True:
                    add(blockers, f"domain gate Batch {batch} is not eligible and CERTIFIED")
            except Exception as exc:  # noqa: BLE001
                add(blockers, f"domain gate Batch {batch}: invalid raw gate: {exc}")
            bindings.append({"kind": "domain-gate", "id": str(batch), "digest": sha256_file(path)})
        verifier = record.get("verifier_id")
        if isinstance(verifier, str):
            verifier_ids.add(verifier)
    if seen_batches != set(EXPECTED_BATCHES):
        add(blockers, "all exact M38-M45 domain gates are required")
    return sorted(bindings, key=lambda item: (item["kind"], item["id"])), verifier_ids


def verify_certification_request(
    suite_root: Path,
    request_path: Path,
    signature_path: Path,
    trust_store_path: Path,
    controls: dict[str, str],
    release_gate_digest: str,
    expected_bindings: list[dict[str, Any]],
    external_bindings: list[dict[str, str]],
    verifier_ids: set[str],
    now: datetime,
    blockers: list[str],
) -> bool:
    try:
        request_path.relative_to(suite_root)
        signature_path.relative_to(suite_root)
        try:
            trust_store_path.relative_to(suite_root)
            add(blockers, "trust store must be external to the evidence suite")
        except ValueError:
            pass
        request = load_json(request_path)
        trust_store = load_json(trust_store_path)
    except Exception as exc:  # noqa: BLE001
        add(blockers, f"invalid certification inputs: {exc}")
        return False
    required = {"request_version", "suite_id", "requested_at", "expires_at", "signer_id", "authorization_refs", "control_digests", "release_gate_digest", "case_bindings", "external_bindings"}
    if not isinstance(request, dict) or required - set(request):
        add(blockers, "certification request is malformed")
        return False
    if request.get("request_version") != 1 or request.get("suite_id") != "batch38-45-strict":
        add(blockers, "certification request version or suite mismatch")
    if request.get("control_digests") != controls:
        add(blockers, "certification request control digests mismatch")
    if request.get("release_gate_digest") != release_gate_digest:
        add(blockers, "certification request release gate digest mismatch")
    if request.get("case_bindings") != expected_bindings:
        add(blockers, "certification request does not bind the exact 400 result/evidence sets")
    if request.get("external_bindings") != external_bindings:
        add(blockers, "certification request external evidence bindings mismatch")
    signer_id = request.get("signer_id")
    if verifier_ids != {signer_id}:
        add(blockers, "certification signer must independently verify every passed case")
    if not isinstance(request.get("authorization_refs"), list) or not request["authorization_refs"]:
        add(blockers, "certification request authorization is missing")
    try:
        requested = parse_utc(request.get("requested_at"))
        expires = parse_utc(request.get("expires_at"))
        if requested > now + timedelta(minutes=5) or expires <= requested or expires - requested > timedelta(days=7) or now > expires:
            add(blockers, "certification request is future, expired or overlong")
    except ValidationError as exc:
        add(blockers, f"invalid certification request timestamp: {exc}")
    authorities = trust_store.get("authorities", []) if isinstance(trust_store, dict) else []
    anchors = [entry for entry in authorities if isinstance(entry, dict) and entry.get("signer_id") == signer_id]
    if len(anchors) != 1:
        add(blockers, "exactly one trust anchor is required for the signer")
        return False
    anchor = anchors[0]
    if anchor.get("revoked") is not False or anchor.get("algorithm") != "rsa-sha256":
        add(blockers, "trust anchor is revoked or uses an unsupported algorithm")
    if "independent-certifier" not in anchor.get("roles", []) or "batch38-45-strict" not in anchor.get("suites", []) or anchor.get("batches") != EXPECTED_BATCHES:
        add(blockers, "trust anchor lacks exact suite and Batch authority")
    try:
        valid_from = parse_utc(anchor.get("valid_from"))
        valid_until = parse_utc(anchor.get("valid_until"))
        if not valid_from <= now <= valid_until:
            add(blockers, "trust anchor is outside its validity interval")
        public_key = resolve_beneath(trust_store_path.parent, anchor.get("public_key", ""))
        if sha256_file(public_key) != anchor.get("public_key_sha256"):
            add(blockers, "trust-anchor public key digest mismatch")
            return False
    except Exception as exc:  # noqa: BLE001
        add(blockers, f"invalid trust anchor: {exc}")
        return False
    completed = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(public_key), "-signature", str(signature_path), str(request_path)], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        add(blockers, "certification request signature verification failed")
        return False
    return not blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", default="test-suites/batch38-45-strict")
    parser.add_argument("--schema-root", default=str(REPOSITORY_ROOT / "schemas/test-suite-b38-45"))
    parser.add_argument("--skill-root", default=str(REPOSITORY_ROOT / ".agents/skills"))
    parser.add_argument("--certification-request")
    parser.add_argument("--signature")
    parser.add_argument("--trust-store")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.suite).resolve()
    schema_root = Path(args.schema_root).resolve()
    now = datetime.now(timezone.utc)
    blockers: list[str] = []
    try:
        suite = load_json(root / "suite.json")
        catalog_path = resolve_beneath(root, suite.get("case_catalog", ""))
        coverage_path = resolve_beneath(root, suite.get("coverage_matrix", ""))
        profile_path = resolve_beneath(root, suite.get("profile", ""))
        release_path = resolve_beneath(root, suite.get("release_gate", ""))
        catalog = load_json(catalog_path)
        profile = load_json(profile_path)
        release = load_json(release_path)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: cannot load suite controls: {exc}", file=sys.stderr)
        return 2
    for error in validate_catalog(catalog_path, Path(args.skill_root)):
        add(blockers, f"catalog: {error}")
    for error in validate_coverage(coverage_path, catalog_path):
        add(blockers, f"coverage: {error}")
    try:
        controls = verify_control_manifest(root, suite, schema_root, blockers)
    except Exception as exc:  # noqa: BLE001
        add(blockers, f"control verification failed: {exc}")
        controls = {}

    thresholds = profile.get("thresholds", {})
    max_age_days = int(thresholds.get("max_evidence_age_days", 0) or 0)
    zero_tolerance = profile.get("zero_tolerance", [])
    counts = {key: 0 for key in ("passed", "failed", "blocked", "not-run", "waived", "missing", "invalid")}
    priority_totals = Counter(case.get("priority") for case in catalog.get("cases", []))
    priority_passed: Counter[str] = Counter()
    counter_totals = {key: 0 for key in zero_tolerance}
    expected_bindings: list[dict[str, Any]] = []
    verifier_ids: set[str] = set()
    catalog_digest = sha256_file(catalog_path)

    for case in catalog.get("cases", []):
        case_id = case.get("case_id", "<unknown>")
        result_path = root / "results" / f"{case_id}.json"
        if not result_path.is_file():
            counts["missing"] += 1
            add(blockers, f"missing result {case_id}")
            continue
        try:
            result = load_json(result_path)
        except Exception as exc:  # noqa: BLE001
            counts["invalid"] += 1
            add(blockers, f"invalid result {case_id}: {exc}")
            continue
        errors = validate_result_shape(result)
        if errors:
            counts["invalid"] += 1
            for error in errors:
                add(blockers, f"{case_id}: {error}")
        status = result.get("status")
        if status in counts:
            counts[status] += 1
        if result.get("case_id") != case_id:
            add(blockers, f"{case_id}: result case mismatch")
        if case.get("priority") in {"P0", "P1"} and status != "passed":
            add(blockers, f"{case.get('priority')} {case_id} is {status}")
        counters = result.get("counters", {})
        for key in zero_tolerance:
            value = counters.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                add(blockers, f"{case_id}: counter {key} must be non-negative")
            else:
                counter_totals[key] += value
        evidence_digests: list[str] = []
        if status == "passed":
            priority_passed[case["priority"]] += 1
            if case.get("required_real_system") and result.get("execution_kind") != "real":
                add(blockers, f"{case_id}: real execution is required")
            if result.get("trace_coverage", 0) < thresholds.get("evidence_trace_coverage", 1):
                add(blockers, f"{case_id}: evidence trace coverage below threshold")
            if case.get("category") == "performance":
                metrics = result.get("metrics", {})
                for key, threshold_key in (("p95_latency_regression", "p95_latency_regression_max"), ("p99_latency_regression", "p99_latency_regression_max"), ("unit_cost_regression", "unit_cost_regression_max")):
                    value = metrics.get(key) if isinstance(metrics, dict) else None
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        add(blockers, f"{case_id}: performance metric {key} is required")
                    elif value > thresholds.get(threshold_key, 0):
                        add(blockers, f"{case_id}: {key} exceeds threshold")
            evidence_digests, case_verifiers = verify_evidence(root, case, result, catalog_digest, now, max_age_days, blockers)
            verifier_ids.update(case_verifiers)
        expected_bindings.append({"case_id": case_id, "result_digest": sha256_file(result_path), "evidence_manifest_digests": evidence_digests})

    for key, value in counter_totals.items():
        if value:
            add(blockers, f"zero-tolerance counter {key} is {value}")
    rates = {priority: priority_passed[priority] / priority_totals[priority] if priority_totals[priority] else 0 for priority in ("P0", "P1", "P2")}
    for priority, threshold_key in (("P0", "p0_pass_rate"), ("P1", "p1_pass_rate"), ("P2", "p2_pass_rate")):
        if rates[priority] < thresholds.get(threshold_key, 1):
            add(blockers, f"{priority} pass rate {rates[priority]:.6f} below threshold")
    if counts["not-run"] or counts["blocked"] or counts["missing"] or counts["invalid"] or counts["waived"]:
        add(blockers, "every case requires an executed terminal result before certification")

    external_bindings, _external_verifiers = verify_external_evidence(root, release, profile, now, blockers)
    request_args = [args.certification_request, args.signature, args.trust_store]
    certification_requested = any(request_args)
    valid_request = False
    if certification_requested and not all(request_args):
        add(blockers, "certification requires request, signature and external trust store together")
    elif certification_requested:
        valid_request = verify_certification_request(
            root,
            Path(args.certification_request).resolve(),
            Path(args.signature).resolve(),
            Path(args.trust_store).resolve(),
            controls,
            sha256_file(release_path),
            expected_bindings,
            external_bindings,
            verifier_ids,
            now,
            blockers,
        )
    elif counts["passed"]:
        add(blockers, "passed results lack an externally trusted signed certification request")

    decision = "CERTIFIED" if not blockers and valid_request else "BLOCKED"
    all_not_run = counts["not-run"] == 400 and not any(counts[key] for key in ("passed", "failed", "blocked", "waived", "missing", "invalid"))
    field_status = "PASSED" if decision == "CERTIFIED" else ("NOT_RUN" if all_not_run else "FAILED")
    status = "passed" if decision == "CERTIFIED" else ("blocked" if all_not_run else "failed")
    gate = {
        "gate_id": "batch38-45-strict",
        "gate_version": 2,
        "status": status,
        "decision": decision,
        "field_evidence_status": field_status,
        "certification_requested": certification_requested,
        "evaluated_at": now.isoformat().replace("+00:00", "Z"),
        "control_digests": controls,
        "metrics": {"counts": counts, "priority_totals": dict(priority_totals), "priority_passed": dict(priority_passed), "pass_rates": rates, "zero_tolerance_totals": counter_totals, "external_bindings": len(external_bindings)},
        "blockers": blockers,
        "gate_code_digest": sha256_file(Path(__file__)),
        "evidence_digest": sha256_json({"controls": controls, "bindings": expected_bindings, "external_bindings": external_bindings, "counts": counts, "blockers": blockers}),
    }
    output = Path(args.output).resolve() if args.output else root / "strict-gate-result.json"
    output.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0 if decision == "CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
