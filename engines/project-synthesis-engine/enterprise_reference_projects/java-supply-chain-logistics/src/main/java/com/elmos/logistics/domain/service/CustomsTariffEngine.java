package com.elmos.logistics.domain.service;

import com.elmos.logistics.domain.model.common.Money;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.*;

/**
 * Enterprise Customs Tariff &amp; Trade Compliance Engine.
 * Implements WCO Harmonized System (HS) classification, Ad Valorem/Specific/Compound duties,
 * Free Trade Agreement (FTA) Rules of Origin (RVC &amp; CTC tests), and Anti-Dumping surcharges.
 */
public class CustomsTariffEngine {

    public enum DutyType {
        AD_VALOREM,
        SPECIFIC,
        COMPOUND
    }

    public enum RuleOfOriginCriterion {
        WHOLLY_OBTAINED,
        REGIONAL_VALUE_CONTENT,
        CHANGE_IN_TARIFF_CLASSIFICATION,
        SPECIFIC_PROCESSING_OPERATION
    }

    public static final class TariffScheduleLine {
        private final String hsCode; // 6 to 10 digit string
        private final String description;
        private final DutyType dutyType;
        private final BigDecimal adValoremRatePercent; // e.g. 6.50%
        private final BigDecimal specificRateAmount;   // e.g. $0.15 per unit/kg
        private final String specificUnit;            // e.g. "KG", "ITEM", "LITER"
        private final BigDecimal vatGstRatePercent;    // e.g. 19.00%
        private final Map<String, BigDecimal> ftaPreferentialRates; // CountryCode -> Preferential %
        private final Map<String, BigDecimal> antiDumpingDutyRates; // CountryCode -> AD/CVD %

        public TariffScheduleLine(String hsCode, String description, DutyType dutyType,
                                  BigDecimal adValoremRatePercent, BigDecimal specificRateAmount,
                                  String specificUnit, BigDecimal vatGstRatePercent,
                                  Map<String, BigDecimal> ftaPreferentialRates,
                                  Map<String, BigDecimal> antiDumpingDutyRates) {
            this.hsCode = Objects.requireNonNull(hsCode, "hsCode").replaceAll("\\.", "").trim();
            this.description = Objects.requireNonNull(description, "description");
            this.dutyType = Objects.requireNonNull(dutyType, "dutyType");
            this.adValoremRatePercent = adValoremRatePercent != null ? adValoremRatePercent : BigDecimal.ZERO;
            this.specificRateAmount = specificRateAmount != null ? specificRateAmount : BigDecimal.ZERO;
            this.specificUnit = specificUnit != null ? specificUnit : "UNIT";
            this.vatGstRatePercent = vatGstRatePercent != null ? vatGstRatePercent : BigDecimal.ZERO;
            this.ftaPreferentialRates = ftaPreferentialRates != null ? new HashMap<>(ftaPreferentialRates) : Collections.emptyMap();
            this.antiDumpingDutyRates = antiDumpingDutyRates != null ? new HashMap<>(antiDumpingDutyRates) : Collections.emptyMap();
        }

        public String getHsCode() { return hsCode; }
        public String getDescription() { return description; }
        public DutyType getDutyType() { return dutyType; }
        public BigDecimal getAdValoremRatePercent() { return adValoremRatePercent; }
        public BigDecimal getSpecificRateAmount() { return specificRateAmount; }
        public String getSpecificUnit() { return specificUnit; }
        public BigDecimal getVatGstRatePercent() { return vatGstRatePercent; }
        public Map<String, BigDecimal> getFtaPreferentialRates() { return ftaPreferentialRates; }
        public Map<String, BigDecimal> getAntiDumpingDutyRates() { return antiDumpingDutyRates; }
    }

    public static final class DeclarationCommercialItem {
        private final String itemSku;
        private final String hsCode;
        private final String countryOfOrigin; // ISO 2-letter country code
        private final BigDecimal quantity;
        private final BigDecimal unitCustomsValueFob; // Free On Board customs value
        private final BigDecimal nonOriginatingMaterialValue; // VNM for RVC test
        private final String inputMaterialHsCode; // For CTC test

