package com.elmos.logistics.domain.model.wave;

/**
 * Status lifecycle of a wave picking batch.
 */
public enum WaveStatus {
    PLANNING,
    OPTIMIZING_ROUTES,
    RELEASED_TO_FLOOR,
    IN_PROGRESS,
    PICKING_COMPLETE,
    CONSOLIDATED_AT_PACKING,
    CANCELLED
}
