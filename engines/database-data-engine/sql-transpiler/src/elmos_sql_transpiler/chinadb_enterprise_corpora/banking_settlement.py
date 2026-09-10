"""Core Banking & Double-Entry Settlement Enterprise Corpus.

Provides production banking schemas, stored procedures, triggers, views,
and transaction workloads designed for cross-engine database migration verification.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any


@dataclass
class BranchRecord:
    """Branch office metadata."""

    branch_code: str
    branch_name: str
    swift_bic: str
    clearing_code: str
    city_code: str
    operating_status: str = "OPEN"


@dataclass
class CustomerRecord:
    """Core banking customer profile."""

    customer_id: str
    customer_type: str  # INDIVIDUAL or CORPORATE
    id_type: str
    id_number: str
    full_name: str
    risk_rating: str = "R1"
    kyc_status: str = "VERIFIED"
    aml_blacklisted: bool = False


@dataclass
class AccountRecord:
    """Core banking account representation."""

    account_no: str
    customer_id: str
    account_type: str
    currency_code: str = "CNY"
    branch_code: str = "BR001"
    balance: float = 0.0
    frozen_balance: float = 0.0
    overdraft_limit: float = 0.0
    status: str = "ACTIVE"
    interest_rate: float = 0.0035

    @property
    def available_balance(self) -> float:
        """Compute available balance after holds and overdraft limit."""
        return self.balance - self.frozen_balance + self.overdraft_limit


@dataclass
class AccountHoldRecord:
    """Judicial or compliance hold on account."""

    hold_id: str
    account_no: str
    hold_amount: float
    hold_reason: str
    issuing_authority: str
    hold_status: str = "ACTIVE"


@dataclass
class FxRateRecord:
    """FX spot exchange rate entry."""

    base_currency: str
    target_currency: str
    buy_rate: float
    sell_rate: float
    middle_rate: float


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


@dataclass
class SettlementTxRecord:
    """Interbank or internal settlement transaction."""

    tx_id: str
    source_account: str
    target_account: str
    amount: float
    fee_amount: float = 0.0
    currency_code: str = "CNY"
    channel_code: str = "ONLINE"
    tx_status: str = "PENDING"
    reference_code: str = ""


@dataclass
class StandingOrderRecord:
    """Automated recurring transfer order."""

    order_id: str
    source_account: str
    target_account: str
    amount: float
    frequency: str = "MONTHLY"
    status: str = "ACTIVE"


@dataclass
class LoanContractRecord:
    """Commercial or retail loan contract."""

    contract_no: str
    customer_id: str
    disbursement_account: str
    repayment_account: str
    principal_amount: float
    remaining_principal: float
    annual_interest_rate: float
    term_months: int
    repayment_method: str = "EQUAL_INSTALLMENT"
    loan_status: str = "DISBURSED"


@dataclass
class LoanScheduleRecord:
    """Amortization period installment schedule."""

    schedule_id: str
    contract_no: str
    period_number: int
    principal_due: float
    interest_due: float
    total_installment: float
    principal_paid: float = 0.0
    interest_paid: float = 0.0
    payment_status: str = "UNPAID"


@dataclass
class TrialBalanceRecord:
    """End-of-day trial balance entry."""

    balance_date: str
    branch_code: str
    currency_code: str
    total_debit: float
    total_credit: float
    closing_balance: float
    is_balanced: bool = True


@dataclass
class AmlAlertRecord:
    """AML risk scoring and alert record."""

    alert_id: str
    tx_id: str
    account_no: str
    alert_type: str
    severity_level: str
    alert_score: float
    status: str = "OPEN"


@dataclass
class CdcEvent:
    """Change Data Capture (CDC) streaming event."""

    event_id: str
    table_name: str
    operation: str  # INSERT, UPDATE, DELETE
    timestamp_ms: int
    before_state: dict[str, Any] = field(default_factory=dict)
    after_state: dict[str, Any] = field(default_factory=dict)


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
    def get_seed_branches(cls, count: int = 10) -> list[BranchRecord]:
        """Generate deterministic branch offices."""
        branches: list[BranchRecord] = []
        for i in range(1, count + 1):
            branches.append(
                BranchRecord(
                    branch_code=f"BR{i:03d}",
                    branch_name=f"Metropolitan Branch #{i:03d}",
                    swift_bic=f"BKCNBJ{i:02d}",
                    clearing_code=f"CLR_100{i:03d}",
                    city_code=f"{110000 + i}",
                )
            )
        return branches

    @classmethod
    def get_seed_customers(cls, count: int = 50) -> list[CustomerRecord]:
        """Generate deterministic master customer records."""
        customers: list[CustomerRecord] = []
        for i in range(1, count + 1):
            is_corp = (i % 3 == 0)
            customers.append(
                CustomerRecord(
                    customer_id=f"CUST_{i:04d}",
                    customer_type="CORPORATE" if is_corp else "INDIVIDUAL",
                    id_type="UNIFIED_CREDIT_CODE" if is_corp else "NATIONAL_ID",
                    id_number=f"ID_CN_{i:010d}",
                    full_name=f"Enterprise Client {i}" if is_corp else f"Individual Client {i}",
                    risk_rating="R2" if i % 5 == 0 else "R1",
                    kyc_status="VERIFIED",
                    aml_blacklisted=(i % 49 == 0),
                )
            )
        return customers

    @classmethod
    def get_seed_accounts(cls, count: int = 50) -> list[AccountRecord]:
        """Generate deterministic seed accounts for settlement verification."""
        accounts: list[AccountRecord] = []
        for i in range(1, count + 1):
            acc_no = f"622202{i:010d}"
            cust_id = f"CUST_{i:04d}"
            acc_type = "SAVINGS" if i % 3 != 0 else "CHECKING"
            balance = 10000.0 + (i * 250.0)
            overdraft = 5000.0 if acc_type == "CHECKING" else 0.0
            accounts.append(
                AccountRecord(
                    account_no=acc_no,
                    customer_id=cust_id,
                    account_type=acc_type,
                    balance=balance,
                    overdraft_limit=overdraft,
                )
            )
        return accounts

    @classmethod
    def get_seed_fx_rates(cls) -> list[FxRateRecord]:
        """Generate major foreign currency exchange rates."""
        return [
            FxRateRecord("USD", "CNY", 7.1500, 7.1800, 7.1650),
            FxRateRecord("EUR", "CNY", 7.6500, 7.6900, 7.6700),
            FxRateRecord("GBP", "CNY", 9.1000, 9.1500, 9.1250),
            FxRateRecord("JPY", "CNY", 0.0470, 0.0475, 0.04725),
            FxRateRecord("HKD", "CNY", 0.9150, 0.9180, 0.9165),
        ]

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
    def execute_in_memory_transfer(
        cls,
        accounts_map: dict[str, AccountRecord],
        src_acc_no: str,
        tgt_acc_no: str,
        amount: float,
        fee: float = 0.0,
    ) -> tuple[bool, str, list[LedgerEntry]]:
        """Execute double-entry transfer transaction in memory maintaining ACID invariants."""
        if amount <= 0:
            return False, "INVALID_AMOUNT", []

        src_acc = accounts_map.get(src_acc_no)
        tgt_acc = accounts_map.get(tgt_acc_no)
        if not src_acc or not tgt_acc:
            return False, "ACCOUNT_NOT_FOUND", []

        if src_acc.status != "ACTIVE":
            return False, "SRC_ACCOUNT_FROZEN", []
        if tgt_acc.status != "ACTIVE":
            return False, "TGT_ACCOUNT_INACTIVE", []

        total_debit = amount + fee
        if src_acc.available_balance < total_debit:
            return False, "INSUFFICIENT_FUNDS", []

        src_acc.balance -= total_debit
        tgt_acc.balance += amount

        jid = f"JRN_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        entries = [
            LedgerEntry(
                ledger_id=f"GL_{jid}_D",
                account_no=src_acc_no,
                journal_id=jid,
                entry_type="DEBIT",
                amount=total_debit,
                running_balance=src_acc.balance,
                description="Transfer Debit",
            ),
            LedgerEntry(
                ledger_id=f"GL_{jid}_C1",
                account_no=tgt_acc_no,
                journal_id=jid,
                entry_type="CREDIT",
                amount=amount,
                running_balance=tgt_acc.balance,
                description="Transfer Credit",
            ),
        ]
        if fee > 0:
            fee_pool_acc = accounts_map.get("ACC_FEE_POOL")
            if fee_pool_acc:
                fee_pool_acc.balance += fee
                entries.append(
                    LedgerEntry(
                        ledger_id=f"GL_{jid}_C2",
                        account_no="ACC_FEE_POOL",
                        journal_id=jid,
                        entry_type="CREDIT",
                        amount=fee,
                        running_balance=fee_pool_acc.balance,
                        description="Service Fee Income Credit",
                    )
                )
            else:
                entries.append(
                    LedgerEntry(
                        ledger_id=f"GL_{jid}_C2",
                        account_no="SYS_FEE_ACCOUNT",
                        journal_id=jid,
                        entry_type="CREDIT",
                        amount=fee,
                        running_balance=0.0,
                        description="Service Fee Income Credit",
                    )
                )

        return True, "SUCCESS", entries

    @classmethod
    def generate_loan_amortization_schedule(
        cls, contract: LoanContractRecord
    ) -> list[LoanScheduleRecord]:
        """Compute exact monthly annuity loan amortization schedule."""
        p = Decimal(str(contract.principal_amount))
        annual_rate = Decimal(str(contract.annual_interest_rate))
        n = contract.term_months
        monthly_rate = annual_rate / Decimal("12.0")

        if monthly_rate > Decimal("0"):
            factor = (Decimal("1") + monthly_rate) ** n
            monthly_payment = (p * monthly_rate * factor) / (factor - Decimal("1"))
            monthly_payment = monthly_payment.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        else:
            monthly_payment = (p / Decimal(str(n))).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )

        rem_principal = p
        schedules: list[LoanScheduleRecord] = []

        for period in range(1, n + 1):
            interest_part = (rem_principal * monthly_rate).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            principal_part = monthly_payment - interest_part

            if period == n or principal_part > rem_principal:
                principal_part = rem_principal
                monthly_payment = principal_part + interest_part

            rem_principal -= principal_part
            schedules.append(
                LoanScheduleRecord(
                    schedule_id=f"SCH_{contract.contract_no}_{period:03d}",
                    contract_no=contract.contract_no,
                    period_number=period,
                    principal_due=float(principal_part),
                    interest_due=float(interest_part),
                    total_installment=float(monthly_payment),
                )
            )

        return schedules

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

    @classmethod
    def verify_account_balance_conservation(
        cls,
        initial_accounts: list[AccountRecord],
        final_accounts: list[AccountRecord],
        external_inflows: float = 0.0,
        external_outflows: float = 0.0,
    ) -> tuple[bool, float, str]:
        """Verify macro closed-system total balance invariant."""
        init_sum = sum(a.balance for a in initial_accounts)
        final_sum = sum(a.balance for a in final_accounts)
        expected_final = init_sum + external_inflows - external_outflows
        diff = abs(final_sum - expected_final)

        is_conserved = diff < 0.0001
        msg = (
            f"Initial: {init_sum:.4f}, Inflow: {external_inflows:.4f}, "
            f"Outflow: {external_outflows:.4f}, Expected: {expected_final:.4f}, "
            f"Observed: {final_sum:.4f}, Delta: {diff:.4f}"
        )
        return is_conserved, diff, msg

    @classmethod
    def verify_loan_schedule_integrity(
        cls, contract: LoanContractRecord, schedules: list[LoanScheduleRecord]
    ) -> tuple[bool, list[str]]:
        """Verify that loan repayment schedule sums exactly to principal."""
        errors: list[str] = []
        if len(schedules) != contract.term_months:
            errors.append(
                f"Schedule count {len(schedules)} != term months {contract.term_months}"
            )

        sum_principal = sum(s.principal_due for s in schedules)
        diff = abs(sum_principal - contract.principal_amount)
        if diff > 0.01:
            errors.append(
                f"Principal sum {sum_principal:.4f} != contract principal "
                f"{contract.principal_amount:.4f} (diff: {diff:.4f})"
            )

        for s in schedules:
            expected_total = s.principal_due + s.interest_due
            if abs(expected_total - s.total_installment) > 0.0001:
                errors.append(
                    f"Period {s.period_number} installment mismatch: "
                    f"{s.principal_due} + {s.interest_due} != {s.total_installment}"
                )

        return (len(errors) == 0, errors)

    @classmethod
    def simulate_cdc_stream(
        cls,
        entries: list[LedgerEntry],
    ) -> list[CdcEvent]:
        """Generate CDC change event stream for real-time replication verification."""
        events: list[CdcEvent] = []
        base_ts = int(time.time() * 1000)

        for idx, e in enumerate(entries):
            events.append(
                CdcEvent(
                    event_id=f"EVT_CDC_{idx + 1:08d}",
                    table_name="cbs_general_ledger",
                    operation="INSERT",
                    timestamp_ms=base_ts + idx * 5,
                    before_state={},
                    after_state={
                        "ledger_id": e.ledger_id,
                        "account_no": e.account_no,
                        "journal_id": e.journal_id,
                        "entry_type": e.entry_type,
                        "amount": e.amount,
                        "running_balance": e.running_balance,
                        "currency_code": e.currency_code,
                        "description": e.description,
                    },
                )
            )
        return events

    @classmethod
    def simulate_concurrent_settlement_stress(
        cls,
        concurrency: int = 16,
        transactions_per_worker: int = 50,
    ) -> dict[str, Any]:
        """Simulate high-throughput multi-worker concurrent transaction burst."""
        accounts = cls.get_seed_accounts(count=100)
        fee_pool = AccountRecord(
            account_no="ACC_FEE_POOL", customer_id="SYS_BANK", account_type="NOSTRO", balance=0.0
        )
        accounts_map: dict[str, AccountRecord] = {a.account_no: a for a in accounts}
        accounts_map[fee_pool.account_no] = fee_pool

        initial_total = sum(a.balance for a in accounts_map.values())

        latencies_ms: list[float] = []
        success_count = 0
        failure_count = 0
        all_ledger_entries: list[LedgerEntry] = []

        start_time = time.time()
        for worker_id in range(concurrency):
            for t_idx in range(transactions_per_worker):
                t0 = time.time()
                src_i = (worker_id * 5 + t_idx) % len(accounts)
                tgt_i = (src_i + 7) % len(accounts)
                src_acc = accounts[src_i].account_no
                tgt_acc = accounts[tgt_i].account_no
                amount = 25.0 + (t_idx % 15)
                fee = 1.5

                ok, _, entries = cls.execute_in_memory_transfer(
                    accounts_map, src_acc, tgt_acc, amount, fee
                )
                t1 = time.time()
                latencies_ms.append((t1 - t0) * 1000.0)

                if ok:
                    success_count += 1
                    all_ledger_entries.extend(entries)
                else:
                    failure_count += 1

        total_duration = max(0.001, time.time() - start_time)
        latencies_ms.sort()
        p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        final_total = sum(a.balance for a in accounts_map.values())
        conserved = abs(final_total - initial_total) < 0.0001
        balanced, imbalance, errs = cls.verify_double_entry_conservation(all_ledger_entries)

        return {
            "total_transactions": len(latencies_ms),
            "success_count": success_count,
            "failure_count": failure_count,
            "total_duration_sec": total_duration,
            "throughput_tps": len(latencies_ms) / total_duration,
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "p99_latency_ms": p99,
            "total_balance_conserved": conserved,
            "double_entry_balanced": balanced,
            "ledger_imbalance": imbalance,
            "ledger_errors": errs,
        }
