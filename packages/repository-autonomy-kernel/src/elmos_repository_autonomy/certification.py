"""T00-T08 evidence matrix, E1-E5 aggregation and conservative P05 gate."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .adapters import ADAPTERS, CONFORMANCE_CASES
from .errors import AuthorizationError, ContractError
from .models import (
    canonical_json,
    digest,
    is_sha256_digest,
    require_mapping,
    require_sha256_digest,
    require_string,
    utc_now,
)
from .storage import DurableStore

LOCAL_CLASSES = frozenset({"LOCAL_ENGINEERING_VALIDATED", "EMULATOR_EXECUTED", "STATIC_VALIDATED"})
EXTERNAL_CLASSES = frozenset({"EXTERNAL_EXECUTED", "INDEPENDENTLY_VERIFIED"})
REAL_SOURCE_KINDS = frozenset({"real-runtime", "real-provider", "customer-repository", "independent-replay"})
LOCAL_SOURCE_KINDS = frozenset({"local-runtime", "repository-test", "static-validator", "emulator"})
RESULT_PRECEDENCE = {"FAIL": 0, "UNKNOWN": 1, "BLOCKED": 2, "NOT_RUN": 3, "PASS": 4}


@dataclass(frozen=True, slots=True)
class TestCaseSpec:
    case_id: str
    suite_id: str
    capability: str
    level: str
    external_required: bool
    independent_required: bool
    zero_tolerance: bool = False


@dataclass(frozen=True, slots=True)
class TrustAnchor:
    key: bytes
    subject_id: str
    allowed_source_kinds: frozenset[str] = REAL_SOURCE_KINDS
    revoked: bool = False
    not_after: str | None = None


def _suite(prefix: str, level: str, capability: str, names: Sequence[str], *, external: bool = True, zero_tolerance: bool = False) -> tuple[TestCaseSpec, ...]:
    return tuple(
        TestCaseSpec(
            case_id=f"{prefix}-{name}", suite_id=prefix, capability=capability, level=level,
            external_required=external, independent_required=external, zero_tolerance=zero_tolerance,
        )
        for name in names
    )


BASE_TEST_CASES = (
    *_suite("T00", "E1", "local-contract", ("01-package", "02-handlers", "03-state", "04-idempotency", "05-tenant", "06-anti-fabrication"), external=False, zero_tolerance=True),
    *_suite("T01", "E2", "postgresql", ("01-migrations", "02-rls", "03-transaction-recovery", "04-backup-restore", "05-independent-replay"), zero_tolerance=True),
    *_suite("T02", "E3", "scm", ("01-exact-commit", "02-permissions", "03-submodule-lfs", "04-resume-reconcile", "05-write-rollback"), zero_tolerance=True),
    *_suite("T03", "E2", "object-store", ("01-put-readback", "02-signed-url", "03-encryption-isolation", "04-retention-gc", "05-fault-reconcile"), zero_tolerance=True),
    *_suite("T04", "E2", "event-bus", ("01-publish-consume", "02-duplicate-ordering", "03-dlq-replay", "04-unknown-confirm", "05-tenant-schema"), zero_tolerance=True),
    *_suite("T05", "E2", "secrets-broker", ("01-lease", "02-scope-negative", "03-sandbox-zero-secret", "04-revoke-rotate", "05-incident-reconcile"), zero_tolerance=True),
    *_suite("T07", "E4", "kubernetes", ("01-manifest-supply-chain", "02-rollout", "03-fault-injection", "04-backup-rollback", "05-security-cleanup"), zero_tolerance=True),
    *_suite("T08", "E3", "customer-golden-route", ("01-baseline", "02-digest-lineage", "03-holdout", "04-customer-acceptance", "05-cost-eta-slo"), zero_tolerance=True),
)

T06_TEST_CASES = tuple(
    TestCaseSpec(
        case_id=f"T06-{adapter_id}-{case}", suite_id="T06", capability=f"provider:{adapter_id}",
        level="E2", external_required=True, independent_required=True, zero_tolerance=True,
    )
    for adapter_id in ADAPTERS
    for case in CONFORMANCE_CASES
)

TEST_CASES = BASE_TEST_CASES + T06_TEST_CASES
TEST_CASE_BY_ID = {item.case_id: item for item in TEST_CASES}
SUITE_IDS = tuple(f"T{index:02d}" for index in range(9))
E_LEVEL_SUITES = {
    "E1": ("T00",),
    "E2": ("T01", "T03", "T04", "T05", "T06"),
    "E3": ("T02", "T08"),
    "E4": ("T05", "T07"),
    "E5": ("T08",),
}


class EvidenceTrustStore:
    """HMAC trust store for externally supplied verification receipts.

    The secret keys are configuration owned by the host process and are never
    persisted by this package.
    """

    def __init__(self, keys: Mapping[str, bytes | TrustAnchor]) -> None:
        self._keys = {
            key_id: value if isinstance(value, TrustAnchor) else TrustAnchor(key=value, subject_id=key_id)
            for key_id, value in keys.items()
        }

    @staticmethod
    def unsigned(record: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key): value for key, value in record.items() if key != "signature"}

    @classmethod
    def sign(cls, record: Mapping[str, Any], key: bytes) -> str:
        return hmac.new(key, canonical_json(cls.unsigned(record)), hashlib.sha256).hexdigest()

    def verify(self, record: Mapping[str, Any]) -> bool:
        anchor = self._keys.get(str(record.get("key_id", "")))
        signature = str(record.get("signature", ""))
        signer = str(record.get("verifier_id") or record.get("producer_id") or "")
        source_kind = str(record.get("source_kind", ""))
        anchor_active = bool(anchor and not anchor.revoked)
        if anchor_active and anchor and anchor.not_after:
            try:
                anchor_expiry = datetime.fromisoformat(anchor.not_after)
            except ValueError:
                anchor_active = False
            else:
                anchor_active = anchor_expiry.tzinfo is not None and anchor_expiry.astimezone(UTC) > datetime.now(UTC)
        return bool(
            anchor
            and anchor_active
            and signature
            and signer == anchor.subject_id
            and source_kind in anchor.allowed_source_kinds
            and hmac.compare_digest(self.sign(record, anchor.key), signature)
        )


class CertificationEvidenceIngestor:
    def __init__(self, store: DurableStore, trust_store: EvidenceTrustStore | None = None) -> None:
        self.store = store
        self.trust_store = trust_store or EvidenceTrustStore({})

    def ingest(self, *, tenant_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
        case_id = require_string(record.get("case_id"), "case_id")
        spec = TEST_CASE_BY_ID.get(case_id)
        if spec is None:
            raise ContractError("TEST_CASE_UNKNOWN", f"case is not in T00-T08: {case_id}")
        if record.get("tenant_id") != tenant_id:
            raise AuthorizationError("TENANT_SCOPE_DENIED", "evidence tenant does not match authenticated tenant")
        status = str(record.get("status", "NOT_RUN")).upper()
        if status not in RESULT_PRECEDENCE:
            raise ContractError("EVIDENCE_INVALID", f"unsupported evidence status: {status}")
        evidence_class = require_string(record.get("evidence_class"), "evidence_class")
        if evidence_class not in LOCAL_CLASSES | EXTERNAL_CLASSES | {"NOT_RUN"}:
            raise ContractError("EVIDENCE_INVALID", "unknown evidence class")
        if status == "PASS" and evidence_class == "NOT_RUN":
            raise ContractError("EVIDENCE_INVALID", "PASS evidence cannot use the NOT_RUN class")
        source_kind = require_string(record.get("source_kind"), "source_kind")
        producer_id = require_string(record.get("producer_id"), "producer_id")
        verifier_id = str(record.get("verifier_id", "")) or None
        independent = bool(record.get("independent", False))
        if independent and (not verifier_id or verifier_id == producer_id):
            raise ContractError("SELF_VERIFICATION_DENIED", "independent verifier must differ from producer")
        payload = require_mapping(record.get("payload", {}), "payload")
        signature_verified = self.trust_store.verify(record)
        if status == "PASS":
            required_payload = ("raw_artifacts", "replay", "environment")
            missing = [key for key in required_payload if not payload.get(key)]
            artifacts = payload.get("raw_artifacts", [])
            replay = payload.get("replay", {})
            environment = payload.get("environment", {})
            structured = (
                isinstance(artifacts, list)
                and bool(artifacts)
                and all(
                    isinstance(item, Mapping)
                    and is_sha256_digest(item.get("content_hash"))
                    and bool(item.get("artifact_ref"))
                    for item in artifacts
                )
                and isinstance(replay, Mapping)
                and is_sha256_digest(replay.get("command_digest"))
                and replay.get("status") == "PASS"
                and isinstance(environment, Mapping)
                and bool(environment.get("id"))
                and is_sha256_digest(environment.get("digest"))
            )
            if missing or not structured:
                raise ContractError("EVIDENCE_PAYLOAD_INVALID", f"PASS evidence payload is incomplete; missing={missing}")
        if evidence_class in EXTERNAL_CLASSES:
            authorization = payload.get("authorization_receipt", {})
            authorization_valid = (
                isinstance(authorization, Mapping)
                and is_sha256_digest(authorization.get("receipt_hash"))
                and is_sha256_digest(authorization.get("scope_hash"))
            )
            if source_kind not in REAL_SOURCE_KINDS or not authorization_valid or not signature_verified:
                raise ContractError(
                    "EXTERNAL_EVIDENCE_INVALID",
                    "external evidence is not source-bound, authorized and signed",
                )
            if evidence_class == "INDEPENDENTLY_VERIFIED" and not independent:
                raise ContractError("INDEPENDENT_EVIDENCE_REQUIRED", "independent evidence is not independently verified")
        elif status == "PASS" and source_kind not in LOCAL_SOURCE_KINDS:
            raise ContractError("LOCAL_EVIDENCE_INVALID", "local PASS evidence must use a bounded local source kind")
        captured_at = require_string(record.get("captured_at", utc_now()), "captured_at")
        try:
            captured = datetime.fromisoformat(captured_at)
        except ValueError as exc:
            raise ContractError("EVIDENCE_INVALID", "captured_at must be RFC3339") from exc
        if captured.tzinfo is None or captured.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=5):
            raise ContractError("EVIDENCE_INVALID", "captured_at is timezone-free or unreasonably in the future")
        expires_at = str(record["expires_at"]) if record.get("expires_at") else None
        if expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at)
            except ValueError as exc:
                raise ContractError("EVIDENCE_INVALID", "expires_at must be RFC3339") from exc
            if expiry.tzinfo is None or expiry.astimezone(UTC) <= datetime.now(UTC):
                raise ContractError("EVIDENCE_EXPIRED", "evidence is already expired")
        unsigned = EvidenceTrustStore.unsigned(record)
        normalized = {
            "evidence_id": str(record.get("evidence_id") or uuid.uuid4()),
            "tenant_id": tenant_id,
            "case_id": case_id,
            "capability": spec.capability,
            "level": spec.level,
            "status": status,
            "evidence_class": evidence_class,
            "source_kind": source_kind,
            "producer_id": producer_id,
            "verifier_id": verifier_id,
            "independent": independent,
            "payload": payload,
            "signed_document": unsigned,
            "signature": str(record.get("signature", "")) or None,
            "key_id": str(record.get("key_id", "")) or None,
            "content_hash": digest(unsigned),
            "signature_verified": signature_verified,
            "captured_at": captured_at,
            "expires_at": expires_at,
        }
        return self.store.record_certification_evidence(tenant_id=tenant_id, record=normalized)


def _evidence_unexpired(item: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    value = item.get("expires_at")
    if not value:
        return True
    try:
        expiry = datetime.fromisoformat(str(value))
    except ValueError:
        return False
    return expiry.tzinfo is not None and expiry.astimezone(UTC) > (now or datetime.now(UTC))


def _case_result(spec: TestCaseSpec, records: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"case_id": spec.case_id, "status": "NOT_RUN", "reason": "evidence-missing", "evidence_ids": []}
    statuses = {str(item.get("status", "NOT_RUN")).upper() for item in records}
    if "FAIL" in statuses:
        status, reason = "FAIL", "recorded-failure"
    elif "UNKNOWN" in statuses:
        status, reason = "UNKNOWN", "external-outcome-unreconciled"
    else:
        passing = [
            item
            for item in records
            if str(item.get("status", "")).upper() == "PASS" and _evidence_unexpired(item)
        ]
        eligible = []
        for item in passing:
            evidence_class = str(item.get("evidence_class", ""))
            if spec.external_required and evidence_class != "INDEPENDENTLY_VERIFIED":
                continue
            if spec.independent_required and not bool(item.get("independent")):
                continue
            if not bool(item.get("signature_verified")) and evidence_class in EXTERNAL_CLASSES:
                continue
            eligible.append(item)
        if eligible:
            status, reason = "PASS", "required-evidence-satisfied"
        elif passing:
            status, reason = "BLOCKED", "local-or-unverified-evidence-cannot-satisfy-case"
        elif "PASS" in statuses:
            status, reason = "BLOCKED", "passing-evidence-expired"
        elif "BLOCKED" in statuses:
            status, reason = "BLOCKED", "recorded-blocker"
        else:
            status, reason = "NOT_RUN", "no-passing-execution-evidence"
    return {
        "case_id": spec.case_id,
        "status": status,
        "reason": reason,
        "evidence_ids": sorted(str(item.get("evidence_id")) for item in records if item.get("evidence_id")),
        "zero_tolerance": spec.zero_tolerance,
    }


class TestMatrixEvaluator:
    def evaluate(self, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        by_case: dict[str, list[Mapping[str, Any]]] = {case_id: [] for case_id in TEST_CASE_BY_ID}
        unknown_records: list[str] = []
        for item in records:
            case_id = str(item.get("case_id", ""))
            if case_id in by_case:
                by_case[case_id].append(item)
            else:
                unknown_records.append(case_id)
        case_results = [_case_result(spec, by_case[spec.case_id]) for spec in TEST_CASES]
        suites = {}
        for suite_id in SUITE_IDS:
            rows = [item for item in case_results if item["case_id"].startswith(suite_id + "-")]
            statuses = {item["status"] for item in rows}
            if "FAIL" in statuses:
                status = "FAIL"
            elif "UNKNOWN" in statuses:
                status = "UNKNOWN"
            elif statuses == {"PASS"}:
                status = "PASS"
            elif statuses == {"NOT_RUN"}:
                status = "NOT_RUN"
            else:
                status = "BLOCKED"
            suites[suite_id] = {
                "status": status,
                "total": len(rows),
                "passed": sum(item["status"] == "PASS" for item in rows),
                "blocked": sum(item["status"] == "BLOCKED" for item in rows),
                "not_run": sum(item["status"] == "NOT_RUN" for item in rows),
                "failed": sum(item["status"] == "FAIL" for item in rows),
                "unknown": sum(item["status"] == "UNKNOWN" for item in rows),
            }
        return {
            "status": "PASS" if all(item["status"] == "PASS" for item in suites.values()) else "NOT_CERTIFIED",
            "suite_results": suites,
            "case_results": case_results,
            "required_case_count": len(TEST_CASES),
            "t06_conformance_units": len(T06_TEST_CASES),
            "unknown_record_case_ids": sorted(set(filter(None, unknown_records))),
            "evaluated_at": utc_now(),
            "certification": "NOT_CERTIFIED",
        }


def evaluate_levels(matrix: Mapping[str, Any]) -> dict[str, Any]:
    suites = require_mapping(matrix.get("suite_results", {}), "matrix.suite_results")
    levels: dict[str, Any] = {}
    previous_pass = True
    for level in ("E1", "E2", "E3", "E4", "E5"):
        required = E_LEVEL_SUITES[level]
        statuses = [str(require_mapping(suites.get(suite, {}), f"suite {suite}").get("status", "NOT_RUN")) for suite in required]
        if not previous_pass:
            status, reasons = "BLOCKED", ["previous-level-not-pass"]
        elif any(value == "FAIL" for value in statuses):
            status, reasons = "FAIL", ["required-suite-failed"]
        elif any(value == "UNKNOWN" for value in statuses):
            status, reasons = "UNKNOWN", ["required-suite-outcome-unknown"]
        elif all(value == "PASS" for value in statuses):
            status, reasons = "PASS", []
        elif all(value == "NOT_RUN" for value in statuses):
            status, reasons = "NOT_RUN", ["required-suites-not-run"]
        else:
            status, reasons = "BLOCKED", ["required-suites-incomplete"]
        levels[level] = {"status": status, "required_suites": list(required), "suite_statuses": statuses, "reasons": reasons}
        previous_pass = status == "PASS"
    return levels


def evaluate_p05(
    levels: Mapping[str, Any],
    release_context: Mapping[str, Any],
    *,
    verified_evidence_ids: frozenset[str] = frozenset(),
    verified_evidence: Mapping[str, Mapping[str, Any]] | None = None,
    customer_acceptances: Sequence[Mapping[str, Any]] = (),
    candidate_digest: str | None = None,
) -> dict[str, Any]:
    evidence_index = dict(verified_evidence or {})
    verified_ids = set(verified_evidence_ids) | set(evidence_index)

    def bound_evidence(
        reference: Mapping[str, Any], *, case_prefixes: tuple[str, ...]
    ) -> Mapping[str, Any] | None:
        evidence_id = str(reference.get("evidence_id", ""))
        record = evidence_index.get(evidence_id)
        if not record or evidence_id not in verified_ids:
            return None
        if not str(record.get("case_id", "")).startswith(case_prefixes):
            return None
        for field in ("producer_id", "verifier_id", "content_hash"):
            if reference.get(field) is not None and reference.get(field) != record.get(field):
                return None
        return record

    missing: list[str] = []
    if any(require_mapping(levels.get(level, {}), level).get("status") != "PASS" for level in ("E1", "E2", "E3", "E4", "E5")):
        missing.append("E1-E5-pass")
    health = require_mapping(release_context.get("health", {}), "release_context.health")
    if not all(health.get(name) is True for name in ("livez", "readyz", "metrics", "version")):
        missing.append("deployment-health")
    if not bool(release_context.get("rollback_ready")):
        missing.append("rollback-ready")
    if not bool(release_context.get("restore_replayed")):
        missing.append("restore-replayed")
    findings = release_context.get("open_findings", [])
    if (
        not isinstance(findings, list)
        or any(not isinstance(item, Mapping) for item in findings)
        or any(
            str(item.get("status", "OPEN")).upper() == "OPEN"
            and str(item.get("severity", "P1")).upper() in {"P0", "P1"}
            for item in findings
            if isinstance(item, Mapping)
        )
    ):
        missing.append("no-open-P0-P1")
    artifacts = release_context.get("artifacts", [])
    artifacts_valid = (
        isinstance(artifacts, list)
        and bool(artifacts)
        and all(
            isinstance(item, Mapping)
            and is_sha256_digest(item.get("content_hash"))
            and item.get("integrity_verified") is True
            and item.get("subject_digest") == candidate_digest
            for item in artifacts
        )
        and any(
            isinstance(item, Mapping)
            and item.get("artifact_kind") == "release-candidate"
            and item.get("content_hash") == candidate_digest
            for item in artifacts
        )
    )
    if not artifacts_valid:
        missing.append("artifact-integrity")
    approvals = release_context.get("independent_approvals", [])
    approvals_valid = isinstance(approvals, list) and bool(approvals)
    for item in approvals if isinstance(approvals, list) else []:
        record = (
            bound_evidence(item, case_prefixes=("T07-", "T08-"))
            if isinstance(item, Mapping)
            else None
        )
        payload = record.get("payload", {}) if record else {}
        approval = payload.get("approval", {}) if isinstance(payload, Mapping) else {}
        approvals_valid = bool(
            approvals_valid
            and isinstance(approval, Mapping)
            and approval.get("decision") == "APPROVED"
            and approval.get("scope") == "release"
            and approval.get("candidate_digest") == candidate_digest
            and record
            and record.get("producer_id") != record.get("verifier_id")
        )
    if not approvals_valid:
        missing.append("independent-approval")
    deployment_evidence = release_context.get("deployment_evidence", [])
    deployment_valid = isinstance(deployment_evidence, list) and bool(deployment_evidence)
    for item in deployment_evidence if isinstance(deployment_evidence, list) else []:
        record = (
            bound_evidence(item, case_prefixes=("T07-",))
            if isinstance(item, Mapping)
            else None
        )
        payload = record.get("payload", {}) if record else {}
        deployment = payload.get("deployment", {}) if isinstance(payload, Mapping) else {}
        deployment_valid = bool(
            deployment_valid
            and isinstance(deployment, Mapping)
            and deployment.get("status") == "PASS"
            and deployment.get("candidate_digest") == candidate_digest
        )
    if not deployment_valid:
        missing.append("deployment-evidence")
    customer = require_mapping(release_context.get("customer_acceptance", {}), "customer_acceptance")
    customer_evidence_ids = customer.get("evidence_ids", [])
    acceptance = next(
        (
            item
            for item in customer_acceptances
            if item.get("acceptance_id") == customer.get("acceptance_id")
        ),
        None,
    )
    customer_evidence = (
        [evidence_index.get(str(item)) for item in customer_evidence_ids]
        if isinstance(customer_evidence_ids, list)
        else []
    )
    if (
        customer.get("decision") != "ACCEPTED"
        or customer.get("signature_verified") is not True
        or customer.get("customer_actor_id") == customer.get("executor_id")
        or not isinstance(customer_evidence_ids, list)
        or not customer_evidence_ids
        or not set(customer_evidence_ids).issubset(verified_ids)
        or not all(customer_evidence)
        or not any(str(item.get("case_id", "")).startswith("T08-04-") for item in customer_evidence)
        or acceptance is None
        or acceptance.get("candidate_digest") != candidate_digest
        or acceptance.get("decision") != "ACCEPTED"
        or acceptance.get("signature_verified") is not True
        or acceptance.get("customer_actor_id") != customer.get("customer_actor_id")
        or acceptance.get("executor_id") != customer.get("executor_id")
        or set(acceptance.get("evidence_ids", [])) != set(customer_evidence_ids)
    ):
        missing.append("customer-acceptance")
    issued = not missing
    return {
        "decision": "P05_DEPLOYMENT_COMPLETE" if issued else "P05_DEPLOYMENT_COMPLETE_NOT_ISSUED",
        "issued": issued,
        "reasons": missing,
        "completion_claim_ignored": True,
        "certification": "CERTIFIED" if issued else "NOT_CERTIFIED",
        "decided_at": utc_now(),
    }


class CertificationEngine:
    def __init__(self, store: DurableStore, trust_store: EvidenceTrustStore | None = None) -> None:
        self.store = store
        self.ingestor = CertificationEvidenceIngestor(store, trust_store)
        self.matrix = TestMatrixEvaluator()

    def ingest(self, *, tenant_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
        return self.ingestor.ingest(tenant_id=tenant_id, record=record)

    def evaluate(self, *, tenant_id: str, candidate_digest: str, release_context: Mapping[str, Any]) -> dict[str, Any]:
        require_sha256_digest(candidate_digest, "candidate_digest")
        records = self.store.list_certification_evidence(tenant_id=tenant_id)
        effective_records = []
        for item in records:
            effective = dict(item)
            if effective.get("evidence_class") in EXTERNAL_CLASSES:
                signed_document = effective.get("signed_document")
                current_record = (
                    {**dict(signed_document), "signature": effective.get("signature")}
                    if isinstance(signed_document, Mapping)
                    else {}
                )
                effective["signature_verified"] = self.ingestor.trust_store.verify(current_record)
            effective_records.append(effective)
        matrix_result = self.matrix.evaluate(effective_records)
        levels = evaluate_levels(matrix_result)
        verified_evidence = {
            str(item["evidence_id"]): item
            for item in effective_records
            if item.get("status") == "PASS"
            and item.get("evidence_class") == "INDEPENDENTLY_VERIFIED"
            and bool(item.get("signature_verified"))
            and bool(item.get("independent"))
            and _evidence_unexpired(item)
        }
        customer_acceptances = self.store.list_customer_acceptances(
            tenant_id=tenant_id, candidate_digest=candidate_digest
        )
        p05 = evaluate_p05(
            levels,
            release_context,
            verified_evidence_ids=frozenset(verified_evidence),
            verified_evidence=verified_evidence,
            customer_acceptances=customer_acceptances,
            candidate_digest=candidate_digest,
        )
        state = "P05_DEPLOYMENT_COMPLETE" if p05["issued"] else "NOT_CERTIFIED"
        persisted = self.store.record_certification_run(
            tenant_id=tenant_id, candidate_digest=candidate_digest, state=state,
            level_results=levels, matrix_result=matrix_result, p05_issued=bool(p05["issued"]),
        )
        return {
            "certification_run": persisted,
            "matrix": matrix_result,
            "levels": levels,
            "p05": p05,
            "external_evidence": "INDEPENDENTLY_VERIFIED" if p05["issued"] else "NOT_RUN",
            "certification": "CERTIFIED" if p05["issued"] else "NOT_CERTIFIED",
        }
