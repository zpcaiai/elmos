package com.elmos.logistics.domain.model.outbox;

import java.time.Instant;
import java.util.Objects;

/**
 * Transactional outbox event guaranteeing reliable asynchronous message delivery without two-phase commits.
 */
public class OutboxEvent {
    private final String eventId;
    private final String tenantId;
    private final String aggregateType;
    private final String aggregateId;
    private final String eventType;
    private final String payloadJson;
    private final Instant createdAt;

    private OutboxStatus status;
    private int retryCount;
    private String lastError;
    private Instant nextAttemptAfter;
    private Instant publishedAt;

    public OutboxEvent(String eventId,
                       String tenantId,
                       String aggregateType,
                       String aggregateId,
                       String eventType,
                       String payloadJson) {
        this.eventId = Objects.requireNonNull(eventId, "eventId must not be null");
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId must not be null");
        this.aggregateType = Objects.requireNonNull(aggregateType, "aggregateType must not be null");
        this.aggregateId = Objects.requireNonNull(aggregateId, "aggregateId must not be null");
        this.eventType = Objects.requireNonNull(eventType, "eventType must not be null");
        this.payloadJson = Objects.requireNonNull(payloadJson, "payloadJson must not be null");
        this.createdAt = Instant.now();
        this.status = OutboxStatus.PENDING;
        this.retryCount = 0;
        this.nextAttemptAfter = this.createdAt;
    }

    public String getEventId() {
        return eventId;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getAggregateType() {
        return aggregateType;
    }

    public String getAggregateId() {
        return aggregateId;
    }

    public String getEventType() {
        return eventType;
    }

    public String getPayloadJson() {
        return payloadJson;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public OutboxStatus getStatus() {
        return status;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public String getLastError() {
        return lastError;
    }

    public Instant getNextAttemptAfter() {
        return nextAttemptAfter;
    }

    public Instant getPublishedAt() {
        return publishedAt;
    }

    public synchronized void markPublished() {
        this.status = OutboxStatus.PUBLISHED;
        this.publishedAt = Instant.now();
    }

    public synchronized void recordFailure(String errorMessage, int maxRetries) {
        this.retryCount++;
        this.lastError = errorMessage;

        if (this.retryCount >= maxRetries) {
            this.status = OutboxStatus.DEAD_LETTER;
        } else {
            this.status = OutboxStatus.FAILED_RETRYABLE;
            // Exponential backoff: 2^retryCount * 500ms
            long delayMs = (1L << retryCount) * 500L;
            this.nextAttemptAfter = Instant.now().plusMillis(delayMs);
        }
    }
}
