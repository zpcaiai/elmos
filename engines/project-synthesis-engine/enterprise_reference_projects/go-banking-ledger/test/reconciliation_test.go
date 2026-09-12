package test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
	"github.com/google/uuid"
)

func TestTrialBalanceConservationLaw(t *testing.T) {
	engine, accRepo, jourRepo := setupTestPostingEngine()
	recSvc := service.NewReconciliationService(accRepo, jourRepo)
	ctx := context.Background()
	tenantID := "tenant_tb_audit"

	// 1. Setup Chart of Accounts:
	// Cash Asset Account
	cash, _ := model.NewAccount("acc_cash", tenantID, "1000-CASH", "Cash Vault", model.AccountTypeAsset, "USD", 0)
	// Equity / Paid-in Capital Account
	capital, _ := model.NewAccount("acc_capital", tenantID, "3000-EQUITY", "Shareholder Capital", model.AccountTypeEquity, "USD", 0)
	// Customer Deposit Liability Account
	custDeposit, _ := model.NewAccount("acc_cust_dep", tenantID, "2000-LIAB", "Customer Deposit", model.AccountTypeLiability, "USD", 0)
	// Fee Revenue Account
	feeRevenue, _ := model.NewAccount("acc_fee_rev", tenantID, "4000-REV", "Fee Income", model.AccountTypeRevenue, "USD", 0)

	_ = accRepo.Save(ctx, cash)
	_ = accRepo.Save(ctx, capital)
	_ = accRepo.Save(ctx, custDeposit)
	_ = accRepo.Save(ctx, feeRevenue)

	// Transaction 1: Initial capital infusion of $10,000 (1,000,000 cents)
	// Debit Cash, Credit Capital
	tx1 := model.PostingRequest{
		RequestID:      uuid.New().String(),
		TenantID:       tenantID,
		IdempotencyKey: "idem_tb_01",
		Type:           model.TxTypeTransfer,
		ReferenceID:    "CAPITAL_INFUSION",
		SourceAccount:  "acc_cash",
		TargetAccount:  "acc_capital",
		Amount:         1000000,
		Currency:       "USD",
		Description:    "Initial capital",
		ValueDate:      time.Now().UTC(),
	}
	_, err := engine.ProcessTransfer(ctx, tx1)
	if err != nil {
		t.Fatalf("tx1 failed: %v", err)
	}

	// Transaction 2: Transfer to customer deposit $2,000 with $10 fee
	tx2 := model.PostingRequest{
		RequestID:      uuid.New().String(),
		TenantID:       tenantID,
		IdempotencyKey: "idem_tb_02",
		Type:           model.TxTypeTransfer,
		ReferenceID:    "CUSTOMER_DEPOSIT",
		SourceAccount:  "acc_cash",
		TargetAccount:  "acc_cust_dep",
		Amount:         200000,
		Currency:       "USD",
		FeeAmount:      1000,
		FeeAccount:     "acc_fee_rev",
		Description:    "Fund customer deposit with fee",
		ValueDate:      time.Now().UTC(),
	}
	_, err = engine.ProcessTransfer(ctx, tx2)
	if err != nil {
		t.Fatalf("tx2 failed: %v", err)
	}

	// Run Trial Balance
	tbReport, err := recSvc.GenerateTrialBalance(ctx, tenantID, time.Now().UTC())
	if err != nil {
		t.Fatalf("trial balance generation failed: %v", err)
	}

	if !tbReport.IsBalanced {
		t.Errorf("expected trial balance to be balanced! Variance = %d (Debits=%d, Credits=%d)",
			tbReport.Variance, tbReport.TotalDebit, tbReport.TotalCredit)
	}

	if tbReport.TotalDebit != tbReport.TotalCredit {
		t.Errorf("fundamental ledger accounting invariant violated: TotalDebit != TotalCredit")
	}

	t.Logf("Trial Balance OK: Total Debits = %d, Total Credits = %d, Net Variance = %d",
		tbReport.TotalDebit, tbReport.TotalCredit, tbReport.Variance)
}

func TestMerkleTreeAuditProofIntegrity(t *testing.T) {
	// Verify zero length error
	if _, err := model.BuildMerkleTree([]string{}); err == nil {
		t.Errorf("expected error for empty leaves")
	}

	// Generate 16 sample SHA-256 hashes representing transactions in a block
	var hashes []string
	for i := 0; i < 16; i++ {
		hashVal := fmt.Sprintf("%064x", i*1000+42)
		hashes = append(hashes, hashVal)
	}

	tree, err := model.BuildMerkleTree(hashes)
	if err != nil {
		t.Fatalf("failed building merkle tree: %v", err)
	}

	rootHex := tree.RootHex()
	if len(rootHex) != 64 {
		t.Errorf("expected 64-character hex root, got %s", rootHex)
	}

	// Verify inclusion proof for leaf 7
	proof, err := tree.GenerateProof(7)
	if err != nil {
		t.Fatalf("failed generating proof: %v", err)
	}

	if !model.VerifyProof(proof) {
		t.Errorf("merkle proof verification failed for legitimate leaf 7")
	}

	// Simulate Tamper: change target hash
	tamperedProof := *proof
	tamperedProof.TargetHash = fmt.Sprintf("%064x", 999999)
	if model.VerifyProof(&tamperedProof) {
		t.Errorf("merkle verification should fail on tampered target hash!")
	}
}
