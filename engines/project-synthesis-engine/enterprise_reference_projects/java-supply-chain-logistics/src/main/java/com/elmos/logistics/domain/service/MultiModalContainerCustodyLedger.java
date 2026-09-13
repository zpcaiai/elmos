package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.common.Money;

import java.math.BigDecimal;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.*;

public class MultiModalContainerCustodyLedger {

    public enum ContainerType {
        STANDARD_20FT,
        STANDARD_40FT,
        HIGH_CUBE_40FT,
        HIGH_CUBE_45FT,
        REEFER_40FT
    }

    public enum TransportModality {
        OCEAN_VESSEL,
        PORT_GANTRY_CRANE,
        DRAYAGE_TRUCK,
        INTERMODAL_RAIL,
        INLAND_CONTAINER_YARD
    }

    public enum SealIntegrityStatus {
        VERIFIED_INTACT,
        SEAL_BROKEN_TAMPERED,
        SEAL_REPLACED_UNAUTHORIZED,
        SEAL_ABSENT
    }

    public static final class ElectronicSeal {
        private final String sealId;
        private final String expectedSha256Digest;
        private final boolean physicalTamperFlag;

        public ElectronicSeal(String sealId, String expectedSha256Digest, boolean physicalTamperFlag) {
            this.sealId = Objects.requireNonNull(sealId);
            this.expectedSha256Digest = Objects.requireNonNull(expectedSha256Digest);
            this.physicalTamperFlag = physicalTamperFlag;
        }

        public String getSealId() { return sealId; }
        public String getExpectedSha256Digest() { return expectedSha256Digest; }
        public boolean isPhysicalTamperFlag() { return physicalTamperFlag; }

        public static String computeSealDigest(String sealId, String salt) {
            try {
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                byte[] hash = digest.digest((sealId + ":" + salt).getBytes());
                StringBuilder hex = new StringBuilder();
                for (byte b : hash) {
                    hex.append(String.format("%02x", b));
                }
                return hex.toString();
            } catch (NoSuchAlgorithmException e) {
                throw new RuntimeException("SHA-256 algorithm not available", e);
            }
        }
    }

    public static final class CustodyInterchangeEvent {
        private final String eventId;
        private final String containerIsoCode; // e.g. MSKU1234567
        private final TransportModality modality;
        private final String locationUnLoCode;  // e.g. USLAX, USCHI
        private final double latitude;
        private final double longitude;
        private final Instant timestamp;
        private final String releasingEntity;
        private final String receivingEntity;
        private final ElectronicSeal inspectedSeal;
        private final SealIntegrityStatus sealStatus;

        public CustodyInterchangeEvent(
                String eventId,
                String containerIsoCode,
                TransportModality modality,
                String locationUnLoCode,
                double latitude,
                double longitude,
                Instant timestamp,
                String releasingEntity,
                String receivingEntity,
                ElectronicSeal inspectedSeal,
                SealIntegrityStatus sealStatus) {
            this.eventId = Objects.requireNonNull(eventId);
            this.containerIsoCode = Objects.requireNonNull(containerIsoCode);
            this.modality = modality;
            this.locationUnLoCode = locationUnLoCode;
            this.latitude = latitude;
            this.longitude = longitude;
            this.timestamp = Objects.requireNonNull(timestamp);
            this.releasingEntity = releasingEntity;
            this.receivingEntity = receivingEntity;
            this.inspectedSeal = inspectedSeal;
            this.sealStatus = sealStatus;
        }

        public String getEventId() { return eventId; }
        public String getContainerIsoCode() { return containerIsoCode; }
        public TransportModality getModality() { return modality; }
        public String getLocationUnLoCode() { return locationUnLoCode; }
        public double getLatitude() { return latitude; }
        public double getLongitude() { return longitude; }
        public Instant getTimestamp() { return timestamp; }
        public String getReleasingEntity() { return releasingEntity; }
        public String getReceivingEntity() { return receivingEntity; }
        public ElectronicSeal getInspectedSeal() { return inspectedSeal; }
        public SealIntegrityStatus getSealStatus() { return sealStatus; }
    }

    public static final class CustodyLedgerValidationResult {
        private final String containerIsoCode;
        private final boolean chainOfCustodyValid;
        private final boolean tamperDetected;
        private final boolean impossibleSpeedDetected;
        private final List<String> anomalyDescriptions;

