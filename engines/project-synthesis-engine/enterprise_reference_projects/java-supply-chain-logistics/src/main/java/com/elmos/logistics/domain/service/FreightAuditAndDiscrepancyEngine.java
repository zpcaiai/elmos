package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.common.Money;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.*;

public class FreightAuditAndDiscrepancyEngine {

    public enum FreightInvoiceType {
        MOTOR_LTL,
        MOTOR_FTL,
        OCEAN_FCL,
        INTERMODAL_RAIL
    }

    public enum AccessorialCode {
        LINEHAUL_BASE,
        FUEL_SURCHARGE,
        DETENTION_AT_SITE,
        LIFTGATE_SERVICE,
        RESIDENTIAL_DELIVERY,
        INSIDE_PICKUP_DELIVERY,
        RE_WEIGH_RE_CLASS,
        HAZMAT_SURCHARGE
    }

    public enum DiscrepancyClaimCode {
        RATE_OVERBILLING,
        UNAUTHORIZED_ACCESSORIAL,
        EXCESSIVE_DETENTION,
        WEIGHT_SURCHARGE_DISCREPANCY,
        FUEL_SURCHARGE_MISCALCULATION,
        DUPLICATE_BILLING
    }

    public enum VoucherStatus {
        APPROVED_AUTO_PAY,
        APPROVED_WITH_ADJUSTMENTS,
        REJECTED_DISPUTED
    }

    public static final class InvoiceLineItem {
        private final String lineId;
        private final AccessorialCode code;
        private final String description;
        private final BigDecimal billedUnits;
        private final Money ratePerUnit;
        private final Money billedAmount;

        public InvoiceLineItem(String lineId, AccessorialCode code, String description, BigDecimal billedUnits, Money ratePerUnit, Money billedAmount) {
            this.lineId = Objects.requireNonNull(lineId, "lineId cannot be null");
            this.code = Objects.requireNonNull(code, "code cannot be null");
            this.description = description;
            this.billedUnits = billedUnits != null ? billedUnits : BigDecimal.ONE;
            this.ratePerUnit = ratePerUnit;
            this.billedAmount = Objects.requireNonNull(billedAmount, "billedAmount cannot be null");
        }

        public String getLineId() { return lineId; }
        public AccessorialCode getCode() { return code; }
        public String getDescription() { return description; }
        public BigDecimal getBilledUnits() { return billedUnits; }
        public Money getRatePerUnit() { return ratePerUnit; }
        public Money getBilledAmount() { return billedAmount; }
    }

    public static final class CarrierFreightInvoice {
        private final String invoiceNumber;
        private final String carrierScac;
        private final String bolNumber;
        private final FreightInvoiceType invoiceType;
        private final LocalDate invoiceDate;
        private final List<InvoiceLineItem> lineItems;
        private final Money billedTotal;

        public CarrierFreightInvoice(String invoiceNumber, String carrierScac, String bolNumber, FreightInvoiceType invoiceType, LocalDate invoiceDate, List<InvoiceLineItem> lineItems, Money billedTotal) {
            this.invoiceNumber = Objects.requireNonNull(invoiceNumber, "invoiceNumber cannot be null");
            this.carrierScac = Objects.requireNonNull(carrierScac, "carrierScac cannot be null");
            this.bolNumber = Objects.requireNonNull(bolNumber, "bolNumber cannot be null");
            this.invoiceType = invoiceType;
            this.invoiceDate = invoiceDate;
            this.lineItems = Collections.unmodifiableList(new ArrayList<>(lineItems));
            this.billedTotal = Objects.requireNonNull(billedTotal, "billedTotal cannot be null");
        }

        public String getInvoiceNumber() { return invoiceNumber; }
        public String getCarrierScac() { return carrierScac; }
        public String getBolNumber() { return bolNumber; }
        public FreightInvoiceType getInvoiceType() { return invoiceType; }
        public LocalDate getInvoiceDate() { return invoiceDate; }
        public List<InvoiceLineItem> getLineItems() { return lineItems; }
        public Money getBilledTotal() { return billedTotal; }
    }

