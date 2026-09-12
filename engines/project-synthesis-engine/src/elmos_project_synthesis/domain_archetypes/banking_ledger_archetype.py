"""Industrial Banking and Double-Entry Multi-Currency Ledger Archetype Engine.

Provides deep domain modeling, aggregate roots, strict zero-sum balancing rules,
trial balance reconciliation, Merkle audit chains, and multi-currency FX revaluation.
"""

from __future__ import annotations

import datetime as dt
import enum
import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

# ==============================================================================
# 1. Enums and Value Objects
# ==============================================================================


class AccountType(enum.StrEnum):
    """Standard accounting equation primary classifications."""

    ASSET = "ASSET"  # Normal Balance: DEBIT
    LIABILITY = "LIABILITY"  # Normal Balance: CREDIT
    EQUITY = "EQUITY"  # Normal Balance: CREDIT
    REVENUE = "REVENUE"  # Normal Balance: CREDIT
    EXPENSE = "EXPENSE"  # Normal Balance: DEBIT


class NormalBalance(enum.StrEnum):
    """The normal balance side for account types."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


ACCOUNT_NORMAL_BALANCE: dict[AccountType, NormalBalance] = {
    AccountType.ASSET: NormalBalance.DEBIT,
    AccountType.EXPENSE: NormalBalance.DEBIT,
    AccountType.LIABILITY: NormalBalance.CREDIT,
    AccountType.EQUITY: NormalBalance.CREDIT,
    AccountType.REVENUE: NormalBalance.CREDIT,
}


class PostingKey(enum.StrEnum):
    """The direction of a line in a double-entry journal entry."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class AccountStatus(enum.StrEnum):
    """Lifecycle states of a financial account."""

    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    RESTRICTED = "RESTRICTED"
    CLOSED = "CLOSED"


class JournalEntryStatus(enum.StrEnum):
    """Lifecycle states of a double-entry journal entry."""

    DRAFT = "DRAFT"
    BALANCED = "BALANCED"
    POSTED = "POSTED"
    REVERSED = "REVERSED"
    REJECTED = "REJECTED"


# ISO-4217 Currency Precision Specification
CURRENCY_PRECISION: dict[str, int] = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "CNY": 2,
    "JPY": 0,
    "KRW": 0,
    "CHF": 2,
    "CAD": 2,
    "AUD": 2,
    "NZD": 2,
    "SGD": 2,
    "HKD": 2,
    "BHD": 3,
    "KWD": 3,
    "OMR": 3,
    "BTC": 8,
    "ETH": 8,
    "USDT": 6,
}


@dataclass(frozen=True)
class Currency:
    """ISO-4217 Currency Value Object with precision and symbol validation."""

    code: str

    def __post_init__(self) -> None:
        norm = self.code.strip().upper()
        if not re.fullmatch(r"^[A-Z]{3,5}$", norm):
            raise ValueError(f"Invalid currency code format: {self.code}")
        object.__setattr__(self, "code", norm)

    @property
    def precision(self) -> int:
        return CURRENCY_PRECISION.get(self.code, 2)

    def round_amount(self, amount: Decimal) -> Decimal:
        exp = Decimal(10) ** -self.precision
        return amount.quantize(exp, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class MoneyAmount:
    """High-precision monetary amount value object."""

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        rounded = self.currency.round_amount(self.amount)
        object.__setattr__(self, "amount", rounded)

    def __add__(self, other: MoneyAmount) -> MoneyAmount:
        self._check_currency(other)
        return MoneyAmount(self.amount + other.amount, self.currency)

    def __sub__(self, other: MoneyAmount) -> MoneyAmount:
        self._check_currency(other)
        return MoneyAmount(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int | float) -> MoneyAmount:
        f = Decimal(str(factor))
        return MoneyAmount(self.amount * f, self.currency)

    def __lt__(self, other: MoneyAmount) -> bool:
        self._check_currency(other)
        return self.amount < other.amount

    def __le__(self, other: MoneyAmount) -> bool:
        self._check_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: MoneyAmount) -> bool:
        self._check_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: MoneyAmount) -> bool:
        self._check_currency(other)
        return self.amount >= other.amount

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MoneyAmount):
            return False
        return self.currency == other.currency and self.amount == other.amount

    def _check_currency(self, other: MoneyAmount) -> None:
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency.code} vs {other.currency.code}")

    @property
    def is_zero(self) -> bool:
        return self.amount == Decimal("0")

    @property
    def is_negative(self) -> bool:
        return self.amount < Decimal("0")


