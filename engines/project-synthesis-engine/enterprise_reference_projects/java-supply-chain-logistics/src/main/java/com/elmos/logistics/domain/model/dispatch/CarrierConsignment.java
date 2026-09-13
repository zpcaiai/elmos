package com.elmos.logistics.domain.model.dispatch;

import com.elmos.logistics.domain.model.common.Money;
import com.elmos.logistics.domain.model.common.Weight;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * Commercial contract with a logistics freight carrier for physical shipment transit.
 */
public class CarrierConsignment {
    private final String consignmentId;
    private final String carrierCode; // e.g. "DHL_EXPRESS", "FEDEX_GROUND", "UPS_FREIGHT"
    private final String serviceLevel; // e.g. "PRIORITY_OVERNIGHT", "ECONOMY"
    private final String trackingNumber;
    private final Weight billableWeight;
    private final Money freightCost;
    private final List<TrackingMilestone> milestones;

    private DeliveryStatus currentStatus;
    private Instant deliveredAt;

    public CarrierConsignment(String consignmentId,
                              String carrierCode,
                              String serviceLevel,
                              String trackingNumber,
                              Weight billableWeight,
                              Money freightCost) {
        this.consignmentId = Objects.requireNonNull(consignmentId, "consignmentId must not be null");
        this.carrierCode = Objects.requireNonNull(carrierCode, "carrierCode must not be null");
        this.serviceLevel = Objects.requireNonNull(serviceLevel, "serviceLevel must not be null");
        this.trackingNumber = Objects.requireNonNull(trackingNumber, "trackingNumber must not be null");
        this.billableWeight = Objects.requireNonNull(billableWeight, "billableWeight must not be null");
        this.freightCost = Objects.requireNonNull(freightCost, "freightCost must not be null");
        this.milestones = new ArrayList<>();
        this.currentStatus = DeliveryStatus.MANIFESTED;
    }

    public String getConsignmentId() {
        return consignmentId;
    }

    public String getCarrierCode() {
        return carrierCode;
    }

    public String getServiceLevel() {
        return serviceLevel;
    }

    public String getTrackingNumber() {
        return trackingNumber;
    }

    public Weight getBillableWeight() {
        return billableWeight;
    }

    public Money getFreightCost() {
        return freightCost;
    }

    public List<TrackingMilestone> getMilestones() {
        return Collections.unmodifiableList(milestones);
    }

    public DeliveryStatus getCurrentStatus() {
        return currentStatus;
    }

    public Instant getDeliveredAt() {
        return deliveredAt;
    }

    public void addMilestone(TrackingMilestone milestone) {
        Objects.requireNonNull(milestone, "Milestone must not be null");
        this.milestones.add(milestone);
        this.currentStatus = milestone.getStatus();
        if (this.currentStatus == DeliveryStatus.DELIVERED) {
            this.deliveredAt = milestone.getTimestamp();
        }
    }
}
