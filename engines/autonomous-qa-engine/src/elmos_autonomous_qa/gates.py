"""Conservative autonomous-QA quality, repair, impact, and ETA gates.

All unknown or incomplete evidence is blocking.  This local evaluator can
prepare an external review, but it cannot issue a certification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .canonical import normalize_relative_path
from .contracts import ContractError, digest_json, require_resource_id, require_text


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ResultStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    FLAKY = "FLAKY"
    FLAKY_CONFIRMED = "FLAKY_CONFIRMED"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"
    SKIPPED = "SKIPPED"


class RunMode(str, Enum):
    GENERATE = "generate"
    VERIFY = "verify"
    REPAIR = "repair"
    CERTIFY = "certify"
    CONTINUOUS = "continuous"


class Decision(str, Enum):
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    READY_FOR_EXTERNAL_GATE = "READY_FOR_EXTERNAL_GATE"


class FindingKind(str, Enum):
    FAILURE = "FAILURE"
    MISSING_OR_UNKNOWN = "MISSING_OR_UNKNOWN"


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    priority: Priority | str
    required: bool = True


@dataclass(frozen=True)
class TestObservation:
    test_id: str
    status: ResultStatus | str
    requirement_refs: tuple[str, ...] = ()
    risk_refs: tuple[str, ...] = ()
    materialized_ref: str | None = None
    build_status: ResultStatus | str = ResultStatus.UNKNOWN
    discovery_status: ResultStatus | str = ResultStatus.UNKNOWN
    required: bool = True


@dataclass(frozen=True)
class OutputEvidence:
    project_output_manifest_ref: str | None
    test_artifact_manifest_ref: str | None
    bundles: frozenset[str]
    materialized_artifact_refs: frozenset[str]
    all_artifacts_have_sha256: bool | None
    bundle_checksums_match: bool | None
    tamper_detected: bool | None
    test_targets_build: bool | None
    generated_tests_discoverable: bool | None
    replay_entrypoint_present: bool | None
    untracked_generated_files: bool | None
    secrets_detected: bool | None
    unsafe_symlink_detected: bool | None
    partial_output_available: bool | None = None


@dataclass(frozen=True)
class SecurityEvidence:
    unresolved_critical_findings: int | None
    unresolved_high_findings: int | None
    production_credentials_used: bool | None
    permissions_broadened: bool | None
    security_controls_disabled: bool | None
    direct_main_write: bool | None
    direct_production_write: bool | None


@dataclass(frozen=True)
class CertificationEvidence:
    project_manifest_signed: bool | None
    evidence_manifest_signed: bool | None
    signatures_valid: bool | None
    signer_trusted: bool | None
    evidence_digests_valid: bool | None
    authorization_valid: bool | None
    independent_corpus: bool | None
    independent_evidence: bool | None
    external_validation_completed: bool | None
    executor_id: str | None
    verifier_id: str | None
    signer_id: str | None


@dataclass(frozen=True)
class QualityGateInput:
    mode: RunMode | str
    requirements: tuple[Requirement, ...]
    tests: tuple[TestObservation, ...]
    output: OutputEvidence
    security: SecurityEvidence
    certification: CertificationEvidence
    run_succeeded: bool | None = None
    risk_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class GateFinding:
    code: str
    kind: FindingKind
    message: str


@dataclass(frozen=True)
class QualityGateReport:
    decision: Decision
    findings: tuple[GateFinding, ...]
    executable_coverage: Mapping[Priority, float]
    result_counts: Mapping[ResultStatus, int]
    certified: bool
    certification_boundary: str

    @property
    def ready_for_external_gate(self) -> bool:
        return self.decision is Decision.READY_FOR_EXTERNAL_GATE


class _Findings:
    def __init__(self) -> None:
        self.items: list[GateFinding] = []

    def fail(self, code: str, message: str) -> None:
        self.items.append(GateFinding(code, FindingKind.FAILURE, message))

    def block(self, code: str, message: str) -> None:
        self.items.append(GateFinding(code, FindingKind.MISSING_OR_UNKNOWN, message))

    def require_true(self, value: bool | None, code: str, message: str) -> None:
        if value is True:
            return
        if value is None:
            self.block(code, f"{message}: evidence is unknown")
        else:
            self.fail(code, message)

    def require_false(self, value: bool | None, code: str, message: str) -> None:
        if value is False:
            return
        if value is None:
            self.block(code, f"{message}: evidence is unknown")
        else:
            self.fail(code, message)


def _priority(value: Priority | str) -> Priority | None:
    try:
        return Priority(value)
    except (TypeError, ValueError):
        return None


def _status(value: ResultStatus | str) -> ResultStatus | None:
    try:
        return ResultStatus(value)
    except (TypeError, ValueError):
        return None


def _required_bundles(mode: RunMode) -> frozenset[str]:
    common = {"project-with-tests", "tests-only"}
    if mode is not RunMode.GENERATE:
        common.add("qa-evidence")
    if mode is RunMode.REPAIR:
        common.add("repair-patches")
    return frozenset(common)


def _evaluate_test_status(
    findings: _Findings,
    *,
    code_prefix: str,
    label: str,
    raw_status: ResultStatus | str,
) -> ResultStatus | None:
    status = _status(raw_status)
    if status is ResultStatus.PASSED:
        return status
    if status is ResultStatus.FAILED:
        findings.fail(f"{code_prefix}.failed", f"{label} failed")
    elif status in {
        ResultStatus.BLOCKED,
        ResultStatus.FLAKY,
        ResultStatus.FLAKY_CONFIRMED,
        ResultStatus.NOT_RUN,
        ResultStatus.UNKNOWN,
        ResultStatus.SKIPPED,
    }:
        findings.block(
            f"{code_prefix}.{status.value.lower()}",
            f"{label} has non-passing status {status.value}",
        )
    else:
        findings.block(f"{code_prefix}.unknown", f"{label} status is unrecognized")
    return status


def evaluate_quality_gate(request: QualityGateInput) -> QualityGateReport:
    findings = _Findings()
    try:
        mode = RunMode(request.mode)
    except (TypeError, ValueError):
        mode = RunMode.VERIFY
        findings.block("mode.unknown", f"unsupported run mode: {request.mode!r}")

    if not request.requirements:
        findings.block("traceability.no-requirements", "no requirements were supplied")
    if not request.tests:
        findings.block("execution.no-tests", "no executable tests were supplied")

    requirements: dict[str, Requirement] = {}
    requirement_priorities: dict[str, Priority] = {}
    for requirement in request.requirements:
        if not requirement.requirement_id:
            findings.fail("traceability.empty-requirement-id", "requirement id is empty")
            continue
        if requirement.requirement_id in requirements:
            findings.fail(
                "traceability.duplicate-requirement",
                f"duplicate requirement id: {requirement.requirement_id}",
            )
            continue
        requirements[requirement.requirement_id] = requirement
        priority = _priority(requirement.priority)
        if priority is None:
            findings.block(
                "traceability.unknown-priority",
                f"requirement {requirement.requirement_id} has unknown priority",
            )
        else:
            requirement_priorities[requirement.requirement_id] = priority

    seen_tests: set[str] = set()
    executable_requirements: set[str] = set()
    result_counts = {status: 0 for status in ResultStatus}
    p0_p1_test_statuses: list[ResultStatus | None] = []

    for test in request.tests:
        if not test.test_id:
            findings.fail("traceability.empty-test-id", "test id is empty")
        elif test.test_id in seen_tests:
            findings.fail("traceability.duplicate-test", f"duplicate test id: {test.test_id}")
        seen_tests.add(test.test_id)

        if not test.requirement_refs and not test.risk_refs:
            findings.fail(
                "traceability.orphan-test",
                f"test {test.test_id!r} has no requirement or risk reference",
            )
        unknown_refs = sorted(set(test.requirement_refs).difference(requirements))
        if unknown_refs:
            findings.fail(
                "traceability.unknown-reference",
                f"test {test.test_id!r} references unknown requirements {unknown_refs}",
            )
        unknown_risks = sorted(set(test.risk_refs).difference(request.risk_ids))
        if unknown_risks:
            findings.fail(
                "traceability.unknown-risk-reference",
                f"test {test.test_id!r} references unknown risks {unknown_risks}",
            )

        test_status = _evaluate_test_status(
            findings,
            code_prefix=f"execution.{test.test_id}.result",
            label=f"test {test.test_id!r}",
            raw_status=test.status,
        )
        if test_status is not None:
            result_counts[test_status] += 1

        build_status = _evaluate_test_status(
            findings,
            code_prefix=f"execution.{test.test_id}.build",
            label=f"test target {test.test_id!r} build",
            raw_status=test.build_status,
        )
        discovery_status = _evaluate_test_status(
            findings,
            code_prefix=f"execution.{test.test_id}.discovery",
            label=f"test {test.test_id!r} discovery",
            raw_status=test.discovery_status,
        )

        materialized = bool(test.materialized_ref)
        if not materialized:
            findings.block(
                "output.missing-materialized-ref",
                f"test {test.test_id!r} has no materialized artifact reference",
            )
        elif test.materialized_ref not in request.output.materialized_artifact_refs:
            findings.fail(
                "output.unmanifested-materialized-ref",
                f"test {test.test_id!r} artifact is absent from the output manifest",
            )

        executable = (
            materialized
            and build_status is ResultStatus.PASSED
            and discovery_status is ResultStatus.PASSED
        )
        if executable:
            executable_requirements.update(test.requirement_refs)

        mapped_priorities = {
            requirement_priorities[ref]
            for ref in test.requirement_refs
            if ref in requirement_priorities
        }
        if Priority.P0 in mapped_priorities or Priority.P1 in mapped_priorities:
            p0_p1_test_statuses.append(test_status)

    if any(status is not ResultStatus.PASSED for status in p0_p1_test_statuses):
        findings.fail("correctness.p0-p1-pass-rate", "P0/P1 pass rate must be 100%")

    coverage: dict[Priority, float] = {}
    for priority in Priority:
        required_ids = {
            requirement_id
            for requirement_id, requirement in requirements.items()
            if requirement.required and requirement_priorities.get(requirement_id) is priority
        }
        covered = required_ids.intersection(executable_requirements)
        ratio = len(covered) / len(required_ids) if required_ids else 1.0
        coverage[priority] = ratio
        threshold = 1.0 if priority in {Priority.P0, Priority.P1} else 0.98 if priority is Priority.P2 else 0.0
        if ratio < threshold:
            findings.fail(
                f"traceability.{priority.value.lower()}-coverage",
                f"{priority.value} executable coverage {ratio:.3f} is below {threshold:.3f}",
            )

    output = request.output
    if not output.project_output_manifest_ref:
        findings.block("output.project-manifest", "project output manifest is missing")
    if not output.test_artifact_manifest_ref:
        findings.block("output.test-artifact-manifest", "test artifact manifest is missing")
    missing_bundles = sorted(_required_bundles(mode).difference(output.bundles))
    if missing_bundles:
        findings.block("output.required-bundles", f"required bundles are missing: {missing_bundles}")
    findings.require_true(
        output.all_artifacts_have_sha256,
        "output.sha256",
        "every artifact must have a SHA-256 digest",
    )
    findings.require_true(
        output.bundle_checksums_match,
        "output.bundle-checksums",
        "bundle checksums must match",
    )
    findings.require_false(output.tamper_detected, "output.tamper", "tamper evidence was detected")
    findings.require_true(output.test_targets_build, "output.targets-build", "test targets must build")
    findings.require_true(
        output.generated_tests_discoverable,
        "output.tests-discoverable",
        "generated tests must be discoverable",
    )
    findings.require_true(
        output.replay_entrypoint_present,
        "output.replay-entrypoint",
        "a replay entrypoint is required",
    )
    findings.require_false(
        output.untracked_generated_files,
        "output.untracked-files",
        "generated files may not be left untracked",
    )
    findings.require_false(output.secrets_detected, "output.secrets", "output contains secrets")
    findings.require_false(
        output.unsafe_symlink_detected,
        "output.unsafe-symlink",
        "output contains an unsafe symlink",
    )
    if request.run_succeeded is not True:
        findings.require_true(
            output.partial_output_available,
            "output.partial-on-failure",
            "failed or incomplete runs must retain partial output",
        )
        if request.run_succeeded is None:
            findings.block("execution.run-outcome", "run outcome is unknown")
        else:
            findings.fail("execution.run-failed", "the QA run did not succeed")

    security = request.security
    for label, count in (
        ("critical", security.unresolved_critical_findings),
        ("high", security.unresolved_high_findings),
    ):
        if count is None:
            findings.block(f"security.{label}-findings", f"{label} finding count is unknown")
        elif not isinstance(count, int) or isinstance(count, bool) or count < 0:
            findings.fail(f"security.{label}-findings", f"{label} finding count is invalid")
        elif count != 0:
            findings.fail(
                f"security.{label}-findings",
                f"{count} unresolved {label} security findings remain",
            )
    findings.require_false(
        security.production_credentials_used,
        "security.production-credentials",
        "production credentials were used by test workers",
    )
    findings.require_false(
        security.permissions_broadened,
        "security.permissions-broadened",
        "permissions were broadened",
    )
    findings.require_false(
        security.security_controls_disabled,
        "security.controls-disabled",
        "security controls were disabled",
    )
    findings.require_false(
        security.direct_main_write,
        "security.direct-main-write",
        "direct main-branch writes are forbidden",
    )
    findings.require_false(
        security.direct_production_write,
        "security.direct-production-write",
        "direct production writes are forbidden",
    )

    certification = request.certification
    findings.require_true(
        certification.project_manifest_signed,
        "certification.project-signature",
        "project output manifest signature is required",
    )
    findings.require_true(
        certification.evidence_manifest_signed,
        "certification.evidence-signature",
        "evidence manifest signature is required",
    )
    findings.require_true(
        certification.signatures_valid,
        "certification.signature-validity",
        "all signatures must validate",
    )
    findings.require_true(
        certification.signer_trusted,
        "certification.signer-trust",
        "the signer must resolve in a non-revoked trust store",
    )
    findings.require_true(
        certification.evidence_digests_valid,
        "certification.evidence-digests",
        "evidence byte counts and digests must validate",
    )
    findings.require_true(
        certification.authorization_valid,
        "certification.authorization",
        "scoped authorization must be valid",
    )
    findings.require_true(
        certification.independent_corpus,
        "certification.independent-corpus",
        "an independent corpus is required",
    )
    findings.require_true(
        certification.independent_evidence,
        "certification.independent-evidence",
        "independently collected evidence is required",
    )
    findings.require_true(
        certification.external_validation_completed,
        "certification.external-validation",
        "external validation evidence is required",
    )
    if not certification.executor_id:
        findings.block("certification.executor", "executor identity is missing")
    if not certification.verifier_id:
        findings.block("certification.verifier", "verifier identity is missing")
    if not certification.signer_id:
        findings.block("certification.signer", "signer identity is missing")
    if (
        certification.executor_id
        and certification.verifier_id
        and certification.executor_id == certification.verifier_id
    ):
        findings.fail(
            "certification.executor-verifier-separation",
            "executor and verifier must be different identities",
        )

    items = tuple(findings.items)
    if any(item.kind is FindingKind.FAILURE for item in items):
        decision = Decision.FAILED
    elif items:
        decision = Decision.BLOCKED
    else:
        decision = Decision.READY_FOR_EXTERNAL_GATE

    return QualityGateReport(
        decision=decision,
        findings=items,
        executable_coverage=MappingProxyType(coverage),
        result_counts=MappingProxyType(result_counts),
        certified=False,
        certification_boundary=(
            "Local evaluation never certifies; an authorized independent external "
            "authority must validate the signed evidence and issue any certificate."
        ),
    )


class RepairRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class RepairDiff:
    path: str
    risk: RepairRisk | str
    product_code_changed: bool = False
    deleted_test: bool = False
    weakened_assertion: bool = False
    reduced_coverage: bool = False
    broadened_permission: bool = False
    disabled_security_control: bool = False
    production_write: bool = False
    direct_main_write: bool = False
    destructive_migration: bool = False
    modified_holdout_or_oracle: bool = False


@dataclass(frozen=True)
class RepairAssessment:
    allowed: bool
    findings: tuple[GateFinding, ...]
    maximum_risk: RepairRisk | None


_RISK_ORDER = {
    RepairRisk.LOW: 0,
    RepairRisk.MEDIUM: 1,
    RepairRisk.HIGH: 2,
    RepairRisk.CRITICAL: 3,
}


def _safe_repository_path(path: str) -> bool:
    try:
        return normalize_relative_path(path) == path
    except (TypeError, ValueError):
        return False


def assess_repair(
    diffs: Sequence[RepairDiff],
    *,
    approval_ref: str | None,
    approver_id: str | None,
    executor_id: str | None,
    full_regression_status: ResultStatus | str,
    tests_rematerialized: bool | None,
    lineage_updated: bool | None,
    trusted_receipt_valid: bool | None = None,
) -> RepairAssessment:
    findings = _Findings()
    risks: list[RepairRisk] = []
    product_changed = False
    if not diffs:
        findings.block("repair.empty-diff", "repair assessment requires at least one diff")
    for diff in diffs:
        if not _safe_repository_path(diff.path):
            findings.fail("repair.path", f"unsafe repair path: {diff.path!r}")
        try:
            risk = RepairRisk(diff.risk)
        except (TypeError, ValueError):
            findings.block("repair.risk", f"unknown repair risk for {diff.path!r}")
            risk = RepairRisk.CRITICAL
        risks.append(risk)
        product_changed = product_changed or diff.product_code_changed
        forbidden = {
            "deleted-test": diff.deleted_test,
            "weakened-assertion": diff.weakened_assertion,
            "reduced-coverage": diff.reduced_coverage,
            "broadened-permission": diff.broadened_permission,
            "disabled-security-control": diff.disabled_security_control,
            "production-write": diff.production_write,
            "direct-main-write": diff.direct_main_write,
            "destructive-migration": diff.destructive_migration,
            "modified-holdout-or-oracle": diff.modified_holdout_or_oracle,
        }
        for name, present in forbidden.items():
            if present:
                findings.fail(
                    f"repair.forbidden-{name}",
                    f"repair diff {diff.path!r} contains forbidden change {name}",
                )

    maximum_risk = max(risks, key=_RISK_ORDER.get) if risks else None
    if maximum_risk in {RepairRisk.HIGH, RepairRisk.CRITICAL}:
        if not approval_ref or not approver_id or not executor_id:
            findings.block(
                "repair.approval",
                "high-risk repair requires explicit approval and attributable identities",
            )
        elif executor_id == approver_id:
            findings.fail("repair.separation", "repair executor may not self-approve")
    if product_changed:
        _evaluate_test_status(
            findings,
            code_prefix="repair.full-regression",
            label="full regression after product repair",
            raw_status=full_regression_status,
        )
        findings.require_true(
            tests_rematerialized,
            "repair.rematerialization",
            "changed tests must be rematerialized",
        )
        findings.require_true(
            lineage_updated,
            "repair.lineage",
            "repair artifact lineage must be updated",
        )
    findings.require_true(
        trusted_receipt_valid,
        "repair.trusted-receipt",
        "a digest-bound authorization and execution receipt is required",
    )
    return RepairAssessment(not findings.items, tuple(findings.items), maximum_risk)


@dataclass(frozen=True)
class EtaEstimate:
    state: str
    completed_units: int
    total_units: int
    throughput_per_second: float | None
    remaining_seconds: float | None
    confidence: str


def estimate_eta(
    *,
    completed_units: int,
    total_units: int,
    elapsed_seconds: float,
    recent_unit_durations: Iterable[float] = (),
) -> EtaEstimate:
    if total_units < 0 or completed_units < 0 or completed_units > total_units:
        raise ValueError("unit counts are inconsistent")
    if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
        raise ValueError("elapsed_seconds must be finite and non-negative")
    durations = tuple(recent_unit_durations)
    if any(not math.isfinite(duration) or duration <= 0 for duration in durations):
        raise ValueError("recent unit durations must be finite and positive")
    if completed_units == total_units:
        return EtaEstimate("COMPLETE", completed_units, total_units, None, 0.0, "HIGH")
    if completed_units == 0 or elapsed_seconds == 0:
        return EtaEstimate("UNKNOWN", completed_units, total_units, None, None, "NONE")
    historical_rate = completed_units / elapsed_seconds
    try:
        duration_total = math.fsum(durations)
    except OverflowError as exc:
        raise ValueError("recent unit duration total is outside the finite range") from exc
    if durations and (not math.isfinite(duration_total) or duration_total <= 0):
        raise ValueError("recent unit duration total must be finite and positive")
    recent_rate = len(durations) / duration_total if durations else historical_rate
    rate = min(historical_rate, recent_rate)
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("ETA throughput must be finite and positive")
    remaining = (total_units - completed_units) / rate
    if not math.isfinite(remaining):
        raise ValueError("ETA remaining duration is outside the finite range")
    confidence = "HIGH" if len(durations) >= 10 else "MEDIUM" if len(durations) >= 3 else "LOW"
    return EtaEstimate("ESTIMATED", completed_units, total_units, rate, remaining, confidence)


@dataclass(frozen=True)
class ImpactAssessment:
    impacted_tests: tuple[str, ...]
    unknown_paths: tuple[str, ...]
    full_regression_required: bool


def analyze_impact(
    changed_paths: Iterable[str],
    *,
    exact_path_to_tests: Mapping[str, Sequence[str]],
    all_tests: Iterable[str],
) -> ImpactAssessment:
    all_known_tests = tuple(sorted(set(all_tests)))
    impacted: set[str] = set()
    unknown: list[str] = []
    for path in sorted(set(changed_paths)):
        if not _safe_repository_path(path):
            unknown.append(path)
            continue
        mapped = exact_path_to_tests.get(path)
        if not mapped:
            unknown.append(path)
            continue
        mapped_set = set(mapped)
        if not mapped_set.issubset(all_known_tests):
            unknown.append(path)
            continue
        impacted.update(mapped_set)
    if unknown:
        return ImpactAssessment(all_known_tests, tuple(unknown), True)
    return ImpactAssessment(tuple(sorted(impacted)), (), False)


def analyze_impact_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    changed = inputs.get("changed_paths")
    all_tests = inputs.get("all_tests")
    raw_mapping = inputs.get("exact_path_to_tests")
    product_code_changed = inputs.get("product_code_changed", False)
    if not isinstance(changed, list) or any(not isinstance(item, str) for item in changed):
        raise ContractError("changed_paths must be a string array")
    if not isinstance(all_tests, list) or any(not isinstance(item, str) for item in all_tests):
        raise ContractError("all_tests must be a string array")
    if not isinstance(raw_mapping, Mapping) or any(
        not isinstance(path, str)
        or not isinstance(tests, list)
        or any(not isinstance(test, str) for test in tests)
        for path, tests in raw_mapping.items()
    ):
        raise ContractError("exact_path_to_tests must map paths to string arrays")
    if not isinstance(product_code_changed, bool):
        raise ContractError("product_code_changed must be boolean")
    if len(set(changed)) != len(changed) or len(set(all_tests)) != len(all_tests):
        raise ContractError("changed_paths and all_tests may not contain duplicates")
    if any(
        len(set(tests)) != len(tests)
        for tests in raw_mapping.values()
    ):
        raise ContractError("exact_path_to_tests values may not contain duplicates")
    for test_id in all_tests:
        require_resource_id(test_id, "all_tests[]")
    for tests in raw_mapping.values():
        for test_id in tests:
            require_resource_id(test_id, "exact_path_to_tests[]")
    report = analyze_impact(
        changed,
        exact_path_to_tests={path: tuple(tests) for path, tests in raw_mapping.items()},
        all_tests=all_tests,
    )
    if product_code_changed:
        report = ImpactAssessment(tuple(sorted(set(all_tests))), report.unknown_paths, True)
    outputs = {
        "impacted_tests": list(report.impacted_tests),
        "unknown_paths": list(report.unknown_paths),
        "full_regression_required": report.full_regression_required,
        "caller_confidence_accepted": False,
    }
    outputs["report_digest"] = digest_json(outputs)
    return {
        "state": "PARTIAL" if report.full_regression_required else "SUCCEEDED",
        "code": "FULL_REGRESSION_REQUIRED"
        if report.full_regression_required
        else "EXACT_IMPACT_SCOPE_SELECTED",
        "outputs": outputs,
    }


def estimate_eta_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    completed = inputs.get("completed_units")
    total = inputs.get("total_units")
    elapsed = inputs.get("elapsed_seconds")
    durations = inputs.get("recent_unit_durations", [])
    if (
        not isinstance(completed, int)
        or isinstance(completed, bool)
        or not isinstance(total, int)
        or isinstance(total, bool)
        or not isinstance(elapsed, (int, float))
        or isinstance(elapsed, bool)
        or not isinstance(durations, list)
        or any(
            not isinstance(item, (int, float)) or isinstance(item, bool)
            for item in durations
        )
    ):
        raise ContractError("ETA inputs must use exact numeric types")
    try:
        estimate = estimate_eta(
            completed_units=completed,
            total_units=total,
            elapsed_seconds=float(elapsed),
            recent_unit_durations=(float(item) for item in durations),
        )
    except (OverflowError, ValueError) as exc:
        raise ContractError(str(exc)) from exc
    return {
        "state": "PARTIAL" if estimate.state == "UNKNOWN" else "SUCCEEDED",
        "code": "ETA_" + estimate.state,
        "outputs": {
            "completed_units": estimate.completed_units,
            "total_units": estimate.total_units,
            "throughput_per_second": estimate.throughput_per_second,
            "remaining_seconds": estimate.remaining_seconds,
            "confidence": estimate.confidence,
            "human_equivalent_time_inferred": False,
        },
    }


def evaluate_quality_gate_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Parse strict JSON input and expose the conservative gate as a Skill result."""

    def objects(value: Any, field: str) -> list[Mapping[str, Any]]:
        if not isinstance(value, list) or not value or any(
            not isinstance(item, Mapping) for item in value
        ):
            raise ContractError(f"{field} must be a non-empty object array")
        return list(value)

    def object_value(value: Any, field: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise ContractError(f"{field} must be an object")
        return value

    def strings(value: Any, field: str) -> tuple[str, ...]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ContractError(f"{field} must be a string array")
        if len(set(value)) != len(value):
            raise ContractError(f"{field} may not contain duplicates")
        return tuple(value)

    def required_string(value: Any, field: str) -> str:
        return require_text(value, field, maximum=512)

    def optional_string(value: Any, field: str) -> str | None:
        if value is None:
            return None
        return required_string(value, field)

    def optional_boolean(value: Any, field: str) -> bool | None:
        if value is None or isinstance(value, bool):
            return value
        raise ContractError(f"{field} must be boolean when supplied")

    def optional_count(value: Any, field: str) -> int | None:
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise ContractError(f"{field} must be an integer when supplied")
        return value

    requirements = tuple(
        Requirement(
            requirement_id=require_resource_id(
                item.get("requirement_id"), "requirement.requirement_id"
            ),
            priority=required_string(item.get("priority"), "requirement.priority"),
            required=item.get("required", True),
        )
        for item in objects(inputs.get("requirements"), "requirements")
    )
    if any(not isinstance(item.required, bool) for item in requirements):
        raise ContractError("requirement.required must be boolean")
    tests = tuple(
        TestObservation(
            test_id=require_resource_id(
                item.get("test_id", item.get("test_case_id")), "test.test_id"
            ),
            status=required_string(item.get("status"), "test.status"),
            requirement_refs=strings(item.get("requirement_refs", []), "requirement_refs"),
            risk_refs=strings(item.get("risk_refs", []), "risk_refs"),
            materialized_ref=optional_string(
                item.get("materialized_ref"), "test.materialized_ref"
            ),
            build_status=required_string(
                item.get("build_status", "UNKNOWN"), "test.build_status"
            ),
            discovery_status=required_string(
                item.get("discovery_status", "UNKNOWN"), "test.discovery_status"
            ),
            required=item.get("required", True),
        )
        for item in objects(inputs.get("tests"), "tests")
    )
    if any(not isinstance(item.required, bool) for item in tests):
        raise ContractError("test.required must be boolean")
    output = object_value(inputs.get("output"), "output")
    security = object_value(inputs.get("security"), "security")
    certification = object_value(inputs.get("certification", {}), "certification")
    bundles = strings(output.get("bundles", []), "output.bundles")
    materialized = strings(
        output.get("materialized_artifact_refs", []),
        "output.materialized_artifact_refs",
    )
    risk_ids = strings(inputs.get("risk_ids", []), "risk_ids")
    for risk_id in risk_ids:
        require_resource_id(risk_id, "risk_ids[]")
    request = QualityGateInput(
        mode=required_string(inputs.get("mode", "verify"), "mode"),
        requirements=requirements,
        tests=tests,
        output=OutputEvidence(
            project_output_manifest_ref=optional_string(
                output.get("project_output_manifest_ref"),
                "output.project_output_manifest_ref",
            ),
            test_artifact_manifest_ref=optional_string(
                output.get("test_artifact_manifest_ref"),
                "output.test_artifact_manifest_ref",
            ),
            bundles=frozenset(bundles),
            materialized_artifact_refs=frozenset(materialized),
            all_artifacts_have_sha256=optional_boolean(output.get("all_artifacts_have_sha256"), "output.all_artifacts_have_sha256"),
            bundle_checksums_match=optional_boolean(output.get("bundle_checksums_match"), "output.bundle_checksums_match"),
            tamper_detected=optional_boolean(output.get("tamper_detected"), "output.tamper_detected"),
            test_targets_build=optional_boolean(output.get("test_targets_build"), "output.test_targets_build"),
            generated_tests_discoverable=optional_boolean(output.get("generated_tests_discoverable"), "output.generated_tests_discoverable"),
            replay_entrypoint_present=optional_boolean(output.get("replay_entrypoint_present"), "output.replay_entrypoint_present"),
            untracked_generated_files=optional_boolean(output.get("untracked_generated_files"), "output.untracked_generated_files"),
            secrets_detected=optional_boolean(output.get("secrets_detected"), "output.secrets_detected"),
            unsafe_symlink_detected=optional_boolean(output.get("unsafe_symlink_detected"), "output.unsafe_symlink_detected"),
            partial_output_available=optional_boolean(output.get("partial_output_available"), "output.partial_output_available"),
        ),
        security=SecurityEvidence(
            unresolved_critical_findings=optional_count(security.get("unresolved_critical_findings"), "security.unresolved_critical_findings"),
            unresolved_high_findings=optional_count(security.get("unresolved_high_findings"), "security.unresolved_high_findings"),
            production_credentials_used=optional_boolean(security.get("production_credentials_used"), "security.production_credentials_used"),
            permissions_broadened=optional_boolean(security.get("permissions_broadened"), "security.permissions_broadened"),
            security_controls_disabled=optional_boolean(security.get("security_controls_disabled"), "security.security_controls_disabled"),
            direct_main_write=optional_boolean(security.get("direct_main_write"), "security.direct_main_write"),
            direct_production_write=optional_boolean(security.get("direct_production_write"), "security.direct_production_write"),
        ),
        certification=CertificationEvidence(
            project_manifest_signed=None,
            evidence_manifest_signed=None,
            signatures_valid=None,
            signer_trusted=None,
            evidence_digests_valid=None,
            authorization_valid=None,
            independent_corpus=None,
            independent_evidence=None,
            external_validation_completed=None,
            executor_id=None,
            verifier_id=None,
            signer_id=None,
        ),
        run_succeeded=optional_boolean(inputs.get("run_succeeded"), "run_succeeded"),
        risk_ids=frozenset(risk_ids),
    )
    report = evaluate_quality_gate(request)
    state = {
        Decision.FAILED: "FAILED",
        Decision.BLOCKED: "BLOCKED",
        Decision.READY_FOR_EXTERNAL_GATE: "SUCCEEDED",
    }[report.decision]
    gate_outputs = {
        "decision": report.decision.value,
        "findings": [
            {
                "code": finding.code,
                "kind": finding.kind.value,
                "message": finding.message,
            }
            for finding in report.findings
        ],
        "executable_coverage": {
            priority.value: value
            for priority, value in report.executable_coverage.items()
        },
        "result_counts": {
            status.value: value for status, value in report.result_counts.items()
        },
        "ready_for_external_gate": report.ready_for_external_gate,
        "certified": False,
        "caller_certification_assertions_accepted": False,
        "caller_certification_fields_observed": sorted(certification),
        "trusted_external_receipt": "NOT_RUN",
        "certification_boundary": report.certification_boundary,
    }
    gate_outputs["report_digest"] = digest_json(gate_outputs)
    return {
        "state": state,
        "code": "QUALITY_GATE_" + report.decision.value,
        "outputs": gate_outputs,
        "implementation_state": "LOCAL_VALIDATED",
    }
