package com.elmos.logistics.domain.model.warehouse;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.StorageClass;
import com.elmos.logistics.domain.model.common.Weight;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Aggregate root for a physical fulfillment center or distribution hub.
 */
public class Warehouse {
    private final String warehouseId;
    private final String tenantId;
    private final String code;
    private final String name;
    private final String address;
    private final Coordinates3D receivingDockLocation;
    private final Coordinates3D shippingBayLocation;
    private final List<Zone> zones;
    private boolean active;

    public Warehouse(String warehouseId,
                     String tenantId,
                     String code,
                     String name,
                     String address,
                     Coordinates3D receivingDockLocation,
                     Coordinates3D shippingBayLocation) {
        this.warehouseId = Objects.requireNonNull(warehouseId, "warehouseId must not be null");
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId must not be null");
        this.code = Objects.requireNonNull(code, "code must not be null");
        this.name = Objects.requireNonNull(name, "name must not be null");
        this.address = Objects.requireNonNull(address, "address must not be null");
        this.receivingDockLocation = Objects.requireNonNull(receivingDockLocation, "receivingDockLocation must not be null");
        this.shippingBayLocation = Objects.requireNonNull(shippingBayLocation, "shippingBayLocation must not be null");
        this.zones = new ArrayList<>();
        this.active = true;
    }

    public String getWarehouseId() {
        return warehouseId;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }

    public String getAddress() {
        return address;
    }

    public Coordinates3D getReceivingDockLocation() {
        return receivingDockLocation;
    }

    public Coordinates3D getShippingBayLocation() {
        return shippingBayLocation;
    }

    public List<Zone> getZones() {
        return Collections.unmodifiableList(zones);
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }

    public void addZone(Zone zone) {
        Objects.requireNonNull(zone, "Zone must not be null");
        this.zones.add(zone);
    }

    public Optional<Zone> findZone(String zoneId) {
        return zones.stream().filter(z -> z.getZoneId().equals(zoneId)).findFirst();
    }

    public List<Bin> getAllBins() {
        List<Bin> all = new ArrayList<>();
        for (Zone z : zones) {
            all.addAll(z.getAllBins());
        }
        return all;
    }

    public Optional<Bin> findOptimalPutawayBin(Dimensions dims, Weight weight, StorageClass storageClass) {
        return getAllBins().stream()
                .filter(b -> b.canAccommodate(dims, weight, storageClass))
                // Sort by distance to receiving dock to minimize travel distance during putaway
                .min((b1, b2) -> {
                    long dist1 = b1.getCoordinates().manhattanDistanceTo(receivingDockLocation);
                    long dist2 = b2.getCoordinates().manhattanDistanceTo(receivingDockLocation);
                    return Long.compare(dist1, dist2);
                });
    }

    public long getTotalCapacityBins() {
        return getAllBins().size();
    }

    public long getAvailableCapacityBins() {
        return getAllBins().stream().filter(b -> b.getStatus() == BinStatus.AVAILABLE).count();
    }
}
