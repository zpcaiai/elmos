import { CrossBorderTaxService } from '../src/modules/cross-border-tax/domain/services/cross-border-tax.service';
import {
  TaxAuthorityType,
  CrossBorderTaxCalculationRequest,
} from '../src/modules/cross-border-tax/domain/entities/cross-border-tax.entity';

describe('Cross-Border Indirect Tax Engine', () => {
  let taxService: CrossBorderTaxService;

  beforeEach(() => {
    taxService = new CrossBorderTaxService();
  });

  it('should validate Australian Business Number (ABN) with statutory Modulo-89 algorithm', () => {
    // Australian Taxation Office valid ABN: 51 824 753 556
    expect(taxService.validateABN('51 824 753 556')).toBe(true);
    expect(taxService.validateABN('51824753556')).toBe(true);

    // Corrupted ABNs
    expect(taxService.validateABN('51 824 753 557')).toBe(false);
    expect(taxService.validateABN('12345678901')).toBe(false);
    expect(taxService.validateABN('12345')).toBe(false);
  });

  it('should apply B2B reverse charge on Australian digital services when valid ABN provided', () => {
    const req: CrossBorderTaxCalculationRequest = {
      countryCode: 'AU',
      isBusinessCustomer: true,
      taxRegistrationNumber: '51 824 753 556',
      amountCents: 100000, // $1,000.00 AUD
      currency: 'AUD',
    };

    const res = taxService.calculateCrossBorderTax(req);

    expect(res.customerTaxIdValid).toBe(true);
    expect(res.reverseChargeApplied).toBe(true);
    expect(res.totalTaxCents).toBe(0);
    expect(res.grandTotalCents).toBe(100000);
    expect(res.lines).toHaveLength(0);
    expect(res.reverseChargeNote).toContain('s 84-5');
  });

  it('should collect 10% GST on Australian B2C transactions', () => {
    const req: CrossBorderTaxCalculationRequest = {
      countryCode: 'AU',
      isBusinessCustomer: false,
      amountCents: 100000, // $1,000.00 AUD
      currency: 'AUD',
    };

    const res = taxService.calculateCrossBorderTax(req);

    expect(res.reverseChargeApplied).toBe(false);
    expect(res.totalTaxCents).toBe(10000); // $100.00 AUD
    expect(res.grandTotalCents).toBe(110000); // $1,100.00 AUD
    expect(res.lines).toHaveLength(1);
    expect(res.lines[0].taxAuthority).toBe(TaxAuthorityType.AUSTRALIA_ATO_GST);
    expect(res.lines[0].taxRatePercentage).toBe(10.0);
  });

  it('should correctly calculate Ontario HST (13%) in Canada', () => {
    const req: CrossBorderTaxCalculationRequest = {
      countryCode: 'CA',
      subdivisionCode: 'ON',
      isBusinessCustomer: false,
      amountCents: 10000, // $100.00 CAD
      currency: 'CAD',
    };

    const res = taxService.calculateCrossBorderTax(req);

    expect(res.totalTaxCents).toBe(1300); // $13.00 HST
    expect(res.grandTotalCents).toBe(11300);
    expect(res.lines).toHaveLength(1);
    expect(res.lines[0].jurisdictionCode).toBe('CA-ON');
    expect(res.lines[0].taxRatePercentage).toBe(13.0);
  });

  it('should compute dual GST (5%) and QST (9.975%) for Quebec customers', () => {
    const req: CrossBorderTaxCalculationRequest = {
      countryCode: 'CA',
      subdivisionCode: 'QC',
      isBusinessCustomer: false,
      amountCents: 10000, // $100.00 CAD
      currency: 'CAD',
    };

    const res = taxService.calculateCrossBorderTax(req);

    // GST 5% = $5.00 (500 cents)
    // QST 9.975% = $9.98 (998 cents, rounded to nearest cent)
    // Total Tax = $14.98 (1498 cents)
    expect(res.lines).toHaveLength(2);
    expect(res.lines[0].taxAuthority).toBe(TaxAuthorityType.CANADA_CRA_GST);
    expect(res.lines[0].taxCollectedCents).toBe(500);

    expect(res.lines[1].taxAuthority).toBe(TaxAuthorityType.CANADA_REVENU_QUEBEC_QST);
    expect(res.lines[1].taxCollectedCents).toBe(998);

    expect(res.totalTaxCents).toBe(1498);
    expect(res.grandTotalCents).toBe(11498);
  });

  it('should evaluate Indian GSTIN format and apply cross-border OIDAR 18% IGST', () => {
    // Valid Karnataka GSTIN: 29AAAAA0000A1Z5
    expect(taxService.validateGSTIN('29AAAAA0000A1Z5')).toBe(true);
    // Invalid state code 00
    expect(taxService.validateGSTIN('00AAAAA0000A1Z5')).toBe(false);

    // B2C Indian consumer -> 18% IGST under OIDAR
    const reqB2C: CrossBorderTaxCalculationRequest = {
      countryCode: 'IN',
      isBusinessCustomer: false,
      amountCents: 100000, // ₹1,000.00
      currency: 'INR',
    };

    const resB2C = taxService.calculateCrossBorderTax(reqB2C);
    expect(resB2C.reverseChargeApplied).toBe(false);
    expect(resB2C.totalTaxCents).toBe(18000); // 18% = ₹180.00
    expect(resB2C.grandTotalCents).toBe(118000);

    // B2B Indian business with GSTIN -> Reverse charge
    const reqB2B: CrossBorderTaxCalculationRequest = {
      countryCode: 'IN',
      isBusinessCustomer: true,
      taxRegistrationNumber: '29AAAAA0000A1Z5',
      amountCents: 100000,
      currency: 'INR',
    };

    const resB2B = taxService.calculateCrossBorderTax(reqB2B);
    expect(resB2B.customerTaxIdValid).toBe(true);
    expect(resB2B.reverseChargeApplied).toBe(true);
    expect(resB2B.totalTaxCents).toBe(0);
    expect(resB2B.reverseChargeNote).toContain('Section 5(3) IGST Act');
  });
});
