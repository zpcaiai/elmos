package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.common.TemperatureRange;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.*;

/**
 * Enterprise Cold Chain IoT Telemetry Auditor.
 * Implements WHO Good Distribution Practice (GDP) Annex 5 &amp; USP &lt;1079&gt; compliance standards.
 * Computes Arrhenius Mean Kinetic Temperature (MKT), degree-minute thermal loads,
 * multi-sensor drift detection, and automatic lot quarantine disposition.
 */
public class ColdChainTelemetryAuditor {

    // Universal gas constant R = 8.314472 J/(mol*K)
    private static final double GAS_CONSTANT = 8.314472;
    // Standard activation energy for pharmaceutical thermal degradation: Delta H = 83.144 kJ/mol
    private static final double ACTIVATION_ENERGY = 83144.0;
    // Ratio Delta H / R = 10,000 Kelvin
    private static final double ARRHENIUS_RATIO = ACTIVATION_ENERGY / GAS_CONSTANT;
    // Celsius to Kelvin offset
    private static final double KELVIN_OFFSET = 273.15;

    public enum ExcursionSeverity {
        NORMAL,
        MINOR_TRANSIENT,
        MAJOR_INVESTIGATION,
        CRITICAL_BREACH,
        QUARANTINE_MANDATORY
    }

    public static final class TelemetryReading implements Comparable<TelemetryReading> {
        private final String readingId;
        private final String sensorId;
        private final String lotId;
        private final Instant timestamp;
        private final double temperatureCelsius;
        private final double relativeHumidityPercent;
        private final int batteryMillivolts;

        public TelemetryReading(String readingId, String sensorId, String lotId, Instant timestamp,
                                double temperatureCelsius, double relativeHumidityPercent, int batteryMillivolts) {
            this.readingId = Objects.requireNonNull(readingId, "readingId");
            this.sensorId = Objects.requireNonNull(sensorId, "sensorId");
            this.lotId = Objects.requireNonNull(lotId, "lotId");
            this.timestamp = Objects.requireNonNull(timestamp, "timestamp");
            this.temperatureCelsius = temperatureCelsius;
            this.relativeHumidityPercent = relativeHumidityPercent;
            this.batteryMillivolts = batteryMillivolts;
        }

        public String getReadingId() { return readingId; }
        public String getSensorId() { return sensorId; }
        public String getLotId() { return lotId; }
        public Instant getTimestamp() { return timestamp; }
        public double getTemperatureCelsius() { return temperatureCelsius; }
        public double getRelativeHumidityPercent() { return relativeHumidityPercent; }
        public int getBatteryMillivolts() { return batteryMillivolts; }

        public double getTemperatureKelvin() {
            return temperatureCelsius + KELVIN_OFFSET;
        }

        @Override
        public int compareTo(TelemetryReading o) {
            return this.timestamp.compareTo(o.timestamp);
        }
    }

    public static final class ExcursionRecord {
        private final Instant startTime;
        private final Instant endTime;
        private final long durationSeconds;
        private final double peakTemperature;
        private final double thermalLoadDegreeMinutes;
        private final ExcursionSeverity severity;
        private final String rootCauseEstimate;
        private final boolean quarantineTriggered;

        public ExcursionRecord(Instant startTime, Instant endTime, long durationSeconds,
                               double peakTemperature, double thermalLoadDegreeMinutes,
                               ExcursionSeverity severity, String rootCauseEstimate, boolean quarantineTriggered) {
            this.startTime = startTime;
            this.endTime = endTime;
            this.durationSeconds = durationSeconds;
            this.peakTemperature = peakTemperature;
            this.thermalLoadDegreeMinutes = thermalLoadDegreeMinutes;
            this.severity = severity;
            this.rootCauseEstimate = rootCauseEstimate;
            this.quarantineTriggered = quarantineTriggered;
        }

        public Instant getStartTime() { return startTime; }
        public Instant getEndTime() { return endTime; }
        public long getDurationSeconds() { return durationSeconds; }
        public double getPeakTemperature() { return peakTemperature; }
        public double getThermalLoadDegreeMinutes() { return thermalLoadDegreeMinutes; }
        public ExcursionSeverity getSeverity() { return severity; }
        public String getRootCauseEstimate() { return rootCauseEstimate; }
        public boolean isQuarantineTriggered() { return quarantineTriggered; }
    }

    public static final class ColdChainAuditSummary {
        private final String lotId;
        private final int totalReadings;
        private final double minRecordedCelsius;
        private final double maxRecordedCelsius;
        private final double averageCelsius;
        private final double meanKineticTemperatureCelsius;
        private final double totalDegreeMinutesAboveUpper;
        private final double totalDegreeMinutesBelowLower;
        private final List<ExcursionRecord> excursions;
        private final boolean gdpCompliant;
        private final boolean quarantineEnforced;
        private final String complianceReportHash;
        private final List<String> operationalAlerts;

