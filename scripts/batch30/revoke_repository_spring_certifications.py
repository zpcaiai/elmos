#!/usr/bin/env python3
"""Revoke Spring certification claims produced with repository-owned keys.

Dry-run is the default.  ``--apply`` removes the compromised campaign material,
demotes affected packs to their evidence-supported ceiling, refreshes local
content bindings, revokes the exposed signer in repository trust stores, and
corrects the business-line closure matrix.  The operation is intentionally
idempotent and only touches the allowlisted Spring certification surfaces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LIMITED_PACK = "spring-boot-2-7-18-to-3-5-3"
LEGACY_MVC_PACK = "spring-framework-5-3-mvc-to-spring-boot-3-5-3"
PACK_KEYS = (
    "spring-boot-1-5-to-3-5-3",
    "spring-boot-1-5-to-4-1-0",
    "spring-boot-2-0-2-6-to-3-5-3",
    "spring-boot-2-0-2-6-to-4-1-0",
    LIMITED_PACK,
    "spring-boot-2-7-18-to-4-1-0",
    "spring-boot-2-x-gradle-to-3-5-3",
    "spring-boot-2-x-gradle-to-4-1-0",
    "spring-boot-3-0-3-4-to-3-5-3",
    "spring-boot-3-0-3-4-to-4-1-0",
    "spring-boot-3-5-to-4-1-0",
    "spring-framework-5-3-mvc-to-boot-4-1-0",
    "spring-framework-5-3-mvc-to-spring-boot-3-5-3",
)
EXTERNAL_GATE_FIELDS = (
    "authorized_customer_repository",
    "customer_acceptance",
    "customer_holdout",
    "external_certification",
    "independent_review",
    "rootless_runner",
    "rootless_transformer",
    "rootless_verifier",
)
LOCAL_RUNTIME_GATE_FIELDS = (
    "source_build",
    "source_startup",
    "openrewrite_execution",
    "target_build",
    "target_startup",
    "behavior_equivalence",
)
EXPERIMENTAL_NOT_RUN_GATE_FIELDS = EXTERNAL_GATE_FIELDS + (
    "negative_corpus",
    "holdout",
    "representative_repository",
    "performance",
    "security",
    "operability",
    "sbom",
    "rollback",
)
COMPROMISED_SIGNER = "ethan-independent-certifier"
CENTRAL_ARTIFACTS = (
    "certification/dossiers/spring-modernization-v1",
    "certification/dossiers/spring-boot-4-modernization-v1",
    "certification/reports/spring-modernization-v1-certification-report.json",
    "certification/reports/spring-boot-4-modernization-v1-certification-report.json",
    "certification/ethan-certifier/certifier-private.pem",
)
TRUST_STORES = (
    "certification/trust-store.json",
    "certification/batch1-37-trust-store.json",
    "certification/batch38-45-trust-store.json",
    "certification/mature-product-trust-store.json",
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _without_external_refs(refs: Any) -> list[str]:
    if not isinstance(refs, list):
        return []
    return [
        ref
        for ref in refs
        if isinstance(ref, str)
        and not ref.endswith("external-admission.json")
        and "campaign-runs/actor-ethan-certified" not in ref
    ]


def _refresh_bindings(pack: Path, support: dict[str, Any]) -> None:
    for capability in support.get("capabilities", []):
        if not isinstance(capability, dict):
            continue
        for binding in capability.get("evidence_bindings", []):
            if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
                continue
            relative = Path(binding["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"unsafe evidence binding in {pack.name}: {relative}")
            evidence_path = (pack / relative).resolve(strict=True)
            if not evidence_path.is_relative_to(pack.resolve()) or evidence_path.is_symlink():
                raise ValueError(f"unsafe evidence binding in {pack.name}: {relative}")
            raw = evidence_path.read_bytes()
            binding["bytes"] = len(raw)
            binding["sha256"] = hashlib.sha256(raw).hexdigest()


def _restore_legacy_mvc_local_evidence(
    evidence: dict[str, Any], certification: dict[str, Any]
) -> None:
    """Restore only the bounded local replay claims that have durable evidence."""

    evidence.update(
        {
            "evidence_class": "LOCAL_ENGINEERING_EXACT_FIXTURE",
            "runs": [
                {
                    "id": "spring-mvc-5.3.39-to-boot-3.5.3-local-2026-08-30",
                    "status": "PASSED_LOCAL",
                    "scope": "LOCAL_ENGINEERING_EXACT_FIXTURE_ONLY",
                    "evidence_index": (
                        "certification/local-execution/2026-08-30/evidence-index.json"
                    ),
                }
            ],
            "metrics": {
                "source_fingerprint_coverage": None,
                "framework_contract_coverage": None,
                "build_green_rate": None,
                "startup_pass_rate": None,
                "p0_contract_pass_rate": None,
                "source_map_coverage": None,
                "manual_hours": None,
                "cost_per_verified_workload": None,
            },
            "metric_status": "NOT_EVALUATED_BEYOND_EXACT_FIXTURE",
            "critical_unknowns": 12,
            "silent_framework_drops": None,
            "critical_security_regressions": None,
            "critical_transaction_regressions": None,
            "critical_data_regressions": None,
            "duplicate_message_or_job_effects": None,
            "test_integrity_violations": None,
            "source_build_status": "PASSED_LOCAL",
            "source_startup_status": "PASSED_LOCAL",
            "transformation_status": "PASSED_LOCAL",
            "target_build_status": "PASSED_LOCAL",
            "target_startup_status": "PASSED_LOCAL",
            "behavior_equivalence_status": "PASSED_LOCAL",
            "negative_corpus_status": "NOT_RUN",
            "holdout_status": "NOT_RUN",
            "representative_repository_status": "NOT_RUN",
            "external_execution_status": "NOT_RUN",
        }
    )
    certification["gate_results"] = {
        "pack_specific_static_validation": "PASSED_LOCAL_STATIC",
        "batch30_structural_validation": "PASSED_LOCAL",
        "batch30_gate": "PASSED_EXPERIMENTAL_NOT_CERTIFIED",
        **{field: "PASSED_LOCAL" for field in LOCAL_RUNTIME_GATE_FIELDS},
        **{field: "NOT_RUN" for field in EXPERIMENTAL_NOT_RUN_GATE_FIELDS},
    }
    certification["metrics"] = {
        "source_fingerprint_coverage": None,
        "framework_contract_coverage": None,
        "build_green_rate": None,
        "startup_pass_rate": None,
        "p0_contract_pass_rate": None,
        "source_map_coverage": None,
    }


def _restore_limited_pack_local_evidence(
    evidence: dict[str, Any], certification: dict[str, Any]
) -> dict[str, Any]:
    """Retain the five pre-existing local/public engineering receipts only."""

    certification["gate_results"] = {
        "authorized_customer_repository": "NOT_RUN",
        "customer_acceptance": "NOT_RUN",
        "customer_holdout": "NOT_RUN",
        "development_fixture": "PASSED_LOCAL",
        "external_certification": "NOT_RUN",
        "github_app_private_repository": "NOT_RUN",
        "independent_review": "NOT_RUN",
        "public_holdout": "PASSED_LOCAL_ENGINEERING",
        "public_representative": "PASSED_LOCAL_ENGINEERING",
        "rootless_runner": "NOT_RUN",
        "rootless_transformer": "NOT_RUN",
        "rootless_verifier": "NOT_RUN",
        "structural_validation": "PASSED",
        "synthetic_holdout": "PASSED_LOCAL",
        "synthetic_representative": "PASSED_LOCAL",
    }
    return {
        "critical_data_regressions": 0,
        "critical_security_regressions": 0,
        "critical_transaction_regressions": 0,
        "critical_unknowns": 0,
        "customer_and_independent_evidence": "NOT_RUN",
        "duplicate_message_or_job_effects": 0,
        "external_execution_status": "NOT_RUN",
        "metrics": {
            "build_green_rate": 1.0,
            "cost_per_verified_workload": 0,
            "framework_contract_coverage": 1.0,
            "manual_hours": 0,
            "p0_contract_pass_rate": 1.0,
            "source_fingerprint_coverage": 1.0,
            "source_map_coverage": 1.0,
            "startup_pass_rate": 1.0,
        },
        "pack_key": evidence["pack_key"],
        "pack_version": evidence["pack_version"],
        "runs": [
            "local-reference-evidence.json",
            "local-product-journey-evidence.json",
            "public-reference-route-evidence.json",
            "local-product-surface-qualification-7b385827-20260809.json",
            "local-product-surface-qualification-fbe840c8-20260809.json",
        ],
        "schema_version": evidence["schema_version"],
        "silent_framework_drops": 0,
        "target_repository_runtime_evidence": "NOT_RUN",
        "test_integrity_violations": 0,
    }


def _reset_untrusted_experimental_claims(
    evidence: dict[str, Any], certification: dict[str, Any]
) -> None:
    """Remove pass claims that were supported only by the revoked campaign."""

    gate_results = certification.setdefault("gate_results", {})
    for field in EXPERIMENTAL_NOT_RUN_GATE_FIELDS + LOCAL_RUNTIME_GATE_FIELDS + (
        "behavioral_equivalence",
    ):
        gate_results[field] = "NOT_RUN"
    certification["metrics"] = {
        key: None for key in certification.get("metrics", {})
    }
    evidence["evidence_class"] = "NO_TRUSTED_EXECUTION_EVIDENCE"
    evidence["metric_status"] = "NOT_EVALUATED_NO_TRUSTED_RUN"
    evidence["metrics"] = {key: None for key in evidence.get("metrics", {})}
    for field in (
        "source_build_status",
        "source_startup_status",
        "transformation_status",
        "target_build_status",
        "target_startup_status",
        "behavior_equivalence_status",
        "negative_corpus_status",
        "holdout_status",
        "representative_repository_status",
    ):
        evidence[field] = "NOT_RUN"
    for field in (
        "critical_unknowns",
        "silent_framework_drops",
        "critical_security_regressions",
        "critical_transaction_regressions",
        "critical_data_regressions",
        "duplicate_message_or_job_effects",
        "test_integrity_violations",
    ):
        evidence[field] = None


def _normalize_pack(pack: Path, *, apply: bool) -> list[str]:
    changed: list[str] = []
    target_status = "limited" if pack.name == LIMITED_PACK else "experimental"
    manifest_path = pack / "pack.json"
    support_path = pack / "support-matrix.json"
    evidence_path = pack / "certification/evidence.json"
    certification_path = pack / "certification/certification.json"

    manifest = _load(manifest_path)
    support = _load(support_path)
    evidence = _load(evidence_path)
    certification = _load(certification_path)

    manifest["status"] = target_status
    certification["status"] = target_status
    certification["certification_decision"] = "NOT_CERTIFIED"
    certification["evidence_refs"] = _without_external_refs(
        certification.get("evidence_refs")
    )
    gate_results = certification.setdefault("gate_results", {})
    for field in EXTERNAL_GATE_FIELDS:
        gate_results[field] = "NOT_RUN"

    evidence["evidence_class"] = "LOCAL_ENGINEERING_EVIDENCE"
    evidence["external_execution_status"] = "NOT_RUN"
    evidence["customer_and_independent_evidence"] = "NOT_RUN"
    evidence["target_repository_runtime_evidence"] = "NOT_RUN"
    if "metric_status" in evidence:
        evidence["metric_status"] = "LOCAL_ENGINEERING_ONLY"
    evidence["runs"] = _without_external_refs(evidence.get("runs"))
    if pack.name == LIMITED_PACK:
        evidence = _restore_limited_pack_local_evidence(evidence, certification)
    elif pack.name == LEGACY_MVC_PACK:
        _restore_legacy_mvc_local_evidence(evidence, certification)
    else:
        _reset_untrusted_experimental_claims(evidence, certification)
    metrics = evidence.get("metrics")
    if isinstance(metrics, dict) and pack.name == LIMITED_PACK:
        metrics["manual_hours"] = 0
        metrics["cost_per_verified_workload"] = 0

    for capability in support.get("capabilities", []):
        if not isinstance(capability, dict):
            continue
        if capability.get("status") == "certified":
            capability["status"] = (
                "supported" if target_status == "limited" else "experimental"
            )
        capability["evidence_refs"] = _without_external_refs(
            capability.get("evidence_refs")
        )
    _refresh_bindings(pack, support)

    updates = {
        manifest_path: manifest,
        support_path: support,
        evidence_path: evidence,
        certification_path: certification,
    }
    for path, value in updates.items():
        rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if path.read_text(encoding="utf-8") != rendered:
            changed.append(path.relative_to(ROOT).as_posix())
            if apply:
                _atomic_json(path, value)

    for relative in (
        "certification/external-admission.json",
        "certification/campaign-runs/actor-ethan-certified",
    ):
        path = pack / relative
        if path.exists():
            changed.append(path.relative_to(ROOT).as_posix())
            if apply:
                if path.is_symlink():
                    raise ValueError(f"refusing to remove symlink: {path}")
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
    return changed


def _revoke_signer(path: Path, *, apply: bool) -> list[str]:
    if not path.exists():
        return []
    document = _load(path)
    changed = False

    def visit(value: Any) -> None:
        nonlocal changed
        if isinstance(value, dict):
            identity = value.get("signer_id") or value.get("keyId")
            if identity == COMPROMISED_SIGNER:
                if value.get("revoked") is not True:
                    value["revoked"] = True
                    changed = True
                if value.get("revocation_reason") != "PRIVATE_KEY_DISCLOSED_IN_REPOSITORY_HISTORY":
                    value["revocation_reason"] = "PRIVATE_KEY_DISCLOSED_IN_REPOSITORY_HISTORY"
                    changed = True
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    if changed and apply:
        _atomic_json(path, document)
    return [path.relative_to(ROOT).as_posix()] if changed else []


def _update_closure_matrix(*, apply: bool) -> list[str]:
    path = ROOT / "docs/BUSINESS_LINE_CLOSURE_MATRIX.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    replacements = {
        "| Spring 老项目翻新 M30 ": "| Spring 老项目翻新 M30 (向 Spring Boot 3.5.3) | 6 条精确路由、本地迁移引擎与保守 Batch 30 门禁 | 本地工程证据可用；仓库自签材料已撤销。客户私库、Rootless 生产执行、独立审查和外部认证必须由仓库外可信主体重新提供 | `READY_FOR_EXTERNAL_GATE / NOT_CERTIFIED` | 真实 Java 21/Maven/Gradle 构建启动、客户/代表性语料、Rootless、独立复核和外部签名仍为 `NOT_RUN` |",
        "| 低版本 Spring 向 Spring Boot 4.x 升级路线 M30 ": "| 低版本 Spring 向 Spring Boot 4.x 升级路线 M30 | 7 条精确路由及企业复杂场景实现 | 本地实现和测试不得替代客户、Rootless、独立审查或外部认证；仓库自签材料已撤销 | `READY_FOR_EXTERNAL_GATE / NOT_CERTIFIED` | 精确 Boot 4.x/Java 21 运行、外部证据与独立认证仍为 `NOT_RUN` |",
    }
    changed = False
    for index, line in enumerate(lines):
        for prefix, replacement in replacements.items():
            if line.startswith(prefix):
                if line != replacement:
                    lines[index] = replacement
                    changed = True
                break
    if changed and apply:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [path.relative_to(ROOT).as_posix()] if changed else []


def revoke(*, apply: bool) -> list[str]:
    changed: list[str] = []
    for pack_key in PACK_KEYS:
        pack = (ROOT / "framework-packs" / pack_key).resolve(strict=True)
        if not pack.is_relative_to((ROOT / "framework-packs").resolve()):
            raise ValueError(f"pack escaped framework-packs: {pack_key}")
        changed.extend(_normalize_pack(pack, apply=apply))
    for relative in CENTRAL_ARTIFACTS:
        path = ROOT / relative
        if path.exists():
            changed.append(relative)
            if apply:
                if path.is_symlink():
                    raise ValueError(f"refusing to remove symlink: {path}")
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
    for relative in TRUST_STORES:
        changed.extend(_revoke_signer(ROOT / relative, apply=apply))
    changed.extend(_update_closure_matrix(apply=apply))
    return sorted(set(changed))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    changed = revoke(apply=args.apply)
    print(json.dumps({
        "apply_requested": args.apply,
        "changed_paths": changed,
        "certification": "NOT_CERTIFIED",
        "external_evidence": "NOT_RUN",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
