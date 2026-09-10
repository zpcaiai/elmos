package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.inventory.AllocationPolicy;
import com.elmos.logistics.domain.model.inventory.AllocationStatus;
import com.elmos.logistics.domain.model.inventory.InventoryLot;
import com.elmos.logistics.domain.model.inventory.ProductSku;
import com.elmos.logistics.domain.model.inventory.StockUnit;
import com.elmos.logistics.domain.model.outbox.OutboxEvent;
import com.elmos.logistics.domain.model.warehouse.Bin;
import com.elmos.logistics.domain.repository.BinRepository;
import com.elmos.logistics.domain.repository.InventoryLotRepository;
import com.elmos.logistics.domain.repository.OutboxRepository;
import com.elmos.logistics.domain.repository.ProductSkuRepository;
import com.elmos.logistics.domain.repository.StockUnitRepository;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * High-performance inventory allocation engine supporting FIFO, FEFO, and Proximity policies.
 * Guarantees zero stock over-allocation under concurrent order spikes.
 */
public class InventoryAllocationEngine {
    private final ProductSkuRepository skuRepository;
    private final InventoryLotRepository lotRepository;
    private final StockUnitRepository stockUnitRepository;
    private final BinRepository binRepository;
    private final OutboxRepository outboxRepository;

    public static class AllocationResult {
        private final String orderId;
        private final String skuId;
        private final int requestedQuantity;
        private final int allocatedQuantity;
        private final List<StockUnit> allocatedUnits;
        private final boolean fullyAllocated;
        private final String failureReason;

        public AllocationResult(String orderId,
                                String skuId,
                                int requestedQuantity,
                                int allocatedQuantity,
                                List<StockUnit> allocatedUnits,
                                boolean fullyAllocated,
                                String failureReason) {
            this.orderId = orderId;
            this.skuId = skuId;
            this.requestedQuantity = requestedQuantity;
            this.allocatedQuantity = allocatedQuantity;
            this.allocatedUnits = allocatedUnits;
            this.fullyAllocated = fullyAllocated;
            this.failureReason = failureReason;
        }

        public String getOrderId() {
            return orderId;
        }

        public String getSkuId() {
            return skuId;
        }

        public int getRequestedQuantity() {
            return requestedQuantity;
        }

        public int getAllocatedQuantity() {
            return allocatedQuantity;
        }

        public List<StockUnit> getAllocatedUnits() {
            return allocatedUnits;
        }

        public boolean isFullyAllocated() {
            return fullyAllocated;
        }

        public String getFailureReason() {
            return failureReason;
        }
    }

    public InventoryAllocationEngine(ProductSkuRepository skuRepository,
                                   InventoryLotRepository lotRepository,
                                   StockUnitRepository stockUnitRepository,
                                   BinRepository binRepository,
                                   OutboxRepository outboxRepository) {
        this.skuRepository = Objects.requireNonNull(skuRepository, "skuRepository must not be null");
        this.lotRepository = Objects.requireNonNull(lotRepository, "lotRepository must not be null");
        this.stockUnitRepository = Objects.requireNonNull(stockUnitRepository, "stockUnitRepository must not be null");
        this.binRepository = Objects.requireNonNull(binRepository, "binRepository must not be null");
        this.outboxRepository = Objects.requireNonNull(outboxRepository, "outboxRepository must not be null");
    }

