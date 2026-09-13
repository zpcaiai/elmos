package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.inventory.ProductSku;
import com.elmos.logistics.domain.model.outbox.OutboxEvent;
import com.elmos.logistics.domain.repository.OutboxRepository;
import com.elmos.logistics.domain.repository.ProductSkuRepository;
import com.elmos.logistics.domain.repository.StockUnitRepository;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Monitors stock levels against safety stock thresholds and generates replenishment orders.
 */
public class SafetyStockEvaluationService {
    private final ProductSkuRepository skuRepository;
    private final StockUnitRepository stockUnitRepository;
    private final OutboxRepository outboxRepository;

    public static class ReplenishmentTrigger {
        private final String skuId;
        private final String skuCode;
        private final long currentAvailable;
        private final int safetyStockThreshold;
        private final int recommendedReorderQuantity;

        public ReplenishmentTrigger(String skuId, String skuCode, long currentAvailable, int safetyStockThreshold, int recommendedReorderQuantity) {
            this.skuId = skuId;
            this.skuCode = skuCode;
            this.currentAvailable = currentAvailable;
            this.safetyStockThreshold = safetyStockThreshold;
            this.recommendedReorderQuantity = recommendedReorderQuantity;
        }

        public String getSkuId() {
            return skuId;
        }

        public String getSkuCode() {
            return skuCode;
        }

        public long getCurrentAvailable() {
            return currentAvailable;
        }

        public int getSafetyStockThreshold() {
            return safetyStockThreshold;
        }

        public int getRecommendedReorderQuantity() {
            return recommendedReorderQuantity;
        }
    }

    public SafetyStockEvaluationService(ProductSkuRepository skuRepository,
                                        StockUnitRepository stockUnitRepository,
                                        OutboxRepository outboxRepository) {
        this.skuRepository = Objects.requireNonNull(skuRepository, "skuRepository must not be null");
        this.stockUnitRepository = Objects.requireNonNull(stockUnitRepository, "stockUnitRepository must not be null");
        this.outboxRepository = Objects.requireNonNull(outboxRepository, "outboxRepository must not be null");
    }

    public List<ReplenishmentTrigger> evaluateWarehouseStock(String tenantId, String warehouseId) {
        List<ProductSku> allSkus = skuRepository.findAllByTenantId(tenantId);
        List<ReplenishmentTrigger> triggers = new ArrayList<>();

        for (ProductSku sku : allSkus) {
            long available = stockUnitRepository.countAvailable(warehouseId, sku.getSkuId());
            if (available <= sku.getSafetyStockThreshold()) {
                ReplenishmentTrigger trigger = new ReplenishmentTrigger(
                        sku.getSkuId(),
                        sku.getSkuCode(),
                        available,
                        sku.getSafetyStockThreshold(),
                        sku.getReorderQuantity()
                );
                triggers.add(trigger);
                recordReplenishmentEvent(warehouseId, trigger);
            }
        }

        return triggers;
    }

    private void recordReplenishmentEvent(String warehouseId, ReplenishmentTrigger trigger) {
        String eventId = UUID.randomUUID().toString();
        String payload = String.format("{\"warehouseId\":\"%s\",\"skuId\":\"%s\",\"skuCode\":\"%s\",\"available\":%d,\"threshold\":%d,\"reorderQty\":%d}",
                warehouseId, trigger.getSkuId(), trigger.getSkuCode(), trigger.getCurrentAvailable(), trigger.getSafetyStockThreshold(), trigger.getRecommendedReorderQuantity());
        OutboxEvent event = new OutboxEvent(eventId, "default_tenant", "SafetyStock", trigger.getSkuId(), "REPLENISHMENT_ORDER_TRIGGERED", payload);
        outboxRepository.save(event);
    }
}