        public DeclarationCommercialItem(String itemSku, String hsCode, String countryOfOrigin,
                                         BigDecimal quantity, BigDecimal unitCustomsValueFob,
                                         BigDecimal nonOriginatingMaterialValue,
                                         String inputMaterialHsCode) {
            this.itemSku = Objects.requireNonNull(itemSku, "itemSku");
            this.hsCode = Objects.requireNonNull(hsCode, "hsCode").replaceAll("\\.", "").trim();
            this.countryOfOrigin = Objects.requireNonNull(countryOfOrigin, "countryOfOrigin").toUpperCase();
            this.quantity = Objects.requireNonNull(quantity, "quantity");
            this.unitCustomsValueFob = Objects.requireNonNull(unitCustomsValueFob, "unitCustomsValueFob");
            this.nonOriginatingMaterialValue = nonOriginatingMaterialValue != null ? nonOriginatingMaterialValue : BigDecimal.ZERO;
            this.inputMaterialHsCode = inputMaterialHsCode != null ? inputMaterialHsCode.replaceAll("\\.", "").trim() : "";
        }

        public String getItemSku() { return itemSku; }
        public String getHsCode() { return hsCode; }
        public String getCountryOfOrigin() { return countryOfOrigin; }
        public BigDecimal getQuantity() { return quantity; }
        public BigDecimal getUnitCustomsValueFob() { return unitCustomsValueFob; }
        public BigDecimal getNonOriginatingMaterialValue() { return nonOriginatingMaterialValue; }
        public String getInputMaterialHsCode() { return inputMaterialHsCode; }

        public BigDecimal getTotalFobValue() {
            return unitCustomsValueFob.multiply(quantity).setScale(2, RoundingMode.HALF_UP);
        }
    }

    public static final class DutyItemCalculation {
        private final DeclarationCommercialItem item;
        private final String appliedHsCode;
        private final BigDecimal customsValueCif; // CIF = FOB + Freight + Insurance
        private final BigDecimal basicCustomsDuty;
        private final BigDecimal antiDumpingDuty;
        private final BigDecimal vatGstAmount;
        private final BigDecimal totalImportTaxes;
        private final boolean preferentialRateApplied;
        private final String ruleOfOriginCertificateStatus;

        public DutyItemCalculation(DeclarationCommercialItem item, String appliedHsCode,
                                  BigDecimal customsValueCif, BigDecimal basicCustomsDuty,
                                  BigDecimal antiDumpingDuty, BigDecimal vatGstAmount,
                                  BigDecimal totalImportTaxes, boolean preferentialRateApplied,
                                  String ruleOfOriginCertificateStatus) {
            this.item = item;
            this.appliedHsCode = appliedHsCode;
            this.customsValueCif = customsValueCif;
            this.basicCustomsDuty = basicCustomsDuty;
            this.antiDumpingDuty = antiDumpingDuty;
            this.vatGstAmount = vatGstAmount;
            this.totalImportTaxes = totalImportTaxes;
            this.preferentialRateApplied = preferentialRateApplied;
            this.ruleOfOriginCertificateStatus = ruleOfOriginCertificateStatus;
        }

        public DeclarationCommercialItem getItem() { return item; }
        public String getAppliedHsCode() { return appliedHsCode; }
        public BigDecimal getCustomsValueCif() { return customsValueCif; }
        public BigDecimal getBasicCustomsDuty() { return basicCustomsDuty; }
        public BigDecimal getAntiDumpingDuty() { return antiDumpingDuty; }
        public BigDecimal getVatGstAmount() { return vatGstAmount; }
        public BigDecimal getTotalImportTaxes() { return totalImportTaxes; }
        public boolean isPreferentialRateApplied() { return preferentialRateApplied; }
        public String getRuleOfOriginCertificateStatus() { return ruleOfOriginCertificateStatus; }
    }

