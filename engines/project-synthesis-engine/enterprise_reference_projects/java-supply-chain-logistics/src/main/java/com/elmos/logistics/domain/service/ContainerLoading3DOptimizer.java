package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.Weight;

import java.util.*;

/**
 * Enterprise 3D Container &amp; Pallet Loading Optimizer.
 * Implements Extreme Point (EP) 3D bin packing heuristic with physical stability,
 * axle weight distribution (Center of Gravity), and stacking fragility constraints.
 */
public class ContainerLoading3DOptimizer {

    public enum ContainerType {
        ISO_20FT_DRY(5898, 2352, 2393, 28200.0, "20ft Standard Dry Container"),
        ISO_40FT_DRY(12032, 2352, 2393, 26700.0, "40ft Standard Dry Container"),
        ISO_40FT_HC(12032, 2352, 2698, 28600.0, "40ft High-Cube Container"),
        ISO_40FT_REEFER(11583, 2286, 2532, 29200.0, "40ft Refrigerated Container"),
        DOMESTIC_53FT(16000, 2480, 2750, 22000.0, "53ft Domestic Intermodal Trailer");

        private final int lengthMm;
        private final int widthMm;
        private final int heightMm;
        private final double maxPayloadKg;
        private final String description;

        ContainerType(int lengthMm, int widthMm, int heightMm, double maxPayloadKg, String description) {
            this.lengthMm = lengthMm;
            this.widthMm = widthMm;
            this.heightMm = heightMm;
            this.maxPayloadKg = maxPayloadKg;
            this.description = description;
        }

        public Dimensions getInternalDimensions() {
            return new Dimensions(lengthMm, widthMm, heightMm);
        }

        public double getMaxPayloadKg() { return maxPayloadKg; }
        public String getDescription() { return description; }
    }

    public static final class PackableItem {
        private final String itemId;
        private final String sku;
        private final Dimensions dimensions;
        private final double weightKg;
        private final boolean allowRotationYaw;
        private final boolean fragile;
        private final double maxSuperimposedWeightKg; // Max weight this item can bear on its top face

        public PackableItem(String itemId, String sku, Dimensions dimensions, double weightKg,
                            boolean allowRotationYaw, boolean fragile, double maxSuperimposedWeightKg) {
            this.itemId = Objects.requireNonNull(itemId, "itemId");
            this.sku = Objects.requireNonNull(sku, "sku");
            this.dimensions = Objects.requireNonNull(dimensions, "dimensions");
            this.weightKg = weightKg;
            this.allowRotationYaw = allowRotationYaw;
            this.fragile = fragile;
            this.maxSuperimposedWeightKg = maxSuperimposedWeightKg;
        }

        public String getItemId() { return itemId; }
        public String getSku() { return sku; }
        public Dimensions getDimensions() { return dimensions; }
        public double getWeightKg() { return weightKg; }
        public boolean isAllowRotationYaw() { return allowRotationYaw; }
        public boolean isFragile() { return fragile; }
        public double getMaxSuperimposedWeightKg() { return maxSuperimposedWeightKg; }
    }

    public static final class PlacedBox {
        private final PackableItem item;
        private final Coordinates3D origin; // (x, y, z) in mm from front-left-bottom corner
        private final Dimensions placedDimensions; // length along X, width along Y, height along Z

        public PlacedBox(PackableItem item, Coordinates3D origin, Dimensions placedDimensions) {
            this.item = item;
            this.origin = origin;
            this.placedDimensions = placedDimensions;
        }

        public PackableItem getItem() { return item; }
        public Coordinates3D getOrigin() { return origin; }
        public Dimensions getPlacedDimensions() { return placedDimensions; }

        public int getX1() { return origin.getXMm(); }
        public int getY1() { return origin.getYMm(); }
        public int getZ1() { return origin.getZMm(); }
        public int getX2() { return origin.getXMm() + placedDimensions.getLengthMm(); }
        public int getY2() { return origin.getYMm() + placedDimensions.getWidthMm(); }
        public int getZ2() { return origin.getZMm() + placedDimensions.getHeightMm(); }

