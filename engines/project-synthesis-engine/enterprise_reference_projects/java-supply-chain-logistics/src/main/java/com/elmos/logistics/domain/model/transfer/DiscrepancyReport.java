package com.elmos.logistics.domain.model.transfer;

import java.time.Instant;
import java.util.Objects;

/**
 * Audit record generated when physical receipt at destination warehouse diverges from manifest.
 */
public class DiscrepancyReport {
    private final String reportId;
    private final String transferOrderId;
    private final String lineItemId;
    private final String skuId;
    private final int expectedQuantity;
    private final int actualReceivedQuantity;
    private final int damagedQuantity;
    private final String notes;
    private final Instant reportedAt;

    private boolean resolved;
    private String resolutionAction; // e.g., "WRITE_OFF", "CARRIER_INSURANCE_CLAIM", "RETURN_TO_VENDOR"
    private Instant resolvedAt;

    public DiscrepancyReport(String reportId,
                             String transferOrderId,
                             String lineItemId,
                             String skuId,
                             int expectedQuantity,
                             int actualReceivedQuantity,
                             int damagedQuantity,
                             String notes) {
        this.reportId = Objects.requireNonNull(reportId, "reportId must not be null");
        this.transferOrderId = Objects.requireNonNull(transferOrderId, "transferOrderId must not be null");
        this.lineItemId = Objects.requireNonNull(lineItemId, "lineItemId must not be null");
        this.skuId = Objects.requireNonNull(skuId, "skuId must not be null");
        this.expectedQuantity = expectedQuantity;
        this.actualReceivedQuantity = actualReceivedQuantity;
        this.damagedQuantity = damagedQuantity;
        this.notes = notes;
        this.reportedAt = Instant.now();
        this.resolved = false;
    }

    public String getReportId() {
        return reportId;
    }

    public String getTransferOrderId() {
        return transferOrderId;
    }

    public String getLineItemId() {
        return lineItemId;
    }

    public String getSkuId() {
        return skuId;
    }

    public int getExpectedQuantity() {
        return expectedQuantity;
    }

    public int getActualReceivedQuantity() {
        return actualReceivedQuantity;
    }

    public int getDamagedQuantity() {
        return damagedQuantity;
    }

    public int getDiscrepancyShortage() {
        return expectedQuantity - (actualReceivedQuantity + damagedQuantity);
    }

    public String getNotes() {
        return notes;
    }

    public Instant getReportedAt() {
        return reportedAt;
    }

    public boolean isResolved() {
        return resolved;
    }

    public String getResolutionAction() {
        return resolutionAction;
    }

    public Instant getResolvedAt() {
        return resolvedAt;
    }

    public void resolve(String resolutionAction) {
        this.resolved = true;
        this.resolutionAction = Objects.requireNonNull(resolutionAction, "resolutionAction must not be null");
        this.resolvedAt = Instant.now();
    }
}
