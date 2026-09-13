package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sync"
	"time"
)

// AccountType represents the standard double-entry accounting category.
type AccountType string

const (
	AccountTypeAsset     AccountType = "ASSET"
	AccountTypeLiability AccountType = "LIABILITY"
	AccountTypeEquity    AccountType = "EQUITY"
	AccountTypeRevenue   AccountType = "REVENUE"
	AccountTypeExpense   AccountType = "EXPENSE"
)

// IsValid verifies whether the AccountType is known and supported.
func (at AccountType) IsValid() bool {
	switch at {
	case AccountTypeAsset, AccountTypeLiability, AccountTypeEquity, AccountTypeRevenue, AccountTypeExpense:
		return true
	default:
		return false
	}
}

// NormalBalance returns whether the normal balance is Debit or Credit.
// Asset and Expense have normal Debit balance.
// Liability, Equity, and Revenue have normal Credit balance.
func (at AccountType) NormalBalance() PostingDirection {
	switch at {
	case AccountTypeAsset, AccountTypeExpense:
		return DirectionDebit
	default:
		return DirectionCredit
	}
}

// AccountStatus defines the operational lifecycle state of a ledger account.
type AccountStatus string

const (
	AccountStatusPending   AccountStatus = "PENDING"
	AccountStatusActive    AccountStatus = "ACTIVE"
	AccountStatusFrozen    AccountStatus = "FROZEN"
	AccountStatusSuspended AccountStatus = "SUSPENDED"
	AccountStatusClosed    AccountStatus = "CLOSED"
)

// Common account domain errors.
var (
	ErrInvalidAccountType    = errors.New("invalid account type")
	ErrInvalidAccountStatus  = errors.New("invalid account status")
	ErrAccountNotActive      = errors.New("account is not active")
	ErrAccountFrozen         = errors.New("account is frozen, debits and credits rejected")
	ErrAccountClosed         = errors.New("account is closed, operations rejected")
	ErrInsufficientFunds     = errors.New("insufficient available balance")
	ErrInvalidAmount         = errors.New("amount must be strictly positive")
	ErrHoldNotFound          = errors.New("hold id not found")
	ErrHoldAlreadyReleased   = errors.New("hold is already released")
	ErrHoldAmountMismatch    = errors.New("release amount exceeds active held amount")
	ErrCurrencyMismatch      = errors.New("currency mismatch for account operation")
	ErrOptimisticLockFailure = errors.New("concurrent account modification detected, version conflict")
)

// HoldRecord tracks temporary authorizations or ring-fenced funds on an account.
type HoldRecord struct {
	HoldID      string    `json:"hold_id"`
	AccountID   string    `json:"account_id"`
	Amount      int64     `json:"amount"` // Scaled integer in minor units (e.g. cents)
	Currency    string    `json:"currency"`
	Reason      string    `json:"reason"`
	ReferenceID string    `json:"reference_id"`
	CreatedAt   time.Time `json:"created_at"`
	ExpiresAt   time.Time `json:"expires_at"`
	IsReleased  bool      `json:"is_released"`
	ReleasedAt  time.Time `json:"released_at,omitempty"`
}

// AccountAggregate represents the primary domain aggregate root for a ledger account.
type AccountAggregate struct {
	mu sync.RWMutex

	AccountID      string        `json:"account_id"`
	TenantID       string        `json:"tenant_id"`
	AccountNumber  string        `json:"account_number"`
	Name           string        `json:"name"`
	Type           AccountType   `json:"type"`
	Status         AccountStatus `json:"status"`
	Currency       string        `json:"currency"`
	PostedBalance  int64         `json:"posted_balance"`  // Settled balance in minor units
	PendingDebit   int64         `json:"pending_debit"`   // Unsettled debits
	PendingCredit  int64         `json:"pending_credit"`  // Unsettled credits
	HeldAmount     int64         `json:"held_amount"`     // Active holds
	OverdraftLimit int64         `json:"overdraft_limit"` // Permitted negative balance threshold
	Version        int64         `json:"version"`         // Optimistic concurrency version
	MerkleRoot     string        `json:"merkle_root"`     // Hash of latest ledger state
	CreatedAt      time.Time     `json:"created_at"`
	UpdatedAt      time.Time     `json:"updated_at"`

	ActiveHolds map[string]*HoldRecord `json:"active_holds"`
}

