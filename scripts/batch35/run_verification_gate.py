#!/usr/bin/env python3
"""Run the conservative Batch 35 gate and expose certification blockers.

Structural success is intentionally separate from certification readiness.  A
research, experimental, or limited pack may be valid while still having
external obligations.  Those obligations must remain machine-readable even
when certification has not yet been requested.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from _common import (
    evaluated_pack_digest as compose_evaluated_pack_digest,
)
from _common import (
    load,
    local_ref_path,
    pack_content_digest,
    repository_binding_records,
    repository_files_digest,
    resolve_ref,
)

TECHNIQUE_THRESHOLDS = {
    "property": ("property_pass_rate", 1.0),
    "property-based-testing": ("property_pass_rate", 1.0),
    "metamorphic": ("metamorphic_pass_rate", 1.0),
    "metamorphic-testing": ("metamorphic_pass_rate", 1.0),
    "mutation": ("mutation_score", 0.80),
    "mutation-testing": ("mutation_score", 0.80),
    "fuzz": ("fuzz_campaign_pass_rate", 1.0),
    "structured-fuzz": ("fuzz_campaign_pass_rate", 1.0),
    "structured-fuzzing": ("fuzz_campaign_pass_rate", 1.0),
    "model": ("model_transition_coverage", 0.95),
    "model-based-testing": ("model_transition_coverage", 0.95),
    "contract": ("p0_contract_pass_rate", 1.0),
    "api-schema-contract-verification": ("p0_contract_pass_rate", 1.0),
    "data-money": ("data_money_invariant_pass_rate", 1.0),
    "data-money-invariants": ("data_money_invariant_pass_rate", 1.0),
    "security": ("security_property_pass_rate", 1.0),
    "security-properties": ("security_property_pass_rate", 1.0),
    "query": ("query_equivalence_pass_rate", 1.0),
    "query-equivalence": ("query_equivalence_pass_rate", 1.0),
    "numeric": ("numeric_verification_pass_rate", 1.0),
    "numeric-verification": ("numeric_verification_pass_rate", 1.0),
    "counterexample-replay": ("counterexample_replay_pass_rate", 1.0),
    "assurance-case": ("assurance_claim_support_rate", 1.0),
}

ALWAYS_REQUIRED_THRESHOLDS = {
    "representative_workload_pass_rate": 1.0,
    "source_map_coverage": 0.95,
    "evidence_trace_coverage": 0.95,
}

ALWAYS_ZERO_TOLERANCE_FIELDS = (
    "critical_unknown_obligations",
    "unresolved_oracle_conflicts",
    "unsupported_p0_claims",
    "test_integrity_violations",
    "unapproved_oracle_changes",
    "unapproved_tolerance_changes",
)

TECHNIQUE_ZERO_TOLERANCE_FIELDS = {
    "mutation": ("surviving_critical_mutants",),
    "mutation-testing": ("surviving_critical_mutants",),
    "fuzz": ("critical_fuzz_crashes",),
    "structured-fuzz": ("critical_fuzz_crashes",),
    "structured-fuzzing": ("critical_fuzz_crashes",),
    "counterexample-replay": ("unreplayed_counterexamples",),
    "security": ("security_property_violations",),
    "security-properties": ("security_property_violations",),
    "data-money": ("money_invariant_violations",),
    "data-money-invariants": ("money_invariant_violations",),
    "concurrency": (
        "forbidden_concurrency_outcomes",
        "race_deadlock_liveness_violations",
    ),
    "schedule-exploration": (
        "forbidden_concurrency_outcomes",
        "race_deadlock_liveness_violations",
    ),
    "query": ("query_equivalence_failures",),
    "query-equivalence": ("query_equivalence_failures",),
    "numeric": ("numeric_precision_regressions",),
    "numeric-verification": ("numeric_precision_regressions",),
    "solver": ("invalid_or_unknown_required_proofs",),
    "symbolic": ("invalid_or_unknown_required_proofs",),
    "bounded-proof": ("invalid_or_unknown_required_proofs",),
    "bounded-finite-domain-proof": ("invalid_or_unknown_required_proofs",),
}

SOLVER_TECHNIQUES = {
    "solver",
    "symbolic",
    "bounded-proof",
    "bounded-finite-domain-proof",
}
GOVERNED_TECHNIQUES = (
    set(TECHNIQUE_THRESHOLDS)
    | set(TECHNIQUE_ZERO_TOLERANCE_FIELDS)
    | {
        "assurance-case",
        "browser-journey",
        "holdout",
        "missing-context",
        "negative-authentication",
        "negative-cross-tenant",
        "negative-traces",
        "oracle-governance",
        "restart-recovery",
        "scope-authorization",
        "write-isolation",
    }
)
MAXIMUM_LOCAL_DECISION = "READY_FOR_EXTERNAL_GATE"


def write_gate_output(pack: Path, name: str, content: str) -> None:
    """Atomically write one fixed gate output without following pack symlinks."""

    if name not in {"gate-result.json", "gate-report.md"}:
        raise ValueError("unsupported gate output")
    root = pack.resolve(strict=True)
    certification = root / "certification"
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(certification, directory_flags)
    temporary_name = f".{name}.{secrets.token_hex(16)}.tmp"
    temporary_fd: int | None = None
    try:
        directory_stat = os.fstat(directory_fd)
        if not stat.S_ISDIR(directory_stat.st_mode):
            raise OSError("certification output parent is not a directory")
        try:
            target_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            target_stat = None
        if target_stat is not None and not stat.S_ISREG(target_stat.st_mode):
            raise OSError(f"unsafe gate output target: certification/{name}")

        create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        create_flags |= getattr(os, "O_NOFOLLOW", 0)
        temporary_fd = os.open(
            temporary_name,
            create_flags,
            0o600,
            dir_fd=directory_fd,
        )
        payload = content.encode("utf-8")
        written = 0
        while written < len(payload):
            count = os.write(temporary_fd, payload[written:])
            if count <= 0:
                raise OSError("short write while persisting gate output")
            written += count
        os.fchmod(temporary_fd, 0o644)
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = None
        os.replace(
            temporary_name,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def append_once(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def load_required_local(pack: Path, relative: str) -> dict[str, Any]:
    path = local_ref_path(pack, relative)
    if path is None:
        raise ValueError(f"required pack file is missing or unsafe: {relative}")
    document = load(path)
    if not isinstance(document, dict):
        raise TypeError(f"required pack file is not an object: {relative}")
    return document


def validate_certification_corpus(
    pack: Path,
    corpus_key: str,
    expected_source_digest: str | None,
    blockers: list[str],
) -> dict[str, Any]:
    relative_manifest = f"corpus/{corpus_key}/manifest.json"
    path = local_ref_path(pack, relative_manifest)
    if path is None:
        append_once(blockers, f"{corpus_key} corpus manifest missing")
        return {}
    try:
        manifest = load(path)
    except (OSError, ValueError) as exc:
        append_once(blockers, f"{corpus_key} corpus manifest invalid: {exc}")
        return {}
    if manifest.get("status") != "passed":
        append_once(blockers, f"{corpus_key} corpus status must be passed")
    digest_pattern = re.compile(r"^sha256:[0-9a-f]{64}$")
    source_digest = manifest.get("source_digest")
    dataset_digest = manifest.get("dataset_digest")
    if not isinstance(source_digest, str) or not digest_pattern.fullmatch(
        source_digest
    ):
        append_once(blockers, f"{corpus_key} corpus source_digest is not exact SHA-256")
    elif source_digest != expected_source_digest:
        append_once(
            blockers, f"{corpus_key} corpus source_digest does not match pack scope"
        )
    if not isinstance(dataset_digest, str) or not digest_pattern.fullmatch(
        dataset_digest
    ):
        append_once(
            blockers, f"{corpus_key} corpus dataset_digest is not exact SHA-256"
        )
    refs = manifest.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        append_once(blockers, f"{corpus_key} corpus evidence_refs empty")
    else:
        dataset_digest_matched = False
        data_prefix = f"corpus/{corpus_key}/"
        for ref in refs:
            if not resolve_ref(pack, ref):
                append_once(
                    blockers, f"{corpus_key} corpus missing evidence ref: {ref}"
                )
                continue
            if not isinstance(ref, str) or not ref.startswith(data_prefix):
                continue
            if ref == relative_manifest or ref.startswith(("http://", "https://")):
                continue
            data_path = local_ref_path(pack, ref)
            if data_path is None:
                continue
            actual_digest = (
                "sha256:" + hashlib.sha256(data_path.read_bytes()).hexdigest()
            )
            if actual_digest == dataset_digest:
                dataset_digest_matched = True
        if not dataset_digest_matched:
            append_once(
                blockers,
                f"{corpus_key} corpus dataset_digest does not match a content-bound corpus data ref",
            )
    return manifest


def representative_authorization_is_valid(
    pack: Path,
    authorization_ref: Any,
    pack_manifest: dict[str, Any],
    corpus_manifest: dict[str, Any],
) -> bool:
    if not isinstance(authorization_ref, str) or authorization_ref.startswith(
        ("http://", "https://")
    ):
        return False
    path = local_ref_path(pack, authorization_ref)
    if path is None:
        return False
    try:
        record = load(path)
    except (OSError, ValueError):
        return False
    if not isinstance(record, dict):
        return False
    required_strings = ("authorization_id", "authorized_by", "approved_at")
    if any(
        not isinstance(record.get(field), str) or not record[field].strip()
        for field in required_strings
    ):
        return False
    scope = pack_manifest.get("scope", {})
    return (
        record.get("schema_version") == 1
        and record.get("status") == "approved"
        and record.get("pack_key") == pack_manifest.get("pack_key")
        and record.get("source_digest") == scope.get("source_artifact_digest")
        and record.get("dataset_digest") == corpus_manifest.get("dataset_digest")
        and record.get("workload_key") == scope.get("workload_key")
    )


def certification_blockers(
    pack: Path,
    manifest: dict[str, Any],
    profile: dict[str, Any],
    oracles: dict[str, Any],
    proof: dict[str, Any],
    assurance: dict[str, Any],
    evidence: dict[str, Any],
    certification: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if (
        manifest.get("status") != "certified"
        or certification.get("status") != "certified"
    ):
        append_once(
            blockers, "pack and certification status must both request certified"
        )

    techniques = set(profile.get("techniques", []))
    for claim in profile.get("claims", []):
        techniques.update(claim.get("required_techniques", []))
    for technique in sorted(techniques - GOVERNED_TECHNIQUES):
        append_once(blockers, f"unknown required verification technique: {technique}")
    fuzz_path = local_ref_path(pack, "fuzz/campaign.json")
    if fuzz_path is None:
        append_once(blockers, "fuzz campaign is missing or unsafe")
    else:
        try:
            fuzz_campaign = load(fuzz_path)
        except (OSError, ValueError) as exc:
            append_once(blockers, f"fuzz campaign is invalid: {exc}")
            fuzz_campaign = {}
        for field in ("seed_corpus", "dictionary_refs"):
            values = fuzz_campaign.get(field, [])
            if not isinstance(values, list):
                append_once(blockers, f"fuzz {field} must be an array")
                continue
            for ref in values:
                if (
                    not isinstance(ref, str)
                    or ref.startswith(("http://", "https://"))
                    or local_ref_path(pack, ref) is None
                ):
                    append_once(
                        blockers,
                        f"fuzz {field} ref must be a safe pack-local file: {ref!r}",
                    )
    thresholds = dict(ALWAYS_REQUIRED_THRESHOLDS)
    for technique in techniques:
        threshold = TECHNIQUE_THRESHOLDS.get(technique)
        if threshold:
            thresholds[threshold[0]] = threshold[1]
    metrics: dict[str, Any] = {}
    metrics.update(evidence.get("metrics", {}))
    metrics.update(certification.get("metrics", {}))
    for key, threshold in thresholds.items():
        raw_value = metrics.get(key, 0)
        if (
            isinstance(raw_value, bool)
            or not isinstance(raw_value, (int, float))
            or not math.isfinite(float(raw_value))
            or not 0 <= float(raw_value) <= 1
        ):
            append_once(blockers, f"{key} must be a finite number between 0 and 1")
            continue
        value = float(raw_value)
        if value < threshold:
            append_once(blockers, f"{key} below {threshold}")

    zero_tolerance: dict[str, Any] = dict(evidence.get("zero_tolerance", {}))
    for key, value in certification.get("zero_tolerance", {}).items():
        if key in zero_tolerance and zero_tolerance[key] != value:
            append_once(
                blockers, f"conflicting evidence and certification count: {key}"
            )
            continue
        zero_tolerance[key] = value
    required_zero_fields = set(ALWAYS_ZERO_TOLERANCE_FIELDS)
    for technique in techniques:
        required_zero_fields.update(TECHNIQUE_ZERO_TOLERANCE_FIELDS.get(technique, ()))
    for key in sorted(required_zero_fields):
        value = zero_tolerance.get(key, 1)
        if isinstance(value, bool) or not isinstance(value, int) or value != 0:
            append_once(blockers, f"{key} must be explicitly zero")

    property_spec = load_required_local(pack, "properties/sample.json")
    global_solver_required = bool(
        set(profile.get("techniques", [])) & SOLVER_TECHNIQUES
    )
    for claim in profile.get("claims", []):
        if claim.get("criticality") != "P0":
            continue
        claim_id = claim.get("claim_id")
        claim_solver_required = bool(
            set(claim.get("required_techniques", [])) & SOLVER_TECHNIQUES
        )
        if not (global_solver_required or claim_solver_required):
            continue
        if property_spec.get("claim_id") != claim_id:
            append_once(
                blockers, f"P0 solver claim {claim_id} has no governed property"
            )
        elif proof.get("property_id") != property_spec.get("property_id"):
            append_once(blockers, "required P0 property proof identity does not match")
        elif proof.get("status") != "proved":
            append_once(blockers, "required P0 property proof is not proved")
        else:
            solver = proof.get("solver", {})
            if (
                not isinstance(solver, dict)
                or not isinstance(solver.get("name"), str)
                or not solver.get("name", "").strip()
                or not isinstance(solver.get("version"), str)
                or solver.get("version") in {"", "NOT_CONFIGURED", "unknown"}
                or isinstance(solver.get("timeout_ms"), bool)
                or not isinstance(solver.get("timeout_ms"), int)
                or solver.get("timeout_ms", 0) <= 0
                or not isinstance(solver.get("options"), dict)
            ):
                append_once(blockers, "required P0 proof solver contract is invalid")
            model_ref = proof.get("model_ref")
            model_path = local_ref_path(pack, model_ref)
            if model_path is None:
                append_once(
                    blockers, "required P0 proof model_ref is missing or unsafe"
                )
            else:
                model_digest = (
                    "sha256:" + hashlib.sha256(model_path.read_bytes()).hexdigest()
                )
                if proof.get("input_digest") != model_digest:
                    append_once(
                        blockers,
                        "required P0 proof input_digest does not bind model_ref",
                    )
            for field in ("certificate_ref", "concrete_replay_ref"):
                if local_ref_path(pack, proof.get(field)) is None:
                    append_once(
                        blockers, f"required P0 proof {field} is missing or unsafe"
                    )

    for corpus_key in ("negative", "holdout", "representative-workloads"):
        corpus = validate_certification_corpus(
            pack,
            corpus_key,
            manifest.get("scope", {}).get("source_artifact_digest"),
            blockers,
        )
        if corpus_key == "holdout":
            if corpus.get("independence") != "independently-verified":
                append_once(blockers, "holdout corpus is not independently verified")
            verifier = corpus.get("independent_verifier")
            executor = corpus.get("executor")
            if not isinstance(verifier, str) or not verifier.strip():
                append_once(blockers, "holdout corpus independent verifier missing")
            if not isinstance(executor, str) or not executor.strip():
                append_once(blockers, "holdout corpus executor missing")
            elif verifier == executor:
                append_once(
                    blockers, "holdout corpus executor and verifier must differ"
                )
        elif corpus_key == "representative-workloads":
            if corpus.get("provenance") != "production-derived":
                append_once(
                    blockers, "representative workload corpus is not production-derived"
                )
            authorization_ref = corpus.get("authorization_ref")
            if not representative_authorization_is_valid(
                pack, authorization_ref, manifest, corpus
            ):
                append_once(
                    blockers,
                    "representative workload authorization record is missing, invalid, or not content-bound locally",
                )

    for claim in assurance.get("claims", []):
        if claim.get("status") != "supported":
            append_once(
                blockers,
                f"assurance claim {claim.get('claim_id')} is not fully supported",
            )
    if not assurance.get("approvals"):
        append_once(blockers, "assurance case approvals empty")
    if not profile.get("approvals"):
        append_once(blockers, "validation profile approvals empty")
    if not oracles.get("approvals"):
        append_once(blockers, "oracle registry approvals empty")
    if not certification.get("approved_at"):
        append_once(blockers, "certification approval timestamp missing")
    if oracles.get("conflicts"):
        append_once(blockers, "oracle conflicts remain")

    oracle_by_id = {
        oracle.get("oracle_id"): oracle for oracle in oracles.get("oracles", [])
    }
    pack_owner = manifest.get("owner")
    for claim in profile.get("claims", []):
        if claim.get("criticality") != "P0":
            continue
        required_ids = claim.get("required_oracles", [])
        missing_oracle_ids = [
            oracle_id for oracle_id in required_ids if oracle_id not in oracle_by_id
        ]
        if missing_oracle_ids:
            append_once(
                blockers,
                f"P0 claim {claim.get('claim_id')} references missing required oracles: {sorted(missing_oracle_ids)}",
            )
        required = [oracle_by_id.get(oracle_id, {}) for oracle_id in required_ids]
        independent = [
            oracle
            for oracle in required
            if oracle.get("independence") == "independent"
            and oracle.get("owner") != pack_owner
            and oracle.get("evidence_refs")
            and all(
                isinstance(ref, str)
                and not ref.startswith(("http://", "https://"))
                and local_ref_path(pack, ref) is not None
                for ref in oracle.get("evidence_refs", [])
            )
        ]
        if not independent:
            append_once(
                blockers,
                f"P0 claim {claim.get('claim_id')} has no independent external oracle evidence",
            )

    scope = manifest.get("scope", {})
    for field in (
        "controlled_public_dns_rebinding_campaign",
        "independent_holdout",
        "representative_production_workload",
    ):
        if scope.get(field) != "passed":
            append_once(
                blockers,
                f"scope {field} must be passed (found {scope.get(field)!r})",
            )

    expected_references = {
        ("contracts", "validation_profile"): "validation-profile.json",
        ("contracts", "oracle_registry"): "oracle-registry.json",
        ("contracts", "assurance_case"): "assurance/assurance-case.json",
        ("corpus", "development"): "corpus/development",
        ("corpus", "negative"): "corpus/negative",
        ("corpus", "holdout"): "corpus/holdout",
        ("corpus", "representative_workloads"): "corpus/representative-workloads",
        ("certification", "evidence_path"): "certification/evidence.json",
        ("certification", "result_path"): "certification/gate-result.json",
    }
    for (section, key), expected in expected_references.items():
        actual = manifest.get(section, {}).get(key)
        if actual != expected:
            append_once(
                blockers,
                f"pack {section}.{key} must reference {expected} (found {actual!r})",
            )

    integrity_ref = evidence.get("integrity_manifest")
    if not isinstance(integrity_ref, str) or not integrity_ref:
        append_once(blockers, "content-addressed evidence manifest is required")
    elif not resolve_ref(pack, integrity_ref):
        append_once(blockers, "content-addressed evidence manifest is missing")

    refs = (
        evidence.get("evidence_refs", [])
        + certification.get("evidence_refs", [])
        + assurance.get("evidence", [])
        + proof.get("evidence_refs", [])
    )
    binding_records = evidence.get("repository_binding_records")
    if not isinstance(binding_records, list) or not binding_records:
        append_once(blockers, "repository binding records are required for readiness")
    if not refs:
        append_once(blockers, "certification evidence refs empty")
    for ref in refs:
        if isinstance(ref, str) and ref.startswith(("http://", "https://")):
            append_once(
                blockers,
                f"external evidence ref is not locally content-bound: {ref}",
            )
        elif not resolve_ref(pack, ref):
            append_once(blockers, f"missing evidence ref: {ref}")
    return blockers


def main(repository_root: Path | None = None) -> int:
    output_pack = Path(sys.argv[1])
    repository_root = (
        repository_root.resolve(strict=True)
        if repository_root is not None
        else Path(__file__).resolve().parents[2]
    )
    provisional_result = {
        "schema_version": 1,
        "pack_key": None,
        "status": "failed",
        "structural_gate_status": "failed",
        "certification_requested": False,
        "certification_decision": "BLOCKED",
        "certification_readiness": "BLOCKED",
        "maximum_local_decision": MAXIMUM_LOCAL_DECISION,
        "evaluated_pack_digest": None,
        "pack_status": None,
        "failures": ["gate evaluation did not complete"],
        "certification_blockers": [],
    }
    try:
        write_gate_output(
            output_pack,
            "gate-result.json",
            json.dumps(provisional_result, indent=2) + "\n",
        )
        write_gate_output(
            output_pack,
            "gate-report.md",
            "# Batch 35 gate\n\n- Structural gate status: `failed`\n"
            "- Certification decision: `BLOCKED`\n"
            "- Certification readiness: `BLOCKED`\n\n"
            "Gate evaluation did not complete.\n",
        )
    except (OSError, ValueError) as exc:
        print(
            f"GATE FAIL: cannot safely initialize gate outputs: {exc}", file=sys.stderr
        )
        return 2

    structural_failures: list[str] = []
    validator = Path(__file__).with_name("validate_verification_pack.py")
    records: list[tuple[Any, dict[str, Any]]] = []
    repository_digest: str | None = None
    evaluated_digest: str | None = None
    try:
        original_digest = pack_content_digest(output_pack)
        with tempfile.TemporaryDirectory(prefix="elmos-b35-gate-") as temporary:
            pack = Path(temporary) / "pack"
            shutil.copytree(output_pack.resolve(strict=True), pack, symlinks=True)
            snapshot_digest = pack_content_digest(pack)
            if snapshot_digest != original_digest:
                structural_failures.append(
                    "verification pack changed while the immutable snapshot was created"
                )
            if subprocess.run(
                [
                    sys.executable,
                    str(validator),
                    str(pack),
                    "--repository-root",
                    str(repository_root),
                ],
                check=False,
            ).returncode:
                structural_failures.append("verification pack validation failed")
            manifest = load_required_local(pack, "pack.json")
            profile = load_required_local(pack, "validation-profile.json")
            oracles = load_required_local(pack, "oracle-registry.json")
            proof = load_required_local(pack, "solver/proof.json")
            assurance = load_required_local(pack, "assurance/assurance-case.json")
            evidence = load_required_local(pack, "certification/evidence.json")
            certification = load_required_local(
                pack, "certification/certification.json"
            )
            records = repository_binding_records(pack)
            repository_digest, repository_errors = repository_files_digest(
                records, repository_root
            )
            for error in repository_errors:
                append_once(
                    structural_failures,
                    f"repository binding evaluation failed: {error}",
                )
            evaluated_digest = compose_evaluated_pack_digest(
                snapshot_digest, repository_digest
            )

            if manifest.get("status") != certification.get("status"):
                structural_failures.append("pack and certification status mismatch")
            blockers = certification_blockers(
                pack,
                manifest,
                profile,
                oracles,
                proof,
                assurance,
                evidence,
                certification,
            )
            if pack_content_digest(pack) != snapshot_digest:
                structural_failures.append(
                    "immutable verification snapshot changed during evaluation"
                )
            if pack_content_digest(output_pack) != original_digest:
                structural_failures.append(
                    "verification pack changed during gate evaluation"
                )
            current_repository_digest, current_repository_errors = (
                repository_files_digest(records, repository_root)
            )
            for error in current_repository_errors:
                append_once(
                    structural_failures,
                    f"repository binding changed during gate evaluation: {error}",
                )
            if current_repository_digest != repository_digest:
                append_once(
                    structural_failures,
                    "repository-bound files changed during gate evaluation",
                )
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        print(f"GATE FAIL: cannot load stable pack snapshot: {exc}", file=sys.stderr)
        return 2

    def live_drift_failures(stage: str) -> list[str]:
        drift: list[str] = []
        try:
            if pack_content_digest(output_pack) != original_digest:
                drift.append(f"verification pack changed {stage}")
            current_digest, current_errors = repository_files_digest(
                records, repository_root
            )
            drift.extend(
                f"repository binding changed {stage}: {error}"
                for error in current_errors
            )
            if current_digest != repository_digest:
                drift.append(f"repository-bound files changed {stage}")
        except (OSError, ValueError) as exc:
            drift.append(f"cannot revalidate evaluated inputs {stage}: {exc}")
        return drift

    for failure in live_drift_failures("before final gate output"):
        append_once(structural_failures, failure)

    requested_certified = (
        manifest.get("status") == "certified"
        or certification.get("status") == "certified"
    )
    def build_outputs() -> tuple[dict[str, Any], str]:
        failures = [
            *structural_failures,
            *(blockers if requested_certified else []),
        ]
        structural_status = "failed" if structural_failures else "passed"
        status = "failed" if failures else "passed"
        # Repository-owned JSON and an unsigned evidence manifest can establish
        # local readiness, but they cannot establish an independent certification
        # authority. A successful local gate stops at an external-gate handoff.
        decision = "BLOCKED" if failures else "NOT_CERTIFIED"
        readiness = (
            MAXIMUM_LOCAL_DECISION
            if not structural_failures and not blockers
            else "BLOCKED"
        )
        result = {
            "schema_version": 1,
            "pack_key": manifest.get("pack_key"),
            "status": status,
            "structural_gate_status": structural_status,
            "certification_requested": requested_certified,
            "certification_decision": decision,
            "certification_readiness": readiness,
            "maximum_local_decision": MAXIMUM_LOCAL_DECISION,
            "evaluated_pack_digest": evaluated_digest,
            "pack_status": manifest.get("status"),
            "failures": failures,
            "certification_blockers": blockers,
        }
        lines = [
            f"# Batch 35 gate: {manifest.get('pack_key')}",
            "",
            f"- Pack status: `{manifest.get('status')}`",
            f"- Structural gate status: `{structural_status}`",
            f"- Certification decision: `{decision}`",
            f"- Certification readiness: `{readiness}`",
            f"- Evaluated pack digest: `{evaluated_digest}`",
            "",
        ]
        if failures:
            lines.extend(
                ["## Failures", *[f"- {failure}" for failure in failures], ""]
            )
        if blockers:
            lines.extend(
                [
                    "## Certification blockers",
                    *[f"- {blocker}" for blocker in blockers],
                ]
            )
        elif not failures and readiness == MAXIMUM_LOCAL_DECISION:
            lines.append(
                "The exact declared scope is locally ready for an independent signed "
                "certification gate; this repository gate did not issue certification."
            )
        elif not failures:
            lines.append(
                "The pack remains NOT_CERTIFIED and is not ready for external certification."
            )
        return result, "\n".join(lines) + "\n"

    result, report = build_outputs()
    try:
        write_gate_output(output_pack, "gate-report.md", report)
    except (OSError, ValueError) as exc:
        print(f"GATE FAIL: cannot safely write gate report: {exc}", file=sys.stderr)
        return 2
    try:
        write_gate_output(
            output_pack, "gate-result.json", json.dumps(result, indent=2) + "\n"
        )
    except (OSError, ValueError) as exc:
        print(f"GATE FAIL: cannot safely write gate result: {exc}", file=sys.stderr)
        return 2

    post_write_drift = live_drift_failures("while final gate outputs were written")
    if post_write_drift:
        for failure in post_write_drift:
            append_once(structural_failures, failure)
        result, report = build_outputs()
        try:
            # Once drift is observed, persist the fail-closed machine result first.
            write_gate_output(
                output_pack, "gate-result.json", json.dumps(result, indent=2) + "\n"
            )
            write_gate_output(output_pack, "gate-report.md", report)
        except (OSError, ValueError) as exc:
            print(
                f"GATE FAIL: cannot safely persist drift-blocked outputs: {exc}",
                file=sys.stderr,
            )
            return 2

    if result["failures"]:
        print(
            "\n".join(
                f"GATE FAIL: {failure}" for failure in result["failures"]
            ),
            file=sys.stderr,
        )
        return 2
    print(
        f"GATE PASS: {manifest.get('pack_key')} status={manifest.get('status')} "
        f"decision={result['certification_decision']} "
        f"readiness={result['certification_readiness']} blockers={len(blockers)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
