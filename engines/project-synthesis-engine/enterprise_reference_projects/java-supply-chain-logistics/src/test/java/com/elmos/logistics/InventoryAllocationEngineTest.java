package com.elmos.logistics;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.Money;
import com.elmos.logistics.domain.model.common.StorageClass;
import com.elmos.logistics.domain.model.common.TemperatureRange;
import com.elmos.logistics.domain.model.common.Weight;
import com.elmos.logistics.domain.model.inventory.AllocationPolicy;
import com.elmos.logistics.domain.model.inventory.InventoryLot;
import com.elmos.logistics.domain.model.inventory.ProductSku;
import com.elmos.logistics.domain.model.inventory.StockUnit;
import com.elmos.logistics.domain.model.outbox.OutboxEvent;
import com.elmos.logistics.domain.model.warehouse.Bin;
import com.elmos.logistics.domain.service.InventoryAllocationEngine;
import com.elmos.logistics.infrastructure.persistence.InMemoryBinRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryInventoryLotRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryOutboxRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryProductSkuRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryStockUnitRepository;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;

public class InventoryAllocationEngineTest {
    public static void runTests() {
        System.out.println("Running InventoryAllocationEngineTest...");
        testFefoLotPrioritization();
        testFifoLotPrioritization();
        testInsufficientStockHandling();
        System.out.println("  ✓ InventoryAllocationEngineTest passed successfully.");
    }

    private static void testFefoLotPrioritization() {
        InMemoryBinRepository binRepo = new InMemoryBinRepository();
        InMemoryProductSkuRepository skuRepo = new InMemoryProductSkuRepository();
        InMemoryInventoryLotRepository lotRepo = new InMemoryInventoryLotRepository();
        InMemoryStockUnitRepository stockRepo = new InMemoryStockUnitRepository();
        InMemoryOutboxRepository outboxRepo = new InMemoryOutboxRepository();

        InventoryAllocationEngine engine = new InventoryAllocationEngine(skuRepo, lotRepo, stockRepo, binRepo, outboxRepo);

        String whId = "WH-1";
        String skuId = "SKU-VACCINE";
        ProductSku sku = new ProductSku(
                skuId, "tenant_1", "VAC-01", "Measles Vaccine", "1234567890123",
                Dimensions.of(100, 50, 50), Weight.ofGrams(100), StorageClass.COLD_CHILLED,
                TemperatureRange.coldChilled(), 10, 50, Money.ofCents(2500, "USD"), true
        );
        skuRepo.save(sku);

        Instant now = Instant.now();
        // Lot 1: expires in 15 days
        InventoryLot lotSoon = new InventoryLot("LOT-SOON", skuId, "BATCH-1", now.minus(30, ChronoUnit.DAYS), now.plus(15, ChronoUnit.DAYS), "SUPP", null, 10);
        lotRepo.save(lotSoon);

        // Lot 2: expires in 90 days
        InventoryLot lotLater = new InventoryLot("LOT-LATER", skuId, "BATCH-2", now.minus(60, ChronoUnit.DAYS), now.plus(90, ChronoUnit.DAYS), "SUPP", null, 10);
        lotRepo.save(lotLater);

        Bin bin = new Bin("B1", whId, "Z1", "A1", 1, 1, 1, Coordinates3D.origin(), Dimensions.of(1000, 1000, 1000), Weight.ofKilograms(500), StorageClass.COLD_CHILLED);
        binRepo.save(bin);

        // Add 5 units to lotLater, 5 units to lotSoon
        for (int i = 0; i < 5; i++) {
            stockRepo.save(new StockUnit("U-LATER-" + i, "tenant_1", whId, skuId, lotLater.getLotId(), "SN-L-" + i, "B1"));
        }
        for (int i = 0; i < 5; i++) {
            stockRepo.save(new StockUnit("U-SOON-" + i, "tenant_1", whId, skuId, lotSoon.getLotId(), "SN-S-" + i, "B1"));
        }

        // Allocate 3 units
        InventoryAllocationEngine.AllocationResult result = engine.allocateStock(whId, "ORD-1", skuId, 3, AllocationPolicy.FEFO, Coordinates3D.origin());
        if (!result.isFullyAllocated()) throw new AssertionError("Expected fully allocated");
        if (result.getAllocatedQuantity() != 3) throw new AssertionError("Expected 3 allocated units");

        // FEFO invariant: All 3 units must come from LOT-SOON (expires first)
        for (StockUnit u : result.getAllocatedUnits()) {
            if (!u.getLotId().equals(lotSoon.getLotId())) {
                throw new AssertionError("FEFO violation: allocated unit " + u.getStockUnitId() + " from lot " + u.getLotId() + ", expected " + lotSoon.getLotId());
            }
        }
    }

