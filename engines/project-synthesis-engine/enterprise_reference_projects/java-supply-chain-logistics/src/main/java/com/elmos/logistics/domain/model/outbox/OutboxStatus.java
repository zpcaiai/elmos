package com.elmos.logistics.domain.model.outbox;

/**
 * Status lifecycle of an outbox message.
 */
public enum OutboxStatus {
    PENDING,
    PUBLISHED,
    FAILED_RETRYABLE,
    DEAD_LETTER
}