    public static final class AgreedFreightContract {
        private final String contractId;
        private final String carrierScac;
        private final Money baseLinehaulRate;
        private final BigDecimal fscBaselineDieselPricePerGal;
        private final BigDecimal fscIndexDieselPricePerGal;
        private final BigDecimal fscRatePercentPerIncrement; // e.g. 0.005 for 0.5%
        private final BigDecimal fscPriceIncrementStep;      // e.g. 0.05 ($0.05/gal step)
        private final BigDecimal allowedDetentionFreeHours;
        private final Money detentionHourlyRate;
        private final Map<AccessorialCode, Money> agreedAccessorialRates;
        private final BigDecimal tolerancePercentage;        // e.g. 0.015 for 1.5%
        private final Money toleranceAbsoluteThreshold;      // e.g. $25.00

        public AgreedFreightContract(
                String contractId,
                String carrierScac,
                Money baseLinehaulRate,
                BigDecimal fscBaselineDieselPricePerGal,
                BigDecimal fscIndexDieselPricePerGal,
                BigDecimal fscRatePercentPerIncrement,
                BigDecimal fscPriceIncrementStep,
                BigDecimal allowedDetentionFreeHours,
                Money detentionHourlyRate,
                Map<AccessorialCode, Money> agreedAccessorialRates,
                BigDecimal tolerancePercentage,
                Money toleranceAbsoluteThreshold) {
            this.contractId = Objects.requireNonNull(contractId);
            this.carrierScac = Objects.requireNonNull(carrierScac);
            this.baseLinehaulRate = Objects.requireNonNull(baseLinehaulRate);
            this.fscBaselineDieselPricePerGal = fscBaselineDieselPricePerGal;
            this.fscIndexDieselPricePerGal = fscIndexDieselPricePerGal;
            this.fscRatePercentPerIncrement = fscRatePercentPerIncrement;
            this.fscPriceIncrementStep = fscPriceIncrementStep;
            this.allowedDetentionFreeHours = allowedDetentionFreeHours;
            this.detentionHourlyRate = Objects.requireNonNull(detentionHourlyRate);
            this.agreedAccessorialRates = new EnumMap<>(agreedAccessorialRates);
            this.tolerancePercentage = tolerancePercentage;
            this.toleranceAbsoluteThreshold = toleranceAbsoluteThreshold;
        }

        public String getContractId() { return contractId; }
        public String getCarrierScac() { return carrierScac; }
        public Money getBaseLinehaulRate() { return baseLinehaulRate; }
        public BigDecimal getFscBaselineDieselPricePerGal() { return fscBaselineDieselPricePerGal; }
        public BigDecimal getFscIndexDieselPricePerGal() { return fscIndexDieselPricePerGal; }
        public BigDecimal getFscRatePercentPerIncrement() { return fscRatePercentPerIncrement; }
        public BigDecimal getFscPriceIncrementStep() { return fscPriceIncrementStep; }
        public BigDecimal getAllowedDetentionFreeHours() { return allowedDetentionFreeHours; }
        public Money getDetentionHourlyRate() { return detentionHourlyRate; }
        public Map<AccessorialCode, Money> getAgreedAccessorialRates() { return Collections.unmodifiableMap(agreedAccessorialRates); }
        public BigDecimal getTolerancePercentage() { return tolerancePercentage; }
        public Money getToleranceAbsoluteThreshold() { return toleranceAbsoluteThreshold; }
    }

    public static final class AuditFinding {
        private final String lineId;
        private final AccessorialCode code;
        private final Money billedAmount;
        private final Money expectedContractAmount;
        private final Money varianceAmount;
        private final DiscrepancyClaimCode claimCode;
        private final String explanation;

        public AuditFinding(String lineId, AccessorialCode code, Money billedAmount, Money expectedContractAmount, Money varianceAmount, DiscrepancyClaimCode claimCode, String explanation) {
            this.lineId = lineId;
            this.code = code;
            this.billedAmount = billedAmount;
            this.expectedContractAmount = expectedContractAmount;
            this.varianceAmount = varianceAmount;
            this.claimCode = claimCode;
            this.explanation = explanation;
        }

