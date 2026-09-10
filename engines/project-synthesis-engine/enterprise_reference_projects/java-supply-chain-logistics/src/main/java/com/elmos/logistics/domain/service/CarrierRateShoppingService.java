package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.Money;
import com.elmos.logistics.domain.model.common.Weight;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.*;

/**
 * Enterprise Multi-Modal Carrier Rate Shopping &amp; Carbon Emission Engine.
 * Supports Parcel, LTL, FTL, and Air Expedited modal selection,
 * dimensional weight calculation, EIA fuel surcharge indexing,
 * accessorial charge evaluation, and GLEC-compliant CO2 footprint auditing.
 */
public class CarrierRateShoppingService {

    public enum TransportMode {
        PARCEL_GROUND(139, 62.0),       // US Domestic Dim Divisor, 62g CO2/t-km
        PARCEL_EXPEDITED(139, 150.0),   // Air/Road blend
        LTL_FREIGHT(250, 85.0),         // Less-Than-Truckload
        FTL_DIRECT(0, 52.0),            // Full Truckload (flat vehicle rate)
        AIR_CARGO_EXPRESS(5000, 500.0); // IATA Metric Dim Divisor, 500g CO2/t-km

        private final int standardDimDivisor;
        private final double co2GramsPerTonneKm;

        TransportMode(int standardDimDivisor, double co2GramsPerTonneKm) {
            this.standardDimDivisor = standardDimDivisor;
            this.co2GramsPerTonneKm = co2GramsPerTonneKm;
        }

        public int getStandardDimDivisor() { return standardDimDivisor; }
        public double getCo2GramsPerTonneKm() { return co2GramsPerTonneKm; }
    }

    public enum AccessorialType {
        LIFTGATE_ORIGIN(BigDecimal.valueOf(65.0)),
        LIFTGATE_DESTINATION(BigDecimal.valueOf(65.0)),
        RESIDENTIAL_DELIVERY(BigDecimal.valueOf(85.0)),
        INSIDE_DELIVERY(BigDecimal.valueOf(110.0)),
        HAZMAT_COMPLIANCE(BigDecimal.valueOf(175.0)),
        SATURDAY_APPOINTMENT(BigDecimal.valueOf(150.0)),
        LIMITED_ACCESS(BigDecimal.valueOf(75.0));

        private final BigDecimal standardFeeUsd;

        AccessorialType(BigDecimal standardFeeUsd) {
            this.standardFeeUsd = standardFeeUsd;
        }

        public BigDecimal getStandardFeeUsd() { return standardFeeUsd; }
    }

    public static final class CarrierContract {
        private final String carrierId;
        private final String carrierName;
        private final TransportMode mode;
        private final BigDecimal baseRatePerHundredweight; // $/CWT (per 100 lbs or approx 45kg)
        private final BigDecimal minimumCharge;
        private final BigDecimal fuelSurchargePercent; // e.g. 18.5%
        private final Map<AccessorialType, BigDecimal> negotiatedAccessorialFees;
        private final double serviceReliabilityScore; // 0.0 to 1.0 historical on-time %

        public CarrierContract(String carrierId, String carrierName, TransportMode mode,
                               BigDecimal baseRatePerHundredweight, BigDecimal minimumCharge,
                               BigDecimal fuelSurchargePercent,
                               Map<AccessorialType, BigDecimal> negotiatedAccessorialFees,
                               double serviceReliabilityScore) {
            this.carrierId = Objects.requireNonNull(carrierId, "carrierId");
            this.carrierName = Objects.requireNonNull(carrierName, "carrierName");
            this.mode = Objects.requireNonNull(mode, "mode");
            this.baseRatePerHundredweight = baseRatePerHundredweight;
            this.minimumCharge = minimumCharge;
            this.fuelSurchargePercent = fuelSurchargePercent;
            this.negotiatedAccessorialFees = negotiatedAccessorialFees != null
                    ? new HashMap<>(negotiatedAccessorialFees) : Collections.emptyMap();
            this.serviceReliabilityScore = serviceReliabilityScore;
        }

        public String getCarrierId() { return carrierId; }
        public String getCarrierName() { return carrierName; }
        public TransportMode getMode() { return mode; }
        public BigDecimal getBaseRatePerHundredweight() { return baseRatePerHundredweight; }
        public BigDecimal getMinimumCharge() { return minimumCharge; }
        public BigDecimal getFuelSurchargePercent() { return fuelSurchargePercent; }
        public Map<AccessorialType, BigDecimal> getNegotiatedAccessorialFees() { return negotiatedAccessorialFees; }
        public double getServiceReliabilityScore() { return serviceReliabilityScore; }
    }

