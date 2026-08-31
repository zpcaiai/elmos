#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

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

SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
PLACEHOLDER = re.compile(
    r"(?:^|[^A-Z0-9])(?:NOT_RUN|NOT_PROVIDED|NOT_EVALUATED|NOT_CERTIFIED|"
    r"UNASSIGNED|UNSET|TBD|TODO|PLACEHOLDER|INCONCLUSIVE)(?:$|[^A-Z0-9])"
)
VISUAL_ARTIFACT_SUFFIXES = {
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
}


def load(path: Path):
    return json.loads(path.read_text())


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        normalized = re.sub(r"[-\s]+", "_", value.upper())
        return PLACEHOLDER.search(normalized) is not None
    if isinstance(value, list):
        return any(contains_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(contains_placeholder(item) for item in value.values())
    return False


def iter_named_values(value: Any, names: set[str]):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in names:
                yield item
            yield from iter_named_values(item, names)
    elif isinstance(value, list):
        for item in value:
            yield from iter_named_values(item, names)


def iter_state_values(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if isinstance(item, str) and (
                normalized.endswith(("_state", "_status", "_result"))
                or normalized
                in {
                    "state",
                    "status",
                    "result",
                    "certification",
                    "external_evidence",
                }
            ):
                yield normalized, item
            yield from iter_state_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_state_values(item)


def is_non_local_pass(value: str) -> bool:
    normalized = value.strip().upper().replace("-", "_")
    if "LOCAL" in normalized or "SELF_ATTESTED" in normalized:
        return False
    return normalized in {
        "PASSED",
        "VERIFIED",
        "SUCCEEDED",
        "COMPLETED",
        "CERTIFIED",
        "PASSED_EXTERNAL",
        "PASSED_INDEPENDENT",
        "INDEPENDENTLY_VERIFIED",
    }


def has_non_local_pass(value: Any, *, external_only: bool = False) -> bool:
    for key, state in iter_state_values(value):
        if not is_non_local_pass(state):
            continue
        if not external_only or any(
            marker in key
            for marker in (
                "external",
                "independent",
                "verification",
                "customer",
                "production",
                "certification",
            )
        ):
            return True
    return False


def resolve_local_reference(
    pack: Path, reference: Any, *, relative_to: Path | None = None
) -> Path | None:
    if not isinstance(reference, str) or not reference.strip():
        return None
    if reference.startswith(("http://", "https://")):
        return None
    relative = Path(reference)
    if relative.is_absolute():
        return None
    pack_root = pack.resolve()
    candidates = [pack / relative]
    if relative_to is not None:
        candidates.insert(0, relative_to / relative)
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(pack_root)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def content_bound_artifact(
    pack: Path,
    document: Any,
    *,
    relative_to: Path | None = None,
    suffixes: set[str] | None = None,
) -> bool:
    digest_names = {
        "digest",
        "sha256",
        "dataset_digest",
        "artifact_digest",
        "evidence_digest",
        "result_digest",
    }
    digests = {
        item
        for item in iter_named_values(document, digest_names)
        if isinstance(item, str) and SHA256.fullmatch(item)
    }
    references: list[Any] = []
    for value in iter_named_values(document, {"evidence_refs"}):
        if isinstance(value, list):
            references.extend(value)

    def add_direct_pairs(value: Any) -> None:
        if isinstance(value, dict):
            digest = value.get("sha256", value.get("digest"))
            reference = value.get(
                "path",
                value.get("artifact_ref", value.get("evidence_ref", value.get("file"))),
            )
            if isinstance(digest, str) and SHA256.fullmatch(digest) and reference:
                references.append(reference)
            for item in value.values():
                add_direct_pairs(item)
        elif isinstance(value, list):
            for item in value:
                add_direct_pairs(item)

    add_direct_pairs(document)
    for reference in references:
        path = resolve_local_reference(pack, reference, relative_to=relative_to)
        if path is None or (suffixes is not None and path.suffix.lower() not in suffixes):
            continue
        if sha256_file(path) in digests:
            return True
    return False


def corpus_has_verified_evidence(pack: Path, relative: str, *, holdout: bool) -> bool:
    root = pack / relative
    if not root.is_dir():
        return False
    for path in sorted(root.rglob("*.json")):
        try:
            document = load(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        inventory = document.get("cases", document.get("workloads"))
        if not isinstance(inventory, list) or not inventory:
            continue
        if contains_placeholder(document) or not has_non_local_pass(document):
            continue
        independent = (
            document.get("independent_from_development") is True
            or document.get("transformation_authors_have_not_inspected_inputs") is True
            or document.get("independence") == "independently-verified"
        )
        if not independent:
            continue
        if holdout:
            executors = [
                item
                for item in iter_named_values(document, {"executor"})
                if isinstance(item, str) and not contains_placeholder(item)
            ]
            verifiers = [
                item
                for item in iter_named_values(
                    document, {"independent_verifier", "verifier"}
                )
                if isinstance(item, str) and not contains_placeholder(item)
            ]
            if (
                not executors
                or not verifiers
                or not set(executors).isdisjoint(verifiers)
            ):
                continue
        if content_bound_artifact(pack, document, relative_to=path.parent):
            return True
    return False


def visual_baselines_have_verified_evidence(pack: Path) -> bool:
    root = pack / "visual-baselines" / "approved"
    if not root.is_dir():
        return False
    for path in sorted(root.rglob("*.json")):
        try:
            document = load(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        if contains_placeholder(document) or not has_non_local_pass(document):
            continue
        if content_bound_artifact(
            pack,
            document,
            relative_to=path.parent,
            suffixes=VISUAL_ARTIFACT_SUFFIXES,
        ):
            return True
    return False


def pack_relative_path(pack: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    relative = Path(value)
    if relative.is_absolute():
        return None
    parts = relative.parts
    if pack.name in parts:
        relative = Path(*parts[parts.index(pack.name) + 1 :])
    try:
        resolved = (pack / relative).resolve(strict=True)
        resolved.relative_to(pack.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def validate_source_snapshot_binding(
    failures: list[str], pack: Path, fingerprint: dict[str, Any]
) -> None:
    manifest_path = pack / "source-snapshots" / "manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = load(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        failures.append(f"source snapshot manifest is invalid: {exc}")
        return
    if not isinstance(manifest, dict):
        failures.append("source snapshot manifest must be an object")
        return
    expected_digest = fingerprint.get("snapshot_digest")
    entries = manifest.get("files")
    source_root = pack_relative_path(pack, manifest.get("source_root"))
    if source_root is None or not source_root.is_dir():
        failures.append("source snapshot manifest source_root is missing or unsafe")
        return
    if not isinstance(entries, list) or not entries:
        failures.append("source snapshot manifest file inventory is empty")
        return
    normalized: list[tuple[str, str, int]] = []
    declared_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            failures.append("source snapshot manifest contains an invalid file entry")
            return
        relative = entry.get("path")
        claimed_digest = entry.get("sha256")
        claimed_bytes = entry.get("bytes")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in relative.split("/"))
            or not isinstance(claimed_bytes, int)
            or isinstance(claimed_bytes, bool)
            or claimed_bytes < 0
            or not isinstance(claimed_digest, str)
            or not SHA256.fullmatch(claimed_digest)
        ):
            failures.append("source snapshot manifest contains an unsafe file entry")
            return
        candidate = source_root / relative
        try:
            candidate.relative_to(source_root)
            path = candidate.resolve(strict=True)
            path.relative_to(source_root)
        except (OSError, ValueError):
            path = None
        if path is None or candidate.is_symlink() or not path.is_file():
            failures.append(f"source snapshot file is missing or unsafe: {relative}")
            return
        if path.stat().st_size != claimed_bytes or sha256_file(path) != claimed_digest:
            failures.append(f"source snapshot file digest or size drift: {relative}")
            return
        if relative in declared_paths:
            failures.append(f"source snapshot manifest contains duplicate path: {relative}")
            return
        declared_paths.add(relative)
        normalized.append((relative, claimed_digest, claimed_bytes))
    actual_paths = {
        item.relative_to(source_root).as_posix()
        for item in source_root.rglob("*")
        if item.is_file()
    }
    if actual_paths != declared_paths:
        failures.append("source snapshot manifest does not bind the exact file set")
    if manifest.get("file_count") != len(entries):
        failures.append("source snapshot manifest file_count mismatch")
    serialized = "\n".join(
        f"{relative}\0{digest}\0{size}"
        for relative, digest, size in sorted(normalized)
    ).encode("utf-8")
    actual_digest = "sha256:" + hashlib.sha256(serialized).hexdigest()
    if manifest.get("aggregate_digest") != actual_digest:
        failures.append("source snapshot manifest aggregate digest mismatch")
    if expected_digest != actual_digest:
        failures.append("source fingerprint snapshot digest is stale")


def validate_referenced_snapshot_bindings(
    failures: list[str],
    pack: Path,
    fingerprint: dict[str, Any],
    records: tuple[dict[str, Any], ...],
) -> None:
    expected_digest = fingerprint.get("snapshot_digest")
    references: set[str] = set()
    for record in records:
        values = record.get("evidence_refs", [])
        if isinstance(values, list):
            references.update(item for item in values if isinstance(item, str))
    source_manifest = pack / "source-snapshots" / "manifest.json"
    target_profile = pack / "target-profile" / "profile.json"
    pending = sorted(references)
    visited: set[str] = set()
    while pending:
        reference = pending.pop(0)
        if reference in visited:
            continue
        visited.add(reference)
        if len(visited) > 512:
            failures.append("referenced evidence graph exceeds 512 records")
            return
        path = resolve_local_reference(pack, reference)
        if path is None:
            if not reference.startswith(("http://", "https://")):
                failures.append(f"referenced evidence is missing or unsafe: {reference}")
            continue
        if path.suffix.lower() != ".json":
            continue
        try:
            record = load(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"referenced evidence is invalid JSON: {reference}: {exc}")
            continue
        if not isinstance(record, dict):
            failures.append(f"referenced evidence must be an object: {reference}")
            continue
        nested_references = list(iter_named_values(record, {"evidence_ref"}))
        for values in iter_named_values(record, {"evidence_refs"}):
            if isinstance(values, list):
                nested_references.extend(values)
        for nested in nested_references:
            if isinstance(nested, str) and nested not in visited:
                pending.append(nested)
        pack_key = record.get("pack_key")
        if pack_key is not None and pack_key != fingerprint.get("pack_key"):
            failures.append(f"referenced evidence pack_key mismatch: {reference}")
        bindings = {
            "source_snapshot_digest": record.get("source_snapshot_digest"),
            "source.manifest_aggregate_digest": (
                record.get("source", {}).get("manifest_aggregate_digest")
                if isinstance(record.get("source"), dict)
                else None
            ),
            "source.runtime_file_set_digest": (
                record.get("source", {}).get("runtime_file_set_digest")
                if isinstance(record.get("source"), dict)
                else None
            ),
            "request.source_revision": (
                record.get("request", {}).get("source_revision")
                if isinstance(record.get("request"), dict)
                else None
            ),
        }
        for label, supplied in bindings.items():
            if supplied is not None and supplied != expected_digest:
                failures.append(f"referenced evidence is stale at {reference}:{label}")
        source = record.get("source")
        if (
            isinstance(source, dict)
            and source.get("manifest_sha256") is not None
            and source_manifest.is_file()
            and source.get("manifest_sha256") != sha256_file(source_manifest)
        ):
            failures.append(f"referenced evidence source manifest digest mismatch: {reference}")
        request = record.get("request")
        if (
            isinstance(request, dict)
            and request.get("target_profile_digest") is not None
            and target_profile.is_file()
            and request.get("target_profile_digest") != sha256_file(target_profile)
        ):
            failures.append(f"referenced evidence target profile digest mismatch: {reference}")


def certification_evidence_is_real(
    pack: Path, reference: str, pack_key: Any
) -> bool:
    path = resolve_local_reference(pack, reference)
    if path is None or path.suffix.lower() != ".json":
        return False
    try:
        record = load(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(record, dict):
        return False
    if record.get("pack_key") not in {None, pack_key}:
        return False
    return (
        not contains_placeholder(record)
        and has_non_local_pass(record, external_only=True)
        and content_bound_artifact(pack, record, relative_to=path.parent)
    )


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

    validate_source_snapshot_binding(failures, pack, fingerprint)
    validate_referenced_snapshot_bindings(
        failures,
        pack,
        fingerprint,
        (fingerprint, evidence, certification),
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
        if not corpus_has_verified_evidence(
            pack, "corpus/holdout", holdout=True
        ):
            failures.append(
                "holdout corpus has no executed, independently verified, content-bound evidence"
            )
        if not corpus_has_verified_evidence(
            pack, "corpus/representative-workloads", holdout=False
        ):
            failures.append(
                "representative workload corpus has no executed, independent, content-bound evidence"
            )
        if not visual_baselines_have_verified_evidence(pack):
            failures.append(
                "approved visual baselines have no passed, content-bound visual artifact"
            )

        references: list[Any] = []
        for label, record in (
            ("evidence", evidence),
            ("certification", certification),
        ):
            values = record.get("evidence_refs", [])
            if not isinstance(values, list):
                failures.append(f"{label} evidence_refs must be a list")
            else:
                references.extend(values)
        for capability in support.get("capabilities", []):
            if capability.get("status") == "certified":
                values = capability.get("evidence_refs", [])
                if not isinstance(values, list):
                    failures.append(
                        f"certified capability evidence_refs must be a list: {capability.get('id')}"
                    )
                else:
                    references.extend(values)
        if not references:
            failures.append("certification evidence refs empty")
        real_certification_evidence = False
        for reference in references:
            if not isinstance(reference, str):
                failures.append("certification evidence ref is invalid")
                continue
            if resolve_local_reference(pack, reference) is None:
                failures.append(f"missing evidence ref: {reference}")
                continue
            if certification_evidence_is_real(
                pack, reference, manifest.get("pack_key")
            ):
                real_certification_evidence = True
        if not real_certification_evidence:
            failures.append(
                "certification evidence has no passed independent/external content-bound record"
            )

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
