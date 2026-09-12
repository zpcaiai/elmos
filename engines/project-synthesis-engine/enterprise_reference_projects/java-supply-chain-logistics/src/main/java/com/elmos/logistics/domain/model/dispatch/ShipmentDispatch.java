package com.elmos.logistics.domain.model.dispatch;

import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.Weight;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * Aggregate root for an outbound shipment dispatched from a warehouse loading bay.
 */
public class ShipmentDispatch {
    private final String dispatchId;
    private final String tenantId;
    private final String warehouseId;
    private final String orderId;
    private final String recipientName;
    private final String destinationAddress;
    private final Instant createdAt;
    private final List<PackedBox> packedBoxes;

    private CarrierConsignment consignment;
    private boolean dispatched;
    private Instant dispatchedAt;

    public static class PackedBox {
        private final String boxBarcode;
        private final Dimensions dimensions;
        private final Weight grossWeight;
        private final List<String> stockUnitIds;

        public PackedBox(String boxBarcode, Dimensions dimensions, Weight grossWeight, List<String> stockUnitIds) {
            this.boxBarcode = Objects.requireNonNull(boxBarcode, "boxBarcode must not be null");
            this.dimensions = Objects.requireNonNull(dimensions, "dimensions must not be null");
            this.grossWeight = Objects.requireNonNull(grossWeight, "grossWeight must not be null");
            this.stockUnitIds = new ArrayList<>(stockUnitIds);
        }

        public String getBoxBarcode() {
            return boxBarcode;
        }

        public Dimensions getDimensions() {
            return dimensions;
        }

        public Weight getGrossWeight() {
            return grossWeight;
        }

        public List<String> getStockUnitIds() {
            return Collections.unmodifiableList(stockUnitIds);
        }

        /**
         * Dimensional weight calculation (IATA standard: length*width*height / 5000 in cm/kg).
         */
        public Weight calculateDimensionalWeight() {
            double volumeCubicMeters = dimensions.volumeCubicMeters();
            // 1 cubic meter = 200 kg dimensional weight (standard 1:5 ratio)
            double dimWeightKg = volumeCubicMeters * 200.0;
            return Weight.ofKilograms(dimWeightKg);
        }

        public Weight getBillableWeight() {
            Weight dimWeight = calculateDimensionalWeight();
            return grossWeight.isGreaterThan(dimWeight) ? grossWeight : dimWeight;
        }
    }

    public ShipmentDispatch(String dispatchId,
                            String tenantId,
                            String warehouseId,
                            String orderId,
                            String recipientName,
                            String destinationAddress) {
        this.dispatchId = Objects.requireNonNull(dispatchId, "dispatchId must not be null");
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId must not be null");
        this.warehouseId = Objects.requireNonNull(warehouseId, "warehouseId must not be null");
        this.orderId = Objects.requireNonNull(orderId, "orderId must not be null");
        this.recipientName = Objects.requireNonNull(recipientName, "recipientName must not be null");
        this.destinationAddress = Objects.requireNonNull(destinationAddress, "destinationAddress must not be null");
        this.createdAt = Instant.now();
        this.packedBoxes = new ArrayList<>();
        this.dispatched = false;
    }

    public String getDispatchId() {
        return dispatchId;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getWarehouseId() {
        return warehouseId;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getRecipientName() {
        return recipientName;
    }

    public String getDestinationAddress() {
        return destinationAddress;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public List<PackedBox> getPackedBoxes() {
        return Collections.unmodifiableList(packedBoxes);
    }

    public CarrierConsignment getConsignment() {
        return consignment;
    }

    public boolean isDispatched() {
        return dispatched;
    }

    public Instant getDispatchedAt() {
        return dispatchedAt;
    }

    public void addPackedBox(PackedBox box) {
        if (dispatched) {
            throw new IllegalStateException("Cannot add boxes to already dispatched shipment");
        }
        this.packedBoxes.add(Objects.requireNonNull(box, "PackedBox must not be null"));
    }

    public void assignConsignment(CarrierConsignment consignment) {
        this.consignment = Objects.requireNonNull(consignment, "Consignment must not be null");
    }

    public void dispatch() {
        if (packedBoxes.isEmpty()) {
            throw new IllegalStateException("Cannot dispatch empty shipment without packed boxes");
        }
        if (consignment == null) {
            throw new IllegalStateException("Cannot dispatch without an assigned carrier consignment");
        }
        this.dispatched = true;
        this.dispatchedAt = Instant.now();
    }

    public Weight getTotalBillableWeight() {
        Weight total = Weight.zero();
        for (PackedBox box : packedBoxes) {
            total = total.add(box.getBillableWeight());
        }
        return total;
    }
}