        public CustodyLedgerValidationResult(
                String containerIsoCode,
                boolean chainOfCustodyValid,
                boolean tamperDetected,
                boolean impossibleSpeedDetected,
                List<String> anomalyDescriptions) {
            this.containerIsoCode = containerIsoCode;
            this.chainOfCustodyValid = chainOfCustodyValid;
            this.tamperDetected = tamperDetected;
            this.impossibleSpeedDetected = impossibleSpeedDetected;
            this.anomalyDescriptions = Collections.unmodifiableList(new ArrayList<>(anomalyDescriptions));
        }

        public String getContainerIsoCode() { return containerIsoCode; }
        public boolean isChainOfCustodyValid() { return chainOfCustodyValid; }
        public boolean isTamperDetected() { return tamperDetected; }
        public boolean isImpossibleSpeedDetected() { return impossibleSpeedDetected; }
        public List<String> getAnomalyDescriptions() { return anomalyDescriptions; }
    }

    public static final class DemurrageAndDetentionAssessment {
        private final String containerIsoCode;
        private final long totalDaysHeld;
        private final long freeDaysAllowed;
        private final long billableDemurrageDays;
        private final Money demurrageCost;
        private final Money detentionCost;
        private final Money totalTerminalCharges;

        public DemurrageAndDetentionAssessment(
                String containerIsoCode,
                long totalDaysHeld,
                long freeDaysAllowed,
                long billableDemurrageDays,
                Money demurrageCost,
                Money detentionCost,
                Money totalTerminalCharges) {
            this.containerIsoCode = containerIsoCode;
            this.totalDaysHeld = totalDaysHeld;
            this.freeDaysAllowed = freeDaysAllowed;
            this.billableDemurrageDays = billableDemurrageDays;
            this.demurrageCost = demurrageCost;
            this.detentionCost = detentionCost;
            this.totalTerminalCharges = totalTerminalCharges;
        }

        public String getContainerIsoCode() { return containerIsoCode; }
        public long getTotalDaysHeld() { return totalDaysHeld; }
        public long getFreeDaysAllowed() { return freeDaysAllowed; }
        public long getBillableDemurrageDays() { return billableDemurrageDays; }
        public Money getDemurrageCost() { return demurrageCost; }
        public Money getDetentionCost() { return detentionCost; }
        public Money getTotalTerminalCharges() { return totalTerminalCharges; }
    }

    private final Map<String, List<CustodyInterchangeEvent>> containerAuditTrail = new HashMap<>();

    public void recordInterchangeEvent(CustodyInterchangeEvent event) {
        Objects.requireNonNull(event, "event cannot be null");
        containerAuditTrail.computeIfAbsent(event.getContainerIsoCode(), k -> new ArrayList<>()).add(event);
    }

    public List<CustodyInterchangeEvent> getContainerHistory(String containerIsoCode) {
        return Collections.unmodifiableList(containerAuditTrail.getOrDefault(containerIsoCode, Collections.emptyList()));
    }