// NewAccount creates a newly initialized, uncommitted account aggregate.
func NewAccount(
	accountID, tenantID, accountNumber, name string,
	accType AccountType,
	currency string,
	overdraftLimit int64,
) (*AccountAggregate, error) {
	if !accType.IsValid() {
		return nil, ErrInvalidAccountType
	}
	if currency == "" {
		return nil, errors.New("currency code cannot be empty")
	}
	if overdraftLimit < 0 {
		return nil, errors.New("overdraft limit must be non-negative")
	}

	now := time.Now().UTC()
	acc := &AccountAggregate{
		AccountID:      accountID,
		TenantID:       tenantID,
		AccountNumber:  accountNumber,
		Name:           name,
		Type:           accType,
		Status:         AccountStatusActive,
		Currency:       currency,
		PostedBalance:  0,
		PendingDebit:   0,
		PendingCredit:  0,
		HeldAmount:     0,
		OverdraftLimit: overdraftLimit,
		Version:        1,
		CreatedAt:      now,
		UpdatedAt:      now,
		ActiveHolds:    make(map[string]*HoldRecord),
	}
	acc.MerkleRoot = acc.computeStateHash()
	return acc, nil
}

// AvailableBalance computes the spendable funds considering overdraft and active holds.
// Formula:
// For Asset/Expense: Available = PostedBalance + PendingCredit - PendingDebit - HeldAmount + OverdraftLimit
// For Liability/Equity/Revenue: Available = PostedBalance + PendingCredit - PendingDebit
func (a *AccountAggregate) AvailableBalance() int64 {
	a.mu.RLock()
	defer a.mu.RUnlock()

	return a.calculateAvailableBalance()
}

func (a *AccountAggregate) calculateAvailableBalance() int64 {
	return a.PostedBalance + a.PendingCredit - a.PendingDebit - a.HeldAmount + a.OverdraftLimit
}

// CheckDebitAllowed verifies if a debit operation can proceed without violating funds constraints.
// For Asset/Expense, Debit is an increase (always allowed).
// For Liability/Equity/Revenue, Debit is a decrease (requires available balance).
func (a *AccountAggregate) CheckDebitAllowed(amount int64, currency string) error {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if err := a.checkOperationPreconditions(currency); err != nil {
		return err
	}
	if amount <= 0 {
		return ErrInvalidAmount
	}

	if a.Type.NormalBalance() == DirectionCredit {
		avail := a.calculateAvailableBalance()
		if avail < amount {
			return fmt.Errorf("%w: available %d, requested debit %d", ErrInsufficientFunds, avail, amount)
		}
	}
	return nil
}

// CheckCreditAllowed verifies if a credit operation can proceed.
// For Liability/Equity/Revenue, Credit is an increase (always allowed).
// For Asset/Expense, Credit is a decrease (requires available balance).
func (a *AccountAggregate) CheckCreditAllowed(amount int64, currency string) error {
	a.mu.RLock()
	defer a.mu.RUnlock()

	if err := a.checkOperationPreconditions(currency); err != nil {
		return err
	}
	if amount <= 0 {
		return ErrInvalidAmount
	}

	if a.Type.NormalBalance() == DirectionDebit {
		avail := a.calculateAvailableBalance()
		if avail < amount {
			return fmt.Errorf("%w: available %d, requested credit %d", ErrInsufficientFunds, avail, amount)
		}
	}
	return nil
}

// ApplyDebit mutates the settled or pending balance by debiting the account.
func (a *AccountAggregate) ApplyDebit(amount int64, currency string, isPending bool) error {
	a.mu.Lock()
	defer a.mu.Unlock()

	if err := a.checkOperationPreconditions(currency); err != nil {
		return err
	}
	if amount <= 0 {
		return ErrInvalidAmount
	}

	if a.Type.NormalBalance() == DirectionCredit {
		// Debit decreases liability/equity/revenue
		avail := a.calculateAvailableBalance()
		if avail < amount {
			return fmt.Errorf("%w: available %d, required %d", ErrInsufficientFunds, avail, amount)
		}
		if isPending {
			a.PendingDebit += amount
		} else {
			a.PostedBalance -= amount
		}
	} else {
		// Debit increases asset/expense
		if isPending {
			a.PendingDebit += amount
		} else {
			a.PostedBalance += amount
		}
	}

	a.Version++
	a.UpdatedAt = time.Now().UTC()
	a.MerkleRoot = a.computeStateHash()
	return nil
}

