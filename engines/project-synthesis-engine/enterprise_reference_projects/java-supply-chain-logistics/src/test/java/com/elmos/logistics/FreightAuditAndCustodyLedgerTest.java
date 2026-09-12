package com.elmos.logistics;

import com.elmos.logistics.domain.model.common.Money;
import com.elmos.logistics.domain.service.FreightAuditAndDiscrepancyEngine;
import com.elmos.logistics.domain.service.FreightAuditAndDiscrepancyEngine.*;
import com.elmos.logistics.domain.service.MultiModalContainerCustodyLedger;
import com.elmos.logistics.domain.service.MultiModalContainerCustodyLedger.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.*;

public class FreightAuditAndCustodyLedgerTest {

    public static void runTests() {
        System.out.println("Running FreightAuditAndCustodyLedgerTest...");
        testCleanFreightInvoiceWithinContractualToleranceApproved();
        testOverbilledAccessorialAndDetentionGeneratesVoucherAdjustments();
        testMultiModalContainerChainOfCustodyCleanTransit();
        testTamperedSealAndImpossibleSpeedAnomalies();
        testTieredDemurrageAndDetentionTariffCalculations();
        System.out.println("  ✓ FreightAuditAndCustodyLedgerTest passed successfully.");
    }

    private static void testCleanFreightInvoiceWithinContractualToleranceApproved() {
        FreightAuditAndDiscrepancyEngine engine = new FreightAuditAndDiscrepancyEngine();
        String currency = "USD";

        Map<AccessorialCode, Money> agreedRates = new EnumMap<>(AccessorialCode.class);
        agreedRates.put(AccessorialCode.LIFTGATE_SERVICE, Money.ofMajor(new BigDecimal("65.00"), currency));

        AgreedFreightContract contract = new AgreedFreightContract(
                "CONTRACT-XPO-01",
                "CNWY",
                Money.ofMajor(new BigDecimal("2500.00"), currency), // $2,500 base linehaul
                new BigDecimal("3.00"),                             // $3.00 baseline diesel
                new BigDecimal("3.80"),                             // $3.80 current diesel index (+$0.80 -> 16 increments of 0.05)
                new BigDecimal("0.005"),                            // 0.5% per increment -> 8.0% FSC = $200.00
                new BigDecimal("0.05"),                             // $0.05 step
                new BigDecimal("2.0"),                              // 2.0 free detention hours
                Money.ofMajor(new BigDecimal("75.00"), currency),   // $75/hr detention
                agreedRates,
                new BigDecimal("0.015"),                            // 1.5% tolerance
                Money.ofMajor(new BigDecimal("25.00"), currency)    // $25.00 min threshold
        );

        List<InvoiceLineItem> items = Arrays.asList(
                new InvoiceLineItem("L-01", AccessorialCode.LINEHAUL_BASE, "Linehaul Chicago to Dallas", BigDecimal.ONE, null, Money.ofMajor(new BigDecimal("2500.00"), currency)),
                new InvoiceLineItem("L-02", AccessorialCode.FUEL_SURCHARGE, "DOE National Fuel Surcharge", BigDecimal.ONE, null, Money.ofMajor(new BigDecimal("200.00"), currency))
        );

        // Billed total $2,715.00 (Benchmark is $2,700.00. Variance = $15.00, below $40.50 tolerance)
        CarrierFreightInvoice invoice = new CarrierFreightInvoice(
                "INV-CNWY-991", "CNWY", "BOL-88192", FreightInvoiceType.MOTOR_FTL,
                LocalDate.now(), items, Money.ofMajor(new BigDecimal("2715.00"), currency)
        );

        FreightAuditVoucher voucher = engine.auditInvoice(invoice, contract, new BigDecimal("1.5")); // 1.5 hrs detention (< 2.0 hrs)

        if (voucher.getStatus() != VoucherStatus.APPROVED_AUTO_PAY) {
            throw new RuntimeException("Expected APPROVED_AUTO_PAY for invoice within contractual tolerance");
        }

        if (voucher.getApprovedPaymentAmount().toMajorUnits().compareTo(new BigDecimal("2715.00")) != 0) {
            throw new RuntimeException("Approved payment must match full invoice amount when within tolerance");
        }

        if (voucher.getDisputedWithheldAmount().toMajorUnits().compareTo(BigDecimal.ZERO) != 0) {
            throw new RuntimeException("Disputed amount must be zero for auto-approved invoice");
        }
    }