        public boolean overlaps(PlacedBox other) {
            return this.getX1() < other.getX2() && this.getX2() > other.getX1()
                    && this.getY1() < other.getY2() && this.getY2() > other.getY1()
                    && this.getZ1() < other.getZ2() && this.getZ2() > other.getZ1();
        }

        public Coordinates3D getCenterOfMass() {
            return new Coordinates3D(
                    (getX1() + getX2()) / 2,
                    (getY1() + getY2()) / 2,
                    (getZ1() + getZ2()) / 2
            );
        }
    }

    public static final class ContainerLoadPlan {
        private final ContainerType containerType;
        private final List<PlacedBox> placedBoxes;
        private final List<PackableItem> unplacedItems;
        private final double totalCargoWeightKg;
        private final double volumetricUtilizationPercent;
        private final double weightUtilizationPercent;
        private final double longitudinalCenterOfGravityPercent; // 0% = front, 100% = rear (optimal 45-55%)
        private final double transverseCenterOfGravityPercent;   // 0% = left, 100% = right (optimal 48-52%)
        private final boolean axleBalanceCompliant;

        public ContainerLoadPlan(ContainerType containerType, List<PlacedBox> placedBoxes,
                                 List<PackableItem> unplacedItems, double totalCargoWeightKg,
                                 double volumetricUtilizationPercent, double weightUtilizationPercent,
                                 double longitudinalCenterOfGravityPercent,
                                 double transverseCenterOfGravityPercent, boolean axleBalanceCompliant) {
            this.containerType = containerType;
            this.placedBoxes = Collections.unmodifiableList(placedBoxes);
            this.unplacedItems = Collections.unmodifiableList(unplacedItems);
            this.totalCargoWeightKg = totalCargoWeightKg;
            this.volumetricUtilizationPercent = volumetricUtilizationPercent;
            this.weightUtilizationPercent = weightUtilizationPercent;
            this.longitudinalCenterOfGravityPercent = longitudinalCenterOfGravityPercent;
            this.transverseCenterOfGravityPercent = transverseCenterOfGravityPercent;
            this.axleBalanceCompliant = axleBalanceCompliant;
        }

        public ContainerType getContainerType() { return containerType; }
        public List<PlacedBox> getPlacedBoxes() { return placedBoxes; }
        public List<PackableItem> getUnplacedItems() { return unplacedItems; }
        public double getTotalCargoWeightKg() { return totalCargoWeightKg; }
        public double getVolumetricUtilizationPercent() { return volumetricUtilizationPercent; }
        public double getWeightUtilizationPercent() { return weightUtilizationPercent; }
        public double getLongitudinalCenterOfGravityPercent() { return longitudinalCenterOfGravityPercent; }
        public double getTransverseCenterOfGravityPercent() { return transverseCenterOfGravityPercent; }
        public boolean isAxleBalanceCompliant() { return axleBalanceCompliant; }
    }

