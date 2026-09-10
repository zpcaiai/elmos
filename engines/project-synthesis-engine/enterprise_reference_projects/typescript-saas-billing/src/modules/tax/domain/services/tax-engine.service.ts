/**
 * Global Tax Calculation Engine
 *
 * Implements end-to-end tax determination across US sales tax, EU VAT OSS,
 * UK VAT, Canadian GST/HST, and Australian GST.
 */

import { Injectable } from '@nestjs/common';
import { TaxJurisdiction, TaxType, JurisdictionLevel, SourcingRule } from '../entities/tax-jurisdiction.entity';
import { TaxExemptionCertificate, CertificateStatus, VatFormatValidator } from '../entities/tax-exemption.entity';
import { TaxNexusEvaluatorService } from './tax-nexus-evaluator.service';

export interface AddressDto {
  line1: string;
  city: string;
  stateProvince: string;
  postalCode: string;
  countryCode: string; // ISO-3166-1 alpha-2
}

export interface TaxableItemDto {
  itemId: string;
  sku: string;
  description: string;
  amount: number;
  quantity: number;
  isDigitalGood: boolean;
  isService: boolean;
  taxCode?: string;
}

export interface TaxCalculationRequest {
  transactionId: string;
  customerId: string;
  customerAddress: AddressDto;
  customerVatNumber?: string;
  sellerAddress?: AddressDto;
  items: TaxableItemDto[];
  exemptionCertificates?: TaxExemptionCertificate[];
  asOfDate?: Date;
}

export interface ItemTaxDetail {
  itemId: string;
  taxableAmount: number;
  exemptAmount: number;
  taxAmount: number;
  effectiveRate: number;
  appliedJurisdictions: Array<{
    jurisdictionCode: string;
    level: string;
    rate: number;
    amount: number;
  }>;
}

export interface TaxCalculationResult {
  transactionId: string;
  currency: string;
  totalTaxableAmount: number;
  totalExemptAmount: number;
  totalTaxAmount: number;
  isReverseChargeApplied: boolean;
  reverseChargeNote?: string;
  itemDetails: ItemTaxDetail[];
  jurisdictionSummary: Record<string, number>;
  calculatedAt: Date;
}

@Injectable()
export class TaxEngineService {
  private readonly jurisdictions: Map<string, TaxJurisdiction> = new Map();

  // European Union standard member state VAT rates (as of 2026)
  private readonly euVatRates: Record<string, number> = {
    DE: 0.19, // Germany
    FR: 0.20, // France
    IT: 0.22, // Italy
    ES: 0.21, // Spain
    NL: 0.21, // Netherlands
    BE: 0.21, // Belgium
    IE: 0.23, // Ireland
    SE: 0.25, // Sweden
    PL: 0.23, // Poland
    AT: 0.20, // Austria
    DK: 0.25, // Denmark
    FI: 0.255, // Finland
    PT: 0.23, // Portugal
  };

  // Canada combined GST/HST rates
  private readonly canadaRates: Record<string, { rate: number; name: string }> = {
    ON: { rate: 0.13, name: 'Ontario HST' },
    BC: { rate: 0.12, name: 'BC GST (5%) + PST (7%)' },
    QC: { rate: 0.14975, name: 'Quebec GST (5%) + QST (9.975%)' },
    AB: { rate: 0.05, name: 'Alberta GST' },
    NS: { rate: 0.15, name: 'Nova Scotia HST' },
  };

  constructor(private readonly nexusEvaluator: TaxNexusEvaluatorService) {
    this.seedDefaultJurisdictions();
  }

  private seedDefaultJurisdictions(): void {
    // US State default rates
    const usStates: Array<{ code: string; name: string; rate: number }> = [
      { code: 'US-NY', name: 'New York State', rate: 0.04 },
      { code: 'US-TX', name: 'Texas State', rate: 0.0625 },
      { code: 'US-WA', name: 'Washington State', rate: 0.065 },
      { code: 'US-IL', name: 'Illinois State', rate: 0.0625 },
      { code: 'US-PA', name: 'Pennsylvania State', rate: 0.06 },
    ];

    for (const st of usStates) {
      const jur = new TaxJurisdiction({
        id: `jur-${st.code.toLowerCase()}`,
        code: st.code,
        name: st.name,
        countryCode: 'US',
        level: JurisdictionLevel.STATE_PROVINCE,
        sourcingRule: SourcingRule.DESTINATION,
      });
      jur.addRule({
        ruleId: `rule-${st.code.toLowerCase()}-standard`,
        taxType: TaxType.SALES_TAX,
        ratePercentage: st.rate,
        appliesToDigitalGoods: true,
        appliesToServices: true,
        effectiveFrom: new Date('2020-01-01'),
      });
      this.jurisdictions.set(st.code, jur);
    }
  }

