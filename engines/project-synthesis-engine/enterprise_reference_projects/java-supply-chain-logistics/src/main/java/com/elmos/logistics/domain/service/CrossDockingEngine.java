package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.common.StorageClass;

import java.time.Duration;
import java.time.Instant;
import java.util.*;

/**
 * Enterprise Cross-Docking &amp; Flow-Through Transshipment Engine.
 * Matches incoming inbound supplier shipments directly to departing outbound trailers,
 * eliminating intermediate warehouse rack storage, reducing yard dwell time,
 * and minimizing fork-truck transit distance between dock doors.
 */
public class CrossDockingEngine {

    public enum CrossDockType {
        DIRECT_FLOW_THROUGH, // Inbound door directly to outbound door (zero staging)
        STAGED_CROSS_DOCK,   // Short buffer (1-4 hours) in floor staging lane
        OPPORTUNISTIC_MERGE  // Consolidated with existing rack inventory
    }

    public static final class InboundDockPallet {
        private final String palletLpn; // License Plate Number
        private final String sku;
        private final int quantity;
        private final String inboundDoorId;
        private final int dockDoorX;
        private final int dockDoorY;
        private final StorageClass storageClass;
        private final Instant arrivalTime;

        public InboundDockPallet(String palletLpn, String sku, int quantity, String inboundDoorId,
                                 int dockDoorX, int dockDoorY, StorageClass storageClass, Instant arrivalTime) {
            this.palletLpn = Objects.requireNonNull(palletLpn, "palletLpn");
            this.sku = Objects.requireNonNull(sku, "sku");
            this.quantity = quantity;
            this.inboundDoorId = Objects.requireNonNull(inboundDoorId, "inboundDoorId");
            this.dockDoorX = dockDoorX;
            this.dockDoorY = dockDoorY;
            this.storageClass = Objects.requireNonNull(storageClass, "storageClass");
            this.arrivalTime = Objects.requireNonNull(arrivalTime, "arrivalTime");
        }

        public String getPalletLpn() { return palletLpn; }
        public String getSku() { return sku; }
        public int getQuantity() { return quantity; }
        public String getInboundDoorId() { return inboundDoorId; }
        public int getDockDoorX() { return dockDoorX; }
        public int getDockDoorY() { return dockDoorY; }
        public StorageClass getStorageClass() { return storageClass; }
        public Instant getArrivalTime() { return arrivalTime; }
    }

    public static final class OutboundOrderDemand {
        private final String orderId;
        private final String sku;
        private final int demandedQuantity;
        private final String outboundDoorId;
        private final int dockDoorX;
        private final int dockDoorY;
        private final StorageClass requiredStorageClass;
        private final Instant scheduledDepartureEtd;
        private final int priorityScore; // 1 (lowest) to 10 (highest/expedited)

        public OutboundOrderDemand(String orderId, String sku, int demandedQuantity, String outboundDoorId,
                                   int dockDoorX, int dockDoorY, StorageClass requiredStorageClass,
                                   Instant scheduledDepartureEtd, int priorityScore) {
            this.orderId = Objects.requireNonNull(orderId, "orderId");
            this.sku = Objects.requireNonNull(sku, "sku");
            this.demandedQuantity = demandedQuantity;
            this.outboundDoorId = Objects.requireNonNull(outboundDoorId, "outboundDoorId");
            this.dockDoorX = dockDoorX;
            this.dockDoorY = dockDoorY;
            this.requiredStorageClass = Objects.requireNonNull(requiredStorageClass, "requiredStorageClass");
            this.scheduledDepartureEtd = Objects.requireNonNull(scheduledDepartureEtd, "scheduledDepartureEtd");
            this.priorityScore = priorityScore;
        }

        public String getOrderId() { return orderId; }
        public String getSku() { return sku; }
        public int getDemandedQuantity() { return demandedQuantity; }
        public String getOutboundDoorId() { return outboundDoorId; }
        public int getDockDoorX() { return dockDoorX; }
        public int getDockDoorY() { return dockDoorY; }
        public StorageClass getRequiredStorageClass() { return requiredStorageClass; }
        public Instant getScheduledDepartureEtd() { return scheduledDepartureEtd; }
        public int getPriorityScore() { return priorityScore; }
    }

