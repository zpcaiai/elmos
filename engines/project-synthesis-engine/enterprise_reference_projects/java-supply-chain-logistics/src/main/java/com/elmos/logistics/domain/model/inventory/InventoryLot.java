package com.elmos.logistics.domain.model.inventory;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

/**
 * An inventory lot/batch representing a manufacturing run with expiration and QA traceability.
 */
public class InventoryLot implements Comparable<InventoryLot> {
    private final String lotId;
    private final String skuId;
    private final String lotNumber;
    private final Instant manufacturedDate;
    private final Instant expirationDate;
    private final String supplierId;
    private final String certificateOfAnalysisUrl;
    private final int initialQuantity;

    private int remainingQuantity;
    private boolean quarantined;
    private String quarantineReason;
    private long version;

    public InventoryLot(String lotId,
                        String skuId,
                        String lotNumber,
                        Instant manufacturedDate,
                        Instant expirationDate,
                        String supplierId,
                        String certificateOfAnalysisUrl,
                        int initialQuantity) {
        this.lotId = Objects.requireNonNull(lotId, "lotId must not be null");
        this.skuId = Objects.requireNonNull(skuId, "skuId must not be null");
        this.lotNumber = Objects.requireNonNull(lotNumber, "lotNumber must not be null");
        this.manufacturedDate = Objects.requireNonNull(manufacturedDate, "manufacturedDate must not be null");
        this.expirationDate = Objects.requireNonNull(expirationDate, "expirationDate must not be null");
        this.supplierId = Objects.requireNonNull(supplierId, "supplierId must not be null");
        this.certificateOfAnalysisUrl = certificateOfAnalysisUrl;
        this.initialQuantity = initialQuantity;
        this.remainingQuantity = initialQuantity;
        this.quarantined = false;
        this.quarantineReason = null;
        this.version = 0L;
    }

    public String getLotId() {
        return lotId;
    }

    public String getSkuId() {
        return skuId;
    }

    public String getLotNumber() {
        return lotNumber;
    }

    public Instant getManufacturedDate() {
        return manufacturedDate;
    }

    public Instant getExpirationDate() {
        return expirationDate;
    }

    public String getSupplierId() {
        return supplierId;
    }

    public String getCertificateOfAnalysisUrl() {
        return certificateOfAnalysisUrl;
    }

    public int getInitialQuantity() {
        return initialQuantity;
    }

    public int getRemainingQuantity() {
        return remainingQuantity;
    }

    public boolean isQuarantined() {
        return quarantined;
    }

    public String getQuarantineReason() {
        return quarantineReason;
    }

    public long getVersion() {
        return version;
    }

    public boolean isExpiredAt(Instant now) {
        return now.isAfter(expirationDate);
    }

    public long daysUntilExpiration(Instant now) {
        return ChronoUnit.DAYS.between(now, expirationDate);
    }

    public synchronized void quarantine(String reason) {
        this.quarantined = true;
        this.quarantineReason = Objects.requireNonNull(reason, "Quarantine reason must not be null");
        this.version++;
    }

    public synchronized void releaseQuarantine() {
        this.quarantined = false;
        this.quarantineReason = null;
        this.version++;
    }

    public synchronized void decrementQuantity(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Decrement amount must be positive: " + amount);
        }
        if (amount > this.remainingQuantity) {
            throw new IllegalStateException("Insufficient lot quantity: requested " + amount + " but only " + remainingQuantity + " available");
        }
        this.remainingQuantity -= amount;
        this.version++;
    }

    public synchronized void incrementQuantity(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Increment amount must be positive: " + amount);
        }
        this.remainingQuantity += amount;
        this.version++;
    }

    @Override
    public int compareTo(InventoryLot o) {
        // Default sort by expiration date ascending (FEFO order)
        int cmp = this.expirationDate.compareTo(o.expirationDate);
        if (cmp != 0) return cmp;
        return this.manufacturedDate.compareTo(o.manufacturedDate);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        InventoryLot that = (InventoryLot) o;
        return Objects.equals(lotId, that.lotId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(lotId);
    }

    @Override
    public String toString() {
        return "Lot{" + lotNumber + ", exp=" + expirationDate + ", qty=" + remainingQuantity + "}";
    }
}
