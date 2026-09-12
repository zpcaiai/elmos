package com.elmos.logistics.domain.model.common;

/**
 * Material storage classification indicating environmental and security segregation.
 */
public enum StorageClass {
    STANDARD_AMBIENT(false, false, false),
    TEMPERATURE_CONTROLLED(true, false, false),
    COLD_CHILLED(true, false, false),
    FROZEN_DEEP(true, false, false),
    HAZMAT_FLAMMABLE(false, true, false),
    HAZMAT_CORROSIVE(false, true, false),
    HIGH_VALUE_VAULT(false, false, true),
    BULK_OVERSIZED(false, false, false);

    private final boolean requiresClimateControl;
    private final boolean isHazardous;
    private final boolean requiresHighSecurity;

    StorageClass(boolean requiresClimateControl, boolean isHazardous, boolean requiresHighSecurity) {
        this.requiresClimateControl = requiresClimateControl;
        this.isHazardous = isHazardous;
        this.requiresHighSecurity = requiresHighSecurity;
    }

    public boolean isRequiresClimateControl() {
        return requiresClimateControl;
    }

    public boolean isHazardous() {
        return isHazardous;
    }

    public boolean isRequiresHighSecurity() {
        return requiresHighSecurity;
    }

    /**
     * Checks whether two storage classes can be co-located in the same warehouse zone/aisle.
     * Hazardous materials must never be stored alongside standard foodstuffs or high-value vaults.
     */
    public boolean isCompatibleForCoLocation(StorageClass other) {
        if (this == other) return true;
        if (this.isHazardous || other.isHazardous) return false;
        if (this.requiresHighSecurity || other.requiresHighSecurity) return false;
        if (this.requiresClimateControl != other.requiresClimateControl) return false;
        return true;
    }
}
