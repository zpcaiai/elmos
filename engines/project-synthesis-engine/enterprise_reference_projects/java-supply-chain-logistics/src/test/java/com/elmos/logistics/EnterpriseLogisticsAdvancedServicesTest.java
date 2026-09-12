package com.elmos.logistics;

import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.StorageClass;
import com.elmos.logistics.domain.model.common.TemperatureRange;
import com.elmos.logistics.domain.service.*;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.*;

/**
 * Enterprise verification test suite for advanced logistics and supply chain services.
 */
public class EnterpriseLogisticsAdvancedServicesTest {

    public static void runTests() {
        System.out.println("Running EnterpriseLogisticsAdvancedServicesTest...");
        testColdChainTelemetryAuditor();
        testContainerLoading3DOptimizer();
        testCustomsTariffEngine();
        testCrossDockingEngine();
        testCarrierRateShoppingService();
        System.out.println("  ✓ EnterpriseLogisticsAdvancedServicesTest passed successfully.");
    }

    private static void testColdChainTelemetryAuditor() {
        ColdChainTelemetryAuditor auditor = new ColdChainTelemetryAuditor();
        TemperatureRange coldChilled = TemperatureRange.coldChilled(); // 2.0 to 8.0 C

        List<ColdChainTelemetryAuditor.TelemetryReading> readings = new ArrayList<>();
        Instant baseTime = Instant.parse("2026-09-01T08:00:00Z");

        // 10 normal readings at 4.5 C
        for (int i = 0; i < 10; i++) {
            readings.add(new ColdChainTelemetryAuditor.TelemetryReading(
                    "R-" + i, "SENS-01", "LOT-BIO-9901",
                    baseTime.plusSeconds(i * 600), 4.5, 45.0, 3100));
        }

        ColdChainTelemetryAuditor.ColdChainAuditSummary normalSummary = auditor.auditTelemetry(
                "LOT-BIO-9901", coldChilled, readings, 7.0, 100.0);

        if (!normalSummary.isGdpCompliant()) {
            throw new AssertionError("Normal cold chain readings should be GDP compliant");
        }
        if (normalSummary.isQuarantineEnforced()) {
            throw new AssertionError("Normal cold chain should not trigger quarantine");
        }
        if (normalSummary.getMeanKineticTemperatureCelsius() < 4.0 || normalSummary.getMeanKineticTemperatureCelsius() > 5.0) {
            throw new AssertionError("Expected MKT around 4.5°C, got: " + normalSummary.getMeanKineticTemperatureCelsius());
        }

        // Test with Critical Freezing Excursion (-1.5 C)
        List<ColdChainTelemetryAuditor.TelemetryReading> freezeReadings = new ArrayList<>(readings);
        freezeReadings.add(new ColdChainTelemetryAuditor.TelemetryReading(
                "R-FREEZE", "SENS-01", "LOT-BIO-9901",
                baseTime.plusSeconds(6000), -1.5, 50.0, 3050));

        ColdChainTelemetryAuditor.ColdChainAuditSummary freezeSummary = auditor.auditTelemetry(
                "LOT-BIO-9901", coldChilled, freezeReadings, 7.0, 100.0);

        if (freezeSummary.isGdpCompliant()) {
            throw new AssertionError("Freezing event must fail GDP compliance");
        }
        if (!freezeSummary.isQuarantineEnforced()) {
            throw new AssertionError("Freezing event for biologics must trigger quarantine enforcement");
        }
        if (freezeSummary.getComplianceReportHash() == null || freezeSummary.getComplianceReportHash().length() != 64) {
            throw new AssertionError("Audit summary must yield valid 64-char SHA-256 certificate hash");
        }
    }

    private static void testContainerLoading3DOptimizer() {
        ContainerLoading3DOptimizer optimizer = new ContainerLoading3DOptimizer();
        List<ContainerLoading3DOptimizer.PackableItem> items = new ArrayList<>();

        // Add 12 heavy base pallets (each 1200 x 1000 x 1000 mm, 600kg, non-fragile, can bear 1500kg)
        for (int i = 0; i < 12; i++) {
            items.add(new ContainerLoading3DOptimizer.PackableItem(
                    "HEAVY-PLT-" + i, "SKU-PUMP",
                    Dimensions.of(1200, 1000, 1000),
                    600.0, true, false, 1500.0));
        }

        // Add 20 light fragile cartons (each 600 x 400 x 400 mm, 15kg, fragile, can bear 0kg)
        for (int i = 0; i < 20; i++) {
            items.add(new ContainerLoading3DOptimizer.PackableItem(
                    "FRAGILE-BOX-" + i, "SKU-GLASS",
                    Dimensions.of(600, 400, 400),
                    15.0, true, true, 0.0));
        }

        ContainerLoading3DOptimizer.ContainerLoadPlan plan = optimizer.optimizeLoading(
                ContainerLoading3DOptimizer.ContainerType.ISO_40FT_HC, items);

        if (plan.getPlacedBoxes().isEmpty()) {
            throw new AssertionError("Container loading should have placed boxes");
        }

        // Check for 3D collisions
        for (int i = 0; i < plan.getPlacedBoxes().size(); i++) {
            for (int j = i + 1; j < plan.getPlacedBoxes().size(); j++) {
                if (plan.getPlacedBoxes().get(i).overlaps(plan.getPlacedBoxes().get(j))) {
                    throw new AssertionError("Overlap detected between placed box " + i + " and " + j);
                }
            }
        }

        // Verify longitudinal center of gravity is computed within valid bounds
        if (plan.getLongitudinalCenterOfGravityPercent() <= 0.0 || plan.getLongitudinalCenterOfGravityPercent() >= 100.0) {
            throw new AssertionError("Longitudinal center of gravity must be within (0%, 100%), got: "
                    + plan.getLongitudinalCenterOfGravityPercent() + "%");
        }
        if (plan.getTransverseCenterOfGravityPercent() <= 0.0 || plan.getTransverseCenterOfGravityPercent() >= 100.0) {
            throw new AssertionError("Transverse center of gravity must be within (0%, 100%), got: "
                    + plan.getTransverseCenterOfGravityPercent() + "%");
        }
    }

