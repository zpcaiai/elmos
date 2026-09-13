/**
 * Tax Exemption Certificate & B2B VAT Identification Entities
 */

export enum ExemptionType {
  WHOLESALE_RESALE = 'WHOLESALE_RESALE',
  EDUCATIONAL = 'EDUCATIONAL',
  GOVERNMENT = 'GOVERNMENT',
  CHARITABLE_NONPROFIT = 'CHARITABLE_NONPROFIT',
  DIRECT_PAY_PERMIT = 'DIRECT_PAY_PERMIT',
}

export enum CertificateStatus {
  PENDING_VERIFICATION = 'PENDING_VERIFICATION',
  VALID = 'VALID',
  EXPIRED = 'EXPIRED',
  REJECTED = 'REJECTED',
}

export interface TaxExemptionCertificate {
  certificateId: string;
  customerId: string;
  jurisdictionCode: string;
  exemptionType: ExemptionType;
  certificateNumber: string;
  issuingState: string;
  validFrom: Date;
  validTo: Date;
  status: CertificateStatus;
  documentStorageUrl?: string;
  verifiedAt?: Date;
  rejectionReason?: string;
}

export interface VatValidationResult {
  vatNumber: string;
  countryCode: string;
  isValidFormat: boolean;
  isRegisteredVies: boolean;
  companyName?: string;
  companyAddress?: string;
  reverseChargeApplicable: boolean;
  validatedAt: Date;
}

export class VatFormatValidator {
  /**
   * Validates standard European Union VAT identification number formats
   * Format: Country prefix (2 letters) + 8 to 12 alphanumeric digits
   */
  public static validateEUVatFormat(countryCode: string, vatNumber: string): boolean {
    const cleaned = vatNumber.trim().toUpperCase().replace(/[\s.-]/g, '');
    const patterns: Record<string, RegExp> = {
      DE: /^DE[0-9]{9}$/,
      FR: /^FR[A-Z0-9]{2}[0-9]{9}$/,
      IT: /^IT[0-9]{11}$/,
      ES: /^ES[A-Z0-9][0-9]{7}[A-Z0-9]$/,
      NL: /^NL[0-9]{9}B[0-9]{2}$/,
      BE: /^BE[0-9]{10}$/,
      IE: /^IE[0-9]{7}[A-W][A-I]?$/,
      SE: /^SE[0-9]{12}$/,
      PL: /^PL[0-9]{10}$/,
      AT: /^ATU[0-9]{8}$/,
      GB: /^GB([0-9]{9}|[0-9]{12}|(GD|HA)[0-9]{3})$/, // UK HMRC VAT
    };

    const regex = patterns[countryCode.toUpperCase()];
    if (!regex) {
      // Fallback generic EU pattern: 2 letter prefix + 8-12 alphanumeric
      return /^[A-Z]{2}[0-9A-Z]{8,12}$/.test(cleaned);
    }
    return regex.test(cleaned);
  }
}
