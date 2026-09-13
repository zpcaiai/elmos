/**
 * Global Tax Jurisdiction & Rules Entities
 *
 * Models tax jurisdictions across multiple hierarchical tiers:
 * Country, State/Province, County, City, Special Tax District.
 * Supports destination-based vs origin-based sourcing, digital services tax (DST),
 * and standard VAT/GST/Sales Tax regimes.
 */

export enum JurisdictionLevel {
  COUNTRY = 'COUNTRY',
  STATE_PROVINCE = 'STATE_PROVINCE',
  COUNTY = 'COUNTY',
  CITY = 'CITY',
  SPECIAL_DISTRICT = 'SPECIAL_DISTRICT',
}

export enum TaxType {
  SALES_TAX = 'SALES_TAX',       // US style sales & use tax
  VAT = 'VAT',                   // European Union Value Added Tax / UK VAT
  GST = 'GST',                   // Australia / Canada / India Goods & Services Tax
  DIGITAL_SERVICES = 'DIGITAL_SERVICES', // DST (e.g. France, UK, Italy)
  COMMUNICATIONS = 'COMMUNICATIONS',     // Telecom / VoIP tax
}

export enum SourcingRule {
  DESTINATION = 'DESTINATION',   // Taxed based on customer ship-to / billing location
  ORIGIN = 'ORIGIN',             // Taxed based on seller physical dispatch location
}

export interface TaxRule {
  ruleId: string;
  taxType: TaxType;
  ratePercentage: number; // e.g. 0.0825 for 8.25%
  appliesToDigitalGoods: boolean;
  appliesToServices: boolean;
  reducedRateCategories?: string[];
  effectiveFrom: Date;
  effectiveTo?: Date;
}

export class TaxJurisdiction {
  public id: string;
  public code: string;           // e.g. "US-CA", "EU-DE", "US-TX-AUSTIN"
  public name: string;
  public countryCode: string;    // ISO-3166-1 alpha-2 (e.g. "US", "DE", "GB")
  public level: JurisdictionLevel;
  public parentJurisdictionCode?: string;
  public sourcingRule: SourcingRule;
  public rules: TaxRule[];
  public isEUOSS: boolean;       // Participates in EU One-Stop Shop mechanism
  public reverseChargeAllowed: boolean; // B2B reverse charge applicable

  constructor(params: {
    id: string;
    code: string;
    name: string;
    countryCode: string;
    level: JurisdictionLevel;
    parentJurisdictionCode?: string;
    sourcingRule?: SourcingRule;
    rules?: TaxRule[];
    isEUOSS?: boolean;
    reverseChargeAllowed?: boolean;
  }) {
    this.id = params.id;
    this.code = params.code;
    this.name = params.name;
    this.countryCode = params.countryCode.toUpperCase();
    this.level = params.level;
    this.parentJurisdictionCode = params.parentJurisdictionCode;
    this.sourcingRule = params.sourcingRule || SourcingRule.DESTINATION;
    this.rules = params.rules ? [...params.rules] : [];
    this.isEUOSS = params.isEUOSS ?? false;
    this.reverseChargeAllowed = params.reverseChargeAllowed ?? false;
  }

  /**
   * Adds an active tax rule to the jurisdiction
   */
  public addRule(rule: TaxRule): void {
    const exists = this.rules.some(r => r.ruleId === rule.ruleId);
    if (exists) {
      throw new Error(`Rule ${rule.ruleId} already exists in jurisdiction ${this.code}`);
    }
    this.rules.push(rule);
  }

  /**
   * Finds effective tax rate for a given commodity type at a specific point in time
   */
  public getEffectiveRate(params: {
    taxType: TaxType;
    isDigital: boolean;
    isService: boolean;
    asOfDate?: Date;
  }): number {
    const date = params.asOfDate || new Date();
    let totalRate = 0;

    for (const rule of this.rules) {
      if (rule.taxType !== params.taxType) continue;
      if (rule.effectiveFrom > date) continue;
      if (rule.effectiveTo && rule.effectiveTo < date) continue;

      if (params.isDigital && !rule.appliesToDigitalGoods) continue;
      if (params.isService && !rule.appliesToServices) continue;

      totalRate += rule.ratePercentage;
    }

    return Math.round(totalRate * 10000) / 10000;
  }
}