    public static final class CustomsClearanceDossier {
        private final String declarationId;
        private final String destinationCountry;
        private final List<DutyItemCalculation> itemCalculations;
        private final BigDecimal totalCifValue;
        private final BigDecimal totalBasicDuty;
        private final BigDecimal totalAntiDumpingDuty;
        private final BigDecimal totalVatGst;
        private final BigDecimal grandTotalTaxesAndDuties;
        private final boolean deMinimisExemptionApplied;
        private final List<String> complianceAuditNotes;

        public CustomsClearanceDossier(String declarationId, String destinationCountry,
                                       List<DutyItemCalculation> itemCalculations,
                                       BigDecimal totalCifValue, BigDecimal totalBasicDuty,
                                       BigDecimal totalAntiDumpingDuty, BigDecimal totalVatGst,
                                       BigDecimal grandTotalTaxesAndDuties, boolean deMinimisExemptionApplied,
                                       List<String> complianceAuditNotes) {
            this.declarationId = declarationId;
            this.destinationCountry = destinationCountry;
            this.itemCalculations = Collections.unmodifiableList(itemCalculations);
            this.totalCifValue = totalCifValue;
            this.totalBasicDuty = totalBasicDuty;
            this.totalAntiDumpingDuty = totalAntiDumpingDuty;
            this.totalVatGst = totalVatGst;
            this.grandTotalTaxesAndDuties = grandTotalTaxesAndDuties;
            this.deMinimisExemptionApplied = deMinimisExemptionApplied;
            this.complianceAuditNotes = Collections.unmodifiableList(complianceAuditNotes);
        }

        public String getDeclarationId() { return declarationId; }
        public String getDestinationCountry() { return destinationCountry; }
        public List<DutyItemCalculation> getItemCalculations() { return itemCalculations; }
        public BigDecimal getTotalCifValue() { return totalCifValue; }
        public BigDecimal getTotalBasicDuty() { return totalBasicDuty; }
        public BigDecimal getTotalAntiDumpingDuty() { return totalAntiDumpingDuty; }
        public BigDecimal getTotalVatGst() { return totalVatGst; }
        public BigDecimal getGrandTotalTaxesAndDuties() { return grandTotalTaxesAndDuties; }
        public boolean isDeMinimisExemptionApplied() { return deMinimisExemptionApplied; }
        public List<String> getComplianceAuditNotes() { return complianceAuditNotes; }
    }

    private final Map<String, TariffScheduleLine> tariffSchedule = new HashMap<>();

    public void registerTariffLine(TariffScheduleLine line) {
        Objects.requireNonNull(line, "line");
        tariffSchedule.put(line.getHsCode(), line);
    }

    /**
     * Resolves the most specific matching tariff line using HS prefix tree logic.
     */
    public Optional<TariffScheduleLine> resolveTariffLine(String hsCode) {
        String clean = hsCode.replaceAll("\\.", "").trim();
        // Exact match
        if (tariffSchedule.containsKey(clean)) {
            return Optional.of(tariffSchedule.get(clean));
        }
        // Subheading fallback (first 6 digits)
        if (clean.length() >= 6) {
            String sub6 = clean.substring(0, 6);
            if (tariffSchedule.containsKey(sub6)) {
                return Optional.of(tariffSchedule.get(sub6));
            }
        }
        // Heading fallback (first 4 digits)
        if (clean.length() >= 4) {
            String head4 = clean.substring(0, 4);
            if (tariffSchedule.containsKey(head4)) {
                return Optional.of(tariffSchedule.get(head4));
            }
        }
        return Optional.empty();
    }

