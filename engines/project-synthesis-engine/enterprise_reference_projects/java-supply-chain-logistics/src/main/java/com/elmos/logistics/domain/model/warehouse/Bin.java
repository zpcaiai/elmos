package com.elmos.logistics.domain.model.warehouse;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.StorageClass;
import com.elmos.logistics.domain.model.common.Weight;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * An individual storage cell (Bin) in a warehouse rack.
 * Identified by hierarchical coordinate: Warehouse-Zone-Aisle-Rack-Shelf-Bin.
 */
public class Bin {
    private final String binId;
    private final String warehouseId;
    private final String zoneId;
    private final String aisleCode;
    private final int rackNumber;
    private final int shelfLevel;
    private final int binPosition;
    private final Coordinates3D coordinates;
    private final Dimensions dimensions;
    private final Weight maxWeightCapacity;
    private final StorageClass storageClass;

    private BinStatus status;
    private Weight currentWeight;
    private long currentVolumeCubicMm;
    private final List<String> occupiedStockUnitIds;
    private long version;

    public Bin(String binId,
               String warehouseId,
               String zoneId,
               String aisleCode,
               int rackNumber,
               int shelfLevel,
               int binPosition,
               Coordinates3D coordinates,
               Dimensions dimensions,
               Weight maxWeightCapacity,
               StorageClass storageClass) {
        this.binId = Objects.requireNonNull(binId, "binId must not be null");
        this.warehouseId = Objects.requireNonNull(warehouseId, "warehouseId must not be null");
        this.zoneId = Objects.requireNonNull(zoneId, "zoneId must not be null");
        this.aisleCode = Objects.requireNonNull(aisleCode, "aisleCode must not be null");
        this.rackNumber = rackNumber;
        this.shelfLevel = shelfLevel;
        this.binPosition = binPosition;
        this.coordinates = Objects.requireNonNull(coordinates, "coordinates must not be null");
        this.dimensions = Objects.requireNonNull(dimensions, "dimensions must not be null");
        this.maxWeightCapacity = Objects.requireNonNull(maxWeightCapacity, "maxWeightCapacity must not be null");
        this.storageClass = Objects.requireNonNull(storageClass, "storageClass must not be null");

        this.status = BinStatus.AVAILABLE;
        this.currentWeight = Weight.zero();
        this.currentVolumeCubicMm = 0;
        this.occupiedStockUnitIds = new ArrayList<>();
        this.version = 0L;
    }

    public String getBinId() {
        return binId;
    }

    public String getWarehouseId() {
        return warehouseId;
    }

    public String getZoneId() {
        return zoneId;
    }

    public String getAisleCode() {
        return aisleCode;
    }

    public int getRackNumber() {
        return rackNumber;
    }

    public int getShelfLevel() {
        return shelfLevel;
    }

    public int getBinPosition() {
        return binPosition;
    }

    public Coordinates3D getCoordinates() {
        return coordinates;
    }

    public Dimensions getDimensions() {
        return dimensions;
    }

    public Weight getMaxWeightCapacity() {
        return maxWeightCapacity;
    }

    public StorageClass getStorageClass() {
        return storageClass;
    }

    public BinStatus getStatus() {
        return status;
    }

    public Weight getCurrentWeight() {
        return currentWeight;
    }

    public long getCurrentVolumeCubicMm() {
        return currentVolumeCubicMm;
    }

    public List<String> getOccupiedStockUnitIds() {
        return Collections.unmodifiableList(occupiedStockUnitIds);
    }

    public long getVersion() {
        return version;
    }

    public String getFormattedCode() {
        return String.format("%s-%s-%s-R%02d-S%02d-B%02d",
                warehouseId, zoneId, aisleCode, rackNumber, shelfLevel, binPosition);
    }

