"""Core Banking & Double-Entry Settlement Enterprise Corpus.

Provides production banking schemas, stored procedures, triggers, views,
and transaction workloads designed for cross-engine database migration verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AccountRecord:
    """Core banking account representation."""

    account_no: str
    customer_id: str
    account_type: str
    currency_code: str = "CNY"
    balance: float = 0.0
    frozen_balance: float = 0.0
    status: str = "ACTIVE"
    interest_rate: float = 0.0035


@dataclass
class LedgerEntry:
    """Double-entry general ledger journal entry."""

    ledger_id: str
    account_no: str
    journal_id: str
    entry_type: str  # "DEBIT" or "CREDIT"
    amount: float
    running_balance: float
    currency_code: str = "CNY"
    description: str = ""


class BankingSettlementCorpus:
    """Industrial Core Banking & Settlement Workload Suite."""

    domain_name = "Core Banking & Settlement"
    primary_source_dialect = "oracle"

    @classmethod
    def get_raw_sql_path(cls) -> Path:
        """Return path to raw SQL corpus file."""
        return Path(__file__).with_name("banking_settlement.sql")

    @classmethod
    def get_raw_sql(cls) -> str:
        """Load full raw SQL corpus text."""
        return cls.get_raw_sql_path().read_text(encoding="utf-8")

    @classmethod
    def get_seed_accounts(cls, count: int = 50) -> list[AccountRecord]:
        """Generate deterministic seed accounts for settlement verification."""
        accounts: list[AccountRecord] = []
        for i in range(1, count + 1):
            acc_no = f"622202{i:010d}"
            cust_id = f"CUST_{i:06d}"
            acc_type = "SAVINGS" if i % 3 != 0 else "CHECKING"
            balance = 10000.0 + (i * 250.0)
            accounts.append(
                AccountRecord(
                    account_no=acc_no,
                    customer_id=cust_id,
                    account_type=acc_type,
                    balance=balance,
                )
            )
        return accounts

    @classmethod
    def generate_transfer_workload(
        cls, accounts: list[AccountRecord], count: int = 100
    ) -> list[dict[str, Any]]:
        """Generate atomic transfer workloads between seed accounts."""
        workloads: list[dict[str, Any]] = []
        n = len(accounts)
        if n < 2:
            return workloads

        for idx in range(count):
            src_idx = idx % n
            tgt_idx = (idx + 1) % n
            amount = 10.0 + ((idx % 20) * 5.0)
            fee = 1.0 if idx % 5 == 0 else 0.0
            workloads.append(
                {
                    "workload_id": f"WL_TRF_{idx + 1:06d}",
                    "src_account": accounts[src_idx].account_no,
                    "tgt_account": accounts[tgt_idx].account_no,
                    "amount": amount,
                    "fee": fee,
                    "channel": "MOBILE_BANKING",
                }
            )
        return workloads

    @classmethod
    def verify_double_entry_conservation(
        cls, entries: list[LedgerEntry]
    ) -> tuple[bool, float, list[str]]:
        """Verify fundamental conservation invariant: Total Debits == Total Credits."""
        by_journal: dict[str, list[LedgerEntry]] = {}
        for e in entries:
            by_journal.setdefault(e.journal_id, []).append(e)

        discrepancies: list[str] = []
        total_imbalance = 0.0

        for jid, group in by_journal.items():
            debits = sum(e.amount for e in group if e.entry_type == "DEBIT")
            credits = sum(e.amount for e in group if e.entry_type == "CREDIT")
            diff = abs(debits - credits)
            if diff > 0.0001:
                discrepancies.append(
                    f"Journal {jid} imbalance: Debit {debits:.4f} != Credit {credits:.4f} "
                    f"(diff: {diff:.4f})"
                )
                total_imbalance += diff

        return (len(discrepancies) == 0, total_imbalance, discrepancies)
