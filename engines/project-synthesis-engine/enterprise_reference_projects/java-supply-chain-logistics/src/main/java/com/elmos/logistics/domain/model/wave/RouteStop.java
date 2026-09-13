package com.elmos.logistics.domain.model.wave;

import com.elmos.logistics.domain.model.common.Coordinates3D;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * A scheduled stop in an optimized picking sequence at a specific warehouse bin.
 */
public class RouteStop {
    private final int sequenceIndex;
    private final String binId;
    private final String aisleCode;
    private final Coordinates3D coordinates;
    private final List<PickItem> itemsToPick;
    private final long distanceFromPreviousMm;

    public RouteStop(int sequenceIndex,
                     String binId,
                     String aisleCode,
                     Coordinates3D coordinates,
                     List<PickItem> itemsToPick,
                     long distanceFromPreviousMm) {
        this.sequenceIndex = sequenceIndex;
        this.binId = Objects.requireNonNull(binId, "binId must not be null");
        this.aisleCode = Objects.requireNonNull(aisleCode, "aisleCode must not be null");
        this.coordinates = Objects.requireNonNull(coordinates, "coordinates must not be null");
        this.itemsToPick = new ArrayList<>(itemsToPick);
        this.distanceFromPreviousMm = distanceFromPreviousMm;
    }

    public int getSequenceIndex() {
        return sequenceIndex;
    }

    public String getBinId() {
        return binId;
    }

    public String getAisleCode() {
        return aisleCode;
    }

    public Coordinates3D getCoordinates() {
        return coordinates;
    }

    public List<PickItem> getItemsToPick() {
        return Collections.unmodifiableList(itemsToPick);
    }

    public long getDistanceFromPreviousMm() {
        return distanceFromPreviousMm;
    }

    public int getTotalUnitsToPick() {
        return itemsToPick.stream().mapToInt(PickItem::getQuantity).sum();
    }
}
