"""Unit and integration tests for Industrial Banking and Double-Entry Ledger Archetype."""
from decimal import Decimal
import datetime as dt
import pytest

from elmos_project_synthesis.domain_archetypes.banking_ledger_archetype import (
    Currency,
    MoneyAmount,
    AccountType,
    NormalBalance,
    AccountStatus,
    JournalEntryStatus,
    PostingKey,
    AccountAggregate,
    JournalEntryLine,
    JournalEntryAggregate,
    PostingRuleEngine,
    LedgerReconciliationService,
    InvariantViolationError,
    InsufficientFundsError,
    AccountFrozenError,
)


def test_currency_and_money_operations():
    usd = Currency("USD")
    jpy = Currency("JPY")
    bhd = Currency("BHD")

    assert usd.precision == 2
    assert jpy.precision == 0
    assert bhd.precision == 3

    m1 = MoneyAmount(Decimal("100.555"), usd)
    assert m1.amount == Decimal("100.56") # ROUND_HALF_EVEN

    m2 = MoneyAmount(Decimal("50.20"), usd)
    m_sum = m1 + m2
    assert m_sum.amount == Decimal("150.76")

    m_diff = m1 - m2
    assert m_diff.amount == Decimal("50.36")

    m_prod = m2 * 2
    assert m_prod.amount == Decimal("100.40")

    # Currency mismatch
    with pytest.raises(ValueError, match="Currency mismatch"):
        _ = m1 + MoneyAmount(Decimal("100"), jpy)


def test_account_aggregate_holds_and_overdraft():
    usd = Currency("USD")
    acc = AccountAggregate(
        account_id="acc-101",
        tenant_id="tenant-alpha",
        account_number="CHK-00101",
        account_name="Customer Checking",
        account_type=AccountType.ASSET,
        currency=usd,
        posted_balance=Decimal("1000.00"),
        overdraft_limit=Decimal("200.00"),
        allow_overdraft=True,
    )

    assert acc.normal_balance == NormalBalance.DEBIT
    assert acc.available_balance == Decimal("1200.00")

    # Place hold
    acc.place_hold("hold-1", Decimal("300.00"), "Card Pre-auth")
    assert acc.held_amount == Decimal("300.00")
    assert acc.available_balance == Decimal("900.00")

    # Release hold
    acc.release_hold("hold-1", Decimal("300.00"))
    assert acc.held_amount == Decimal("0.00")
    assert acc.available_balance == Decimal("1200.00")

    # Excessive hold
    with pytest.raises(InsufficientFundsError):
        acc.place_hold("hold-excess", Decimal("1500.00"), "Exceeds funds")

    # Freeze account
    acc.freeze("Suspicious activity")
    assert acc.status == AccountStatus.FROZEN
    with pytest.raises(AccountFrozenError):
        acc.apply_posting_line(PostingKey.DEBIT, Decimal("100.00"))

    acc.unfreeze()
    assert acc.status == AccountStatus.ACTIVE


def test_journal_entry_balancing_and_merkle_hash():
    usd = Currency("USD")
    acc_a = AccountAggregate("acc-a", "t1", "1001", "Cash", AccountType.ASSET, usd, posted_balance=Decimal("1000.00"))
    acc_b = AccountAggregate("acc-b", "t1", "2001", "Payable", AccountType.LIABILITY, usd, posted_balance=Decimal("500.00"))

    repo = {"acc-a": acc_a, "acc-b": acc_b}

    entry = JournalEntryAggregate(
        entry_id="je-001",
        tenant_id="t1",
        reference="PAYMENT-001",
        description="Vendor settlement",
        base_currency=usd,
        posting_date=dt.date.today(),
    )

    # Imbalanced entry
    entry.add_line("acc-a", PostingKey.DEBIT, Decimal("200.00"), usd)
    entry.add_line("acc-b", PostingKey.CREDIT, Decimal("150.00"), usd)

    assert not entry.is_balanced
    with pytest.raises(InvariantViolationError, match="Double-entry out of balance"):
        entry.validate_and_balance()

    # Balance it
    entry.lines.clear()
    entry.add_line("acc-a", PostingKey.DEBIT, Decimal("200.00"), usd, narration="Debit cash")
    entry.add_line("acc-b", PostingKey.CREDIT, Decimal("200.00"), usd, narration="Credit liability")

    assert entry.is_balanced
    entry.validate_and_balance()
    assert entry.status == JournalEntryStatus.BALANCED
    assert len(entry.merkle_hash) == 64

    # Post entry
    entry.post(repo)
    assert entry.status == JournalEntryStatus.POSTED
    assert acc_a.posted_balance == Decimal("1200.00") # Asset DEBIT increase
    assert acc_b.posted_balance == Decimal("700.00")  # Liability CREDIT increase

    # Create reversal
    reversal = entry.create_reversal("REV-PAYMENT-001", "Payment canceled by user")
    assert reversal.is_balanced
    assert reversal.previous_merkle_hash == entry.merkle_hash
    reversal.post(repo)
    assert acc_a.posted_balance == Decimal("1000.00") # Back to baseline
    assert acc_b.posted_balance == Decimal("500.00")


def test_posting_rule_engine_and_trial_balance():
    usd = Currency("USD")
    engine = PostingRuleEngine("tenant-prime", usd)

    # Asset backing the deposits to maintain global accounting equation (Assets = Liabilities + Equity)
    vault = AccountAggregate("v1", "t-prime", "AST-1", "Central Reserve", AccountType.ASSET, usd, posted_balance=Decimal("1200.00"))
    sender = AccountAggregate("s1", "t-prime", "CHK-1", "Alice", AccountType.LIABILITY, usd, posted_balance=Decimal("1000.00"))
    receiver = AccountAggregate("r1", "t-prime", "CHK-2", "Bob", AccountType.LIABILITY, usd, posted_balance=Decimal("200.00"))
    fee_acc = AccountAggregate("f1", "t-prime", "REV-1", "Platform Fee", AccountType.REVENUE, usd, posted_balance=Decimal("0.00"))

    repo = {"v1": vault, "s1": sender, "r1": receiver, "f1": fee_acc}

    entry = engine.build_p2p_transfer(
        entry_id="tx-p2p-1",
        reference="REF-TRANSFER-101",
        sender_account=sender,
        receiver_account=receiver,
        amount=Decimal("100.00"),
        fee_amount=Decimal("2.50"),
        fee_revenue_account=fee_acc,
        narration="Dinner split",
    )

    entry.post(repo)
    assert sender.posted_balance == Decimal("897.50") # 1000 - 102.50
    assert receiver.posted_balance == Decimal("300.00") # 200 + 100
    assert fee_acc.posted_balance == Decimal("2.50")

    # Reconciliation Service
    reconciler = LedgerReconciliationService("tenant-prime", usd)
    tb = reconciler.generate_trial_balance([vault, sender, receiver, fee_acc], [entry])
    assert tb.is_balanced
    assert tb.total_credits == tb.total_debits

    # Verify Merkle Chain Integrity
    valid, errors = reconciler.verify_merkle_chain_integrity([entry])
    assert valid
    assert len(errors) == 0
