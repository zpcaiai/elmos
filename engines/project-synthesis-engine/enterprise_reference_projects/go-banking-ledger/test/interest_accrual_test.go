package test

import (
	"context"
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/infrastructure/persistence"
)

func TestInterestAccrualTieredCalculation(t *testing.T) {
	calc := service.NewDayCountCalculator()
	start := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	end := time.Date(2026, 1, 31, 0, 0, 0, 0, time.UTC) // 30 days under 30/360, 30 days fraction = 30/360 = 1/12

	frac := calc.YearFraction(start, end, service.DayCount30360US)
	if frac != 30.0/360.0 {
		t.Fatalf("Expected 30/360 fraction = 0.08333, got %f", frac)
	}

	acctRepo := persistence.NewInMemoryAccountRepository()
	journalRepo := persistence.NewInMemoryJournalEntryRepository()
	lockMgr := persistence.NewInMemoryLockManager()
	postingEng := service.NewPostingEngine(acctRepo, journalRepo, lockMgr)
	accrualSvc := service.NewInterestAccrualService(acctRepo, journalRepo, postingEng)

	// $100,000.00 deposit
	custAcct, _ := model.NewAccount(
		"CUST-01",
		"ACME Corp",
		model.AccountTypeChecking,
		model.USD,
		model.AccountNormalBalanceCredit,
	)
	custAcct.AvailableBalance, _ = model.NewMoney(10000000, model.USD) // $100,000.00
	acctRepo.Save(context.Background(), custAcct)

	cfg := &service.InterestProductConfig{
		ProductID: "HIGH_YIELD_SAVINGS",
		DayCount:  service.DayCountActual360,
		Frequency: service.CompoundingMonthly,
		Tiers: []service.InterestTier{
			{MinBalanceCents: 0, MaxBalanceCents: 2500000, AnnualRatePct: 3.00},        // First $25k @ 3%
			{MinBalanceCents: 2500000, MaxBalanceCents: 10000000, AnnualRatePct: 4.50}, // Next $75k @ 4.5%
		},
		OverdraftRatePct:    18.00,
		InterestExpenseAcct: "GL-INTEREST-EXPENSE",
	}

	res, err := accrualSvc.CalculateAccrual(custAcct, cfg, start, end)
	if err != nil {
		t.Fatalf("Accrual calculation failed: %v", err)
	}

	if res.AccruedInterestCents <= 0 {
		t.Fatalf("Expected positive accrued interest, got %d", res.AccruedInterestCents)
	}

	// First tranche: $25,000 * 3% * (30/360) = $62.50 = 6250 cents
	// Second tranche: $75,000 * 4.5% * (30/360) = $281.25 = 28125 cents
	// Total = $343.75 = 34375 cents
	expected := int64(34375)
	if res.AccruedInterestCents != expected {
		t.Fatalf("Expected %d cents accrued interest, got %d", expected, res.AccruedInterestCents)
	}
}

func TestOverdraftInterestCharge(t *testing.T) {
	acctRepo := persistence.NewInMemoryAccountRepository()
	journalRepo := persistence.NewInMemoryJournalEntryRepository()
	lockMgr := persistence.NewInMemoryLockManager()
	postingEng := service.NewPostingEngine(acctRepo, journalRepo, lockMgr)
	accrualSvc := service.NewInterestAccrualService(acctRepo, journalRepo, postingEng)

	// Account is overdrawn by $5,000.00
	custAcct, _ := model.NewAccount(
		"CUST-OVERDRAWN",
		"Struggling LLC",
		model.AccountTypeChecking,
		model.USD,
		model.AccountNormalBalanceCredit,
	)
	custAcct.AvailableBalance, _ = model.NewMoney(-500000, model.USD) // -$5,000.00
	acctRepo.Save(context.Background(), custAcct)

	cfg := &service.InterestProductConfig{
		ProductID:        "STANDARD_CHECKING",
		DayCount:         service.DayCountActual360,
		Frequency:        service.CompoundingMonthly,
		OverdraftRatePct: 24.00, // 24% annual APR overdraft charge
		Tiers:            []service.InterestTier{},
	}

	start := time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC)
	end := time.Date(2026, 3, 31, 0, 0, 0, 0, time.UTC) // 30 days

	res, err := accrualSvc.CalculateAccrual(custAcct, cfg, start, end)
	if err != nil {
		t.Fatalf("Accrual calculation failed: %v", err)
	}

	if !res.IsOverdraftCharge {
		t.Fatalf("Expected overdraft charge flag to be true")
	}

	// $5,000 * 24% * (30/360) = $100.00 = 10000 cents
	expected := int64(10000)
	if res.AccruedInterestCents != expected {
		t.Fatalf("Expected overdraft charge %d cents, got %d", expected, res.AccruedInterestCents)
	}
}