    /**
     * Audits the end-to-end chain of custody for a shipping container across all multi-modal interchange points.
     */
    public CustodyLedgerValidationResult validateContainerChainOfCustody(String containerIsoCode) {
        List<CustodyInterchangeEvent> events = containerAuditTrail.get(containerIsoCode);
        if (events == null || events.isEmpty()) {
            return new CustodyLedgerValidationResult(
                    containerIsoCode, false, false, false,
                    Collections.singletonList("No custody events recorded for container")
            );
        }

        boolean tamperDetected = false;
        boolean impossibleSpeedDetected = false;
        List<String> anomalies = new ArrayList<>();

        // Sort events chronologically
        List<CustodyInterchangeEvent> sorted = new ArrayList<>(events);
        sorted.sort(Comparator.comparing(CustodyInterchangeEvent::getTimestamp));

        CustodyInterchangeEvent prev = null;
        for (CustodyInterchangeEvent current : sorted) {
            // 1. Seal Integrity Check
            if (current.getSealStatus() != SealIntegrityStatus.VERIFIED_INTACT) {
                tamperDetected = true;
                anomalies.add(String.format("Seal anomaly at %s [%s]: status is %s",
                        current.getLocationUnLoCode(), current.getModality(), current.getSealStatus()));
            }

            if (current.getInspectedSeal() != null && current.getInspectedSeal().isPhysicalTamperFlag()) {
                tamperDetected = true;
                anomalies.add(String.format("Physical tamper sensor triggered on seal %s at %s",
                        current.getInspectedSeal().getSealId(), current.getLocationUnLoCode()));
            }

            // 2. Anomaly: Impossible Transit Velocity (> 75 mph sustained over ground/water)
            if (prev != null) {
                double distanceMiles = haversineDistanceMiles(
                        prev.getLatitude(), prev.getLongitude(),
                        current.getLatitude(), current.getLongitude()
                );
                long seconds = Duration.between(prev.getTimestamp(), current.getTimestamp()).getSeconds();
                if (seconds > 0) {
                    double hours = seconds / 3600.0;
                    double speedMph = distanceMiles / hours;
                    if (speedMph > 75.0 && distanceMiles > 50.0) {
                        impossibleSpeedDetected = true;
                        anomalies.add(String.format("Impossible speed %.1f mph detected between %s and %s (dist: %.1f miles in %.1f hrs)",
                                speedMph, prev.getLocationUnLoCode(), current.getLocationUnLoCode(), distanceMiles, hours));
                    }
                }
            }
            prev = current;
        }

        boolean valid = !tamperDetected && !impossibleSpeedDetected;
        return new CustodyLedgerValidationResult(
                containerIsoCode, valid, tamperDetected, impossibleSpeedDetected, anomalies
        );
    }

    /**
     * Computes port terminal demurrage and equipment detention according to tiered tariff schedules.
     */
    public DemurrageAndDetentionAssessment calculateDemurrageAndDetention(
            String containerIsoCode,
            Instant vesselDischargeTime,
            Instant terminalGateOutTime,
            Instant emptyContainerReturnTime,
            int terminalFreeDays,
            int equipmentFreeDays,
            Money tier1DemurrageDailyRate,  // e.g. $150/day (days 5-8)
            Money tier2DemurrageDailyRate,  // e.g. $300/day (day 9+)
            Money equipmentDetentionDailyRate // e.g. $125/day
    ) {
        String currency = tier1DemurrageDailyRate.getCurrency();

        // 1. Demurrage (Port terminal dwell time)
        long portDwellDays = Math.max(0, Duration.between(vesselDischargeTime, terminalGateOutTime).toDays());
        long billableDemurrageDays = Math.max(0, portDwellDays - terminalFreeDays);

        BigDecimal demurrageTotal = BigDecimal.ZERO;
        if (billableDemurrageDays > 0) {
            long tier1Days = Math.min(billableDemurrageDays, 4); // First 4 penalty days under Tier 1
            long tier2Days = Math.max(0, billableDemurrageDays - 4);

            demurrageTotal = demurrageTotal.add(tier1DemurrageDailyRate.toMajorUnits().multiply(BigDecimal.valueOf(tier1Days)));
            demurrageTotal = demurrageTotal.add(tier2DemurrageDailyRate.toMajorUnits().multiply(BigDecimal.valueOf(tier2Days)));
        }

        // 2. Equipment Detention (Time between terminal gate out and empty return)
        long equipmentDays = Math.max(0, Duration.between(terminalGateOutTime, emptyContainerReturnTime).toDays());
        long billableDetentionDays = Math.max(0, equipmentDays - equipmentFreeDays);

        BigDecimal detentionTotal = BigDecimal.ZERO;
        if (billableDetentionDays > 0) {
            detentionTotal = equipmentDetentionDailyRate.toMajorUnits().multiply(BigDecimal.valueOf(billableDetentionDays));
        }

        BigDecimal combinedTotal = demurrageTotal.add(detentionTotal);

        return new DemurrageAndDetentionAssessment(
                containerIsoCode,
                portDwellDays,
                terminalFreeDays,
                billableDemurrageDays,
                Money.ofMajor(demurrageTotal, currency),
                Money.ofMajor(detentionTotal, currency),
                Money.ofMajor(combinedTotal, currency)
        );
    }

    private double haversineDistanceMiles(double lat1, double lon1, double lat2, double lon2) {
        final double R = 3958.8; // Earth radius in miles
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2)) *
                        Math.sin(dLon / 2) * Math.sin(dLon / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }
}
