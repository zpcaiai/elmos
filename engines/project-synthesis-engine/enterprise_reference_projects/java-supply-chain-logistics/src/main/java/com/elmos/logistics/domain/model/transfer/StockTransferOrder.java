package com.elmos.logistics.domain.model.transfer;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * Aggregate root for inter-warehouse inventory rebalancing and stock transfer orders.
 */
public class StockTransferOrder {
    private final String transferOrderId;
    private final String tenantId;
    private final String sourceWarehouseId;
    private final String destinationWarehouseId;
    private final String orderNumber;
    private final Instant createdAt;
    private final List<TransferLineItem> lineItems;
    private final List<DiscrepancyReport> discrepancies;

    private TransferStatus status;
    private String carrierName;
    private String trackingNumber;
    private Instant approvedAt;
    private Instant dispatchedAt;
    private Instant receivedAt;

    public StockTransferOrder(String transferOrderId,
                              String tenantId,
                              String sourceWarehouseId,
                              String destinationWarehouseId,
                              String orderNumber) {
        if (sourceWarehouseId.equals(destinationWarehouseId)) {
            throw new IllegalArgumentException("Source and destination warehouse cannot be identical: " + sourceWarehouseId);
        }
        this.transferOrderId = Objects.requireNonNull(transferOrderId, "transferOrderId must not be null");
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId must not be null");
        this.sourceWarehouseId = Objects.requireNonNull(sourceWarehouseId, "sourceWarehouseId must not be null");
        this.destinationWarehouseId = Objects.requireNonNull(destinationWarehouseId, "destinationWarehouseId must not be null");
        this.orderNumber = Objects.requireNonNull(orderNumber, "orderNumber must not be null");
        this.createdAt = Instant.now();
        this.lineItems = new ArrayList<>();
        this.discrepancies = new ArrayList<>();
        this.status = TransferStatus.DRAFT;
    }

    public String getTransferOrderId() {
        return transferOrderId;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getSourceWarehouseId() {
        return sourceWarehouseId;
    }

    public String getDestinationWarehouseId() {
        return destinationWarehouseId;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public List<TransferLineItem> getLineItems() {
        return Collections.unmodifiableList(lineItems);
    }

    public List<DiscrepancyReport> getDiscrepancies() {
        return Collections.unmodifiableList(discrepancies);
    }

    public TransferStatus getStatus() {
        return status;
    }

    public String getCarrierName() {
        return carrierName;
    }

    public String getTrackingNumber() {
        return trackingNumber;
    }

    public Instant getApprovedAt() {
        return approvedAt;
    }

    public Instant getDispatchedAt() {
        return dispatchedAt;
    }

    public Instant getReceivedAt() {
        return receivedAt;
    }

    public void addLineItem(TransferLineItem item) {
        if (status != TransferStatus.DRAFT) {
            throw new IllegalStateException("Cannot add items to transfer order in status " + status);
        }
        this.lineItems.add(Objects.requireNonNull(item, "Transfer line item must not be null"));
    }

    public void submitForApproval() {
        if (this.status != TransferStatus.DRAFT) {
            throw new IllegalStateException("Only DRAFT orders can be submitted: " + status);
        }
        if (this.lineItems.isEmpty()) {
            throw new IllegalStateException("Cannot submit empty transfer order");
        }
        this.status = TransferStatus.SUBMITTED_FOR_APPROVAL;
    }

    public void approve() {
        if (this.status != TransferStatus.SUBMITTED_FOR_APPROVAL) {
            throw new IllegalStateException("Order must be SUBMITTED_FOR_APPROVAL before approving: " + status);
        }
        this.status = TransferStatus.APPROVED;
        this.approvedAt = Instant.now();
    }

    public void startPicking() {
        if (this.status != TransferStatus.APPROVED) {
            throw new IllegalStateException("Order must be APPROVED before picking: " + status);
        }
        this.status = TransferStatus.PICKING_AND_PACKING;
    }

    public void dispatch(String carrierName, String trackingNumber) {
        if (this.status != TransferStatus.PICKING_AND_PACKING) {
            throw new IllegalStateException("Order must be PACKED before dispatch: " + status);
        }
        this.carrierName = Objects.requireNonNull(carrierName, "carrierName must not be null");
        this.trackingNumber = Objects.requireNonNull(trackingNumber, "trackingNumber must not be null");
        this.status = TransferStatus.DISPATCHED_IN_TRANSIT;
        this.dispatchedAt = Instant.now();
    }

    public void arriveAtDestination() {
        if (this.status != TransferStatus.DISPATCHED_IN_TRANSIT) {
            throw new IllegalStateException("Order must be IN_TRANSIT before arriving: " + status);
        }
        this.status = TransferStatus.ARRIVED_AT_DESTINATION;
    }

    public void startInspection() {
        if (this.status != TransferStatus.ARRIVED_AT_DESTINATION) {
            throw new IllegalStateException("Order must be ARRIVED before inspection: " + status);
        }
        this.status = TransferStatus.INSPECTING_AND_RECEIVING;
    }

    public void addDiscrepancy(DiscrepancyReport report) {
        this.discrepancies.add(Objects.requireNonNull(report, "Discrepancy report must not be null"));
    }

    public void reconcileReceipt() {
        if (this.status != TransferStatus.INSPECTING_AND_RECEIVING) {
            throw new IllegalStateException("Order must be INSPECTING before reconciliation: " + status);
        }
        this.receivedAt = Instant.now();

        boolean hasDiscrepancies = lineItems.stream().anyMatch(TransferLineItem::hasDiscrepancy) || !discrepancies.isEmpty();
        if (hasDiscrepancies) {
            this.status = TransferStatus.DISCREPANCY_FLAGGED;
        } else {
            this.status = TransferStatus.RECONCILED_SUCCESS;
        }
    }

    public void cancel(String reason) {
        if (status == TransferStatus.DISPATCHED_IN_TRANSIT || status == TransferStatus.RECONCILED_SUCCESS) {
            throw new IllegalStateException("Cannot cancel order in status " + status);
        }
        this.status = TransferStatus.CANCELLED;
    }

    public int getTotalRequestedUnits() {
        return lineItems.stream().mapToInt(TransferLineItem::getRequestedQuantity).sum();
    }

    public int getTotalShippedUnits() {
        return lineItems.stream().mapToInt(TransferLineItem::getShippedQuantity).sum();
    }

    public int getTotalReceivedUnits() {
        return lineItems.stream().mapToInt(TransferLineItem::getReceivedQuantity).sum();
    }
}
