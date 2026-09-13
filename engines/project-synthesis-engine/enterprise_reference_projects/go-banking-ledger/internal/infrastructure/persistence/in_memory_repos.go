package persistence

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
)

// InMemoryAccountRepository provides concurrent-safe in-memory persistence for accounts.
type InMemoryAccountRepository struct {
	mu       sync.RWMutex
	accounts map[string]*model.AccountAggregate // key: tenantID:accountID
}

func NewInMemoryAccountRepository() *InMemoryAccountRepository {
	return &InMemoryAccountRepository{
		accounts: make(map[string]*model.AccountAggregate),
	}
}

func makeKey(tenantID, accountID string) string {
	return fmt.Sprintf("%s:%s", tenantID, accountID)
}

func (r *InMemoryAccountRepository) FindByID(ctx context.Context, tenantID, accountID string) (*model.AccountAggregate, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	key := makeKey(tenantID, accountID)
	acc, found := r.accounts[key]
	if !found {
		return nil, fmt.Errorf("%w: %s", repository.ErrAccountNotFound, accountID)
	}
	return acc, nil
}

func (r *InMemoryAccountRepository) FindByIDForUpdate(ctx context.Context, tenantID, accountID string) (*model.AccountAggregate, error) {
	// In-memory simulates row locking by returning the direct pointer
	return r.FindByID(ctx, tenantID, accountID)
}

func (r *InMemoryAccountRepository) Save(ctx context.Context, account *model.AccountAggregate) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := makeKey(account.TenantID, account.AccountID)
	r.accounts[key] = account
	return nil
}

func (r *InMemoryAccountRepository) ListByTenant(ctx context.Context, tenantID string, limit, offset int) ([]*model.AccountAggregate, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	var result []*model.AccountAggregate
	for _, acc := range r.accounts {
		if acc.TenantID == tenantID {
			result = append(result, acc)
		}
	}

	if offset >= len(result) {
		return nil, nil
	}
	end := offset + limit
	if end > len(result) {
		end = len(result)
	}
	return result[offset:end], nil
}

func (r *InMemoryAccountRepository) GetTrialBalance(ctx context.Context, tenantID string) (map[string]int64, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	res := make(map[string]int64)
	for _, acc := range r.accounts {
		if acc.TenantID == tenantID {
			res[acc.AccountID] = acc.PostedBalance
		}
	}
	return res, nil
}

// InMemoryJournalRepository provides concurrent-safe in-memory persistence for journal entries.
type InMemoryJournalRepository struct {
	mu      sync.RWMutex
	entries map[string]*model.JournalEntryAggregate // key: tenantID:entryID
	latest  map[string]*model.JournalEntryAggregate // key: tenantID -> latest
	history map[string][]*model.JournalEntryAggregate // key: tenantID:accountID
}

func NewInMemoryJournalRepository() *InMemoryJournalRepository {
	return &InMemoryJournalRepository{
		entries: make(map[string]*model.JournalEntryAggregate),
		latest:  make(map[string]*model.JournalEntryAggregate),
		history: make(map[string][]*model.JournalEntryAggregate),
	}
}

func (r *InMemoryJournalRepository) SaveEntry(ctx context.Context, entry *model.JournalEntryAggregate) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := makeKey(entry.TenantID, entry.EntryID)
	r.entries[key] = entry
	r.latest[entry.TenantID] = entry

	for _, l := range entry.Lines {
		accKey := makeKey(entry.TenantID, l.AccountID)
		r.history[accKey] = append(r.history[accKey], entry)
	}

	return nil
}

func (r *InMemoryJournalRepository) FindEntryByID(ctx context.Context, tenantID, entryID string) (*model.JournalEntryAggregate, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	key := makeKey(tenantID, entryID)
	entry, found := r.entries[key]
	if !found {
		return nil, fmt.Errorf("%w: %s", repository.ErrEntryNotFound, entryID)
	}
	return entry, nil
}

func (r *InMemoryJournalRepository) FindLatestEntry(ctx context.Context, tenantID string) (*model.JournalEntryAggregate, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	latest, found := r.latest[tenantID]
	if !found {
		return nil, nil
	}
	return latest, nil
}

