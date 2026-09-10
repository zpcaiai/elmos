package com.elmos.logistics.domain.model.inventory;

import java.time.Instant;
import java.util.Objects;

/**
 * An individually tracked unit of stock located in a specific bin.
 * Supports optimistic concurrency versioning and reservation state transitions.
 */
public class StockUnit {
    private final String stockUnitId;
    private final String tenantId;
    private final String warehouseId;
    private final String skuId;
    private final String lotId;
    private final String serialNumber;

    private String currentBinId;
    private AllocationStatus status;
    private String reservedForOrderId;
    private String allocatedWaveId;
    private Instant reservedAt;
    private Instant pickedAt;
    private Instant shippedAt;
    private long version;

    public StockUnit(String stockUnitId,
                     String tenantId,
                     String warehouseId,
                     String skuId,
                     String lotId,
                     String serialNumber,
                     String initialBinId) {
        this.stockUnitId = Objects.requireNonNull(stockUnitId, "stockUnitId must not be null");
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId must not be null");
        this.warehouseId = Objects.requireNonNull(warehouseId, "warehouseId must not be null");
        this.skuId = Objects.requireNonNull(skuId, "skuId must not be null");
        this.lotId = Objects.requireNonNull(lotId, "lotId must not be null");
        this.serialNumber = serialNumber;
        this.currentBinId = Objects.requireNonNull(initialBinId, "initialBinId must not be null");
        this.status = AllocationStatus.AVAILABLE;
        this.version = 0L;
    }

    public String getStockUnitId() {
        return stockUnitId;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getWarehouseId() {
        return warehouseId;
    }

    public String getSkuId() {
        return skuId;
    }

    public String getLotId() {
        return lotId;
    }

    public String getSerialNumber() {
        return serialNumber;
    }

    public String getCurrentBinId() {
        return currentBinId;
    }

    public AllocationStatus getStatus() {
        return status;
    }

    public String getReservedForOrderId() {
        return reservedForOrderId;
    }

    public String getAllocatedWaveId() {
        return allocatedWaveId;
    }

    public Instant getReservedAt() {
        return reservedAt;
    }

    public Instant getPickedAt() {
        return pickedAt;
    }

    public Instant getShippedAt() {
        return shippedAt;
    }

    public long getVersion() {
        return version;
    }

    public synchronized void reserveForOrder(String orderId) {
        if (this.status != AllocationStatus.AVAILABLE) {
            throw new IllegalStateException("Stock unit " + stockUnitId + " cannot be reserved in status " + status);
        }
        this.status = AllocationStatus.RESERVED;
        this.reservedForOrderId = Objects.requireNonNull(orderId, "orderId must not be null");
        this.reservedAt = Instant.now();
        this.version++;
    }

    public synchronized void releaseReservation() {
        if (this.status != AllocationStatus.RESERVED) {
            throw new IllegalStateException("Stock unit " + stockUnitId + " is not currently reserved");
        }
        this.status = AllocationStatus.AVAILABLE;
        this.reservedForOrderId = null;
        this.reservedAt = null;
        this.version++;
    }

    public synchronized void assignToWave(String waveId) {
        if (this.status != AllocationStatus.RESERVED) {
            throw new IllegalStateException("Stock unit must be RESERVED before allocating to wave: " + status);
        }
        this.status = AllocationStatus.ALLOCATED_TO_WAVE;
        this.allocatedWaveId = Objects.requireNonNull(waveId, "waveId must not be null");
        this.version++;
    }

    public synchronized void recordPicked() {
        if (this.status != AllocationStatus.ALLOCATED_TO_WAVE) {
            throw new IllegalStateException("Stock unit must be ALLOCATED_TO_WAVE before picking: " + status);
        }
        this.status = AllocationStatus.PICKED;
        this.pickedAt = Instant.now();
        this.version++;
    }

    public synchronized void recordStaged() {
        if (this.status != AllocationStatus.PICKED) {
            throw new IllegalStateException("Stock unit must be PICKED before staging: " + status);
        }
        this.status = AllocationStatus.STAGED_FOR_PACKING;
        this.version++;
    }

    public synchronized void recordPacked() {
        if (this.status != AllocationStatus.STAGED_FOR_PACKING) {
            throw new IllegalStateException("Stock unit must be STAGED before packing: " + status);
        }
        this.status = AllocationStatus.PACKED;
        this.version++;
    }

    public synchronized void recordShipped() {
        if (this.status != AllocationStatus.PACKED && this.status != AllocationStatus.LOADED_FOR_DISPATCH) {
            throw new IllegalStateException("Stock unit must be PACKED or LOADED before shipping: " + status);
        }
        this.status = AllocationStatus.SHIPPED;
        this.shippedAt = Instant.now();
        this.currentBinId = "DISPATCHED";
        this.version++;
    }

    public synchronized void relocateToBin(String newBinId) {
        this.currentBinId = Objects.requireNonNull(newBinId, "newBinId must not be null");
        this.version++;
    }

    public synchronized void writeOffDamage(String reason) {
        this.status = AllocationStatus.DAMAGED_WRITE_OFF;
        this.version++;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        StockUnit stockUnit = (StockUnit) o;
        return Objects.equals(stockUnitId, stockUnit.stockUnitId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(stockUnitId);
    }

    @Override
    public String toString() {
        return "StockUnit{" + stockUnitId + ", sku=" + skuId + ", bin=" + currentBinId + ", status=" + status + "}";
    }
}
