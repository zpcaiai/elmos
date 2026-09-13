package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"
)

// JournalStatus denotes the state of a financial journal entry.
type JournalStatus string

const (
	JournalStatusDraft    JournalStatus = "DRAFT"
	JournalStatusPosted   JournalStatus = "POSTED"
	JournalStatusReversed JournalStatus = "REVERSED"
	JournalStatusRejected JournalStatus = "REJECTED"
)

var (
	ErrUnbalancedEntry      = errors.New("journal entry is unbalanced: debits must equal credits")
	ErrEmptyLines           = errors.New("journal entry must contain at least two lines")
	ErrInvalidLineAmount    = errors.New("journal entry line amount must be strictly greater than zero")
	ErrLineAccountMissing   = errors.New("journal entry line missing required account ID")
	ErrAlreadyPosted        = errors.New("journal entry is already posted")
	ErrAlreadyReversed      = errors.New("journal entry is already reversed")
	ErrCannotReverseUnposted= errors.New("cannot reverse an unposted journal entry")
)

// EntryLine represents a single debit or credit movement in a journal transaction.
type EntryLine struct {
	LineID       string           `json:"line_id"`
	AccountID    string           `json:"account_id"`
	Direction    PostingDirection `json:"direction"`
	Amount       int64            `json:"amount"` // Minor units (e.g. cents)
	Currency     string           `json:"currency"`
	ExchangeRate float64          `json:"exchange_rate,omitempty"` // Base currency conversion rate
	BaseAmount   int64            `json:"base_amount,omitempty"`    // Amount normalized to ledger base currency
	Description  string           `json:"description"`
	Metadata     map[string]any   `json:"metadata,omitempty"`
}

// ComputeLineHash produces a deterministic hash of an entry line.
func (l *EntryLine) ComputeLineHash() string {
	payload := fmt.Sprintf(
		"%s|%s|%s|%d|%s|%.6f|%d|%s",
		l.LineID,
		l.AccountID,
		l.Direction,
		l.Amount,
		l.Currency,
		l.ExchangeRate,
		l.BaseAmount,
		l.Description,
	)
	h := sha256.Sum256([]byte(payload))
	return hex.EncodeToString(h[:])
}

// JournalEntryAggregate represents an atomic financial voucher in double-entry bookkeeping.
type JournalEntryAggregate struct {
	EntryID            string        `json:"entry_id"`
	TenantID           string        `json:"tenant_id"`
	IdempotencyKey     string        `json:"idempotency_key"`
	ReferenceID        string        `json:"reference_id"`
	Description        string        `json:"description"`
	Status             JournalStatus `json:"status"`
	ValueDate          time.Time     `json:"value_date"`
	PostingDate        time.Time     `json:"posting_date"`
	Lines              []EntryLine   `json:"lines"`
	TotalDebit         int64         `json:"total_debit"`
	TotalCredit        int64         `json:"total_credit"`
	Currency           string        `json:"currency"`
	IsMultiCurrency    bool          `json:"is_multi_currency"`
	BaseCurrency       string        `json:"base_currency,omitempty"`
	MerkleRoot         string        `json:"merkle_root"`
	PreviousEntryHash  string        `json:"previous_entry_hash"`
	ReversalOfEntryID  string        `json:"reversal_of_entry_id,omitempty"`
	ReversedByEntryID  string        `json:"reversed_by_entry_id,omitempty"`
	CreatedAt          time.Time     `json:"created_at"`
	PostedAt           time.Time     `json:"posted_at,omitempty"`
}

// NewJournalEntry creates a new draft journal entry and validates structural constraints.
func NewJournalEntry(
	entryID, tenantID, idempotencyKey, referenceID, description, currency string,
	valueDate time.Time,
	lines []EntryLine,
	previousHash string,
) (*JournalEntryAggregate, error) {
	if len(lines) < 2 {
		return nil, ErrEmptyLines
	}
	if strings.TrimSpace(entryID) == "" {
		return nil, errors.New("entry ID cannot be empty")
	}
	if strings.TrimSpace(tenantID) == "" {
		return nil, errors.New("tenant ID cannot be empty")
	}

	entry := &JournalEntryAggregate{
		EntryID:           entryID,
		TenantID:          tenantID,
		IdempotencyKey:    idempotencyKey,
		ReferenceID:       referenceID,
		Description:       description,
		Status:            JournalStatusDraft,
		ValueDate:         valueDate.UTC(),
		PostingDate:       time.Now().UTC(),
		Lines:             lines,
		Currency:          currency,
		PreviousEntryHash: previousHash,
		CreatedAt:         time.Now().UTC(),
	}

	if err := entry.ValidateAndComputeTotals(); err != nil {
		return nil, err
	}

	entry.MerkleRoot = entry.computeMerkleRoot()
	return entry, nil
}

