package com.elmos.logistics.domain.model.dispatch;

/**
 * Real-time status of carrier delivery consignment.
 */
public enum DeliveryStatus {
    MANIFESTED,
    TENDERED_TO_CARRIER,
    IN_TRANSIT,
    OUT_FOR_DELIVERY,
    DELIVERED,
    DELIVERY_EXCEPTION,
    RETURNED_TO_ORIGIN
}