        public ColdChainAuditSummary(String lotId, int totalReadings, double minRecordedCelsius,
                                     double maxRecordedCelsius, double averageCelsius,
                                     double meanKineticTemperatureCelsius,
                                     double totalDegreeMinutesAboveUpper, double totalDegreeMinutesBelowLower,
                                     List<ExcursionRecord> excursions, boolean gdpCompliant,
                                     boolean quarantineEnforced, String complianceReportHash,
                                     List<String> operationalAlerts) {
            this.lotId = lotId;
            this.totalReadings = totalReadings;
            this.minRecordedCelsius = minRecordedCelsius;
            this.maxRecordedCelsius = maxRecordedCelsius;
            this.averageCelsius = averageCelsius;
            this.meanKineticTemperatureCelsius = meanKineticTemperatureCelsius;
            this.totalDegreeMinutesAboveUpper = totalDegreeMinutesAboveUpper;
            this.totalDegreeMinutesBelowLower = totalDegreeMinutesBelowLower;
            this.excursions = Collections.unmodifiableList(excursions);
            this.gdpCompliant = gdpCompliant;
            this.quarantineEnforced = quarantineEnforced;
            this.complianceReportHash = complianceReportHash;
            this.operationalAlerts = Collections.unmodifiableList(operationalAlerts);
        }

        public String getLotId() { return lotId; }
        public int getTotalReadings() { return totalReadings; }
        public double getMinRecordedCelsius() { return minRecordedCelsius; }
        public double getMaxRecordedCelsius() { return maxRecordedCelsius; }
        public double getAverageCelsius() { return averageCelsius; }
        public double getMeanKineticTemperatureCelsius() { return meanKineticTemperatureCelsius; }
        public double getTotalDegreeMinutesAboveUpper() { return totalDegreeMinutesAboveUpper; }
        public double getTotalDegreeMinutesBelowLower() { return totalDegreeMinutesBelowLower; }
        public List<ExcursionRecord> getExcursions() { return excursions; }
        public boolean isGdpCompliant() { return gdpCompliant; }
        public boolean isQuarantineEnforced() { return quarantineEnforced; }
        public String getComplianceReportHash() { return complianceReportHash; }
        public List<String> getOperationalAlerts() { return operationalAlerts; }
    }

