export enum ASC606ModificationAccountingTreatment {
  SEPARATE_CONTRACT = 'SEPARATE_CONTRACT',
  PROSPECTIVE_REALLOCATION = 'PROSPECTIVE_REALLOCATION',
  CUMULATIVE_CATCH_UP = 'CUMULATIVE_CATCH_UP',
}

export interface ContractPerformanceObligation {
  obligationId: string;
  name: string;
  isDistinct: boolean;
  standaloneSellingPriceCents: number;
  allocatedTransactionPriceCents: number;
  recognizedRevenueCents: number;
  deferredRevenueCents: number;
  progressPercentage: number; // 0.0 to 100.0
  totalPeriodMonths: number;
  remainingPeriodMonths: number;
}

export interface ContractModificationAmendment {
  amendmentId: string;
  originalContractId: string;
  effectiveDate: Date;
  description: string;
  additionalConsiderationCents: number;
  addedObligations: {
    name: string;
    isDistinct: boolean;
    isAtStandaloneSellingPrice: boolean;
    standaloneSellingPriceCents: number;
    offeredPriceCents: number;
    periodMonths: number;
  }[];
  priceConcessionOnRemainingCents: number;
}

export interface ModificationAccountingDecision {
  amendmentId: string;
  treatment: ASC606ModificationAccountingTreatment;
  rationale: string;
  cumulativeCatchUpAdjustmentCents: number; // Positive = increase revenue now, Negative = reduction
  revisedObligations: ContractPerformanceObligation[];
  totalRevisedContractValueCents: number;
  futureRatableMonthlyRevenueCents: number;
}
