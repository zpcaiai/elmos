package service

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
	"github.com/google/uuid"
)

// SettlementService executes interbank clearing batches and multilateral settlement runs.
type SettlementService struct {
	mu           sync.Mutex
	accountRepo  repository.AccountRepository
	journalRepo  repository.JournalRepository
	batches      map[string]*model.ClearingBatch
}

func NewSettlementService(
	accRepo repository.AccountRepository,
	jourRepo repository.JournalRepository,
) *SettlementService {
	return &SettlementService{
		accountRepo: accRepo,
		journalRepo: jourRepo,
		batches:     make(map[string]*model.ClearingBatch),
	}
}

// OpenNewBatch creates an active settlement container for aggregating transactions.
func (s *SettlementService) OpenNewBatch(tenantID, currency string) (*model.ClearingBatch, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	batchID := fmt.Sprintf("batch_%s", uuid.New().String())
	now := time.Now().UTC()
	b := &model.ClearingBatch{
		BatchID:          batchID,
		TenantID:         tenantID,
		BatchNumber:      fmt.Sprintf("CLR-%s-%d", currency, now.Unix()),
		Status:           "OPEN",
		Currency:         currency,
		OpenedAt:         now,
		Transactions:     make([]string, 0),
		TotalGrossAmount: 0,
	}

	s.batches[batchID] = b
	return b, nil
}

// AddTransactionToBatch registers a journal entry into the active batch.
func (s *SettlementService) AddTransactionToBatch(batchID, entryID string, grossAmount int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	b, exists := s.batches[batchID]
	if !exists {
		return fmt.Errorf("clearing batch %s not found", batchID)
	}
	if b.Status != "OPEN" {
		return fmt.Errorf("cannot add transaction to batch with status %s", b.Status)
	}

	b.Transactions = append(b.Transactions, entryID)
	b.TransactionCount++
	b.TotalGrossAmount += grossAmount
	return nil
}

// ExecuteSettlement closes the batch, applies settlement transfers, and marks it settled.
func (s *SettlementService) ExecuteSettlement(
	ctx context.Context,
	batchID string,
	centralClearingAccount string,
	participantReserveAccounts map[string]string,
) (*model.JournalEntryAggregate, error) {
	s.mu.Lock()
	b, exists := s.batches[batchID]
	if !exists {
		s.mu.Unlock()
		return nil, fmt.Errorf("clearing batch %s not found", batchID)
	}
	if b.Status != "OPEN" {
		s.mu.Unlock()
		return nil, fmt.Errorf("batch %s is not OPEN", batchID)
	}
	b.Status = "PROCESSING"
	s.mu.Unlock()

	now := time.Now().UTC()
	b.ClosedAt = now

	// Construct Net Settlement Journal Entry
	entryID := fmt.Sprintf("stl_%s", uuid.New().String())
	var lines []model.EntryLine

	// Credit central clearing account
	lines = append(lines, model.EntryLine{
		LineID:      fmt.Sprintf("%s-cr", entryID),
		AccountID:   centralClearingAccount,
		Direction:   model.DirectionCredit,
		Amount:      b.TotalGrossAmount,
		Currency:    b.Currency,
		Description: fmt.Sprintf("Central clearing pool for batch %s", b.BatchNumber),
	})

	// Debit participant reserve account
	for _, accID := range participantReserveAccounts {
		lines = append(lines, model.EntryLine{
			LineID:      fmt.Sprintf("%s-db-%s", entryID, accID),
			AccountID:   accID,
			Direction:   model.DirectionDebit,
			Amount:      b.TotalGrossAmount,
			Currency:    b.Currency,
			Description: fmt.Sprintf("Settlement reserve drawdown for batch %s", b.BatchNumber),
		})
		break // Single participant settlement in simplified model
	}

	prevHash := "0000000000000000000000000000000000000000000000000000000000000000"
	latest, _ := s.journalRepo.FindLatestEntry(ctx, b.TenantID)
	if latest != nil {
		prevHash = latest.MerkleRoot
	}

	entry, err := model.NewJournalEntry(
		entryID,
		b.TenantID,
		fmt.Sprintf("stl-batch-%s", b.BatchID),
		b.BatchNumber,
		fmt.Sprintf("Settlement voucher for batch %s (%d txs)", b.BatchNumber, b.TransactionCount),
		b.Currency,
		now,
		lines,
		prevHash,
	)
	if err != nil {
		return nil, err
	}

	if err := entry.Post(); err != nil {
		return nil, err
	}

	if err := s.journalRepo.SaveEntry(ctx, entry); err != nil {
		return nil, err
	}

	s.mu.Lock()
	b.Status = "SETTLED"
	b.SettledAt = time.Now().UTC()
	s.mu.Unlock()

	return entry, nil
}
