package com.elmos.logistics.domain.model.warehouse;

/**
 * Operational state of an individual storage location (bin) in a warehouse.
 */
public enum BinStatus {
    AVAILABLE,
    PARTIALLY_OCCUPIED,
    FULL,
    RESERVED_FOR_PUTAWAY,
    BLOCKED_FOR_MAINTENANCE,
    BLOCKED_FOR_CYCLE_COUNT,
    QUARANTINED
}
