package com.elmos.logistics.domain.model.wave;

import com.elmos.logistics.domain.model.common.Coordinates3D;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * An ordered sequence of pick stops minimizing travel distance and pick completion duration.
 */
public class PickPath {
    private final Coordinates3D originCoordinates;
    private final Coordinates3D destinationCoordinates;
    private final List<RouteStop> stops;
    private final long totalDistanceMm;
    private final long estimatedDurationSeconds;

    public PickPath(Coordinates3D originCoordinates,
                    Coordinates3D destinationCoordinates,
                    List<RouteStop> stops,
                    long totalDistanceMm,
                    long estimatedDurationSeconds) {
        this.originCoordinates = Objects.requireNonNull(originCoordinates, "originCoordinates must not be null");
        this.destinationCoordinates = Objects.requireNonNull(destinationCoordinates, "destinationCoordinates must not be null");
        this.stops = new ArrayList<>(stops);
        this.totalDistanceMm = totalDistanceMm;
        this.estimatedDurationSeconds = estimatedDurationSeconds;
    }

    public Coordinates3D getOriginCoordinates() {
        return originCoordinates;
    }

    public Coordinates3D getDestinationCoordinates() {
        return destinationCoordinates;
    }

    public List<RouteStop> getStops() {
        return Collections.unmodifiableList(stops);
    }

    public long getTotalDistanceMm() {
        return totalDistanceMm;
    }

    public double getTotalDistanceMeters() {
        return totalDistanceMm / 1000.0;
    }

    public long getEstimatedDurationSeconds() {
        return estimatedDurationSeconds;
    }

    public int getStopCount() {
        return stops.size();
    }

    public int getTotalUnits() {
        return stops.stream().mapToInt(RouteStop::getTotalUnitsToPick).sum();
    }
}