        public String getLineId() { return lineId; }
        public AccessorialCode getCode() { return code; }
        public Money getBilledAmount() { return billedAmount; }
        public Money getExpectedContractAmount() { return expectedContractAmount; }
        public Money getVarianceAmount() { return varianceAmount; }
        public DiscrepancyClaimCode getClaimCode() { return claimCode; }
        public String getExplanation() { return explanation; }
    }

    public static final class FreightAuditVoucher {
        private final String voucherId;
        private final String invoiceNumber;
        private final VoucherStatus status;
        private final Money totalBilledAmount;
        private final Money expectedContractTotal;
        private final Money approvedPaymentAmount;
        private final Money disputedWithheldAmount;
        private final List<AuditFinding> findings;

        public FreightAuditVoucher(
                String voucherId,
                String invoiceNumber,
                VoucherStatus status,
                Money totalBilledAmount,
                Money expectedContractTotal,
                Money approvedPaymentAmount,
                Money disputedWithheldAmount,
                List<AuditFinding> findings) {
            this.voucherId = voucherId;
            this.invoiceNumber = invoiceNumber;
            this.status = status;
            this.totalBilledAmount = totalBilledAmount;
            this.expectedContractTotal = expectedContractTotal;
            this.approvedPaymentAmount = approvedPaymentAmount;
            this.disputedWithheldAmount = disputedWithheldAmount;
            this.findings = Collections.unmodifiableList(new ArrayList<>(findings));
        }

        public String getVoucherId() { return voucherId; }
        public String getInvoiceNumber() { return invoiceNumber; }
        public VoucherStatus getStatus() { return status; }
        public Money getTotalBilledAmount() { return totalBilledAmount; }
        public Money getExpectedContractTotal() { return expectedContractTotal; }
        public Money getApprovedPaymentAmount() { return approvedPaymentAmount; }
        public Money getDisputedWithheldAmount() { return disputedWithheldAmount; }
        public List<AuditFinding> getFindings() { return findings; }
    }