    public static final class CrossDockAssignment {
        private final String assignmentId;
        private final InboundDockPallet inboundPallet;
        private final OutboundOrderDemand outboundOrder;
        private final int allocatedQuantity;
        private final CrossDockType crossDockType;
        private final String stagingLaneId; // null for DIRECT_FLOW_THROUGH
        private final double travelDistanceMeters;
        private final long dwellMinutes;

        public CrossDockAssignment(String assignmentId, InboundDockPallet inboundPallet,
                                   OutboundOrderDemand outboundOrder, int allocatedQuantity,
                                   CrossDockType crossDockType, String stagingLaneId,
                                   double travelDistanceMeters, long dwellMinutes) {
            this.assignmentId = assignmentId;
            this.inboundPallet = inboundPallet;
            this.outboundOrder = outboundOrder;
            this.allocatedQuantity = allocatedQuantity;
            this.crossDockType = crossDockType;
            this.stagingLaneId = stagingLaneId;
            this.travelDistanceMeters = travelDistanceMeters;
            this.dwellMinutes = dwellMinutes;
        }

        public String getAssignmentId() { return assignmentId; }
        public InboundDockPallet getInboundPallet() { return inboundPallet; }
        public OutboundOrderDemand getOutboundOrder() { return outboundOrder; }
        public int getAllocatedQuantity() { return allocatedQuantity; }
        public CrossDockType getCrossDockType() { return crossDockType; }
        public String getStagingLaneId() { return stagingLaneId; }
        public double getTravelDistanceMeters() { return travelDistanceMeters; }
        public long getDwellMinutes() { return dwellMinutes; }
    }

    public static final class CrossDockPlan {
        private final List<CrossDockAssignment> assignments;
        private final List<InboundDockPallet> unassignedInboundPallets;
        private final List<OutboundOrderDemand> unfilledDemands;
        private final int totalUnitsCrossDocked;
        private final double totalForkTruckTravelMeters;
        private final double crossDockFulfillmentRatio;

        public CrossDockPlan(List<CrossDockAssignment> assignments,
                             List<InboundDockPallet> unassignedInboundPallets,
                             List<OutboundOrderDemand> unfilledDemands,
                             int totalUnitsCrossDocked, double totalForkTruckTravelMeters,
                             double crossDockFulfillmentRatio) {
            this.assignments = Collections.unmodifiableList(assignments);
            this.unassignedInboundPallets = Collections.unmodifiableList(unassignedInboundPallets);
            this.unfilledDemands = Collections.unmodifiableList(unfilledDemands);
            this.totalUnitsCrossDocked = totalUnitsCrossDocked;
            this.totalForkTruckTravelMeters = totalForkTruckTravelMeters;
            this.crossDockFulfillmentRatio = crossDockFulfillmentRatio;
        }

        public List<CrossDockAssignment> getAssignments() { return assignments; }
        public List<InboundDockPallet> getUnassignedInboundPallets() { return unassignedInboundPallets; }
        public List<OutboundOrderDemand> getUnfilledDemands() { return unfilledDemands; }
        public int getTotalUnitsCrossDocked() { return totalUnitsCrossDocked; }
        public double getTotalForkTruckTravelMeters() { return totalForkTruckTravelMeters; }
        public double getCrossDockFulfillmentRatio() { return crossDockFulfillmentRatio; }
    }