// ApplyCredit mutates the settled or pending balance by crediting the account.
func (a *AccountAggregate) ApplyCredit(amount int64, currency string, isPending bool) error {
	a.mu.Lock()
	defer a.mu.Unlock()

	if err := a.checkOperationPreconditions(currency); err != nil {
		return err
	}
	if amount <= 0 {
		return ErrInvalidAmount
	}

	if a.Type.NormalBalance() == DirectionDebit {
		// Credit decreases asset/expense
		avail := a.calculateAvailableBalance()
		if avail < amount {
			return fmt.Errorf("%w: available %d, required %d", ErrInsufficientFunds, avail, amount)
		}
		if isPending {
			a.PendingCredit += amount
		} else {
			a.PostedBalance -= amount
		}
	} else {
		// Credit increases liability/equity/revenue
		if isPending {
			a.PendingCredit += amount
		} else {
			a.PostedBalance += amount
		}
	}

	a.Version++
	a.UpdatedAt = time.Now().UTC()
	a.MerkleRoot = a.computeStateHash()
	return nil
}

// SettlePending resolves a previously marked pending debit or credit into the posted balance.
func (a *AccountAggregate) SettlePending(debitAmount, creditAmount int64) error {
	a.mu.Lock()
	defer a.mu.Unlock()

	if debitAmount < 0 || creditAmount < 0 {
		return errors.New("settlement amounts must not be negative")
	}
	if debitAmount > a.PendingDebit {
		return errors.New("settlement debit exceeds pending debit balance")
	}
	if creditAmount > a.PendingCredit {
		return errors.New("settlement credit exceeds pending credit balance")
	}

	a.PendingDebit -= debitAmount
	a.PendingCredit -= creditAmount

	if a.Type.NormalBalance() == DirectionDebit {
		a.PostedBalance += (debitAmount - creditAmount)
	} else {
		a.PostedBalance += (creditAmount - debitAmount)
	}

	a.Version++
	a.UpdatedAt = time.Now().UTC()
	a.MerkleRoot = a.computeStateHash()
	return nil
}

// PlaceHold creates a reservation on the available balance for a pending external operation.
func (a *AccountAggregate) PlaceHold(
	holdID, referenceID, reason string,
	amount int64,
	currency string,
	duration time.Duration,
) (*HoldRecord, error) {
	a.mu.Lock()
	defer a.mu.Unlock()

	if err := a.checkOperationPreconditions(currency); err != nil {
		return nil, err
	}
	if amount <= 0 {
		return nil, ErrInvalidAmount
	}

	avail := a.calculateAvailableBalance()
	if avail < amount {
		return nil, fmt.Errorf("%w: available %d, requested hold %d", ErrInsufficientFunds, avail, amount)
	}

	if _, exists := a.ActiveHolds[holdID]; exists {
		return nil, fmt.Errorf("hold id %s already exists", holdID)
	}

	now := time.Now().UTC()
	record := &HoldRecord{
		HoldID:      holdID,
		AccountID:   a.AccountID,
		Amount:      amount,
		Currency:    currency,
		Reason:      reason,
		ReferenceID: referenceID,
		CreatedAt:   now,
		ExpiresAt:   now.Add(duration),
		IsReleased:  false,
	}

	a.ActiveHolds[holdID] = record
	a.HeldAmount += amount
	a.Version++
	a.UpdatedAt = now
	a.MerkleRoot = a.computeStateHash()

	return record, nil
}

// ReleaseHold cancels or fulfills an active hold, restoring the available balance.
func (a *AccountAggregate) ReleaseHold(holdID string) (*HoldRecord, error) {
	a.mu.Lock()
	defer a.mu.Unlock()

	record, exists := a.ActiveHolds[holdID]
	if !exists {
		return nil, ErrHoldNotFound
	}
	if record.IsReleased {
		return nil, ErrHoldAlreadyReleased
	}

	now := time.Now().UTC()
	record.IsReleased = true
	record.ReleasedAt = now
	delete(a.ActiveHolds, holdID)

	a.HeldAmount -= record.Amount
	if a.HeldAmount < 0 {
		a.HeldAmount = 0
	}

	a.Version++
	a.UpdatedAt = now
	a.MerkleRoot = a.computeStateHash()
	return record, nil
}

