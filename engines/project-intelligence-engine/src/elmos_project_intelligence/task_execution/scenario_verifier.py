"""Evidence-driven verification for the 248 product acceptance scenarios."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..canonical import canonical_digest, canonical_value, validate_digest
from ..runtime import SKILL_REGISTRY
from .task_runner import _parse_catalog


@dataclass(frozen=True, slots=True)
class ScenarioEvidence:
    requirement: str
    artifact_digest: str
    tenant_id: str
    project_id: str
    revision: str
    corpus_role: str
    executor_id: str

    def __post_init__(self) -> None:
        validate_digest(self.artifact_digest)
        if self.corpus_role not in {"DEVELOPMENT", "NEGATIVE", "HOLDOUT"}:
            raise ValueError("corpus_role is unsupported")
        if not all((self.requirement, self.tenant_id, self.project_id, self.revision, self.executor_id)):
            raise ValueError("scenario evidence identity is incomplete")

    def as_dict(self) -> dict[str, str]:
        return {
            "requirement": self.requirement,
            "artifact_digest": self.artifact_digest,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "revision": self.revision,
            "corpus_role": self.corpus_role,
            "executor_id": self.executor_id,
        }


class IndependentAcceptanceVerifier(Protocol):
    verifier_id: str

    def verify(
        self, claim: Mapping[str, Any], evidence: Sequence[ScenarioEvidence]
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ScenarioVerdict:
    scenario_id: str
    skill: str
    batch: str
    status: str
    missing_evidence: tuple[str, ...]
    holdout_evidence_present: bool
    independent_verifier_id: str | None
    verifier_receipt_digest: str | None
    external_evidence_status: str
    certification_status: str
    verdict_digest: str


class AcceptanceScenarioVerifier:
    """Prepare and verify acceptance without turning declarations into evidence."""

    DEFAULT_SCENARIOS_PATH = (
        Path(__file__).resolve().parents[5]
        / "skills/elmos-project-intelligence-skills-v1.1.0/backlog/acceptance-scenarios.yaml"
    )

    def __init__(self, scenarios_path: Path | str | None = None) -> None:
        self.scenarios_path = Path(scenarios_path) if scenarios_path else self.DEFAULT_SCENARIOS_PATH
        self.scenarios: dict[str, dict[str, Any]] = {}
        self.skill_scenarios: dict[str, list[dict[str, Any]]] = {}
        self.batch_scenarios: dict[str, list[dict[str, Any]]] = {}
        self._load_scenarios()

    def _load_scenarios(self) -> None:
        if not self.scenarios_path.is_file() or self.scenarios_path.is_symlink():
            raise FileNotFoundError(f"acceptance catalog is unavailable: {self.scenarios_path}")
        data = _parse_catalog(self.scenarios_path.read_text(encoding="utf-8"), "scenarios")
        rows = data.get("scenarios")
        if data.get("scenario_count") != 248 or not isinstance(rows, list) or len(rows) != 248:
            raise ValueError("acceptance catalog must contain exactly 248 scenarios")
        for row in rows:
            scenario_id, skill = row.get("id"), row.get("skill")
            required = row.get("evidence_required")
            if not isinstance(scenario_id, str) or scenario_id in self.scenarios:
                raise ValueError("acceptance scenario identifiers must be unique")
            if not isinstance(skill, str) or skill not in SKILL_REGISTRY:
                raise ValueError("acceptance scenario references an unknown exact Skill")
            if not isinstance(required, list) or not required:
                raise ValueError("acceptance scenario must declare evidence")
            self.scenarios[scenario_id] = row
            self.skill_scenarios.setdefault(skill, []).append(row)
            self.batch_scenarios.setdefault(str(row.get("batch", "")), []).append(row)
        if set(self.skill_scenarios) != set(SKILL_REGISTRY):
            raise ValueError("acceptance scenarios do not cover all exact Skills")

    @staticmethod
    def _verdict(
        row: Mapping[str, Any],
        *,
        status: str,
        missing: Sequence[str],
        holdout: bool,
        verifier_id: str | None = None,
        receipt_digest: str | None = None,
    ) -> ScenarioVerdict:
        external = "VERIFIED_EXTERNAL" if status == "PASSED" else "NOT_RUN"
        document = {
            "scenario_id": str(row["id"]),
            "skill": str(row["skill"]),
            "batch": str(row.get("batch", "")),
            "status": status,
            "missing_evidence": list(missing),
            "holdout_evidence_present": holdout,
            "independent_verifier_id": verifier_id,
            "verifier_receipt_digest": receipt_digest,
            "external_evidence_status": external,
            "certification_status": "NOT_CERTIFIED",
        }
        return ScenarioVerdict(
            scenario_id=document["scenario_id"],
            skill=document["skill"],
            batch=document["batch"],
            status=status,
            missing_evidence=tuple(missing),
            holdout_evidence_present=holdout,
            independent_verifier_id=verifier_id,
            verifier_receipt_digest=receipt_digest,
            external_evidence_status=external,
            certification_status="NOT_CERTIFIED",
            verdict_digest=canonical_digest(canonical_value(document)),
        )

    def verify_scenario(
        self,
        scenario_id: str,
        *,
        evidence: Sequence[ScenarioEvidence] = (),
        verifier: IndependentAcceptanceVerifier | None = None,
    ) -> ScenarioVerdict:
        row = self.scenarios.get(scenario_id)
        if row is None:
            raise KeyError(f"unknown acceptance scenario: {scenario_id}")
        required = tuple(str(item) for item in row["evidence_required"])
        if not evidence:
            return self._verdict(
                row,
                status="NOT_RUN",
                missing=(*required, "independent verifier", "holdout corpus"),
                holdout=False,
            )
        scopes = {(item.tenant_id, item.project_id, item.revision) for item in evidence}
        executors = {item.executor_id for item in evidence}
        if len(scopes) != 1 or len(executors) != 1:
            return self._verdict(row, status="BLOCKED", missing=("single bound execution scope",), holdout=False)
        observed = {item.requirement for item in evidence}
        missing = tuple(item for item in required if item not in observed)
        holdout = any(item.corpus_role == "HOLDOUT" for item in evidence)
        if missing or not holdout:
            holdout_gap = ("holdout corpus",) if not holdout else ()
            return self._verdict(row, status="BLOCKED", missing=(*missing, *holdout_gap), holdout=holdout)
        if verifier is None:
            return self._verdict(
                row,
                status="READY_FOR_INDEPENDENT_REVIEW",
                missing=("independent verifier",),
                holdout=True,
            )
        if verifier.verifier_id in executors:
            return self._verdict(row, status="BLOCKED", missing=("independent verifier identity",), holdout=True)
        claim = {
            "schema_version": "elmos.project-intelligence.acceptance-claim.v1",
            "scenario_id": scenario_id,
            "skill": row["skill"],
            "scope": list(next(iter(scopes))),
            "evidence": [item.as_dict() for item in evidence],
        }
        claim_digest = canonical_digest(canonical_value(claim))
        receipt = verifier.verify(claim, evidence)
        if (
            set(receipt) != {"claim_digest", "decision", "receipt_digest", "signature_verified"}
            or receipt.get("claim_digest") != claim_digest
            or receipt.get("decision") != "PASSED"
            or receipt.get("signature_verified") is not True
        ):
            return self._verdict(row, status="REJECTED", missing=("valid independent verifier receipt",), holdout=True)
        receipt_digest = validate_digest(str(receipt["receipt_digest"]))
        return self._verdict(
            row,
            status="PASSED",
            missing=(),
            holdout=True,
            verifier_id=verifier.verifier_id,
            receipt_digest=receipt_digest,
        )

    def verify_all_scenarios(self) -> dict[str, ScenarioVerdict]:
        return {scenario_id: self.verify_scenario(scenario_id) for scenario_id in self.scenarios}