    /**
     * Solves bipartite assignment matching between inbound dock arrivals and outbound departures.
     */
    public CrossDockPlan planCrossDocking(List<InboundDockPallet> arrivals,
                                         List<OutboundOrderDemand> demands,
                                         Duration maxStagingWindow) {
        Objects.requireNonNull(arrivals, "arrivals");
        Objects.requireNonNull(demands, "demands");
        Duration maxWindow = maxStagingWindow != null ? maxStagingWindow : Duration.ofHours(4);

        // Track remaining quantities
        Map<String, Integer> palletRemainingQty = new HashMap<>();
        for (InboundDockPallet p : arrivals) {
            palletRemainingQty.put(p.getPalletLpn(), p.getQuantity());
        }

        Map<String, Integer> demandUnfilledQty = new HashMap<>();
        int totalDemandedUnits = 0;
        for (OutboundOrderDemand d : demands) {
            demandUnfilledQty.put(d.getOrderId(), d.getDemandedQuantity());
            totalDemandedUnits += d.getDemandedQuantity();
        }

        // Sort demands by priority (high score first) and departure urgency (earlier ETD first)
        List<OutboundOrderDemand> sortedDemands = new ArrayList<>(demands);
        sortedDemands.sort((d1, d2) -> {
            if (d1.getPriorityScore() != d2.getPriorityScore()) {
                return Integer.compare(d2.getPriorityScore(), d1.getPriorityScore());
            }
            return d1.getScheduledDepartureEtd().compareTo(d2.getScheduledDepartureEtd());
        });

        List<CrossDockAssignment> assignments = new ArrayList<>();
        int assignmentSeq = 1;
        double totalTravelMeters = 0.0;
        int totalAllocatedUnits = 0;

        for (OutboundOrderDemand demand : sortedDemands) {
            int needed = demandUnfilledQty.get(demand.getOrderId());
            if (needed <= 0) continue;

            // Find eligible inbound pallets matching SKU, Storage Class, and time window
            List<InboundDockPallet> eligiblePallets = new ArrayList<>();
            for (InboundDockPallet pallet : arrivals) {
                if (!pallet.getSku().equals(demand.getSku())) continue;
                if (palletRemainingQty.get(pallet.getPalletLpn()) <= 0) continue;
                // Storage class compatibility
                if (pallet.getStorageClass() != demand.getRequiredStorageClass()) continue;

                // Time window check: Inbound must arrive before outbound departure
                if (pallet.getArrivalTime().isAfter(demand.getScheduledDepartureEtd())) continue;

                Duration diff = Duration.between(pallet.getArrivalTime(), demand.getScheduledDepartureEtd());
                if (diff.compareTo(maxWindow) <= 0) {
                    eligiblePallets.add(pallet);
                }
            }

            // Sort eligible pallets by dock door proximity (Euclidean distance)
            eligiblePallets.sort(Comparator.comparingDouble(p ->
                    calculateEuclideanDistance(p.getDockDoorX(), p.getDockDoorY(), demand.getDockDoorX(), demand.getDockDoorY())));

            for (InboundDockPallet pallet : eligiblePallets) {
                if (needed <= 0) break;
                int available = palletRemainingQty.get(pallet.getPalletLpn());
                if (available <= 0) continue;

                int transferQty = Math.min(needed, available);
                palletRemainingQty.put(pallet.getPalletLpn(), available - transferQty);
                needed -= transferQty;
                demandUnfilledQty.put(demand.getOrderId(), needed);

                Duration dwell = Duration.between(pallet.getArrivalTime(), demand.getScheduledDepartureEtd());
                long dwellMins = Math.max(0, dwell.toMinutes());

                CrossDockType type;
                String stagingLane = null;
                if (dwellMins <= 30) {
                    type = CrossDockType.DIRECT_FLOW_THROUGH;
                } else {
                    type = CrossDockType.STAGED_CROSS_DOCK;
                    stagingLane = "STAGE-LANE-" + (demand.getDockDoorX() / 10);
                }

                double dist = calculateEuclideanDistance(pallet.getDockDoorX(), pallet.getDockDoorY(),
                        demand.getDockDoorX(), demand.getDockDoorY());
                totalTravelMeters += dist;
                totalAllocatedUnits += transferQty;

                assignments.add(new CrossDockAssignment("CD-" + assignmentSeq++, pallet, demand,
                        transferQty, type, stagingLane, Math.round(dist * 10.0) / 10.0, dwellMins));
            }
        }

        // Identify unassigned arrivals and unfilled demands
        List<InboundDockPallet> unassignedPallets = new ArrayList<>();
        for (InboundDockPallet p : arrivals) {
            if (palletRemainingQty.get(p.getPalletLpn()) > 0) {
                unassignedPallets.add(p);
            }
        }

        List<OutboundOrderDemand> unfilledList = new ArrayList<>();
        for (OutboundOrderDemand d : demands) {
            if (demandUnfilledQty.get(d.getOrderId()) > 0) {
                unfilledList.add(d);
            }
        }

        double ratio = totalDemandedUnits > 0
                ? (double) totalAllocatedUnits / totalDemandedUnits
                : 1.0;

        return new CrossDockPlan(assignments, unassignedPallets, unfilledList,
                totalAllocatedUnits, Math.round(totalTravelMeters * 10.0) / 10.0,
                Math.round(ratio * 1000.0) / 1000.0);
    }

    private double calculateEuclideanDistance(int x1, int y1, int x2, int y2) {
        int dx = x1 - x2;
        int dy = y1 - y2;
        return Math.sqrt((double) dx * dx + (double) dy * dy);
    }
}
