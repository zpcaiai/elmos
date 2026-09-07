"""Authorized customer repository bindings and Golden Route acceptance."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import AuthorizationError, ContractError
from .models import digest, is_sha256_digest, require_mapping, require_sha256_digest, require_string, utc_now
from .routes import GOLDEN_ROUTES
from .storage import DurableStore

CORPUS_CLASSES = frozenset({"development", "negative", "holdout", "representative"})


@dataclass(frozen=True, slots=True)
class RepositoryBinding:
    tenant_id: str
    provider_instance: str
    native_repository_id: str
    exact_commit: str
    corpus_class: str
    authorization_receipt: str
    purpose: str
    retention_policy: str
    customer_actor_id: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RepositoryBinding:
        corpus_class = require_string(value.get("corpus_class"), "corpus_class")
        if corpus_class not in CORPUS_CLASSES:
            raise ContractError("CORPUS_CLASS_INVALID", "repository corpus class is not recognized")
        commit = require_string(value.get("exact_commit"), "exact_commit")
        if len(commit) not in {40, 64} or any(
            char not in "0123456789abcdefABCDEF" for char in commit
        ):
            raise ContractError(
                "SCM_COMMIT_INVALID", "repository binding requires an exact 40/64 hexadecimal commit"
            )
        authorization_receipt = require_string(
            value.get("authorization_receipt"), "authorization_receipt"
        )
        require_sha256_digest(authorization_receipt, "authorization_receipt")
        return cls(
            tenant_id=require_string(value.get("tenant_id"), "tenant_id"),
            provider_instance=require_string(value.get("provider_instance"), "provider_instance"),
            native_repository_id=require_string(value.get("native_repository_id"), "native_repository_id"),
            exact_commit=commit.lower(),
            corpus_class=corpus_class,
            authorization_receipt=authorization_receipt,
            purpose=require_string(value.get("purpose"), "purpose"),
            retention_policy=require_string(value.get("retention_policy"), "retention_policy"),
            customer_actor_id=str(value["customer_actor_id"]) if value.get("customer_actor_id") else None,
        )

    @property
    def binding_hash(self) -> str:
        return digest(
            {
                "tenant_id": self.tenant_id,
                "provider_instance": self.provider_instance,
                "native_repository_id": self.native_repository_id,
                "exact_commit": self.exact_commit,
                "corpus_class": self.corpus_class,
                "authorization_receipt": self.authorization_receipt,
                "purpose": self.purpose,
                "retention_policy": self.retention_policy,
                "customer_actor_id": self.customer_actor_id,
            }
        )


class GoldenRouteEvaluator:
    def __init__(
        self,
        acceptance_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
        evidence_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> None:
        self.acceptance_verifier = acceptance_verifier
        self.evidence_verifier = evidence_verifier

    def evaluate(
        self, *, binding: RepositoryBinding | Mapping[str, Any], route_id: str,
        candidate_digest: str, evidence: Mapping[str, Any], executor_id: str,
    ) -> dict[str, Any]:
        repository = binding if isinstance(binding, RepositoryBinding) else RepositoryBinding.from_mapping(binding)
        if route_id not in GOLDEN_ROUTES:
            raise ContractError("GOLDEN_ROUTE_UNKNOWN", f"unknown route: {route_id}")
        require_sha256_digest(candidate_digest, "candidate_digest")
        required = (
            "baseline", "source_snapshot_digest", "target_commit", "semantic_ir_digest",
            "change_graph_digest", "validation_dag_digest", "artifact_graph_digest",
            "rollback_receipt", "cost_eta_slo",
        )
        missing = [key for key in required if not evidence.get(key)]
        for key in (
            "source_snapshot_digest",
            "semantic_ir_digest",
            "change_graph_digest",
            "validation_dag_digest",
            "artifact_graph_digest",
        ):
            if not is_sha256_digest(evidence.get(key)):
                missing.append(f"{key}-invalid")
        target_commit = str(evidence.get("target_commit", ""))
        if len(target_commit) not in {40, 64} or any(char not in "0123456789abcdefABCDEF" for char in target_commit):
            missing.append("target-commit-invalid")
        baseline = require_mapping(evidence.get("baseline", {}), "evidence.baseline")
        if not all(str(baseline.get(key, "NOT_RUN")).upper() == "PASS" for key in ("build", "test", "contract", "security")):
            missing.append("baseline-pass")
        validation = evidence.get("validation_results", [])
        if not isinstance(validation, list) or not validation:
            missing.append("validation-results")
        elif any(not isinstance(item, Mapping) or str(item.get("status", "NOT_RUN")).upper() != "PASS" for item in validation):
            missing.append("all-validation-pass")
        unknown_semantics = evidence.get("unknown_semantics", [])
        if not isinstance(unknown_semantics, list) or unknown_semantics:
            missing.append("no-unknown-semantics")
        execution_receipt = evidence.get("execution_receipt", {})
        holdout_receipt = execution_receipt if repository.corpus_class == "holdout" else evidence.get("holdout_evidence", {})
        representative_receipt = execution_receipt if repository.corpus_class == "representative" else evidence.get("representative_evidence", {})
        holdout = (
            isinstance(holdout_receipt, Mapping)
            and self.evidence_verifier is not None
            and self.evidence_verifier(holdout_receipt)
        )
        representative = (
            isinstance(representative_receipt, Mapping)
            and self.evidence_verifier is not None
            and self.evidence_verifier(representative_receipt)
        )
        if not holdout:
            missing.append("holdout")
        if not representative:
            missing.append("representative")
        cost_eta_slo = require_mapping(evidence.get("cost_eta_slo", {}), "cost_eta_slo")
        if (
            cost_eta_slo.get("status") != "PASS"
            or not cost_eta_slo.get("cost_currency")
            or not isinstance(cost_eta_slo.get("repeat_count"), int)
            or int(cost_eta_slo.get("repeat_count", 0)) < 2
            or not cost_eta_slo.get("raw_evidence")
        ):
            missing.append("cost-eta-slo")
        customer_acceptance = require_mapping(evidence.get("customer_acceptance", {}), "customer_acceptance")
        accepted = (
            customer_acceptance.get("decision") == "ACCEPTED"
            and customer_acceptance.get("signature_verified") is True
            and customer_acceptance.get("customer_actor_id") != executor_id
            and bool(customer_acceptance.get("evidence_ids"))
            and (
                repository.customer_actor_id is None
                or customer_acceptance.get("customer_actor_id") == repository.customer_actor_id
            )
            and self.acceptance_verifier is not None
            and self.acceptance_verifier(customer_acceptance)
        )
        if not accepted:
            missing.append("customer-acceptance")
        return {
            "route_id": route_id,
            "repository_binding_hash": repository.binding_hash,
            "candidate_digest": candidate_digest,
            "status": "PASS" if not missing else "BLOCKED",
            "missing": sorted(set(missing)),
            "corpus_class": repository.corpus_class,
            "holdout_present": holdout,
            "representative_present": representative,
            "customer_acceptance_verified": accepted,
            "evidence_hash": digest(evidence),
            "evaluated_at": utc_now(),
            "external_evidence": "INDEPENDENTLY_VERIFIED" if not missing else "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }


class CustomerAcceptanceRegistry:
    def __init__(
        self, store: DurableStore, verifier: Callable[[Mapping[str, Any]], bool] | None = None
    ) -> None:
        self.store = store
        self.verifier = verifier

    def record(
        self, *, binding: RepositoryBinding | Mapping[str, Any], route_id: str, candidate_digest: str,
        executor_id: str, decision: Mapping[str, Any], authenticated_customer_actor_id: str,
    ) -> dict[str, Any]:
        repository = binding if isinstance(binding, RepositoryBinding) else RepositoryBinding.from_mapping(binding)
        if route_id not in GOLDEN_ROUTES:
            raise ContractError("GOLDEN_ROUTE_UNKNOWN", f"unknown route: {route_id}")
        require_sha256_digest(candidate_digest, "candidate_digest")
        if repository.customer_actor_id and repository.customer_actor_id != authenticated_customer_actor_id:
            raise AuthorizationError("CUSTOMER_IDENTITY_MISMATCH", "acceptance actor is not bound to the customer repository")
        if authenticated_customer_actor_id == executor_id:
            raise AuthorizationError("SELF_APPROVAL_DENIED", "executor cannot issue customer acceptance")
        evidence_ids = decision.get("evidence_ids", [])
        if not isinstance(evidence_ids, list):
            raise ContractError("ACCEPTANCE_EVIDENCE_INVALID", "evidence_ids must be an array")
        normalized_decision = str(decision.get("decision", "REJECTED")).upper()
        if normalized_decision not in {"ACCEPTED", "REJECTED"}:
            raise ContractError("ACCEPTANCE_DECISION_INVALID", "decision must be ACCEPTED or REJECTED")
        verification_envelope = {
            "tenant_id": repository.tenant_id,
            "repository_binding_hash": repository.binding_hash,
            "route_id": route_id,
            "candidate_digest": candidate_digest,
            "customer_actor_id": authenticated_customer_actor_id,
            "executor_id": executor_id,
            **dict(decision),
        }
        signature_verified = self.verifier is not None and self.verifier(verification_envelope)
        return self.store.record_customer_acceptance(
            tenant_id=repository.tenant_id,
            repository_binding_hash=repository.binding_hash,
            route_id=route_id,
            candidate_digest=candidate_digest,
            customer_actor_id=authenticated_customer_actor_id,
            executor_id=executor_id,
            decision=normalized_decision,
            evidence_ids=[require_string(item, "evidence_ids[]") for item in evidence_ids],
            signature_verified=signature_verified,
        )


def cohort_status(bindings: Sequence[RepositoryBinding | Mapping[str, Any]]) -> dict[str, Any]:
    parsed = [item if isinstance(item, RepositoryBinding) else RepositoryBinding.from_mapping(item) for item in bindings]
    by_class = {corpus: sum(item.corpus_class == corpus for item in parsed) for corpus in CORPUS_CLASSES}
    complete = by_class["holdout"] > 0 and by_class["representative"] > 0
    tenant_count = len({item.tenant_id for item in parsed})
    repository_count = len({(item.provider_instance, item.native_repository_id, item.exact_commit) for item in parsed})
    return {
        "status": "READY" if complete else "BLOCKED",
        "counts": by_class,
        "tenant_count": tenant_count,
        "repository_count": repository_count,
        "required": {"holdout": 1, "representative": 1},
        "certification": "NOT_CERTIFIED",
    }