func (r *InMemoryJournalRepository) ListEntriesByAccount(
	ctx context.Context,
	tenantID, accountID string,
	from, to time.Time,
	limit, offset int,
) ([]*model.JournalEntryAggregate, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	accKey := makeKey(tenantID, accountID)
	all := r.history[accKey]
	var filtered []*model.JournalEntryAggregate

	for _, e := range all {
		if !e.PostingDate.Before(from) && !e.PostingDate.After(to) {
			filtered = append(filtered, e)
		}
	}

	if offset >= len(filtered) {
		return nil, nil
	}
	end := offset + limit
	if end > len(filtered) {
		end = len(filtered)
	}
	return filtered[offset:end], nil
}

func (r *InMemoryJournalRepository) GetEntryHashesForPeriod(
	ctx context.Context,
	tenantID string,
	from, to time.Time,
) ([]string, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	var hashes []string
	for _, e := range r.entries {
		if e.TenantID == tenantID {
			if !e.PostingDate.Before(from) && !e.PostingDate.After(to) {
				if e.MerkleRoot != "" {
					hashes = append(hashes, e.MerkleRoot)
				}
			}
		}
	}
	return hashes, nil
}

// InMemoryIdempotencyRepository stores idempotency keys in memory.
type InMemoryIdempotencyRepository struct {
	mu      sync.RWMutex
	records map[string]*model.IdempotencyRecord
}

func NewInMemoryIdempotencyRepository() *InMemoryIdempotencyRepository {
	return &InMemoryIdempotencyRepository{
		records: make(map[string]*model.IdempotencyRecord),
	}
}

func (r *InMemoryIdempotencyRepository) Get(ctx context.Context, tenantID, key string) (*model.IdempotencyRecord, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	k := makeKey(tenantID, key)
	rec, found := r.records[k]
	if !found {
		return nil, nil
	}
	return rec, nil
}

func (r *InMemoryIdempotencyRepository) Save(ctx context.Context, record *model.IdempotencyRecord) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	k := makeKey(record.TenantID, record.Key)
	r.records[k] = record
	return nil
}

// MemoryLockHandle implements LockHandle with fencing token.
type MemoryLockHandle struct {
	resourceKey string
	token       string
	fencingSeq  int64
	expiry      time.Time
}

func (h *MemoryLockHandle) Resource() string      { return h.resourceKey }
func (h *MemoryLockHandle) Token() string         { return h.token }
func (h *MemoryLockHandle) FencingToken() int64   { return h.fencingSeq }
func (h *MemoryLockHandle) ExpiresAt() time.Time  { return h.expiry }

// InMemoryLockManager simulates a distributed lock with monotonically increasing fencing tokens.
type InMemoryLockManager struct {
	mu          sync.Mutex
	locks       map[string]*MemoryLockHandle
	fencingToken int64
}

func NewInMemoryLockManager() *InMemoryLockManager {
	return &InMemoryLockManager{
		locks: make(map[string]*MemoryLockHandle),
	}
}

func (m *InMemoryLockManager) AcquireLock(ctx context.Context, resourceKey string, ttl time.Duration) (repository.LockHandle, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	now := time.Now().UTC()
	if existing, exists := m.locks[resourceKey]; exists {
		if now.Before(existing.expiry) {
			return nil, fmt.Errorf("%w: resource %s currently held", repository.ErrLockAcquisition, resourceKey)
		}
	}

	seq := atomic.AddInt64(&m.fencingToken, 1)
	handle := &MemoryLockHandle{
		resourceKey: resourceKey,
		token:       fmt.Sprintf("token_%d", seq),
		fencingSeq:  seq,
		expiry:      now.Add(ttl),
	}
	m.locks[resourceKey] = handle
	return handle, nil
}

func (m *InMemoryLockManager) ReleaseLock(ctx context.Context, handle repository.LockHandle) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if cur, exists := m.locks[handle.Resource()]; exists {
		if cur.Token() == handle.Token() {
			delete(m.locks, handle.Resource())
			return nil
		}
	}
	return nil
}

func (m *InMemoryLockManager) ExtendLock(ctx context.Context, handle repository.LockHandle, additionalTTL time.Duration) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	cur, exists := m.locks[handle.Resource()]
	if !exists || cur.Token() != handle.Token() {
		return repository.ErrLockLost
	}
	cur.expiry = time.Now().UTC().Add(additionalTTL)
	return nil
}
