#!/usr/bin/env python3
"""Promote a framework pack only after live P0-P11 re-verification.

Dry-run is the default. ``--apply`` updates the four authoritative pack files
and writes a non-self-certifying admission receipt under an exclusive lock. A
post-write Batch 30 gate re-verifies the external intake; any failure restores
the exact previous bytes.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.batch30.certification_campaign import (  # noqa: E402
    REQUIRED_EVIDENCE,
    CampaignError,
    evaluate_certification_campaign,
)
from scripts.precision_migration.trust import read_regular_file_once  # noqa: E402


class PromotionError(ValueError):
    """Raised when a certification promotion cannot complete atomically."""


AUTHORITATIVE_PATHS = (
    "pack.json",
    "support-matrix.json",
    "certification/evidence.json",
    "certification/certification.json",
)
MAX_AUTHORITATIVE_BYTES = 8 * 1024 * 1024


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = read_regular_file_once(
            path,
            max_bytes=MAX_AUTHORITATIVE_BYTES,
            label=label,
        )
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PromotionError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PromotionError(f"{label} must be a JSON object")
    return value


def _render(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _authoritative_path(pack: Path, relative: str) -> Path:
    lexical = Path(relative)
    if lexical.is_absolute() or not lexical.parts or ".." in lexical.parts:
        raise PromotionError(f"authoritative relative path is unsafe: {relative}")
    current = pack
    for part in lexical.parts:
        current /= part
        if current.is_symlink():
            raise PromotionError(
                f"authoritative path must not traverse a symlink: {relative}"
            )
    candidate = pack / lexical
    if not candidate.parent.is_dir() or candidate.parent.is_symlink():
        raise PromotionError(
            f"authoritative parent must be an existing real directory: {relative}"
        )
    return candidate


def _atomic_write(path: Path, raw: bytes) -> None:
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise PromotionError(f"authoritative parent is not a real directory: {path.parent}")
    if path.is_symlink():
        raise PromotionError(f"authoritative output must not be a symlink: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_remove(path: Path) -> None:
    if path.is_symlink():
        raise PromotionError(f"refusing to remove a symlink during rollback: {path}")
    path.unlink(missing_ok=True)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _promotion_lock(pack: Path) -> int:
    """Open a persistent per-pack lock without the classic unlink race."""

    lock_root = Path(tempfile.gettempdir()) / f"elmos-batch30-promotion-locks-{os.getuid()}"
    lock_root.mkdir(mode=0o700, exist_ok=True)
    root_stat = lock_root.lstat()
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or root_stat.st_uid != os.getuid()
        or stat.S_IMODE(root_stat.st_mode) & 0o077
    ):
        raise PromotionError(f"promotion lock directory is not private: {lock_root}")
    lock_name = hashlib.sha256(os.fsencode(pack)).hexdigest() + ".lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_root / lock_name, flags, 0o600)
    lock_stat = os.fstat(descriptor)
    if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != os.getuid():
        os.close(descriptor)
        raise PromotionError("promotion lock is not an owned regular file")
    os.fchmod(descriptor, 0o600)
    return descriptor


def _run_post_write_gate(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def build_promotion_documents(
    pack_dir: Path,
    campaign_result: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build deterministic promoted documents without writing them."""

    if campaign_result.get("decision") != "READY_FOR_BATCH30_CERTIFICATION_GATE":
        raise PromotionError("campaign is not ready for the Batch 30 certification gate")
    if campaign_result.get("verified_evidence_types") != list(REQUIRED_EVIDENCE):
        raise PromotionError("campaign did not verify the exact 13 evidence classes")
    pack = pack_dir.resolve(strict=True)
    manifest = _load(_authoritative_path(pack, "pack.json"), "pack manifest")
    support = _load(
        _authoritative_path(pack, "support-matrix.json"), "support matrix"
    )
    evidence = _load(
        _authoritative_path(pack, "certification/evidence.json"), "evidence record"
    )
    certification = _load(
        _authoritative_path(pack, "certification/certification.json"),
        "certification record",
    )
    if manifest.get("pack_key") != campaign_result.get("pack_key"):
        raise PromotionError("campaign and pack keys do not match")
    if manifest.get("status") not in {"experimental", "limited", "certified"}:
        raise PromotionError("only experimental, limited, or certified packs may be promoted")
    if certification.get("status") != manifest.get("status"):
        raise PromotionError("pack and certification status differ before promotion")

    certified_ids = set(campaign_result["certified_capability_ids"])
    capabilities = support.get("capabilities")
    if not isinstance(capabilities, list):
        raise PromotionError("support matrix capabilities are invalid")
    observed_ids = {item.get("id") for item in capabilities if isinstance(item, dict)}
    if not certified_ids or not certified_ids <= observed_ids:
        raise PromotionError("campaign certified capability scope is missing from the support matrix")

    admission = {
        "schema_version": "elmos.batch30.external-admission.v1",
        "evidence_class": "REVERIFIED_EXTERNAL_CERTIFICATION_ADMISSION",
        "pack_key": manifest["pack_key"],
        "pack_version": manifest["version"],
        "campaign_id": campaign_result["campaign_id"],
        "campaign_digest": campaign_result["campaign_digest"],
        "support_matrix_subject_digest": campaign_result[
            "support_matrix_subject_digest"
        ],
        "intake_id": campaign_result["intake_id"],
        "intake_content_digest": campaign_result["intake_content_digest"],
        "binding_digest": campaign_result["binding_digest"],
        "trust_store_digest": campaign_result["trust_store_digest"],
        "verified_evidence_types": list(REQUIRED_EVIDENCE),
        "verified_content_digests": campaign_result["verified_content_digests"],
        "certified_capability_ids": campaign_result["certified_capability_ids"],
        "metrics": campaign_result["metrics"],
        "zero_tolerance": campaign_result["zero_tolerance"],
        "gate_results": campaign_result["gate_results"],
        "decision": "CERTIFIED",
        "self_certifying": False,
        "requires_live_external_reverification": True,
    }

    promoted_manifest = copy.deepcopy(manifest)
    promoted_manifest["status"] = "certified"

    promoted_support = copy.deepcopy(support)
    for capability in promoted_support["capabilities"]:
        if capability.get("id") not in certified_ids:
            continue
        capability["status"] = "certified"
        if promoted_support.get("schema_version") == 1:
            refs = capability.setdefault("evidence_refs", [])
            if "certification/external-admission.json" not in refs:
                refs.append("certification/external-admission.json")

    promoted_evidence = copy.deepcopy(evidence)
    promoted_evidence["evidence_class"] = "REVERIFIED_EXTERNAL_CERTIFICATION"
    promoted_evidence["runs"] = [
        "external-admission.json",
    ]
    promoted_evidence["metrics"] = campaign_result["metrics"]
    promoted_evidence["metric_status"] = "EVALUATED_EXTERNAL_EXACT_SCOPE"
    for field, value in campaign_result["zero_tolerance"].items():
        promoted_evidence[field] = value
    promoted_evidence.update(
        {
            "source_build_status": "PASSED",
            "source_startup_status": "PASSED",
            "transformation_status": "PASSED",
            "target_build_status": "PASSED",
            "target_startup_status": "PASSED",
            "behavior_equivalence_status": "PASSED",
            "negative_corpus_status": "PASSED",
            "holdout_status": "PASSED",
            "representative_repository_status": "PASSED",
            "external_execution_status": "PASSED",
        }
    )

    promoted_certification = copy.deepcopy(certification)
    promoted_certification["status"] = "certified"
    promoted_certification["certification_decision"] = "CERTIFIED"
    promoted_certification["gate_results"].update(campaign_result["gate_results"])
    promoted_certification["gate_results"].update(
        {name: "PASSED" for name in REQUIRED_EVIDENCE}
    )
    promoted_certification["gate_results"]["behavior_equivalence"] = "PASSED"
    promoted_certification["metrics"] = {
        name: campaign_result["metrics"][name]
        for name in (
            "source_fingerprint_coverage",
            "framework_contract_coverage",
            "build_green_rate",
            "startup_pass_rate",
            "p0_contract_pass_rate",
            "source_map_coverage",
        )
    }
    refs = promoted_certification.setdefault("evidence_refs", [])
    if "certification/external-admission.json" not in refs:
        refs.append("certification/external-admission.json")

    return {
        "pack.json": promoted_manifest,
        "support-matrix.json": promoted_support,
        "certification/evidence.json": promoted_evidence,
        "certification/certification.json": promoted_certification,
        "certification/external-admission.json": admission,
    }


