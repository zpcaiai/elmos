package messaging

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sync"
	"time"

	"github.com/google/uuid"
)

// LedgerEventEnvelope standardizes financial events published over Kafka/event streams.
type LedgerEventEnvelope struct {
	EventID        string         `json:"event_id"`
	TenantID       string         `json:"tenant_id"`
	EventType      string         `json:"event_type"`
	AggregateType  string         `json:"aggregate_type"`
	AggregateID    string         `json:"aggregate_id"`
	SequenceNumber int64          `json:"sequence_number"`
	Timestamp      time.Time      `json:"timestamp"`
	Payload        map[string]any `json:"payload"`
	PayloadHash    string         `json:"payload_hash"`
	TraceID        string         `json:"trace_id"`
}

// EventPublisher defines the contract for emitting ledger events.
type EventPublisher interface {
	Publish(ctx context.Context, topic string, partitionKey string, event LedgerEventEnvelope) error
	PublishBatch(ctx context.Context, topic string, events []LedgerEventEnvelope) error
}

// InMemoryEventBus implements EventPublisher and stores emitted events for testing and outbox forwarding.
type InMemoryEventBus struct {
	mu        sync.RWMutex
	messages  map[string][]LedgerEventEnvelope // topic -> events
	listeners map[string][]func(event LedgerEventEnvelope) error
}

func NewInMemoryEventBus() *InMemoryEventBus {
	return &InMemoryEventBus{
		messages:  make(map[string][]LedgerEventEnvelope),
		listeners: make(map[string][]func(event LedgerEventEnvelope) error),
	}
}

func (b *InMemoryEventBus) Publish(ctx context.Context, topic string, partitionKey string, event LedgerEventEnvelope) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	if event.EventID == "" {
		event.EventID = uuid.New().String()
	}
	if event.Timestamp.IsZero() {
		event.Timestamp = time.Now().UTC()
	}

	payloadBytes, _ := json.Marshal(event.Payload)
	h := sha256.Sum256(payloadBytes)
	event.PayloadHash = hex.EncodeToString(h[:])

	b.messages[topic] = append(b.messages[topic], event)

	// Trigger registered listeners
	for _, fn := range b.listeners[topic] {
		go func(f func(LedgerEventEnvelope) error, e LedgerEventEnvelope) {
			_ = f(e)
		}(fn, event)
	}

	return nil
}

func (b *InMemoryEventBus) PublishBatch(ctx context.Context, topic string, events []LedgerEventEnvelope) error {
	for _, e := range events {
		if err := b.Publish(ctx, topic, e.AggregateID, e); err != nil {
			return err
		}
	}
	return nil
}

func (b *InMemoryEventBus) Subscribe(topic string, handler func(event LedgerEventEnvelope) error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.listeners[topic] = append(b.listeners[topic], handler)
}

func (b *InMemoryEventBus) GetPublished(topic string) []LedgerEventEnvelope {
	b.mu.RLock()
	defer b.mu.RUnlock()
	copied := make([]LedgerEventEnvelope, len(b.messages[topic]))
	copy(copied, b.messages[topic])
	return copied
}

// OutboxRecord represents an unpublished event queued inside the database transaction.
type OutboxRecord struct {
	ID            string    `json:"id"`
	TenantID      string    `json:"tenant_id"`
	Topic         string    `json:"topic"`
	PartitionKey  string    `json:"partition_key"`
	PayloadJSON   string    `json:"payload_json"`
	Status        string    `json:"status"` // PENDING, PUBLISHED, FAILED
	RetryCount    int       `json:"retry_count"`
	CreatedAt     time.Time `json:"created_at"`
	PublishedAt   time.Time `json:"published_at,omitempty"`
	LastError     string    `json:"last_error,omitempty"`
}

// OutboxSweeper periodically scans and dispatches pending events to the streaming broker.
type OutboxSweeper struct {
	publisher EventPublisher
	records   []*OutboxRecord
	mu        sync.Mutex
}

func NewOutboxSweeper(pub EventPublisher) *OutboxSweeper {
	return &OutboxSweeper{
		publisher: pub,
		records:   make([]*OutboxRecord, 0),
	}
}

func (s *OutboxSweeper) Enqueue(tenantID, topic, partitionKey string, payload map[string]any) *OutboxRecord {
	s.mu.Lock()
	defer s.mu.Unlock()

	payloadBytes, _ := json.Marshal(payload)
	rec := &OutboxRecord{
		ID:           uuid.New().String(),
		TenantID:     tenantID,
		Topic:        topic,
		PartitionKey: partitionKey,
		PayloadJSON:  string(payloadBytes),
		Status:       "PENDING",
		CreatedAt:    time.Now().UTC(),
	}
	s.records = append(s.records, rec)
	return rec
}

func (s *OutboxSweeper) Sweep(ctx context.Context) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	count := 0
	for _, rec := range s.records {
		if rec.Status == "PENDING" || (rec.Status == "FAILED" && rec.RetryCount < 5) {
			var payload map[string]any
			_ = json.Unmarshal([]byte(rec.PayloadJSON), &payload)

			env := LedgerEventEnvelope{
				EventID:       rec.ID,
				TenantID:      rec.TenantID,
				EventType:     "OUTBOX_DISPATCHED",
				AggregateID:   rec.PartitionKey,
				Timestamp:     time.Now().UTC(),
				Payload:       payload,
			}

			err := s.publisher.Publish(ctx, rec.Topic, rec.PartitionKey, env)
			if err != nil {
				rec.Status = "FAILED"
				rec.RetryCount++
				rec.LastError = err.Error()
			} else {
				rec.Status = "PUBLISHED"
				rec.PublishedAt = time.Now().UTC()
				count++
			}
		}
	}
	return count, nil
}