    /**
     * Solves 3D bin packing for given cargo against target container type.
     */
    public ContainerLoadPlan optimizeLoading(ContainerType containerType, List<PackableItem> items) {
        Objects.requireNonNull(containerType, "containerType");
        Objects.requireNonNull(items, "items");

        Dimensions containerDim = containerType.getInternalDimensions();
        int cLength = containerDim.getLengthMm();
        int cWidth = containerDim.getWidthMm();
        int cHeight = containerDim.getHeightMm();

        // Sort items by priority: Heavy and large volume items first (Best Fit Decreasing)
        List<PackableItem> pendingItems = new ArrayList<>(items);
        pendingItems.sort((a, b) -> {
            // Fragile items go later
            if (a.isFragile() != b.isFragile()) {
                return a.isFragile() ? 1 : -1;
            }
            // Heavier items first to keep center of gravity low
            int wComp = Double.compare(b.getWeightKg(), a.getWeightKg());
            if (wComp != 0) return wComp;
            // Larger volume first
            return Long.compare(b.getDimensions().volumeCubicMm(), a.getDimensions().volumeCubicMm());
        });

        List<PlacedBox> placedBoxes = new ArrayList<>();
        List<PackableItem> unplacedItems = new ArrayList<>();

        // Extreme Points set initialized with origin (0, 0, 0)
        TreeSet<Coordinates3D> extremePoints = new TreeSet<>((p1, p2) -> {
            if (p1.getZMm() != p2.getZMm()) return Integer.compare(p1.getZMm(), p2.getZMm());
            if (p1.getXMm() != p2.getXMm()) return Integer.compare(p1.getXMm(), p2.getXMm());
            return Integer.compare(p1.getYMm(), p2.getYMm());
        });
        extremePoints.add(new Coordinates3D(0, 0, 0));

        double currentWeightKg = 0.0;

        for (PackableItem item : pendingItems) {
            // Check weight capacity
            if (currentWeightKg + item.getWeightKg() > containerType.getMaxPayloadKg()) {
                unplacedItems.add(item);
                continue;
            }

            Coordinates3D bestPoint = null;
            Dimensions bestDim = null;
            double bestScore = Double.MAX_VALUE;

            // Generate possible orientations (Upright only vs 90-degree yaw rotation)
            List<Dimensions> orientations = new ArrayList<>();
            orientations.add(item.getDimensions());
            if (item.isAllowRotationYaw()) {
                orientations.add(new Dimensions(item.getDimensions().getWidthMm(),
                        item.getDimensions().getLengthMm(),
                        item.getDimensions().getHeightMm()));
            }

            for (Coordinates3D ep : extremePoints) {
                for (Dimensions orient : orientations) {
                    if (canPlace(ep, orient, cLength, cWidth, cHeight, placedBoxes, item)) {
                        // Scoring function: lowest Z first (gravity), then closest to front-wall X, then Y
                        double score = ep.getZMm() * 10000.0 + ep.getXMm() * 10.0 + ep.getYMm();
                        if (score < bestScore) {
                            bestScore = score;
                            bestPoint = ep;
                            bestDim = orient;
                        }
                    }
                }
                if (bestPoint != null && bestPoint.getZMm() == 0) {
                    // Early exit if good base floor point found
                    break;
                }
            }

            if (bestPoint != null) {
                PlacedBox placed = new PlacedBox(item, bestPoint, bestDim);
                placedBoxes.add(placed);
                currentWeightKg += item.getWeightKg();

                // Update Extreme Points
                extremePoints.remove(bestPoint);
                updateExtremePoints(extremePoints, placed, cLength, cWidth, cHeight, placedBoxes);
            } else {
                unplacedItems.add(item);
            }
        }

        // Metrics Computation
        long totalPlacedVolume = 0;
        double weightedXSum = 0.0;
        double weightedYSum = 0.0;

        for (PlacedBox b : placedBoxes) {
            totalPlacedVolume += b.getPlacedDimensions().volumeCubicMm();
            Coordinates3D com = b.getCenterOfMass();
            weightedXSum += com.getXMm() * b.getItem().getWeightKg();
            weightedYSum += com.getYMm() * b.getItem().getWeightKg();
        }

        long containerVol = containerDim.volumeCubicMm();
        double volUtil = (totalPlacedVolume * 100.0) / containerVol;
        double weightUtil = (currentWeightKg * 100.0) / containerType.getMaxPayloadKg();

        double cgXPercent = currentWeightKg > 0 ? (weightedXSum / currentWeightKg / cLength) * 100.0 : 50.0;
        double cgYPercent = currentWeightKg > 0 ? (weightedYSum / currentWeightKg / cWidth) * 100.0 : 50.0;

        // Axle balance: Center of Gravity longitudinal within 43%-57%, transverse within 47%-53%
        boolean compliant = cgXPercent >= 43.0 && cgXPercent <= 57.0
                && cgYPercent >= 47.0 && cgYPercent <= 53.0;

        return new ContainerLoadPlan(containerType, placedBoxes, unplacedItems, currentWeightKg,
                Math.round(volUtil * 100.0) / 100.0,
                Math.round(weightUtil * 100.0) / 100.0,
                Math.round(cgXPercent * 100.0) / 100.0,
                Math.round(cgYPercent * 100.0) / 100.0,
                compliant);
    }

