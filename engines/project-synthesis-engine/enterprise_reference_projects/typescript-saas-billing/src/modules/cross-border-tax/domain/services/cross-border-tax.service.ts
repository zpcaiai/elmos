import { Injectable, BadRequestException } from '@nestjs/common';
import {
  CrossBorderTaxCalculationRequest,
  CrossBorderTaxCalculationResponse,
  TaxCalculationLine,
  TaxAuthorityType,
} from '../entities/cross-border-tax.entity';

@Injectable()
export class CrossBorderTaxService {
  /**
   * Validates Australian Business Number (ABN) using the statutory ATO Modulo-89 algorithm.
   */
  public validateABN(abn: string): boolean {
    const clean = abn.replace(/\s+/g, '');
    if (!/^\d{11}$/.test(clean)) {
      return false;
    }

    const weights = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19];
    const digits = clean.split('').map(Number);

    // Subtract 1 from the first digit
    digits[0] -= 1;

    let sum = 0;
    for (let i = 0; i < 11; i++) {
      sum += digits[i] * weights[i];
    }

    return sum % 89 === 0;
  }

  /**
   * Validates Indian Goods and Services Tax Identification Number (GSTIN) syntax.
   */
  public validateGSTIN(gstin: string): boolean {
    const clean = gstin.trim().toUpperCase();
    const gstinRegex = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
    if (!gstinRegex.test(clean)) {
      return false;
    }

    const stateCode = parseInt(clean.substring(0, 2), 10);
    return stateCode >= 1 && stateCode <= 38;
  }

  /**
   * Computes cross-border indirect taxes with exact multi-jurisdiction rate schedules.
   */
  public calculateCrossBorderTax(
    req: CrossBorderTaxCalculationRequest
  ): CrossBorderTaxCalculationResponse {
    if (req.amountCents < 0) {
      throw new BadRequestException('Transaction amount cannot be negative');
    }

    const country = req.countryCode.toUpperCase();
    const subdivision = (req.subdivisionCode ?? '').toUpperCase();
    const lines: TaxCalculationLine[] = [];
    let reverseChargeApplied = false;
    let reverseChargeNote: string | undefined;
    let customerTaxIdValid = false;

    switch (country) {
      case 'CA': // Canada
        this.computeCanadaTax(req, subdivision, lines);
        break;

      case 'AU': // Australia
        if (req.isBusinessCustomer && req.taxRegistrationNumber) {
          customerTaxIdValid = this.validateABN(req.taxRegistrationNumber);
          if (customerTaxIdValid) {
            reverseChargeApplied = true;
            reverseChargeNote = 'Subject to reverse charge under GST Act 1999 s 84-5 (B2B recipient self-assesses).';
          } else {
            this.addSingleTaxLine(lines, TaxAuthorityType.AUSTRALIA_ATO_GST, 'AU', 10.0, req.amountCents, 'Australian GST (10%)');
          }
        } else {
          this.addSingleTaxLine(lines, TaxAuthorityType.AUSTRALIA_ATO_GST, 'AU', 10.0, req.amountCents, 'Australian GST (10%)');
        }
        break;

      case 'IN': // India
        if (req.isBusinessCustomer && req.taxRegistrationNumber) {
          customerTaxIdValid = this.validateGSTIN(req.taxRegistrationNumber);
          if (customerTaxIdValid) {
            reverseChargeApplied = true;
            reverseChargeNote = 'Recipient liable to pay tax under Reverse Charge Mechanism (Section 5(3) IGST Act 2017).';
          } else {
            this.addSingleTaxLine(lines, TaxAuthorityType.INDIA_GST_IGST, 'IN', 18.0, req.amountCents, 'Integrated GST - OIDAR SAC 9984 (18%)');
          }
        } else {
          this.addSingleTaxLine(lines, TaxAuthorityType.INDIA_GST_IGST, 'IN', 18.0, req.amountCents, 'Integrated GST - OIDAR SAC 9984 (18%)');
        }
        break;

      case 'GB': // United Kingdom
        if (req.isBusinessCustomer && req.taxRegistrationNumber) {
          customerTaxIdValid = /^GB\d{9}$/.test(req.taxRegistrationNumber.trim().toUpperCase());
          if (customerTaxIdValid) {
            reverseChargeApplied = true;
            reverseChargeNote = 'Reverse charge applies under Section 8 VATA 1994.';
          } else {
            this.addSingleTaxLine(lines, TaxAuthorityType.UK_HMRC_VAT, 'GB', 20.0, req.amountCents, 'UK Standard VAT (20%)');
          }
        } else {
          this.addSingleTaxLine(lines, TaxAuthorityType.UK_HMRC_VAT, 'GB', 20.0, req.amountCents, 'UK Standard VAT (20%)');
        }
        break;

      case 'SG': // Singapore
        this.addSingleTaxLine(lines, TaxAuthorityType.SINGAPORE_IRAS_GST, 'SG', 9.0, req.amountCents, 'Singapore Overseas Vendor GST (9%)');
        break;

      default:
        // Other regions outside designated cross-border matrix
        break;
    }

    const totalTaxCents = lines.reduce((sum, l) => sum + l.taxCollectedCents, 0);

    return {
      countryCode: country,
      subdivisionCode: subdivision || undefined,
      currency: req.currency,
      subtotalCents: req.amountCents,
      totalTaxCents,
      grandTotalCents: req.amountCents + totalTaxCents,
      lines,
      reverseChargeApplied,
      reverseChargeNote,
      customerTaxIdValid,
    };
  }

  private computeCanadaTax(
    req: CrossBorderTaxCalculationRequest,
    prov: string,
    lines: TaxCalculationLine[]
  ): void {
    const amount = req.amountCents;

    switch (prov) {
      case 'ON': // Ontario HST 13%
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_CRA_GST, 'CA-ON', 13.0, amount, 'Ontario Harmonized Sales Tax (HST 13%)');
        break;

      case 'QC': // Quebec: Federal GST 5% + Revenu Québec QST 9.975%
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_CRA_GST, 'CA-QC', 5.0, amount, 'Canada Federal GST (5%)');
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_REVENU_QUEBEC_QST, 'CA-QC', 9.975, amount, 'Revenu Québec Sales Tax (QST 9.975%)');
        break;

      case 'BC': // British Columbia: Federal GST 5% + Provincial PST 7%
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_CRA_GST, 'CA-BC', 5.0, amount, 'Canada Federal GST (5%)');
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_PROVINCIAL_PST, 'CA-BC', 7.0, amount, 'British Columbia Provincial Sales Tax (PST 7%)');
        break;

      case 'NS': // Nova Scotia HST 15%
      case 'NB': // New Brunswick HST 15%
      case 'NL': // Newfoundland & Labrador HST 15%
      case 'PE': // Prince Edward Island HST 15%
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_CRA_GST, `CA-${prov}`, 15.0, amount, `${prov} Harmonized Sales Tax (HST 15%)`);
        break;

      case 'SK': // Saskatchewan: GST 5% + PST 6%
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_CRA_GST, 'CA-SK', 5.0, amount, 'Canada Federal GST (5%)');
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_PROVINCIAL_PST, 'CA-SK', 6.0, amount, 'Saskatchewan Provincial Sales Tax (PST 6%)');
        break;

      case 'MB': // Manitoba: GST 5% + RST 7%
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_CRA_GST, 'CA-MB', 5.0, amount, 'Canada Federal GST (5%)');
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_PROVINCIAL_PST, 'CA-MB', 7.0, amount, 'Manitoba Retail Sales Tax (RST 7%)');
        break;

      default:
        // Alberta, Territories, or unstated province: Default 5% Federal GST
        this.addSingleTaxLine(lines, TaxAuthorityType.CANADA_CRA_GST, 'CA-FED', 5.0, amount, 'Canada Federal GST (5%)');
        break;
    }
  }

  private addSingleTaxLine(
    lines: TaxCalculationLine[],
    authority: TaxAuthorityType,
    jurisdictionCode: string,
    ratePercentage: number,
    amountCents: number,
    description: string
  ): void {
    const taxCents = Math.round((amountCents * ratePercentage) / 100.0);
    lines.push({
      taxAuthority: authority,
      jurisdictionCode,
      taxRatePercentage: ratePercentage,
      taxableAmountCents: amountCents,
      taxCollectedCents: taxCents,
      statutoryDescription: description,
    });
  }
}