    /**
     * Computes Free Trade Agreement (FTA) Regional Value Content (RVC).
     * RVC = ((TV - VNM) / TV) * 100%
     */
    public BigDecimal calculateRvcPercent(BigDecimal transactionValueFob, BigDecimal valueNonOriginating) {
        if (transactionValueFob == null || transactionValueFob.compareTo(BigDecimal.ZERO) <= 0) {
            return BigDecimal.ZERO;
        }
        BigDecimal vnm = valueNonOriginating != null ? valueNonOriginating : BigDecimal.ZERO;
        BigDecimal originatingVal = transactionValueFob.subtract(vnm);
        if (originatingVal.compareTo(BigDecimal.ZERO) <= 0) {
            return BigDecimal.ZERO;
        }
        return originatingVal.divide(transactionValueFob, 4, RoundingMode.HALF_UP)
                .multiply(BigDecimal.valueOf(100))
                .setScale(2, RoundingMode.HALF_UP);
    }

    /**
     * Evaluates Change in Tariff Classification (CTC) rule.
     * CTH: Change in 4-digit heading between input material and finished product.
     */
    public boolean checkChangeInTariffHeading(String inputHs, String outputHs) {
        if (inputHs == null || outputHs == null || inputHs.length() < 4 || outputHs.length() < 4) {
            return false;
        }
        String inHeading = inputHs.substring(0, 4);
        String outHeading = outputHs.substring(0, 4);
        return !inHeading.equalsIgnoreCase(outHeading);
    }

    /**
     * Executes customs taxation and duty calculation for a full commercial shipment.
     */
    public CustomsClearanceDossier computeCustomsClearance(String declarationId,
                                                          String destinationCountry,
                                                          List<DeclarationCommercialItem> items,
                                                          BigDecimal totalFreightUsd,
                                                          BigDecimal totalInsuranceUsd,
                                                          BigDecimal destinationDeMinimisThresholdUsd) {
        Objects.requireNonNull(declarationId, "declarationId");
        Objects.requireNonNull(destinationCountry, "destinationCountry");
        Objects.requireNonNull(items, "items");

        List<String> auditNotes = new ArrayList<>();
        BigDecimal totalFob = BigDecimal.ZERO;
        for (DeclarationCommercialItem it : items) {
            totalFob = totalFob.add(it.getTotalFobValue());
        }

        BigDecimal freight = totalFreightUsd != null ? totalFreightUsd : BigDecimal.ZERO;
        BigDecimal insurance = totalInsuranceUsd != null ? totalInsuranceUsd : BigDecimal.ZERO;
        BigDecimal totalCif = totalFob.add(freight).add(insurance).setScale(2, RoundingMode.HALF_UP);

        // De Minimis check (e.g. US Section 321 threshold $800, EU €150)
        boolean deMinimisEligible = destinationDeMinimisThresholdUsd != null
                && totalCif.compareTo(destinationDeMinimisThresholdUsd) <= 0;

        if (deMinimisEligible) {
            auditNotes.add(String.format("Shipment CIF value $%.2f is below de minimis threshold $%.2f; duty-free clearance applied.",
                    totalCif, destinationDeMinimisThresholdUsd));
        }

        List<DutyItemCalculation> calculations = new ArrayList<>();
        BigDecimal sumBasicDuty = BigDecimal.ZERO;
        BigDecimal sumAntiDumping = BigDecimal.ZERO;
        BigDecimal sumVatGst = BigDecimal.ZERO;

        for (DeclarationCommercialItem item : items) {
            // Allocate proportional CIF to item based on FOB weight
            BigDecimal itemFob = item.getTotalFobValue();
            BigDecimal cifProportion = totalFob.compareTo(BigDecimal.ZERO) > 0
                    ? itemFob.divide(totalFob, 6, RoundingMode.HALF_UP)
                    : BigDecimal.ZERO;
            BigDecimal itemCif = totalCif.multiply(cifProportion).setScale(2, RoundingMode.HALF_UP);

            if (deMinimisEligible) {
                calculations.add(new DutyItemCalculation(item, item.getHsCode(), itemCif,
                        BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
                        false, "DE_MINIMIS_EXEMPTION"));
                continue;
            }

            Optional<TariffScheduleLine> optLine = resolveTariffLine(item.getHsCode());
            if (optLine.isEmpty()) {
                auditNotes.add("Warning: No tariff line matched for HS " + item.getHsCode() + "; default 10% rate assumed.");
            }

            TariffScheduleLine tariff = optLine.orElseGet(() -> new TariffScheduleLine(
                    item.getHsCode(), "Unclassified Goods", DutyType.AD_VALOREM,
                    BigDecimal.valueOf(10.0), BigDecimal.ZERO, "UNIT",
                    BigDecimal.valueOf(13.0), null, null));

            // Origin Rule & FTA Preference Check
            boolean preferential = false;
            BigDecimal dutyRate = tariff.getAdValoremRatePercent();
            String originStatus = "NON_PREFERENTIAL_STANDARD";

            if (tariff.getFtaPreferentialRates().containsKey(item.getCountryOfOrigin())) {
                BigDecimal prefRate = tariff.getFtaPreferentialRates().get(item.getCountryOfOrigin());
                // Test RVC: requires >= 40%
                BigDecimal rvc = calculateRvcPercent(item.getTotalFobValue(), item.getNonOriginatingMaterialValue());
                boolean ctcPass = checkChangeInTariffHeading(item.getInputMaterialHsCode(), item.getHsCode());

                if (rvc.compareTo(BigDecimal.valueOf(40.0)) >= 0 || ctcPass) {
                    dutyRate = prefRate;
                    preferential = true;
                    originStatus = String.format("FTA_QUALIFIED(RVC:%.1f%%, CTC:%b)", rvc, ctcPass);
                } else {
                    originStatus = String.format("FTA_DISQUALIFIED(RVC:%.1f%% < 40%%)", rvc);
                }
            }

            // Duty Calculation
            BigDecimal itemDuty = BigDecimal.ZERO;
            switch (tariff.getDutyType()) {
                case AD_VALOREM:
                    itemDuty = itemCif.multiply(dutyRate).divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);
                    break;
                case SPECIFIC:
                    itemDuty = item.getQuantity().multiply(tariff.getSpecificRateAmount()).setScale(2, RoundingMode.HALF_UP);
                    break;
                case COMPOUND:
                    BigDecimal adv = itemCif.multiply(dutyRate).divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);
                    BigDecimal spc = item.getQuantity().multiply(tariff.getSpecificRateAmount()).setScale(2, RoundingMode.HALF_UP);
                    itemDuty = adv.add(spc);
                    break;
            }

