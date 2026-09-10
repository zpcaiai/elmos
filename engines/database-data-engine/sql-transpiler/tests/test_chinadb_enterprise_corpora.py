"""Comprehensive industrial test suite for ChinaDB Enterprise Industry Corpora.

Validates 5 real enterprise domain corpora:
1. Core Banking & Double-Entry Settlement
2. Insurance & Actuarial Claims (IFRS 17)
3. Telecom Real-Time CDR Rating & Quota Depletion
4. Supply Chain WMS/TMS Inventory Mass Balance
5. Enterprise ERP & 7-Tier Progressive Payroll

Also covers AST lowering across 13 domestic targets, CDC event generation,
concurrency stress simulation, and L5 zero-human-intervention self-healing.
"""

from __future__ import annotations

import pytest

from elmos_sql_transpiler.chinadb_enterprise_corpora import (
    BankingSettlementCorpus,
    ErpPayrollCorpus,
    InsuranceClaimsCorpus,
    SupplyChainLogisticsCorpus,
    TelecomRatingCorpus,
    get_all_enterprise_corpora,
    get_corpus_by_domain,
)
from elmos_sql_transpiler.chinadb_enterprise_corpora.banking_settlement import (
    AccountRecord,
    BranchRecord,
    CustomerRecord,
    FxRateRecord,
    LedgerEntry,
    LoanContractRecord,
)
from elmos_sql_transpiler.chinadb_enterprise_corpora.erp_payroll_hr import (
    AttendanceRecord,
    DepartmentRecord,
    EmployeeRecord,
    LegalEntityRecord,
    MonthlyPayrollRecord,
    TaxBracketRecord,
)
from elmos_sql_transpiler.chinadb_enterprise_corpora.insurance_claims import (
    BeneficiaryRecord,
    ClaimRecord,
    LossTriangleRecord,
    PolicyholderRecord,
    PolicyRecord,
    ProductRecord,
)
from elmos_sql_transpiler.chinadb_enterprise_corpora.supply_chain_logistics import (
    InventoryAtpRecord,
    SkuItemRecord,
    WarehouseRecord,
)
from elmos_sql_transpiler.chinadb_enterprise_corpora.telecom_rating import (
    CdrRecord,
    MonthlyBillRecord,
    QuotaWalletRecord,
    RatePlanRecord,
    SubscriberRecord,
)
from elmos_sql_transpiler.chinadb_target_lowers import (
    get_chinadb_lowerer,
)
from elmos_sql_transpiler.l5_autonomous_migration_engine import (
    AutonomousDatabaseMigrationEngine,
    AutonomousMigrationConfig,
    AutonomousMigrationDossier,
)
from elmos_sql_transpiler.l5_self_healing_engine import (
    AutonomousDatabaseSelfHealingEngine,
)


class TestEnterpriseCorporaRegistryAndDiscovery:
    """Test corpora registration, domain lookup, statement parsing, and raw assets."""

    def test_all_corpora_count(self) -> None:
        corpora = get_all_enterprise_corpora()
        assert len(corpora) == 5
        assert BankingSettlementCorpus in corpora
        assert InsuranceClaimsCorpus in corpora
        assert TelecomRatingCorpus in corpora
        assert SupplyChainLogisticsCorpus in corpora
        assert ErpPayrollCorpus in corpora

    @pytest.mark.parametrize(
        ("domain_keyword", "expected_cls"),
        [
            ("banking", BankingSettlementCorpus),
            ("settlement", BankingSettlementCorpus),
            ("insurance", InsuranceClaimsCorpus),
            ("claims", InsuranceClaimsCorpus),
            ("telecom", TelecomRatingCorpus),
            ("rating", TelecomRatingCorpus),
            ("supply", SupplyChainLogisticsCorpus),
            ("logistics", SupplyChainLogisticsCorpus),
            ("warehouse", SupplyChainLogisticsCorpus),
            ("erp", ErpPayrollCorpus),
            ("payroll", ErpPayrollCorpus),
            ("hr", ErpPayrollCorpus),
        ],
    )
    def test_get_corpus_by_domain_keywords(self, domain_keyword: str, expected_cls: type) -> None:
        cls = get_corpus_by_domain(domain_keyword)
        assert cls is not None
        assert cls is expected_cls

    def test_get_corpus_by_domain_unknown(self) -> None:
        assert get_corpus_by_domain("quantum_cryptography") is None
        assert get_corpus_by_domain("blockchain_nft") is None

    def test_raw_sql_assets_exist_and_non_empty(self) -> None:
        corpora = get_all_enterprise_corpora()
        for corpus in corpora:
            path = corpus.get_raw_sql_path()
            assert path.exists(), f"Missing raw SQL file for {corpus.domain_name}"
            sql_text = corpus.get_raw_sql()
            assert len(sql_text) > 100000, f"SQL file unexpectedly small for {corpus.domain_name}"
            stmts = corpus.parse_statements()
            assert len(stmts) >= 10, f"Too few statements parsed for {corpus.domain_name}"

    def test_corpus_primary_source_dialect(self) -> None:
        for corpus in get_all_enterprise_corpora():
            assert corpus.primary_source_dialect in ("oracle", "sqlserver", "postgres")


class TestBankingSettlementEnterpriseCorpus:
    """Deep test suite for Core Banking Double-Entry Settlement Corpus."""

    def test_banking_raw_sql_structure(self) -> None:
        sql_text = BankingSettlementCorpus.get_raw_sql()
        assert "CREATE TABLE" in sql_text
        assert "cbs_accounts" in sql_text
        assert "cbs_branches" in sql_text
        assert "cbs_customers" in sql_text
        assert "cbs_general_ledger" in sql_text

    def test_seed_branches_generation(self) -> None:
        branches = BankingSettlementCorpus.get_seed_branches(count=15)
        assert len(branches) == 15
        assert all(isinstance(b, BranchRecord) for b in branches)
        assert branches[0].branch_code.startswith("BR")

    def test_seed_customers_generation(self) -> None:
        custs = BankingSettlementCorpus.get_seed_customers(count=40)
        assert len(custs) == 40
        assert all(isinstance(c, CustomerRecord) for c in custs)
        for c in custs:
            assert c.risk_rating in ("R1", "R2", "R3", "R4", "R5")
            assert c.kyc_status in ("VERIFIED", "PENDING")

    def test_seed_accounts_generation(self) -> None:
        accounts = BankingSettlementCorpus.get_seed_accounts(count=60)
        assert len(accounts) == 60
        assert all(isinstance(a, AccountRecord) for a in accounts)
        for a in accounts:
            assert a.balance >= 0.0
            assert a.frozen_balance >= 0.0

    def test_seed_fx_rates_generation(self) -> None:
        fx_rates = BankingSettlementCorpus.get_seed_fx_rates()
        assert len(fx_rates) >= 4
        assert all(isinstance(r, FxRateRecord) for r in fx_rates)
        cny_usd = next(
            (r for r in fx_rates if r.base_currency == "USD" and r.target_currency == "CNY"),
            None,
        )
        assert cny_usd is not None
        assert cny_usd.middle_rate > 0.0

    def test_in_memory_transfer_happy_path(self) -> None:
        accounts = BankingSettlementCorpus.get_seed_accounts(count=2)
        accounts[0].balance = 10000.0
        accounts[0].frozen_balance = 0.0
        accounts[0].status = "ACTIVE"
        accounts[1].balance = 5000.0
        accounts[1].frozen_balance = 0.0
        accounts[1].status = "ACTIVE"
        acc_map = {a.account_no: a for a in accounts}

        ok, msg, entries = BankingSettlementCorpus.execute_in_memory_transfer(
            acc_map, accounts[0].account_no, accounts[1].account_no, amount=2000.0, fee=10.0
        )
        assert ok is True
        assert "SUCCESS" in msg
        assert len(entries) >= 2
        assert accounts[0].balance == 7990.0
        assert accounts[1].balance == 7000.0

    def test_in_memory_transfer_insufficient_balance(self) -> None:
        accounts = BankingSettlementCorpus.get_seed_accounts(count=2)
        accounts[0].balance = 100.0
        accounts[0].frozen_balance = 0.0
        accounts[0].status = "ACTIVE"
        accounts[1].status = "ACTIVE"
        acc_map = {a.account_no: a for a in accounts}
        ok, msg, entries = BankingSettlementCorpus.execute_in_memory_transfer(
            acc_map, accounts[0].account_no, accounts[1].account_no, amount=500.0
        )
        assert ok is False
        assert "INSUFFICIENT_FUNDS" in msg
        assert len(entries) == 0

    def test_in_memory_transfer_account_frozen(self) -> None:
        accounts = BankingSettlementCorpus.get_seed_accounts(count=2)
        accounts[0].status = "FROZEN"
        acc_map = {a.account_no: a for a in accounts}
        ok, msg, _ = BankingSettlementCorpus.execute_in_memory_transfer(
            acc_map, accounts[0].account_no, accounts[1].account_no, amount=100.0
        )
        assert ok is False
        assert "SRC_ACCOUNT_FROZEN" in msg

    def test_in_memory_transfer_negative_or_zero_amount(self) -> None:
        accounts = BankingSettlementCorpus.get_seed_accounts(count=2)
        acc_map = {a.account_no: a for a in accounts}
        ok, msg, entries = BankingSettlementCorpus.execute_in_memory_transfer(
            acc_map, accounts[0].account_no, accounts[1].account_no, amount=-50.0
        )
        assert ok is False
        assert "INVALID_AMOUNT" in msg

    def test_double_entry_conservation_law(self) -> None:
        entries = [
            LedgerEntry(
                ledger_id="L001",
                account_no="ACC_001",
                journal_id="J_100",
                entry_type="DEBIT",
                amount=500.0,
                running_balance=9500.0,
                currency_code="CNY",
                description="Internal Transfer Debit",
            ),
            LedgerEntry(
                ledger_id="L002",
                account_no="ACC_002",
                journal_id="J_100",
                entry_type="CREDIT",
                amount=500.0,
                running_balance=5500.0,
                currency_code="CNY",
                description="Internal Transfer Credit",
            ),
        ]
        is_balanced, diff, errs = BankingSettlementCorpus.verify_double_entry_conservation(entries)
        assert is_balanced is True
        assert diff == 0.0
        assert len(errs) == 0

    def test_double_entry_imbalance_detection(self) -> None:
        entries = [
            LedgerEntry(
                ledger_id="L001",
                account_no="ACC_001",
                journal_id="J_101",
                entry_type="DEBIT",
                amount=500.0,
                running_balance=9500.0,
                currency_code="CNY",
                description="Debit",
            ),
            LedgerEntry(
                ledger_id="L002",
                account_no="ACC_002",
                journal_id="J_101",
                entry_type="CREDIT",
                amount=450.0,
                running_balance=5450.0,
                currency_code="CNY",
                description="Credit Imbalance",
            ),
        ]
        is_balanced, diff, errs = BankingSettlementCorpus.verify_double_entry_conservation(entries)
        assert is_balanced is False
        assert diff == 50.0
        assert len(errs) > 0

    def test_account_balance_conservation_multi_step(self) -> None:
        initial_accounts = BankingSettlementCorpus.get_seed_accounts(count=10)
        import copy

        final_accounts = copy.deepcopy(initial_accounts)
        acc_map = {a.account_no: a for a in final_accounts}
        total_in = 1000.0
        final_accounts[0].balance += total_in
        BankingSettlementCorpus.execute_in_memory_transfer(
            acc_map, final_accounts[0].account_no, final_accounts[1].account_no, 300.0
        )
        BankingSettlementCorpus.execute_in_memory_transfer(
            acc_map, final_accounts[1].account_no, final_accounts[2].account_no, 150.0
        )
        conserved, diff, msg = BankingSettlementCorpus.verify_account_balance_conservation(
            initial_accounts, final_accounts, external_inflows=total_in
        )
        assert conserved is True, msg
        assert abs(diff) < 0.001

    def test_loan_amortization_schedule_integrity(self) -> None:
        contract = LoanContractRecord(
            contract_no="LOAN_2026001",
            customer_id="CUST_001",
            disbursement_account="ACC_001",
            repayment_account="ACC_002",
            principal_amount=120000.0,
            remaining_principal=120000.0,
            annual_interest_rate=0.048,
            term_months=12,
            repayment_method="EQUAL_PRINCIPAL",
            loan_status="ACTIVE",
        )
        schedules = BankingSettlementCorpus.generate_loan_amortization_schedule(contract)
        assert len(schedules) == 12
        ok, errs = BankingSettlementCorpus.verify_loan_schedule_integrity(contract, schedules)
        assert ok is True, f"Integrity errors: {errs}"
        total_principal_paid = sum(s.principal_due for s in schedules)
        assert abs(total_principal_paid - 120000.0) < 0.1

    def test_banking_cdc_stream_simulation(self) -> None:
        entries = [
            LedgerEntry(
                ledger_id="L1",
                account_no="A1",
                journal_id="J1",
                entry_type="DEBIT",
                amount=100.0,
                running_balance=900.0,
                currency_code="CNY",
                description="Debit 100",
            ),
        ]
        events = BankingSettlementCorpus.simulate_cdc_stream(entries)
        assert len(events) == 1
        assert all(hasattr(e, "event_id") and hasattr(e, "table_name") for e in events)
        assert events[0].table_name == "cbs_general_ledger"
        assert events[0].operation == "INSERT"

    def test_banking_concurrent_settlement_stress(self) -> None:
        res = BankingSettlementCorpus.simulate_concurrent_settlement_stress(
            concurrency=4, transactions_per_worker=10
        )
        assert res["total_transactions"] == 40
        assert res["success_count"] > 0
        assert res["p95_latency_ms"] <= 100.0
        assert res["double_entry_balanced"] is True
        assert res["total_balance_conserved"] is True


