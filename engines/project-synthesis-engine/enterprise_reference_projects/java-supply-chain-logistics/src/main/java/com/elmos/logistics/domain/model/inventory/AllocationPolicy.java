package com.elmos.logistics.domain.model.inventory;

/**
 * Strategy policy for selecting inventory lots and stock units.
 */
public enum AllocationPolicy {
    /**
     * First-In, First-Out: Allocates older received inventory first.
     */
    FIFO,

    /**
     * First-Expired, First-Out: Mandatory for pharmaceuticals, perishables, and chemical agents.
     */
    FEFO,

    /**
     * Allocates units physically closest to the packing/shipping bays to minimize travel.
     */
    PROXIMITY_OPTIMAL,

    /**
     * Prefers bins that will be completely emptied to minimize aisle fragmentation.
     */
    CLEAN_SWEEP_BIN
}