  /**
   * Calculates comprehensive taxes on transaction items
   */
  public calculateTax(request: TaxCalculationRequest): TaxCalculationResult {
    const country = request.customerAddress.countryCode.toUpperCase();
    const state = (request.customerAddress.stateProvince || '').toUpperCase();
    const asOf = request.asOfDate || new Date();

    let isReverseCharge = false;
    let reverseChargeNote: string | undefined = undefined;

    // 1. Check EU VAT Reverse Charge applicability
    const isEUCountry = country in this.euVatRates;
    if (isEUCountry && request.customerVatNumber) {
      const isValid = VatFormatValidator.validateEUVatFormat(country, request.customerVatNumber);
      if (isValid) {
        isReverseCharge = true;
        reverseChargeNote = `Reverse charge: VAT to be accounted for by the recipient under Art. 196 of Council Directive 2006/112/EC (VAT ID: ${request.customerVatNumber})`;
      }
    }

    // 2. Check Customer Exemption Certificates
    let hasExemption = false;
    if (request.exemptionCertificates && request.exemptionCertificates.length > 0) {
      const activeCert = request.exemptionCertificates.find(
        c => c.status === CertificateStatus.VALID && c.validFrom <= asOf && c.validTo >= asOf
      );
      if (activeCert) {
        hasExemption = true;
      }
    }

    const itemDetails: ItemTaxDetail[] = [];
    const jurSummary: Record<string, number> = {};
    let totalTaxable = 0;
    let totalExempt = 0;
    let totalTax = 0;

    for (const item of request.items) {
      const itemGross = Math.round(item.amount * item.quantity * 100) / 100;

      // If customer has a valid exemption certificate or reverse charge applies:
      if (hasExemption || isReverseCharge) {
        totalExempt += itemGross;
        itemDetails.push({
          itemId: item.itemId,
          taxableAmount: 0,
          exemptAmount: itemGross,
          taxAmount: 0,
          effectiveRate: 0,
          appliedJurisdictions: [],
        });
        continue;
      }

      // Determine applicable tax rate & jurisdictions
      let applicableRate = 0;
      const appliedJuris: Array<{ jurisdictionCode: string; level: string; rate: number; amount: number }> = [];

      if (country === 'US') {
        // Check economic nexus
        const nexus = this.nexusEvaluator.evaluateStateNexus({
          stateCode: state,
          grossSales12M: 600000, // By default reference assuming established merchant
          transactionCount12M: 250,
        });

        if (nexus.hasNexus && nexus.mustCollectTaxOnSaaS) {
          const jurKey = `US-${state}`;
          const jur = this.jurisdictions.get(jurKey);
          const stateRate = jur ? jur.getEffectiveRate({ taxType: TaxType.SALES_TAX, isDigital: item.isDigitalGood, isService: item.isService, asOfDate: asOf }) : 0.05; // default 5%
          applicableRate += stateRate;

          const taxAmt = Math.round(itemGross * stateRate * 100) / 100;
          appliedJuris.push({
            jurisdictionCode: jurKey,
            level: 'STATE_PROVINCE',
            rate: stateRate,
            amount: taxAmt,
          });
          jurSummary[jurKey] = Math.round(((jurSummary[jurKey] || 0) + taxAmt) * 100) / 100;
        }
      } else if (isEUCountry) {
        // EU B2C One-Stop Shop (OSS) Destination VAT
        const vatRate = this.euVatRates[country] || 0.20;
        applicableRate = vatRate;

        const taxAmt = Math.round(itemGross * vatRate * 100) / 100;
        const jurKey = `EU-${country}`;
        appliedJuris.push({
          jurisdictionCode: jurKey,
          level: 'COUNTRY_VAT',
          rate: vatRate,
          amount: taxAmt,
        });
        jurSummary[jurKey] = Math.round(((jurSummary[jurKey] || 0) + taxAmt) * 100) / 100;
      } else if (country === 'GB') {
        // UK Standard VAT (20%)
        const ukRate = 0.20;
        applicableRate = ukRate;
        const taxAmt = Math.round(itemGross * ukRate * 100) / 100;
        appliedJuris.push({
          jurisdictionCode: 'GB-HMRC',
          level: 'COUNTRY_VAT',
          rate: ukRate,
          amount: taxAmt,
        });
        jurSummary['GB-HMRC'] = Math.round(((jurSummary['GB-HMRC'] || 0) + taxAmt) * 100) / 100;
      } else if (country === 'CA') {
        // Canada GST/HST
        const caInfo = this.canadaRates[state] || { rate: 0.05, name: 'Canada GST' };
        applicableRate = caInfo.rate;
        const taxAmt = Math.round(itemGross * applicableRate * 100) / 100;
        const jurKey = `CA-${state || 'FED'}`;
        appliedJuris.push({
          jurisdictionCode: jurKey,
          level: 'PROVINCE_GST_HST',
          rate: applicableRate,
          amount: taxAmt,
        });
        jurSummary[jurKey] = Math.round(((jurSummary[jurKey] || 0) + taxAmt) * 100) / 100;
      } else if (country === 'AU') {
        // Australia GST (10%)
        const auRate = 0.10;
        applicableRate = auRate;
        const taxAmt = Math.round(itemGross * auRate * 100) / 100;
        appliedJuris.push({
          jurisdictionCode: 'AU-ATO',
          level: 'COUNTRY_GST',
          rate: auRate,
          amount: taxAmt,
        });
        jurSummary['AU-ATO'] = Math.round(((jurSummary['AU-ATO'] || 0) + taxAmt) * 100) / 100;
      }

      const itemTaxTotal = Math.round(itemGross * applicableRate * 100) / 100;
      totalTaxable += itemGross;
      totalTax += itemTaxTotal;

      itemDetails.push({
        itemId: item.itemId,
        taxableAmount: itemGross,
        exemptAmount: 0,
        taxAmount: itemTaxTotal,
        effectiveRate: applicableRate,
        appliedJurisdictions: appliedJuris,
      });
    }

    return {
      transactionId: request.transactionId,
      currency: 'USD',
      totalTaxableAmount: Math.round(totalTaxable * 100) / 100,
      totalExemptAmount: Math.round(totalExempt * 100) / 100,
      totalTaxAmount: Math.round(totalTax * 100) / 100,
      isReverseChargeApplied: isReverseCharge,
      reverseChargeNote,
      itemDetails,
      jurisdictionSummary: jurSummary,
      calculatedAt: new Date(),
    };
  }
}
