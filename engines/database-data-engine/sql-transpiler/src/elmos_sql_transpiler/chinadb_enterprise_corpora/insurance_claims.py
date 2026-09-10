"""Enterprise Insurance & Actuarial Claims Corpus.

Provides production life & casualty insurance schemas, policy life-cycle tables,
claims adjudication procedures, actuarial reserve registers, and test workloads.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any


@dataclass
class ProductRecord:
    """Insurance product catalogue specification."""

    product_code: str
    product_name: str
    line_of_business: str  # LIFE, HEALTH, AUTO, PROPERTY, CASUALTY
    coverage_type: str
    min_sum_assured: float
    max_sum_assured: float
    standard_premium_rate: float
    status: str = "ACTIVE"


@dataclass
class PolicyholderRecord:
    """Insurance policyholder master record."""

    holder_id: str
    id_card_no: str
    full_name: str
    gender: str = "MALE"
    smoker_status: bool = False
    credit_score: int = 720
    risk_level: int = 1


@dataclass
class PolicyRecord:
    """Insurance underwriting contract."""

    policy_no: str
    product_code: str
    holder_id: str
    sum_assured: float
    annual_premium: float
    payment_frequency: str = "ANNUAL"
    policy_status: str = "IN_FORCE"
    start_date: str = "2026-01-01"
    end_date: str = "2027-01-01"


@dataclass
class BeneficiaryRecord:
    """Policy designated beneficiary and ratio."""

    beneficiary_id: str
    policy_no: str
    beneficiary_name: str
    relationship: str
    share_percentage: float = 100.0


@dataclass
class InvoiceRecord:
    """Premium billing invoice schedule."""

    invoice_no: str
    policy_no: str
    due_date: str
    billed_amount: float
    paid_amount: float = 0.0
    invoice_status: str = "UNPAID"


@dataclass
class ClaimRecord:
    """First notice of loss and claims adjudication."""

    claim_no: str
    policy_no: str
    incident_date: str
    reported_date: str
    claim_amount: float
    approved_amount: float = 0.0
    claim_status: str = "REPORTED"
    adjudicator_id: str = ""
    denial_reason: str = ""


@dataclass
class AssessmentRecord:
    """Loss adjuster field assessment report."""

    assessment_id: str
    claim_no: str
    adjuster_name: str
    estimated_loss: float
    salvage_value: float = 0.0
    notes: str = ""


@dataclass
class PayoutRecord:
    """Settled claim payout disbursement wire receipt."""

    payout_id: str
    claim_no: str
    beneficiary_id: str
    disbursed_amount: float
    bank_account_no: str
    payout_status: str = "COMPLETED"


@dataclass
class ReserveRecord:
    """Actuarial reserve liability under IFRS 17."""

    reserve_id: str
    valuation_date: str
    product_code: str
    accident_year: int
    case_reserve: float
    ibnr_reserve: float
    risk_adjustment: float
    csm_amount: float
    discounted_reserve: float


@dataclass
class ReinsuranceTreatyRecord:
    """Reinsurance proportional or surplus treaty."""

    treaty_code: str
    reinsurer_name: str
    treaty_type: str  # QUOTA_SHARE, SURPLUS, EXCESS_OF_LOSS
    retention_limit: float
    cession_percentage: float
    effective_year: int = 2026


@dataclass
class LossTriangleRecord:
    """Actuarial claims run-off development triangle."""

    origin_year: int
    development_year: int
    line_of_business: str
    cumulative_paid: float
    incurred_claims: float


@dataclass
class CdcEvent:
    """Change Data Capture (CDC) streaming event."""

    event_id: str
    table_name: str
    operation: str  # INSERT, UPDATE, DELETE
    timestamp_ms: int
    before_state: dict[str, Any] = field(default_factory=dict)
    after_state: dict[str, Any] = field(default_factory=dict)


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
    def parse_statements(cls) -> list[str]:
        """Split corpus into individual executable SQL statements."""
        raw = cls.get_raw_sql()
        stmts: list[str] = []
        cur: list[str] = []
        in_plsql = False

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("--"):
                continue

            if any(
                stripped.upper().startswith(kw)
                for kw in ("CREATE OR REPLACE PROCEDURE", "CREATE OR REPLACE TRIGGER", "BEGIN")
            ):
                in_plsql = True

            cur.append(line)

            if in_plsql:
                if stripped == "/":
                    stmts.append("\n".join(cur[:-1]).strip())
                    cur = []
                    in_plsql = False
            else:
                if stripped.endswith(";"):
                    joined = "\n".join(cur).strip()
                    if joined.endswith(";"):
                        joined = joined[:-1].strip()
                    stmts.append(joined)
                    cur = []

        if cur:
            tail = "\n".join(cur).strip()
            if tail:
                stmts.append(tail)

        return [s for s in stmts if s]

    @classmethod
    def get_seed_products(cls) -> list[ProductRecord]:
        """Generate master catalogue products."""
        return [
            ProductRecord(
                "PROD_TERM_LIFE",
                "Term Life 20 Year",
                "LIFE",
                "DEATH_BENEFIT",
                100000.0,
                5000000.0,
                0.0015,
            ),
            ProductRecord(
                "PROD_CRITICAL_ILL",
                "Critical Illness Comprehensive",
                "HEALTH",
                "ILLNESS",
                50000.0,
                2000000.0,
                0.0035,
            ),
            ProductRecord(
                "PROD_AUTO_COMP",
                "Motor Vehicle Comprehensive",
                "AUTO",
                "COLLISION",
                30000.0,
                1000000.0,
                0.0250,
            ),
            ProductRecord(
                "PROD_COMM_PROP",
                "Commercial Property & Fire",
                "PROPERTY",
                "PROPERTY_DAMAGE",
                500000.0,
                50000000.0,
                0.0008,
            ),
        ]

    @classmethod
    def get_seed_policyholders(cls, count: int = 50) -> list[PolicyholderRecord]:
        """Generate deterministic master policyholders."""
        holders: list[PolicyholderRecord] = []
        for i in range(1, count + 1):
            holders.append(
                PolicyholderRecord(
                    holder_id=f"HLD_{i:04d}",
                    id_card_no=f"ID_H_{i:08d}",
                    full_name=f"Insured Customer {i}",
                    gender="FEMALE" if i % 2 == 0 else "MALE",
                    smoker_status=(i % 4 == 0),
                    credit_score=680 + (i % 120),
                    risk_level=2 if i % 6 == 0 else 1,
                )
            )
        return holders

    @classmethod
    def get_seed_policies(cls, count: int = 50) -> list[PolicyRecord]:
        """Generate deterministic underwriting policies."""
        policies: list[PolicyRecord] = []
        products = cls.get_seed_products()
        for i in range(1, count + 1):
            prod = products[i % len(products)]
            sum_ass = prod.min_sum_assured + (i * 10000.0)
            if sum_ass > prod.max_sum_assured:
                sum_ass = prod.max_sum_assured
            premium = sum_ass * prod.standard_premium_rate
            policies.append(
                PolicyRecord(
                    policy_no=f"POL_{i:04d}",
                    product_code=prod.product_code,
                    holder_id=f"HLD_{i:04d}",
                    sum_assured=sum_ass,
                    annual_premium=premium,
                )
            )
        return policies

    @classmethod
    def generate_claims_workload(
        cls, policies: list[PolicyRecord], count: int = 100
    ) -> list[dict[str, Any]]:
        """Generate claims filing requests."""
        workload: list[dict[str, Any]] = []
        n = len(policies)
        for idx in range(count):
            pol = policies[idx % n]
            claim_amt = pol.sum_assured * (0.05 + ((idx % 10) * 0.05))
            workload.append(
                {
                    "workload_id": f"WL_CLM_{idx + 1:06d}",
                    "policy_no": pol.policy_no,
                    "incident_date": "2026-02-15",
                    "reported_date": "2026-02-18",
                    "claim_amount": claim_amt,
                    "product_code": pol.product_code,
                }
            )
        return workload

    @classmethod
    def adjudicate_in_memory_claim(
        cls,
        policy: PolicyRecord,
        claim_amount: float,
        decision: str = "APPROVE",
        deductible_ratio: float = 0.05,
    ) -> tuple[bool, str, ClaimRecord, list[PayoutRecord]]:
        """Simulate claims adjudication and automatic payout disbursement."""
        if policy.policy_status != "IN_FORCE":
            return False, "POLICY_NOT_IN_FORCE", ClaimRecord("", "", "", "", 0.0), []

        if claim_amount > policy.sum_assured:
            return False, "CLAIM_EXCEEDS_SUM_ASSURED", ClaimRecord("", "", "", "", 0.0), []

        claim_no = f"CLM_{int(time.time() * 1000)}_{random.randint(100, 999)}"
        if decision == "REJECT":
            clm = ClaimRecord(
                claim_no=claim_no,
                policy_no=policy.policy_no,
                incident_date="2026-02-15",
                reported_date="2026-02-18",
                claim_amount=claim_amount,
                claim_status="REJECTED",
                adjudicator_id="ADJ_AUTO_01",
                denial_reason="Policy exclusion criteria triggered",
            )
            return True, "REJECTED", clm, []

        approved_amt = max(0.0, claim_amount * (1.0 - deductible_ratio))
        clm = ClaimRecord(
            claim_no=claim_no,
            policy_no=policy.policy_no,
            incident_date="2026-02-15",
            reported_date="2026-02-18",
            claim_amount=claim_amount,
            approved_amount=approved_amt,
            claim_status="APPROVED",
            adjudicator_id="ADJ_AUTO_01",
        )

        payout = PayoutRecord(
            payout_id=f"PAY_{claim_no}",
            claim_no=claim_no,
            beneficiary_id=f"BEN_{policy.policy_no}",
            disbursed_amount=approved_amt,
            bank_account_no=f"622202_{policy.holder_id}",
            payout_status="COMPLETED",
        )

        return True, "APPROVED", clm, [payout]

    @classmethod
    def calculate_ibnr_chain_ladder(
        cls,
        triangle: list[LossTriangleRecord],
        origin_year: int,
        link_ratio: float = 1.25,
    ) -> float:
        """Estimate ultimate incurred losses using standard actuarial Chain Ladder method."""
        relevant = [r for r in triangle if r.origin_year == origin_year]
        if not relevant:
            return 0.0
        latest = max(relevant, key=lambda r: r.development_year)
        ultimate = Decimal(str(latest.cumulative_paid)) * Decimal(str(link_ratio))
        return float(ultimate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

    @classmethod
    def verify_claim_sum_assured_boundary(
        cls, policy: PolicyRecord, claim: ClaimRecord
    ) -> tuple[bool, str]:
        """Verify that claim and payout never exceed policy sum assured."""
        if claim.claim_amount > policy.sum_assured:
            return False, f"Claim {claim.claim_amount} > Sum Assured {policy.sum_assured}"
        if claim.approved_amount > policy.sum_assured:
            return (
                False,
                f"Approved payout {claim.approved_amount} > Sum Assured {policy.sum_assured}",
            )
        return True, "PASSED"

    @classmethod
    def verify_beneficiary_allocation_total(
        cls, beneficiaries: list[BeneficiaryRecord]
    ) -> tuple[bool, float, str]:
        """Verify beneficiary share allocations sum to exactly 100%."""
        total = sum(b.share_percentage for b in beneficiaries)
        diff = abs(total - 100.0)
        is_valid = diff < 0.001
        msg = f"Beneficiary total share: {total:.2f}% (delta: {diff:.4f})"
        return is_valid, total, msg

    @classmethod
    def simulate_cdc_stream(cls, claims: list[ClaimRecord]) -> list[CdcEvent]:
        """Generate CDC change event stream for real-time replication verification."""
        events: list[CdcEvent] = []
        base_ts = int(time.time() * 1000)

        for idx, c in enumerate(claims):
            events.append(
                CdcEvent(
                    event_id=f"EVT_INS_{idx + 1:08d}",
                    table_name="ins_claims",
                    operation="INSERT",
                    timestamp_ms=base_ts + idx * 5,
                    before_state={},
                    after_state={
                        "claim_no": c.claim_no,
                        "policy_no": c.policy_no,
                        "incident_date": c.incident_date,
                        "reported_date": c.reported_date,
                        "claim_amount": c.claim_amount,
                        "approved_amount": c.approved_amount,
                        "claim_status": c.claim_status,
                    },
                )
            )
        return events

    @classmethod
    def simulate_concurrent_claims_stress(
        cls,
        concurrency: int = 16,
        claims_per_worker: int = 50,
    ) -> dict[str, Any]:
        """Simulate high-concurrency claims adjudication and settlement."""
        policies = cls.get_seed_policies(count=100)
        pol_map = {p.policy_no: p for p in policies}

        latencies_ms: list[float] = []
        approved_count = 0
        rejected_count = 0
        all_payouts: list[PayoutRecord] = []

        start_time = time.time()
        for worker_id in range(concurrency):
            for c_idx in range(claims_per_worker):
                t0 = time.time()
                pol_i = (worker_id * 3 + c_idx) % len(policies)
                pol = policies[pol_i]
                amt = pol.sum_assured * (0.05 + ((c_idx % 8) * 0.05))

                ok, decision, clm, payouts = cls.adjudicate_in_memory_claim(
                    pol, amt, decision="APPROVE" if c_idx % 10 != 0 else "REJECT"
                )
                t1 = time.time()
                latencies_ms.append((t1 - t0) * 1000.0)

                if decision == "APPROVED":
                    approved_count += 1
                    all_payouts.extend(payouts)
                elif decision == "REJECTED":
                    rejected_count += 1

        total_duration = max(0.001, time.time() - start_time)
        latencies_ms.sort()
        p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        # Invariant checks
        boundary_violations = 0
        for pay in all_payouts:
            matching = [p for p in pol_map.values() if f"BEN_{p.policy_no}" == pay.beneficiary_id]
            if matching and pay.disbursed_amount > matching[0].sum_assured:
                boundary_violations += 1


        return {
            "total_claims_processed": len(latencies_ms),
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "total_payout_amount": sum(p.disbursed_amount for p in all_payouts),
            "total_duration_sec": total_duration,
            "throughput_tps": len(latencies_ms) / total_duration,
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "p99_latency_ms": p99,
            "boundary_violations": boundary_violations,
        }
