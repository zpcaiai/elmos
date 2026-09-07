"""Domain aggregates, enums, and data models for Functional Assurance & Certification."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import time
from typing import Any, Mapping


class AssuranceLevel(str, Enum):
    E0 = "E0"  # Undeclared / Unverified
    E1 = "E1"  # Syntactic & Schema Validated
    E2 = "E2"  # Local Unit & Contract Provenance
    E3 = "E3"  # Integrated Metamorphic & Fuzz Verification
    E4 = "E4"  # Formal Machine-Checked Proof & Differential Oracle
    E5 = "E5"  # Complete Independent TEVV & Accredited Certificate


class ProductAssuranceLevel(str, Enum):
    P01 = "P01"  # Basic Sandbox Verified
    P02 = "P02"  # Regression & Mutation Verified
    P03 = "P03"  # Production Profile & SLSA L3 Sealed
    P04 = "P04"  # Cross-Environment & Fault-Injection Hardened
    P05 = "P05"  # Regulated Sector Certified & Accredited Conformity


class CertificateStatus(str, Enum):
    DRAFT = "DRAFT"
    EVALUATING = "EVALUATING"
    ISSUED = "ISSUED"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class DecisionRuleType(str, Enum):
    BINARY_SIMPLE = "BINARY_SIMPLE"
    GUARD_BAND_EXPANDED = "GUARD_BAND_EXPANDED"
    GUARD_BAND_GUARDED = "GUARD_BAND_GUARDED"
    SHARED_RISK = "SHARED_RISK"


class ConformityDecision(str, Enum):
    CONFORMING = "CONFORMING"
    NON_CONFORMING = "NON_CONFORMING"
    CONDITIONAL_CONFORMING = "CONDITIONAL_CONFORMING"
    INDETERMINATE = "INDETERMINATE"


class SectorType(str, Enum):
    AVIATION = "AVIATION"  # DO-178C / DO-330 / ED-12C
    MEDICAL = "MEDICAL"  # IEC 62304 / ISO 14971 / FDA AI/ML SaMD
    AUTOMOTIVE = "AUTOMOTIVE"  # ISO 26262 ASIL-D / ISO 21448 SOTIF / ISO 21434
    RAIL = "RAIL"  # EN 50128 / EN 50657 SIL-4
    FINANCIAL = "FINANCIAL"  # SR 11-7 / OCC 2011-12 / Basel III/IV
    INDUSTRIAL = "INDUSTRIAL"  # IEC 61508 SIL-3 / IEC 62443
    PUBLIC_SECTOR = "PUBLIC_SECTOR"  # EU AI Act High-Risk / NIST AI RMF
    AUTONOMOUS_SYSTEMS = "AUTONOMOUS_SYSTEMS"  # UL 4600 / IEEE 7000 / MIL-STD-882E


@dataclass(frozen=True)
class FunctionalAssuranceContext:
    """Security and tenant boundary for functional assurance execution."""
    tenant_id: str
    project_id: str
    execution_epoch: str
    fencing_token: int
    candidate_digest: str
    base_evidence_receipt: str
    authority_digest: str
    request_timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.tenant_id.strip():
            raise ValueError("tenant_id must not be empty (fail-closed)")
        if not self.project_id or not self.project_id.strip():
            raise ValueError("project_id must not be empty (fail-closed)")
        if not self.candidate_digest or len(self.candidate_digest) < 32:
            raise ValueError("candidate_digest must be a valid SHA-256 digest")
        if self.fencing_token < 0:
            raise ValueError("fencing_token must be non-negative")


@dataclass(frozen=True)
class UncertaintyComponent:
    name: str
    value: float
    distribution: str  # 'NORMAL', 'RECTANGULAR', 'TRIANGULAR', 'U_SHAPED'
    degrees_of_freedom: int = 100

    @property
    def standard_uncertainty(self) -> float:
        if self.distribution == "NORMAL":
            return self.value
        if self.distribution == "RECTANGULAR":
            return self.value / math.sqrt(3.0)
        if self.distribution == "TRIANGULAR":
            return self.value / math.sqrt(6.0)
        if self.distribution == "U_SHAPED":
            return self.value / math.sqrt(2.0)
        return self.value


@dataclass(frozen=True)
class MeasurementUncertaintyBudget:
    """ISO/IEC Guide 98-3 (GUM) and ILAC G17 compliant uncertainty budget."""
    measurand: str
    nominal_value: float
    components: list[UncertaintyComponent]
    coverage_factor_k: float = 2.0  # 95.45% confidence interval

    @property
    def combined_standard_uncertainty(self) -> float:
        variance_sum = sum(c.standard_uncertainty ** 2 for c in self.components)
        return math.sqrt(variance_sum)

    @property
    def expanded_uncertainty(self) -> float:
        return self.coverage_factor_k * self.combined_standard_uncertainty

    def to_dict(self) -> dict[str, Any]:
        return {
            "measurand": self.measurand,
            "nominal_value": self.nominal_value,
            "combined_standard_uncertainty": round(self.combined_standard_uncertainty, 6),
            "expanded_uncertainty": round(self.expanded_uncertainty, 6),
            "coverage_factor_k": self.coverage_factor_k,
            "confidence_interval_percent": 95.45,
            "components": [
                {
                    "name": c.name,
                    "value": c.value,
                    "distribution": c.distribution,
                    "standard_uncertainty": round(c.standard_uncertainty, 6),
                }
                for c in self.components
            ],
        }


@dataclass(frozen=True)
class GuardBandSpecification:
    """ILAC G8:09/2019 decision rule with guard banding."""
    lower_spec_limit: float | None
    upper_spec_limit: float | None
    rule_type: DecisionRuleType = DecisionRuleType.GUARD_BAND_EXPANDED
    target_producer_risk: float = 0.02
    target_consumer_risk: float = 0.01

    def evaluate_conformity(self, measured_value: float, uncertainty: float) -> ConformityDecision:
        guard = uncertainty
        if self.upper_spec_limit is not None and self.lower_spec_limit is not None:
            if measured_value > self.upper_spec_limit or measured_value < self.lower_spec_limit:
                return ConformityDecision.NON_CONFORMING
            if (measured_value + guard) <= self.upper_spec_limit and (measured_value - guard) >= self.lower_spec_limit:
                return ConformityDecision.CONFORMING
            return ConformityDecision.CONDITIONAL_CONFORMING
        elif self.upper_spec_limit is not None:
            if measured_value > self.upper_spec_limit:
                return ConformityDecision.NON_CONFORMING
            if (measured_value + guard) <= self.upper_spec_limit:
                return ConformityDecision.CONFORMING
            return ConformityDecision.CONDITIONAL_CONFORMING
        elif self.lower_spec_limit is not None:
            if measured_value < self.lower_spec_limit:
                return ConformityDecision.NON_CONFORMING
            if (measured_value - guard) >= self.lower_spec_limit:
                return ConformityDecision.CONFORMING
            return ConformityDecision.CONDITIONAL_CONFORMING
        return ConformityDecision.INDETERMINATE


@dataclass
class WormMerkleLeaf:
    index: int
    data_hash: str
    role: str
    timestamp: str
    prev_leaf_hash: str

    @property
    def leaf_hash(self) -> str:
        payload = f"{self.index}:{self.data_hash}:{self.role}:{self.timestamp}:{self.prev_leaf_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WormMerkleTree:
    """Append-only WORM Merkle tree for immutable evidence sealing."""

    def __init__(self, root_seed: str = "GENESIS_ELMOS_CERT_TREE_V4") -> None:
        self.root_seed = root_seed
        self.leaves: list[WormMerkleLeaf] = []

    def append(self, data: Any, role: str) -> WormMerkleLeaf:
        raw_bytes = json.dumps(data, sort_keys=True).encode("utf-8") if not isinstance(data, (str, bytes)) else (data.encode("utf-8") if isinstance(data, str) else data)
        data_hash = hashlib.sha256(raw_bytes).hexdigest()
        prev_hash = self.leaves[-1].leaf_hash if self.leaves else hashlib.sha256(self.root_seed.encode("utf-8")).hexdigest()
        leaf = WormMerkleLeaf(
            index=len(self.leaves),
            data_hash=data_hash,
            role=role,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            prev_leaf_hash=prev_hash,
        )
        self.leaves.append(leaf)
        return leaf

    @property
    def root_digest(self) -> str:
        if not self.leaves:
            return hashlib.sha256(self.root_seed.encode("utf-8")).hexdigest()
        curr_hashes = [l.leaf_hash for l in self.leaves]
        while len(curr_hashes) > 1:
            if len(curr_hashes) % 2 == 1:
                curr_hashes.append(curr_hashes[-1])
            next_hashes = []
            for i in range(0, len(curr_hashes), 2):
                combined = curr_hashes[i] + curr_hashes[i + 1]
                next_hashes.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
            curr_hashes = next_hashes
        return curr_hashes[0]

    def verify_integrity(self) -> bool:
        if not self.leaves:
            return True
        expected_prev = hashlib.sha256(self.root_seed.encode("utf-8")).hexdigest()
        for idx, leaf in enumerate(self.leaves):
            if leaf.index != idx:
                return False
            if leaf.prev_leaf_hash != expected_prev:
                return False
            expected_prev = leaf.leaf_hash
        return True


@dataclass
class CertificateRecord:
    """Authoritative ISO/IEC 17065 machine-verifiable certificate."""
    certificate_id: str
    subject_candidate_digest: str
    tenant_id: str
    project_id: str
    assurance_level: AssuranceLevel
    product_level: ProductAssuranceLevel
    sector: SectorType | None
    decision: ConformityDecision
    status: CertificateStatus
    scope_description: str
    merkle_root_digest: str
    issued_at: str
    expires_at: str
    evaluator_id: str
    independent_reviewer_id: str
    hsm_key_id: str
    signature_receipt: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "certificate_id": self.certificate_id,
            "subject_candidate_digest": self.subject_candidate_digest,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "assurance_level": self.assurance_level.value,
            "product_level": self.product_level.value,
            "sector": self.sector.value if self.sector else None,
            "decision": self.decision.value,
            "status": self.status.value,
            "scope_description": self.scope_description,
            "merkle_root_digest": self.merkle_root_digest,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "evaluator_id": self.evaluator_id,
            "independent_reviewer_id": self.independent_reviewer_id,
            "hsm_key_id": self.hsm_key_id,
            "signature_receipt": self.signature_receipt,
            "metadata": self.metadata,
        }
