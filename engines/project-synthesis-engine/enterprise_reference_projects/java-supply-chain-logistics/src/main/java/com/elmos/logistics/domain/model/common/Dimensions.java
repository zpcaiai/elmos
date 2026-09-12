package com.elmos.logistics.domain.model.common;

import java.util.Objects;

/**
 * Physical bounding box dimensions in millimeters.
 */
public final class Dimensions {
    private final int lengthMm;
    private final int widthMm;
    private final int heightMm;

    public Dimensions(int lengthMm, int widthMm, int heightMm) {
        if (lengthMm <= 0 || widthMm <= 0 || heightMm <= 0) {
            throw new IllegalArgumentException("All dimensions must be strictly positive: " + lengthMm + "x" + widthMm + "x" + heightMm);
        }
        this.lengthMm = lengthMm;
        this.widthMm = widthMm;
        this.heightMm = heightMm;
    }

    public static Dimensions of(int lengthMm, int widthMm, int heightMm) {
        return new Dimensions(lengthMm, widthMm, heightMm);
    }

    public int getLengthMm() {
        return lengthMm;
    }

    public int getWidthMm() {
        return widthMm;
    }

    public int getHeightMm() {
        return heightMm;
    }

    /**
     * Volume in cubic millimeters.
     */
    public long volumeCubicMm() {
        return (long) lengthMm * widthMm * heightMm;
    }

    /**
     * Volume in cubic meters (standard for freight and storage calculation).
     */
    public double volumeCubicMeters() {
        return volumeCubicMm() / 1_000_000_000.0;
    }

    /**
     * Checks if this item can fit into the given container dimensions in standard orientation.
     */
    public boolean fitsWithin(Dimensions container) {
        Objects.requireNonNull(container, "Container dimensions must not be null");
        return this.lengthMm <= container.lengthMm
                && this.widthMm <= container.widthMm
                && this.heightMm <= container.heightMm;
    }

    /**
     * Checks if item can fit into container with any 3D rotation (6 degrees of freedom).
     */
    public boolean fitsWithRotation(Dimensions container) {
        Objects.requireNonNull(container, "Container dimensions must not be null");
        int[] itemDims = new int[]{lengthMm, widthMm, heightMm};
        int[] boxDims = new int[]{container.lengthMm, container.widthMm, container.heightMm};
        java.util.Arrays.sort(itemDims);
        java.util.Arrays.sort(boxDims);
        return itemDims[0] <= boxDims[0] && itemDims[1] <= boxDims[1] && itemDims[2] <= boxDims[2];
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        Dimensions that = (Dimensions) o;
        return lengthMm == that.lengthMm && widthMm == that.widthMm && heightMm == that.heightMm;
    }

    @Override
    public int hashCode() {
        return Objects.hash(lengthMm, widthMm, heightMm);
    }

    @Override
    public String toString() {
        return String.format("%dx%dx%d mm (%.4f m³)", lengthMm, widthMm, heightMm, volumeCubicMeters());
    }
}
