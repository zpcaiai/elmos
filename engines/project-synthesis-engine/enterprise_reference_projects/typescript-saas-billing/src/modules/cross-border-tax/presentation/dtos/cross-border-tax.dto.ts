export class CalculateCrossBorderTaxDto {
  countryCode!: string;
  subdivisionCode?: string;
  postalCode?: string;
  isBusinessCustomer!: boolean;
  taxRegistrationNumber?: string;
  amountCents!: number;
  currency!: string;
  digitalServiceCommodityCode?: string;
}

export class ValidateTaxIdDto {
  countryCode!: string;
  taxRegistrationNumber!: string;
}