    /**
     * Executes order line allocation based on specified warehouse policy.
     */
    public synchronized AllocationResult allocateStock(String warehouseId,
                                                       String orderId,
                                                       String skuId,
                                                       int requiredQuantity,
                                                       AllocationPolicy policy,
                                                       Coordinates3D stagingTarget) {
        if (requiredQuantity <= 0) {
            throw new IllegalArgumentException("Allocation quantity must be positive: " + requiredQuantity);
        }

        ProductSku sku = skuRepository.findById(skuId)
                .orElseThrow(() -> new IllegalArgumentException("Product SKU not found: " + skuId));

        Instant now = Instant.now();
        List<InventoryLot> availableLots = lotRepository.findAvailableLotsBySkuId(skuId).stream()
                .filter(lot -> !lot.isQuarantined())
                .filter(lot -> !lot.isExpiredAt(now))
                .collect(Collectors.toList());

        if (availableLots.isEmpty()) {
            recordStockOutEvent(warehouseId, orderId, skuId, requiredQuantity, 0);
            return new AllocationResult(orderId, skuId, requiredQuantity, 0, Collections.emptyList(), false, "NO_USABLE_LOTS_AVAILABLE");
        }

        // Determine lot prioritization based on policy and SKU characteristics
        AllocationPolicy effectivePolicy = policy;
        if (sku.isPerishable() && effectivePolicy != AllocationPolicy.FEFO) {
            // Perishable items must strictly use FEFO to prevent expired spoilage
            effectivePolicy = AllocationPolicy.FEFO;
        }

        sortLotsByPolicy(availableLots, effectivePolicy);

        List<StockUnit> candidateUnits = new ArrayList<>();
        for (InventoryLot lot : availableLots) {
            List<StockUnit> unitsForLot = stockUnitRepository.findAvailableUnitsForLot(warehouseId, skuId, lot.getLotId());
            if (effectivePolicy == AllocationPolicy.PROXIMITY_OPTIMAL && stagingTarget != null) {
                sortUnitsByProximity(unitsForLot, stagingTarget);
            }
            candidateUnits.addAll(unitsForLot);
            if (candidateUnits.size() >= requiredQuantity) {
                break;
            }
        }

        if (candidateUnits.size() < requiredQuantity) {
            int allocatedCount = candidateUnits.size();
            recordStockOutEvent(warehouseId, orderId, skuId, requiredQuantity, allocatedCount);
            return new AllocationResult(orderId, skuId, requiredQuantity, allocatedCount, Collections.emptyList(), false, "INSUFFICIENT_STOCK");
        }

        // Commit reservation for exact required quantity
        List<StockUnit> allocated = new ArrayList<>(requiredQuantity);
        Map<String, Integer> lotDeductions = new ConcurrentHashMap<>();

        for (int i = 0; i < requiredQuantity; i++) {
            StockUnit unit = candidateUnits.get(i);
            unit.reserveForOrder(orderId);
            allocated.add(unit);
            lotDeductions.merge(unit.getLotId(), 1, Integer::sum);
        }

        // Persist stock unit updates
        stockUnitRepository.saveAll(allocated);

        // Deduct lot remaining quantities
        for (Map.Entry<String, Integer> entry : lotDeductions.entrySet()) {
            lotRepository.findById(entry.getKey()).ifPresent(lot -> {
                lot.decrementQuantity(entry.getValue());
                lotRepository.save(lot);
            });
        }

        // Record outbox event for inventory allocated
        recordAllocationOutboxEvent(warehouseId, orderId, skuId, requiredQuantity, allocated);

        return new AllocationResult(orderId, skuId, requiredQuantity, requiredQuantity, allocated, true, null);
    }

    private void sortLotsByPolicy(List<InventoryLot> lots, AllocationPolicy policy) {
        switch (policy) {
            case FEFO:
                // Earliest expiration date first
                lots.sort(Comparator.comparing(InventoryLot::getExpirationDate));
                break;
            case FIFO:
            default:
                // Oldest manufactured date first
                lots.sort(Comparator.comparing(InventoryLot::getManufacturedDate));
                break;
        }
    }

    private void sortUnitsByProximity(List<StockUnit> units, Coordinates3D stagingTarget) {
        units.sort((u1, u2) -> {
            Coordinates3D c1 = binRepository.findById(u1.getCurrentBinId())
                    .map(Bin::getCoordinates).orElse(Coordinates3D.origin());
            Coordinates3D c2 = binRepository.findById(u2.getCurrentBinId())
                    .map(Bin::getCoordinates).orElse(Coordinates3D.origin());
            long dist1 = c1.manhattanDistanceTo(stagingTarget);
            long dist2 = c2.manhattanDistanceTo(stagingTarget);
            return Long.compare(dist1, dist2);
        });
    }

    private void recordAllocationOutboxEvent(String warehouseId, String orderId, String skuId, int quantity, List<StockUnit> units) {
        String eventId = UUID.randomUUID().toString();
        String payload = String.format("{\"orderId\":\"%s\",\"warehouseId\":\"%s\",\"skuId\":\"%s\",\"quantity\":%d,\"unitCount\":%d}",
                orderId, warehouseId, skuId, quantity, units.size());
        OutboxEvent event = new OutboxEvent(eventId, "default_tenant", "InventoryAllocation", orderId, "INVENTORY_ALLOCATED", payload);
        outboxRepository.save(event);
    }

    private void recordStockOutEvent(String warehouseId, String orderId, String skuId, int requested, int available) {
        String eventId = UUID.randomUUID().toString();
        String payload = String.format("{\"orderId\":\"%s\",\"warehouseId\":\"%s\",\"skuId\":\"%s\",\"requested\":%d,\"available\":%d}",
                orderId, warehouseId, skuId, requested, available);
        OutboxEvent event = new OutboxEvent(eventId, "default_tenant", "InventoryAllocation", orderId, "INVENTORY_SHORTAGE_DETECTED", payload);
        outboxRepository.save(event);
    }
}
