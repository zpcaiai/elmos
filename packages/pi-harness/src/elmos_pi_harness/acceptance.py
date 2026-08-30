"""Executable customer acceptance journeys with externally owned sign-off."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from .canonical import canonical_bytes, digest, require_nonempty, require_uuid, utc_now
from .independent_verifier import SignedVerification, VerifierTrustStore
from .models import PolicyDeniedError
from .production import ExactTarget


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


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
        expected = dict(self.expected_outcome)
        canonical_bytes(expected)
        object.__setattr__(self, "expected_outcome", MappingProxyType(expected))


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
        executor_id: str,
        producer_trust_domain: str,
    ) -> dict[str, Any]:
        require_uuid(run_id, "run_id")
        require_uuid(tenant_id, "tenant_id")
        require_nonempty(authorization_id, "authorization_id", 256)
        require_nonempty(executor_id, "executor_id", 512)
        require_nonempty(producer_trust_domain, "producer_trust_domain", 512)
        if target.environment.lower() in {"prod", "production"}:
            raise PolicyDeniedError("customer UAT must not execute in production")
        if not cases:
            return {
                "run_id": run_id,
                "status": "NOT_RUN",
                "certified": False,
                "results": [],
            }
        case_ids = [case.case_id for case in cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("customer acceptance case IDs must be unique")
        started_at = utc_now()
        results: list[dict[str, Any]] = []
        for case in cases:
            started = time.monotonic()
            try:
                observation = dict(executor(case))
                canonical_bytes(observation)
                evidence_digest = observation.get("evidence_digest")
                actual = observation.get("actual_outcome")
                passed = (
                    isinstance(evidence_digest, str)
                    and _DIGEST.fullmatch(evidence_digest) is not None
                    and actual == dict(case.expected_outcome)
                )
                status = "PASS" if passed else "FAIL"
            except Exception as exc:  # noqa: BLE001 - external journey errors become evidence, not process failures
                observation = {
                    "error_type": type(exc).__name__,
                    "error_message_digest": digest({"message": str(exc)[:4096]}),
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
        completed_at = utc_now()
        result = {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "target": target.to_dict(),
            "environment_digest": digest(target.to_dict()),
            "authorization_id": authorization_id,
            "executor_id": executor_id,
            "producer_trust_domain": producer_trust_domain,
            "started_at": started_at,
            "completed_at": completed_at,
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
    customer_authority_id: str,
    customer_trust_domain: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    expected_evidence = _validate_passed_run(run)
    implementation_trust_domain = require_nonempty(
        implementation_trust_domain, "implementation_trust_domain", 512
    )
    customer_authority_id = require_nonempty(
        customer_authority_id, "customer_authority_id", 512
    )
    customer_trust_domain = require_nonempty(
        customer_trust_domain, "customer_trust_domain", 512
    )
    if (
        receipt.statement.scope != "external_gate_acceptance:P1-G07"
        or receipt.verdict != "VERIFIED"
    ):
        raise PolicyDeniedError(
            "receipt is not a verified customer acceptance sign-off"
        )
    if (
        receipt.verifier_id != customer_authority_id
        or receipt.verifier_trust_domain != customer_trust_domain
    ):
        raise PolicyDeniedError("receipt signer is not the exact customer authority")
    if receipt.verifier_trust_domain in {
        implementation_trust_domain,
        run.get("producer_trust_domain"),
    }:
        raise PolicyDeniedError(
            "implementation team cannot self-sign customer acceptance"
        )
    statement = receipt.statement
    if (
        statement.producer_id != run.get("executor_id")
        or statement.producer_trust_domain != run.get("producer_trust_domain")
        or statement.environment_digest != run.get("environment_digest")
        or statement.raw_evidence_digests != expected_evidence
        or statement.authorization_id != run.get("authorization_id")
        or statement.executor_id != run.get("executor_id")
        or statement.started_at != run.get("started_at")
        or statement.completed_at != run.get("completed_at")
        or statement.result != "PASS"
    ):
        raise PolicyDeniedError(
            "customer sign-off does not bind the exact UAT execution"
        )
    verified = trust_store.verify(
        receipt,
        expected_subject_digest=str(run["result_digest"]),
        now=now,
    )
    return {
        "status": "ACCEPTED",
        "certified": False,
        "run_id": run["run_id"],
        "customer_signoff_receipt": verified,
        "blockers": ["production_release_authority_required"],
    }


def _validate_passed_run(run: Mapping[str, Any]) -> tuple[str, ...]:
    value = dict(run)
    expected_fields = {
        "run_id",
        "tenant_id",
        "target",
        "environment_digest",
        "authorization_id",
        "executor_id",
        "producer_trust_domain",
        "started_at",
        "completed_at",
        "status",
        "certified",
        "failed_cases",
        "results",
        "result_digest",
    }
    if set(value) != expected_fields:
        raise PolicyDeniedError("customer UAT result fields are incomplete or unknown")
    require_uuid(value["run_id"], "run_id")
    require_uuid(value["tenant_id"], "tenant_id")
    for field in ("authorization_id", "executor_id", "producer_trust_domain"):
        require_nonempty(value[field], field, 512)
    if value["status"] != "EXECUTED_PASS" or value["certified"] is not False:
        raise PolicyDeniedError(
            "customer sign-off cannot accept an incomplete or failed UAT run"
        )
    if value["failed_cases"] != []:
        raise PolicyDeniedError("customer UAT result contains failed cases")
    target_value = value["target"]
    if not isinstance(target_value, dict):
        raise PolicyDeniedError("customer UAT target is malformed")
    try:
        exact_target = ExactTarget(**target_value)
    except (TypeError, ValueError) as exc:
        raise PolicyDeniedError("customer UAT target is malformed") from exc
    if exact_target.environment.lower() in {"prod", "production"}:
        raise PolicyDeniedError("customer UAT target cannot be production")
    if value["environment_digest"] != digest(exact_target.to_dict()):
        raise PolicyDeniedError("customer UAT environment digest mismatch")
    try:
        started = datetime.fromisoformat(
            str(value["started_at"]).replace("Z", "+00:00")
        )
        completed = datetime.fromisoformat(
            str(value["completed_at"]).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise PolicyDeniedError("customer UAT execution window is malformed") from exc
    if (
        started.tzinfo is None
        or completed.tzinfo is None
        or completed.astimezone(timezone.utc) < started.astimezone(timezone.utc)
    ):
        raise PolicyDeniedError("customer UAT execution window is invalid")
    rows = value["results"]
    if not isinstance(rows, list) or not rows:
        raise PolicyDeniedError("customer UAT results are empty")
    case_ids: set[str] = set()
    evidence: list[str] = []
    row_fields = {
        "case_id",
        "journey",
        "role",
        "severity",
        "status",
        "duration_ms",
        "evidence_digest",
        "observation_digest",
    }
    for row in rows:
        if not isinstance(row, dict) or set(row) != row_fields:
            raise PolicyDeniedError("customer UAT case result is malformed")
        case_id = require_nonempty(row["case_id"], "case_id", 512)
        if case_id in case_ids or row["status"] != "PASS":
            raise PolicyDeniedError("customer UAT case is duplicate or failed")
        case_ids.add(case_id)
        for field in ("journey", "role"):
            require_nonempty(row[field], field, 512)
        if row["severity"] not in {"P0", "P1", "P2"}:
            raise PolicyDeniedError("customer UAT case severity is invalid")
        duration = row["duration_ms"]
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or not math.isfinite(float(duration))
            or duration < 0
        ):
            raise PolicyDeniedError("customer UAT duration is invalid")
        for field in ("evidence_digest", "observation_digest"):
            if not isinstance(row[field], str) or _DIGEST.fullmatch(row[field]) is None:
                raise PolicyDeniedError(f"customer UAT {field} is invalid")
        evidence.append(row["evidence_digest"])
    supplied_result_digest = value.pop("result_digest")
    if supplied_result_digest != digest(value):
        raise PolicyDeniedError("customer UAT result digest is invalid")
    return tuple(evidence)
