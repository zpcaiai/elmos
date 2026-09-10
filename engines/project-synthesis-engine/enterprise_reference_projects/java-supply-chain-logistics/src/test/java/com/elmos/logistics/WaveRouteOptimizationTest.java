package com.elmos.logistics;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.StorageClass;
import com.elmos.logistics.domain.model.common.Weight;
import com.elmos.logistics.domain.model.warehouse.Bin;
import com.elmos.logistics.domain.model.wave.PickItem;
import com.elmos.logistics.domain.model.wave.PickPath;
import com.elmos.logistics.domain.service.WaveRouteOptimizationService;
import com.elmos.logistics.infrastructure.persistence.InMemoryBinRepository;

import java.util.ArrayList;
import java.util.List;

public class WaveRouteOptimizationTest {
    public static void runTests() {
        System.out.println("Running WaveRouteOptimizationTest...");
        testCoordinatesDistance();
        testTspRouteOptimizationReducesDistance();
        System.out.println("  ✓ WaveRouteOptimizationTest passed successfully.");
    }

    private static void testCoordinatesDistance() {
        Coordinates3D p1 = Coordinates3D.of(1000, 2000, 500);
        Coordinates3D p2 = Coordinates3D.of(4000, 6000, 1500);

        long manhattan = p1.manhattanDistanceTo(p2);
        // |1000-4000| + |2000-6000| + |500-1500| = 3000 + 4000 + 1000 = 8000 mm
        if (manhattan != 8000L) {
            throw new AssertionError("Expected Manhattan distance 8000, got: " + manhattan);
        }

        double euclidean = p1.euclideanDistanceTo(p2);
        // sqrt(3000^2 + 4000^2 + 1000^2) = sqrt(9M + 16M + 1M) = sqrt(26M) ≈ 5099.019
        if (Math.abs(euclidean - 5099.019) > 0.01) {
            throw new AssertionError("Expected Euclidean distance ~5099.02, got: " + euclidean);
        }
    }

    private static void testTspRouteOptimizationReducesDistance() {
        InMemoryBinRepository binRepo = new InMemoryBinRepository();
        WaveRouteOptimizationService routeService = new WaveRouteOptimizationService(binRepo);

        Coordinates3D depot = Coordinates3D.of(0, 0, 0);
        Coordinates3D packStation = Coordinates3D.of(100000, 0, 0);

        // Create 6 bins located along different aisles
        Coordinates3D[] coords = new Coordinates3D[]{
                Coordinates3D.of(10000, 50000, 1000),  // Stop 1
                Coordinates3D.of(80000, 20000, 1200),  // Stop 2
                Coordinates3D.of(20000, 48000, 800),   // Stop 3 (close to Stop 1)
                Coordinates3D.of(75000, 22000, 1500),  // Stop 4 (close to Stop 2)
                Coordinates3D.of(30000, 45000, 1000),  // Stop 5
                Coordinates3D.of(85000, 18000, 600),   // Stop 6
        };

        List<PickItem> items = new ArrayList<>();
        for (int i = 0; i < coords.length; i++) {
            String binId = "BIN-" + (i + 1);
            Bin bin = new Bin(binId, "WH-1", "Z-1", "A-" + (i + 1), i, 1, 1, coords[i],
                    Dimensions.of(1000, 1000, 1000), Weight.ofKilograms(500), StorageClass.STANDARD_AMBIENT);
            binRepo.save(bin);

            items.add(new PickItem("PI-" + i, "TASK-1", "ORD-1", "UNIT-" + i, "SKU-A", binId, coords[i], 1));
        }

        // Calculate naive unoptimized route distance: depot -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> packStation
        long naiveDistance = 0;
        Coordinates3D curr = depot;
        for (Coordinates3D c : coords) {
            naiveDistance += curr.manhattanDistanceTo(c);
            curr = c;
        }
        naiveDistance += curr.manhattanDistanceTo(packStation);

        // Run TSP Optimization
        PickPath optimized = routeService.optimizePickRoute(depot, packStation, items);

        if (optimized.getStops().size() != 6) {
            throw new AssertionError("Expected 6 stops, got " + optimized.getStops().size());
        }

        // The optimized route should visit clusters together (1,3,5 then 4,2,6) and beat naive zig-zag distance
        long optimizedDistance = optimized.getTotalDistanceMm();
        if (optimizedDistance >= naiveDistance) {
            throw new AssertionError("Expected TSP optimization to reduce distance: naive=" + naiveDistance + ", optimized=" + optimizedDistance);
        }

        if (optimized.getEstimatedDurationSeconds() <= 0) {
            throw new AssertionError("Estimated duration must be positive");
        }
    }
}
