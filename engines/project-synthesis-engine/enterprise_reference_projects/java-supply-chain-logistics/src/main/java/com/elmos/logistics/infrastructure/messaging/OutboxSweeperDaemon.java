package com.elmos.logistics.infrastructure.messaging;

import com.elmos.logistics.domain.model.outbox.OutboxEvent;
import com.elmos.logistics.domain.repository.OutboxRepository;

import java.time.Instant;
import java.util.List;
import java.util.Objects;

/**
 * Sweeper daemon that processes pending outbox entries, publishes to message broker,
 * and tracks exponential backoff retries and dead-letter queue escalation.
 */
public class OutboxSweeperDaemon {
    private final OutboxRepository outboxRepository;
    private final OutboxEventPublisher publisher;
    private final int batchSize;
    private final int maxRetries;

    public OutboxSweeperDaemon(OutboxRepository outboxRepository,
                               OutboxEventPublisher publisher,
                               int batchSize,
                               int maxRetries) {
        this.outboxRepository = Objects.requireNonNull(outboxRepository, "outboxRepository must not be null");
        this.publisher = Objects.requireNonNull(publisher, "publisher must not be null");
        this.batchSize = batchSize;
        this.maxRetries = maxRetries;
    }

    /**
     * Executes a single sweep cycle.
     * Returns the count of successfully published events.
     */
    public int sweepOnce() {
        Instant now = Instant.now();
        List<OutboxEvent> pending = outboxRepository.findPendingEvents(now, batchSize);

        int publishedCount = 0;
        for (OutboxEvent event : pending) {
            try {
                publisher.publish(event);
                event.markPublished();
                outboxRepository.save(event);
                publishedCount++;
            } catch (Exception ex) {
                event.recordFailure(ex.getMessage(), maxRetries);
                outboxRepository.save(event);
            }
        }

        return publishedCount;
    }
}
