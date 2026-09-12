package messaging

import (
	"context"
	"fmt"
	"math"
	"math/rand"
	"sync"
	"time"
)

// DeadLetterEntry represents a poisoned or repeatedly failed message routed to the DLQ.
type DeadLetterEntry struct {
	DLQID         string              `json:"dlq_id"`
	OriginalTopic string              `json:"original_topic"`
	OriginalEvent LedgerEventEnvelope `json:"original_event"`
	FailureReason string              `json:"failure_reason"`
	AttemptCount  int                 `json:"attempt_count"`
	FirstFailedAt time.Time           `json:"first_failed_at"`
	LastFailedAt  time.Time           `json:"last_failed_at"`
	IsReplayed    bool                `json:"is_replayed"`
	ReplayedAt    time.Time           `json:"replayed_at,omitempty"`
}

// FullJitterBackoff computes exponential backoff with full jitter to eliminate thundering herds.
// Formula: Sleep = rand(0, min(MaxWait, BaseWait * 2^attempt))
func FullJitterBackoff(attempt int, baseWait, maxWait time.Duration) time.Duration {
	if attempt < 0 {
		attempt = 0
	}
	multiplier := math.Pow(2, float64(attempt))
	rawWait := float64(baseWait) * multiplier
	maxWaitFloat := float64(maxWait)

	capped := rawWait
	if capped > maxWaitFloat {
		capped = maxWaitFloat
	}

	if capped <= 0 {
		return baseWait
	}

	// Full jitter random interval [0, capped]
	jittered := rand.Float64() * capped
	return time.Duration(jittered)
}

// DeadLetterQueueManager handles capturing, inspecting, and replaying dead-lettered messages.
type DeadLetterQueueManager struct {
	mu        sync.RWMutex
	entries   map[string]*DeadLetterEntry
	publisher EventPublisher
}

func NewDeadLetterQueueManager(publisher EventPublisher) *DeadLetterQueueManager {
	return &DeadLetterQueueManager{
		entries:   make(map[string]*DeadLetterEntry),
		publisher: publisher,
	}
}

// EnqueueDLQ captures a failed message into the dead letter store.
func (d *DeadLetterQueueManager) EnqueueDLQ(
	topic string,
	event LedgerEventEnvelope,
	reason string,
	attemptCount int,
) *DeadLetterEntry {
	d.mu.Lock()
	defer d.mu.Unlock()

	dlqID := fmt.Sprintf("dlq_%s_%d", event.EventID, time.Now().UnixNano())
	now := time.Now().UTC()

	entry := &DeadLetterEntry{
		DLQID:         dlqID,
		OriginalTopic: topic,
		OriginalEvent: event,
		FailureReason: reason,
		AttemptCount:  attemptCount,
		FirstFailedAt: now,
		LastFailedAt:  now,
		IsReplayed:    false,
	}

	d.entries[dlqID] = entry
	return entry
}

// ListDLQ retrieves unresolved dead-letter items.
func (d *DeadLetterQueueManager) ListDLQ(limit int) []*DeadLetterEntry {
	d.mu.RLock()
	defer d.mu.RUnlock()

	var results []*DeadLetterEntry
	for _, e := range d.entries {
		if !e.IsReplayed {
			results = append(results, e)
			if len(results) >= limit {
				break
			}
		}
	}
	return results
}

// ReplayMessage re-publishes a dead letter entry to the original topic for reprocessing.
func (d *DeadLetterQueueManager) ReplayMessage(ctx context.Context, dlqID string) error {
	d.mu.Lock()
	defer d.mu.Unlock()

	entry, exists := d.entries[dlqID]
	if !exists {
		return fmt.Errorf("dlq entry %s not found", dlqID)
	}
	if entry.IsReplayed {
		return fmt.Errorf("dlq entry %s has already been replayed", dlqID)
	}

	// Replay via publisher
	err := d.publisher.Publish(ctx, entry.OriginalTopic, entry.OriginalEvent.AggregateID, entry.OriginalEvent)
	if err != nil {
		return fmt.Errorf("failed replaying dlq message: %w", err)
	}

	entry.IsReplayed = true
	entry.ReplayedAt = time.Now().UTC()
	return nil
}
