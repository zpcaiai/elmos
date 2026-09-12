package com.elmos.logistics.domain.model.transfer;

/**
 * Lifecycle states of an inter-warehouse stock transfer order.
 */
public enum TransferStatus {
    DRAFT,
    SUBMITTED_FOR_APPROVAL,
    APPROVED,
    PICKING_AND_PACKING,
    DISPATCHED_IN_TRANSIT,
    ARRIVED_AT_DESTINATION,
    INSPECTING_AND_RECEIVING,
    RECONCILED_SUCCESS,
    DISCREPANCY_FLAGGED,
    CANCELLED
}
