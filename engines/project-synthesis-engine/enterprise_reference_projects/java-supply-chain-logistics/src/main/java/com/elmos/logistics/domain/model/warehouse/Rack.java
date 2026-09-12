package com.elmos.logistics.domain.model.warehouse;

import com.elmos.logistics.domain.model.common.Coordinates3D;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * A vertical rack structure within an aisle containing multiple shelves and bins.
 */
public class Rack {
    private final String rackId;
    private final String aisleCode;
    private final int rackNumber;
    private final Coordinates3D baseCoordinates;
    private final int numberOfShelves;
    private final List<Bin> bins;

    public Rack(String rackId, String aisleCode, int rackNumber, Coordinates3D baseCoordinates, int numberOfShelves) {
        this.rackId = Objects.requireNonNull(rackId, "rackId must not be null");
        this.aisleCode = Objects.requireNonNull(aisleCode, "aisleCode must not be null");
        this.rackNumber = rackNumber;
        this.baseCoordinates = Objects.requireNonNull(baseCoordinates, "baseCoordinates must not be null");
        this.numberOfShelves = numberOfShelves;
        this.bins = new ArrayList<>();
    }

    public String getRackId() {
        return rackId;
    }

    public String getAisleCode() {
        return aisleCode;
    }

    public int getRackNumber() {
        return rackNumber;
    }

    public Coordinates3D getBaseCoordinates() {
        return baseCoordinates;
    }

    public int getNumberOfShelves() {
        return numberOfShelves;
    }

    public List<Bin> getBins() {
        return Collections.unmodifiableList(bins);
    }

    public void addBin(Bin bin) {
        Objects.requireNonNull(bin, "Bin cannot be null");
        this.bins.add(bin);
    }

    public int getTotalCapacityBins() {
        return bins.size();
    }

    public long getAvailableBinsCount() {
        return bins.stream().filter(b -> b.getStatus() == BinStatus.AVAILABLE).count();
    }
}
