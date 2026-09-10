package com.elmos.logistics.domain.model.wave;

import com.elmos.logistics.domain.model.common.Coordinates3D;

import java.time.Instant;
import java.util.Objects;

/**
 * An individual item scheduled to be picked from a specific bin during a wave task.
 */
public class PickItem {
    private final String pickItemId;
    private final String waveTaskId;
    private final String orderId;
    private final String stockUnitId;
    private final String skuId;
    private final String sourceBinId;
    private final Coordinates3D coordinates;
    private final int quantity;

    private boolean picked;
    private Instant pickedAt;
    private String pickerWorkerId;

    public PickItem(String pickItemId,
                    String waveTaskId,
                    String orderId,
                    String stockUnitId,
                    String skuId,
                    String sourceBinId,
                    Coordinates3D coordinates,
                    int quantity) {
        this.pickItemId = Objects.requireNonNull(pickItemId, "pickItemId must not be null");
        this.waveTaskId = Objects.requireNonNull(waveTaskId, "waveTaskId must not be null");
        this.orderId = Objects.requireNonNull(orderId, "orderId must not be null");
        this.stockUnitId = Objects.requireNonNull(stockUnitId, "stockUnitId must not be null");
        this.skuId = Objects.requireNonNull(skuId, "skuId must not be null");
        this.sourceBinId = Objects.requireNonNull(sourceBinId, "sourceBinId must not be null");
        this.coordinates = Objects.requireNonNull(coordinates, "coordinates must not be null");
        this.quantity = quantity;
        this.picked = false;
    }

    public String getPickItemId() {
        return pickItemId;
    }

    public String getWaveTaskId() {
        return waveTaskId;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getStockUnitId() {
        return stockUnitId;
    }

    public String getSkuId() {
        return skuId;
    }

    public String getSourceBinId() {
        return sourceBinId;
    }

    public Coordinates3D getCoordinates() {
        return coordinates;
    }

    public int getQuantity() {
        return quantity;
    }

    public boolean isPicked() {
        return picked;
    }

    public Instant getPickedAt() {
        return pickedAt;
    }

    public String getPickerWorkerId() {
        return pickerWorkerId;
    }

    public synchronized void markPicked(String workerId) {
        this.picked = true;
        this.pickedAt = Instant.now();
        this.pickerWorkerId = Objects.requireNonNull(workerId, "workerId must not be null");
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        PickItem pickItem = (PickItem) o;
        return Objects.equals(pickItemId, pickItem.pickItemId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(pickItemId);
    }
}