// Freeze prevents any debits or credits on this account, useful for fraud prevention.
func (a *AccountAggregate) Freeze(reason string) error {
	a.mu.Lock()
	defer a.mu.Unlock()

	if a.Status == AccountStatusClosed {
		return ErrAccountClosed
	}
	a.Status = AccountStatusFrozen
	a.Version++
	a.UpdatedAt = time.Now().UTC()
	a.MerkleRoot = a.computeStateHash()
	return nil
}

// Unfreeze restores a frozen account to active status.
func (a *AccountAggregate) Unfreeze() error {
	a.mu.Lock()
	defer a.mu.Unlock()

	if a.Status != AccountStatusFrozen {
		return errors.New("account is not frozen")
	}
	a.Status = AccountStatusActive
	a.Version++
	a.UpdatedAt = time.Now().UTC()
	a.MerkleRoot = a.computeStateHash()
	return nil
}

// Close marks the account as closed if there is zero balance and no active holds.
func (a *AccountAggregate) Close() error {
	a.mu.Lock()
	defer a.mu.Unlock()

	if a.PostedBalance != 0 || a.PendingDebit != 0 || a.PendingCredit != 0 || a.HeldAmount != 0 {
		return errors.New("cannot close account with non-zero balance or active holds")
	}
	a.Status = AccountStatusClosed
	a.Version++
	a.UpdatedAt = time.Now().UTC()
	a.MerkleRoot = a.computeStateHash()
	return nil
}

// checkOperationPreconditions verifies status and currency match.
func (a *AccountAggregate) checkOperationPreconditions(currency string) error {
	if a.Status != AccountStatusActive {
		if a.Status == AccountStatusFrozen {
			return ErrAccountFrozen
		}
		if a.Status == AccountStatusClosed {
			return ErrAccountClosed
		}
		return ErrAccountNotActive
	}
	if a.Currency != currency {
		return fmt.Errorf("%w: expected %s, got %s", ErrCurrencyMismatch, a.Currency, currency)
	}
	return nil
}

// computeStateHash produces a deterministic SHA-256 hash of the account state.
func (a *AccountAggregate) computeStateHash() string {
	payload := fmt.Sprintf(
		"%s|%s|%s|%s|%s|%d|%d|%d|%d|%d|%d",
		a.AccountID,
		a.TenantID,
		a.AccountNumber,
		a.Type,
		a.Status,
		a.PostedBalance,
		a.PendingDebit,
		a.PendingCredit,
		a.HeldAmount,
		a.OverdraftLimit,
		a.Version,
	)
	hash := sha256.Sum256([]byte(payload))
	return hex.EncodeToString(hash[:])
}

// StateSnapshot exports an immutable copy of the account aggregate state.
type AccountSnapshot struct {
	AccountID        string        `json:"account_id"`
	TenantID         string        `json:"tenant_id"`
	AccountNumber    string        `json:"account_number"`
	Name             string        `json:"name"`
	Type             AccountType   `json:"type"`
	Status           AccountStatus `json:"status"`
	Currency         string        `json:"currency"`
	PostedBalance    int64         `json:"posted_balance"`
	PendingDebit     int64         `json:"pending_debit"`
	PendingCredit    int64         `json:"pending_credit"`
	HeldAmount       int64         `json:"held_amount"`
	AvailableBalance int64         `json:"available_balance"`
	OverdraftLimit   int64         `json:"overdraft_limit"`
	Version          int64         `json:"version"`
	MerkleRoot       string        `json:"merkle_root"`
	UpdatedAt        time.Time     `json:"updated_at"`
}

// Snapshot returns a point-in-time read-only copy of the account.
func (a *AccountAggregate) Snapshot() AccountSnapshot {
	a.mu.RLock()
	defer a.mu.RUnlock()

	return AccountSnapshot{
		AccountID:        a.AccountID,
		TenantID:         a.TenantID,
		AccountNumber:    a.AccountNumber,
		Name:             a.Name,
		Type:             a.Type,
		Status:           a.Status,
		Currency:         a.Currency,
		PostedBalance:    a.PostedBalance,
		PendingDebit:     a.PendingDebit,
		PendingCredit:    a.PendingCredit,
		HeldAmount:       a.HeldAmount,
		AvailableBalance: a.calculateAvailableBalance(),
		OverdraftLimit:   a.OverdraftLimit,
		Version:          a.Version,
		MerkleRoot:       a.MerkleRoot,
		UpdatedAt:        a.UpdatedAt,
	}
}
