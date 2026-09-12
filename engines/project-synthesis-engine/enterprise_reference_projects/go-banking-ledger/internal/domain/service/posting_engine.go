package service

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sort"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
	"github.com/google/uuid"
)

var (
	ErrDuplicateRequest = errors.New("request already processed, idempotency violation")
	ErrDeadlockRisk     = errors.New("aborted to avoid deadlock")
)

// PostingEngine coordinates multi-account double-entry transaction posting.
type PostingEngine struct {
	accountRepo    repository.AccountRepository
	journalRepo    repository.JournalRepository
	idempotencyRepo repository.IdempotencyRepository
	lockManager    repository.DistributedLockManager
	currencyReg    *model.CurrencyRegistry
}

// NewPostingEngine constructs an industrial posting engine with injected repositories.
func NewPostingEngine(
	accRepo repository.AccountRepository,
	jourRepo repository.JournalRepository,
	idemRepo repository.IdempotencyRepository,
	lockMgr repository.DistributedLockManager,
	currReg *model.CurrencyRegistry,
) *PostingEngine {
	return &PostingEngine{
		accountRepo:     accRepo,
		journalRepo:     jourRepo,
		idempotencyRepo: idemRepo,
		lockManager:     lockMgr,
		currencyReg:     currReg,
	}
}