// ValidateAndComputeTotals enforces double-entry balance: Sum(Debits) == Sum(Credits).
func (j *JournalEntryAggregate) ValidateAndComputeTotals() error {
	var totalDebit, totalCredit int64
	currencies := make(map[string]bool)

	for idx, line := range j.Lines {
		if strings.TrimSpace(line.AccountID) == "" {
			return fmt.Errorf("%w at index %d", ErrLineAccountMissing, idx)
		}
		if line.Amount <= 0 {
			return fmt.Errorf("%w at index %d (got %d)", ErrInvalidLineAmount, idx, line.Amount)
		}
		currencies[line.Currency] = true

		switch line.Direction {
		case DirectionDebit:
			totalDebit += line.Amount
		case DirectionCredit:
			totalCredit += line.Amount
		default:
			return fmt.Errorf("invalid direction %s at line index %d", line.Direction, idx)
		}
	}

	j.TotalDebit = totalDebit
	j.TotalCredit = totalCredit
	j.IsMultiCurrency = len(currencies) > 1

	if !j.IsMultiCurrency {
		if totalDebit != totalCredit {
			return fmt.Errorf(
				"%w: total debits (%d) do not equal total credits (%d), imbalance = %d",
				ErrUnbalancedEntry,
				totalDebit,
				totalCredit,
				totalDebit-totalCredit,
			)
		}
	} else {
		// Multi-currency validation: require BaseAmount on each line and ensure base amounts balance
		var baseDebit, baseCredit int64
		for idx, line := range j.Lines {
			if line.BaseAmount <= 0 {
				return fmt.Errorf("multi-currency entry line %d missing valid positive BaseAmount", idx)
			}
			if line.Direction == DirectionDebit {
				baseDebit += line.BaseAmount
			} else {
				baseCredit += line.BaseAmount
			}
		}
		if baseDebit != baseCredit {
			return fmt.Errorf(
				"%w: multi-currency base debits (%d) != base credits (%d)",
				ErrUnbalancedEntry,
				baseDebit,
				baseCredit,
			)
		}
	}

	return nil
}

// Post marks the journal entry as permanently posted.
func (j *JournalEntryAggregate) Post() error {
	if j.Status == JournalStatusPosted {
		return ErrAlreadyPosted
	}
	if j.Status == JournalStatusReversed {
		return ErrAlreadyReversed
	}
	if err := j.ValidateAndComputeTotals(); err != nil {
		return err
	}

	now := time.Now().UTC()
	j.Status = JournalStatusPosted
	j.PostedAt = now
	j.PostingDate = now
	j.MerkleRoot = j.computeMerkleRoot()
	return nil
}

// CreateReversal generates a counter-entry that inverts all debits and credits.
func (j *JournalEntryAggregate) CreateReversal(reversalEntryID, reason string) (*JournalEntryAggregate, error) {
	if j.Status != JournalStatusPosted {
		return nil, ErrCannotReverseUnposted
	}
	if j.ReversedByEntryID != "" {
		return nil, ErrAlreadyReversed
	}

	reversalLines := make([]EntryLine, len(j.Lines))
	for i, line := range j.Lines {
		invertedDirection := DirectionCredit
		if line.Direction == DirectionCredit {
			invertedDirection = DirectionDebit
		}
		reversalLines[i] = EntryLine{
			LineID:       fmt.Sprintf("%s-rev-%d", reversalEntryID, i+1),
			AccountID:    line.AccountID,
			Direction:    invertedDirection,
			Amount:       line.Amount,
			Currency:     line.Currency,
			ExchangeRate: line.ExchangeRate,
			BaseAmount:   line.BaseAmount,
			Description:  fmt.Sprintf("Reversal of line %s: %s", line.LineID, line.Description),
			Metadata: map[string]any{
				"original_line_id": line.LineID,
				"reversal_reason":  reason,
			},
		}
	}

	rev, err := NewJournalEntry(
		reversalEntryID,
		j.TenantID,
		fmt.Sprintf("rev-%s", j.IdempotencyKey),
		fmt.Sprintf("REV-%s", j.ReferenceID),
		fmt.Sprintf("Reversal: %s (Reason: %s)", j.Description, reason),
		j.Currency,
		time.Now().UTC(),
		reversalLines,
		j.MerkleRoot,
	)
	if err != nil {
		return nil, err
	}

	rev.ReversalOfEntryID = j.EntryID
	j.ReversedByEntryID = reversalEntryID
	j.Status = JournalStatusReversed

	return rev, nil
}

// computeMerkleRoot builds a Merkle tree root hash from all entry lines and header metadata.
func (j *JournalEntryAggregate) computeMerkleRoot() string {
	if len(j.Lines) == 0 {
		return ""
	}

	var hashes [][]byte
	for _, l := range j.Lines {
		lineHex := l.ComputeLineHash()
		decoded, _ := hex.DecodeString(lineHex)
		hashes = append(hashes, decoded)
	}

	// Pairwise hashing up to root
	for len(hashes) > 1 {
		var nextLevel [][]byte
		for i := 0; i < len(hashes); i += 2 {
			if i+1 < len(hashes) {
				combined := append(hashes[i], hashes[i+1]...)
				h := sha256.Sum256(combined)
				nextLevel = append(nextLevel, h[:])
			} else {
				// Duplicate last odd node
				combined := append(hashes[i], hashes[i]...)
				h := sha256.Sum256(combined)
				nextLevel = append(nextLevel, h[:])
			}
		}
		hashes = nextLevel
	}

	// Blend with header metadata and previous entry hash
	headerPayload := fmt.Sprintf(
		"%s|%s|%s|%s|%d|%d|%s|%s",
		j.EntryID,
		j.TenantID,
		j.Status,
		hex.EncodeToString(hashes[0]),
		j.TotalDebit,
		j.TotalCredit,
		j.PreviousEntryHash,
		j.ValueDate.Format(time.RFC3339),
	)
	finalHash := sha256.Sum256([]byte(headerPayload))
	return hex.EncodeToString(finalHash[:])
}
