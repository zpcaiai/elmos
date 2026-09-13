package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.inventory.AllocationStatus;
import com.elmos.logistics.domain.model.inventory.StockUnit;
import com.elmos.logistics.domain.model.outbox.OutboxEvent;
import com.elmos.logistics.domain.model.transfer.DiscrepancyReport;
import com.elmos.logistics.domain.model.transfer.StockTransferOrder;
import com.elmos.logistics.domain.model.transfer.TransferLineItem;
import com.elmos.logistics.domain.model.transfer.TransferStatus;
import com.elmos.logistics.domain.repository.OutboxRepository;
import com.elmos.logistics.domain.repository.StockTransferRepository;
import com.elmos.logistics.domain.repository.StockUnitRepository;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Governs the multi-step finite state machine for inter-warehouse stock rebalancing.
 * Enforces transactional consistency and discrepancy logging.
 */
public class TransferStateMachineService {
    private final StockTransferRepository transferRepository;
    private final StockUnitRepository stockUnitRepository;
    private final OutboxRepository outboxRepository;

    public TransferStateMachineService(StockTransferRepository transferRepository,
                                       StockUnitRepository stockUnitRepository,
                                       OutboxRepository outboxRepository) {
        this.transferRepository = Objects.requireNonNull(transferRepository, "transferRepository must not be null");
        this.stockUnitRepository = Objects.requireNonNull(stockUnitRepository, "stockUnitRepository must not be null");
        this.outboxRepository = Objects.requireNonNull(outboxRepository, "outboxRepository must not be null");
    }

    public synchronized void submitOrder(String transferOrderId) {
        StockTransferOrder order = getOrderOrThrow(transferOrderId);
        order.submitForApproval();
        transferRepository.save(order);
        emitEvent(order, "TRANSFER_ORDER_SUBMITTED");
    }

    public synchronized void approveOrder(String transferOrderId) {
        StockTransferOrder order = getOrderOrThrow(transferOrderId);
        order.approve();
        transferRepository.save(order);
        emitEvent(order, "TRANSFER_ORDER_APPROVED");
    }

    public synchronized void startPicking(String transferOrderId) {
        StockTransferOrder order = getOrderOrThrow(transferOrderId);
        order.startPicking();
        transferRepository.save(order);
        emitEvent(order, "TRANSFER_ORDER_PICKING_STARTED");
    }

    public synchronized void dispatchOrder(String transferOrderId, String carrierName, String trackingNumber, List<String> stockUnitIds) {
        StockTransferOrder order = getOrderOrThrow(transferOrderId);
        order.dispatch(carrierName, trackingNumber);

        for (TransferLineItem item : order.getLineItems()) {
            item.setShippedQuantity(item.getRequestedQuantity());
        }

        // Relocate stock units to transit status
        for (String unitId : stockUnitIds) {
            stockUnitRepository.findById(unitId).ifPresent(u -> {
                u.relocateToBin("IN_TRANSIT_" + carrierName);
                stockUnitRepository.save(u);
            });
        }

        transferRepository.save(order);
        emitEvent(order, "TRANSFER_ORDER_DISPATCHED");
    }

    public synchronized void recordArrival(String transferOrderId) {
        StockTransferOrder order = getOrderOrThrow(transferOrderId);
        order.arriveAtDestination();
        order.startInspection();
        transferRepository.save(order);
        emitEvent(order, "TRANSFER_ORDER_ARRIVED_AT_DESTINATION");
    }

    public synchronized void receiveLineItem(String transferOrderId, String lineItemId, int goodQty, int damagedQty, String receivingBinId) {
        StockTransferOrder order = getOrderOrThrow(transferOrderId);

        TransferLineItem targetLine = order.getLineItems().stream()
                .filter(l -> l.getLineItemId().equals(lineItemId))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Line item not found: " + lineItemId));

        targetLine.recordReceipt(goodQty, damagedQty);

        if (targetLine.hasDiscrepancy()) {
            String reportId = UUID.randomUUID().toString();
            DiscrepancyReport report = new DiscrepancyReport(
                    reportId,
                    transferOrderId,
                    lineItemId,
                    targetLine.getSkuId(),
                    targetLine.getShippedQuantity(),
                    goodQty,
                    damagedQty,
                    "Variance of " + targetLine.getVarianceQuantity() + " units detected during receipt inspection."
            );
            order.addDiscrepancy(report);
        }

        transferRepository.save(order);
    }

    public synchronized void finalizeReconciliation(String transferOrderId) {
        StockTransferOrder order = getOrderOrThrow(transferOrderId);
        order.reconcileReceipt();
        transferRepository.save(order);

        String eventType = (order.getStatus() == TransferStatus.RECONCILED_SUCCESS)
                ? "TRANSFER_RECONCILIATION_SUCCESS"
                : "TRANSFER_RECONCILIATION_DISCREPANCY_FLAGGED";
        emitEvent(order, eventType);
    }

    private StockTransferOrder getOrderOrThrow(String transferOrderId) {
        return transferRepository.findById(transferOrderId)
                .orElseThrow(() -> new IllegalArgumentException("Stock transfer order not found: " + transferOrderId));
    }

    private void emitEvent(StockTransferOrder order, String eventType) {
        String eventId = UUID.randomUUID().toString();
        String payload = String.format("{\"transferOrderId\":\"%s\",\"orderNumber\":\"%s\",\"source\":\"%s\",\"destination\":\"%s\",\"status\":\"%s\"}",
                order.getTransferOrderId(), order.getOrderNumber(), order.getSourceWarehouseId(), order.getDestinationWarehouseId(), order.getStatus());
        OutboxEvent event = new OutboxEvent(eventId, order.getTenantId(), "StockTransferOrder", order.getTransferOrderId(), eventType, payload);
        outboxRepository.save(event);
    }
}
