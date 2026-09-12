package model

import (
	"errors"
	"time"
)

// TransactionType defines the operational classification of a financial transaction.
type TransactionType string

const (
	TxTypeDeposit         TransactionType = "DEPOSIT"
	TxTypeWithdrawal      TransactionType = "WITHDRAWAL"
	TxTypeTransfer        TransactionType = "TRANSFER"
	TxTypeFeeDeduction    TransactionType = "FEE_DEDUCTION"
	TxTypeInterestAccrual TransactionType = "INTEREST_ACCRUAL"
	TxTypeFXExchange      TransactionType = "FX_EXCHANGE"
	TxTypeClearingPayout  TransactionType = "CLEARING_PAYOUT"
	TxTypeManualJournal   TransactionType = "MANUAL_JOURNAL"
)

// PostingRequest encapsulates a high-level intent to record a financial transaction.
type PostingRequest struct {
	RequestID      string          `json:"request_id"`
	TenantID       string          `json:"tenant_id"`
	IdempotencyKey string          `json:"idempotency_key"`
	Type           TransactionType `json:"type"`
	ReferenceID    string          `json:"reference_id"`
	SourceAccount  string          `json:"source_account,omitempty"`
	TargetAccount  string          `json:"target_account,omitempty"`
	Amount         int64           `json:"amount"` // In minor units
	Currency       string          `json:"currency"`
	FeeAmount      int64           `json:"fee_amount,omitempty"`
	FeeAccount     string          `json:"fee_account,omitempty"`
	Description    string          `json:"description"`
	ValueDate      time.Time       `json:"value_date"`
	Metadata       map[string]any  `json:"metadata,omitempty"`
}

// Validate ensures all mandatory parameters for the transaction type are present.
func (p *PostingRequest) Validate() error {
	if p.RequestID == "" {
		return errors.New("request ID is required")
	}
	if p.TenantID == "" {
		return errors.New("tenant ID is required")
	}
	if p.IdempotencyKey == "" {
		return errors.New("idempotency key is required")
	}
	if p.Amount <= 0 {
		return errors.New("amount must be positive")
	}
	if p.Currency == "" {
		return errors.New("currency is required")
	}

	switch p.Type {
	case TxTypeTransfer:
		if p.SourceAccount == "" || p.TargetAccount == "" {
			return errors.New("transfer requires both source_account and target_account")
		}
		if p.SourceAccount == p.TargetAccount {
			return errors.New("source and target accounts cannot be identical in transfer")
		}
	case TxTypeDeposit:
		if p.TargetAccount == "" {
			return errors.New("deposit requires target_account")
		}
	case TxTypeWithdrawal:
		if p.SourceAccount == "" {
			return errors.New("withdrawal requires source_account")
		}
	case TxTypeFeeDeduction:
		if p.SourceAccount == "" || p.FeeAccount == "" {
			return errors.New("fee deduction requires source_account and fee_account")
		}
	}
	return nil
}

// IdempotencyRecord tracks processed requests to guarantee exactly-once execution.
type IdempotencyRecord struct {
	Key          string    `json:"key"`
	TenantID     string    `json:"tenant_id"`
	RequestHash  string    `json:"request_hash"`
	EntryID      string    `json:"entry_id"`
	ResponseJSON string    `json:"response_json"`
	StatusCode   int       `json:"status_code"`
	CreatedAt    time.Time `json:"created_at"`
	ExpiresAt    time.Time `json:"expires_at"`
}

// IsExpired checks if the idempotency lock has lapsed.
func (r *IdempotencyRecord) IsExpired() bool {
	return time.Now().UTC().After(r.ExpiresAt)
}

// ClearingBatch groups multiple transactions for periodic bulk settlement.
type ClearingBatch struct {
	BatchID          string          `json:"batch_id"`
	TenantID         string          `json:"tenant_id"`
	BatchNumber      string          `json:"batch_number"`
	Status           string          `json:"status"` // OPEN, PROCESSING, SETTLED, FAILED
	TransactionCount int             `json:"transaction_count"`
	TotalGrossAmount int64           `json:"total_gross_amount"`
	Currency         string          `json:"currency"`
	OpenedAt         time.Time       `json:"opened_at"`
	ClosedAt         time.Time       `json:"closed_at,omitempty"`
	SettledAt        time.Time       `json:"settled_at,omitempty"`
	Transactions     []string        `json:"transactions"` // List of Journal Entry IDs
}
