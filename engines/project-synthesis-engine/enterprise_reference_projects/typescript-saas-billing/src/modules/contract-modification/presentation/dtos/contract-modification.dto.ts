export class AddedObligationDto {
  name!: string;
  isDistinct!: boolean;
  isAtStandaloneSellingPrice!: boolean;
  standaloneSellingPriceCents!: number;
  offeredPriceCents!: number;
  periodMonths!: number;
}

export class ExistingObligationDto {
  obligationId!: string;
  name!: string;
  isDistinct!: boolean;
  standaloneSellingPriceCents!: number;
  allocatedTransactionPriceCents!: number;
  recognizedRevenueCents!: number;
  deferredRevenueCents!: number;
  progressPercentage!: number;
  totalPeriodMonths!: number;
  remainingPeriodMonths!: number;
}

export class EvaluateModificationRequestDto {
  amendmentId!: string;
  originalContractId!: string;
  description!: string;
  additionalConsiderationCents!: number;
  priceConcessionOnRemainingCents?: number;
  addedObligations!: AddedObligationDto[];
  existingObligations!: ExistingObligationDto[];
}
