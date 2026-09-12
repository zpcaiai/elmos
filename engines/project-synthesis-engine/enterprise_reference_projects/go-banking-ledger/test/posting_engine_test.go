package test

import (
	"context"
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/infrastructure/persistence"
	"github.com/google/uuid"
)

func setupTestPostingEngine() (*service.PostingEngine, *persistence.InMemoryAccountRepository, *persistence.InMemoryJournalRepository) {
	accRepo := persistence.NewInMemoryAccountRepository()
	jourRepo := persistence.NewInMemoryJournalRepository()
	idemRepo := persistence.NewInMemoryIdempotencyRepository()
	lockMgr := persistence.NewInMemoryLockManager()
	currReg := model.NewCurrencyRegistry()

	engine := service.NewPostingEngine(accRepo, jourRepo, idemRepo, lockMgr, currReg)
	return engine, accRepo, jourRepo
}

func TestSuccessfulTransferBetweenAccounts(t *testing.T) {
	engine, accRepo, jourRepo := setupTestPostingEngine()
	ctx := context.Background()
	tenantID := "tenant_bank_01"

	// Create source account (Alice checking) and target account (Bob savings)
	alice, _ := model.NewAccount("acc_alice", tenantID, "1001-ALICE", "Alice Checking", model.AccountTypeLiability, "USD", 0)
	_ = alice.ApplyCredit(50000, "USD", false) // $500.00 initial customer deposit credit
	_ = accRepo.Save(ctx, alice)

	bob, _ := model.NewAccount("acc_bob", tenantID, "2001-BOB", "Bob Savings", model.AccountTypeLiability, "USD", 0)
	_ = accRepo.Save(ctx, bob)

	// Execute transfer of $150.00 (15000 cents)
	req := model.PostingRequest{
		RequestID:      uuid.New().String(),
		TenantID:       tenantID,
		IdempotencyKey: "idem_tx_001",
		Type:           model.TxTypeTransfer,
		ReferenceID:    "REF_TX_001",
		SourceAccount:  "acc_alice",
		TargetAccount:  "acc_bob",
		Amount:         15000,
		Currency:       "USD",
		Description:    "P2P payment for dinner",
		ValueDate:      time.Now().UTC(),
	}

	entry, err := engine.ProcessTransfer(ctx, req)
	if err != nil {
		t.Fatalf("transfer failed: %v", err)
	}

	if entry.Status != model.JournalStatusPosted {
		t.Errorf("expected POSTED status, got %s", entry.Status)
	}
	if entry.TotalDebit != 15000 || entry.TotalCredit != 15000 {
		t.Errorf("expected debit 15000 and credit 15000, got D:%d C:%d", entry.TotalDebit, entry.TotalCredit)
	}

	// Verify Alice balance: 50000 - 15000 = 35000
	aliceUpdated, _ := accRepo.FindByID(ctx, tenantID, "acc_alice")
	if aliceUpdated.PostedBalance != 35000 {
		t.Errorf("expected Alice balance 35000, got %d", aliceUpdated.PostedBalance)
	}

	// Verify Bob balance: 0 + 15000 = 15000
	bobUpdated, _ := accRepo.FindByID(ctx, tenantID, "acc_bob")
	if bobUpdated.PostedBalance != 15000 {
		t.Errorf("expected Bob balance 15000, got %d", bobUpdated.PostedBalance)
	}

	// Verify Journal Entry persisted
	persistedEntry, err := jourRepo.FindEntryByID(ctx, tenantID, entry.EntryID)
	if err != nil || persistedEntry == nil {
		t.Fatalf("failed retrieving persisted journal entry: %v", err)
	}
	if persistedEntry.MerkleRoot == "" {
		t.Errorf("expected valid non-empty MerkleRoot on journal entry")
	}
}

func TestTransferInsufficientFundsRejection(t *testing.T) {
	engine, accRepo, _ := setupTestPostingEngine()
	ctx := context.Background()
	tenantID := "tenant_bank_01"

	alice, _ := model.NewAccount("acc_alice_poor", tenantID, "1002-POOR", "Poor Alice", model.AccountTypeLiability, "USD", 0)
	_ = alice.ApplyCredit(1000, "USD", false) // $10.00
	_ = accRepo.Save(ctx, alice)

	bob, _ := model.NewAccount("acc_bob_rich", tenantID, "1003-RICH", "Rich Bob", model.AccountTypeLiability, "USD", 0)
	_ = accRepo.Save(ctx, bob)

	// Attempt to transfer $50.00 (5000 cents)
	req := model.PostingRequest{
		RequestID:      uuid.New().String(),
		TenantID:       tenantID,
		IdempotencyKey: "idem_tx_insufficient",
		Type:           model.TxTypeTransfer,
		ReferenceID:    "REF_TX_FAIL",
		SourceAccount:  "acc_alice_poor",
		TargetAccount:  "acc_bob_rich",
		Amount:         5000,
		Currency:       "USD",
		Description:    "Should fail due to insufficient funds",
		ValueDate:      time.Now().UTC(),
	}

	_, err := engine.ProcessTransfer(ctx, req)
	if err == nil {
		t.Fatalf("expected insufficient funds error, but transfer succeeded")
	}

	// Alice balance must remain intact
	aliceRefetched, _ := accRepo.FindByID(ctx, tenantID, "acc_alice_poor")
	if aliceRefetched.PostedBalance != 1000 {
		t.Errorf("expected balance to remain 1000, got %d", aliceRefetched.PostedBalance)
	}
}

func TestIdempotentDuplicateTransfer(t *testing.T) {
	engine, accRepo, _ := setupTestPostingEngine()
	ctx := context.Background()
	tenantID := "tenant_bank_01"

	alice, _ := model.NewAccount("acc_idem_alice", tenantID, "1004-IDEM", "Alice Idem", model.AccountTypeLiability, "USD", 0)
	_ = alice.ApplyCredit(20000, "USD", false)
	_ = accRepo.Save(ctx, alice)

	bob, _ := model.NewAccount("acc_idem_bob", tenantID, "1005-IDEM", "Bob Idem", model.AccountTypeLiability, "USD", 0)
	_ = accRepo.Save(ctx, bob)

	req := model.PostingRequest{
		RequestID:      uuid.New().String(),
		TenantID:       tenantID,
		IdempotencyKey: "idem_exact_same_key_123",
		Type:           model.TxTypeTransfer,
		ReferenceID:    "REF_TX_IDEM",
		SourceAccount:  "acc_idem_alice",
		TargetAccount:  "acc_idem_bob",
		Amount:         5000,
		Currency:       "USD",
		Description:    "First attempt",
		ValueDate:      time.Now().UTC(),
	}

	firstEntry, err := engine.ProcessTransfer(ctx, req)
	if err != nil {
		t.Fatalf("first transfer failed: %v", err)
	}

	// Resubmit identical request with same idempotency key
	secondEntry, err := engine.ProcessTransfer(ctx, req)
	if err != nil {
		t.Fatalf("second transfer should succeed idempotently, but got: %v", err)
	}

	if firstEntry.EntryID != secondEntry.EntryID {
		t.Errorf("expected returned entry IDs to match: %s vs %s", firstEntry.EntryID, secondEntry.EntryID)
	}

	// Alice should only have been debited ONCE ($50.00, remaining 15000)
	aliceFinal, _ := accRepo.FindByID(ctx, tenantID, "acc_idem_alice")
	if aliceFinal.PostedBalance != 15000 {
		t.Errorf("expected single deduction 15000, got %d", aliceFinal.PostedBalance)
	}
}
