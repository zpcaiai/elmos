package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.warehouse.Bin;
import com.elmos.logistics.domain.model.wave.PickItem;
import com.elmos.logistics.domain.model.wave.PickPath;
import com.elmos.logistics.domain.model.wave.RouteStop;
import com.elmos.logistics.domain.repository.BinRepository;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Wave Route Optimization Engine solving the Warehouse Traveling Salesperson Problem (TSP).
 * Employs Nearest Neighbor construction followed by 2-Opt local search heuristics
 * over 3D coordinates to minimize picker walking/transit distance and time.
 */
public class WaveRouteOptimizationService {
    private final BinRepository binRepository;

    public WaveRouteOptimizationService(BinRepository binRepository) {
        this.binRepository = Objects.requireNonNull(binRepository, "binRepository must not be null");
    }

    /**
     * Optimizes picking sequence for a list of pick items starting from origin (e.g. equipment depot)
     * and ending at destination (e.g. packing station).
     */
    public PickPath optimizePickRoute(Coordinates3D origin, Coordinates3D destination, List<PickItem> items) {
        Objects.requireNonNull(origin, "Origin coordinates must not be null");
        Objects.requireNonNull(destination, "Destination coordinates must not be null");
        if (items == null || items.isEmpty()) {
            return new PickPath(origin, destination, Collections.emptyList(), 0, 0);
        }

        // 1. Group items by bin location to avoid duplicate stops at the same bin
        Map<String, List<PickItem>> itemsByBin = new HashMap<>();
        Map<String, Coordinates3D> binCoordinates = new HashMap<>();
        Map<String, String> binAisles = new HashMap<>();

        for (PickItem item : items) {
            itemsByBin.computeIfAbsent(item.getSourceBinId(), k -> new ArrayList<>()).add(item);
            binCoordinates.putIfAbsent(item.getSourceBinId(), item.getCoordinates());

            Bin bin = binRepository.findById(item.getSourceBinId()).orElse(null);
            binAisles.putIfAbsent(item.getSourceBinId(), bin != null ? bin.getAisleCode() : "UNKNOWN");
        }

        List<String> uniqueBinIds = new ArrayList<>(itemsByBin.keySet());

        // 2. Solve TSP using Nearest Neighbor heuristic as initial solution
        List<String> tour = solveNearestNeighbor(origin, uniqueBinIds, binCoordinates);

        // 3. Improve tour using 2-Opt iterative improvement
        tour = optimizeWith2Opt(origin, destination, tour, binCoordinates);

        // 4. Construct detailed RouteStops and calculate total travel distance
        List<RouteStop> stops = new ArrayList<>(tour.size());
        Coordinates3D currentPos = origin;
        long totalDistanceMm = 0;

        for (int i = 0; i < tour.size(); i++) {
            String binId = tour.get(i);
            Coordinates3D stopCoords = binCoordinates.get(binId);
            long segmentDistance = currentPos.manhattanDistanceTo(stopCoords);
            totalDistanceMm += segmentDistance;

            RouteStop stop = new RouteStop(
                    i + 1,
                    binId,
                    binAisles.get(binId),
                    stopCoords,
                    itemsByBin.get(binId),
                    segmentDistance
            );
            stops.add(stop);
            currentPos = stopCoords;
        }

        // Final leg from last bin to destination (e.g. pack station)
        long finalLegMm = currentPos.manhattanDistanceTo(destination);
        totalDistanceMm += finalLegMm;

        // Calculate estimated pick duration:
        // Walking transit speed: 1.2 meters/second (1200 mm/s)
        // Pick execution time: 8 seconds per unique item
        long travelTimeSeconds = totalDistanceMm / 1200L;
        long pickExecutionSeconds = items.size() * 8L;
        long totalEstimatedSeconds = travelTimeSeconds + pickExecutionSeconds;

        return new PickPath(origin, destination, stops, totalDistanceMm, totalEstimatedSeconds);
    }

    private List<String> solveNearestNeighbor(Coordinates3D origin, List<String> binIds, Map<String, Coordinates3D> coordinates) {
        List<String> remaining = new ArrayList<>(binIds);
        List<String> tour = new ArrayList<>(binIds.size());
        Coordinates3D current = origin;

        while (!remaining.isEmpty()) {
            int bestIndex = 0;
            long minDistance = Long.MAX_VALUE;

            for (int i = 0; i < remaining.size(); i++) {
                String binId = remaining.get(i);
                Coordinates3D target = coordinates.get(binId);
                long dist = current.manhattanDistanceTo(target);
                if (dist < minDistance) {
                    minDistance = dist;
                    bestIndex = i;
                }
            }

            String nextBin = remaining.remove(bestIndex);
            tour.add(nextBin);
            current = coordinates.get(nextBin);
        }

        return tour;
    }

    /**
     * 2-Opt local search: inverts sub-sequences of the tour whenever the swap reduces total Manhattan tour distance.
     */
    private List<String> optimizeWith2Opt(Coordinates3D origin, Coordinates3D destination, List<String> tour, Map<String, Coordinates3D> coordinates) {
        int n = tour.size();
        if (n <= 3) return tour; // 2-opt requires at least 4 stops to swap edges effectively

        boolean improved = true;
        int maxIterations = 50;
        int iteration = 0;

        List<String> bestTour = new ArrayList<>(tour);

        while (improved && iteration < maxIterations) {
            improved = false;
            iteration++;

            for (int i = 0; i < n - 1; i++) {
                for (int k = i + 1; k < n; k++) {
                    long currentCost = calculateSubtourDistance(origin, destination, bestTour, i, k, coordinates);
                    List<String> candidateTour = twoOptSwap(bestTour, i, k);
                    long candidateCost = calculateSubtourDistance(origin, destination, candidateTour, i, k, coordinates);

                    if (candidateCost < currentCost) {
                        bestTour = candidateTour;
                        improved = true;
                        break;
                    }
                }
                if (improved) break;
            }
        }

        return bestTour;
    }

    private List<String> twoOptSwap(List<String> tour, int i, int k) {
        List<String> newTour = new ArrayList<>(tour.size());
        // 1. Take 0 to i-1
        for (int c = 0; c < i; c++) {
            newTour.add(tour.get(c));
        }
        // 2. Invert from i to k
        for (int c = k; c >= i; c--) {
            newTour.add(tour.get(c));
        }
        // 3. Take k+1 to end
        for (int c = k + 1; c < tour.size(); c++) {
            newTour.add(tour.get(c));
        }
        return newTour;
    }

    private long calculateSubtourDistance(Coordinates3D origin, Coordinates3D destination, List<String> tour, int i, int k, Map<String, Coordinates3D> coordinates) {
        long total = 0;
        Coordinates3D prev = (i == 0) ? origin : coordinates.get(tour.get(i - 1));

        for (int idx = i; idx <= Math.min(k + 1, tour.size() - 1); idx++) {
            Coordinates3D curr = coordinates.get(tour.get(idx));
            total += prev.manhattanDistanceTo(curr);
            prev = curr;
        }

        if (k == tour.size() - 1) {
            total += prev.manhattanDistanceTo(destination);
        }

        return total;
    }
}