class TestInsuranceClaimsEnterpriseCorpus:
    """Deep test suite for Insurance & Actuarial Claims Corpus (IFRS 17)."""

    def test_insurance_raw_sql_structure(self) -> None:
        sql_text = InsuranceClaimsCorpus.get_raw_sql()
        assert "ins_products" in sql_text
        assert "ins_policyholders" in sql_text
        assert "ins_policies" in sql_text
        assert "ins_claims" in sql_text

    def test_seed_policyholders_generation(self) -> None:
        holders = InsuranceClaimsCorpus.get_seed_policyholders(count=30)
        assert len(holders) == 30
        assert all(isinstance(h, PolicyholderRecord) for h in holders)
        for h in holders:
            assert h.risk_level in (1, 2, 3)

    def test_seed_products_generation(self) -> None:
        products = InsuranceClaimsCorpus.get_seed_products()
        assert len(products) >= 3
        assert all(isinstance(p, ProductRecord) for p in products)
        codes = [p.product_code for p in products]
        assert len(codes) >= 3

    def test_seed_policies_generation(self) -> None:
        policies = InsuranceClaimsCorpus.get_seed_policies(count=50)
        assert len(policies) == 50
        assert all(isinstance(p, PolicyRecord) for p in policies)
        for p in policies:
            assert p.sum_assured > 0.0
            assert p.annual_premium > 0.0

    def test_claim_adjudication_approval(self) -> None:
        policies = InsuranceClaimsCorpus.get_seed_policies(count=1)
        policy = policies[0]
        policy.sum_assured = 100000.0
        policy.policy_status = "IN_FORCE"
        ok, msg, claim, payouts = InsuranceClaimsCorpus.adjudicate_in_memory_claim(
            policy, claim_amount=20000.0, decision="APPROVE", deductible_ratio=0.05
        )
        assert ok is True
        assert msg == "APPROVED"
        assert claim.claim_status == "APPROVED"
        assert len(payouts) == 1
        assert payouts[0].disbursed_amount == 19000.0

    def test_claim_adjudication_rejection(self) -> None:
        policies = InsuranceClaimsCorpus.get_seed_policies(count=1)
        policy = policies[0]
        policy.policy_status = "IN_FORCE"
        ok, msg, claim, payouts = InsuranceClaimsCorpus.adjudicate_in_memory_claim(
            policy, claim_amount=10000.0, decision="REJECT"
        )
        assert ok is True
        assert msg == "REJECTED"
        assert claim.claim_status == "REJECTED"
        assert len(payouts) == 0

    def test_claim_sum_assured_boundary_check(self) -> None:
        policies = InsuranceClaimsCorpus.get_seed_policies(count=1)
        policy = policies[0]
        policy.sum_assured = 50000.0
        claim = ClaimRecord(
            claim_no="CLM_2026_001",
            policy_no=policy.policy_no,
            incident_date="2026-01-01",
            reported_date="2026-01-02",
            claim_amount=80000.0,
            approved_amount=0.0,
            claim_status="SUBMITTED",
            adjudicator_id="SYS",
            denial_reason="",
        )
        ok, msg = InsuranceClaimsCorpus.verify_claim_sum_assured_boundary(policy, claim)
        assert ok is False
        assert "Sum Assured" in msg

    def test_beneficiary_allocation_total_verification(self) -> None:
        bens_valid = [
            BeneficiaryRecord(
                beneficiary_id="B1",
                policy_no="POL1",
                beneficiary_name="Ben One",
                relationship="SPOUSE",
                share_percentage=60.0,
            ),
            BeneficiaryRecord(
                beneficiary_id="B2",
                policy_no="POL1",
                beneficiary_name="Ben Two",
                relationship="CHILD",
                share_percentage=40.0,
            ),
        ]
        ok, total, msg = InsuranceClaimsCorpus.verify_beneficiary_allocation_total(bens_valid)
        assert ok is True
        assert abs(total - 100.0) < 0.001

        bens_invalid = [
            BeneficiaryRecord(
                beneficiary_id="B1",
                policy_no="POL1",
                beneficiary_name="Ben One",
                relationship="SPOUSE",
                share_percentage=50.0,
            ),
            BeneficiaryRecord(
                beneficiary_id="B2",
                policy_no="POL1",
                beneficiary_name="Ben Two",
                relationship="CHILD",
                share_percentage=30.0,
            ),
        ]
        ok, total, msg = InsuranceClaimsCorpus.verify_beneficiary_allocation_total(bens_invalid)
        assert ok is False

    def test_actuarial_ibnr_chain_ladder_calculation(self) -> None:
        triangle = [
            LossTriangleRecord(
                origin_year=2024,
                development_year=1,
                line_of_business="CASUALTY",
                cumulative_paid=500000.0,
                incurred_claims=600000.0,
            ),
            LossTriangleRecord(
                origin_year=2024,
                development_year=2,
                line_of_business="CASUALTY",
                cumulative_paid=750000.0,
                incurred_claims=800000.0,
            ),
            LossTriangleRecord(
                origin_year=2025,
                development_year=1,
                line_of_business="CASUALTY",
                cumulative_paid=600000.0,
                incurred_claims=720000.0,
            ),
        ]
        ibnr = InsuranceClaimsCorpus.calculate_ibnr_chain_ladder(
            triangle, origin_year=2025, link_ratio=1.3
        )
        assert ibnr > 0.0
        assert abs(ibnr - 780000.0) < 1.0

    def test_insurance_cdc_stream_simulation(self) -> None:
        claims = [
            ClaimRecord(
                claim_no="C1",
                policy_no="P1",
                incident_date="2026-01-01",
                reported_date="2026-01-02",
                claim_amount=15000.0,
                approved_amount=14250.0,
                claim_status="APPROVED",
                adjudicator_id="SYS",
                denial_reason="",
            ),
        ]
        events = InsuranceClaimsCorpus.simulate_cdc_stream(claims)
        assert len(events) == 1
        assert all(hasattr(e, "event_id") and hasattr(e, "table_name") for e in events)
        assert events[0].table_name == "ins_claims"

    def test_insurance_concurrent_claims_stress(self) -> None:
        res = InsuranceClaimsCorpus.simulate_concurrent_claims_stress(
            concurrency=4, claims_per_worker=10
        )
        assert res["total_claims_processed"] == 40
        assert res["approved_count"] + res["rejected_count"] == 40
        assert res["p95_latency_ms"] <= 100.0
        assert res["boundary_violations"] == 0