    private static void testOverbilledAccessorialAndDetentionGeneratesVoucherAdjustments() {
        FreightAuditAndDiscrepancyEngine engine = new FreightAuditAndDiscrepancyEngine();
        String currency = "USD";

        Map<AccessorialCode, Money> agreedRates = new EnumMap<>(AccessorialCode.class);
        agreedRates.put(AccessorialCode.LIFTGATE_SERVICE, Money.ofMajor(new BigDecimal("65.00"), currency));

        AgreedFreightContract contract = new AgreedFreightContract(
                "CONTRACT-ODFL-02",
                "ODFL",
                Money.ofMajor(new BigDecimal("1000.00"), currency),
                new BigDecimal("3.00"),
                new BigDecimal("3.00"), // No FSC
                new BigDecimal("0.005"),
                new BigDecimal("0.05"),
                new BigDecimal("2.0"), // 2 hrs free
                Money.ofMajor(new BigDecimal("75.00"), currency), // $75/hr
                agreedRates,
                new BigDecimal("0.01"), // 1% tolerance ($10)
                Money.ofMajor(new BigDecimal("20.00"), currency)
        );

        // Carrier overbills: 5.0 hours detention ($225 expected, carrier bills $450) + unauthorized $150 inside delivery
        List<InvoiceLineItem> items = Arrays.asList(
                new InvoiceLineItem("L-01", AccessorialCode.LINEHAUL_BASE, "Base Linehaul", BigDecimal.ONE, null, Money.ofMajor(new BigDecimal("1000.00"), currency)),
                new InvoiceLineItem("L-02", AccessorialCode.DETENTION_AT_SITE, "Detention at receiver", new BigDecimal("5.0"), null, Money.ofMajor(new BigDecimal("450.00"), currency)),
                new InvoiceLineItem("L-03", AccessorialCode.INSIDE_PICKUP_DELIVERY, "Unauthorized inside delivery", BigDecimal.ONE, null, Money.ofMajor(new BigDecimal("150.00"), currency))
        );

        CarrierFreightInvoice invoice = new CarrierFreightInvoice(
                "INV-ODFL-772", "ODFL", "BOL-10928", FreightInvoiceType.MOTOR_LTL,
                LocalDate.now(), items, Money.ofMajor(new BigDecimal("1600.00"), currency)
        );

        // Actual telemetry indicates 5.0 facility dwell hours (3 billable hours = $225)
        FreightAuditVoucher voucher = engine.auditInvoice(invoice, contract, new BigDecimal("5.0"));

        if (voucher.getStatus() != VoucherStatus.APPROVED_WITH_ADJUSTMENTS) {
            throw new RuntimeException("Expected APPROVED_WITH_ADJUSTMENTS due to substantial overbilling");
        }

        // Expected total: $1,000 + $225 detention + $0 unauthorized inside delivery = $1,225.00
        BigDecimal expectedContract = new BigDecimal("1225.00");
        if (voucher.getExpectedContractTotal().toMajorUnits().compareTo(expectedContract) != 0) {
            throw new RuntimeException("Expected $1225.00 benchmark, got: " + voucher.getExpectedContractTotal());
        }

        // Disputed withheld amount: $1,600 - $1,225 = $375.00
        BigDecimal expectedDispute = new BigDecimal("375.00");
        if (voucher.getDisputedWithheldAmount().toMajorUnits().compareTo(expectedDispute) != 0) {
            throw new RuntimeException("Expected $375.00 disputed withheld, got: " + voucher.getDisputedWithheldAmount());
        }

        if (voucher.getFindings().size() < 2) {
            throw new RuntimeException("Expected at least 2 audit findings (detention overbilling + unauthorized accessorial)");
        }
    }

    private static void testMultiModalContainerChainOfCustodyCleanTransit() {
        MultiModalContainerCustodyLedger ledger = new MultiModalContainerCustodyLedger();
        String container = "MSKU7492018";
        String salt = "SECRET-PORT-SALT";
        String sealDigest = ElectronicSeal.computeSealDigest("SEAL-9941", salt);

        Instant t0 = Instant.now().minus(48, ChronoUnit.HOURS);

        // 1. Vessel Discharge at Port of Los Angeles (USLAX)
        ledger.recordInterchangeEvent(new CustodyInterchangeEvent(
                "EVT-01", container, TransportModality.PORT_GANTRY_CRANE, "USLAX",
                33.7432, -118.2673, t0, "APM-TERMINALS", "HARBOR-TRUCKING",
                new ElectronicSeal("SEAL-9941", sealDigest, false),
                SealIntegrityStatus.VERIFIED_INTACT
        ));

        // 2. Gate Out by Drayage Truck 4 hours later
        ledger.recordInterchangeEvent(new CustodyInterchangeEvent(
                "EVT-02", container, TransportModality.DRAYAGE_TRUCK, "USLAX",
                33.7500, -118.2500, t0.plus(4, ChronoUnit.HOURS), "HARBOR-TRUCKING", "BNSF-RAILWAY",
                new ElectronicSeal("SEAL-9941", sealDigest, false),
                SealIntegrityStatus.VERIFIED_INTACT
        ));

        // 3. Rail Ingate at BNSF Los Angeles Hobart Intermodal Yard 6 hours later (20 miles away)
        ledger.recordInterchangeEvent(new CustodyInterchangeEvent(
                "EVT-03", container, TransportModality.INTERMODAL_RAIL, "USLAX",
                34.0040, -118.1920, t0.plus(10, ChronoUnit.HOURS), "BNSF-RAILWAY", "BNSF-TRAIN",
                new ElectronicSeal("SEAL-9941", sealDigest, false),
                SealIntegrityStatus.VERIFIED_INTACT
        ));

        CustodyLedgerValidationResult result = ledger.validateContainerChainOfCustody(container);
        if (!result.isChainOfCustodyValid()) {
            throw new RuntimeException("Expected valid chain of custody for normal transit: " + result.getAnomalyDescriptions());
        }
        if (result.isTamperDetected() || result.isImpossibleSpeedDetected()) {
            throw new RuntimeException("Should not detect any tamper or speed anomaly");
        }
    }