    private static void testCustomsTariffEngine() {
        CustomsTariffEngine engine = new CustomsTariffEngine();

        // Register HS lines
        Map<String, BigDecimal> ftaRates = new HashMap<>();
        ftaRates.put("CA", BigDecimal.ZERO); // USMCA preferential 0%
        ftaRates.put("MX", BigDecimal.ZERO);

        Map<String, BigDecimal> adDuties = new HashMap<>();
        adDuties.put("CN", BigDecimal.valueOf(25.0)); // 25% Section 301 / AD tariff

        engine.registerTariffLine(new CustomsTariffEngine.TariffScheduleLine(
                "8471.30.01", "Portable automatic data processing machines",
                CustomsTariffEngine.DutyType.AD_VALOREM,
                BigDecimal.valueOf(5.0), BigDecimal.ZERO, "UNIT",
                BigDecimal.valueOf(19.0), ftaRates, adDuties));

        // Case 1: De Minimis shipment ($200 CIF < $800 threshold)
        List<CustomsTariffEngine.DeclarationCommercialItem> deMinimisItems = Collections.singletonList(
                new CustomsTariffEngine.DeclarationCommercialItem(
                        "LAPTOP-01", "84713001", "JP",
                        BigDecimal.ONE, BigDecimal.valueOf(180.0), BigDecimal.ZERO, ""));

        CustomsTariffEngine.CustomsClearanceDossier deMinimisDossier = engine.computeCustomsClearance(
                "DEC-001", "US", deMinimisItems,
                BigDecimal.valueOf(15.0), BigDecimal.valueOf(5.0), BigDecimal.valueOf(800.0));

        if (!deMinimisDossier.isDeMinimisExemptionApplied()) {
            throw new AssertionError("Expected de minimis exemption to apply");
        }
        if (deMinimisDossier.getGrandTotalTaxesAndDuties().compareTo(BigDecimal.ZERO) != 0) {
            throw new AssertionError("De minimis goods must have 0 duty/tax");
        }

        // Case 2: Commercial import with FTA Preferential Rate
        List<CustomsTariffEngine.DeclarationCommercialItem> ftaItems = Collections.singletonList(
                new CustomsTariffEngine.DeclarationCommercialItem(
                        "LAPTOP-CA", "84713001", "CA",
                        BigDecimal.valueOf(10), BigDecimal.valueOf(1000.0),
                        BigDecimal.valueOf(3000.0), "847330")); // $10,000 FOB, $3,000 VNM -> RVC = 70%

        CustomsTariffEngine.CustomsClearanceDossier ftaDossier = engine.computeCustomsClearance(
                "DEC-002", "US", ftaItems,
                BigDecimal.valueOf(500.0), BigDecimal.valueOf(100.0), BigDecimal.valueOf(800.0));

        if (!ftaDossier.getItemCalculations().get(0).isPreferentialRateApplied()) {
            throw new AssertionError("Canadian origin goods with RVC=70% should qualify for FTA preferential duty");
        }
        if (ftaDossier.getTotalBasicDuty().compareTo(BigDecimal.ZERO) != 0) {
            throw new AssertionError("Preferential basic duty should be 0");
        }
    }