class TestTelecomRatingEnterpriseCorpus:
    """Deep test suite for Telecom Real-Time Rating & Quota Depletion Corpus."""

    def test_telecom_raw_sql_structure(self) -> None:
        sql_text = TelecomRatingCorpus.get_raw_sql()
        assert "tel_rate_plans" in sql_text
        assert "tel_subscribers" in sql_text
        assert "tel_quota_wallets" in sql_text
        assert "tel_cdr_records" in sql_text

    def test_seed_rate_plans_generation(self) -> None:
        plans = TelecomRatingCorpus.get_seed_rate_plans()
        assert len(plans) >= 3
        assert all(isinstance(p, RatePlanRecord) for p in plans)
        for p in plans:
            assert p.monthly_fee >= 0.0
            assert p.out_of_bundle_voice_rate >= 0.0
            assert p.out_of_bundle_data_rate >= 0.0

    def test_seed_subscribers_generation(self) -> None:
        subs = TelecomRatingCorpus.get_seed_subscribers(count=40)
        assert len(subs) == 40
        assert all(isinstance(s, SubscriberRecord) for s in subs)
        for s in subs:
            assert s.account_status in ("ACTIVE", "SUSPENDED", "INACTIVE")

    def test_seed_wallets_generation(self) -> None:
        subs = TelecomRatingCorpus.get_seed_subscribers(count=20)
        wallets = TelecomRatingCorpus.get_seed_wallets(subs)
        assert len(wallets) >= 20
        assert all(isinstance(w, QuotaWalletRecord) for w in wallets)
        for w in wallets:
            assert w.total_units >= w.consumed_units
            assert w.reserved_units >= 0

    def test_voice_cdr_rating_within_bundle(self) -> None:
        sub = TelecomRatingCorpus.get_seed_subscribers(count=1)[0]
        plan = TelecomRatingCorpus.get_seed_rate_plans()[0]
        wallet = QuotaWalletRecord(
            wallet_id="W1",
            subscriber_id=sub.subscriber_id,
            unit_type="MINUTES",
            total_units=300,
            consumed_units=50,
            reserved_units=0,
            cycle_start_date="2026-03-01",
            cycle_end_date="2026-03-31",
        )
        charge, deducted, status = TelecomRatingCorpus.rate_voice_cdr_in_memory(
            sub, plan, wallet, duration_seconds=120
        )
        assert charge == 0.0
        assert deducted == 2.0
        assert status == "RATED_FROM_WALLET"
        assert wallet.consumed_units == 52

    def test_voice_cdr_rating_out_of_bundle(self) -> None:
        sub = TelecomRatingCorpus.get_seed_subscribers(count=1)[0]
        plan = TelecomRatingCorpus.get_seed_rate_plans()[0]
        plan.out_of_bundle_voice_rate = 0.15
        wallet = QuotaWalletRecord(
            wallet_id="W2",
            subscriber_id=sub.subscriber_id,
            unit_type="MINUTES",
            total_units=100,
            consumed_units=100,
            reserved_units=0,
            cycle_start_date="2026-03-01",
            cycle_end_date="2026-03-31",
        )
        charge, deducted, status = TelecomRatingCorpus.rate_voice_cdr_in_memory(
            sub, plan, wallet, duration_seconds=180
        )
        assert charge > 0.0
        assert status == "RATED_OVERAGE"

    def test_data_cdr_rating_within_bundle(self) -> None:
        sub = TelecomRatingCorpus.get_seed_subscribers(count=1)[0]
        plan = TelecomRatingCorpus.get_seed_rate_plans()[0]
        wallet = QuotaWalletRecord(
            wallet_id="W3",
            subscriber_id=sub.subscriber_id,
            unit_type="MEGABYTES",
            total_units=10240,
            consumed_units=2048,
            reserved_units=0,
            cycle_start_date="2026-03-01",
            cycle_end_date="2026-03-31",
        )
        charge, deducted_mb, status = TelecomRatingCorpus.rate_data_cdr_in_memory(
            sub, plan, wallet, bytes_transferred=104857600
        )
        assert charge == 0.0
        assert abs(deducted_mb - 100.0) < 0.01
        assert status == "RATED_FROM_WALLET"

    def test_ocs_credit_reservation_and_commit(self) -> None:
        sub = TelecomRatingCorpus.get_seed_subscribers(count=1)[0]
        sub.wallet_balance = 50.0
        ok, msg, resv = TelecomRatingCorpus.reserve_ocs_credit(sub, requested_amount=20.0)
        assert ok is True
        assert msg == "APPROVED"
        assert resv is not None
        assert sub.wallet_balance == 30.0

        commit_ok, refunded = TelecomRatingCorpus.commit_ocs_credit(sub, resv, actual_consumed=12.0)
        assert commit_ok is True
        assert refunded == 8.0
        assert sub.wallet_balance == 38.0

    def test_quota_monotonicity_verification(self) -> None:
        w_before = QuotaWalletRecord(
            wallet_id="W1",
            subscriber_id="SUB_01",
            unit_type="MEGABYTES",
            total_units=10000,
            consumed_units=2000,
            reserved_units=0,
            cycle_start_date="2026-03-01",
            cycle_end_date="2026-03-31",
        )
        w_after_valid = QuotaWalletRecord(
            wallet_id="W1",
            subscriber_id="SUB_01",
            unit_type="MEGABYTES",
            total_units=10000,
            consumed_units=3000,
            reserved_units=0,
            cycle_start_date="2026-03-01",
            cycle_end_date="2026-03-31",
        )
        ok, msg = TelecomRatingCorpus.verify_quota_depletion_monotonicity(w_before, w_after_valid)
        assert ok is True

        w_after_invalid = QuotaWalletRecord(
            wallet_id="W1",
            subscriber_id="SUB_01",
            unit_type="MEGABYTES",
            total_units=10000,
            consumed_units=1500,
            reserved_units=0,
            cycle_start_date="2026-03-01",
            cycle_end_date="2026-03-31",
        )
        ok, msg = TelecomRatingCorpus.verify_quota_depletion_monotonicity(w_before, w_after_invalid)
        assert ok is False
        assert "decreased" in msg

    def test_monthly_bill_reconciliation(self) -> None:
        plan = TelecomRatingCorpus.get_seed_rate_plans()[0]
        plan.monthly_fee = 88.0
        bill = MonthlyBillRecord(
            bill_id="B_202603",
            subscriber_id="SUB_01",
            billing_cycle="202603",
            base_plan_fee=88.0,
            out_bundle_usage=35.5,
            tax_amount=7.41,
            total_due=130.91,
            paid_status="UNPAID",
        )
        ok, errs = TelecomRatingCorpus.verify_monthly_bill_calculation(plan, 35.5, bill)
        assert ok is True, f"Bill errors: {errs}"

    def test_telecom_cdc_stream_simulation(self) -> None:
        cdrs = [
            CdrRecord(
                cdr_id="CDR1",
                subscriber_id="S1",
                service_type="VOICE",
                call_direction="MO",
                calling_party="13800001111",
                called_party="13900002222",
                start_time="2026-03-01 10:00:00",
                duration_seconds=120,
                bytes_transferred=0,
                cell_tower_id="CELL_1",
                roaming_flag=False,
                rated_amount=0.30,
                rating_status="RATED",
            ),
        ]
        events = TelecomRatingCorpus.simulate_cdc_stream(cdrs)
        assert len(events) == 1
        assert all(hasattr(e, "event_id") and hasattr(e, "table_name") for e in events)
        assert events[0].table_name == "tel_cdr_records"

    def test_telecom_concurrent_rating_stress(self) -> None:
        res = TelecomRatingCorpus.simulate_concurrent_cdr_rating_stress(
            concurrency=4, cdrs_per_worker=10
        )
        assert res["total_cdrs_rated"] == 40
        assert res["rated_voice_count"] + res["rated_data_count"] == 40
        assert res["p95_latency_ms"] <= 100.0


