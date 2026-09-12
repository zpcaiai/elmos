"""Enterprise Telecom Billing & Real-Time Rating Corpus.

Provides subscriber entities, rating plan models, call detail records (CDRs),
and real-time rating procedures for cross-engine database verification.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any


@dataclass
class RatePlanRecord:
    """Cellular tariff and bundle rate plan."""

    plan_id: str
    plan_name: str
    monthly_fee: float
    voice_bundle_minutes: int
    data_bundle_mb: int
    sms_bundle_count: int
    out_of_bundle_voice_rate: float  # per minute
    out_of_bundle_data_rate: float  # per MB
    status: str = "ACTIVE"


@dataclass
class SubscriberRecord:
    """Telecom subscriber profile and wallet."""

    subscriber_id: str
    msisdn: str
    imsi: str
    plan_id: str
    wallet_balance: float = 100.0
    credit_limit: float = 100.0
    home_region_code: str = "REG_BJ"
    account_status: str = "ACTIVE"

    @property
    def total_available_credit(self) -> float:
        """Compute available funds for credit reservation."""
        return self.wallet_balance + self.credit_limit


@dataclass
class QuotaWalletRecord:
    """Real-time free unit quota bucket."""

    wallet_id: str
    subscriber_id: str
    unit_type: str  # MINUTES, MEGABYTES, SMS, MONETARY
    total_units: float
    consumed_units: float = 0.0
    reserved_units: float = 0.0
    cycle_start_date: str = "2026-03-01"
    cycle_end_date: str = "2026-03-31"

    @property
    def remaining_units(self) -> float:
        """Compute available remaining units."""
        return max(0.0, self.total_units - self.consumed_units - self.reserved_units)


@dataclass
class CdrRecord:
    """Call Detail Record (CDR) for consumed network events."""

    cdr_id: str
    subscriber_id: str
    service_type: str  # VOICE, DATA, SMS
    call_direction: str  # MO (Mobile Originated) or MT (Mobile Terminated)
    calling_party: str
    called_party: str
    start_time: str
    duration_seconds: int = 0
    bytes_transferred: int = 0
    cell_tower_id: str = "BTS_001"
    roaming_flag: bool = False
    rated_amount: float = 0.0
    rating_status: str = "UNRATED"


@dataclass
class RatingDiscountRecord:
    """Volume promotion tier discount."""

    discount_id: str
    plan_id: str
    tier_min_volume: float
    tier_max_volume: float
    discount_percentage: float


@dataclass
class RoamingPartnerRecord:
    """Wholesale roaming interconnect agreement."""

    partner_id: str
    carrier_name: str
    country_code: str
    inbound_rate: float
    outbound_rate: float
    settlement_currency: str = "USD"


@dataclass
class MonthlyBillRecord:
    """Consolidated subscriber monthly bill."""

    bill_id: str
    subscriber_id: str
    billing_cycle: str
    base_plan_fee: float
    out_bundle_usage: float
    tax_amount: float
    total_due: float
    paid_status: str = "UNPAID"


@dataclass
class BalanceReservationRecord:
    """Diameter OCS credit control reservation session."""

    session_id: str
    subscriber_id: str
    service_type: str
    reserved_amount: float
    status: str = "ACTIVE"


@dataclass
class CellTowerRecord:
    """Base transceiver station BTS radio node."""

    tower_id: str
    tower_name: str
    latitude: float
    longitude: float
    province_code: str
    status: str = "ONLINE"


@dataclass
class CdcEvent:
    """Change Data Capture (CDC) streaming event."""

    event_id: str
    table_name: str
    operation: str  # INSERT, UPDATE, DELETE
    timestamp_ms: int
    before_state: dict[str, Any] = field(default_factory=dict)
    after_state: dict[str, Any] = field(default_factory=dict)


class TelecomRatingCorpus:
    """Industrial Telecom Rating Workload Suite."""

    domain_name = "Telecom Billing & Rating"
    primary_source_dialect = "oracle"

    @classmethod
    def get_raw_sql_path(cls) -> Path:
        """Return path to raw SQL corpus file."""
        return Path(__file__).with_name("telecom_rating.sql")

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
    def get_seed_rate_plans(cls) -> list[RatePlanRecord]:
        """Generate master cellular plans."""
        return [
            RatePlanRecord(
                "PLAN_5G_UNLIMITED",
                "5G Prime Unlimited",
                129.0,
                500,
                30720,
                200,
                0.15,
                0.00005,
            ),
            RatePlanRecord(
                "PLAN_BASIC_DATA",
                "Standard Data 10GB",
                49.0,
                100,
                10240,
                50,
                0.20,
                0.00008,
            ),
            RatePlanRecord(
                "PLAN_VOICE_PRO",
                "Executive Voice 2000Min",
                88.0,
                2000,
                5120,
                100,
                0.10,
                0.00010,
            ),
        ]

    @classmethod
    def get_seed_subscribers(cls, count: int = 50) -> list[SubscriberRecord]:
        """Generate deterministic subscribers."""
        subs: list[SubscriberRecord] = []
        plans = cls.get_seed_rate_plans()
        for i in range(1, count + 1):
            msisdn = f"1380000{i:04d}"
            imsi = f"4600000000{i:04d}"
            plan = plans[i % len(plans)]
            subs.append(
                SubscriberRecord(
                    subscriber_id=f"SUB_{i:04d}",
                    msisdn=msisdn,
                    imsi=imsi,
                    plan_id=plan.plan_id,
                    wallet_balance=150.0 + (i * 10.0),
                    credit_limit=100.0,
                )
            )
        return subs

    @classmethod
    def get_seed_wallets(cls, subscribers: list[SubscriberRecord]) -> list[QuotaWalletRecord]:
        """Generate voice and data wallets for subscribers."""
        wallets: list[QuotaWalletRecord] = []
        for s in subscribers:
            wallets.append(
                QuotaWalletRecord(
                    wallet_id=f"WLT_V_{s.subscriber_id}",
                    subscriber_id=s.subscriber_id,
                    unit_type="MINUTES",
                    total_units=300.0,
                    consumed_units=20.0,
                )
            )
            wallets.append(
                QuotaWalletRecord(
                    wallet_id=f"WLT_D_{s.subscriber_id}",
                    subscriber_id=s.subscriber_id,
                    unit_type="MEGABYTES",
                    total_units=10240.0,
                    consumed_units=1024.0,
                )
            )
        return wallets

    @classmethod
    def generate_cdr_workload(
        cls, subscribers: list[SubscriberRecord], count: int = 100
    ) -> list[dict[str, Any]]:
        """Generate raw CDR usage traffic events."""
        workload: list[dict[str, Any]] = []
        n = len(subscribers)
        for idx in range(count):
            sub = subscribers[idx % n]
            stype = "VOICE" if idx % 2 == 0 else "DATA"
            dur = 60 + ((idx % 15) * 30) if stype == "VOICE" else 0
            bytes_tf = (5 * 1024 * 1024) + ((idx % 20) * 10 * 1024 * 1024) if stype == "DATA" else 0
            workload.append(
                {
                    "cdr_id": f"CDR_{idx + 1:06d}",
                    "subscriber_id": sub.subscriber_id,
                    "service_type": stype,
                    "duration_seconds": dur,
                    "bytes_transferred": bytes_tf,
                    "calling_party": sub.msisdn,
                    "called_party": "13800009999",
                }
            )
        return workload

    @classmethod
    def rate_voice_cdr_in_memory(
        cls,
        sub: SubscriberRecord,
        plan: RatePlanRecord,
        wallet: QuotaWalletRecord | None,
        duration_seconds: int,
    ) -> tuple[float, float, str]:
        """Rate voice call duration with quota wallet depletion and overage pricing."""
        dur_minutes = float(math.ceil(duration_seconds / 60.0))
        consumed_from_wallet = 0.0
        charged_amount = 0.0

        if wallet and wallet.unit_type == "MINUTES":
            available = wallet.remaining_units
            if available >= dur_minutes:
                wallet.consumed_units += dur_minutes
                consumed_from_wallet = dur_minutes
                return 0.0, consumed_from_wallet, "RATED_FROM_WALLET"
            else:
                consumed_from_wallet = available
                wallet.consumed_units += available
                overage_min = dur_minutes - available
                v_rate = Decimal(str(plan.out_of_bundle_voice_rate))
                amt_dec = (Decimal(str(overage_min)) * v_rate).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
                charged_amount = float(amt_dec)

        else:
            charged_amount = float(
                (Decimal(str(dur_minutes)) * Decimal(str(plan.out_of_bundle_voice_rate))).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
            )

        sub.wallet_balance -= charged_amount
        return charged_amount, consumed_from_wallet, "RATED_OVERAGE"

    @classmethod
    def rate_data_cdr_in_memory(
        cls,
        sub: SubscriberRecord,
        plan: RatePlanRecord,
        wallet: QuotaWalletRecord | None,
        bytes_transferred: int,
    ) -> tuple[float, float, str]:
        """Rate mobile data consumption with quota wallet depletion and overage pricing."""
        mb_used = bytes_transferred / (1024.0 * 1024.0)
        consumed_from_wallet = 0.0
        charged_amount = 0.0

        if wallet and wallet.unit_type == "MEGABYTES":
            available = wallet.remaining_units
            if available >= mb_used:
                wallet.consumed_units += mb_used
                consumed_from_wallet = mb_used
                return 0.0, consumed_from_wallet, "RATED_FROM_WALLET"
            else:
                consumed_from_wallet = available
                wallet.consumed_units += available
                overage_mb = mb_used - available
                d_rate = Decimal(str(plan.out_of_bundle_data_rate))
                amt_dec = (Decimal(str(overage_mb)) * d_rate).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
                charged_amount = float(amt_dec)
        else:
            charged_amount = float(
                (Decimal(str(mb_used)) * Decimal(str(plan.out_of_bundle_data_rate))).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
            )

        sub.wallet_balance -= charged_amount
        return charged_amount, consumed_from_wallet, "RATED_OVERAGE"

    @classmethod
    def reserve_ocs_credit(
        cls, sub: SubscriberRecord, requested_amount: float
    ) -> tuple[bool, str, BalanceReservationRecord | None]:
        """Reserve credit balance during Diameter online charging session."""
        if sub.total_available_credit < requested_amount:
            return False, "DENIED_INSUFFICIENT_CREDIT", None

        sub.wallet_balance -= requested_amount
        sid = f"SES_{int(time.time() * 1000)}_{random.randint(100, 999)}"
        res = BalanceReservationRecord(
            session_id=sid,
            subscriber_id=sub.subscriber_id,
            service_type="VOICE",
            reserved_amount=requested_amount,
            status="ACTIVE",
        )
        return True, "APPROVED", res

    @classmethod
    def commit_ocs_credit(
        cls, sub: SubscriberRecord, reservation: BalanceReservationRecord, actual_consumed: float
    ) -> tuple[bool, float]:
        """Finalize reservation session and return unconsumed reserved amount to balance."""
        if reservation.status != "ACTIVE":
            return False, 0.0

        refund = max(0.0, reservation.reserved_amount - actual_consumed)
        sub.wallet_balance += refund
        reservation.status = "COMMITTED"
        return True, refund

    @classmethod
    def verify_quota_depletion_monotonicity(
        cls, before_wallet: QuotaWalletRecord, after_wallet: QuotaWalletRecord
    ) -> tuple[bool, str]:
        """Verify that consumed quota units only ever increase during normal rating."""
        if after_wallet.consumed_units < before_wallet.consumed_units:
            return (
                False,
                f"Consumed units decreased from {before_wallet.consumed_units} "
                f"to {after_wallet.consumed_units}",
            )
        return True, "PASSED"

    @classmethod
    def verify_monthly_bill_calculation(
        cls, plan: RatePlanRecord, out_of_bundle_usage: float, bill: MonthlyBillRecord
    ) -> tuple[bool, list[str]]:
        """Verify subscriber invoice calculation and tax withholding."""
        errors: list[str] = []
        expected_base = plan.monthly_fee
        taxable_base = Decimal(str(expected_base)) + Decimal(str(out_of_bundle_usage))
        tax_dec = (taxable_base * Decimal("0.06")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        expected_tax = float(tax_dec)
        expected_total = expected_base + out_of_bundle_usage + expected_tax

        if abs(bill.base_plan_fee - expected_base) > 0.001:
            errors.append(f"Base fee {bill.base_plan_fee} != expected {expected_base}")
        if abs(bill.tax_amount - expected_tax) > 0.001:
            errors.append(f"Tax {bill.tax_amount} != expected {expected_tax}")
        if abs(bill.total_due - expected_total) > 0.001:
            errors.append(f"Total {bill.total_due} != expected {expected_total}")

        return len(errors) == 0, errors

    @classmethod
    def simulate_cdc_stream(cls, cdrs: list[CdrRecord]) -> list[CdcEvent]:
        """Generate CDC change event stream for real-time replication verification."""
        events: list[CdcEvent] = []
        base_ts = int(time.time() * 1000)

        for idx, c in enumerate(cdrs):
            events.append(
                CdcEvent(
                    event_id=f"EVT_TEL_{idx + 1:08d}",
                    table_name="tel_cdr_records",
                    operation="INSERT",
                    timestamp_ms=base_ts + idx * 5,
                    before_state={},
                    after_state={
                        "cdr_id": c.cdr_id,
                        "subscriber_id": c.subscriber_id,
                        "service_type": c.service_type,
                        "call_direction": c.call_direction,
                        "duration_seconds": c.duration_seconds,
                        "bytes_transferred": c.bytes_transferred,
                        "rated_amount": c.rated_amount,
                        "rating_status": c.rating_status,
                    },
                )
            )
        return events

    @classmethod
    def simulate_concurrent_cdr_rating_stress(
        cls,
        concurrency: int = 16,
        cdrs_per_worker: int = 50,
    ) -> dict[str, Any]:
        """Simulate high-throughput CDR ingestion and rating pipeline."""
        plans = cls.get_seed_rate_plans()
        plan_map = {p.plan_id: p for p in plans}
        subscribers = cls.get_seed_subscribers(count=100)
        wallets = cls.get_seed_wallets(subscribers)
        wallet_map = {f"{w.subscriber_id}_{w.unit_type}": w for w in wallets}

        latencies_ms: list[float] = []
        rated_voice_count = 0
        rated_data_count = 0
        total_charged = 0.0

        start_time = time.time()
        for worker_id in range(concurrency):
            for c_idx in range(cdrs_per_worker):
                t0 = time.time()
                sub_i = (worker_id * 5 + c_idx) % len(subscribers)
                sub = subscribers[sub_i]
                plan = plan_map[sub.plan_id]

                if c_idx % 2 == 0:
                    # Voice
                    w_key = f"{sub.subscriber_id}_MINUTES"
                    w = wallet_map.get(w_key)
                    dur = 120 + ((c_idx % 10) * 30)
                    cost, _, _ = cls.rate_voice_cdr_in_memory(sub, plan, w, dur)
                    rated_voice_count += 1
                else:
                    # Data
                    w_key = f"{sub.subscriber_id}_MEGABYTES"
                    w = wallet_map.get(w_key)
                    bytes_tf = (20 * 1024 * 1024) + ((c_idx % 10) * 50 * 1024 * 1024)
                    cost, _, _ = cls.rate_data_cdr_in_memory(sub, plan, w, bytes_tf)
                    rated_data_count += 1

                t1 = time.time()
                latencies_ms.append((t1 - t0) * 1000.0)
                total_charged += cost

        total_duration = max(0.001, time.time() - start_time)
        latencies_ms.sort()
        p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        return {
            "total_cdrs_rated": len(latencies_ms),
            "rated_voice_count": rated_voice_count,
            "rated_data_count": rated_data_count,
            "total_charged_amount": total_charged,
            "total_duration_sec": total_duration,
            "throughput_tps": len(latencies_ms) / total_duration,
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "p99_latency_ms": p99,
        }