    private static void testCrossDockingEngine() {
        CrossDockingEngine engine = new CrossDockingEngine();
        Instant now = Instant.parse("2026-09-01T10:00:00Z");

        List<CrossDockingEngine.InboundDockPallet> arrivals = Arrays.asList(
                new CrossDockingEngine.InboundDockPallet("LPN-001", "SKU-BEV-01", 50, "DOOR-IN-01", 10, 0, StorageClass.STANDARD_AMBIENT, now),
                new CrossDockingEngine.InboundDockPallet("LPN-002", "SKU-BIO-02", 20, "DOOR-IN-02", 20, 0, StorageClass.COLD_CHILLED, now.plusSeconds(900))
        );

        List<CrossDockingEngine.OutboundOrderDemand> demands = Arrays.asList(
                new CrossDockingEngine.OutboundOrderDemand("ORD-OUT-01", "SKU-BEV-01", 30, "DOOR-OUT-01", 12, 50, StorageClass.STANDARD_AMBIENT, now.plusSeconds(1800), 8),
                new CrossDockingEngine.OutboundOrderDemand("ORD-OUT-02", "SKU-BIO-02", 20, "DOOR-OUT-02", 22, 50, StorageClass.COLD_CHILLED, now.plusSeconds(7200), 10)
        );

        CrossDockingEngine.CrossDockPlan plan = engine.planCrossDocking(arrivals, demands, Duration.ofHours(3));

        if (plan.getAssignments().size() != 2) {
            throw new AssertionError("Expected 2 cross-dock assignments, got: " + plan.getAssignments().size());
        }
        if (plan.getTotalUnitsCrossDocked() != 50) {
            throw new AssertionError("Expected 50 units cross-docked, got: " + plan.getTotalUnitsCrossDocked());
        }
        CrossDockingEngine.CrossDockAssignment directAssignment = plan.getAssignments().stream()
                .filter(a -> a.getOutboundOrder().getOrderId().equals("ORD-OUT-01"))
                .findFirst().orElseThrow();
        if (directAssignment.getCrossDockType() != CrossDockingEngine.CrossDockType.DIRECT_FLOW_THROUGH) {
            throw new AssertionError("30-min dwell should be DIRECT_FLOW_THROUGH");
        }

        CrossDockingEngine.CrossDockAssignment stagedAssignment = plan.getAssignments().stream()
                .filter(a -> a.getOutboundOrder().getOrderId().equals("ORD-OUT-02"))
                .findFirst().orElseThrow();
        if (stagedAssignment.getCrossDockType() != CrossDockingEngine.CrossDockType.STAGED_CROSS_DOCK) {
            throw new AssertionError("105-min dwell should be STAGED_CROSS_DOCK");
        }
    }

    private static void testCarrierRateShoppingService() {
        CarrierRateShoppingService service = new CarrierRateShoppingService();

        // Register carriers
        Map<CarrierRateShoppingService.AccessorialType, BigDecimal> accessorials = new HashMap<>();
        accessorials.put(CarrierRateShoppingService.AccessorialType.LIFTGATE_DESTINATION, BigDecimal.valueOf(50.0));

        service.registerCarrier(new CarrierRateShoppingService.CarrierContract(
                "FEDEX_PRIORITY", "FedEx Express",
                CarrierRateShoppingService.TransportMode.AIR_CARGO_EXPRESS,
                BigDecimal.valueOf(85.0), BigDecimal.valueOf(150.0), BigDecimal.valueOf(14.0),
                accessorials, 0.98));

        service.registerCarrier(new CarrierRateShoppingService.CarrierContract(
                "ODFL_LTL", "Old Dominion Freight Line",
                CarrierRateShoppingService.TransportMode.LTL_FREIGHT,
                BigDecimal.valueOf(28.0), BigDecimal.valueOf(120.0), BigDecimal.valueOf(22.0),
                accessorials, 0.95));

        Set<CarrierRateShoppingService.AccessorialType> requested = new HashSet<>();
        requested.add(CarrierRateShoppingService.AccessorialType.LIFTGATE_DESTINATION);

        CarrierRateShoppingService.ShippingConsignmentRequest req =
                new CarrierRateShoppingService.ShippingConsignmentRequest(
                        "SHP-001", "60601", "90210", 2800.0, 150.0,
                        Dimensions.of(1200, 800, 1000), requested, false, 3);

        List<CarrierRateShoppingService.CarrierQuote> quotes = service.shopRates(req);

        if (quotes.size() != 2) {
            throw new AssertionError("Expected 2 carrier quotes, got: " + quotes.size());
        }

        // First quote should be the cheaper one
        if (quotes.get(0).getGrandTotalRate().compareTo(quotes.get(1).getGrandTotalRate()) > 0) {
            throw new AssertionError("Quotes should be sorted ascending by total price");
        }

        // Air quote should have higher carbon footprint than LTL
        CarrierRateShoppingService.CarrierQuote airQuote = quotes.stream()
                .filter(q -> q.getCarrier().getMode() == CarrierRateShoppingService.TransportMode.AIR_CARGO_EXPRESS)
                .findFirst().orElseThrow();
        CarrierRateShoppingService.CarrierQuote ltlQuote = quotes.stream()
                .filter(q -> q.getCarrier().getMode() == CarrierRateShoppingService.TransportMode.LTL_FREIGHT)
                .findFirst().orElseThrow();

        if (airQuote.getEstimatedCo2Kg() <= ltlQuote.getEstimatedCo2Kg()) {
            throw new AssertionError("Air freight should have higher CO2 footprint than LTL");
        }
    }
}
