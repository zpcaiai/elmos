package com.elmos.logistics.domain.model.common;

import java.util.Objects;

/**
 * Temperature compliance range in Celsius (with 0.1 degree precision).
 */
public final class TemperatureRange {
    private final double minCelsius;
    private final double maxCelsius;

    public TemperatureRange(double minCelsius, double maxCelsius) {
        if (minCelsius > maxCelsius) {
            throw new IllegalArgumentException("Min temp (" + minCelsius + "°C) cannot exceed max temp (" + maxCelsius + "°C)");
        }
        this.minCelsius = minCelsius;
        this.maxCelsius = maxCelsius;
    }

    public static TemperatureRange ambient() {
        return new TemperatureRange(15.0, 25.0);
    }

    public static TemperatureRange coldChilled() {
        return new TemperatureRange(2.0, 8.0);
    }

    public static TemperatureRange frozenDeep() {
        return new TemperatureRange(-25.0, -18.0);
    }

    public static TemperatureRange cryogenic() {
        return new TemperatureRange(-196.0, -80.0);
    }

    public double getMinCelsius() {
        return minCelsius;
    }

    public double getMaxCelsius() {
        return maxCelsius;
    }

    /**
     * Checks if a recorded ambient temperature complies with this range.
     */
    public boolean contains(double tempCelsius) {
        return tempCelsius >= minCelsius && tempCelsius <= maxCelsius;
    }

    /**
     * Checks if an environmental zone satisfies the storage requirement of this product.
     */
    public boolean isCompatibleWith(TemperatureRange environmentZone) {
        Objects.requireNonNull(environmentZone, "Environment zone must not be null");
        return environmentZone.minCelsius >= this.minCelsius && environmentZone.maxCelsius <= this.maxCelsius;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        TemperatureRange that = (TemperatureRange) o;
        return Double.compare(that.minCelsius, minCelsius) == 0 && Double.compare(that.maxCelsius, maxCelsius) == 0;
    }

    @Override
    public int hashCode() {
        return Objects.hash(minCelsius, maxCelsius);
    }

    @Override
    public String toString() {
        return String.format("[%.1f°C to %.1f°C]", minCelsius, maxCelsius);
    }
}