    /**
     * Executes automated freight invoice audit against contracted rates and actual logistics telemetry.
     */
    public FreightAuditVoucher auditInvoice(
            CarrierFreightInvoice invoice,
            AgreedFreightContract contract,
            BigDecimal actualFacilityDetentionHours) {

        Objects.requireNonNull(invoice, "invoice cannot be null");
        Objects.requireNonNull(contract, "contract cannot be null");

        String currency = invoice.getBilledTotal().getCurrency();
        List<AuditFinding> findings = new ArrayList<>();
        BigDecimal expectedTotalMajor = BigDecimal.ZERO;

        for (InvoiceLineItem item : invoice.getLineItems()) {
            Money expectedItemCost = calculateExpectedItemCost(item, contract, actualFacilityDetentionHours, currency);
            expectedTotalMajor = expectedTotalMajor.add(expectedItemCost.toMajorUnits());

            BigDecimal variance = item.getBilledAmount().toMajorUnits().subtract(expectedItemCost.toMajorUnits());
            if (variance.compareTo(BigDecimal.ZERO) > 0) {
                // Overbilled
                DiscrepancyClaimCode claimCode = mapClaimCode(item.getCode());
                findings.add(new AuditFinding(
                        item.getLineId(),
                        item.getCode(),
                        item.getBilledAmount(),
                        expectedItemCost,
                        Money.ofMajor(variance, currency),
                        claimCode,
                        String.format("Line %s billed %s exceeds contract benchmark %s by %s",
                                item.getLineId(), item.getBilledAmount(), expectedItemCost, variance)
                ));
            }
        }

        Money contractExpectedTotal = Money.ofMajor(expectedTotalMajor.setScale(2, RoundingMode.HALF_UP), currency);
        BigDecimal netVariance = invoice.getBilledTotal().toMajorUnits().subtract(contractExpectedTotal.toMajorUnits());

        // Tolerance Calculation: max(expectedTotal * tolerancePercentage, absoluteThreshold)
        BigDecimal percentTolerance = contractExpectedTotal.toMajorUnits().multiply(contract.getTolerancePercentage());
        BigDecimal maxAllowedTolerance = percentTolerance.max(contract.getToleranceAbsoluteThreshold().toMajorUnits());

        VoucherStatus status;
        Money approvedPayment;
        Money disputedWithheld;

        if (netVariance.compareTo(BigDecimal.ZERO) <= 0 || netVariance.compareTo(maxAllowedTolerance) <= 0) {
            // Within allowable contractual tolerance -> full auto-approval
            status = VoucherStatus.APPROVED_AUTO_PAY;
            approvedPayment = invoice.getBilledTotal();
            disputedWithheld = Money.zero(currency);
        } else {
            // Beyond tolerance -> approve contract undisputed amount, withhold disputed delta
            status = findings.isEmpty() ? VoucherStatus.APPROVED_AUTO_PAY : VoucherStatus.APPROVED_WITH_ADJUSTMENTS;
            approvedPayment = contractExpectedTotal;
            disputedWithheld = Money.ofMajor(netVariance.setScale(2, RoundingMode.HALF_UP), currency);
        }

        String voucherId = "VOUCHER-" + invoice.getInvoiceNumber() + "-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        return new FreightAuditVoucher(
                voucherId,
                invoice.getInvoiceNumber(),
                status,
                invoice.getBilledTotal(),
                contractExpectedTotal,
                approvedPayment,
                disputedWithheld,
                findings
        );
    }

    private Money calculateExpectedItemCost(
            InvoiceLineItem item,
            AgreedFreightContract contract,
            BigDecimal actualDetentionHours,
            String currency) {

        switch (item.getCode()) {
            case LINEHAUL_BASE:
                return contract.getBaseLinehaulRate();

            case FUEL_SURCHARGE:
                BigDecimal diff = contract.getFscIndexDieselPricePerGal().subtract(contract.getFscBaselineDieselPricePerGal());
                if (diff.compareTo(BigDecimal.ZERO) <= 0) {
                    return Money.zero(currency);
                }
                BigDecimal increments = diff.divide(contract.getFscPriceIncrementStep(), 0, RoundingMode.FLOOR);
                BigDecimal fscPercent = increments.multiply(contract.getFscRatePercentPerIncrement());
                BigDecimal fscAmount = contract.getBaseLinehaulRate().toMajorUnits().multiply(fscPercent);
                return Money.ofMajor(fscAmount.setScale(2, RoundingMode.HALF_UP), currency);

            case DETENTION_AT_SITE:
                BigDecimal actualHours = actualDetentionHours != null ? actualDetentionHours : BigDecimal.ZERO;
                BigDecimal billableHours = actualHours.subtract(contract.getAllowedDetentionFreeHours()).max(BigDecimal.ZERO);
                BigDecimal detentionAmount = billableHours.multiply(contract.getDetentionHourlyRate().toMajorUnits());
                return Money.ofMajor(detentionAmount.setScale(2, RoundingMode.HALF_UP), currency);

            default:
                Money contractedRate = contract.getAgreedAccessorialRates().get(item.getCode());
                if (contractedRate != null) {
                    BigDecimal total = contractedRate.toMajorUnits().multiply(item.getBilledUnits());
                    return Money.ofMajor(total.setScale(2, RoundingMode.HALF_UP), currency);
                }
                return Money.zero(currency);
        }
    }

    private DiscrepancyClaimCode mapClaimCode(AccessorialCode code) {
        switch (code) {
            case LINEHAUL_BASE:
                return DiscrepancyClaimCode.RATE_OVERBILLING;
            case FUEL_SURCHARGE:
                return DiscrepancyClaimCode.FUEL_SURCHARGE_MISCALCULATION;
            case DETENTION_AT_SITE:
                return DiscrepancyClaimCode.EXCESSIVE_DETENTION;
            case RE_WEIGH_RE_CLASS:
                return DiscrepancyClaimCode.WEIGHT_SURCHARGE_DISCREPANCY;
            default:
                return DiscrepancyClaimCode.UNAUTHORIZED_ACCESSORIAL;
        }
    }
}