    private static void testFifoLotPrioritization() {
        InMemoryBinRepository binRepo = new InMemoryBinRepository();
        InMemoryProductSkuRepository skuRepo = new InMemoryProductSkuRepository();
        InMemoryInventoryLotRepository lotRepo = new InventoryLotRepositoryImpl();
        InMemoryStockUnitRepository stockRepo = new InMemoryStockUnitRepository();
        InMemoryOutboxRepository outboxRepo = new InMemoryOutboxRepository();

        InventoryAllocationEngine engine = new InventoryAllocationEngine(skuRepo, lotRepo, stockRepo, binRepo, outboxRepo);

        String whId = "WH-1";
        String skuId = "SKU-STEEL-BOLT";
        // Non-perishable hardware bolt
        ProductSku sku = new ProductSku(
                skuId, "tenant_1", "BOLT-M8", "Steel Bolt M8", "1234567890124",
                Dimensions.of(50, 10, 10), Weight.ofGrams(20), StorageClass.STANDARD_AMBIENT,
                TemperatureRange.ambient(), 100, 500, Money.ofCents(50, "USD"), false
        );
        skuRepo.save(sku);

        Instant now = Instant.now();
        // Lot 1: manufactured 100 days ago
        InventoryLot lotOld = new InventoryLot("LOT-OLD", skuId, "BATCH-OLD", now.minus(100, ChronoUnit.DAYS), now.plus(1000, ChronoUnit.DAYS), "SUPP", null, 10);
        lotRepo.save(lotOld);

        // Lot 2: manufactured 10 days ago
        InventoryLot lotNew = new InventoryLot("LOT-NEW", skuId, "BATCH-NEW", now.minus(10, ChronoUnit.DAYS), now.plus(1000, ChronoUnit.DAYS), "SUPP", null, 10);
        lotRepo.save(lotNew);

        for (int i = 0; i < 5; i++) {
            stockRepo.save(new StockUnit("U-NEW-" + i, "tenant_1", whId, skuId, lotNew.getLotId(), "SN-N-" + i, "B1"));
        }
        for (int i = 0; i < 5; i++) {
            stockRepo.save(new StockUnit("U-OLD-" + i, "tenant_1", whId, skuId, lotOld.getLotId(), "SN-O-" + i, "B1"));
        }

        InventoryAllocationEngine.AllocationResult result = engine.allocateStock(whId, "ORD-2", skuId, 4, AllocationPolicy.FIFO, Coordinates3D.origin());
        if (!result.isFullyAllocated()) throw new AssertionError("Expected fully allocated");

        // FIFO invariant: units must come from older manufactured lot
        for (StockUnit u : result.getAllocatedUnits()) {
            if (!u.getLotId().equals(lotOld.getLotId())) {
                throw new AssertionError("FIFO violation: allocated unit from lot " + u.getLotId() + ", expected " + lotOld.getLotId());
            }
        }
    }

    private static void testInsufficientStockHandling() {
        InMemoryBinRepository binRepo = new InMemoryBinRepository();
        InMemoryProductSkuRepository skuRepo = new InMemoryProductSkuRepository();
        InMemoryInventoryLotRepository lotRepo = new InMemoryInventoryLotRepository();
        InMemoryStockUnitRepository stockRepo = new InMemoryStockUnitRepository();
        InMemoryOutboxRepository outboxRepo = new InMemoryOutboxRepository();

        InventoryAllocationEngine engine = new InventoryAllocationEngine(skuRepo, lotRepo, stockRepo, binRepo, outboxRepo);

        String whId = "WH-1";
        String skuId = "SKU-COPPER-PIPE";
        ProductSku sku = new ProductSku(
                skuId, "tenant_1", "COP-01", "Copper Pipe 2m", "1234567890125",
                Dimensions.of(2000, 30, 30), Weight.ofGrams(1500), StorageClass.STANDARD_AMBIENT,
                TemperatureRange.ambient(), 5, 20, Money.ofCents(4500, "USD"), false
        );
        skuRepo.save(sku);

        InventoryAllocationEngine.AllocationResult result = engine.allocateStock(whId, "ORD-3", skuId, 10, AllocationPolicy.FIFO, Coordinates3D.origin());
        if (result.isFullyAllocated()) throw new AssertionError("Expected allocation failure for zero stock");

        // Check outbox event recorded
        List<OutboxEvent> events = outboxRepo.findByStatus(com.elmos.logistics.domain.model.outbox.OutboxStatus.PENDING);
        if (events.isEmpty()) throw new AssertionError("Expected shortage outbox event");
    }

    // Helper implementation alias
    private static class InventoryLotRepositoryImpl extends InMemoryInventoryLotRepository {}
}
