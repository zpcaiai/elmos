export enum PrepaidCreditBucketType {
  PROMOTIONAL_NON_REFUNDABLE = 'PROMOTIONAL_NON_REFUNDABLE',
  CONTRACTUAL_INCLUDED = 'CONTRACTUAL_INCLUDED',
  PAID_ON_DEMAND = 'PAID_ON_DEMAND',
}

export interface PrepaidCreditGrant {
  grantId: string;
  customerId: string;
  bucketType: PrepaidCreditBucketType;
  currency: string;
  initialCreditsCents: number;
  remainingCreditsCents: number;
  priorityRank: number; // Lower number = drawn down first (e.g. promotional=10, included=20, paid=30)
  grantedAt: Date;
  expiresAt: Date | null; // null for non-expiring
  applicableMetricCodes: string[]; // empty array means universal credit
  isRolloverEligible: boolean;
}

export interface DrawdownTransaction {
  transactionId: string;
  grantId: string;
  bucketType: PrepaidCreditBucketType;
  amountDrawnCents: number;
  drawnAt: Date;
  remainingAfterCents: number;
}

export interface DrawdownResult {
  customerId: string;
  totalRequestedCents: number;
  totalDrawnCents: number;
  uncoveredDeficitCents: number;
  transactions: DrawdownTransaction[];
  exhaustedGrantIds: string[];
  remainingTotalCreditsCents: number;
}