    /**
     * Verifies if a unit with the given dimensions and weight can be put away into this bin.
     */
    public boolean canAccommodate(Dimensions itemDimensions, Weight itemWeight, StorageClass itemClass) {
        if (status == BinStatus.BLOCKED_FOR_CYCLE_COUNT
                || status == BinStatus.BLOCKED_FOR_MAINTENANCE
                || status == BinStatus.QUARANTINED
                || status == BinStatus.FULL) {
            return false;
        }

        if (!this.storageClass.isCompatibleForCoLocation(itemClass)) {
            return false;
        }

        Weight projectedWeight = this.currentWeight.add(itemWeight);
        if (projectedWeight.isGreaterThan(this.maxWeightCapacity)) {
            return false;
        }

        long projectedVolume = this.currentVolumeCubicMm + itemDimensions.volumeCubicMm();
        if (projectedVolume > this.dimensions.volumeCubicMm()) {
            return false;
        }

        return itemDimensions.fitsWithRotation(this.dimensions);
    }

    /**
     * Stores a stock unit into this bin.
     */
    public synchronized void placeStockUnit(String stockUnitId, Dimensions itemDims, Weight itemWeight, StorageClass itemClass) {
        if (!canAccommodate(itemDims, itemWeight, itemClass)) {
            throw new IllegalStateException("Bin " + getFormattedCode() + " cannot accommodate stock unit " + stockUnitId);
        }

        this.occupiedStockUnitIds.add(stockUnitId);
        this.currentWeight = this.currentWeight.add(itemWeight);
        this.currentVolumeCubicMm += itemDims.volumeCubicMm();

        double fillRatioByVolume = (double) this.currentVolumeCubicMm / this.dimensions.volumeCubicMm();
        double fillRatioByWeight = (double) this.currentWeight.toMilligrams() / this.maxWeightCapacity.toMilligrams();

        if (fillRatioByVolume >= 0.95 || fillRatioByWeight >= 0.95) {
            this.status = BinStatus.FULL;
        } else {
            this.status = BinStatus.PARTIALLY_OCCUPIED;
        }
        this.version++;
    }

    /**
     * Removes a stock unit from this bin during order picking.
     */
    public synchronized void removeStockUnit(String stockUnitId, Dimensions itemDims, Weight itemWeight) {
        boolean removed = this.occupiedStockUnitIds.remove(stockUnitId);
        if (!removed) {
            throw new IllegalArgumentException("Stock unit " + stockUnitId + " was not found in bin " + getFormattedCode());
        }

        this.currentWeight = this.currentWeight.subtract(itemWeight);
        this.currentVolumeCubicMm = Math.max(0, this.currentVolumeCubicMm - itemDims.volumeCubicMm());

        if (this.occupiedStockUnitIds.isEmpty()) {
            this.status = BinStatus.AVAILABLE;
        } else {
            this.status = BinStatus.PARTIALLY_OCCUPIED;
        }
        this.version++;
    }

    public synchronized void lockForCycleCount() {
        if (status == BinStatus.BLOCKED_FOR_MAINTENANCE || status == BinStatus.QUARANTINED) {
            throw new IllegalStateException("Cannot lock bin in " + status + " for cycle count");
        }
        this.status = BinStatus.BLOCKED_FOR_CYCLE_COUNT;
        this.version++;
    }

    public synchronized void releaseCycleCount() {
        if (this.status == BinStatus.BLOCKED_FOR_CYCLE_COUNT) {
            this.status = occupiedStockUnitIds.isEmpty() ? BinStatus.AVAILABLE : BinStatus.PARTIALLY_OCCUPIED;
            this.version++;
        }
    }

    public synchronized void quarantine(String reason) {
        this.status = BinStatus.QUARANTINED;
        this.version++;
    }

    public synchronized void unquarantine() {
        this.status = occupiedStockUnitIds.isEmpty() ? BinStatus.AVAILABLE : BinStatus.PARTIALLY_OCCUPIED;
        this.version++;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        Bin bin = (Bin) o;
        return Objects.equals(binId, bin.binId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(binId);
    }

    @Override
    public String toString() {
        return "Bin{" + getFormattedCode() + ", status=" + status + ", coords=" + coordinates + "}";
    }
}
