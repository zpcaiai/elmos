package test

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/infrastructure/messaging"
)

func TestFullJitterBackoffBounds(t *testing.T) {
	baseWait := 50 * time.Millisecond
	maxWait := 1000 * time.Millisecond

	for attempt := 0; attempt < 10; attempt++ {
		wait := messaging.FullJitterBackoff(attempt, baseWait, maxWait)
		if wait < 0 {
			t.Errorf("wait time must never be negative, got %v", wait)
		}
		if wait > maxWait {
			t.Errorf("wait time %v exceeded maxWait %v at attempt %d", wait, maxWait, attempt)
		}
	}
}

func TestResilientConsumerRetryAndDLQDiversion(t *testing.T) {
	eventBus := messaging.NewInMemoryEventBus()
	dlqMgr := messaging.NewDeadLetterQueueManager(eventBus)
	dedup := messaging.NewMemoryDeduplicationStore()

	consumer := messaging.NewResilientMessageConsumer(
		dedup,
		dlqMgr,
		2, // Max 2 retries (3 attempts total)
		10*time.Millisecond,
		50*time.Millisecond,
	)

	ctx := context.Background()
	event := messaging.LedgerEventEnvelope{
		EventID:     "evt_poison_pill_01",
		TenantID:    "tenant_dlq_01",
		EventType:   "TRANSACTION_POSTED",
		AggregateID: "acc_999",
		Timestamp:   time.Now().UTC(),
	}

	var executionAttempts int32
	poisonError := errors.New("simulated transient database deadlock")

	err := consumer.Consume(ctx, "ledger.events", event, func(c context.Context, e messaging.LedgerEventEnvelope) error {
		atomic.AddInt32(&executionAttempts, 1)
		return poisonError
	})

	if err == nil {
		t.Fatalf("expected error after retry exhaustion, got nil")
	}

	if atomic.LoadInt32(&executionAttempts) != 3 { // 1 initial + 2 retries
		t.Errorf("expected 3 total execution attempts, got %d", executionAttempts)
	}

	// Verify message in DLQ
	dlqItems := dlqMgr.ListDLQ(10)
	if len(dlqItems) != 1 {
		t.Fatalf("expected 1 item in DLQ, got %d", len(dlqItems))
	}

	dlqEntry := dlqItems[0]
	if dlqEntry.OriginalEvent.EventID != "evt_poison_pill_01" {
		t.Errorf("expected dlq event ID evt_poison_pill_01, got %s", dlqEntry.OriginalEvent.EventID)
	}
	if dlqEntry.IsReplayed {
		t.Errorf("newly queued dlq item should not be replayed yet")
	}

	// Test replay
	err = dlqMgr.ReplayMessage(ctx, dlqEntry.DLQID)
	if err != nil {
		t.Fatalf("failed replaying message: %v", err)
	}

	if !dlqEntry.IsReplayed {
		t.Errorf("expected dlq item to be marked as replayed")
	}

	published := eventBus.GetPublished("ledger.events")
	if len(published) != 1 {
		t.Errorf("expected replayed message to be re-published to event bus, got %d events", len(published))
	}
}