class TestSupplyChainLogisticsEnterpriseCorpus:
    """Deep test suite for Supply Chain Logistics & Warehouse FIFO Corpus."""

    def test_supply_chain_raw_sql_structure(self) -> None:
        sql_text = SupplyChainLogisticsCorpus.get_raw_sql()
        assert "scm_warehouses" in sql_text
        assert "scm_sku_items" in sql_text
        assert "scm_inventory_atp" in sql_text
        assert "scm_purchase_orders" in sql_text

    def test_seed_warehouses_generation(self) -> None:
        warehouses = SupplyChainLogisticsCorpus.get_seed_warehouses()
        assert len(warehouses) >= 4
        assert all(isinstance(w, WarehouseRecord) for w in warehouses)
        for wh in warehouses:
            assert wh.total_capacity_sqm > 0.0

    def test_seed_skus_generation(self) -> None:
        skus = SupplyChainLogisticsCorpus.get_seed_skus(count=30)
        assert len(skus) == 30
        assert all(isinstance(s, SkuItemRecord) for s in skus)
        for s in skus:
            assert s.unit_weight_kg > 0.0

    def test_seed_inventory_generation(self) -> None:
        warehouses = SupplyChainLogisticsCorpus.get_seed_warehouses()[:2]
        skus = SupplyChainLogisticsCorpus.get_seed_skus(count=10)
        inv = SupplyChainLogisticsCorpus.get_seed_inventory(warehouses, skus)
        assert len(inv) == 20
        assert all(isinstance(i, InventoryAtpRecord) for i in inv)
        for i in inv:
            assert i.on_hand_qty >= i.allocated_qty
            assert i.available_to_promise >= 0

    def test_in_memory_inventory_allocation_success(self) -> None:
        inv_rec = InventoryAtpRecord(
            wh_code="WH_001",
            sku_id="SKU_0001",
            on_hand_qty=500,
            allocated_qty=100,
            in_transit_qty=50,
            reorder_point=50,
        )
        inv_map = {"WH_001_SKU_0001": inv_rec}
        ok, msg, allocated = SupplyChainLogisticsCorpus.allocate_order_inventory_in_memory(
            inv_map, "WH_001", [{"sku_id": "SKU_0001", "ordered_qty": 150}]
        )
        assert ok is True
        assert "ALLOCATED" in msg
        assert len(allocated) == 1
        assert allocated[0] == ("SKU_0001", 150)
        assert inv_rec.allocated_qty == 250
        assert inv_rec.available_to_promise == 250

    def test_in_memory_inventory_allocation_insufficient_atp(self) -> None:
        inv_rec = InventoryAtpRecord(
            wh_code="WH_001",
            sku_id="SKU_0002",
            on_hand_qty=100,
            allocated_qty=80,
            in_transit_qty=0,
            reorder_point=50,
        )
        inv_map = {"WH_001_SKU_0002": inv_rec}
        ok, msg, allocated = SupplyChainLogisticsCorpus.allocate_order_inventory_in_memory(
            inv_map, "WH_001", [{"sku_id": "SKU_0002", "ordered_qty": 50}]
        )
        assert ok is False
        assert "INSUFFICIENT_ATP" in msg
        assert len(allocated) == 0
        assert inv_rec.allocated_qty == 80

    def test_inbound_asn_receipt(self) -> None:
        inv_rec = InventoryAtpRecord(
            wh_code="WH_001",
            sku_id="SKU_0003",
            on_hand_qty=200,
            allocated_qty=50,
            in_transit_qty=100,
            reorder_point=50,
        )
        inv_map = {"WH_001_SKU_0003": inv_rec}
        SupplyChainLogisticsCorpus.receive_inbound_asn_in_memory(
            inv_map, "WH_001", [("SKU_0003", 100)]
        )
        assert inv_rec.on_hand_qty == 300
        assert inv_rec.available_to_promise == 250

    def test_atp_non_negativity_verification(self) -> None:
        inv_valid = [
            InventoryAtpRecord(
                wh_code="W1",
                sku_id="S1",
                on_hand_qty=100,
                allocated_qty=60,
                in_transit_qty=0,
                reorder_point=10,
            ),
            InventoryAtpRecord(
                wh_code="W1",
                sku_id="S2",
                on_hand_qty=50,
                allocated_qty=50,
                in_transit_qty=0,
                reorder_point=10,
            ),
        ]
        ok, errs = SupplyChainLogisticsCorpus.verify_atp_non_negativity(inv_valid)
        assert ok is True
        assert len(errs) == 0

    def test_inventory_mass_conservation(self) -> None:
        initial = [
            InventoryAtpRecord(
                wh_code="W1",
                sku_id="S1",
                on_hand_qty=1000,
                allocated_qty=0,
                in_transit_qty=0,
                reorder_point=50,
            ),
        ]
        final = [
            InventoryAtpRecord(
                wh_code="W1",
                sku_id="S1",
                on_hand_qty=1150,
                allocated_qty=0,
                in_transit_qty=0,
                reorder_point=50,
            ),
        ]
        ok, diff, msg = SupplyChainLogisticsCorpus.verify_inventory_conservation(
            initial, final, inbound_received=200, outbound_shipped=50
        )
        assert ok is True, msg
        assert diff == 0

    def test_freight_cost_calculation(self) -> None:
        rate = SupplyChainLogisticsCorpus.get_seed_freight_rates()[0]
        cost = SupplyChainLogisticsCorpus.calculate_freight_cost(rate, weight_kg=10.0)
        assert cost > 0.0
        assert abs(cost - (rate.base_fee + 10.0 * rate.per_kg_rate)) < 0.01

    def test_supply_chain_cdc_stream_simulation(self) -> None:
        allocations = [("WH_EAST", "SKU_1", 20), ("WH_WEST", "SKU_2", 15)]
        events = SupplyChainLogisticsCorpus.simulate_cdc_stream(allocations)
        assert len(events) == 2
        assert all(hasattr(e, "event_id") and hasattr(e, "table_name") for e in events)
        assert events[0].table_name == "scm_inventory_atp"

    def test_supply_chain_concurrent_stress(self) -> None:
        res = SupplyChainLogisticsCorpus.simulate_concurrent_order_allocation_stress(
            concurrency=4, orders_per_worker=10
        )
        assert res["total_orders_processed"] == 40
        assert res["success_count"] + res["insufficient_atp_count"] == 40
        assert res["p95_latency_ms"] <= 100.0
        assert res["atp_valid"] is True


class TestErpPayrollEnterpriseCorpus:
    """Deep test suite for Enterprise ERP & 7-Tier Progressive Payroll Corpus."""

    def test_erp_raw_sql_structure(self) -> None:
        sql_text = ErpPayrollCorpus.get_raw_sql()
        assert "erp_legal_entities" in sql_text
        assert "erp_departments" in sql_text
        assert "erp_employees" in sql_text
        assert "erp_tax_brackets" in sql_text
        assert "erp_monthly_payroll" in sql_text

    def test_seed_entities_generation(self) -> None:
        entities = ErpPayrollCorpus.get_seed_entities()
        assert len(entities) >= 2
        assert all(isinstance(e, LegalEntityRecord) for e in entities)
        for e in entities:
            assert len(e.tax_registration_no) > 0

    def test_seed_departments_generation(self) -> None:
        depts = ErpPayrollCorpus.get_seed_departments()
        assert len(depts) >= 4
        assert all(isinstance(d, DepartmentRecord) for d in depts)

    def test_seed_employees_generation(self) -> None:
        emps = ErpPayrollCorpus.get_seed_employees(count=40)
        assert len(emps) == 40
        assert all(isinstance(e, EmployeeRecord) for e in emps)
        for e in emps:
            assert e.base_salary > 0.0

    def test_seed_tax_brackets_progressive_curve(self) -> None:
        brackets = ErpPayrollCorpus.get_seed_tax_brackets()
        assert len(brackets) == 7
        assert all(isinstance(b, TaxBracketRecord) for b in brackets)
        rates = [b.tax_rate for b in brackets]
        assert rates == sorted(rates)
        assert rates[0] == 0.03
        assert rates[-1] == 0.45

    def test_employee_payroll_calculation_mass_balance(self) -> None:
        emp = EmployeeRecord(
            employee_id="EMP_001",
            entity_code="ENT_CN",
            dept_code="D_FIN",
            full_name="Zhang San",
            id_number="110101199001011234",
            hire_date="2020-01-01",
            base_salary=25000.0,
            performance_target=5000.0,
            employment_status="ACTIVE",
        )
        att = AttendanceRecord(
            record_id="ATT_01",
            employee_id=emp.employee_id,
            period_month="202603",
            working_days=22,
            leave_days=0,
            overtime_hours=0,
        )
        payroll = ErpPayrollCorpus.calculate_employee_payroll_in_memory(
            emp, att, period_month="202603"
        )
        assert isinstance(payroll, MonthlyPayrollRecord)
        assert payroll.gross_salary == 25000.0
        assert payroll.social_security_deduction > 0.0
        assert payroll.housing_fund_deduction > 0.0
        assert payroll.income_tax > 0.0
        assert payroll.net_salary > 0.0

        balanced, diff, msg = ErpPayrollCorpus.verify_payroll_mass_balance(payroll)
        assert balanced is True, msg
        assert abs(diff) < 0.01

    def test_payroll_attendance_deduction(self) -> None:
        emp = EmployeeRecord(
            employee_id="EMP_002",
            entity_code="ENT_CN",
            dept_code="D_OPS",
            full_name="Li Si",
            id_number="110101199002022345",
            hire_date="2021-06-01",
            base_salary=10000.0,
            performance_target=0.0,
            employment_status="ACTIVE",
        )
        att = AttendanceRecord(
            record_id="ATT_02",
            employee_id=emp.employee_id,
            period_month="202603",
            working_days=22,
            leave_days=0,
            overtime_hours=10,
        )
        payroll = ErpPayrollCorpus.calculate_employee_payroll_in_memory(
            emp, att, period_month="202603"
        )
        assert payroll.gross_salary > emp.base_salary

    def test_erp_cdc_stream_simulation(self) -> None:
        payrolls = [
            MonthlyPayrollRecord(
                payroll_id="PR_01",
                employee_id="E01",
                period_month="202603",
                gross_salary=15000.0,
                social_security_deduction=1575.0,
                housing_fund_deduction=1050.0,
                income_tax=221.25,
                net_salary=12153.75,
                payout_status="PAID",
            ),
        ]
        events = ErpPayrollCorpus.simulate_cdc_stream(payrolls)
        assert len(events) == 1
        assert all(hasattr(e, "event_id") and hasattr(e, "table_name") for e in events)
        assert events[0].table_name == "erp_monthly_payroll"

    def test_erp_concurrent_payroll_stress(self) -> None:
        res = ErpPayrollCorpus.simulate_concurrent_payroll_stress(
            concurrency=4, batches_per_worker=10
        )
        assert res["total_payrolls_calculated"] == 40
        assert res["calculated_count"] == 40
        assert res["p95_latency_ms"] <= 100.0
        assert res["balance_failures"] == 0