def promote(
    *,
    pack_dir: Path,
    campaign_path: Path,
    intake_path: Path,
    trust_store: Path,
    evidence_roots: Iterable[Path],
    apply: bool,
) -> dict[str, Any]:
    if pack_dir.is_symlink():
        raise PromotionError("pack_dir must not be a symlink")
    pack = pack_dir.resolve(strict=True)
    if not pack.is_dir():
        raise PromotionError("pack_dir must be a directory")
    campaign = campaign_path.resolve(strict=True)
    intake = intake_path.resolve(strict=True)
    trust = trust_store.resolve(strict=True)
    roots = [root.resolve(strict=True) for root in evidence_roots]
    def evaluate_and_build() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        campaign_result = evaluate_certification_campaign(
            pack_dir=pack,
            campaign_path=campaign,
            intake_path=intake,
            trust_store=trust,
            evidence_roots=roots,
        )
        return campaign_result, build_promotion_documents(pack, campaign_result)

    if not apply:
        campaign_result, documents = evaluate_and_build()
        return {
            "decision": "READY_TO_APPLY",
            "apply_requested": False,
            "pack_key": campaign_result["pack_key"],
            "campaign_digest": campaign_result["campaign_digest"],
            "intake_content_digest": campaign_result["intake_content_digest"],
            "verified_evidence_types": campaign_result["verified_evidence_types"],
            "changed_paths": list(documents),
        }

    lock_descriptor = _promotion_lock(pack)
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        campaign_result, documents = evaluate_and_build()
        before: dict[str, bytes | None] = {}
        for relative in documents:
            path = _authoritative_path(pack, relative)
            if path.is_symlink():
                raise PromotionError(f"authoritative path must not be a symlink: {relative}")
            before[relative] = (
                read_regular_file_once(
                    path,
                    max_bytes=MAX_AUTHORITATIVE_BYTES,
                    label=f"authoritative path {relative}",
                )
                if path.exists()
                else None
            )
        try:
            for relative, value in documents.items():
                _atomic_write(_authoritative_path(pack, relative), _render(value))
            gate = ROOT / "scripts" / "batch30" / "run_framework_gate.py"
            command = [
                sys.executable,
                str(gate),
                str(pack),
                "--campaign",
                str(campaign),
                "--external-intake",
                str(intake),
                "--trust-store",
                str(trust),
            ]
            for root in roots:
                command.extend(["--evidence-root", str(root)])
            completed = _run_post_write_gate(command)
            if completed.returncode != 0:
                raise PromotionError(
                    "post-write Batch 30 gate failed: "
                    + (completed.stderr.strip() or completed.stdout.strip())
                )
        except Exception:
            for relative, raw in before.items():
                path = _authoritative_path(pack, relative)
                if raw is None:
                    _atomic_remove(path)
                else:
                    _atomic_write(path, raw)
            raise
    finally:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(lock_descriptor)
    return {
        "decision": "CERTIFIED",
        "apply_requested": True,
        "pack_key": campaign_result["pack_key"],
        "campaign_digest": campaign_result["campaign_digest"],
        "intake_content_digest": campaign_result["intake_content_digest"],
        "verified_evidence_types": campaign_result["verified_evidence_types"],
        "changed_paths": list(documents),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path)
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--external-intake", type=Path, required=True)
    parser.add_argument("--trust-store", type=Path, required=True)
    parser.add_argument("--evidence-root", action="append", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    campaign = args.campaign or args.pack_dir / "certification/p0-p11-campaign.json"
    try:
        result = promote(
            pack_dir=args.pack_dir,
            campaign_path=campaign,
            intake_path=args.external_intake,
            trust_store=args.trust_store,
            evidence_roots=args.evidence_root,
            apply=args.apply,
        )
    except (CampaignError, PromotionError, OSError, ValueError) as exc:
        print(f"PROMOTION FAIL: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
