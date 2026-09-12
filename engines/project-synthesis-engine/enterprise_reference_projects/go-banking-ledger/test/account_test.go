package test

import (
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
)

func TestAccountCreationAndValidation(t *testing.T) {
	acc, err := model.NewAccount("acc_001", "tenant_a", "1001-ASSET", "Cash Vault", model.AccountTypeAsset, "USD", 0)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if acc.Status != model.AccountStatusActive {
		t.Errorf("expected active status, got %s", acc.Status)
	}
	if acc.AvailableBalance() != 0 {
		t.Errorf("expected 0 available balance, got %d", acc.AvailableBalance())
	}
	if acc.Type.NormalBalance() != model.DirectionDebit {
		t.Errorf("expected normal debit balance for Asset, got %s", acc.Type.NormalBalance())
	}
}

func TestAccountBalanceAndHolds(t *testing.T) {
	acc, _ := model.NewAccount("acc_002", "tenant_a", "1002-ASSET", "Operating Checking", model.AccountTypeAsset, "USD", 5000)

	// Credit 10,000 cents ($100.00)
	err := acc.ApplyDebit(10000, "USD", false) // Asset increases with Debit
	if err != nil {
		t.Fatalf("failed applying debit: %v", err)
	}

	// Available = 10000 + overdraft(5000) = 15000
	if acc.AvailableBalance() != 15000 {
		t.Errorf("expected 15000 available balance, got %d", acc.AvailableBalance())
	}

	// Place hold of 3000
	hold, err := acc.PlaceHold("h_1", "ref_h1", "Card pre-auth", 3000, "USD", 1*time.Hour)
	if err != nil {
		t.Fatalf("failed placing hold: %v", err)
	}
	if hold.Amount != 3000 {
		t.Errorf("expected hold amount 3000, got %d", hold.Amount)
	}

	// Available should now be 15000 - 3000 = 12000
	if acc.AvailableBalance() != 12000 {
		t.Errorf("expected 12000 available after hold, got %d", acc.AvailableBalance())
	}

	// Release hold
	released, err := acc.ReleaseHold("h_1")
	if err != nil {
		t.Fatalf("failed releasing hold: %v", err)
	}
	if !released.IsReleased {
		t.Errorf("expected hold to be marked released")
	}

	if acc.AvailableBalance() != 15000 {
		t.Errorf("expected 15000 available after hold release, got %d", acc.AvailableBalance())
	}
}

func TestAccountFreezeEnforcement(t *testing.T) {
	acc, _ := model.NewAccount("acc_003", "tenant_a", "1003-ASSET", "Suspicious Account", model.AccountTypeAsset, "USD", 0)
	_ = acc.ApplyDebit(5000, "USD", false)

	err := acc.Freeze("AML Investigation")
	if err != nil {
		t.Fatalf("failed freezing account: %v", err)
	}

	// Debit attempt should fail
	err = acc.ApplyDebit(1000, "USD", false)
	if err != model.ErrAccountFrozen {
		t.Errorf("expected ErrAccountFrozen, got %v", err)
	}

	// Unfreeze
	err = acc.Unfreeze()
	if err != nil {
		t.Fatalf("failed unfreezing account: %v", err)
	}

	err = acc.ApplyDebit(1000, "USD", false)
	if err != nil {
		t.Errorf("expected debit to succeed after unfreezing, got %v", err)
	}
}
