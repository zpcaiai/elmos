package com.elmos.logistics.domain.model.warehouse;

import com.elmos.logistics.domain.model.common.Coordinates3D;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * An aisle corridor between rack rows through which human pickers and AGVs navigate.
 */
public class Aisle {
    private final String aisleCode;
    private final String zoneId;
    private final Coordinates3D entryCoordinates;
    private final Coordinates3D exitCoordinates;
    private final int widthMm;
    private final boolean oneWayOnly;
    private final List<Rack> leftRacks;
    private final List<Rack> rightRacks;

    public Aisle(String aisleCode,
                 String zoneId,
                 Coordinates3D entryCoordinates,
                 Coordinates3D exitCoordinates,
                 int widthMm,
                 boolean oneWayOnly) {
        this.aisleCode = Objects.requireNonNull(aisleCode, "aisleCode must not be null");
        this.zoneId = Objects.requireNonNull(zoneId, "zoneId must not be null");
        this.entryCoordinates = Objects.requireNonNull(entryCoordinates, "entryCoordinates must not be null");
        this.exitCoordinates = Objects.requireNonNull(exitCoordinates, "exitCoordinates must not be null");
        this.widthMm = widthMm;
        this.oneWayOnly = oneWayOnly;
        this.leftRacks = new ArrayList<>();
        this.rightRacks = new ArrayList<>();
    }

    public String getAisleCode() {
        return aisleCode;
    }

    public String getZoneId() {
        return zoneId;
    }

    public Coordinates3D getEntryCoordinates() {
        return entryCoordinates;
    }

    public Coordinates3D getExitCoordinates() {
        return exitCoordinates;
    }

    public int getWidthMm() {
        return widthMm;
    }

    public boolean isOneWayOnly() {
        return oneWayOnly;
    }

    public List<Rack> getLeftRacks() {
        return Collections.unmodifiableList(leftRacks);
    }

    public List<Rack> getRightRacks() {
        return Collections.unmodifiableList(rightRacks);
    }

    public void addLeftRack(Rack rack) {
        this.leftRacks.add(rack);
    }

    public void addRightRack(Rack rack) {
        this.rightRacks.add(rack);
    }

    public long lengthMm() {
        return entryCoordinates.manhattanDistanceTo(exitCoordinates);
    }

    public List<Bin> getAllBins() {
        List<Bin> all = new ArrayList<>();
        for (Rack r : leftRacks) all.addAll(r.getBins());
        for (Rack r : rightRacks) all.addAll(r.getBins());
        return all;
    }
}