class TestEnterpriseCorporaCrossDialectLowering:
    """Comprehensive AST lowering matrix: 5 Enterprise Corpora to 13 ChinaDB Targets."""

    @pytest.mark.parametrize(
        "target_id",
        [
            "dm8",
            "kingbase",
            "opengauss",
            "tidb",
            "gbase8s",
            "gbase8c",
            "gbase8a",
            "highgo",
            "oceanbase_oracle",
            "oceanbase_mysql",
            "gaussdb_oracle",
            "gaussdb_mysql",
            "goldendb",
        ],
    )
    def test_banking_ddl_lowering_matrix(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        source_ddl = """
        CREATE TABLE ACCOUNT_MASTER (
            ACCOUNT_NO VARCHAR2(32) NOT NULL,
            CUSTOMER_ID VARCHAR2(32) NOT NULL,
            BRANCH_CODE VARCHAR2(16) NOT NULL,
            ACCOUNT_TYPE VARCHAR2(16) NOT NULL,
            CURRENCY_CODE VARCHAR2(3) DEFAULT 'CNY' NOT NULL,
            BALANCE NUMBER(18, 4) DEFAULT 0.0 NOT NULL,
            AVAILABLE_BALANCE NUMBER(18, 4) DEFAULT 0.0 NOT NULL,
            STATUS VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
            OPEN_DATE DATE DEFAULT SYSDATE NOT NULL,
            LAST_UPDATED TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT PK_ACCOUNT_MASTER PRIMARY KEY (ACCOUNT_NO)
        );
        """
        res = lowerer.lower_table_ddl(source_ddl, source_dialect="oracle")
        assert res is not None
        assert len(res) > 0
        assert "ACCOUNT_MASTER" in res.upper()

    @pytest.mark.parametrize(
        "target_id",
        [
            "dm8",
            "kingbase",
            "opengauss",
            "tidb",
            "gbase8s",
            "gbase8c",
            "gbase8a",
            "highgo",
            "oceanbase_oracle",
            "oceanbase_mysql",
            "gaussdb_oracle",
            "gaussdb_mysql",
            "goldendb",
        ],
    )
    def test_insurance_ddl_lowering_matrix(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        source_ddl = """
        CREATE TABLE INS_CLAIM (
            CLAIM_ID VARCHAR2(32) NOT NULL,
            CLAIM_NO VARCHAR2(32) NOT NULL,
            POLICY_NO VARCHAR2(32) NOT NULL,
            CLAIMANT_ID VARCHAR2(32) NOT NULL,
            CLAIM_AMOUNT NUMBER(18, 2) NOT NULL,
            DEDUCTIBLE_AMOUNT NUMBER(18, 2) DEFAULT 0.0 NOT NULL,
            APPROVED_AMOUNT NUMBER(18, 2) DEFAULT 0.0 NOT NULL,
            STATUS VARCHAR2(16) DEFAULT 'SUBMITTED' NOT NULL,
            ACCIDENT_DATE DATE NOT NULL,
            REPORT_DATE DATE DEFAULT SYSDATE NOT NULL,
            CONSTRAINT PK_INS_CLAIM PRIMARY KEY (CLAIM_ID)
        );
        """
        res = lowerer.lower_table_ddl(source_ddl, source_dialect="oracle")
        assert res is not None
        assert "INS_CLAIM" in res.upper()

    @pytest.mark.parametrize(
        "target_id",
        [
            "dm8",
            "kingbase",
            "opengauss",
            "tidb",
            "gbase8s",
            "gbase8c",
            "gbase8a",
            "highgo",
            "oceanbase_oracle",
            "oceanbase_mysql",
            "gaussdb_oracle",
            "gaussdb_mysql",
            "goldendb",
        ],
    )
    def test_telecom_ddl_lowering_matrix(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        source_ddl = """
        CREATE TABLE TEL_CDR_RATED (
            CDR_ID VARCHAR2(64) NOT NULL,
            IMSI VARCHAR2(32) NOT NULL,
            CALL_TYPE VARCHAR2(16) NOT NULL,
            START_TIME TIMESTAMP NOT NULL,
            DURATION_SEC NUMBER(8, 0) DEFAULT 0 NOT NULL,
            BYTES_TRANSFERRED NUMBER(16, 0) DEFAULT 0 NOT NULL,
            CHARGED_AMOUNT NUMBER(12, 4) DEFAULT 0.0 NOT NULL,
            WALLET_DEDUCTED NUMBER(12, 4) DEFAULT 0.0 NOT NULL,
            RATING_TIMESTAMP TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT PK_TEL_CDR_RATED PRIMARY KEY (CDR_ID)
        );
        """
        res = lowerer.lower_table_ddl(source_ddl, source_dialect="oracle")
        assert res is not None
        assert "TEL_CDR_RATED" in res.upper()

    @pytest.mark.parametrize(
        "target_id",
        [
            "dm8",
            "kingbase",
            "opengauss",
            "tidb",
            "gbase8s",
            "gbase8c",
            "gbase8a",
            "highgo",
            "oceanbase_oracle",
            "oceanbase_mysql",
            "gaussdb_oracle",
            "gaussdb_mysql",
            "goldendb",
        ],
    )
    def test_supply_chain_ddl_lowering_matrix(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        source_ddl = """
        CREATE TABLE WMS_INVENTORY_BALANCE (
            BALANCE_ID VARCHAR2(32) NOT NULL,
            WH_CODE VARCHAR2(32) NOT NULL,
            SKU_CODE VARCHAR2(64) NOT NULL,
            LOT_NO VARCHAR2(32) DEFAULT 'DEFAULT' NOT NULL,
            ON_HAND_QTY NUMBER(12, 0) DEFAULT 0 NOT NULL,
            ALLOCATED_QTY NUMBER(12, 0) DEFAULT 0 NOT NULL,
            AVAILABLE_ATP NUMBER(12, 0) DEFAULT 0 NOT NULL,
            LAST_UPDATED TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT PK_WMS_INV_BAL PRIMARY KEY (BALANCE_ID)
        );
        """
        res = lowerer.lower_table_ddl(source_ddl, source_dialect="oracle")
        assert res is not None
        assert "WMS_INVENTORY_BALANCE" in res.upper()

    @pytest.mark.parametrize(
        "target_id",
        [
            "dm8",
            "kingbase",
            "opengauss",
            "tidb",
            "gbase8s",
            "gbase8c",
            "gbase8a",
            "highgo",
            "oceanbase_oracle",
            "oceanbase_mysql",
            "gaussdb_oracle",
            "gaussdb_mysql",
            "goldendb",
        ],
    )
    def test_erp_ddl_lowering_matrix(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        source_ddl = """
        CREATE TABLE HR_PAYROLL_MONTHLY (
            PAYROLL_ID VARCHAR2(32) NOT NULL,
            EMPLOYEE_ID VARCHAR2(32) NOT NULL,
            PERIOD_MONTH VARCHAR2(6) NOT NULL,
            GROSS_SALARY NUMBER(14, 2) NOT NULL,
            SOCIAL_SECURITY NUMBER(14, 2) DEFAULT 0.0 NOT NULL,
            HOUSING_FUND NUMBER(14, 2) DEFAULT 0.0 NOT NULL,
            TAXABLE_INCOME NUMBER(14, 2) DEFAULT 0.0 NOT NULL,
            INCOME_TAX NUMBER(14, 2) DEFAULT 0.0 NOT NULL,
            NET_SALARY NUMBER(14, 2) NOT NULL,
            PAYMENT_STATUS VARCHAR2(16) DEFAULT 'PENDING' NOT NULL,
            CONSTRAINT PK_HR_PAYROLL PRIMARY KEY (PAYROLL_ID)
        );
        """
        res = lowerer.lower_table_ddl(source_ddl, source_dialect="oracle")
        assert res is not None
        assert "HR_PAYROLL_MONTHLY" in res.upper()


class TestEnterpriseCorporaComplexQueriesLowering:
    """Test lowering complex queries with window functions, CTEs, and outer joins."""

    @pytest.mark.parametrize(
        "target_id",
        [
            "dm8",
            "kingbase",
            "opengauss",
            "tidb",
            "gbase8s",
            "gbase8c",
            "gbase8a",
            "highgo",
            "oceanbase_oracle",
            "oceanbase_mysql",
            "gaussdb_oracle",
            "gaussdb_mysql",
            "goldendb",
        ],
    )
    def test_banking_window_aggregation_query(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        query = """
        SELECT
            ACCOUNT_NO,
            TX_DATE,
            AMOUNT,
            NVL(FEE, 0) AS FEE,
            SUM(AMOUNT) OVER (PARTITION BY ACCOUNT_NO ORDER BY TX_DATE) AS RUNNING_BAL,
            ROW_NUMBER() OVER (PARTITION BY ACCOUNT_NO ORDER BY TX_DATE DESC) AS RN
        FROM JOURNAL_ENTRY
        WHERE STATUS = 'SETTLED';
        """
        res = lowerer.lower_statement(query, source_dialect="oracle", asset_kind="DML")
        assert res is not None
        assert "JOURNAL_ENTRY" in res.upper()
        assert "OVER" in res.upper()

    @pytest.mark.parametrize(
        "target_id",
        [
            "dm8",
            "kingbase",
            "opengauss",
            "tidb",
            "gbase8s",
            "gbase8c",
            "gbase8a",
            "highgo",
            "oceanbase_oracle",
            "oceanbase_mysql",
            "gaussdb_oracle",
            "gaussdb_mysql",
            "goldendb",
        ],
    )
    def test_insurance_loss_development_cte_query(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        query = """
        WITH DEV_SUMMARY AS (
            SELECT
                ORIGIN_YEAR,
                DEV_YEAR,
                SUM(PAID_AMOUNT) AS TOTAL_PAID
            FROM INS_PAYOUT
            GROUP BY ORIGIN_YEAR, DEV_YEAR
        )
        SELECT
            ORIGIN_YEAR,
            DEV_YEAR,
            TOTAL_PAID,
            LAG(TOTAL_PAID, 1, 0) OVER (
                PARTITION BY ORIGIN_YEAR ORDER BY DEV_YEAR
            ) AS PREV_PAID
        FROM DEV_SUMMARY;
        """
        res = lowerer.lower_statement(query, source_dialect="oracle", asset_kind="DML")
        assert res is not None
        assert "DEV_SUMMARY" in res.upper()

    @pytest.mark.parametrize(
        "target_id",
        [
            "dm8",
            "kingbase",
            "opengauss",
            "tidb",
            "gbase8s",
            "gbase8c",
            "gbase8a",
            "highgo",
            "oceanbase_oracle",
            "oceanbase_mysql",
            "gaussdb_oracle",
            "gaussdb_mysql",
            "goldendb",
        ],
    )
    def test_telecom_rating_aggregation_query(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        query = """
        SELECT
            IMSI,
            TRUNC(START_TIME) AS CALL_DAY,
            COUNT(*) AS CALL_COUNT,
            SUM(DURATION_SEC) AS TOTAL_DURATION,
            SUM(CHARGED_AMOUNT) AS TOTAL_CHARGE
        FROM TEL_CDR_RATED
        GROUP BY IMSI, TRUNC(START_TIME);
        """
        res = lowerer.lower_statement(query, source_dialect="oracle", asset_kind="DML")
        assert res is not None
        assert "TEL_CDR_RATED" in res.upper()

    @pytest.mark.parametrize(
        "target_id",
        [
            "dm8",
            "kingbase",
            "opengauss",
            "tidb",
            "gbase8s",
            "gbase8c",
            "gbase8a",
            "highgo",
            "oceanbase_oracle",
            "oceanbase_mysql",
            "gaussdb_oracle",
            "gaussdb_mysql",
            "goldendb",
        ],
    )
    def test_supply_chain_fifo_lot_query(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        query = """
        SELECT
            WH_CODE,
            SKU_CODE,
            LOT_NO,
            ON_HAND_QTY - ALLOCATED_QTY AS AVAILABLE_QTY,
            EXPIRY_DATE,
            ROW_NUMBER() OVER (
                PARTITION BY WH_CODE, SKU_CODE
                ORDER BY EXPIRY_DATE ASC, CREATED_DATE ASC
            ) AS FIFO_PRIORITY
        FROM WMS_INVENTORY_BALANCE
        WHERE ON_HAND_QTY > ALLOCATED_QTY;
        """
        res = lowerer.lower_statement(query, source_dialect="oracle", asset_kind="DML")
        assert res is not None
        assert "WMS_INVENTORY_BALANCE" in res.upper()

    @pytest.mark.parametrize(
        "target_id",
        [
            "dm8",
            "kingbase",
            "opengauss",
            "tidb",
            "gbase8s",
            "gbase8c",
            "gbase8a",
            "highgo",
            "oceanbase_oracle",
            "oceanbase_mysql",
            "gaussdb_oracle",
            "gaussdb_mysql",
            "goldendb",
        ],
    )
    def test_erp_payroll_department_rollup_query(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        query = """
        SELECT
            E.ENTITY_ID,
            E.DEPARTMENT_ID,
            COUNT(*) AS HEADCOUNT,
            SUM(P.GROSS_SALARY) AS TOTAL_GROSS,
            SUM(P.NET_SALARY) AS TOTAL_NET,
            SUM(P.INCOME_TAX) AS TOTAL_TAX
        FROM HR_PAYROLL_MONTHLY P
        JOIN HR_EMPLOYEE E ON P.EMPLOYEE_ID = E.EMPLOYEE_ID
        WHERE P.PERIOD_MONTH = '202603'
        GROUP BY E.ENTITY_ID, E.DEPARTMENT_ID;
        """
        res = lowerer.lower_statement(query, source_dialect="oracle", asset_kind="DML")
        assert res is not None
        assert "HR_PAYROLL_MONTHLY" in res.upper()


class TestEnterpriseCorporaL5SelfHealingIntegration:
    """Test L5 Autonomous Self-Healing on enterprise-scale migration error patterns."""

    @pytest.fixture
    def healing_engine(self) -> AutonomousDatabaseSelfHealingEngine:
        return AutonomousDatabaseSelfHealingEngine()

    def test_banking_nvl2_healing_on_opengauss(
        self, healing_engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        failing_sql = (
            "SELECT ACCOUNT_NO, NVL(FEE_AMT, 0) AS FEE FROM JOURNAL_ENTRY WHERE STATUS = 1;"
        )
        err_msg = "42883: function nvl(numeric, integer) does not exist"
        ok, repaired, receipt = healing_engine.autonomous_repair_and_verify(
            failing_sql=failing_sql,
            raw_error=err_msg,
            target_engine="opengauss",
            sandbox_verifier=lambda s: (True, "OK"),
        )
        assert ok is True
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True
        assert len(repaired) > 0
        assert "COALESCE" in repaired

    def test_insurance_sysdate_healing_on_tidb(
        self, healing_engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        failing_sql = "INSERT INTO INS_CLAIM (CLAIM_ID, REPORT_DATE) VALUES (101, SYSDATE);"
        err_msg = "Error 1064: You have an error in your SQL syntax near 'SYSDATE'"
        ok, repaired, receipt = healing_engine.autonomous_repair_and_verify(
            failing_sql=failing_sql,
            raw_error=err_msg,
            target_engine="tidb",
            sandbox_verifier=lambda s: (True, "OK"),
        )
        assert ok is True
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_telecom_sequence_healing_on_mysql_family(
        self, healing_engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        failing_sql = (
            "INSERT INTO TEL_CDR_RAW (CDR_ID, IMSI) VALUES (SEQ_CDR_ID.NEXTVAL, 460010001);"
        )
        err_msg = "Error 1054: Unknown column 'SEQ_CDR_ID.NEXTVAL' in 'field list'"
        ok, repaired, receipt = healing_engine.autonomous_repair_and_verify(
            failing_sql=failing_sql,
            raw_error=err_msg,
            target_engine="oceanbase_mysql",
            sandbox_verifier=lambda s: (True, "OK"),
        )
        assert ok is True
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_supply_chain_keyword_escaping_healing(
        self, healing_engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        failing_sql = "SELECT ORDER, SKU_CODE FROM TMS_TRANSPORT_ORDER;"
        err_msg = "42703: KingbaseES: 字段不存在: ORDER"
        ok, repaired, receipt = healing_engine.autonomous_repair_and_verify(
            failing_sql=failing_sql,
            raw_error=err_msg,
            target_engine="kingbase",
            sandbox_verifier=lambda s: (True, "OK"),
        )
        assert ok is True
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True

    def test_erp_type_cast_mismatch_healing(
        self, healing_engine: AutonomousDatabaseSelfHealingEngine
    ) -> None:
        failing_sql = "SELECT * FROM HR_PAYROLL_MONTHLY WHERE PERIOD_MONTH = 202603;"
        err_msg = "ERROR: 42804: datatype mismatch, cannot cast type text to integer"
        ok, repaired, receipt = healing_engine.autonomous_repair_and_verify(
            failing_sql=failing_sql,
            raw_error=err_msg,
            target_engine="gaussdb_oracle",
            sandbox_verifier=lambda s: (True, "OK"),
        )
        assert ok is True
        assert receipt.zero_human_intervention is True
        assert receipt.verification_passed is True


class TestEnterpriseCorporaFullAutonomousMigrationLifecycle:
    """Full 9-stage autonomous migration engine test with enterprise corpora."""

    @pytest.fixture
    def migration_config(self) -> AutonomousMigrationConfig:
        return AutonomousMigrationConfig(
            project_id="test_enterprise_migration",
            source_engine="oracle",
            target_engine="dm8",
            concurrency_threads=4,
            target_p95_latency_ms=75.0,
            zero_human_review_required=True,
        )

    def test_banking_corpus_autonomous_migration_lifecycle(
        self, migration_config: AutonomousMigrationConfig
    ) -> None:
        engine = AutonomousDatabaseMigrationEngine(config=migration_config)
        engine.register_source_assets(
            [
                {
                    "asset_id": "BANK_DDL_01",
                    "asset_name": "ACCOUNT_MASTER",
                    "asset_kind": "TABLE",
                    "source_dialect": "oracle",
                    "source_ddl": (
                        "CREATE TABLE ACCOUNT_MASTER (ACCOUNT_NO VARCHAR2(32) NOT NULL, "
                        "BALANCE NUMBER(18, 4) NOT NULL);"
                    ),
                },
            ]
        )
        dossier = engine.execute_full_migration()
        assert isinstance(dossier, AutonomousMigrationDossier)
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0
        assert dossier.autonomy_level == "L5_AUTONOMOUS_ZERO_HUMAN"
        assert len(dossier.stages) == 9

    def test_insurance_corpus_autonomous_migration_lifecycle(
        self, migration_config: AutonomousMigrationConfig
    ) -> None:
        engine = AutonomousDatabaseMigrationEngine(config=migration_config)
        engine.config.target_engine = "kingbase"
        engine.register_source_assets(
            [
                {
                    "asset_id": "INS_DDL_01",
                    "asset_name": "INS_CLAIM",
                    "asset_kind": "TABLE",
                    "source_dialect": "oracle",
                    "source_ddl": (
                        "CREATE TABLE INS_CLAIM (CLAIM_ID VARCHAR2(32) NOT NULL, "
                        "AMOUNT NUMBER(18, 2) NOT NULL);"
                    ),
                },
            ]
        )
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0

    def test_telecom_corpus_autonomous_migration_lifecycle(
        self, migration_config: AutonomousMigrationConfig
    ) -> None:
        engine = AutonomousDatabaseMigrationEngine(config=migration_config)
        engine.config.target_engine = "opengauss"
        engine.register_source_assets(
            [
                {
                    "asset_id": "TEL_DDL_01",
                    "asset_name": "TEL_CDR",
                    "asset_kind": "TABLE",
                    "source_dialect": "oracle",
                    "source_ddl": (
                        "CREATE TABLE TEL_CDR (CDR_ID VARCHAR2(64) NOT NULL, "
                        "DURATION NUMBER(8, 0) NOT NULL);"
                    ),
                },
            ]
        )
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0

    def test_supply_chain_corpus_autonomous_migration_lifecycle(
        self, migration_config: AutonomousMigrationConfig
    ) -> None:
        engine = AutonomousDatabaseMigrationEngine(config=migration_config)
        engine.config.target_engine = "tidb"
        engine.register_source_assets(
            [
                {
                    "asset_id": "WMS_DDL_01",
                    "asset_name": "WMS_BALANCE",
                    "asset_kind": "TABLE",
                    "source_dialect": "oracle",
                    "source_ddl": (
                        "CREATE TABLE WMS_BALANCE (WH_CODE VARCHAR2(32) NOT NULL, "
                        "ON_HAND NUMBER(12, 0) NOT NULL);"
                    ),
                },
            ]
        )
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0

    def test_erp_corpus_autonomous_migration_lifecycle(
        self, migration_config: AutonomousMigrationConfig
    ) -> None:
        engine = AutonomousDatabaseMigrationEngine(config=migration_config)
        engine.config.target_engine = "highgo"
        engine.register_source_assets(
            [
                {
                    "asset_id": "ERP_DDL_01",
                    "asset_name": "HR_PAYROLL",
                    "asset_kind": "TABLE",
                    "source_dialect": "oracle",
                    "source_ddl": (
                        "CREATE TABLE HR_PAYROLL (PAYROLL_ID VARCHAR2(32) NOT NULL, "
                        "GROSS NUMBER(14, 2) NOT NULL);"
                    ),
                },
            ]
        )
        dossier = engine.execute_full_migration()
        assert dossier.overall_success is True
        assert dossier.human_review_backlog_count == 0


class TestBankingCorpusExhaustiveTargetMatrix:
    """Exhaustive target compatibility matrix for Banking Enterprise Corpus."""

    @pytest.fixture
    def corpus(self) -> type[BankingSettlementCorpus]:
        return BankingSettlementCorpus

    def test_banking_lowering_to_dm8(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DDL to dm8."""
        lowerer = get_chinadb_lowerer("dm8")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_dm8(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DML to dm8."""
        lowerer = get_chinadb_lowerer("dm8")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_kingbase(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DDL to kingbase."""
        lowerer = get_chinadb_lowerer("kingbase")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_kingbase(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DML to kingbase."""
        lowerer = get_chinadb_lowerer("kingbase")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_opengauss(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DDL to opengauss."""
        lowerer = get_chinadb_lowerer("opengauss")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_opengauss(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DML to opengauss."""
        lowerer = get_chinadb_lowerer("opengauss")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_tidb(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DDL to tidb."""
        lowerer = get_chinadb_lowerer("tidb")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_tidb(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DML to tidb."""
        lowerer = get_chinadb_lowerer("tidb")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_gbase8s(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DDL to gbase8s."""
        lowerer = get_chinadb_lowerer("gbase8s")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_gbase8s(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DML to gbase8s."""
        lowerer = get_chinadb_lowerer("gbase8s")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_gbase8c(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DDL to gbase8c."""
        lowerer = get_chinadb_lowerer("gbase8c")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_gbase8c(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DML to gbase8c."""
        lowerer = get_chinadb_lowerer("gbase8c")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_gbase8a(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DDL to gbase8a."""
        lowerer = get_chinadb_lowerer("gbase8a")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_gbase8a(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DML to gbase8a."""
        lowerer = get_chinadb_lowerer("gbase8a")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_highgo(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DDL to highgo."""
        lowerer = get_chinadb_lowerer("highgo")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_highgo(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DML to highgo."""
        lowerer = get_chinadb_lowerer("highgo")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_oceanbase_oracle(
        self, corpus: type[BankingSettlementCorpus]
    ) -> None:
        """Validate lowering Banking DDL to oceanbase_oracle."""
        lowerer = get_chinadb_lowerer("oceanbase_oracle")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_oceanbase_oracle(
        self, corpus: type[BankingSettlementCorpus]
    ) -> None:
        """Validate lowering Banking DML to oceanbase_oracle."""
        lowerer = get_chinadb_lowerer("oceanbase_oracle")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_oceanbase_mysql(
        self, corpus: type[BankingSettlementCorpus]
    ) -> None:
        """Validate lowering Banking DDL to oceanbase_mysql."""
        lowerer = get_chinadb_lowerer("oceanbase_mysql")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_oceanbase_mysql(
        self, corpus: type[BankingSettlementCorpus]
    ) -> None:
        """Validate lowering Banking DML to oceanbase_mysql."""
        lowerer = get_chinadb_lowerer("oceanbase_mysql")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_gaussdb_oracle(
        self, corpus: type[BankingSettlementCorpus]
    ) -> None:
        """Validate lowering Banking DDL to gaussdb_oracle."""
        lowerer = get_chinadb_lowerer("gaussdb_oracle")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_gaussdb_oracle(
        self, corpus: type[BankingSettlementCorpus]
    ) -> None:
        """Validate lowering Banking DML to gaussdb_oracle."""
        lowerer = get_chinadb_lowerer("gaussdb_oracle")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_gaussdb_mysql(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DDL to gaussdb_mysql."""
        lowerer = get_chinadb_lowerer("gaussdb_mysql")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_gaussdb_mysql(
        self, corpus: type[BankingSettlementCorpus]
    ) -> None:
        """Validate lowering Banking DML to gaussdb_mysql."""
        lowerer = get_chinadb_lowerer("gaussdb_mysql")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_banking_lowering_to_goldendb(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DDL to goldendb."""
        lowerer = get_chinadb_lowerer("goldendb")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_banking_dml_lowering_to_goldendb(self, corpus: type[BankingSettlementCorpus]) -> None:
        """Validate lowering Banking DML to goldendb."""
        lowerer = get_chinadb_lowerer("goldendb")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM BANKING_SETTLEMENT_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()


class TestInsuranceCorpusExhaustiveTargetMatrix:
    """Exhaustive target compatibility matrix for Insurance Enterprise Corpus."""

    @pytest.fixture
    def corpus(self) -> type[InsuranceClaimsCorpus]:
        return InsuranceClaimsCorpus

    def test_insurance_lowering_to_dm8(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DDL to dm8."""
        lowerer = get_chinadb_lowerer("dm8")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_dm8(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DML to dm8."""
        lowerer = get_chinadb_lowerer("dm8")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_kingbase(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DDL to kingbase."""
        lowerer = get_chinadb_lowerer("kingbase")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_kingbase(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DML to kingbase."""
        lowerer = get_chinadb_lowerer("kingbase")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_opengauss(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DDL to opengauss."""
        lowerer = get_chinadb_lowerer("opengauss")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_opengauss(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DML to opengauss."""
        lowerer = get_chinadb_lowerer("opengauss")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_tidb(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DDL to tidb."""
        lowerer = get_chinadb_lowerer("tidb")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_tidb(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DML to tidb."""
        lowerer = get_chinadb_lowerer("tidb")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_gbase8s(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DDL to gbase8s."""
        lowerer = get_chinadb_lowerer("gbase8s")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_gbase8s(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DML to gbase8s."""
        lowerer = get_chinadb_lowerer("gbase8s")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_gbase8c(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DDL to gbase8c."""
        lowerer = get_chinadb_lowerer("gbase8c")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_gbase8c(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DML to gbase8c."""
        lowerer = get_chinadb_lowerer("gbase8c")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_gbase8a(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DDL to gbase8a."""
        lowerer = get_chinadb_lowerer("gbase8a")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_gbase8a(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DML to gbase8a."""
        lowerer = get_chinadb_lowerer("gbase8a")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_highgo(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DDL to highgo."""
        lowerer = get_chinadb_lowerer("highgo")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_highgo(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DML to highgo."""
        lowerer = get_chinadb_lowerer("highgo")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_oceanbase_oracle(
        self, corpus: type[InsuranceClaimsCorpus]
    ) -> None:
        """Validate lowering Insurance DDL to oceanbase_oracle."""
        lowerer = get_chinadb_lowerer("oceanbase_oracle")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_oceanbase_oracle(
        self, corpus: type[InsuranceClaimsCorpus]
    ) -> None:
        """Validate lowering Insurance DML to oceanbase_oracle."""
        lowerer = get_chinadb_lowerer("oceanbase_oracle")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_oceanbase_mysql(
        self, corpus: type[InsuranceClaimsCorpus]
    ) -> None:
        """Validate lowering Insurance DDL to oceanbase_mysql."""
        lowerer = get_chinadb_lowerer("oceanbase_mysql")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_oceanbase_mysql(
        self, corpus: type[InsuranceClaimsCorpus]
    ) -> None:
        """Validate lowering Insurance DML to oceanbase_mysql."""
        lowerer = get_chinadb_lowerer("oceanbase_mysql")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_gaussdb_oracle(
        self, corpus: type[InsuranceClaimsCorpus]
    ) -> None:
        """Validate lowering Insurance DDL to gaussdb_oracle."""
        lowerer = get_chinadb_lowerer("gaussdb_oracle")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_gaussdb_oracle(
        self, corpus: type[InsuranceClaimsCorpus]
    ) -> None:
        """Validate lowering Insurance DML to gaussdb_oracle."""
        lowerer = get_chinadb_lowerer("gaussdb_oracle")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_gaussdb_mysql(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DDL to gaussdb_mysql."""
        lowerer = get_chinadb_lowerer("gaussdb_mysql")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_gaussdb_mysql(
        self, corpus: type[InsuranceClaimsCorpus]
    ) -> None:
        """Validate lowering Insurance DML to gaussdb_mysql."""
        lowerer = get_chinadb_lowerer("gaussdb_mysql")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_insurance_lowering_to_goldendb(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DDL to goldendb."""
        lowerer = get_chinadb_lowerer("goldendb")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_insurance_dml_lowering_to_goldendb(self, corpus: type[InsuranceClaimsCorpus]) -> None:
        """Validate lowering Insurance DML to goldendb."""
        lowerer = get_chinadb_lowerer("goldendb")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM INSURANCE_CLAIMS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()


class TestTelecomCorpusExhaustiveTargetMatrix:
    """Exhaustive target compatibility matrix for Telecom Enterprise Corpus."""

    @pytest.fixture
    def corpus(self) -> type[TelecomRatingCorpus]:
        return TelecomRatingCorpus

    def test_telecom_lowering_to_dm8(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to dm8."""
        lowerer = get_chinadb_lowerer("dm8")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_dm8(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DML to dm8."""
        lowerer = get_chinadb_lowerer("dm8")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_kingbase(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to kingbase."""
        lowerer = get_chinadb_lowerer("kingbase")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_kingbase(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DML to kingbase."""
        lowerer = get_chinadb_lowerer("kingbase")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_opengauss(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to opengauss."""
        lowerer = get_chinadb_lowerer("opengauss")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_opengauss(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DML to opengauss."""
        lowerer = get_chinadb_lowerer("opengauss")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_tidb(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to tidb."""
        lowerer = get_chinadb_lowerer("tidb")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_tidb(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DML to tidb."""
        lowerer = get_chinadb_lowerer("tidb")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_gbase8s(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to gbase8s."""
        lowerer = get_chinadb_lowerer("gbase8s")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_gbase8s(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DML to gbase8s."""
        lowerer = get_chinadb_lowerer("gbase8s")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_gbase8c(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to gbase8c."""
        lowerer = get_chinadb_lowerer("gbase8c")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_gbase8c(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DML to gbase8c."""
        lowerer = get_chinadb_lowerer("gbase8c")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_gbase8a(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to gbase8a."""
        lowerer = get_chinadb_lowerer("gbase8a")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_gbase8a(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DML to gbase8a."""
        lowerer = get_chinadb_lowerer("gbase8a")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_highgo(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to highgo."""
        lowerer = get_chinadb_lowerer("highgo")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_highgo(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DML to highgo."""
        lowerer = get_chinadb_lowerer("highgo")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_oceanbase_oracle(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to oceanbase_oracle."""
        lowerer = get_chinadb_lowerer("oceanbase_oracle")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_oceanbase_oracle(
        self, corpus: type[TelecomRatingCorpus]
    ) -> None:
        """Validate lowering Telecom DML to oceanbase_oracle."""
        lowerer = get_chinadb_lowerer("oceanbase_oracle")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_oceanbase_mysql(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to oceanbase_mysql."""
        lowerer = get_chinadb_lowerer("oceanbase_mysql")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_oceanbase_mysql(
        self, corpus: type[TelecomRatingCorpus]
    ) -> None:
        """Validate lowering Telecom DML to oceanbase_mysql."""
        lowerer = get_chinadb_lowerer("oceanbase_mysql")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_gaussdb_oracle(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to gaussdb_oracle."""
        lowerer = get_chinadb_lowerer("gaussdb_oracle")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_gaussdb_oracle(
        self, corpus: type[TelecomRatingCorpus]
    ) -> None:
        """Validate lowering Telecom DML to gaussdb_oracle."""
        lowerer = get_chinadb_lowerer("gaussdb_oracle")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_gaussdb_mysql(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to gaussdb_mysql."""
        lowerer = get_chinadb_lowerer("gaussdb_mysql")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_gaussdb_mysql(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DML to gaussdb_mysql."""
        lowerer = get_chinadb_lowerer("gaussdb_mysql")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_telecom_lowering_to_goldendb(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DDL to goldendb."""
        lowerer = get_chinadb_lowerer("goldendb")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_telecom_dml_lowering_to_goldendb(self, corpus: type[TelecomRatingCorpus]) -> None:
        """Validate lowering Telecom DML to goldendb."""
        lowerer = get_chinadb_lowerer("goldendb")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM TELECOM_RATING_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()


class TestSupplyChainCorpusExhaustiveTargetMatrix:
    """Exhaustive target compatibility matrix for SupplyChain Enterprise Corpus."""

    @pytest.fixture
    def corpus(self) -> type[SupplyChainLogisticsCorpus]:
        return SupplyChainLogisticsCorpus

    def test_supplychain_lowering_to_dm8(self, corpus: type[SupplyChainLogisticsCorpus]) -> None:
        """Validate lowering SupplyChain DDL to dm8."""
        lowerer = get_chinadb_lowerer("dm8")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_dm8(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to dm8."""
        lowerer = get_chinadb_lowerer("dm8")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_kingbase(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DDL to kingbase."""
        lowerer = get_chinadb_lowerer("kingbase")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_kingbase(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to kingbase."""
        lowerer = get_chinadb_lowerer("kingbase")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_opengauss(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DDL to opengauss."""
        lowerer = get_chinadb_lowerer("opengauss")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_opengauss(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to opengauss."""
        lowerer = get_chinadb_lowerer("opengauss")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_tidb(self, corpus: type[SupplyChainLogisticsCorpus]) -> None:
        """Validate lowering SupplyChain DDL to tidb."""
        lowerer = get_chinadb_lowerer("tidb")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_tidb(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to tidb."""
        lowerer = get_chinadb_lowerer("tidb")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_gbase8s(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DDL to gbase8s."""
        lowerer = get_chinadb_lowerer("gbase8s")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_gbase8s(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to gbase8s."""
        lowerer = get_chinadb_lowerer("gbase8s")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_gbase8c(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DDL to gbase8c."""
        lowerer = get_chinadb_lowerer("gbase8c")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_gbase8c(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to gbase8c."""
        lowerer = get_chinadb_lowerer("gbase8c")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_gbase8a(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DDL to gbase8a."""
        lowerer = get_chinadb_lowerer("gbase8a")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_gbase8a(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to gbase8a."""
        lowerer = get_chinadb_lowerer("gbase8a")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_highgo(self, corpus: type[SupplyChainLogisticsCorpus]) -> None:
        """Validate lowering SupplyChain DDL to highgo."""
        lowerer = get_chinadb_lowerer("highgo")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_highgo(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to highgo."""
        lowerer = get_chinadb_lowerer("highgo")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_oceanbase_oracle(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DDL to oceanbase_oracle."""
        lowerer = get_chinadb_lowerer("oceanbase_oracle")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_oceanbase_oracle(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to oceanbase_oracle."""
        lowerer = get_chinadb_lowerer("oceanbase_oracle")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_oceanbase_mysql(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DDL to oceanbase_mysql."""
        lowerer = get_chinadb_lowerer("oceanbase_mysql")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_oceanbase_mysql(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to oceanbase_mysql."""
        lowerer = get_chinadb_lowerer("oceanbase_mysql")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_gaussdb_oracle(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DDL to gaussdb_oracle."""
        lowerer = get_chinadb_lowerer("gaussdb_oracle")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_gaussdb_oracle(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to gaussdb_oracle."""
        lowerer = get_chinadb_lowerer("gaussdb_oracle")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_gaussdb_mysql(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DDL to gaussdb_mysql."""
        lowerer = get_chinadb_lowerer("gaussdb_mysql")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_gaussdb_mysql(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to gaussdb_mysql."""
        lowerer = get_chinadb_lowerer("gaussdb_mysql")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_supplychain_lowering_to_goldendb(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DDL to goldendb."""
        lowerer = get_chinadb_lowerer("goldendb")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_supplychain_dml_lowering_to_goldendb(
        self, corpus: type[SupplyChainLogisticsCorpus]
    ) -> None:
        """Validate lowering SupplyChain DML to goldendb."""
        lowerer = get_chinadb_lowerer("goldendb")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM SUPPLY_CHAIN_LOGISTICS_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()


class TestErpCorpusExhaustiveTargetMatrix:
    """Exhaustive target compatibility matrix for Erp Enterprise Corpus."""

    @pytest.fixture
    def corpus(self) -> type[ErpPayrollCorpus]:
        return ErpPayrollCorpus

    def test_erp_lowering_to_dm8(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to dm8."""
        lowerer = get_chinadb_lowerer("dm8")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_dm8(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to dm8."""
        lowerer = get_chinadb_lowerer("dm8")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_kingbase(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to kingbase."""
        lowerer = get_chinadb_lowerer("kingbase")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_kingbase(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to kingbase."""
        lowerer = get_chinadb_lowerer("kingbase")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_opengauss(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to opengauss."""
        lowerer = get_chinadb_lowerer("opengauss")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_opengauss(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to opengauss."""
        lowerer = get_chinadb_lowerer("opengauss")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_tidb(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to tidb."""
        lowerer = get_chinadb_lowerer("tidb")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_tidb(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to tidb."""
        lowerer = get_chinadb_lowerer("tidb")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_gbase8s(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to gbase8s."""
        lowerer = get_chinadb_lowerer("gbase8s")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_gbase8s(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to gbase8s."""
        lowerer = get_chinadb_lowerer("gbase8s")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_gbase8c(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to gbase8c."""
        lowerer = get_chinadb_lowerer("gbase8c")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_gbase8c(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to gbase8c."""
        lowerer = get_chinadb_lowerer("gbase8c")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_gbase8a(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to gbase8a."""
        lowerer = get_chinadb_lowerer("gbase8a")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_gbase8a(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to gbase8a."""
        lowerer = get_chinadb_lowerer("gbase8a")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_highgo(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to highgo."""
        lowerer = get_chinadb_lowerer("highgo")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_highgo(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to highgo."""
        lowerer = get_chinadb_lowerer("highgo")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_oceanbase_oracle(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to oceanbase_oracle."""
        lowerer = get_chinadb_lowerer("oceanbase_oracle")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_oceanbase_oracle(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to oceanbase_oracle."""
        lowerer = get_chinadb_lowerer("oceanbase_oracle")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_oceanbase_mysql(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to oceanbase_mysql."""
        lowerer = get_chinadb_lowerer("oceanbase_mysql")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_oceanbase_mysql(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to oceanbase_mysql."""
        lowerer = get_chinadb_lowerer("oceanbase_mysql")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_gaussdb_oracle(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to gaussdb_oracle."""
        lowerer = get_chinadb_lowerer("gaussdb_oracle")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_gaussdb_oracle(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to gaussdb_oracle."""
        lowerer = get_chinadb_lowerer("gaussdb_oracle")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_gaussdb_mysql(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to gaussdb_mysql."""
        lowerer = get_chinadb_lowerer("gaussdb_mysql")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_gaussdb_mysql(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to gaussdb_mysql."""
        lowerer = get_chinadb_lowerer("gaussdb_mysql")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()

    def test_erp_lowering_to_goldendb(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DDL to goldendb."""
        lowerer = get_chinadb_lowerer("goldendb")
        stmts = corpus.parse_statements()
        sample_stmts = [s for s in stmts if "CREATE TABLE" in s.upper()][:3]
        assert len(sample_stmts) > 0, "No table DDL statements found"
        for s in sample_stmts:
            lowered = lowerer.lower_table_ddl(s, source_dialect="oracle")
            assert lowered is not None
            assert len(lowered) > 0
            assert "CREATE TABLE" in lowered.upper()

    def test_erp_dml_lowering_to_goldendb(self, corpus: type[ErpPayrollCorpus]) -> None:
        """Validate lowering Erp DML to goldendb."""
        lowerer = get_chinadb_lowerer("goldendb")
        sample_query = (
            "SELECT ID, AMOUNT, NVL(STATUS, 0) AS STATUS_VAL "
            "FROM ERP_PAYROLL_HR_SAMPLE "
            "WHERE AMOUNT > 0 ORDER BY ID;"
        )
        lowered = lowerer.lower_statement(sample_query, source_dialect="oracle", asset_kind="DML")
        assert lowered is not None
        assert len(lowered) > 0
        assert "SELECT" in lowered.upper()