    private boolean canPlace(Coordinates3D ep, Dimensions dim, int cL, int cW, int cH,
                             List<PlacedBox> placedBoxes, PackableItem candidate) {
        // Boundary check
        if (ep.getXMm() + dim.getLengthMm() > cL ||
            ep.getYMm() + dim.getWidthMm() > cW ||
            ep.getZMm() + dim.getHeightMm() > cH) {
            return false;
        }

        PlacedBox testBox = new PlacedBox(candidate, ep, dim);

        // Overlap check
        for (PlacedBox existing : placedBoxes) {
            if (testBox.overlaps(existing)) {
                return false;
            }
        }

        // Stability / Support check if not resting on container floor
        if (ep.getZMm() > 0) {
            int supportArea = 0;
            int boxArea = dim.getLengthMm() * dim.getWidthMm();

            for (PlacedBox under : placedBoxes) {
                if (under.getZ2() == ep.getZMm()) {
                    // Check horizontal overlap
                    int xOverlap = Math.max(0, Math.min(testBox.getX2(), under.getX2()) - Math.max(testBox.getX1(), under.getX1()));
                    int yOverlap = Math.max(0, Math.min(testBox.getY2(), under.getY2()) - Math.max(testBox.getY1(), under.getY1()));
                    supportArea += xOverlap * yOverlap;

                    // Superimposed weight constraint check on the underlying item
                    if (candidate.getWeightKg() > under.getItem().getMaxSuperimposedWeightKg()) {
                        return false;
                    }
                    // Cannot place on top of fragile item
                    if (under.getItem().isFragile()) {
                        return false;
                    }
                }
            }
            // Require at least 65% base area support
            if ((double) supportArea / boxArea < 0.65) {
                return false;
            }
        }

        return true;
    }

    private void updateExtremePoints(TreeSet<Coordinates3D> extremePoints, PlacedBox placed,
                                    int cL, int cW, int cH, List<PlacedBox> placedBoxes) {
        // Generate new candidate extreme points on top, right, and front faces of placed box
        int px2 = placed.getX2();
        int py2 = placed.getY2();
        int pz2 = placed.getZ2();

        Coordinates3D ep1 = new Coordinates3D(px2, placed.getY1(), placed.getZ1());
        Coordinates3D ep2 = new Coordinates3D(placed.getX1(), py2, placed.getZ1());
        Coordinates3D ep3 = new Coordinates3D(placed.getX1(), placed.getY1(), pz2);

        for (Coordinates3D candidate : Arrays.asList(ep1, ep2, ep3)) {
            if (candidate.getXMm() < cL && candidate.getYMm() < cW && candidate.getZMm() < cH) {
                boolean insideExisting = false;
                for (PlacedBox b : placedBoxes) {
                    if (candidate.getXMm() >= b.getX1() && candidate.getXMm() < b.getX2()
                            && candidate.getYMm() >= b.getY1() && candidate.getYMm() < b.getY2()
                            && candidate.getZMm() >= b.getZ1() && candidate.getZMm() < b.getZ2()) {
                        insideExisting = true;
                        break;
                    }
                }
                if (!insideExisting) {
                    extremePoints.add(candidate);
                }
            }
        }
    }
}
