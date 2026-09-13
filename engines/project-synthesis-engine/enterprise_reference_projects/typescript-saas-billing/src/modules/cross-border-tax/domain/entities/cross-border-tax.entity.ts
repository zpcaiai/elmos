export enum TaxJurisdictionRegion {
  CANADA = 'CANADA',
  AUSTRALIA = 'AUSTRALIA',
  INDIA = 'INDIA',
  UNITED_KINGDOM = 'UNITED_KINGDOM',
  SINGAPORE = 'SINGAPORE',
}

export enum TaxAuthorityType {
  CANADA_CRA_GST = 'CANADA_CRA_GST',
  CANADA_PROVINCIAL_PST = 'CANADA_PROVINCIAL_PST',
  CANADA_REVENU_QUEBEC_QST = 'CANADA_REVENU_QUEBEC_QST',
  AUSTRALIA_ATO_GST = 'AUSTRALIA_ATO_GST',
  INDIA_GST_IGST = 'INDIA_GST_IGST',
  INDIA_GST_CGST = 'INDIA_GST_CGST',
  INDIA_GST_SGST = 'INDIA_GST_SGST',
  UK_HMRC_VAT = 'UK_HMRC_VAT',
  SINGAPORE_IRAS_GST = 'SINGAPORE_IRAS_GST',
}

export interface TaxCalculationLine {
  taxAuthority: TaxAuthorityType;
  jurisdictionCode: string; // e.g. 'CA-ON', 'CA-QC', 'AU', 'IN-KA'
  taxRatePercentage: number; // e.g. 5.0 for 5%, 9.975 for 9.975%
  taxableAmountCents: number;
  taxCollectedCents: number;
  statutoryDescription: string;
}

export interface CrossBorderTaxCalculationRequest {
  countryCode: string; // ISO 3166-1 alpha-2 ('CA', 'AU', 'IN', 'GB', 'SG')
  subdivisionCode?: string; // e.g. 'ON', 'QC', 'BC', 'NSW', 'KA' (Karnataka)
  postalCode?: string;
  isBusinessCustomer: boolean;
  taxRegistrationNumber?: string; // ABN, GSTIN, QST Number, etc.
  amountCents: number;
  currency: string;
  digitalServiceCommodityCode?: string; // e.g. 'SAC-9984'
}

export interface CrossBorderTaxCalculationResponse {
  countryCode: string;
  subdivisionCode?: string;
  currency: string;
  subtotalCents: number;
  totalTaxCents: number;
  grandTotalCents: number;
  lines: TaxCalculationLine[];
  reverseChargeApplied: boolean;
  reverseChargeNote?: string;
  customerTaxIdValid: boolean;
}
