/**
 * Global Tax Engine Unit & Integration Tests
 */

import { TaxEngineService } from '../src/modules/tax/domain/services/tax-engine.service';
import { TaxNexusEvaluatorService } from '../src/modules/tax/domain/services/tax-nexus-evaluator.service';
import { ExemptionType, CertificateStatus } from '../src/modules/tax/domain/entities/tax-exemption.entity';

describe('Global Tax Engine', () => {
  let nexusEvaluator: TaxNexusEvaluatorService;
  let taxEngine: TaxEngineService;

  beforeEach(() => {
    nexusEvaluator = new TaxNexusEvaluatorService();
    taxEngine = new TaxEngineService(nexusEvaluator);
  });

  it('should evaluate US state economic nexus thresholds correctly', () => {
    // WA standard threshold is $100k
    const waResultUnder = nexusEvaluator.evaluateStateNexus({
      stateCode: 'WA',
      grossSales12M: 85000,
      transactionCount12M: 50,
    });
    expect(waResultUnder.hasNexus).toBe(false);

    const waResultOver = nexusEvaluator.evaluateStateNexus({
      stateCode: 'WA',
      grossSales12M: 120000,
      transactionCount12M: 50,
    });
    expect(waResultOver.hasNexus).toBe(true);
    expect(waResultOver.nexusReason).toBe('ECONOMIC_REVENUE');
    expect(waResultOver.mustCollectTaxOnSaaS).toBe(true);
  });

  it('should calculate destination-based US state sales tax when nexus is active', () => {
    const calc = taxEngine.calculateTax({
      transactionId: 'tx-us-001',
      customerId: 'cust-ny-1',
      customerAddress: {
        line1: '350 5th Ave',
        city: 'New York',
        stateProvince: 'NY',
        postalCode: '10118',
        countryCode: 'US',
      },
      items: [
        {
          itemId: 'item-saas-sub',
          sku: 'SAAS-PRO-MONTHLY',
          description: 'SaaS Pro Monthly Subscription',
          amount: 100,
          quantity: 2,
          isDigitalGood: true,
          isService: true,
        },
      ],
    });

    expect(calc.totalTaxableAmount).toBe(200);
    expect(calc.totalTaxAmount).toBe(8); // NY State 4% of $200 = $8
    expect(calc.isReverseChargeApplied).toBe(false);
  });

  it('should apply EU VAT reverse charge for verified B2B customers', () => {
    const calc = taxEngine.calculateTax({
      transactionId: 'tx-eu-001',
      customerId: 'cust-bmw-de',
      customerVatNumber: 'DE123456789', // Valid German VAT ID format
      customerAddress: {
        line1: 'Petuelring 130',
        city: 'Munich',
        stateProvince: 'BY',
        postalCode: '80788',
        countryCode: 'DE',
      },
      items: [
        {
          itemId: 'item-api-tier',
          sku: 'API-ENTERPRISE-ANNUAL',
          description: 'High-Volume Enterprise API Gateway',
          amount: 5000,
          quantity: 1,
          isDigitalGood: true,
          isService: true,
        },
      ],
    });

    expect(calc.totalTaxableAmount).toBe(0);
    expect(calc.totalExemptAmount).toBe(5000);
    expect(calc.totalTaxAmount).toBe(0);
    expect(calc.isReverseChargeApplied).toBe(true);
    expect(calc.reverseChargeNote).toBeDefined();
  });

  it('should apply destination VAT under EU OSS for B2C consumer without VAT ID', () => {
    const calc = taxEngine.calculateTax({
      transactionId: 'tx-eu-b2c-001',
      customerId: 'cust-consumer-fr',
      customerAddress: {
        line1: '10 Rue de la Paix',
        city: 'Paris',
        stateProvince: 'IDF',
        postalCode: '75002',
        countryCode: 'FR',
      },
      items: [
        {
          itemId: 'item-single-sub',
          sku: 'SAAS-STARTER',
          description: 'Cloud Starter Seat',
          amount: 50,
          quantity: 1,
          isDigitalGood: true,
          isService: true,
        },
      ],
    });

    expect(calc.totalTaxableAmount).toBe(50);
    expect(calc.totalTaxAmount).toBe(10); // France VAT 20% of 50 = $10
    expect(calc.isReverseChargeApplied).toBe(false);
  });

  it('should honor valid wholesale resale exemption certificates', () => {
    const cert = {
      certificateId: 'cert-resale-999',
      customerId: 'cust-reseller-1',
      jurisdictionCode: 'US-NY',
      exemptionType: ExemptionType.WHOLESALE_RESALE,
      certificateNumber: 'RESALE-NY-2026',
      issuingState: 'NY',
      validFrom: new Date('2025-01-01'),
      validTo: new Date('2027-01-01'),
      status: CertificateStatus.VALID,
    };

    const calc = taxEngine.calculateTax({
      transactionId: 'tx-exempt-001',
      customerId: 'cust-reseller-1',
      customerAddress: {
        line1: '100 Broadway',
        city: 'New York',
        stateProvince: 'NY',
        postalCode: '10005',
        countryCode: 'US',
      },
      items: [
        {
          itemId: 'item-resell-sub',
          sku: 'SAAS-RESELLER-PACK',
          description: 'Reseller Core Subscription',
          amount: 1000,
          quantity: 1,
          isDigitalGood: true,
          isService: true,
        },
      ],
      exemptionCertificates: [cert],
    });

    expect(calc.totalExemptAmount).toBe(1000);
    expect(calc.totalTaxAmount).toBe(0);
  });
});