// ProcessTransfer executes an atomic debit and credit transfer between two distinct accounts.
func (pe *PostingEngine) ProcessTransfer(ctx context.Context, req model.PostingRequest) (*model.JournalEntryAggregate, error) {
	if err := req.Validate(); err != nil {
		return nil, fmt.Errorf("invalid transfer request: %w", err)
	}

	// 1. Idempotency Check
	if pe.idempotencyRepo != nil {
		existing, err := pe.idempotencyRepo.Get(ctx, req.TenantID, req.IdempotencyKey)
		if err == nil && existing != nil && !existing.IsExpired() {
			if existing.EntryID != "" {
				return pe.journalRepo.FindEntryByID(ctx, req.TenantID, existing.EntryID)
			}
			return nil, ErrDuplicateRequest
		}
	}

	// 2. Deadlock-free Lock Acquisition: Sort account IDs lexicographically
	accountIDs := []string{req.SourceAccount, req.TargetAccount}
	if req.FeeAmount > 0 && req.FeeAccount != "" {
		accountIDs = append(accountIDs, req.FeeAccount)
	}
	sort.Strings(accountIDs)

	var locks []repository.LockHandle
	defer func() {
		for _, l := range locks {
			_ = pe.lockManager.ReleaseLock(ctx, l)
		}
	}()

	for _, accID := range accountIDs {
		lockKey := fmt.Sprintf("ledger:lock:%s:%s", req.TenantID, accID)
		handle, err := pe.lockManager.AcquireLock(ctx, lockKey, 10*time.Second)
		if err != nil {
			return nil, fmt.Errorf("failed locking account %s: %w", accID, err)
		}
		locks = append(locks, handle)
	}

	// 3. Fetch source and target account aggregates
	sourceAcc, err := pe.accountRepo.FindByID(ctx, req.TenantID, req.SourceAccount)
	if err != nil {
		return nil, fmt.Errorf("source account %s not found: %w", req.SourceAccount, err)
	}
	targetAcc, err := pe.accountRepo.FindByID(ctx, req.TenantID, req.TargetAccount)
	if err != nil {
		return nil, fmt.Errorf("target account %s not found: %w", req.TargetAccount, err)
	}

	var feeAcc *model.AccountAggregate
	if req.FeeAmount > 0 && req.FeeAccount != "" {
		feeAcc, err = pe.accountRepo.FindByID(ctx, req.TenantID, req.FeeAccount)
		if err != nil {
			return nil, fmt.Errorf("fee account %s not found: %w", req.FeeAccount, err)
		}
	}

	// 4. Validate Funds Constraint
	totalDeduction := req.Amount + req.FeeAmount
	if err := sourceAcc.CheckDebitAllowed(totalDeduction, req.Currency); err != nil {
		return nil, fmt.Errorf("source account balance constraint failed: %w", err)
	}
	if err := targetAcc.CheckCreditAllowed(req.Amount, req.Currency); err != nil {
		return nil, fmt.Errorf("target account credit check failed: %w", err)
	}
	if feeAcc != nil && req.FeeAmount > 0 {
		if err := feeAcc.CheckCreditAllowed(req.FeeAmount, req.Currency); err != nil {
			return nil, fmt.Errorf("fee account credit check failed: %w", err)
		}
	}

	// 5. Construct Journal Entry Lines
	entryID := fmt.Sprintf("je_%s", uuid.New().String())
	var lines []model.EntryLine

	// Debit source account
	lines = append(lines, model.EntryLine{
		LineID:      fmt.Sprintf("%s-1", entryID),
		AccountID:   sourceAcc.AccountID,
		Direction:   model.DirectionDebit,
		Amount:      req.Amount,
		Currency:    req.Currency,
		Description: fmt.Sprintf("Transfer to %s: %s", targetAcc.AccountNumber, req.Description),
	})

	// Credit target account
	lines = append(lines, model.EntryLine{
		LineID:      fmt.Sprintf("%s-2", entryID),
		AccountID:   targetAcc.AccountID,
		Direction:   model.DirectionCredit,
		Amount:      req.Amount,
		Currency:    req.Currency,
		Description: fmt.Sprintf("Transfer from %s: %s", sourceAcc.AccountNumber, req.Description),
	})

	// Optional Fee lines
	if req.FeeAmount > 0 && feeAcc != nil {
		lines = append(lines, model.EntryLine{
			LineID:      fmt.Sprintf("%s-3", entryID),
			AccountID:   sourceAcc.AccountID,
			Direction:   model.DirectionDebit,
			Amount:      req.FeeAmount,
			Currency:    req.Currency,
			Description: fmt.Sprintf("Transaction fee for transfer %s", req.ReferenceID),
		})
		lines = append(lines, model.EntryLine{
			LineID:      fmt.Sprintf("%s-4", entryID),
			AccountID:   feeAcc.AccountID,
			Direction:   model.DirectionCredit,
			Amount:      req.FeeAmount,
			Currency:    req.Currency,
			Description: fmt.Sprintf("Fee revenue from transfer %s", req.ReferenceID),
		})
	}

	// 6. Fetch previous entry hash for tamper-evident chain
	previousHash := "0000000000000000000000000000000000000000000000000000000000000000"
	latestEntry, _ := pe.journalRepo.FindLatestEntry(ctx, req.TenantID)
	if latestEntry != nil && latestEntry.MerkleRoot != "" {
		previousHash = latestEntry.MerkleRoot
	}

	// 7. Create Journal Entry Aggregate and Post
	journalEntry, err := model.NewJournalEntry(
		entryID,
		req.TenantID,
		req.IdempotencyKey,
		req.ReferenceID,
		req.Description,
		req.Currency,
		req.ValueDate,
		lines,
		previousHash,
	)
	if err != nil {
		return nil, fmt.Errorf("journal entry creation failed: %w", err)
	}

	if err := journalEntry.Post(); err != nil {
		return nil, fmt.Errorf("posting journal entry failed: %w", err)
	}

	// 8. Mutate Account Balances
	if err := sourceAcc.ApplyDebit(req.Amount, req.Currency, false); err != nil {
		return nil, fmt.Errorf("debiting source account failed: %w", err)
	}
	if err := targetAcc.ApplyCredit(req.Amount, req.Currency, false); err != nil {
		return nil, fmt.Errorf("crediting target account failed: %w", err)
	}
	if req.FeeAmount > 0 && feeAcc != nil {
		if err := sourceAcc.ApplyDebit(req.FeeAmount, req.Currency, false); err != nil {
			return nil, fmt.Errorf("debiting fee failed: %w", err)
		}
		if err := feeAcc.ApplyCredit(req.FeeAmount, req.Currency, false); err != nil {
			return nil, fmt.Errorf("crediting fee failed: %w", err)
		}
	}

	// 9. Persist Entities
	if err := pe.accountRepo.Save(ctx, sourceAcc); err != nil {
		return nil, fmt.Errorf("saving source account failed: %w", err)
	}
	if err := pe.accountRepo.Save(ctx, targetAcc); err != nil {
		return nil, fmt.Errorf("saving target account failed: %w", err)
	}
	if feeAcc != nil && req.FeeAmount > 0 {
		if err := pe.accountRepo.Save(ctx, feeAcc); err != nil {
			return nil, fmt.Errorf("saving fee account failed: %w", err)
		}
	}
	if err := pe.journalRepo.SaveEntry(ctx, journalEntry); err != nil {
		return nil, fmt.Errorf("saving journal entry failed: %w", err)
	}

	// 10. Record Idempotency
	if pe.idempotencyRepo != nil {
		reqHash := computeRequestHash(req)
		_ = pe.idempotencyRepo.Save(ctx, &model.IdempotencyRecord{
			Key:         req.IdempotencyKey,
			TenantID:    req.TenantID,
			RequestHash: reqHash,
			EntryID:     journalEntry.EntryID,
			StatusCode:  200,
			CreatedAt:   time.Now().UTC(),
			ExpiresAt:   time.Now().UTC().Add(24 * time.Hour),
		})
	}

	return journalEntry, nil
}