            // Anti-dumping surcharge check
            BigDecimal adDuty = BigDecimal.ZERO;
            if (tariff.getAntiDumpingDutyRates().containsKey(item.getCountryOfOrigin())) {
                BigDecimal adRate = tariff.getAntiDumpingDutyRates().get(item.getCountryOfOrigin());
                adDuty = itemCif.multiply(adRate).divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);
                auditNotes.add(String.format("AD/CVD duty imposed on %s origin goods: %.1f%% ($%.2f)",
                        item.getCountryOfOrigin(), adRate, adDuty));
            }

            // VAT/GST Tax Base = CIF + Customs Duty + Anti-Dumping Duty
            BigDecimal taxBase = itemCif.add(itemDuty).add(adDuty);
            BigDecimal itemVat = taxBase.multiply(tariff.getVatGstRatePercent())
                    .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);

            BigDecimal totalItemTaxes = itemDuty.add(adDuty).add(itemVat);

            sumBasicDuty = sumBasicDuty.add(itemDuty);
            sumAntiDumping = sumAntiDumping.add(adDuty);
            sumVatGst = sumVatGst.add(itemVat);

            calculations.add(new DutyItemCalculation(item, tariff.getHsCode(), itemCif,
                    itemDuty, adDuty, itemVat, totalItemTaxes, preferential, originStatus));
        }

        BigDecimal grandTotal = sumBasicDuty.add(sumAntiDumping).add(sumVatGst);

        return new CustomsClearanceDossier(declarationId, destinationCountry, calculations,
                totalCif, sumBasicDuty, sumAntiDumping, sumVatGst, grandTotal,
                deMinimisEligible, auditNotes);
    }
}
