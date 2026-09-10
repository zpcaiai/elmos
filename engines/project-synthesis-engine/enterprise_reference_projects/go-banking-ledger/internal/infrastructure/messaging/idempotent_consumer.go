package messaging

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

var ErrMessageAlreadyProcessed = errors.New("event has already been successfully processed")

// DeduplicationStore keeps tracks of handled event IDs to enforce exactly-once semantics.
type DeduplicationStore interface {
	IsProcessed(ctx context.Context, tenantID, eventID string) (bool, error)
	MarkProcessed(ctx context.Context, tenantID, eventID string, ttl time.Duration) error
}

// MemoryDeduplicationStore implements DeduplicationStore using an in-memory map with TTL.
type MemoryDeduplicationStore struct {
	mu      sync.RWMutex
	records map[string]time.Time
}

func NewMemoryDeduplicationStore() *MemoryDeduplicationStore {
	return &MemoryDeduplicationStore{
		records: make(map[string]time.Time),
	}
}

func (s *MemoryDeduplicationStore) IsProcessed(ctx context.Context, tenantID, eventID string) (bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	k := fmt.Sprintf("%s:%s", tenantID, eventID)
	expiry, found := s.records[k]
	if !found {
		return false, nil
	}
	if time.Now().UTC().After(expiry) {
		return false, nil
	}
	return true, nil
}

func (s *MemoryDeduplicationStore) MarkProcessed(ctx context.Context, tenantID, eventID string, ttl time.Duration) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	k := fmt.Sprintf("%s:%s", tenantID, eventID)
	s.records[k] = time.Now().UTC().Add(ttl)
	return nil
}

// ResilientMessageConsumer wraps an event handler with deduplication, retry, and DLQ diversion.
type ResilientMessageConsumer struct {
	dedupStore DeduplicationStore
	dlqManager *DeadLetterQueueManager
	maxRetries int
	baseWait   time.Duration
	maxWait    time.Duration
}

func NewResilientMessageConsumer(
	dedup DeduplicationStore,
	dlq *DeadLetterQueueManager,
	maxRetries int,
	baseWait, maxWait time.Duration,
) *ResilientMessageConsumer {
	return &ResilientMessageConsumer{
		dedupStore: dedup,
		dlqManager: dlq,
		maxRetries: maxRetries,
		baseWait:   baseWait,
		maxWait:    maxWait,
	}
}

// Consume processes an event safely with idempotency and retry protection.
func (c *ResilientMessageConsumer) Consume(
	ctx context.Context,
	topic string,
	event LedgerEventEnvelope,
	handler func(ctx context.Context, event LedgerEventEnvelope) error,
) error {
	// 1. Check deduplication
	isProcessed, err := c.dedupStore.IsProcessed(ctx, event.TenantID, event.EventID)
	if err != nil {
		return fmt.Errorf("dedup check error: %w", err)
	}
	if isProcessed {
		return ErrMessageAlreadyProcessed
	}

	// 2. Execute with exponential backoff retry loop
	var lastErr error
	for attempt := 0; attempt <= c.maxRetries; attempt++ {
		err = handler(ctx, event)
		if err == nil {
			// Success: Mark processed for 7 days
			_ = c.dedupStore.MarkProcessed(ctx, event.TenantID, event.EventID, 7*24*time.Hour)
			return nil
		}

		lastErr = err
		if attempt < c.maxRetries {
			wait := FullJitterBackoff(attempt, c.baseWait, c.maxWait)
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(wait):
			}
		}
	}

	// 3. Exceeded max retries: divert to DLQ
	if c.dlqManager != nil {
		c.dlqManager.EnqueueDLQ(topic, event, lastErr.Error(), c.maxRetries+1)
	}

	return fmt.Errorf("message processing exhausted %d retries: %w", c.maxRetries, lastErr)
}
