"""Executable customer acceptance journeys with externally owned sign-off."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .canonical import digest, require_nonempty, require_uuid, utc_now
from .independent_verifier import SignedVerification, VerifierTrustStore
from .models import PolicyDeniedError
from .production import ExactTarget


@dataclass(frozen=True)
class AcceptanceCase:
    case_id: str
    journey: str
    role: str
    expected_outcome: Mapping[str, Any]
    severity: str = "P1"

    def __post_init__(self) -> None:
        for name in ("case_id", "journey", "role"):
            require_nonempty(getattr(self, name), name, 512)
        if self.severity not in {"P0", "P1", "P2"}:
            raise ValueError("acceptance severity must be P0, P1, or P2")


class AcceptanceRunner:
    def run(
        self,
        *,
        run_id: str,
        tenant_id: str,
        target: ExactTarget,
        cases: Sequence[AcceptanceCase],
        executor: Callable[[AcceptanceCase], Mapping[str, Any]],
        authorization_id: str,
    ) -> dict[str, Any]:
        require_uuid(run_id, "run_id")
        require_uuid(tenant_id, "tenant_id")
        require_nonempty(authorization_id, "authorization_id", 256)
        if not cases:
            return {
                "run_id": run_id,
                "status": "NOT_RUN",
                "certified": False,
                "results": [],
            }
        results: list[dict[str, Any]] = []
        for case in cases:
            started = time.monotonic()
            try:
                observation = dict(executor(case))
                evidence_digest = observation.get("evidence_digest")
                actual = observation.get("actual_outcome")
                passed = bool(evidence_digest) and actual == dict(case.expected_outcome)
                status = "PASS" if passed else "FAIL"
            except Exception as exc:  # noqa: BLE001 - external journey errors become evidence, not process failures
                observation = {
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1000],
                }
                evidence_digest = None
                status = "FAIL"
            results.append(
                {
                    "case_id": case.case_id,
                    "journey": case.journey,
                    "role": case.role,
                    "severity": case.severity,
                    "status": status,
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                    "evidence_digest": evidence_digest,
                    "observation_digest": digest(observation),
                }
            )
        failed = [item["case_id"] for item in results if item["status"] != "PASS"]
        result = {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "target": target.to_dict(),
            "authorization_id": authorization_id,
            "executed_at": utc_now(),
            "status": "EXECUTED_PASS" if not failed else "EXECUTED_FAIL",
            "certified": False,
            "failed_cases": failed,
            "results": results,
        }
        return result | {"result_digest": digest(result)}


def accept_customer_signoff(
    run: Mapping[str, Any],
    receipt: SignedVerification,
    trust_store: VerifierTrustStore,
    *,
    implementation_trust_domain: str,
) -> dict[str, Any]:
    if run.get("status") != "EXECUTED_PASS" or not run.get("result_digest"):
        raise PolicyDeniedError(
            "customer sign-off cannot accept an incomplete or failed UAT run"
        )
    if (
        receipt.statement.scope != "customer_acceptance"
        or receipt.verdict != "VERIFIED"
    ):
        raise PolicyDeniedError(
            "receipt is not a verified customer acceptance sign-off"
        )
    if receipt.verifier_trust_domain == implementation_trust_domain:
        raise PolicyDeniedError(
            "implementation team cannot self-sign customer acceptance"
        )
    verified = trust_store.verify(
        receipt, expected_subject_digest=str(run["result_digest"])
    )
    return {
        "status": "ACCEPTED",
        "certified": False,
        "run_id": run["run_id"],
        "customer_signoff_receipt": verified,
        "blockers": ["production_release_authority_required"],
    }
