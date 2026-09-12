package com.elmos.logistics;

import com.elmos.logistics.domain.model.transfer.StockTransferOrder;
import com.elmos.logistics.domain.model.transfer.TransferLineItem;
import com.elmos.logistics.domain.model.transfer.TransferStatus;
import com.elmos.logistics.domain.service.TransferStateMachineService;
import com.elmos.logistics.infrastructure.persistence.InMemoryOutboxRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryStockTransferRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryStockUnitRepository;

import java.util.Collections;

public class TransferStateMachineTest {
    public static void runTests() {
        System.out.println("Running TransferStateMachineTest...");
        testNormalTransferLifecycle();
        testDiscrepancyReporting();
        System.out.println("  ✓ TransferStateMachineTest passed successfully.");
    }

    private static void testNormalTransferLifecycle() {
        InMemoryStockTransferRepository transferRepo = new InMemoryStockTransferRepository();
        InMemoryStockUnitRepository stockRepo = new InMemoryStockUnitRepository();
        InMemoryOutboxRepository outboxRepo = new InMemoryOutboxRepository();

        TransferStateMachineService service = new TransferStateMachineService(transferRepo, stockRepo, outboxRepo);

        String orderId = "TX-001";
        StockTransferOrder order = new StockTransferOrder(orderId, "tenant_1", "WH-SRC", "WH-DST", "TO-2026-001");
        TransferLineItem item = new TransferLineItem("LINE-1", "SKU-1", "LOT-1", 50);
        order.addLineItem(item);
        transferRepo.save(order);

        service.submitOrder(orderId);
        if (order.getStatus() != TransferStatus.SUBMITTED_FOR_APPROVAL) throw new AssertionError("Expected SUBMITTED");

        service.approveOrder(orderId);
        if (order.getStatus() != TransferStatus.APPROVED) throw new AssertionError("Expected APPROVED");

        service.startPicking(orderId);
        if (order.getStatus() != TransferStatus.PICKING_AND_PACKING) throw new AssertionError("Expected PICKING");

        service.dispatchOrder(orderId, "DHL_EXPRESS", "DHL-TRACK-99", Collections.emptyList());
        if (order.getStatus() != TransferStatus.DISPATCHED_IN_TRANSIT) throw new AssertionError("Expected IN_TRANSIT");

        service.recordArrival(orderId);
        if (order.getStatus() != TransferStatus.INSPECTING_AND_RECEIVING) throw new AssertionError("Expected INSPECTING");

        // Receive full quantity with zero damage
        service.receiveLineItem(orderId, "LINE-1", 50, 0, "BIN-DST-1");
        service.finalizeReconciliation(orderId);

        if (order.getStatus() != TransferStatus.RECONCILED_SUCCESS) throw new AssertionError("Expected RECONCILED_SUCCESS");
        if (order.getDiscrepancies().size() != 0) throw new AssertionError("Expected zero discrepancies");
    }

    private static void testDiscrepancyReporting() {
        InMemoryStockTransferRepository transferRepo = new InMemoryStockTransferRepository();
        InMemoryStockUnitRepository stockRepo = new InMemoryStockUnitRepository();
        InMemoryOutboxRepository outboxRepo = new InMemoryOutboxRepository();

        TransferStateMachineService service = new TransferStateMachineService(transferRepo, stockRepo, outboxRepo);

        String orderId = "TX-002";
        StockTransferOrder order = new StockTransferOrder(orderId, "tenant_1", "WH-SRC", "WH-DST", "TO-2026-002");
        TransferLineItem item = new TransferLineItem("LINE-2", "SKU-2", "LOT-2", 100);
        order.addLineItem(item);
        transferRepo.save(order);

        service.submitOrder(orderId);
        service.approveOrder(orderId);
        service.startPicking(orderId);
        service.dispatchOrder(orderId, "FEDEX_FREIGHT", "FX-999", Collections.emptyList());
        service.recordArrival(orderId);

        // Receive with 10 units damaged and 5 units missing: 85 good, 10 damaged (shortage = 5)
        service.receiveLineItem(orderId, "LINE-2", 85, 10, "BIN-DST-2");
        service.finalizeReconciliation(orderId);

        if (order.getStatus() != TransferStatus.DISCREPANCY_FLAGGED) {
            throw new AssertionError("Expected DISCREPANCY_FLAGGED, got: " + order.getStatus());
        }

        if (order.getDiscrepancies().size() != 1) {
            throw new AssertionError("Expected 1 discrepancy report, got: " + order.getDiscrepancies().size());
        }

        if (order.getDiscrepancies().get(0).getDiscrepancyShortage() != 5) {
            throw new AssertionError("Expected 5 shortage, got: " + order.getDiscrepancies().get(0).getDiscrepancyShortage());
        }
    }
}
