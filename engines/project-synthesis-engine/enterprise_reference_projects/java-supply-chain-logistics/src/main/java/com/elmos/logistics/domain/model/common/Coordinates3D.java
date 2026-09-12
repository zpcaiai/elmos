package com.elmos.logistics.domain.model.common;

import java.util.Objects;

/**
 * Represents a 3-dimensional spatial coordinate in a warehouse grid.
 * All units are in millimeters for integer precision without floating-point inaccuracies.
 */
public final class Coordinates3D implements Comparable<Coordinates3D> {
    private final int xMm; // Aisle axis (lateral)
    private final int yMm; // Bay axis (longitudinal down the aisle)
    private final int zMm; // Shelf tier axis (vertical height)

    public Coordinates3D(int xMm, int yMm, int zMm) {
        if (xMm < 0 || yMm < 0 || zMm < 0) {
            throw new IllegalArgumentException("Warehouse coordinates must be non-negative: (" + xMm + "," + yMm + "," + zMm + ")");
        }
        this.xMm = xMm;
        this.yMm = yMm;
        this.zMm = zMm;
    }

    public static Coordinates3D of(int xMm, int yMm, int zMm) {
        return new Coordinates3D(xMm, yMm, zMm);
    }

    public static Coordinates3D origin() {
        return new Coordinates3D(0, 0, 0);
    }

    public int getXMm() {
        return xMm;
    }

    public int getYMm() {
        return yMm;
    }

    public int getZMm() {
        return zMm;
    }

    /**
     * Calculates the Manhattan (rectilinear) distance between this point and target.
     * In warehouse automated guided vehicles (AGVs) and standard aisle travel,
     * travel is typically rectilinear rather than diagonal.
     */
    public long manhattanDistanceTo(Coordinates3D other) {
        Objects.requireNonNull(other, "Target coordinates must not be null");
        return (long) Math.abs(this.xMm - other.xMm)
                + Math.abs(this.yMm - other.yMm)
                + Math.abs(this.zMm - other.zMm);
    }

    /**
     * Calculates Euclidean distance for aerial/drone picking or line-of-sight analysis.
     */
    public double euclideanDistanceTo(Coordinates3D other) {
        Objects.requireNonNull(other, "Target coordinates must not be null");
        long dx = this.xMm - other.xMm;
        long dy = this.yMm - other.yMm;
        long dz = this.zMm - other.zMm;
        return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }

    /**
     * Calculates travel time for standard material handling equipment.
     * Horizontal transit: 1,500 mm/sec. Vertical hoist: 500 mm/sec.
     */
    public long estimatedTravelTimeMillis(Coordinates3D destination) {
        long horizontalMm = (long) Math.abs(this.xMm - destination.xMm) + Math.abs(this.yMm - destination.yMm);
        long verticalMm = Math.abs(this.zMm - destination.zMm);

        long horizontalTimeMs = (horizontalMm * 1000L) / 1500L;
        long verticalTimeMs = (verticalMm * 1000L) / 500L;
        return Math.max(horizontalTimeMs, verticalTimeMs);
    }

    @Override
    public int compareTo(Coordinates3D o) {
        if (this.xMm != o.xMm) return Integer.compare(this.xMm, o.xMm);
        if (this.yMm != o.yMm) return Integer.compare(this.yMm, o.yMm);
        return Integer.compare(this.zMm, o.zMm);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        Coordinates3D that = (Coordinates3D) o;
        return xMm == that.xMm && yMm == that.yMm && zMm == that.zMm;
    }

    @Override
    public int hashCode() {
        return Objects.hash(xMm, yMm, zMm);
    }

    @Override
    public String toString() {
        return String.format("(%d, %d, %d) mm", xMm, yMm, zMm);
    }
}
