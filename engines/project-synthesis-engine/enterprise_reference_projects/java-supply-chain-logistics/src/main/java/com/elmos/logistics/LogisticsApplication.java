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
import com.elmos.logistics.domain.model.warehouse.Bin;
import com.elmos.logistics.domain.model.warehouse.Warehouse;
import com.elmos.logistics.domain.model.warehouse.Zone;
import com.elmos.logistics.domain.service.InventoryAllocationEngine;
import com.elmos.logistics.infrastructure.messaging.OutboxEventPublisher;
import com.elmos.logistics.infrastructure.messaging.OutboxSweeperDaemon;
import com.elmos.logistics.infrastructure.persistence.InMemoryBinRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryInventoryLotRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryOutboxRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryProductSkuRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryStockUnitRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryWarehouseRepository;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

/**
 * Enterprise Logistics & Automated Fulfillment Center Application.
 */
public class LogisticsApplication {
    public static void main(String[] args) {
        System.out.println("==========================================================");
        System.out.println("  Enterprise Supply Chain Logistics Engine (Java 21)");
        System.out.println("==========================================================");

        // Bootstrap Repositories
        InMemoryWarehouseRepository warehouseRepo = new InMemoryWarehouseRepository();
        InMemoryBinRepository binRepo = new InMemoryBinRepository();
        InMemoryProductSkuRepository skuRepo = new InMemoryProductSkuRepository();
        InMemoryInventoryLotRepository lotRepo = new InMemoryInventoryLotRepository();
        InMemoryStockUnitRepository stockUnitRepo = new InMemoryStockUnitRepository();
        InMemoryOutboxRepository outboxRepo = new InMemoryOutboxRepository();

        OutboxEventPublisher publisher = new OutboxEventPublisher();
        OutboxSweeperDaemon sweeper = new OutboxSweeperDaemon(outboxRepo, publisher, 50, 3);

        InventoryAllocationEngine allocationEngine = new InventoryAllocationEngine(
                skuRepo, lotRepo, stockUnitRepo, binRepo, outboxRepo
        );

        // Seed Warehouse
        String whId = "WH-CHICAGO-01";
        Warehouse warehouse = new Warehouse(
                whId, "tenant_corp", "ORD1", "O'Hare Fulfillment Center",
                "1000 Cargo Way, Chicago, IL",
                Coordinates3D.of(0, 0, 0),
                Coordinates3D.of(100000, 50000, 0)
        );
        warehouseRepo.save(warehouse);

        // Seed SKU & Lots
        String skuId = "SKU-INSULIN-100";
        ProductSku insulinSku = new ProductSku(
                skuId, "tenant_corp", "INS-100U", "Humalog 100U/mL Insulin Cartridge",
                "00300028215014",
                Dimensions.of(150, 50, 30),
                Weight.ofGrams(120),
                StorageClass.COLD_CHILLED,
                TemperatureRange.coldChilled(),
                50, 200, Money.ofCents(4500, "USD"), true
        );
        skuRepo.save(insulinSku);

        // Add 2 lots (FEFO test: lot1 expires in 30 days, lot2 expires in 180 days)
        Instant now = Instant.now();
        InventoryLot lotExpiringSoon = new InventoryLot(
                "LOT-2026-A", skuId, "BATCH-A-SOON",
                now.minus(60, ChronoUnit.DAYS), now.plus(30, ChronoUnit.DAYS),
                "SUPPLIER-PHARMA", "https://certs.pharma.corp/lot-a.pdf", 100
        );
        lotRepo.save(lotExpiringSoon);

        InventoryLot lotExpiringLater = new InventoryLot(
                "LOT-2026-B", skuId, "BATCH-B-LATER",
                now.minus(10, ChronoUnit.DAYS), now.plus(180, ChronoUnit.DAYS),
                "SUPPLIER-PHARMA", "https://certs.pharma.corp/lot-b.pdf", 100
        );
        lotRepo.save(lotExpiringLater);

        // Seed Stock Units into Bins
        Bin binA = new Bin("BIN-01-A", whId, "ZONE-COLD", "AISLE-01", 1, 1, 1,
                Coordinates3D.of(5000, 10000, 1200), Dimensions.of(1000, 800, 600),
                Weight.ofKilograms(200), StorageClass.COLD_CHILLED);
        binRepo.save(binA);

        for (int i = 0; i < 10; i++) {
            StockUnit unit = new StockUnit(UUID.randomUUID().toString(), "tenant_corp", whId, skuId, lotExpiringSoon.getLotId(), "SN-A-" + i, binA.getBinId());
            stockUnitRepo.save(unit);
        }
        for (int i = 0; i < 10; i++) {
            StockUnit unit = new StockUnit(UUID.randomUUID().toString(), "tenant_corp", whId, skuId, lotExpiringLater.getLotId(), "SN-B-" + i, binA.getBinId());
            stockUnitRepo.save(unit);
        }

        System.out.println("Warehouse initialized with " + stockUnitRepo.countAvailable(whId, skuId) + " units of " + insulinSku.getName());

        // Allocate 5 units under FEFO policy
        InventoryAllocationEngine.AllocationResult result = allocationEngine.allocateStock(
                whId, "ORD-9901", skuId, 5, AllocationPolicy.FEFO, Coordinates3D.origin()
        );

        System.out.println("Allocation result: fullyAllocated=" + result.isFullyAllocated() + ", units=" + result.getAllocatedQuantity());
        for (StockUnit u : result.getAllocatedUnits()) {
            System.out.println("  Allocated unit " + u.getStockUnitId() + " from lot " + u.getLotId() + " (" + u.getSerialNumber() + ")");
        }

        // Run outbox sweeper
        int swept = sweeper.sweepOnce();
        System.out.println("Outbox sweeper dispatched " + swept + " events to message broker.");
        System.out.println("Logistics Application startup check complete.");
    }
}
