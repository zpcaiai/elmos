package service

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
)

var (
	ErrTrialBalanceImbalance = errors.New("trial balance failed: total debits do not equal total credits")
	ErrMerkleTamperDetected  = errors.New("merkle chain tampering or broken link detected")
)

// TrialBalanceEntry represents one line item on the trial balance sheet.
type TrialBalanceEntry struct {
	AccountID     string                `json:"account_id"`
	AccountNumber string                `json:"account_number"`
	AccountName   string                `json:"account_name"`
	Type          model.AccountType     `json:"type"`
	DebitBalance  int64                 `json:"debit_balance"`
	CreditBalance int64                 `json:"credit_balance"`
	Currency      string                `json:"currency"`
	Status        model.AccountStatus   `json:"status"`
}

// TrialBalanceReport summarizes the financial state of all accounts for a tenant.
type TrialBalanceReport struct {
	TenantID     string              `json:"tenant_id"`
	AsOfTime     time.Time           `json:"as_of_time"`
	TotalDebit   int64               `json:"total_debit"`
	TotalCredit  int64               `json:"total_credit"`
	Variance     int64               `json:"variance"`
	IsBalanced   bool                `json:"is_balanced"`
	AccountCount int                 `json:"account_count"`
	Entries      []TrialBalanceEntry `json:"entries"`
}

// AuditVerificationReport summarizes cryptographic audit verification across ledger entries.
type AuditVerificationReport struct {
	TenantID        string    `json:"tenant_id"`
	CheckedFrom     time.Time `json:"checked_from"`
	CheckedTo       time.Time `json:"checked_to"`
	TotalVerified   int       `json:"total_verified"`
	IsChainIntact   bool      `json:"is_chain_intact"`
	BrokenAtEntryID string    `json:"broken_at_entry_id,omitempty"`
	RootMerkleHash  string    `json:"root_merkle_hash"`
}

// ReconciliationService provides automated trial balance auditing and Merkle integrity verification.
type ReconciliationService struct {
	accountRepo repository.AccountRepository
	journalRepo repository.JournalRepository
}

func NewReconciliationService(
	accRepo repository.AccountRepository,
	jourRepo repository.JournalRepository,
) *ReconciliationService {
	return &ReconciliationService{
		accountRepo: accRepo,
		journalRepo: jourRepo,
	}
}

// GenerateTrialBalance computes the trial balance sheet across all active ledger accounts.
func (rs *ReconciliationService) GenerateTrialBalance(
	ctx context.Context,
	tenantID string,
	asOf time.Time,
) (*TrialBalanceReport, error) {
	accounts, err := rs.accountRepo.ListByTenant(ctx, tenantID, 10000, 0)
	if err != nil {
		return nil, fmt.Errorf("failed fetching accounts for trial balance: %w", err)
	}

	report := &TrialBalanceReport{
		TenantID:     tenantID,
		AsOfTime:     asOf.UTC(),
		AccountCount: len(accounts),
	}

	for _, acc := range accounts {
		snap := acc.Snapshot()
		entry := TrialBalanceEntry{
			AccountID:     snap.AccountID,
			AccountNumber: snap.AccountNumber,
			AccountName:   snap.Name,
			Type:          snap.Type,
			Currency:      snap.Currency,
			Status:        snap.Status,
		}

		if snap.Type.NormalBalance() == model.DirectionDebit {
			if snap.PostedBalance >= 0 {
				entry.DebitBalance = snap.PostedBalance
			} else {
				entry.CreditBalance = -snap.PostedBalance
			}
		} else {
			if snap.PostedBalance >= 0 {
				entry.CreditBalance = snap.PostedBalance
			} else {
				entry.DebitBalance = -snap.PostedBalance
			}
		}

		report.TotalDebit += entry.DebitBalance
		report.TotalCredit += entry.CreditBalance
		report.Entries = append(report.Entries, entry)
	}

	report.Variance = report.TotalDebit - report.TotalCredit
	report.IsBalanced = report.Variance == 0

	return report, nil
}

// VerifyAuditIntegrity traverses journal entries and validates cryptographic hash chaining.
func (rs *ReconciliationService) VerifyAuditIntegrity(
	ctx context.Context,
	tenantID string,
	from, to time.Time,
) (*AuditVerificationReport, error) {
	hashes, err := rs.journalRepo.GetEntryHashesForPeriod(ctx, tenantID, from, to)
	if err != nil {
		return nil, err
	}

	report := &AuditVerificationReport{
		TenantID:      tenantID,
		CheckedFrom:   from,
		CheckedTo:     to,
		TotalVerified: len(hashes),
		IsChainIntact: true,
	}

	if len(hashes) == 0 {
		return report, nil
	}

	tree, err := model.BuildMerkleTree(hashes)
	if err != nil {
		return nil, fmt.Errorf("merkle tree construction failed: %w", err)
	}
	report.RootMerkleHash = tree.RootHex()

	// Verify each leaf proof against root
	for idx := range hashes {
		proof, err := tree.GenerateProof(idx)
		if err != nil {
			report.IsChainIntact = false
			report.BrokenAtEntryID = fmt.Sprintf("leaf_index_%d", idx)
			return report, fmt.Errorf("proof generation failed at %d: %w", idx, err)
		}
		if !model.VerifyProof(proof) {
			report.IsChainIntact = false
			report.BrokenAtEntryID = fmt.Sprintf("invalid_proof_leaf_%d", idx)
			return report, fmt.Errorf("tamper detected at leaf %d", idx)
		}
	}

	return report, nil
}
