package http

import (
	"errors"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
)

// CreateAccountRequest contains fields to provision a new ledger account.
type CreateAccountRequest struct {
	AccountNumber  string            `json:"account_number" binding:"required"`
	Name           string            `json:"name" binding:"required"`
	Type           model.AccountType `json:"type" binding:"required"`
	Currency       string            `json:"currency" binding:"required"`
	OverdraftLimit int64             `json:"overdraft_limit"`
}

func (r *CreateAccountRequest) Validate() error {
	if !r.Type.IsValid() {
		return model.ErrInvalidAccountType
	}
	if r.AccountNumber == "" {
		return errors.New("account_number cannot be blank")
	}
	if r.Currency == "" {
		return errors.New("currency cannot be blank")
	}
	if r.OverdraftLimit < 0 {
		return errors.New("overdraft_limit must be non-negative")
	}
	return nil
}

// TransferRequest represents a transfer between two accounts.
type TransferRequest struct {
	IdempotencyKey string         `json:"idempotency_key" binding:"required"`
	ReferenceID    string         `json:"reference_id" binding:"required"`
	SourceAccount  string         `json:"source_account" binding:"required"`
	TargetAccount  string         `json:"target_account" binding:"required"`
	Amount         int64          `json:"amount" binding:"required,gt=0"`
	Currency       string         `json:"currency" binding:"required"`
	FeeAmount      int64          `json:"fee_amount"`
	FeeAccount     string         `json:"fee_account"`
	Description    string         `json:"description" binding:"required"`
	ValueDate      *time.Time     `json:"value_date"`
	Metadata       map[string]any `json:"metadata"`
}

// PlaceHoldRequest reserves funds on an account.
type PlaceHoldRequest struct {
	HoldID      string `json:"hold_id" binding:"required"`
	ReferenceID string `json:"reference_id" binding:"required"`
	Amount      int64  `json:"amount" binding:"required,gt=0"`
	Currency    string `json:"currency" binding:"required"`
	Reason      string `json:"reason" binding:"required"`
	DurationSec int64  `json:"duration_sec" binding:"required,gt=0"`
}

// ReversalRequest triggers inversion of a posted transaction.
type ReversalRequest struct {
	Reason string `json:"reason" binding:"required"`
}

// ApiResponse standardizes REST output format.
type ApiResponse struct {
	Success bool   `json:"success"`
	Data    any    `json:"data,omitempty"`
	Error   string `json:"error,omitempty"`
	TraceID string `json:"trace_id,omitempty"`
}
