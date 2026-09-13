export enum PricingModel {
  VOLUME = 'VOLUME',
  GRADUATED_TIERED = 'GRADUATED_TIERED',
  FLAT_FEE_WITH_OVERAGE = 'FLAT_FEE_WITH_OVERAGE',
  STAIR_STEP = 'STAIR_STEP',
}

export interface RatingTier {
  tierNumber: number;
  minUnits: number;
  maxUnits: number | null; // null means unbounded upper slab
  unitRateCents: number; // Stored in integer cents or micros
  flatFeeCents: number;
}

export interface TierBreakdownItem {
  tierNumber: number;
  unitsAllocated: number;
  unitRateCents: number;
  flatFeeCents: number;
  subtotalCents: number;
}

export interface RatingMatrix {
  matrixId: string;
  metricCode: string; // e.g. 'api_calls', 'storage_gb', 'compute_hours'
  currency: string;
  pricingModel: PricingModel;
  tiers: RatingTier[];
  minimumCommitmentCents: number; // Take-or-pay minimum contractual fee
  surgeMultiplier: number; // 1.0 for normal, e.g. 1.25 for peak congestion
  effectiveFrom: Date;
  effectiveTo: Date | null;
}

export interface RatingResult {
  matrixId: string;
  metricCode: string;
  currency: string;
  rawUnits: number;
  ratedAmountCents: number;
  commitmentShortfallCents: number;
  totalBilledCents: number;
  breakdown: TierBreakdownItem[];
  surgeApplied: boolean;
  surgeMultiplier: number;
}
