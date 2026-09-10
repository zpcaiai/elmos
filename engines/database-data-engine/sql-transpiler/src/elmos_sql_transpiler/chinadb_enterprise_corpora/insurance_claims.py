"""Enterprise Insurance & Actuarial Claims Corpus.

Provides production life & casualty insurance schemas, policy life-cycle tables,
claims adjudication procedures, actuarial reserve registers, and test workloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PolicyholderRecord:
    """Insurance policyholder profile."""

    holder_id: str
    id_card_no: str
    full_name: str
    phone_number: str
    credit_rating: str = "AAA"
    risk_level: int = 1


@dataclass
class PolicyRecord:
    """Insurance contract entity."""

    policy_no: str
    holder_id: str
    product_type: str
    sum_insured: float
    deductible: float
    premium: float
    start_date: str
    end_date: str
    policy_status: str = "IN_FORCE"


class InsuranceClaimsCorpus:
    """Industrial Insurance & Claims Workload Suite."""

    domain_name = "Insurance & Actuarial Claims"
    primary_source_dialect = "oracle"

    @classmethod
    def get_raw_sql_path(cls) -> Path:
        """Return path to raw SQL corpus file."""
        return Path(__file__).with_name("insurance_claims.sql")

    @classmethod
    def get_raw_sql(cls) -> str:
        """Load full raw SQL corpus text."""
        return cls.get_raw_sql_path().read_text(encoding="utf-8")

    @classmethod
    def get_seed_policies(cls, count: int = 40) -> list[PolicyRecord]:
        policies: list[PolicyRecord] = []
        product_types = [
            "AUTO_COLLISION",
            "HEALTH_CRITICAL",
            "PROPERTY_FIRE",
            "COMMERCIAL_LIABILITY",
        ]
        for i in range(1, count + 1):
            pol_no = f"POL_{i:08d}"
            holder_id = f"HLD_{i:06d}"
            ptype = product_types[i % len(product_types)]
            sum_ins = 50000.0 * (1 + (i % 10))
            deductible = 500.0 if "AUTO" in ptype else 1000.0
            premium = sum_ins * 0.02
            policies.append(
                PolicyRecord(
                    policy_no=pol_no,
                    holder_id=holder_id,
                    product_type=ptype,
                    sum_insured=sum_ins,
                    deductible=deductible,
                    premium=premium,
                    start_date="2026-01-01",
                    end_date="2027-01-01",
                )
            )
        return policies

    @classmethod
    def generate_claims_workload(
        cls, policies: list[PolicyRecord], count: int = 60
    ) -> list[dict[str, Any]]:
        """Generate claims submissions for testing adjudication logic."""
        claims: list[dict[str, Any]] = []
        for idx in range(count):
            pol = policies[idx % len(policies)]
            claimed = 1000.0 + ((idx % 15) * 500.0)
            fraud_score = 15.0 + ((idx * 7) % 80)
            claims.append(
                {
                    "claim_id": f"CLM_{idx + 1:08d}",
                    "policy_no": pol.policy_no,
                    "incident_date": "2026-06-15",
                    "claimed_amount": claimed,
                    "fraud_risk_score": fraud_score,
                    "adjudicator_id": f"ADJ_{1 + (idx % 5):03d}",
                }
            )
        return claims