// ProcessDeposit credits an asset/liability account against an external clearing source.
func (pe *PostingEngine) ProcessDeposit(
	ctx context.Context,
	req model.PostingRequest,
	clearingAccountID string,
) (*model.JournalEntryAggregate, error) {
	if err := req.Validate(); err != nil {
		return nil, err
	}

	lockKey := fmt.Sprintf("ledger:lock:%s:%s", req.TenantID, req.TargetAccount)
	handle, err := pe.lockManager.AcquireLock(ctx, lockKey, 10*time.Second)
	if err != nil {
		return nil, err
	}
	defer pe.lockManager.ReleaseLock(ctx, handle)

	targetAcc, err := pe.accountRepo.FindByID(ctx, req.TenantID, req.TargetAccount)
	if err != nil {
		return nil, err
	}
	clearingAcc, err := pe.accountRepo.FindByID(ctx, req.TenantID, clearingAccountID)
	if err != nil {
		return nil, err
	}

	entryID := fmt.Sprintf("dep_%s", uuid.New().String())
	lines := []model.EntryLine{
		{
			LineID:      fmt.Sprintf("%s-1", entryID),
			AccountID:   clearingAcc.AccountID,
			Direction:   model.DirectionDebit,
			Amount:      req.Amount,
			Currency:    req.Currency,
			Description: fmt.Sprintf("Clearing deposit funding for %s", targetAcc.AccountNumber),
		},
		{
			LineID:      fmt.Sprintf("%s-2", entryID),
			AccountID:   targetAcc.AccountID,
			Direction:   model.DirectionCredit,
			Amount:      req.Amount,
			Currency:    req.Currency,
			Description: req.Description,
		},
	}

	prevHash := "0000000000000000000000000000000000000000000000000000000000000000"
	latest, _ := pe.journalRepo.FindLatestEntry(ctx, req.TenantID)
	if latest != nil {
		prevHash = latest.MerkleRoot
	}

	entry, err := model.NewJournalEntry(
		entryID, req.TenantID, req.IdempotencyKey, req.ReferenceID,
		req.Description, req.Currency, req.ValueDate, lines, prevHash,
	)
	if err != nil {
		return nil, err
	}
	if err := entry.Post(); err != nil {
		return nil, err
	}

	if err := clearingAcc.ApplyDebit(req.Amount, req.Currency, false); err != nil {
		return nil, err
	}
	if err := targetAcc.ApplyCredit(req.Amount, req.Currency, false); err != nil {
		return nil, err
	}

	_ = pe.accountRepo.Save(ctx, clearingAcc)
	_ = pe.accountRepo.Save(ctx, targetAcc)
	_ = pe.journalRepo.SaveEntry(ctx, entry)

	return entry, nil
}

// ReverseTransaction inverts an existing posted journal entry with full audit trail.
func (pe *PostingEngine) ReverseTransaction(
	ctx context.Context,
	tenantID, entryID, reason string,
) (*model.JournalEntryAggregate, error) {
	original, err := pe.journalRepo.FindEntryByID(ctx, tenantID, entryID)
	if err != nil {
		return nil, err
	}

	reversalID := fmt.Sprintf("rev_%s", uuid.New().String())
	reversalEntry, err := original.CreateReversal(reversalID, reason)
	if err != nil {
		return nil, err
	}

	// Post reversal
	if err := reversalEntry.Post(); err != nil {
		return nil, err
	}

	// Mutate accounts by applying lines
	for _, l := range reversalEntry.Lines {
		acc, err := pe.accountRepo.FindByID(ctx, tenantID, l.AccountID)
		if err != nil {
			return nil, err
		}
		if l.Direction == model.DirectionDebit {
			_ = acc.ApplyDebit(l.Amount, l.Currency, false)
		} else {
			_ = acc.ApplyCredit(l.Amount, l.Currency, false)
		}
		_ = pe.accountRepo.Save(ctx, acc)
	}

	_ = pe.journalRepo.SaveEntry(ctx, original)
	_ = pe.journalRepo.SaveEntry(ctx, reversalEntry)

	return reversalEntry, nil
}

func computeRequestHash(req model.PostingRequest) string {
	payload := fmt.Sprintf("%s|%s|%s|%d|%s|%s|%s",
		req.TenantID, req.IdempotencyKey, req.ReferenceID,
		req.Amount, req.Currency, req.SourceAccount, req.TargetAccount,
	)
	h := sha256.Sum256([]byte(payload))
	return hex.EncodeToString(h[:])
}