    private static void testTamperedSealAndImpossibleSpeedAnomalies() {
        MultiModalContainerCustodyLedger ledger = new MultiModalContainerCustodyLedger();
        String container = "MAEU5501923";
        String sealDigest = ElectronicSeal.computeSealDigest("SEAL-DEF-1", "SALT");

        Instant t0 = Instant.now().minus(24, ChronoUnit.HOURS);

        // Event 1: Gate out Los Angeles (lat 33.74, lon -118.26)
        ledger.recordInterchangeEvent(new CustodyInterchangeEvent(
                "EVT-01", container, TransportModality.DRAYAGE_TRUCK, "USLAX",
                33.74, -118.26, t0, "DRAYAGE-CO", "RAIL-CO",
                new ElectronicSeal("SEAL-DEF-1", sealDigest, false),
                SealIntegrityStatus.VERIFIED_INTACT
        ));

        // Event 2: Only 2 hours later at Chicago Intermodal Yard (lat 41.87, lon -87.62) -> ~1,750 miles in 2 hours (~875 mph!)
        // AND physical tamper flag is true!
        ledger.recordInterchangeEvent(new CustodyInterchangeEvent(
                "EVT-02", container, TransportModality.INLAND_CONTAINER_YARD, "USCHI",
                41.87, -87.62, t0.plus(2, ChronoUnit.HOURS), "RAIL-CO", "DEST-WAREHOUSE",
                new ElectronicSeal("SEAL-DEF-1", sealDigest, true), // Physical tamper tripped!
                SealIntegrityStatus.SEAL_BROKEN_TAMPERED
        ));

        CustodyLedgerValidationResult result = ledger.validateContainerChainOfCustody(container);

        if (result.isChainOfCustodyValid()) {
            throw new RuntimeException("Expected chain of custody failure due to broken seal and impossible speed");
        }
        if (!result.isTamperDetected()) {
            throw new RuntimeException("Expected tamper detection for broken seal");
        }
        if (!result.isImpossibleSpeedDetected()) {
            throw new RuntimeException("Expected impossible transit velocity detection (> 75 mph)");
        }
    }

    private static void testTieredDemurrageAndDetentionTariffCalculations() {
        MultiModalContainerCustodyLedger ledger = new MultiModalContainerCustodyLedger();
        String currency = "USD";

        Instant discharge = Instant.now().minus(15, ChronoUnit.DAYS);
        Instant gateOut = discharge.plus(10, ChronoUnit.DAYS); // 10 days in port
        Instant emptyReturn = gateOut.plus(8, ChronoUnit.DAYS); // 8 days equipment holding

        DemurrageAndDetentionAssessment assessment = ledger.calculateDemurrageAndDetention(
                "CMAU9920194",
                discharge,
                gateOut,
                emptyReturn,
                4, // 4 free days at terminal
                5, // 5 free days for equipment
                Money.ofMajor(new BigDecimal("150.00"), currency), // Tier 1: $150/day
                Money.ofMajor(new BigDecimal("300.00"), currency), // Tier 2: $300/day
                Money.ofMajor(new BigDecimal("125.00"), currency)  // Equipment detention: $125/day
        );

        // Terminal Demurrage:
        // 10 dwell days - 4 free days = 6 billable demurrage days
        // Days 5-8 (4 days) * $150 = $600
        // Days 9-10 (2 days) * $300 = $600
        // Total Demurrage = $1,200.00
        if (assessment.getDemurrageCost().toMajorUnits().compareTo(new BigDecimal("1200.00")) != 0) {
            throw new RuntimeException("Expected $1200.00 demurrage, got: " + assessment.getDemurrageCost());
        }

        // Equipment Detention:
        // 8 holding days - 5 free days = 3 billable days * $125 = $375.00
        if (assessment.getDetentionCost().toMajorUnits().compareTo(new BigDecimal("375.00")) != 0) {
            throw new RuntimeException("Expected $375.00 detention, got: " + assessment.getDetentionCost());
        }

        // Combined Total = $1,575.00
        if (assessment.getTotalTerminalCharges().toMajorUnits().compareTo(new BigDecimal("1575.00")) != 0) {
            throw new RuntimeException("Expected $1575.00 combined terminal charges, got: " + assessment.getTotalTerminalCharges());
        }
    }
}
