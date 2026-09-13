import { PricingModel, RatingTier } from '../../domain/entities/rating-matrix.entity';
import { PrepaidCreditBucketType } from '../../domain/entities/prepaid-credit-grant.entity';

export class CreateRatingMatrixDto {
  matrixId!: string;
  metricCode!: string;
  currency!: string;
  pricingModel!: PricingModel;
  tiers!: RatingTier[];
  minimumCommitmentCents?: number;
  surgeMultiplier?: number;
  effectiveFrom!: string;
  effectiveTo?: string | null;
}

export class RateUsageRequestDto {
  matrixId!: string;
  units!: number;
  surgeMultiplier?: number;
}

export class GrantPrepaidCreditsDto {
  grantId!: string;
  customerId!: string;
  bucketType!: PrepaidCreditBucketType;
  currency!: string;
  amountCents!: number;
  priorityRank?: number;
  expiresAt?: string | null;
  applicableMetricCodes?: string[];
}

export class ApplyDrawdownRequestDto {
  customerId!: string;
  chargeAmountCents!: number;
  metricCode!: string;
}
