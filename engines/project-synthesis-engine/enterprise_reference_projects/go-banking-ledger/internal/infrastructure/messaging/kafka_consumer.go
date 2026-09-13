package messaging

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// ConsumerStats tracks runtime telemetry for message consumption.
type ConsumerStats struct {
	TotalReceived  int64     `json:"total_received"`
	TotalProcessed int64     `json:"total_processed"`
	TotalFailed    int64     `json:"total_failed"`
	TotalDLQ       int64     `json:"total_dlq"`
	LastHeartbeat  time.Time `json:"last_heartbeat"`
}

// ConsumerWorkerPool manages a group of concurrent workers consuming events from topics.
type ConsumerWorkerPool struct {
	concurrency   int
	topics        []string
	consumer      *ResilientMessageConsumer
	inboundChan   chan LedgerEventEnvelope
	stopChan      chan struct{}
	wg            sync.WaitGroup
	isRunning     atomic.Bool
	stats         ConsumerStats
}

func NewConsumerWorkerPool(
	concurrency int,
	topics []string,
	consumer *ResilientMessageConsumer,
) *ConsumerWorkerPool {
	return &ConsumerWorkerPool{
		concurrency: concurrency,
		topics:      topics,
		consumer:    consumer,
		inboundChan: make(chan LedgerEventEnvelope, 1000),
		stopChan:    make(chan struct{}),
	}
}

// Start spawns the concurrent worker pool.
func (p *ConsumerWorkerPool) Start(
	ctx context.Context,
	handler func(ctx context.Context, event LedgerEventEnvelope) error,
) {
	if p.isRunning.Swap(true) {
		return
	}

	for i := 0; i < p.concurrency; i++ {
		p.wg.Add(1)
		go func(workerID int) {
			defer p.wg.Done()
			for {
				select {
				case <-p.stopChan:
					return
				case <-ctx.Done():
					return
				case event, ok := <-p.inboundChan:
					if !ok {
						return
					}
					atomic.AddInt64(&p.stats.TotalReceived, 1)

					err := p.consumer.Consume(ctx, "ledger.events", event, handler)
					if err != nil {
						atomic.AddInt64(&p.stats.TotalFailed, 1)
					} else {
						atomic.AddInt64(&p.stats.TotalProcessed, 1)
					}
				}
			}
		}(i)
	}
}

// Enqueue submits an event into the worker pool channel.
func (p *ConsumerWorkerPool) Enqueue(event LedgerEventEnvelope) error {
	if !p.isRunning.Load() {
		return fmt.Errorf("consumer worker pool is not running")
	}
	select {
	case p.inboundChan <- event:
		return nil
	default:
		return fmt.Errorf("consumer buffer is full, backpressure shedding")
	}
}

// Stop gracefully drains and shuts down the workers.
func (p *ConsumerWorkerPool) Stop() {
	if !p.isRunning.Swap(false) {
		return
	}
	close(p.stopChan)
	p.wg.Wait()
}

// GetStats returns current throughput metrics.
func (p *ConsumerWorkerPool) GetStats() ConsumerStats {
	return ConsumerStats{
		TotalReceived:  atomic.LoadInt64(&p.stats.TotalReceived),
		TotalProcessed: atomic.LoadInt64(&p.stats.TotalProcessed),
		TotalFailed:    atomic.LoadInt64(&p.stats.TotalFailed),
		TotalDLQ:       atomic.LoadInt64(&p.stats.TotalDLQ),
		LastHeartbeat:  time.Now().UTC(),
	}
}
