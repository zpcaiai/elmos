package com.elmos.logistics;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.StorageClass;
import com.elmos.logistics.domain.model.common.Weight;
import com.elmos.logistics.domain.model.warehouse.Bin;
import com.elmos.logistics.domain.model.warehouse.BinStatus;
import com.elmos.logistics.domain.service.CycleCountReconciliationService;
import com.elmos.logistics.infrastructure.persistence.InMemoryBinRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryOutboxRepository;
import com.elmos.logistics.infrastructure.persistence.InMemoryStockUnitRepository;

import java.util.Collections;
import java.util.List;

public class CycleCountReconciliationTest {
    public static void runTests() {
        System.out.println("Running CycleCountReconciliationTest...");
        testCycleCountAuditAndLocking();
        System.out.println("  ✓ CycleCountReconciliationTest passed successfully.");
    }

    private static void testCycleCountAuditAndLocking() {
        InMemoryBinRepository binRepo = new InMemoryBinRepository();
        InMemoryStockUnitRepository stockRepo = new InMemoryStockUnitRepository();
        InMemoryOutboxRepository outboxRepo = new InMemoryOutboxRepository();

        CycleCountReconciliationService service = new CycleCountReconciliationService(binRepo, stockRepo, outboxRepo);

        String binId = "BIN-AUDIT-01";
        Bin bin = new Bin(binId, "WH-1", "Z-1", "A-1", 1, 1, 1, Coordinates3D.origin(),
                Dimensions.of(1000, 1000, 1000), Weight.ofKilograms(500), StorageClass.STANDARD_AMBIENT);
        binRepo.save(bin);

        // Put 10 units in bin
        for (int i = 0; i < 10; i++) {
            bin.placeStockUnit("U-" + i, Dimensions.of(100, 100, 100), Weight.ofGrams(100), StorageClass.STANDARD_AMBIENT);
        }
        binRepo.save(bin);

        // Lock for audit
        service.lockBinsForCycleCount(Collections.singletonList(binId));
        Bin lockedBin = binRepo.findById(binId).orElseThrow();
        if (lockedBin.getStatus() != BinStatus.BLOCKED_FOR_CYCLE_COUNT) {
            throw new AssertionError("Expected bin to be BLOCKED_FOR_CYCLE_COUNT");
        }

        // Auditor discovers only 9 physical units (1 unit shrinkage)
        List<CycleCountReconciliationService.BinCountSubmission> counts = Collections.singletonList(
                new CycleCountReconciliationService.BinCountSubmission(binId, 9, "One unit packaging damaged/lost")
        );

        List<CycleCountReconciliationService.CycleCountVariance> variances = service.reconcileCounts("WH-1", "WORKER-AUDIT", counts);

        if (variances.size() != 1) throw new AssertionError("Expected 1 variance");
        CycleCountReconciliationService.CycleCountVariance var = variances.get(0);

        if (var.getSystemRecordedUnits() != 10) throw new AssertionError("Expected 10 system recorded");
        if (var.getPhysicalCountedUnits() != 9) throw new AssertionError("Expected 9 physical counted");
        if (var.getVarianceUnits() != -1) throw new AssertionError("Expected -1 variance");

        // Verify bin unlocked
        Bin unlockedBin = binRepo.findById(binId).orElseThrow();
        if (unlockedBin.getStatus() == BinStatus.BLOCKED_FOR_CYCLE_COUNT) {
            throw new AssertionError("Bin must be unlocked after reconciliation");
        }
    }
}
