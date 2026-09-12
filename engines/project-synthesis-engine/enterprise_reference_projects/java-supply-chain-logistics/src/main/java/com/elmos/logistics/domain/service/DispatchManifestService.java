package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.Money;
import com.elmos.logistics.domain.model.common.Weight;
import com.elmos.logistics.domain.model.dispatch.CarrierConsignment;
import com.elmos.logistics.domain.model.dispatch.DeliveryStatus;
import com.elmos.logistics.domain.model.dispatch.ShipmentDispatch;
import com.elmos.logistics.domain.model.dispatch.TrackingMilestone;
import com.elmos.logistics.domain.model.inventory.StockUnit;
import com.elmos.logistics.domain.model.outbox.OutboxEvent;
import com.elmos.logistics.domain.repository.OutboxRepository;
import com.elmos.logistics.domain.repository.StockUnitRepository;

import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Dispatch Manifest Service managing outbound packing, dimensional weight calculation,
 * carrier consignment assignment, and dock staging.
 */
public class DispatchManifestService {
    private final StockUnitRepository stockUnitRepository;
    private final OutboxRepository outboxRepository;

    public DispatchManifestService(StockUnitRepository stockUnitRepository, OutboxRepository outboxRepository) {
        this.stockUnitRepository = Objects.requireNonNull(stockUnitRepository, "stockUnitRepository must not be null");
        this.outboxRepository = Objects.requireNonNull(outboxRepository, "outboxRepository must not be null");
    }

    public ShipmentDispatch createAndPackShipment(String dispatchId,
                                                  String tenantId,
                                                  String warehouseId,
                                                  String orderId,
                                                  String recipientName,
                                                  String destinationAddress,
                                                  List<ShipmentDispatch.PackedBox> boxes,
                                                  String carrierCode,
                                                  String serviceLevel,
                                                  String trackingNumber,
                                                  Money freightCost) {
        ShipmentDispatch dispatch = new ShipmentDispatch(dispatchId, tenantId, warehouseId, orderId, recipientName, destinationAddress);

        for (ShipmentDispatch.PackedBox box : boxes) {
            dispatch.addPackedBox(box);
            // Transition stock units to PACKED
            for (String unitId : box.getStockUnitIds()) {
                stockUnitRepository.findById(unitId).ifPresent(unit -> {
                    unit.recordPacked();
                    stockUnitRepository.save(unit);
                });
            }
        }

        Weight totalBillableWeight = dispatch.getTotalBillableWeight();
        CarrierConsignment consignment = new CarrierConsignment(
                UUID.randomUUID().toString(),
                carrierCode,
                serviceLevel,
                trackingNumber,
                totalBillableWeight,
                freightCost
        );

        consignment.addMilestone(new TrackingMilestone(
                UUID.randomUUID().toString(),
                Instant.now(),
                warehouseId,
                DeliveryStatus.MANIFESTED,
                "Shipping label generated at warehouse fulfillment dock."
        ));

        dispatch.assignConsignment(consignment);
        return dispatch;
    }

    public void dispatchShipment(ShipmentDispatch shipment) {
        shipment.dispatch();

        // Mark stock units as shipped
        for (ShipmentDispatch.PackedBox box : shipment.getPackedBoxes()) {
            for (String unitId : box.getStockUnitIds()) {
                stockUnitRepository.findById(unitId).ifPresent(unit -> {
                    unit.recordShipped();
                    stockUnitRepository.save(unit);
                });
            }
        }

        shipment.getConsignment().addMilestone(new TrackingMilestone(
                UUID.randomUUID().toString(),
                Instant.now(),
                shipment.getWarehouseId(),
                DeliveryStatus.TENDERED_TO_CARRIER,
                "Loaded onto carrier departure vehicle."
        ));

        // Record outbox event
        String eventId = UUID.randomUUID().toString();
        String payload = String.format("{\"dispatchId\":\"%s\",\"orderId\":\"%s\",\"carrier\":\"%s\",\"trackingNumber\":\"%s\",\"weightKg\":%.2f}",
                shipment.getDispatchId(), shipment.getOrderId(), shipment.getConsignment().getCarrierCode(),
                shipment.getConsignment().getTrackingNumber(), shipment.getTotalBillableWeight().toKilograms());
        OutboxEvent event = new OutboxEvent(eventId, shipment.getTenantId(), "ShipmentDispatch", shipment.getDispatchId(), "SHIPMENT_DISPATCHED", payload);
        outboxRepository.save(event);
    }
}
