package com.elmos.logistics.domain.model.common;

import java.util.Objects;

/**
 * Immutable weight value representation with milligram internal precision.
 */
public final class Weight implements Comparable<Weight> {
    private final long milligrams;

    public Weight(long milligrams) {
        if (milligrams < 0) {
            throw new IllegalArgumentException("Weight cannot be negative: " + milligrams);
        }
        this.milligrams = milligrams;
    }

    public static Weight ofMilligrams(long mg) {
        return new Weight(mg);
    }

    public static Weight ofGrams(long g) {
        return new Weight(Math.multiplyExact(g, 1000L));
    }

    public static Weight ofKilograms(double kg) {
        if (kg < 0) {
            throw new IllegalArgumentException("Weight cannot be negative: " + kg);
        }
        return new Weight(Math.round(kg * 1_000_000.0));
    }

    public static Weight zero() {
        return new Weight(0);
    }

    public long toMilligrams() {
        return milligrams;
    }

    public long toGrams() {
        return milligrams / 1000L;
    }

    public double toKilograms() {
        return milligrams / 1_000_000.0;
    }

    public double toMetricTons() {
        return milligrams / 1_000_000_000.0;
    }

    public Weight add(Weight other) {
        Objects.requireNonNull(other, "Weight to add must not be null");
        return new Weight(Math.addExact(this.milligrams, other.milligrams));
    }

    public Weight subtract(Weight other) {
        Objects.requireNonNull(other, "Weight to subtract must not be null");
        if (this.milligrams < other.milligrams) {
            throw new IllegalStateException("Cannot subtract greater weight " + other + " from " + this);
        }
        return new Weight(this.milligrams - other.milligrams);
    }

    public Weight multiply(int factor) {
        if (factor < 0) {
            throw new IllegalArgumentException("Factor must be non-negative: " + factor);
        }
        return new Weight(Math.multiplyExact(this.milligrams, factor));
    }

    public boolean isGreaterThan(Weight other) {
        return this.compareTo(other) > 0;
    }

    @Override
    public int compareTo(Weight o) {
        return Long.compare(this.milligrams, o.milligrams);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        Weight weight = (Weight) o;
        return milligrams == weight.milligrams;
    }

    @Override
    public int hashCode() {
        return Objects.hash(milligrams);
    }

    @Override
    public String toString() {
        return String.format("%.3f kg", toKilograms());
    }
}
