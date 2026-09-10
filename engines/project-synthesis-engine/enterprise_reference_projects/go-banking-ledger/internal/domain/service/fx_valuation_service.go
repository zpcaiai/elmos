package service

import (
	"context"
	"fmt"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
	"github.com/google/uuid"
)

// FXValuationService computes unrealized currency revaluations and records mark-to-market adjustments.
type FXValuationService struct {
	accountRepo repository.AccountRepository
	journalRepo repository.JournalRepository
	currencyReg *model.CurrencyRegistry
}

func NewFXValuationService(
	accRepo repository.AccountRepository,
	jourRepo repository.JournalRepository,
	currReg *model.CurrencyRegistry,
) *FXValuationService {
	return &FXValuationService{
		accountRepo: accRepo,
		journalRepo: jourRepo,
		currencyReg: currReg,
	}
}

// FXRevaluationResult holds the calculated gains or losses for an account.
type FXRevaluationResult struct {
	AccountID     string  `json:"account_id"`
	Currency      string  `json:"currency"`
	ForeignAmount int64   `json:"foreign_amount"`
	BookBaseValue int64   `json:"book_base_value"`
	MarketBaseVal int64   `json:"market_base_val"`
	UnrealizedGainLoss int64 `json:"unrealized_gain_loss"` // Positive = Gain, Negative = Loss
}

// RevalueForeignAccount calculates currency variance and optionally posts mark-to-market journal entries.
func (f *FXValuationService) RevalueForeignAccount(
	ctx context.Context,
	tenantID, accountID string,
	currentFXRate model.FXRate,
	baseCurrency string,
	gainLossAccountID string,
	autoPost bool,
) (*FXRevaluationResult, *model.JournalEntryAggregate, error) {
	acc, err := f.accountRepo.FindByID(ctx, tenantID, accountID)
	if err != nil {
		return nil, nil, err
	}

	if acc.Currency == baseCurrency {
		return nil, nil, fmt.Errorf("account %s is already in base currency %s", accountID, baseCurrency)
	}

	baseSpec, err := f.currencyReg.Get(baseCurrency)
	if err != nil {
		return nil, nil, err
	}
	foreignSpec, err := f.currencyReg.Get(acc.Currency)
	if err != nil {
		return nil, nil, err
	}

	marketBaseVal, err := currentFXRate.Convert(acc.PostedBalance, foreignSpec, baseSpec)
	if err != nil {
		return nil, nil, fmt.Errorf("fx conversion error: %w", err)
	}

	// Calculate difference against book value (assumed previous valuation)
	gainLoss := marketBaseVal - acc.PostedBalance
	res := &FXRevaluationResult{
		AccountID:          accountID,
		Currency:           acc.Currency,
		ForeignAmount:      acc.PostedBalance,
		BookBaseValue:      acc.PostedBalance,
		MarketBaseVal:      marketBaseVal,
		UnrealizedGainLoss: gainLoss,
	}

	if !autoPost || gainLoss == 0 {
		return res, nil, nil
	}

	// Construct Mark-to-Market Journal Entry
	entryID := fmt.Sprintf("fx_mtm_%s", uuid.New().String())
	var lines []model.EntryLine

	if gainLoss > 0 {
		// Gain: Debit Asset (Revalued Account), Credit FX Gain (Revenue/Equity)
		lines = append(lines, model.EntryLine{
			LineID:      fmt.Sprintf("%s-1", entryID),
			AccountID:   accountID,
			Direction:   model.DirectionDebit,
			Amount:      gainLoss,
			Currency:    baseCurrency,
			Description: fmt.Sprintf("FX Mark-to-Market unrealized gain (%s to %s)", acc.Currency, baseCurrency),
		})
		lines = append(lines, model.EntryLine{
			LineID:      fmt.Sprintf("%s-2", entryID),
			AccountID:   gainLossAccountID,
			Direction:   model.DirectionCredit,
			Amount:      gainLoss,
			Currency:    baseCurrency,
			Description: fmt.Sprintf("Unrealized FX Gain for account %s", acc.AccountNumber),
		})
	} else {
		// Loss: Debit FX Loss (Expense), Credit Asset (Revalued Account)
		absLoss := -gainLoss
		lines = append(lines, model.EntryLine{
			LineID:      fmt.Sprintf("%s-1", entryID),
			AccountID:   gainLossAccountID,
			Direction:   model.DirectionDebit,
			Amount:      absLoss,
			Currency:    baseCurrency,
			Description: fmt.Sprintf("Unrealized FX Loss for account %s", acc.AccountNumber),
		})
		lines = append(lines, model.EntryLine{
			LineID:      fmt.Sprintf("%s-2", entryID),
			AccountID:   accountID,
			Direction:   model.DirectionCredit,
			Amount:      absLoss,
			Currency:    baseCurrency,
			Description: fmt.Sprintf("FX Mark-to-Market unrealized loss (%s to %s)", acc.Currency, baseCurrency),
		})
	}

	prevHash := "0000000000000000000000000000000000000000000000000000000000000000"
	latest, _ := f.journalRepo.FindLatestEntry(ctx, tenantID)
	if latest != nil {
		prevHash = latest.MerkleRoot
	}

	entry, err := model.NewJournalEntry(
		entryID,
		tenantID,
		fmt.Sprintf("fx-mtm-%s-%d", accountID, time.Now().Unix()),
		fmt.Sprintf("MTM-%s", accountID),
		fmt.Sprintf("End-of-day FX revaluation for %s", acc.AccountNumber),
		baseCurrency,
		time.Now().UTC(),
		lines,
		prevHash,
	)
	if err != nil {
		return nil, nil, err
	}

	if err := entry.Post(); err != nil {
		return nil, nil, err
	}

	if err := f.journalRepo.SaveEntry(ctx, entry); err != nil {
		return nil, nil, err
	}

	return res, entry, nil
}