    public static final class ShippingConsignmentRequest {
        private final String shipmentId;
        private final String originZip;
        private final String destinationZip;
        private final double distanceKm;
        private final double actualWeightKg;
        private final Dimensions packageDimensions;
        private final Set<AccessorialType> requestedAccessorials;
        private final boolean requiresHazmat;
        private final int transitDayDeadline;

        public ShippingConsignmentRequest(String shipmentId, String originZip, String destinationZip,
                                         double distanceKm, double actualWeightKg,
                                         Dimensions packageDimensions,
                                         Set<AccessorialType> requestedAccessorials,
                                         boolean requiresHazmat, int transitDayDeadline) {
            this.shipmentId = Objects.requireNonNull(shipmentId, "shipmentId");
            this.originZip = Objects.requireNonNull(originZip, "originZip");
            this.destinationZip = Objects.requireNonNull(destinationZip, "destinationZip");
            this.distanceKm = distanceKm;
            this.actualWeightKg = actualWeightKg;
            this.packageDimensions = Objects.requireNonNull(packageDimensions, "packageDimensions");
            this.requestedAccessorials = requestedAccessorials != null ? new HashSet<>(requestedAccessorials) : Collections.emptySet();
            this.requiresHazmat = requiresHazmat;
            this.transitDayDeadline = transitDayDeadline;
        }

        public String getShipmentId() { return shipmentId; }
        public String getOriginZip() { return originZip; }
        public String getDestinationZip() { return destinationZip; }
        public double getDistanceKm() { return distanceKm; }
        public double getActualWeightKg() { return actualWeightKg; }
        public Dimensions getPackageDimensions() { return packageDimensions; }
        public Set<AccessorialType> getRequestedAccessorials() { return requestedAccessorials; }
        public boolean isRequiresHazmat() { return requiresHazmat; }
        public int getTransitDayDeadline() { return transitDayDeadline; }
    }

    public static final class CarrierQuote implements Comparable<CarrierQuote> {
        private final CarrierContract carrier;
        private final double billableWeightKg;
        private final BigDecimal baseLinehaulFreight;
        private final BigDecimal fuelSurchargeAmount;
        private final BigDecimal accessorialsTotal;
        private final BigDecimal grandTotalRate;
        private final int estimatedTransitDays;
        private final double estimatedCo2Kg;
        private final boolean meetsSlaDeadline;

        public CarrierQuote(CarrierContract carrier, double billableWeightKg,
                            BigDecimal baseLinehaulFreight, BigDecimal fuelSurchargeAmount,
                            BigDecimal accessorialsTotal, BigDecimal grandTotalRate,
                            int estimatedTransitDays, double estimatedCo2Kg,
                            boolean meetsSlaDeadline) {
            this.carrier = carrier;
            this.billableWeightKg = billableWeightKg;
            this.baseLinehaulFreight = baseLinehaulFreight;
            this.fuelSurchargeAmount = fuelSurchargeAmount;
            this.accessorialsTotal = accessorialsTotal;
            this.grandTotalRate = grandTotalRate;
            this.estimatedTransitDays = estimatedTransitDays;
            this.estimatedCo2Kg = estimatedCo2Kg;
            this.meetsSlaDeadline = meetsSlaDeadline;
        }

        public CarrierContract getCarrier() { return carrier; }
        public double getBillableWeightKg() { return billableWeightKg; }
        public BigDecimal getBaseLinehaulFreight() { return baseLinehaulFreight; }
        public BigDecimal getFuelSurchargeAmount() { return fuelSurchargeAmount; }
        public BigDecimal getAccessorialsTotal() { return accessorialsTotal; }
        public BigDecimal getGrandTotalRate() { return grandTotalRate; }
        public int getEstimatedTransitDays() { return estimatedTransitDays; }
        public double getEstimatedCo2Kg() { return estimatedCo2Kg; }
        public boolean isMeetsSlaDeadline() { return meetsSlaDeadline; }

        @Override
        public int compareTo(CarrierQuote o) {
            // Sort by total cost ascending
            return this.grandTotalRate.compareTo(o.grandTotalRate);
        }
    }

    private final List<CarrierContract> carriers = new ArrayList<>();

    public void registerCarrier(CarrierContract contract) {
        Objects.requireNonNull(contract, "contract");
        carriers.add(contract);
    }

