package com.elmos.logistics.domain.model.inventory;

/**
 * State lifecycle of an individual item or stock reservation unit.
 */
public enum AllocationStatus {
    AVAILABLE,
    RESERVED,
    ALLOCATED_TO_WAVE,
    PICKED,
    STAGED_FOR_PACKING,
    PACKED,
    LOADED_FOR_DISPATCH,
    SHIPPED,
    QUARANTINED,
    DAMAGED_WRITE_OFF
}
