package com.elmos.logistics.domain.model.warehouse;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.common.StorageClass;
import com.elmos.logistics.domain.model.common.TemperatureRange;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * A major warehouse partition (Zone) representing temperature, security, or handling boundaries.
 */
public class Zone {
    private final String zoneId;
    private final String warehouseId;
    private final String code;
    private final String name;
    private final StorageClass storageClass;
    private final TemperatureRange temperatureRange;
    private final Coordinates3D dispatchStageLocation;
    private final List<Aisle> aisles;

    public Zone(String zoneId,
                String warehouseId,
                String code,
                String name,
                StorageClass storageClass,
                TemperatureRange temperatureRange,
                Coordinates3D dispatchStageLocation) {
        this.zoneId = Objects.requireNonNull(zoneId, "zoneId must not be null");
        this.warehouseId = Objects.requireNonNull(warehouseId, "warehouseId must not be null");
        this.code = Objects.requireNonNull(code, "code must not be null");
        this.name = Objects.requireNonNull(name, "name must not be null");
        this.storageClass = Objects.requireNonNull(storageClass, "storageClass must not be null");
        this.temperatureRange = Objects.requireNonNull(temperatureRange, "temperatureRange must not be null");
        this.dispatchStageLocation = Objects.requireNonNull(dispatchStageLocation, "dispatchStageLocation must not be null");
        this.aisles = new ArrayList<>();
    }

    public String getZoneId() {
        return zoneId;
    }

    public String getWarehouseId() {
        return warehouseId;
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }

    public StorageClass getStorageClass() {
        return storageClass;
    }

    public TemperatureRange getTemperatureRange() {
        return temperatureRange;
    }

    public Coordinates3D getDispatchStageLocation() {
        return dispatchStageLocation;
    }

    public List<Aisle> getAisles() {
        return Collections.unmodifiableList(aisles);
    }

    public void addAisle(Aisle aisle) {
        Objects.requireNonNull(aisle, "Aisle must not be null");
        this.aisles.add(aisle);
    }

    public List<Bin> getAllBins() {
        List<Bin> bins = new ArrayList<>();
        for (Aisle a : aisles) {
            bins.addAll(a.getAllBins());
        }
        return bins;
    }

    public long getAvailableCapacityBins() {
        return getAllBins().stream().filter(b -> b.getStatus() == BinStatus.AVAILABLE).count();
    }
}