    /**
     * Evaluates dimensional weight across metric and imperial conversion divisors.
     */
    public double calculateDimensionalWeightKg(Dimensions dim, TransportMode mode) {
        if (mode == TransportMode.FTL_DIRECT) {
            return 0.0;
        }
        // Volume in cubic centimeters
        double volCm3 = (dim.getLengthMm() / 10.0) * (dim.getWidthMm() / 10.0) * (dim.getHeightMm() / 10.0);
        if (mode == TransportMode.AIR_CARGO_EXPRESS) {
            // IATA Metric: 5000 cm3/kg
            return Math.max(1.0, volCm3 / 5000.0);
        } else {
            // Commercial ground: approx 6000 cm3/kg (139 in3/lb)
            return Math.max(1.0, volCm3 / 6000.0);
        }
    }

    /**
     * Executes rate shopping across all registered carrier tariffs for a given shipment.
     */
    public List<CarrierQuote> shopRates(ShippingConsignmentRequest req) {
        Objects.requireNonNull(req, "req");
        List<CarrierQuote> quotes = new ArrayList<>();

        for (CarrierContract c : carriers) {
            // Calculate billable weight
            double dimWeight = calculateDimensionalWeightKg(req.getPackageDimensions(), c.getMode());
            double billableWeightKg = Math.max(req.getActualWeightKg(), dimWeight);

            // Convert to hundredweight (CWT: 100 lbs approx 45.359 kg)
            double cwt = billableWeightKg / 45.3592;
            BigDecimal linehaul = c.getBaseRatePerHundredweight()
                    .multiply(BigDecimal.valueOf(cwt))
                    .setScale(2, RoundingMode.HALF_UP);

            if (linehaul.compareTo(c.getMinimumCharge()) < 0) {
                linehaul = c.getMinimumCharge();
            }

            // Distance scaling for freight
            BigDecimal distanceFactor = BigDecimal.valueOf(Math.max(1.0, req.getDistanceKm() / 500.0));
            linehaul = linehaul.multiply(distanceFactor).setScale(2, RoundingMode.HALF_UP);

            // Fuel surcharge
            BigDecimal fuel = linehaul.multiply(c.getFuelSurchargePercent())
                    .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);

            // Accessorial fees
            BigDecimal accessorialSum = BigDecimal.ZERO;
            for (AccessorialType acc : req.getRequestedAccessorials()) {
                BigDecimal fee = c.getNegotiatedAccessorialFees().getOrDefault(acc, acc.getStandardFeeUsd());
                accessorialSum = accessorialSum.add(fee);
            }
            if (req.isRequiresHazmat()) {
                BigDecimal fee = c.getNegotiatedAccessorialFees().getOrDefault(
                        AccessorialType.HAZMAT_COMPLIANCE, AccessorialType.HAZMAT_COMPLIANCE.getStandardFeeUsd());
                accessorialSum = accessorialSum.add(fee);
            }

            BigDecimal grandTotal = linehaul.add(fuel).add(accessorialSum);

            // Transit time estimation based on distance and mode
            int transitDays = estimateTransitDays(c.getMode(), req.getDistanceKm());
            boolean meetsSla = transitDays <= req.getTransitDayDeadline();

            // GLEC Carbon Emission: Tonnes * DistanceKm * g/t-km / 1000
            double tonnes = billableWeightKg / 1000.0;
            double co2Kg = (tonnes * req.getDistanceKm() * c.getMode().getCo2GramsPerTonneKm()) / 1000.0;

            quotes.add(new CarrierQuote(c, Math.round(billableWeightKg * 100.0) / 100.0,
                    linehaul, fuel, accessorialSum, grandTotal, transitDays,
                    Math.round(co2Kg * 100.0) / 100.0, meetsSla));
        }

        Collections.sort(quotes);
        return quotes;
    }

    private int estimateTransitDays(TransportMode mode, double distanceKm) {
        switch (mode) {
            case AIR_CARGO_EXPRESS:
                return 1;
            case PARCEL_EXPEDITED:
                return distanceKm > 1500 ? 2 : 1;
            case PARCEL_GROUND:
            case LTL_FREIGHT:
                if (distanceKm <= 500) return 1;
                if (distanceKm <= 1500) return 2;
                if (distanceKm <= 3000) return 3;
                return 4;
            case FTL_DIRECT:
                return (int) Math.ceil(distanceKm / 800.0); // 800km per driving day
            default:
                return 3;
        }
    }
}