# ==============================================================================
# 2. Aggregates and Entities
# ==============================================================================


class BankingDomainError(Exception):
    """Base domain exception for banking operations."""

    pass


class InvariantViolationError(BankingDomainError):
    """Raised when an accounting invariant is violated."""

    pass


class InsufficientFundsError(BankingDomainError):
    """Raised when an account does not have sufficient available balance."""

    pass


class AccountFrozenError(BankingDomainError):
    """Raised when attempting to transact on a frozen or closed account."""

    pass


@dataclass
class AccountAggregate:
    """Enterprise Chart-of-Accounts financial account aggregate root."""

    account_id: str
    tenant_id: str
    account_number: str
    account_name: str
    account_type: AccountType
    currency: Currency
    status: AccountStatus = AccountStatus.ACTIVE
    posted_balance: Decimal = Decimal("0.00")
    held_amount: Decimal = Decimal("0.00")
    pending_debits: Decimal = Decimal("0.00")
    pending_credits: Decimal = Decimal("0.00")
    overdraft_limit: Decimal = Decimal("0.00")
    allow_overdraft: bool = False
    version: int = 1
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    updated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))

    @property
    def normal_balance(self) -> NormalBalance:
        return ACCOUNT_NORMAL_BALANCE[self.account_type]

    @property
    def available_balance(self) -> Decimal:
        """Calculate immediately spendable funds taking holds and overdrafts into account."""
        limit = self.overdraft_limit if self.allow_overdraft else Decimal("0.00")
        if self.normal_balance == NormalBalance.DEBIT:
            return self.posted_balance - self.held_amount - self.pending_debits + limit
        else:
            return self.posted_balance - self.held_amount - self.pending_debits + limit

    def place_hold(self, hold_id: str, amount: Decimal, reason: str) -> None:
        """Place an authorization or settlement hold on the account."""
        self._ensure_operational()
        if amount <= Decimal("0"):
            raise ValueError("Hold amount must be strictly positive")
        if amount > self.available_balance:
            raise InsufficientFundsError(
                f"Cannot hold {amount} {self.currency.code}: Available balance is only {self.available_balance}"
            )
        self.held_amount += amount
        self.version += 1
        self.updated_at = dt.datetime.now(dt.UTC)

    def release_hold(self, hold_id: str, amount: Decimal) -> None:
        """Release an existing authorization hold."""
        self._ensure_operational()
        if amount <= Decimal("0"):
            raise ValueError("Release amount must be positive")
        if amount > self.held_amount:
            raise ValueError(f"Cannot release {amount}: Current hold is only {self.held_amount}")
        self.held_amount -= amount
        self.version += 1
        self.updated_at = dt.datetime.now(dt.UTC)

    def apply_posting_line(self, posting_key: PostingKey, amount: Decimal) -> None:
        """Apply a debit or credit posting directly to the account balance."""
        self._ensure_operational()
        if amount <= Decimal("0"):
            raise ValueError("Posting amount must be strictly positive")

        if self.normal_balance == NormalBalance.DEBIT:
            if posting_key == PostingKey.DEBIT:
                self.posted_balance += amount
            else:
                new_balance = self.posted_balance - amount
                limit = self.overdraft_limit if self.allow_overdraft else Decimal("0.00")
                if new_balance + limit < Decimal("0.00"):
                    raise InsufficientFundsError(
                        f"Account {self.account_number} overdraft exceeded. Attempted credit {amount}, limit {limit}"
                    )
                self.posted_balance = new_balance
        else:
            if posting_key == PostingKey.CREDIT:
                self.posted_balance += amount
            else:
                new_balance = self.posted_balance - amount
                limit = self.overdraft_limit if self.allow_overdraft else Decimal("0.00")
                if new_balance + limit < Decimal("0.00"):
                    raise InsufficientFundsError(
                        f"Account {self.account_number} credit limit exceeded. Attempted debit {amount}, limit {limit}"
                    )
                self.posted_balance = new_balance

        self.version += 1
        self.updated_at = dt.datetime.now(dt.UTC)

    def freeze(self, reason: str) -> None:
        if self.status == AccountStatus.CLOSED:
            raise InvariantViolationError("Cannot freeze a closed account")
        self.status = AccountStatus.FROZEN
        self.version += 1
        self.updated_at = dt.datetime.now(dt.UTC)

    def unfreeze(self) -> None:
        if self.status != AccountStatus.FROZEN:
            raise InvariantViolationError("Account is not frozen")
        self.status = AccountStatus.ACTIVE
        self.version += 1
        self.updated_at = dt.datetime.now(dt.UTC)

    def close(self) -> None:
        if self.posted_balance != Decimal("0.00"):
            raise InvariantViolationError(f"Cannot close account with non-zero balance: {self.posted_balance}")
        if self.held_amount != Decimal("0.00"):
            raise InvariantViolationError(f"Cannot close account with active holds: {self.held_amount}")
        self.status = AccountStatus.CLOSED
        self.version += 1
        self.updated_at = dt.datetime.now(dt.UTC)

    def _ensure_operational(self) -> None:
        if self.status == AccountStatus.FROZEN:
            raise AccountFrozenError(f"Account {self.account_number} is frozen")
        if self.status == AccountStatus.CLOSED:
            raise AccountFrozenError(f"Account {self.account_number} is permanently closed")


