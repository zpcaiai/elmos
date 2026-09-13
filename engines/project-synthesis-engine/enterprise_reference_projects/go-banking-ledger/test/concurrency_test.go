package test

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/google/uuid"
)

func TestConcurrentTransfersMoneyConservation(t *testing.T) {
	engine, accRepo, _ := setupTestPostingEngine()
	ctx := context.Background()
	tenantID := "tenant_concurrency_01"

	// Create 4 test accounts with $10,000 each (1,000,000 cents)
	numAccounts := 4
	initialBalance := int64(1000000)
	var accountIDs []string

	for i := 1; i <= numAccounts; i++ {
		id := fmt.Sprintf("acc_conc_%d", i)
		acc, _ := model.NewAccount(id, tenantID, fmt.Sprintf("100%d", i), fmt.Sprintf("Account %d", i), model.AccountTypeLiability, "USD", 0)
		_ = acc.ApplyCredit(initialBalance, "USD", false)
		_ = accRepo.Save(ctx, acc)
		accountIDs = append(accountIDs, id)
	}

	totalInitialMoney := initialBalance * int64(numAccounts)

	// Launch 50 concurrent transfer requests across cross-pairs
	concurrency := 50
	var wg sync.WaitGroup
	var successfulTransfers int64
	var failedTransfers int64

	for i := 0; i < concurrency; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()

			srcIdx := idx % numAccounts
			tgtIdx := (idx + 1) % numAccounts
			srcID := accountIDs[srcIdx]
			tgtID := accountIDs[tgtIdx]

			req := model.PostingRequest{
				RequestID:      uuid.New().String(),
				TenantID:       tenantID,
				IdempotencyKey: fmt.Sprintf("conc_idem_%d", idx),
				Type:           model.TxTypeTransfer,
				ReferenceID:    fmt.Sprintf("CONC_REF_%d", idx),
				SourceAccount:  srcID,
				TargetAccount:  tgtID,
				Amount:         5000, // $50.00
				Currency:       "USD",
				Description:    fmt.Sprintf("Concurrent transfer run %d", idx),
				ValueDate:      time.Now().UTC(),
			}

			_, err := engine.ProcessTransfer(ctx, req)
			if err != nil {
				atomic.AddInt64(&failedTransfers, 1)
			} else {
				atomic.AddInt64(&successfulTransfers, 1)
			}
		}(i)
	}

	wg.Wait()

	t.Logf("Completed concurrent transfers: %d success, %d failed", successfulTransfers, failedTransfers)

	// Fundamental Invariant: Total Money Conservation
	var totalFinalMoney int64
	for _, id := range accountIDs {
		acc, err := accRepo.FindByID(ctx, tenantID, id)
		if err != nil {
			t.Fatalf("failed fetching account %s: %v", id, err)
		}
		totalFinalMoney += acc.PostedBalance
	}

	if totalFinalMoney != totalInitialMoney {
		t.Fatalf("MONEY CREATED OR DESTROYED! Initial=%d, Final=%d, Discrepancy=%d",
			totalInitialMoney, totalFinalMoney, totalFinalMoney-totalInitialMoney)
	}

	t.Logf("Money Conservation Proof Passed: Initial %d == Final %d", totalInitialMoney, totalFinalMoney)
}
