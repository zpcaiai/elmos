package test

import (
	"context"
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/infrastructure/persistence"
)

func TestStandingOrderRecurringExecution(t *testing.T) {
	acctRepo := persistence.NewInMemoryAccountRepository()
	journalRepo := persistence.NewInMemoryJournalEntryRepository()
	lockMgr := persistence.NewInMemoryLockManager()
	postingEng := service.NewPostingEngine(acctRepo, journalRepo, lockMgr)

	debtor, _ := model.NewAccount("ACCT-A", "Employer Corp", model.AccountTypeChecking, model.USD, model.AccountNormalBalanceCredit)
	debtor.AvailableBalance, _ = model.NewMoney(1000000, model.USD) // $10,000.00
	creditor, _ := model.NewAccount("ACCT-B", "Employee Alice", model.AccountTypeChecking, model.USD, model.AccountNormalBalanceCredit)

	acctRepo.Save(context.Background(), debtor)
	acctRepo.Save(context.Background(), creditor)

	standingSvc := service.NewStandingOrderService(acctRepo, postingEng)

	monthlyAmount, _ := model.NewMoney(250000, model.USD) // $2,500.00
	startDate := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)

	order, err := standingSvc.CreateStandingOrder(
		"ACCT-A",
		"ACCT-B",
		monthlyAmount,
		service.FreqMonthly,
		service.ConvFollowing,
		startDate,
		nil,
		"Monthly salary payment",
	)
	if err != nil {
		t.Fatalf("Failed to create standing order: %v", err)
	}

	// Trigger due orders as of June 1
	entries, errs := standingSvc.ExecuteDueOrders(context.Background(), startDate)
	if len(errs) > 0 {
		t.Fatalf("Standing order execution error: %v", errs[0])
	}
	if len(entries) != 1 {
		t.Fatalf("Expected 1 executed entry, got %d", len(entries))
	}

	// Verify debtor was debited $2,500 ($10,000 - $2,500 = $7,500)
	updatedDebtor, _ := acctRepo.FindByID(context.Background(), "ACCT-A")
	if updatedDebtor.AvailableBalance.AmountMinor() != 750000 {
		t.Fatalf("Expected debtor balance 750000, got %d", updatedDebtor.AvailableBalance.AmountMinor())
	}

	// Next execution date moved to July 1
	if order.NextExecutionDate.Month() != time.July {
		t.Fatalf("Expected next execution date in July, got %v", order.NextExecutionDate)
	}
}

func TestFeeEngineCalculationAndWaivers(t *testing.T) {
	cfg := service.FeeScheduleConfig{
		FeeIncomeAccountID:   "GL-FEE-INCOME",
		DomesticWireFeeCents: 2500, // $25.00
		IntlWireFeeCents:     4500, // $45.00
		OverdraftFeeCents:    3500, // $35.00
		OverdraftBufferCents: 1000, // $10.00 cushion
	}

	acctRepo := persistence.NewInMemoryAccountRepository()
	journalRepo := persistence.NewInMemoryJournalEntryRepository()
	lockMgr := persistence.NewInMemoryLockManager()
	postingEng := service.NewPostingEngine(acctRepo, journalRepo, lockMgr)
	feeSvc := service.NewFeeEngineService(cfg, postingEng)

	wireAmount, _ := model.NewMoney(10000000, model.USD)

	// Retail client pays full fee
	retailFee := feeSvc.CalculateWireFee(wireAmount, false, service.TierRetail)
	if retailFee.NetFeeCents != 2500 {
		t.Fatalf("Expected retail fee 2500, got %d", retailFee.NetFeeCents)
	}

	// Private Banking client gets full fee waiver
	privateFee := feeSvc.CalculateWireFee(wireAmount, true, service.TierPrivate)
	if privateFee.NetFeeCents != 0 || privateFee.WaivedCents != 4500 {
		t.Fatalf("Expected private client 100%% waiver, got net: %d, waived: %d", privateFee.NetFeeCents, privateFee.WaivedCents)
	}

	// Overdraft within $10 cushion gets waived
	minorOverdraft, _ := model.NewMoney(-500, model.USD) // -$5.00
	odRes := feeSvc.AssessOverdraftFee(minorOverdraft, 0)
	if odRes.NetFeeCents != 0 {
		t.Fatalf("Expected overdraft within buffer to be waived, got %d", odRes.NetFeeCents)
	}
}
