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
import com.elmos.logistics.domain.service.InventoryAllocationEngine;
import com.elmos.logistics.infrastructure.persistence.InMemoryBinRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryInventoryLotRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryOutboxRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryProductSkuRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryStockUnitRepository;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrencySafetyTest {
    public static void runTests() throws Exception {
        System.out.println("Running ConcurrencySafetyTest (multi-threaded allocation race)...");
        testConcurrentAllocationZeroOverAllocation();
        System.out.println("  ✓ ConcurrencySafetyTest passed successfully.");
    }

    private static void testConcurrentAllocationZeroOverAllocation() throws Exception {
        InMemoryBinRepository binRepo = new InMemoryBinRepository();
        InMemoryProductSkuRepository skuRepo = new InMemoryProductSkuRepository();
        InMemoryInventoryLotRepository lotRepo = new InMemoryInventoryLotRepository();
        InMemoryStockUnitRepository stockRepo = new InMemoryStockUnitRepository();
        InMemoryOutboxRepository outboxRepo = new InMemoryOutboxRepository();

        InventoryAllocationEngine engine = new InventoryAllocationEngine(skuRepo, lotRepo, stockRepo, binRepo, outboxRepo);

        String whId = "WH-CONCURRENT";
        String skuId = "SKU-SMARTPHONE";
        ProductSku sku = new ProductSku(
                skuId, "tenant_1", "PHONE-X", "Flagship Smartphone 256GB", "1234567890999",
                Dimensions.of(150, 75, 8), Weight.ofGrams(180), StorageClass.HIGH_VALUE_VAULT,
                TemperatureRange.ambient(), 10, 100, Money.ofCents(99900, "USD"), false
        );
        skuRepo.save(sku);

        Instant now = Instant.now();
        InventoryLot lot = new InventoryLot("LOT-TECH-01", skuId, "BATCH-T1", now.minus(10, ChronoUnit.DAYS), now.plus(365, ChronoUnit.DAYS), "TECH_CORP", null, 100);
        lotRepo.save(lot);

        // Seed exactly 100 units
        int totalStock = 100;
        for (int i = 0; i < totalStock; i++) {
            stockRepo.save(new StockUnit("SU-" + i, "tenant_1", whId, skuId, lot.getLotId(), "SN-PHONE-" + i, "BIN-VAULT-1"));
        }

        // 20 concurrent threads, each attempting to allocate 10 units (Total demand = 200 units, but supply = 100)
        int threadCount = 20;
        int demandPerThread = 10;
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch finishGate = new CountDownLatch(threadCount);

        AtomicInteger successfulAllocations = new AtomicInteger(0);
        AtomicInteger failedAllocations = new AtomicInteger(0);
        Set<String> allAllocatedStockUnitIds = Collections.synchronizedSet(new HashSet<>());

        for (int t = 0; t < threadCount; t++) {
            final String orderId = "ORD-RACE-" + t;
            executor.submit(() -> {
                try {
                    startGate.await(); // Simultaneous start
                    InventoryAllocationEngine.AllocationResult res = engine.allocateStock(
                            whId, orderId, skuId, demandPerThread, AllocationPolicy.FIFO, Coordinates3D.origin()
                    );
                    if (res.isFullyAllocated()) {
                        successfulAllocations.incrementAndGet();
                        for (StockUnit u : res.getAllocatedUnits()) {
                            boolean wasAdded = allAllocatedStockUnitIds.add(u.getStockUnitId());
                            if (!wasAdded) {
                                throw new AssertionError("CRITICAL: Double allocation detected for stock unit: " + u.getStockUnitId());
                            }
                        }
                    } else {
                        failedAllocations.incrementAndGet();
                    }
                } catch (Exception ex) {
                    ex.printStackTrace();
                } finally {
                    finishGate.countDown();
                }
            });
        }

        startGate.countDown();
        boolean finished = finishGate.await(10, TimeUnit.SECONDS);
        executor.shutdown();

        if (!finished) {
            throw new AssertionError("Concurrent test timed out");
        }

        // Exactly 10 threads should succeed (10 * 10 = 100 units), 10 threads should fail cleanly
        if (successfulAllocations.get() != 10) {
            throw new AssertionError("Expected exactly 10 successful allocations, got: " + successfulAllocations.get());
        }
        if (failedAllocations.get() != 10) {
            throw new AssertionError("Expected exactly 10 failed allocations, got: " + failedAllocations.get());
        }

        // Invariant: Exactly 100 distinct units allocated, 0 remaining
        if (allAllocatedStockUnitIds.size() != 100) {
            throw new AssertionError("Expected 100 unique allocated units, got: " + allAllocatedStockUnitIds.size());
        }

        long remaining = stockRepo.countAvailable(whId, skuId);
        if (remaining != 0) {
            throw new AssertionError("Expected 0 remaining stock, got: " + remaining);
        }
    }
}
