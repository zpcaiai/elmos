package repository

import (
	"context"
	"errors"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
)

var (
	ErrAccountNotFound = errors.New("account not found")
	ErrEntryNotFound   = errors.New("journal entry not found")
	ErrLockAcquisition = errors.New("failed to acquire distributed lock")
	ErrLockLost        = errors.New("distributed lock lease expired or lost")
)

// LockHandle represents an active distributed lease with a monotonic fencing token.
type LockHandle interface {
	Resource() string
	Token() string
	FencingToken() int64
	ExpiresAt() time.Time
}

// AccountRepository manages persistence for Account aggregates.
type AccountRepository interface {
	FindByID(ctx context.Context, tenantID, accountID string) (*model.AccountAggregate, error)
	FindByIDForUpdate(ctx context.Context, tenantID, accountID string) (*model.AccountAggregate, error)
	Save(ctx context.Context, account *model.AccountAggregate) error
	ListByTenant(ctx context.Context, tenantID string, limit, offset int) ([]*model.AccountAggregate, error)
	GetTrialBalance(ctx context.Context, tenantID string) (map[string]int64, error)
}

// JournalRepository manages append-only persistence of double-entry journal records.
type JournalRepository interface {
	SaveEntry(ctx context.Context, entry *model.JournalEntryAggregate) error
	FindEntryByID(ctx context.Context, tenantID, entryID string) (*model.JournalEntryAggregate, error)
	FindLatestEntry(ctx context.Context, tenantID string) (*model.JournalEntryAggregate, error)
	ListEntriesByAccount(ctx context.Context, tenantID, accountID string, from, to time.Time, limit, offset int) ([]*model.JournalEntryAggregate, error)
	GetEntryHashesForPeriod(ctx context.Context, tenantID string, from, to time.Time) ([]string, error)
}

// IdempotencyRepository guarantees once-and-only-once semantics for financial requests.
type IdempotencyRepository interface {
	Get(ctx context.Context, tenantID, key string) (*model.IdempotencyRecord, error)
	Save(ctx context.Context, record *model.IdempotencyRecord) error
}

// DistributedLockManager coordinates distributed synchronization across ledger instances.
type DistributedLockManager interface {
	AcquireLock(ctx context.Context, resourceKey string, ttl time.Duration) (LockHandle, error)
	ReleaseLock(ctx context.Context, handle LockHandle) error
	ExtendLock(ctx context.Context, handle LockHandle, additionalTTL time.Duration) error
}
