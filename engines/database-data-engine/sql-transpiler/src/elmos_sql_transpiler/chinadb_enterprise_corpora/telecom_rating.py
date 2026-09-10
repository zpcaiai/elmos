"""Enterprise Telecom Billing & Real-Time Rating Corpus.

Provides subscriber entities, rating plan models, call detail records (CDRs),
and real-time rating procedures for cross-engine database verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SubscriberRecord:
    """Telecom subscriber profile."""

    msisdn: str
    imsi: str
    customer_id: str
    plan_id: str
    account_balance: float = 100.0
    voice_bucket_seconds: int = 3600
    data_bucket_mb: int = 10240
    status: str = "ACTIVE"


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
    def get_seed_subscribers(cls, count: int = 50) -> list[SubscriberRecord]:
        """Generate deterministic subscribers."""
        subs: list[SubscriberRecord] = []
        for i in range(1, count + 1):
            msisdn = f"138001{i:05d}"
            imsi = f"460001{i:09d}"
            cid = f"CUST_{i:06d}"
            pid = "PLAN_5G_UNLIMITED" if i % 2 == 0 else "PLAN_STANDARD"
            subs.append(
                SubscriberRecord(
                    msisdn=msisdn,
                    imsi=imsi,
                    customer_id=cid,
                    plan_id=pid,
                    account_balance=150.0 + (i * 10.0),
                )
            )
        return subs

    @classmethod
    def generate_cdr_workload(
        cls, subscribers: list[SubscriberRecord], count: int = 80
    ) -> list[dict[str, Any]]:
        """Generate synthetic Call Detail Records (CDRs)."""
        cdrs: list[dict[str, Any]] = []
        for idx in range(count):
            sub = subscribers[idx % len(subscribers)]
            is_voice = (idx % 2 == 0)
            service_type = "VOICE" if is_voice else "DATA"
            duration = (30 + (idx * 15)) % 600 if is_voice else 0
            data_bytes = ((idx + 1) * 5 * 1024 * 1024) if not is_voice else 0
            cdrs.append(
                {
                    "cdr_id": f"CDR_{idx + 1:08d}",
                    "caller_msisdn": sub.msisdn,
                    "callee_msisdn": "13900000000",
                    "service_type": service_type,
                    "start_time": "2026-07-01 10:00:00",
                    "duration_seconds": duration,
                    "data_bytes": data_bytes,
                    "roaming_flag": 1 if idx % 10 == 0 else 0,
                }
            )
        return cdrs