    /**
     * Executes end-to-end telemetry auditing on a sequence of IoT loggers.
     */
    public ColdChainAuditSummary auditTelemetry(String lotId,
                                                TemperatureRange allowedRange,
                                                List<TelemetryReading> readings,
                                                double maxAllowableMktCelsius,
                                                double maxDegreeMinutesUpperLimit) {
        Objects.requireNonNull(lotId, "lotId");
        Objects.requireNonNull(allowedRange, "allowedRange");
        Objects.requireNonNull(readings, "readings");

        if (readings.isEmpty()) {
            throw new IllegalArgumentException("Cannot audit empty telemetry reading stream for lot: " + lotId);
        }

        List<TelemetryReading> sorted = new ArrayList<>(readings);
        Collections.sort(sorted);

        List<String> alerts = new ArrayList<>();
        double minTemp = Double.MAX_VALUE;
        double maxTemp = -Double.MAX_VALUE;
        double sumTemp = 0.0;
        double sumArrheniusTerms = 0.0;

        // Anomaly & Sensor Health Tracking
        Set<String> uniqueSensors = new HashSet<>();
        for (TelemetryReading r : sorted) {
            uniqueSensors.add(r.getSensorId());
            double t = r.getTemperatureCelsius();
            if (t < minTemp) minTemp = t;
            if (t > maxTemp) maxTemp = t;
            sumTemp += t;

            double tk = r.getTemperatureKelvin();
            if (tk <= 0) {
                throw new IllegalStateException("Absolute temperature below 0K detected: " + tk);
            }
            sumArrheniusTerms += Math.exp(-ARRHENIUS_RATIO / tk);

            // Check battery health
            if (r.getBatteryMillivolts() < 2400) {
                alerts.add(String.format("Sensor %s battery critical: %d mV at %s",
                        r.getSensorId(), r.getBatteryMillivolts(), r.getTimestamp()));
            }
            // Check extreme humidity
            if (r.getRelativeHumidityPercent() > 85.0) {
                alerts.add(String.format("Excessive relative humidity warning: %.1f%% on lot %s at %s",
                        r.getRelativeHumidityPercent(), lotId, r.getTimestamp()));
            }
        }

        int n = sorted.size();
        double avgTemp = sumTemp / n;

        // Arrhenius MKT Formula:
        // MKT = (DeltaH / R) / -ln( (1/n) * sum(e^(-(DeltaH / R) / Tk_i)) ) - 273.15
        double meanExp = sumArrheniusTerms / n;
        double mktKelvin = ARRHENIUS_RATIO / (-Math.log(meanExp));
        double mktCelsius = mktKelvin - KELVIN_OFFSET;

        // Multi-Sensor Inter-Logger Discrepancy (Drift Detection)
        if (uniqueSensors.size() > 1) {
            Map<String, List<Double>> sensorTemps = new HashMap<>();
            for (TelemetryReading r : sorted) {
                sensorTemps.computeIfAbsent(r.getSensorId(), k -> new ArrayList<>()).add(r.getTemperatureCelsius());
            }
            Map<String, Double> sensorAvgs = new HashMap<>();
            for (Map.Entry<String, List<Double>> entry : sensorTemps.entrySet()) {
                double avg = entry.getValue().stream().mapToDouble(Double::doubleValue).average().orElse(0.0);
                sensorAvgs.put(entry.getKey(), avg);
            }
            double minSensorAvg = Collections.min(sensorAvgs.values());
            double maxSensorAvg = Collections.max(sensorAvgs.values());
            if (maxSensorAvg - minSensorAvg > 2.5) {
                alerts.add(String.format("Sensor calibration drift detected! Discrepancy between loggers is %.2f°C",
                        maxSensorAvg - minSensorAvg));
            }
        }

        // Excursion & Degree-Minute Integration
        List<ExcursionRecord> excursions = new ArrayList<>();
        double totalDegreeMinAbove = 0.0;
        double totalDegreeMinBelow = 0.0;

        boolean inExcursion = false;
        Instant excursionStart = null;
        double peakExcursionTemp = 0.0;
        double currentExcursionDegreeMinutes = 0.0;
        boolean upperBreach = false;

        for (int i = 0; i < sorted.size(); i++) {
            TelemetryReading curr = sorted.get(i);
            double temp = curr.getTemperatureCelsius();
            long intervalMinutes = 0;
            if (i > 0) {
                intervalMinutes = Math.max(1, (curr.getTimestamp().toEpochMilli() - sorted.get(i - 1).getTimestamp().toEpochMilli()) / 60000);
            } else {
                intervalMinutes = 1;
            }

            boolean isAbove = temp > allowedRange.getMaxCelsius();
            boolean isBelow = temp < allowedRange.getMinCelsius();

            if (isAbove) {
                double diff = temp - allowedRange.getMaxCelsius();
                double degMin = diff * intervalMinutes;
                totalDegreeMinAbove += degMin;

                if (!inExcursion) {
                    inExcursion = true;
                    excursionStart = curr.getTimestamp();
                    peakExcursionTemp = temp;
                    currentExcursionDegreeMinutes = degMin;
                    upperBreach = true;
                } else {
                    if (temp > peakExcursionTemp) peakExcursionTemp = temp;
                    currentExcursionDegreeMinutes += degMin;
                }
            } else if (isBelow) {
                double diff = allowedRange.getMinCelsius() - temp;
                double degMin = diff * intervalMinutes;
                totalDegreeMinBelow += degMin;

                if (!inExcursion) {
                    inExcursion = true;
                    excursionStart = curr.getTimestamp();
                    peakExcursionTemp = temp;
                    currentExcursionDegreeMinutes = degMin;
                    upperBreach = false;
                } else {
                    if (temp < peakExcursionTemp) peakExcursionTemp = temp;
                    currentExcursionDegreeMinutes += degMin;
                }
            } else {
                // In normal zone
                if (inExcursion) {
                    // Close previous excursion
                    Instant excursionEnd = curr.getTimestamp();
                    long durationSec = (excursionEnd.toEpochMilli() - excursionStart.toEpochMilli()) / 1000;
                    ExcursionSeverity severity = classifySeverity(upperBreach, peakExcursionTemp,
                            currentExcursionDegreeMinutes, durationSec, allowedRange);
                    boolean quarantine = severity == ExcursionSeverity.QUARANTINE_MANDATORY ||
                            severity == ExcursionSeverity.CRITICAL_BREACH;
                    String cause = upperBreach ? "Refrigeration cooling failure or ambient heat exposure"
                            : "Thermostat undercooling or sub-zero freezing excursion";

                    excursions.add(new ExcursionRecord(excursionStart, excursionEnd, durationSec,
                            peakExcursionTemp, currentExcursionDegreeMinutes, severity, cause, quarantine));

                    inExcursion = false;
                    excursionStart = null;
                    peakExcursionTemp = 0.0;
                    currentExcursionDegreeMinutes = 0.0;
                }
            }
        }

        // Handle open excursion at the end of stream
        if (inExcursion) {
            Instant excursionEnd = sorted.get(sorted.size() - 1).getTimestamp();
            long durationSec = Math.max(60, (excursionEnd.toEpochMilli() - excursionStart.toEpochMilli()) / 1000);
            ExcursionSeverity severity = classifySeverity(upperBreach, peakExcursionTemp,
                    currentExcursionDegreeMinutes, durationSec, allowedRange);
            boolean quarantine = severity == ExcursionSeverity.QUARANTINE_MANDATORY ||
                    severity == ExcursionSeverity.CRITICAL_BREACH;
            String cause = "Unresolved ongoing thermal excursion at recording closure";

            excursions.add(new ExcursionRecord(excursionStart, excursionEnd, durationSec,
                    peakExcursionTemp, currentExcursionDegreeMinutes, severity, cause, quarantine));
        }

        // Compliance & Quarantine Decision
        boolean quarantineEnforced = false;
        if (mktCelsius > maxAllowableMktCelsius) {
            alerts.add(String.format("MKT breach: calculated %.2f°C exceeds permitted threshold %.2f°C",
                    mktCelsius, maxAllowableMktCelsius));
            quarantineEnforced = true;
        }
        if (totalDegreeMinAbove > maxDegreeMinutesUpperLimit) {
            alerts.add(String.format("Thermal degree-minutes accumulated (%.1f °C*min) exceeds limit (%.1f °C*min)",
                    totalDegreeMinAbove, maxDegreeMinutesUpperLimit));
            quarantineEnforced = true;
        }
        // Sub-zero freezing check for chilled biologics (2-8°C cannot tolerate < 0°C)
        if (allowedRange.getMinCelsius() >= 2.0 && minTemp <= 0.0) {
            alerts.add(String.format("CRITICAL: Freeze event recorded (%.2f°C)! Protein denaturation risk.", minTemp));
            quarantineEnforced = true;
        }

        for (ExcursionRecord exc : excursions) {
            if (exc.isQuarantineTriggered()) {
                quarantineEnforced = true;
            }
        }

        boolean gdpCompliant = !quarantineEnforced && excursions.isEmpty();

        // Cryptographic Audit Certificate Hash (SHA-256 Merkle Leaf)
        String reportHash = computeAuditHash(lotId, n, mktCelsius, minTemp, maxTemp,
                totalDegreeMinAbove, quarantineEnforced);

        return new ColdChainAuditSummary(lotId, n, round2(minTemp), round2(maxTemp),
                round2(avgTemp), round2(mktCelsius), round2(totalDegreeMinAbove),
                round2(totalDegreeMinBelow), excursions, gdpCompliant,
                quarantineEnforced, reportHash, alerts);
    }

