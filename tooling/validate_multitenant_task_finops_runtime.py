#!/usr/bin/env python3
"""Validate the repository-owned multi-tenant task/FinOps result layer.

The imported package remains immutable source material.  This validator keeps
repository implementation, execution, and evidence states separate and refuses
to promote a task, source-risk mitigation, or dependency binding without
content-addressed repository evidence.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any


TASK_CATALOG = Path(
    "skills/elmos-multitenant-task-finops-skills-v1.0.0/docs/task-catalog.json"
)
SOURCE_RISK_REGISTER = Path(
    "docs/multitenant-task-finops-skills/source-risk-register.json"
)
COMPILED_MANIFEST = Path(
    "docs/multitenant-task-finops-skills/compiled-manifest.json"
)
SOURCE_MATRIX = Path(
    "docs/multitenant-task-finops-skills/implementation-matrix.json"
)
INSTALLED_MANIFEST = Path(
    "docs/multitenant-task-finops-skills/installed-manifest.json"
)
TASK_RESULTS = Path(
    "docs/multitenant-task-finops-skills/repository-task-results.json"
)
RECONCILIATION_REGISTER = Path(
    "docs/multitenant-task-finops-skills/repository-reconciliation-register.json"
)
DEPENDENCY_BINDINGS = Path(
    "docs/multitenant-task-finops-skills/repository-dependency-bindings.json"
)

EXPECTED_PACKAGE = "elmos-multitenant-task-finops-skills"
EXPECTED_VERSION = "1.0.0"
EXPECTED_TASK_COUNT = 144
EXPECTED_FINDING_COUNT = 11
EXPECTED_EXTERNAL_DEPENDENCIES = {
    "elmos-architecture-contract-governance",
    "elmos-identity-tenant-security",
    "elmos-observability-finops",
    "elmos-temporal-task-reliability",
}

IMPLEMENTATION_STATES = {"NOT_STARTED", "PARTIAL", "IMPLEMENTED", "BLOCKED"}
EXECUTION_STATES = {"NOT_RUN", "PASS", "FAIL", "INCONCLUSIVE"}
EVIDENCE_STATES = {
    "NONE",
    "LOCAL_SELF_ATTESTED",
    "LOCAL_INDEPENDENT",
    "EXTERNAL_INDEPENDENT",
}
RECONCILIATION_STATES = {"NOT_EVALUATED", "PARTIAL", "MITIGATED_LOCAL", "BLOCKED"}
DEPENDENCY_STATES = {"UNRESOLVED", "CANDIDATE", "RESOLVED_LOCAL", "EXTERNAL_VERIFIED"}

SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _error(errors: list[str], location: str, message: str) -> None:
    errors.append(f"{location}: {message}")


def _load_json(root: Path, relative: Path, errors: list[str]) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _error(errors, relative.as_posix(), f"cannot load JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        _error(errors, relative.as_posix(), "document must be a JSON object")
        return {}
    return value


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_repository_file(root: Path, logical: Any) -> Path | None:
    if not isinstance(logical, str):
        return None
    relative = PurePosixPath(logical)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        return None
    candidate = root.joinpath(*relative.parts)
    try:
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        resolved_root = root.resolve(strict=True)
    except OSError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        return None
    if resolved_root not in (resolved, *resolved.parents):
        return None
    return resolved


def _validate_package_identity(document: dict[str, Any], location: str, errors: list[str]) -> None:
    package = document.get("package")
    if package != {"name": EXPECTED_PACKAGE, "version": EXPECTED_VERSION}:
        _error(errors, location, "package identity does not match the pinned source package")


def _validate_binding(
    root: Path,
    binding: Any,
    location: str,
    errors: list[str],
) -> str | None:
    if not isinstance(binding, dict):
        _error(errors, location, "binding must be an object")
        return None
    path = _safe_repository_file(root, binding.get("path"))
    if path is None:
        _error(errors, location, "binding path is missing, unsafe, a symlink, or not a regular file")
        return None
    logical = str(binding["path"])
    payload = path.read_bytes()
    if isinstance(binding.get("byte_size"), bool) or binding.get("byte_size") != len(payload):
        _error(errors, location, f"byte_size mismatch for {logical}")
    expected = "sha256:" + hashlib.sha256(payload).hexdigest()
    if binding.get("sha256") != expected:
        _error(errors, location, f"sha256 mismatch for {logical}")
    return logical


def _validate_bindings(
    root: Path,
    bindings: Any,
    location: str,
    errors: list[str],
) -> list[str]:
    if not isinstance(bindings, list):
        _error(errors, location, "implementation_bindings must be an array")
        return []
    paths: list[str] = []
    for index, binding in enumerate(bindings):
        path = _validate_binding(root, binding, f"{location}[{index}]", errors)
        if path is not None:
            paths.append(path)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        _error(errors, location, "binding paths must be unique and lexically sorted")
    return paths


def _validate_receipt(
    root: Path,
    receipt: Any,
    evidence_state: str,
    execution_state: str,
    location: str,
    errors: list[str],
) -> None:
    if not isinstance(receipt, dict):
        _error(errors, location, "result receipt must be an object")
        return
    for field in ("receipt_id", "command", "executor", "verifier"):
        if not isinstance(receipt.get(field), str) or not receipt[field].strip():
            _error(errors, location, f"{field} must be a non-empty string")
    if not COMMIT_SHA.fullmatch(str(receipt.get("repository_commit", ""))):
        _error(errors, location, "repository_commit must be an exact 40-character SHA")
    if not SHA256.fullmatch(str(receipt.get("environment_digest", ""))):
        _error(errors, location, "environment_digest must be an exact SHA-256")
    if isinstance(receipt.get("duration_ms"), bool) or not isinstance(receipt.get("duration_ms"), int) or receipt.get("duration_ms", -1) < 0:
        _error(errors, location, "duration_ms must be a non-negative integer")
    exit_code = receipt.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        _error(errors, location, "exit_code must be an exact integer")
    expected_receipt_status = {
        "PASS": "PASSED",
        "FAIL": "FAILED",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }.get(execution_state)
    if receipt.get("status") != expected_receipt_status:
        _error(errors, location, f"{execution_state} receipt must report status {expected_receipt_status}")
    totals = receipt.get("tests")
    if not isinstance(totals, dict):
        _error(errors, location, "tests must be an object")
    else:
        required = ("total", "passed", "failed", "errors", "skipped")
        if any(isinstance(totals.get(key), bool) or not isinstance(totals.get(key), int) for key in required):
            _error(errors, location, "all test totals must be exact integers")
        elif totals["total"] < 1 or sum(totals[key] for key in ("passed", "failed", "errors", "skipped")) != totals["total"]:
            _error(errors, location, "receipt test totals must be non-empty and arithmetically complete")
        elif execution_state == "PASS" and not (
            exit_code == 0
            and totals["passed"] == totals["total"]
            and totals["failed"] == 0
            and totals["errors"] == 0
            and totals["skipped"] == 0
        ):
            _error(errors, location, "PASS receipt requires exit_code 0 and zero failures/errors/skips")
        elif execution_state == "FAIL" and not (
            exit_code != 0 or totals["failed"] > 0 or totals["errors"] > 0
        ):
            _error(errors, location, "FAIL receipt must contain a failing exit code or failed/error test")
    artifact = receipt.get("artifact")
    _validate_binding(root, artifact, f"{location}.artifact", errors)
    if evidence_state in {"LOCAL_INDEPENDENT", "EXTERNAL_INDEPENDENT"}:
        if receipt.get("executor") == receipt.get("verifier"):
            _error(errors, location, "independent evidence requires distinct executor and verifier")
    if evidence_state == "EXTERNAL_INDEPENDENT":
        authorization = receipt.get("authorization")
        if not isinstance(authorization, dict):
            _error(errors, location, "external evidence requires an authorization object")
        else:
            if authorization.get("status") != "APPROVED":
                _error(errors, location, "external authorization must be APPROVED")
            if not SHA256.fullmatch(str(authorization.get("scope_digest", ""))):
                _error(errors, location, "external authorization scope_digest must be exact SHA-256")


def _validate_source_boundaries(root: Path, errors: list[str]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    catalog = _load_json(root, TASK_CATALOG, errors)
    source_risks = _load_json(root, SOURCE_RISK_REGISTER, errors)
    compiled = _load_json(root, COMPILED_MANIFEST, errors)
    matrix = _load_json(root, SOURCE_MATRIX, errors)
    installed = _load_json(root, INSTALLED_MANIFEST, errors)

    tasks = catalog.get("tasks")
    if catalog.get("total_tasks") != EXPECTED_TASK_COUNT or not isinstance(tasks, list) or len(tasks) != EXPECTED_TASK_COUNT:
        _error(errors, TASK_CATALOG.as_posix(), "source task catalog must contain exactly 144 tasks")
    task_ids = [task.get("task_id") for task in tasks or [] if isinstance(task, dict)]
    if len(task_ids) != len(set(task_ids)):
        _error(errors, TASK_CATALOG.as_posix(), "source task IDs must be unique")

    if matrix.get("summary") != {"NOT_RUN": 144, "PASS": 0, "total": 144}:
        _error(errors, SOURCE_MATRIX.as_posix(), "immutable source matrix summary must remain all NOT_RUN")
    matrix_tasks = matrix.get("tasks")
    if not isinstance(matrix_tasks, list) or len(matrix_tasks) != EXPECTED_TASK_COUNT:
        _error(errors, SOURCE_MATRIX.as_posix(), "immutable source matrix must contain 144 tasks")
    elif any(item.get("status") != "NOT_RUN" or item.get("evidence") != [] for item in matrix_tasks if isinstance(item, dict)):
        _error(errors, SOURCE_MATRIX.as_posix(), "immutable source matrix tasks must remain NOT_RUN without evidence")
    if matrix.get("external_evidence_status") != "NOT_RUN" or matrix.get("certification_status") != "NOT_CERTIFIED":
        _error(errors, SOURCE_MATRIX.as_posix(), "source external/certification boundary drifted")

    findings = source_risks.get("findings")
    if (
        source_risks.get("adoption_gate") != "BLOCKED"
        or source_risks.get("reference_material_application_status") != "NOT_APPLIED"
        or source_risks.get("open_zero_tolerance_findings") != EXPECTED_FINDING_COUNT
        or not isinstance(findings, list)
        or len(findings) != EXPECTED_FINDING_COUNT
    ):
        _error(errors, SOURCE_RISK_REGISTER.as_posix(), "source adoption/risk boundary drifted")
    elif any(item.get("status") != "OPEN" or item.get("severity") != "CRITICAL" for item in findings if isinstance(item, dict)):
        _error(errors, SOURCE_RISK_REGISTER.as_posix(), "all source findings must remain OPEN and CRITICAL")

    external = compiled.get("external_dependencies")
    names = {
        item.get("name")
        for item in external or []
        if isinstance(item, dict) and item.get("status") == "DECLARED_UNRESOLVED"
    }
    if not isinstance(external, list) or len(external) != 4 or names != EXPECTED_EXTERNAL_DEPENDENCIES:
        _error(errors, COMPILED_MANIFEST.as_posix(), "four exact source dependencies must remain DECLARED_UNRESOLVED")
    reference = compiled.get("reference_material")
    reference_statuses = {
        key: value for key, value in reference.items() if key != "reason"
    } if isinstance(reference, dict) else {}
    if not reference_statuses or set(reference_statuses.values()) != {"NOT_APPLIED"}:
        _error(errors, COMPILED_MANIFEST.as_posix(), "all source reference material must remain NOT_APPLIED")
    if compiled.get("external_evidence_status") != "NOT_RUN" or compiled.get("certification_status") != "NOT_CERTIFIED":
        _error(errors, COMPILED_MANIFEST.as_posix(), "compiled external/certification boundary drifted")

    if (
        installed.get("reference_material_application_status") != "NOT_APPLIED"
        or installed.get("external_dependency_status") != "DECLARED_UNRESOLVED"
        or installed.get("external_evidence_status") != "NOT_RUN"
        or installed.get("certification_status") != "NOT_CERTIFIED"
    ):
        _error(errors, INSTALLED_MANIFEST.as_posix(), "installed source boundary drifted")
    return catalog, source_risks, compiled


def _validate_task_results(root: Path, catalog: dict[str, Any], errors: list[str]) -> dict[str, collections.Counter[str]]:
    document = _load_json(root, TASK_RESULTS, errors)
    _validate_package_identity(document, TASK_RESULTS.as_posix(), errors)
    expected_catalog_digest = _file_sha256(root / TASK_CATALOG)
    if document.get("source_task_catalog") != {
        "path": TASK_CATALOG.as_posix(),
        "sha256": expected_catalog_digest,
    }:
        _error(errors, TASK_RESULTS.as_posix(), "source task catalog binding is stale or invalid")
    if (
        document.get("source_reference_application_status") != "NOT_APPLIED"
        or document.get("source_external_dependency_status") != "DECLARED_UNRESOLVED"
        or document.get("external_evidence_status") != "NOT_RUN"
        or document.get("production_certification") != "NOT_CERTIFIED"
    ):
        _error(errors, TASK_RESULTS.as_posix(), "global safety boundary drifted")

    source_tasks = catalog.get("tasks", [])
    source_by_id = {
        item["task_id"]: item for item in source_tasks if isinstance(item, dict) and isinstance(item.get("task_id"), str)
    }
    results = document.get("tasks")
    if not isinstance(results, list):
        _error(errors, TASK_RESULTS.as_posix(), "tasks must be an array")
        return {"implementation": collections.Counter(), "execution": collections.Counter(), "evidence": collections.Counter()}
    ids = [item.get("task_id") for item in results if isinstance(item, dict)]
    if ids != [item.get("task_id") for item in source_tasks]:
        _error(errors, TASK_RESULTS.as_posix(), "task IDs must exactly match source order and completeness")

    counts = {
        "implementation": collections.Counter(),
        "execution": collections.Counter(),
        "evidence": collections.Counter(),
    }
    for index, result in enumerate(results):
        location = f"{TASK_RESULTS.as_posix()}.tasks[{index}]"
        if not isinstance(result, dict):
            _error(errors, location, "task result must be an object")
            continue
        source = source_by_id.get(result.get("task_id"), {})
        for field in ("skill_id", "skill_name", "priority", "gate"):
            if result.get(field) != source.get(field):
                _error(errors, location, f"{field} does not match source task")
        implementation = result.get("implementation_state")
        execution = result.get("execution_state")
        evidence = result.get("evidence_state")
        if implementation not in IMPLEMENTATION_STATES:
            _error(errors, location, f"invalid implementation_state: {implementation!r}")
        else:
            counts["implementation"][implementation] += 1
        if execution not in EXECUTION_STATES:
            _error(errors, location, f"invalid execution_state: {execution!r}")
        else:
            counts["execution"][execution] += 1
        if evidence not in EVIDENCE_STATES:
            _error(errors, location, f"invalid evidence_state: {evidence!r}")
        else:
            counts["evidence"][evidence] += 1

        bindings = result.get("implementation_bindings")
        paths = _validate_bindings(root, bindings, f"{location}.implementation_bindings", errors)
        blockers = result.get("blockers")
        if not isinstance(blockers, list) or any(not isinstance(item, str) or not item for item in blockers):
            _error(errors, location, "blockers must be an array of non-empty strings")
            blockers = []
        if implementation == "NOT_STARTED" and paths:
            _error(errors, location, "NOT_STARTED task cannot claim implementation bindings")
        if implementation in {"PARTIAL", "IMPLEMENTED"} and not paths:
            _error(errors, location, f"{implementation} task requires content-bound implementation bindings")
        if implementation in {"PARTIAL", "BLOCKED"} and not blockers:
            _error(errors, location, f"{implementation} task requires explicit blockers")
        if implementation == "IMPLEMENTED" and blockers:
            _error(errors, location, "IMPLEMENTED task cannot retain implementation blockers")

        receipts = result.get("result_receipts")
        if not isinstance(receipts, list):
            _error(errors, location, "result_receipts must be an array")
            receipts = []
        if execution == "NOT_RUN":
            if evidence != "NONE" or receipts:
                _error(errors, location, "NOT_RUN task must have evidence_state NONE and no receipts")
        else:
            if evidence == "NONE" or not receipts:
                _error(errors, location, "executed task requires a non-NONE evidence state and receipts")
            for receipt_index, receipt in enumerate(receipts):
                _validate_receipt(
                    root,
                    receipt,
                    str(evidence),
                    str(execution),
                    f"{location}.result_receipts[{receipt_index}]",
                    errors,
                )
        if execution == "PASS":
            if implementation != "IMPLEMENTED":
                _error(errors, location, "PASS requires implementation_state IMPLEMENTED")
            if blockers:
                _error(errors, location, "PASS task cannot retain blockers")

    expected_summary = {
        "total": EXPECTED_TASK_COUNT,
        "implementation": dict(sorted(counts["implementation"].items())),
        "execution": dict(sorted(counts["execution"].items())),
        "evidence": dict(sorted(counts["evidence"].items())),
    }
    if document.get("summary") != expected_summary:
        _error(errors, TASK_RESULTS.as_posix(), "summary is not the exact derived task-state count")
    if len(results) != EXPECTED_TASK_COUNT:
        _error(errors, TASK_RESULTS.as_posix(), "repository results must contain exactly 144 tasks")
    return counts


def _validate_reconciliation(root: Path, source: dict[str, Any], errors: list[str]) -> collections.Counter[str]:
    document = _load_json(root, RECONCILIATION_REGISTER, errors)
    _validate_package_identity(document, RECONCILIATION_REGISTER.as_posix(), errors)
    if document.get("source_risk_register") != {
        "path": SOURCE_RISK_REGISTER.as_posix(),
        "sha256": _file_sha256(root / SOURCE_RISK_REGISTER),
    }:
        _error(errors, RECONCILIATION_REGISTER.as_posix(), "source risk binding is stale or invalid")
    if (
        document.get("direct_source_adoption_status") != "NOT_APPLIED"
        or document.get("source_adoption_gate") != "BLOCKED"
        or document.get("external_evidence_status") != "NOT_RUN"
        or document.get("production_certification") != "NOT_CERTIFIED"
    ):
        _error(errors, RECONCILIATION_REGISTER.as_posix(), "reconciliation safety boundary drifted")
    source_findings = source.get("findings", [])
    entries = document.get("findings")
    if not isinstance(entries, list):
        _error(errors, RECONCILIATION_REGISTER.as_posix(), "findings must be an array")
        return collections.Counter()
    if [item.get("finding_id") for item in entries if isinstance(item, dict)] != [
        item.get("id") for item in source_findings
    ]:
        _error(errors, RECONCILIATION_REGISTER.as_posix(), "finding IDs must exactly match source order and completeness")
    counts: collections.Counter[str] = collections.Counter()
    for index, entry in enumerate(entries):
        location = f"{RECONCILIATION_REGISTER.as_posix()}.findings[{index}]"
        if not isinstance(entry, dict):
            _error(errors, location, "finding result must be an object")
            continue
        source_item = source_findings[index] if index < len(source_findings) else {}
        if entry.get("finding_id") != source_item.get("id") or entry.get("severity") != source_item.get("severity") or entry.get("source_status") != "OPEN":
            _error(errors, location, "source finding identity/status drifted")
        state = entry.get("repository_resolution_state")
        if state not in RECONCILIATION_STATES:
            _error(errors, location, f"invalid repository_resolution_state: {state!r}")
        else:
            counts[state] += 1
        paths = _validate_bindings(root, entry.get("implementation_bindings"), f"{location}.implementation_bindings", errors)
        blockers = entry.get("blockers")
        if not isinstance(blockers, list) or any(not isinstance(item, str) or not item for item in blockers):
            _error(errors, location, "blockers must be an array of non-empty strings")
            blockers = []
        receipts = entry.get("evidence_receipts")
        if not isinstance(receipts, list):
            _error(errors, location, "evidence_receipts must be an array")
            receipts = []
        evidence = entry.get("evidence_state")
        if evidence not in EVIDENCE_STATES:
            _error(errors, location, f"invalid evidence_state: {evidence!r}")
        if state == "NOT_EVALUATED":
            if paths or receipts or evidence != "NONE" or not blockers:
                _error(errors, location, "NOT_EVALUATED requires no bindings/receipts, evidence NONE, and a blocker")
        elif state == "PARTIAL":
            if not paths or not blockers or evidence != "NONE" or receipts:
                _error(errors, location, "PARTIAL requires bindings and blockers but no execution evidence")
        elif state == "BLOCKED" and not blockers:
            _error(errors, location, "BLOCKED resolution requires blockers")
        elif state == "MITIGATED_LOCAL":
            if not paths or blockers or evidence == "NONE" or not receipts:
                _error(errors, location, "MITIGATED_LOCAL requires bindings, receipts, evidence, and no blockers")
            for receipt_index, receipt in enumerate(receipts):
                _validate_receipt(root, receipt, str(evidence), "PASS", f"{location}.evidence_receipts[{receipt_index}]", errors)
    expected_summary = {"total": EXPECTED_FINDING_COUNT, **dict(sorted(counts.items()))}
    if document.get("summary") != expected_summary:
        _error(errors, RECONCILIATION_REGISTER.as_posix(), "summary is not the exact derived finding count")
    if len(entries) != EXPECTED_FINDING_COUNT:
        _error(errors, RECONCILIATION_REGISTER.as_posix(), "reconciliation register must contain 11 findings")
    return counts


def _validate_dependencies(root: Path, compiled: dict[str, Any], errors: list[str]) -> collections.Counter[str]:
    document = _load_json(root, DEPENDENCY_BINDINGS, errors)
    _validate_package_identity(document, DEPENDENCY_BINDINGS.as_posix(), errors)
    if document.get("source_compiled_manifest") != {
        "path": COMPILED_MANIFEST.as_posix(),
        "sha256": _file_sha256(root / COMPILED_MANIFEST),
    }:
        _error(errors, DEPENDENCY_BINDINGS.as_posix(), "compiled manifest binding is stale or invalid")
    if (
        document.get("source_external_dependency_status") != "DECLARED_UNRESOLVED"
        or document.get("external_evidence_status") != "NOT_RUN"
        or document.get("production_certification") != "NOT_CERTIFIED"
    ):
        _error(errors, DEPENDENCY_BINDINGS.as_posix(), "dependency safety boundary drifted")
    source = compiled.get("external_dependencies", [])
    source_names = [item.get("name") for item in source if isinstance(item, dict)]
    entries = document.get("dependencies")
    if not isinstance(entries, list):
        _error(errors, DEPENDENCY_BINDINGS.as_posix(), "dependencies must be an array")
        return collections.Counter()
    if [item.get("name") for item in entries if isinstance(item, dict)] != source_names:
        _error(errors, DEPENDENCY_BINDINGS.as_posix(), "dependency names must exactly match source order and completeness")
    counts: collections.Counter[str] = collections.Counter()
    for index, entry in enumerate(entries):
        location = f"{DEPENDENCY_BINDINGS.as_posix()}.dependencies[{index}]"
        if not isinstance(entry, dict):
            _error(errors, location, "dependency binding must be an object")
            continue
        if entry.get("source_status") != "DECLARED_UNRESOLVED":
            _error(errors, location, "source_status must remain DECLARED_UNRESOLVED")
        state = entry.get("binding_state")
        if state not in DEPENDENCY_STATES:
            _error(errors, location, f"invalid binding_state: {state!r}")
        else:
            counts[state] += 1
        paths = _validate_bindings(root, entry.get("implementation_bindings"), f"{location}.implementation_bindings", errors)
        blockers = entry.get("blockers")
        if not isinstance(blockers, list) or any(not isinstance(item, str) or not item for item in blockers):
            _error(errors, location, "blockers must be an array of non-empty strings")
            blockers = []
        receipts = entry.get("resolution_receipts")
        if not isinstance(receipts, list):
            _error(errors, location, "resolution_receipts must be an array")
            receipts = []
        evidence = entry.get("evidence_state")
        if evidence not in EVIDENCE_STATES:
            _error(errors, location, f"invalid evidence_state: {evidence!r}")
        if state == "UNRESOLVED":
            if paths or receipts or evidence != "NONE" or not blockers:
                _error(errors, location, "UNRESOLVED requires no bindings/receipts, evidence NONE, and blockers")
        elif state == "CANDIDATE":
            if not paths or not blockers or receipts or evidence != "NONE":
                _error(errors, location, "CANDIDATE requires bindings and blockers but no resolution evidence")
        elif state in {"RESOLVED_LOCAL", "EXTERNAL_VERIFIED"}:
            required_paths = {
                f".agents/skills/{entry.get('name')}/SKILL.md",
                f"agent-skills/runtime/{entry.get('name')}/SKILL.md",
            }
            if not required_paths.issubset(set(paths)):
                _error(errors, location, "resolved dependency requires both exact installed Skill interfaces")
            if blockers or evidence == "NONE" or not receipts:
                _error(errors, location, "resolved dependency requires receipts/evidence and no blockers")
            if state == "EXTERNAL_VERIFIED" and evidence != "EXTERNAL_INDEPENDENT":
                _error(errors, location, "EXTERNAL_VERIFIED requires EXTERNAL_INDEPENDENT evidence")
            for receipt_index, receipt in enumerate(receipts):
                _validate_receipt(root, receipt, str(evidence), "PASS", f"{location}.resolution_receipts[{receipt_index}]", errors)
    expected_summary = {"total": 4, **dict(sorted(counts.items()))}
    if document.get("summary") != expected_summary:
        _error(errors, DEPENDENCY_BINDINGS.as_posix(), "summary is not the exact derived dependency count")
    if len(entries) != 4:
        _error(errors, DEPENDENCY_BINDINGS.as_posix(), "dependency register must contain exactly four entries")
    return counts


def validate_repository(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    errors: list[str] = []
    catalog, source_risks, compiled = _validate_source_boundaries(root, errors)
    task_counts = _validate_task_results(root, catalog, errors)
    risk_counts = _validate_reconciliation(root, source_risks, errors)
    dependency_counts = _validate_dependencies(root, compiled, errors)
    return {
        "status": "PASS" if not errors else "FAIL",
        "task_count": sum(task_counts["execution"].values()),
        "task_execution": dict(sorted(task_counts["execution"].items())),
        "source_findings": dict(sorted(risk_counts.items())),
        "external_dependencies": dict(sorted(dependency_counts.items())),
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = validate_repository(args.repo_root)
    except (OSError, TypeError, ValueError) as exc:
        result = {
            "status": "FAIL",
            "task_count": 0,
            "task_execution": {},
            "source_findings": {},
            "external_dependencies": {},
            "external_evidence_status": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
            "errors": [f"validator failed closed: {exc}"],
        }
    stream = sys.stdout if result["status"] == "PASS" else sys.stderr
    print(json.dumps(result, sort_keys=True), file=stream)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
