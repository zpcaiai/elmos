package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.outbox.OutboxEvent;
import com.elmos.logistics.domain.model.warehouse.Bin;
import com.elmos.logistics.domain.model.warehouse.BinStatus;
import com.elmos.logistics.domain.repository.BinRepository;
import com.elmos.logistics.domain.repository.OutboxRepository;
import com.elmos.logistics.domain.repository.StockUnitRepository;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Cycle Count & Physical Inventory Audit Service.
 * Implements ABC inventory cycle counting, bin-level freeze locks, and variance accounting.
 */
public class CycleCountReconciliationService {
    private final BinRepository binRepository;
    private final StockUnitRepository stockUnitRepository;
    private final OutboxRepository outboxRepository;

    public static class CycleCountVariance {
        private final String binId;
        private final int systemRecordedUnits;
        private final int physicalCountedUnits;
        private final int varianceUnits;
        private final String auditorNotes;

        public CycleCountVariance(String binId, int systemRecordedUnits, int physicalCountedUnits, String auditorNotes) {
            this.binId = binId;
            this.systemRecordedUnits = systemRecordedUnits;
            this.physicalCountedUnits = physicalCountedUnits;
            this.varianceUnits = physicalCountedUnits - systemRecordedUnits;
            this.auditorNotes = auditorNotes;
        }

        public String getBinId() {
            return binId;
        }

        public int getSystemRecordedUnits() {
            return systemRecordedUnits;
        }

        public int getPhysicalCountedUnits() {
            return physicalCountedUnits;
        }

        public int getVarianceUnits() {
            return varianceUnits;
        }

        public String getAuditorNotes() {
            return auditorNotes;
        }

        public boolean hasDiscrepancy() {
            return varianceUnits != 0;
        }
    }

    public CycleCountReconciliationService(BinRepository binRepository,
                                          StockUnitRepository stockUnitRepository,
                                          OutboxRepository outboxRepository) {
        this.binRepository = Objects.requireNonNull(binRepository, "binRepository must not be null");
        this.stockUnitRepository = Objects.requireNonNull(stockUnitRepository, "stockUnitRepository must not be null");
        this.outboxRepository = Objects.requireNonNull(outboxRepository, "outboxRepository must not be null");
    }

    /**
     * Locks a list of bins for an ongoing cycle count to prevent concurrent picks or putaways.
     */
    public synchronized void lockBinsForCycleCount(List<String> binIds) {
        for (String binId : binIds) {
            binRepository.findById(binId).ifPresent(bin -> {
                bin.lockForCycleCount();
                binRepository.save(bin);
            });
        }
    }

    /**
     * Submits physical counts, compares against system records, and generates variance reports.
     */
    public synchronized List<CycleCountVariance> reconcileCounts(String warehouseId,
                                                                String auditorWorkerId,
                                                                List<BinCountSubmission> counts) {
        List<CycleCountVariance> variances = new ArrayList<>();

        for (BinCountSubmission sub : counts) {
            Bin bin = binRepository.findById(sub.binId)
                    .orElseThrow(() -> new IllegalArgumentException("Bin not found: " + sub.binId));

            int systemUnits = bin.getOccupiedStockUnitIds().size();
            CycleCountVariance variance = new CycleCountVariance(sub.binId, systemUnits, sub.countedUnits, sub.notes);
            variances.add(variance);

            if (variance.hasDiscrepancy()) {
                recordCycleCountDiscrepancyEvent(warehouseId, auditorWorkerId, variance);
            }

            // Unlock bin after audit submission
            bin.releaseCycleCount();
            binRepository.save(bin);
        }

        return variances;
    }

    private void recordCycleCountDiscrepancyEvent(String warehouseId, String auditorWorkerId, CycleCountVariance variance) {
        String eventId = UUID.randomUUID().toString();
        String payload = String.format("{\"warehouseId\":\"%s\",\"auditor\":\"%s\",\"binId\":\"%s\",\"systemUnits\":%d,\"countedUnits\":%d,\"variance\":%d}",
                warehouseId, auditorWorkerId, variance.getBinId(), variance.getSystemRecordedUnits(), variance.getPhysicalCountedUnits(), variance.getVarianceUnits());
        OutboxEvent event = new OutboxEvent(eventId, "default_tenant", "CycleCount", variance.getBinId(), "CYCLE_COUNT_VARIANCE_DETECTED", payload);
        outboxRepository.save(event);
    }

    public static class BinCountSubmission {
        public final String binId;
        public final int countedUnits;
        public final String notes;

        public BinCountSubmission(String binId, int countedUnits, String notes) {
            this.binId = binId;
            this.countedUnits = countedUnits;
            this.notes = notes;
        }
    }
}
