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
	accRepo := persistence.NewInMemoryAccountRepository()
	jourRepo := persistence.NewInMemoryJournalRepository()
	idemRepo := persistence.NewInMemoryIdempotencyRepository()
	lockMgr := persistence.NewInMemoryLockManager()
	currReg := model.NewCurrencyRegistry()
	postingEng := service.NewPostingEngine(accRepo, jourRepo, idemRepo, lockMgr, currReg)

	tenantID := "tenant-1"
	debtor, _ := model.NewAccount("ACCT-A", tenantID, "1001", "Employer Corp", model.AccountTypeLiability, "USD", 0)
	_ = debtor.ApplyCredit(1000000, "USD", false) // $10,000.00
	creditor, _ := model.NewAccount("ACCT-B", tenantID, "1002", "Employee Alice", model.AccountTypeLiability, "USD", 0)

	accRepo.Save(context.Background(), debtor)
	accRepo.Save(context.Background(), creditor)

	standingSvc := service.NewStandingOrderService(accRepo, postingEng)

	monthlyAmountCents := int64(250000) // $2,500.00
	startDate := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)

	order, err := standingSvc.CreateStandingOrder(
		tenantID,
		"ACCT-A",
		"ACCT-B",
		monthlyAmountCents,
		"USD",
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

	// Verify debtor balance was reduced
	updatedDebtor, _ := accRepo.FindByID(context.Background(), tenantID, "ACCT-A")
	if updatedDebtor.AvailableBalance() != 750000 {
		t.Fatalf("Expected debtor balance 750000, got %d", updatedDebtor.AvailableBalance())
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

	accRepo := persistence.NewInMemoryAccountRepository()
	jourRepo := persistence.NewInMemoryJournalRepository()
	idemRepo := persistence.NewInMemoryIdempotencyRepository()
	lockMgr := persistence.NewInMemoryLockManager()
	currReg := model.NewCurrencyRegistry()
	postingEng := service.NewPostingEngine(accRepo, jourRepo, idemRepo, lockMgr, currReg)
	feeSvc := service.NewFeeEngineService(cfg, postingEng)

	wireAmountCents := int64(10000000)

	// Retail client pays full fee
	retailFee := feeSvc.CalculateWireFee(wireAmountCents, "USD", false, service.TierRetail)
	if retailFee.NetFeeCents != 2500 {
		t.Fatalf("Expected retail fee 2500, got %d", retailFee.NetFeeCents)
	}

	// Private Banking client gets full fee waiver
	privateFee := feeSvc.CalculateWireFee(wireAmountCents, "USD", true, service.TierPrivate)
	if privateFee.NetFeeCents != 0 || privateFee.WaivedCents != 4500 {
		t.Fatalf("Expected private client 100%% waiver, got net: %d, waived: %d", privateFee.NetFeeCents, privateFee.WaivedCents)
	}

	// Overdraft within $10 cushion gets waived
	minorOverdraftCents := int64(-500) // -$5.00
	odRes := feeSvc.AssessOverdraftFee(minorOverdraftCents, "USD", 0)
	if odRes.NetFeeCents != 0 {
		t.Fatalf("Expected overdraft within buffer to be waived, got %d", odRes.NetFeeCents)
	}
}
