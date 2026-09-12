export type BillingResponsibility = 'CENTRALIZED_PARENT' | 'DECENTRALIZED_SELF' | 'HYBRID_SPLIT';

export interface SplitBillingRule {
  parentPercentage: number;       // e.g. 0.80 for 80%
  subsidiaryPercentage: number;   // e.g. 0.20 for 20%
}

export interface CustomerHierarchyNode {
  customerId: string;
  legalEntityName: string;
  country: string;
  taxRegistrationNumber?: string;
  parentCustomerId?: string;
  hierarchyLevel: number; // 0 = Global HQ, 1 = Regional Division, 2 = Operating OpCo, 3 = Department
  billingResponsibility: BillingResponsibility;
  splitRule?: SplitBillingRule;
  sharedCreditQuotaUsd?: number;
}

export interface SubsidiaryBillingLine {
  lineId: string;
  subsidiaryCustomerId: string;
  subsidiaryName: string;
  serviceDescription: string;
  unitsConsumed: number;
  unadjustedAmountUsd: number;
  effectiveVolumeDiscountRate: number; // e.g. 0.15 for 15% group discount
  discountedAmountUsd: number;
  allocatedToParentUsd: number;
  allocatedToSubsidiaryUsd: number;
}

export interface ConsolidatedGroupInvoice {
  invoiceId: string;
  rootParentCustomerId: string;
  rootParentEntityName: string;
  billingPeriod: string; // e.g. "2026-06"
  totalGroupUnitsConsumed: number;
  groupVolumeDiscountTierName: string;
  groupVolumeDiscountRate: number;
  totalGrossChargesUsd: number;
  totalGroupVolumeDiscountUsd: number;
  totalNetChargesUsd: number;
  totalBilledToParentHqUsd: number;
  totalBilledDirectToSubsidiariesUsd: number;
  subsidiaryLineItems: SubsidiaryBillingLine[];
  perSubsidiarySummaries: Map<string, {
    grossAmountUsd: number;
    discountedAmountUsd: number;
    parentShareUsd: number;
    selfShareUsd: number;
  }>;
}

export interface SharedCreditDrawdownResult {
  creditPoolOpeningBalanceUsd: number;
  totalDrawnUsd: number;
  creditPoolClosingBalanceUsd: number;
  subsidiaryAllocations: Map<string, number>;
  exhaustionStatus: 'FULLY_SATISFIED' | 'PARTIALLY_SATISFIED' | 'POOL_EXHAUSTED';
}
