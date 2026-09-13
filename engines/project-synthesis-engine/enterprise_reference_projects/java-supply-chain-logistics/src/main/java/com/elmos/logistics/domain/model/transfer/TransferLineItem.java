package com.elmos.logistics.domain.model.transfer;

import java.util.Objects;

/**
 * A line item within a stock transfer order tracking requested, shipped, and received quantities.
 */
public class TransferLineItem {
    private final String lineItemId;
    private final String skuId;
    private final String lotId;
    private final int requestedQuantity;

    private int shippedQuantity;
    private int receivedQuantity;
    private int damagedQuantity;

    public TransferLineItem(String lineItemId, String skuId, String lotId, int requestedQuantity) {
        if (requestedQuantity <= 0) {
            throw new IllegalArgumentException("Requested quantity must be strictly positive: " + requestedQuantity);
        }
        this.lineItemId = Objects.requireNonNull(lineItemId, "lineItemId must not be null");
        this.skuId = Objects.requireNonNull(skuId, "skuId must not be null");
        this.lotId = Objects.requireNonNull(lotId, "lotId must not be null");
        this.requestedQuantity = requestedQuantity;
        this.shippedQuantity = 0;
        this.receivedQuantity = 0;
        this.damagedQuantity = 0;
    }

    public String getLineItemId() {
        return lineItemId;
    }

    public String getSkuId() {
        return skuId;
    }

    public String getLotId() {
        return lotId;
    }

    public int getRequestedQuantity() {
        return requestedQuantity;
    }

    public int getShippedQuantity() {
        return shippedQuantity;
    }

    public int getReceivedQuantity() {
        return receivedQuantity;
    }

    public int getDamagedQuantity() {
        return damagedQuantity;
    }

    public void setShippedQuantity(int quantity) {
        if (quantity < 0) throw new IllegalArgumentException("Shipped quantity cannot be negative");
        this.shippedQuantity = quantity;
    }

    public void recordReceipt(int goodQuantity, int damagedQty) {
        if (goodQuantity < 0 || damagedQty < 0) {
            throw new IllegalArgumentException("Received quantities cannot be negative");
        }
        this.receivedQuantity = goodQuantity;
        this.damagedQuantity = damagedQty;
    }

    public int getVarianceQuantity() {
        return (receivedQuantity + damagedQuantity) - shippedQuantity;
    }

    public boolean hasDiscrepancy() {
        return getVarianceQuantity() != 0 || damagedQuantity > 0;
    }
}