@dataclass(frozen=True)
class JournalEntryLine:
    """Individual debit or credit leg of a financial transaction."""

    line_id: str
    account_id: str
    posting_key: PostingKey
    amount: Decimal
    currency: Currency
    base_currency_amount: Decimal
    exchange_rate: Decimal = Decimal("1.000000")
    narration: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.amount <= Decimal("0"):
            raise ValueError(f"Line amount must be strictly positive, got {self.amount}")
        if self.base_currency_amount <= Decimal("0"):
            raise ValueError(f"Base currency amount must be strictly positive, got {self.base_currency_amount}")
        if self.exchange_rate <= Decimal("0"):
            raise ValueError(f"Exchange rate must be strictly positive, got {self.exchange_rate}")


@dataclass
class JournalEntryAggregate:
    """Double-Entry Accounting Journal Entry aggregate root with zero-sum invariant."""

    entry_id: str
    tenant_id: str
    reference: str
    description: str
    base_currency: Currency
    posting_date: dt.date
    effective_date: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    status: JournalEntryStatus = JournalEntryStatus.DRAFT
    lines: list[JournalEntryLine] = field(default_factory=list)
    previous_merkle_hash: str = "0" * 64
    merkle_hash: str = ""
    version: int = 1
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    posted_at: dt.datetime | None = None

    def add_line(
        self,
        account_id: str,
        posting_key: PostingKey,
        amount: Decimal,
        currency: Currency,
        exchange_rate: Decimal = Decimal("1.000000"),
        narration: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> JournalEntryLine:
        """Add a transaction leg to this journal entry."""
        if self.status != JournalEntryStatus.DRAFT:
            raise InvariantViolationError(f"Cannot add lines to journal entry in status {self.status}")

        base_amount = currency.round_amount(amount * exchange_rate)
        line = JournalEntryLine(
            line_id=f"{self.entry_id}-L{len(self.lines) + 1:03d}",
            account_id=account_id,
            posting_key=posting_key,
            amount=currency.round_amount(amount),
            currency=currency,
            base_currency_amount=base_amount,
            exchange_rate=exchange_rate,
            narration=narration,
            metadata=metadata or {},
        )
        self.lines.append(line)
        self.version += 1
        return line

    @property
    def total_debits_base(self) -> Decimal:
        return sum(
            (line.base_currency_amount for line in self.lines if line.posting_key == PostingKey.DEBIT),
            Decimal("0.00"),
        )

    @property
    def total_credits_base(self) -> Decimal:
        return sum(
            (line.base_currency_amount for line in self.lines if line.posting_key == PostingKey.CREDIT),
            Decimal("0.00"),
        )

    @property
    def is_balanced(self) -> bool:
        """Double-entry rule: Sum of Debits must exactly equal Sum of Credits."""
        if len(self.lines) < 2:
            return False
        return self.total_debits_base == self.total_credits_base

    def validate_and_balance(self) -> None:
        """Strict invariant verification: zero-sum balance & multi-currency consistency."""
        if len(self.lines) < 2:
            raise InvariantViolationError("Journal entry must have at least two legs (one debit, one credit)")

        debits = self.total_debits_base
        credits = self.total_credits_base
        if debits != credits:
            diff = debits - credits
            raise InvariantViolationError(
                f"Double-entry out of balance! Debits: {debits}, Credits: {credits}, Imbalance: {diff}"
            )

        currencies = {line.currency.code for line in self.lines}
        if len(currencies) == 1:
            curr_debits = sum(
                (line.amount for line in self.lines if line.posting_key == PostingKey.DEBIT), Decimal("0")
            )
            curr_credits = sum(
                (line.amount for line in self.lines if line.posting_key == PostingKey.CREDIT), Decimal("0")
            )
            if curr_debits != curr_credits:
                raise InvariantViolationError(
                    f"Single currency {list(currencies)[0]} legs out of balance: {curr_debits} vs {curr_credits}"
                )

        self.status = JournalEntryStatus.BALANCED
        self._compute_merkle_hash()

    def post(self, account_repository: dict[str, AccountAggregate]) -> None:
        """Commit the balanced journal entry to all involved accounts atomically."""
        if self.status != JournalEntryStatus.BALANCED:
            self.validate_and_balance()

        for line in self.lines:
            account = account_repository.get(line.account_id)
            if not account:
                raise InvariantViolationError(f"Account {line.account_id} not found in ledger")
            if account.currency != line.currency:
                raise InvariantViolationError(
                    f"Currency mismatch for account {account.account_number}: "
                    f"expected {account.currency.code}, got {line.currency.code}"
                )
            if account.status != AccountStatus.ACTIVE:
                raise AccountFrozenError(f"Account {account.account_number} is {account.status}")

        for line in self.lines:
            account = account_repository[line.account_id]
            account.apply_posting_line(line.posting_key, line.amount)

        self.status = JournalEntryStatus.POSTED
        self.posted_at = dt.datetime.now(dt.UTC)
        self.version += 1

    def create_reversal(self, reversal_reference: str, reason: str) -> JournalEntryAggregate:
        """Create an exact compensatory reversal entry swapping debits and credits."""
        if self.status != JournalEntryStatus.POSTED:
            raise InvariantViolationError("Can only reverse a POSTED journal entry")

        reversal = JournalEntryAggregate(
            entry_id=f"rev-{self.entry_id}",
            tenant_id=self.tenant_id,
            reference=reversal_reference,
            description=f"Reversal of {self.reference}: {reason}",
            base_currency=self.base_currency,
            posting_date=dt.date.today(),
            previous_merkle_hash=self.merkle_hash,
        )

        for line in self.lines:
            inverted_key = PostingKey.CREDIT if line.posting_key == PostingKey.DEBIT else PostingKey.DEBIT
            reversal.add_line(
                account_id=line.account_id,
                posting_key=inverted_key,
                amount=line.amount,
                currency=line.currency,
                exchange_rate=line.exchange_rate,
                narration=f"Reversal leg: {line.narration}",
            )

        reversal.validate_and_balance()
        self.status = JournalEntryStatus.REVERSED
        return reversal

    def _compute_merkle_hash(self) -> None:
        """Compute tamper-evident SHA-256 Merkle hash for this entry linked to predecessor."""
        lines_payload = [
            {
                "line_id": line.line_id,
                "account_id": line.account_id,
                "key": line.posting_key.value,
                "amount": str(line.amount),
                "curr": line.currency.code,
                "base_amt": str(line.base_currency_amount),
            }
            for line in self.lines
        ]
        body = {
            "entry_id": self.entry_id,
            "tenant_id": self.tenant_id,
            "ref": self.reference,
            "prev_hash": self.previous_merkle_hash,
            "lines": lines_payload,
        }
        raw = json.dumps(body, sort_keys=True)
        self.merkle_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ==============================================================================
# 3. Domain Services: Posting Rule Engine & Trial Balance Reconciliation
# ==============================================================================


class PostingRuleEngine:
    """Encapsulates standard banking transaction posting rules and multi-legged transactions."""

    def __init__(self, tenant_id: str, base_currency: Currency) -> None:
        self.tenant_id = tenant_id
        self.base_currency = base_currency

    def build_p2p_transfer(
        self,
        entry_id: str,
        reference: str,
        sender_account: AccountAggregate,
        receiver_account: AccountAggregate,
        amount: Decimal,
        fee_amount: Decimal = Decimal("0.00"),
        fee_revenue_account: AccountAggregate | None = None,
        narration: str = "P2P Transfer",
    ) -> JournalEntryAggregate:
        """Build a customer fund transfer with optional platform transaction fee."""
        if sender_account.currency != receiver_account.currency:
            raise ValueError("Direct transfer requires identical currency; use FX transfer for cross-currency")

        entry = JournalEntryAggregate(
            entry_id=entry_id,
            tenant_id=self.tenant_id,
            reference=reference,
            description=narration,
            base_currency=self.base_currency,
            posting_date=dt.date.today(),
        )

        curr = sender_account.currency
        total_debit = amount + fee_amount

        entry.add_line(
            account_id=sender_account.account_id,
            posting_key=PostingKey.DEBIT if sender_account.account_type == AccountType.LIABILITY else PostingKey.CREDIT,
            amount=total_debit,
            currency=curr,
            narration=f"Transfer to {receiver_account.account_number}",
        )

        entry.add_line(
            account_id=receiver_account.account_id,
            posting_key=PostingKey.CREDIT
            if receiver_account.account_type == AccountType.LIABILITY
            else PostingKey.DEBIT,
            amount=amount,
            currency=curr,
            narration=f"Transfer from {sender_account.account_number}",
        )

        if fee_amount > Decimal("0.00"):
            if not fee_revenue_account:
                raise ValueError("fee_revenue_account must be provided when fee_amount > 0")
            entry.add_line(
                account_id=fee_revenue_account.account_id,
                posting_key=PostingKey.CREDIT,
                amount=fee_amount,
                currency=curr,
                narration=f"Platform fee for transfer {reference}",
            )

        entry.validate_and_balance()
        return entry

    def build_merchant_settlement(
        self,
        entry_id: str,
        reference: str,
        merchant_payable_acc: AccountAggregate,
        merchant_bank_payout_acc: AccountAggregate,
        platform_fee_acc: AccountAggregate,
        gross_sales: Decimal,
        commission_rate: Decimal,
    ) -> JournalEntryAggregate:
        """Build merchant marketplace settlement with commission deduction."""
        entry = JournalEntryAggregate(
            entry_id=entry_id,
            tenant_id=self.tenant_id,
            reference=reference,
            description=f"Marketplace settlement for {merchant_payable_acc.account_name}",
            base_currency=self.base_currency,
            posting_date=dt.date.today(),
        )

        fee = (gross_sales * commission_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        net_payout = gross_sales - fee
        curr = merchant_payable_acc.currency

        entry.add_line(
            account_id=merchant_payable_acc.account_id,
            posting_key=PostingKey.DEBIT,
            amount=gross_sales,
            currency=curr,
            narration="Gross sales liquidation",
        )

        entry.add_line(
            account_id=merchant_bank_payout_acc.account_id,
            posting_key=PostingKey.CREDIT,
            amount=net_payout,
            currency=curr,
            narration="Net merchant disbursement",
        )

        entry.add_line(
            account_id=platform_fee_acc.account_id,
            posting_key=PostingKey.CREDIT,
            amount=fee,
            currency=curr,
            narration=f"Commission revenue ({commission_rate * 100}%)",
        )

        entry.validate_and_balance()
        return entry


@dataclass
class TrialBalanceSummary:
    """Trial Balance report structure."""

    as_of_date: dt.date
    tenant_id: str
    base_currency: str
    account_balances: list[dict[str, Any]]
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool
    merkle_root: str


class LedgerReconciliationService:
    """Continuously reconciles general ledger, verifies trial balance, and audits Merkle chains."""

    def __init__(self, tenant_id: str, base_currency: Currency) -> None:
        self.tenant_id = tenant_id
        self.base_currency = base_currency

    def generate_trial_balance(
        self,
        accounts: Sequence[AccountAggregate],
        journal_entries: Sequence[JournalEntryAggregate],
        as_of: dt.date | None = None,
    ) -> TrialBalanceSummary:
        """Compute the trial balance across all accounts and verify global accounting equation."""
        target_date = as_of or dt.date.today()
        account_rows: list[dict[str, Any]] = []
        sum_debits = Decimal("0.00")
        sum_credits = Decimal("0.00")

        for acc in accounts:
            bal = acc.posted_balance
            if acc.normal_balance == NormalBalance.DEBIT:
                debit_val = bal if bal >= Decimal("0.00") else Decimal("0.00")
                credit_val = -bal if bal < Decimal("0.00") else Decimal("0.00")
            else:
                credit_val = bal if bal >= Decimal("0.00") else Decimal("0.00")
                debit_val = -bal if bal < Decimal("0.00") else Decimal("0.00")

            sum_debits += debit_val
            sum_credits += credit_val

            account_rows.append(
                {
                    "account_number": acc.account_number,
                    "account_name": acc.account_name,
                    "account_type": acc.account_type.value,
                    "currency": acc.currency.code,
                    "debit": str(debit_val),
                    "credit": str(credit_val),
                }
            )

        merkle_hashes = [entry.merkle_hash for entry in journal_entries if entry.status == JournalEntryStatus.POSTED]
        combined_hash = (
            hashlib.sha256("".join(merkle_hashes).encode("utf-8")).hexdigest() if merkle_hashes else "0" * 64
        )
        is_balanced = sum_debits == sum_credits

        return TrialBalanceSummary(
            as_of_date=target_date,
            tenant_id=self.tenant_id,
            base_currency=self.base_currency.code,
            account_balances=account_rows,
            total_debits=sum_debits,
            total_credits=sum_credits,
            is_balanced=is_balanced,
            merkle_root=combined_hash,
        )

    def verify_merkle_chain_integrity(self, journal_entries: Sequence[JournalEntryAggregate]) -> tuple[bool, list[str]]:
        """Verify the immutable cryptographic hash chain of all posted entries."""
        errors: list[str] = []
        expected_prev = "0" * 64

        for idx, entry in enumerate(journal_entries):
            if entry.status != JournalEntryStatus.POSTED:
                continue

            if entry.previous_merkle_hash != expected_prev:
                errors.append(
                    f"Entry {entry.entry_id} (index {idx}) chain broken: "
                    f"expected prev_hash {expected_prev}, got {entry.previous_merkle_hash}"
                )

            orig_hash = entry.merkle_hash
            entry._compute_merkle_hash()
            if entry.merkle_hash != orig_hash:
                errors.append(f"Entry {entry.entry_id} hash mismatch: {orig_hash} vs {entry.merkle_hash}")

            expected_prev = entry.merkle_hash

        return len(errors) == 0, errors

    def perform_fx_revaluation(
        self,
        foreign_accounts: Sequence[AccountAggregate],
        fx_rates: dict[str, Decimal],
        unrealized_fx_gain_account: AccountAggregate,
        unrealized_fx_loss_account: AccountAggregate,
    ) -> list[JournalEntryAggregate]:
        """Revalue foreign currency asset/liability accounts against current spot rates."""
        revaluation_entries: list[JournalEntryAggregate] = []

        for acc in foreign_accounts:
            if acc.currency == self.base_currency:
                continue

            rate = fx_rates.get(acc.currency.code)
            if not rate:
                continue

            current_base_value = self.base_currency.round_amount(acc.posted_balance * rate)
            delta = current_base_value - acc.posted_balance

            if delta == Decimal("0.00"):
                continue

            entry = JournalEntryAggregate(
                entry_id=f"fx-rev-{acc.account_id}-{int(dt.datetime.now().timestamp())}",
                tenant_id=self.tenant_id,
                reference=f"FX-REV-{acc.account_number}",
                description=f"Unrealized FX revaluation for {acc.account_number} at rate {rate}",
                base_currency=self.base_currency,
                posting_date=dt.date.today(),
            )

            if delta > Decimal("0.00"):
                entry.add_line(
                    account_id=acc.account_id,
                    posting_key=PostingKey.DEBIT if acc.normal_balance == NormalBalance.DEBIT else PostingKey.CREDIT,
                    amount=delta,
                    currency=self.base_currency,
                    narration="FX asset write-up",
                )
                entry.add_line(
                    account_id=unrealized_fx_gain_account.account_id,
                    posting_key=PostingKey.CREDIT,
                    amount=delta,
                    currency=self.base_currency,
                    narration="Unrealized FX Gain",
                )
            else:
                abs_delta = abs(delta)
                entry.add_line(
                    account_id=unrealized_fx_loss_account.account_id,
                    posting_key=PostingKey.DEBIT,
                    amount=abs_delta,
                    currency=self.base_currency,
                    narration="Unrealized FX Loss",
                )
                entry.add_line(
                    account_id=acc.account_id,
                    posting_key=PostingKey.CREDIT if acc.normal_balance == NormalBalance.DEBIT else PostingKey.DEBIT,
                    amount=abs_delta,
                    currency=self.base_currency,
                    narration="FX asset write-down",
                )

            entry.validate_and_balance()
            revaluation_entries.append(entry)

        return revaluation_entries