    private ExcursionSeverity classifySeverity(boolean upper, double peakTemp, double degMin,
                                              long durationSec, TemperatureRange range) {
        if (!upper) {
            // Freezing risk
            if (range.getMinCelsius() >= 2.0 && peakTemp <= 0.0) {
                return ExcursionSeverity.QUARANTINE_MANDATORY;
            }
            if (durationSec > 7200) { // 2 hours below min
                return ExcursionSeverity.CRITICAL_BREACH;
            }
            return ExcursionSeverity.MAJOR_INVESTIGATION;
        } else {
            double delta = peakTemp - range.getMaxCelsius();
            if (delta > 15.0 || degMin > 1200.0) {
                return ExcursionSeverity.QUARANTINE_MANDATORY;
            }
            if (delta > 7.0 || durationSec > 14400) { // 4 hours
                return ExcursionSeverity.CRITICAL_BREACH;
            }
            if (delta > 3.0 || durationSec > 3600) { // 1 hour
                return ExcursionSeverity.MAJOR_INVESTIGATION;
            }
            return ExcursionSeverity.MINOR_TRANSIENT;
        }
    }

    private String computeAuditHash(String lotId, int count, double mkt, double min,
                                    double max, double degMin, boolean quarantine) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            String payload = String.format("LOT:%s|COUNT:%d|MKT:%.4f|MIN:%.2f|MAX:%.2f|DEGMIN:%.2f|Q:%b",
                    lotId, count, mkt, min, max, degMin, quarantine);
            byte[] digest = md.digest(payload.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : digest) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException("SHA-256 not available", e);
        }
    }

    private static double round2(double val) {
        return BigDecimal.valueOf(val).setScale(2, RoundingMode.HALF_UP).doubleValue();
    }
}
