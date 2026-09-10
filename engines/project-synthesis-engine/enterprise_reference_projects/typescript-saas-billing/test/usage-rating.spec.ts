import { UsageRatingEngineService } from '../src/modules/usage-rating/domain/services/usage-rating-engine.service';
import { CreditDrawdownWaterfallService } from '../src/modules/usage-rating/domain/services/credit-drawdown-waterfall.service';
import {
  RatingMatrix,
  PricingModel,
} from '../src/modules/usage-rating/domain/entities/rating-matrix.entity';
import {
  PrepaidCreditGrant,
  PrepaidCreditBucketType,
} from '../src/modules/usage-rating/domain/entities/prepaid-credit-grant.entity';

describe('Usage Rating & Pricing Matrix Engine', () => {
  let ratingEngine: UsageRatingEngineService;

  beforeEach(() => {
    ratingEngine = new UsageRatingEngineService();
  });

  it('should accurately calculate graduated tiered pricing across multiple slabs', () => {
    const matrix: RatingMatrix = {
      matrixId: 'MAT-GRAD-001',
      metricCode: 'api_requests',
      currency: 'USD',
      pricingModel: PricingModel.GRADUATED_TIERED,
      tiers: [
        { tierNumber: 1, minUnits: 0, maxUnits: 1000, unitRateCents: 10, flatFeeCents: 0 }, // $0.10/unit
        { tierNumber: 2, minUnits: 1000, maxUnits: 5000, unitRateCents: 6, flatFeeCents: 0 }, // $0.06/unit
        { tierNumber: 3, minUnits: 5000, maxUnits: null, unitRateCents: 3, flatFeeCents: 0 }, // $0.03/unit
      ],
      minimumCommitmentCents: 0,
      surgeMultiplier: 1.0,
      effectiveFrom: new Date('2026-01-01'),
      effectiveTo: null,
    };

    // 7,500 units:
    // Tier 1: 1,000 * 10 = 10,000 cents ($100.00)
    // Tier 2: 4,000 * 6 = 24,000 cents ($240.00)
    // Tier 3: 2,500 * 3 = 7,500 cents ($75.00)
    // Total = 41,500 cents ($415.00)
    const result = ratingEngine.rateUsage(7500, matrix);

    expect(result.rawUnits).toBe(7500);
    expect(result.ratedAmountCents).toBe(41500);
    expect(result.totalBilledCents).toBe(41500);
    expect(result.commitmentShortfallCents).toBe(0);
    expect(result.breakdown).toHaveLength(3);
    expect(result.breakdown[0].unitsAllocated).toBe(1000);
    expect(result.breakdown[1].unitsAllocated).toBe(4000);
    expect(result.breakdown[2].unitsAllocated).toBe(2500);
  });

  it('should evaluate volume pricing by rating entire consumption at the qualifying tier rate', () => {
    const matrix: RatingMatrix = {
      matrixId: 'MAT-VOL-002',
      metricCode: 'storage_gb',
      currency: 'USD',
      pricingModel: PricingModel.VOLUME,
      tiers: [
        { tierNumber: 1, minUnits: 0, maxUnits: 100, unitRateCents: 25, flatFeeCents: 0 }, // $0.25/GB
        { tierNumber: 2, minUnits: 100, maxUnits: 500, unitRateCents: 18, flatFeeCents: 0 }, // $0.18/GB
        { tierNumber: 3, minUnits: 500, maxUnits: null, unitRateCents: 12, flatFeeCents: 0 }, // $0.12/GB
      ],
      minimumCommitmentCents: 0,
      surgeMultiplier: 1.0,
      effectiveFrom: new Date('2026-01-01'),
      effectiveTo: null,
    };

    // 250 GB qualifies for Tier 2 ($0.18/GB) -> 250 * 18 = 4,500 cents ($45.00)
    const result = ratingEngine.rateUsage(250, matrix);

    expect(result.ratedAmountCents).toBe(4500);
    expect(result.breakdown).toHaveLength(1);
    expect(result.breakdown[0].tierNumber).toBe(2);
    expect(result.breakdown[0].unitRateCents).toBe(18);
  });

  it('should enforce contractual minimum spend commitment and bill shortfall fee', () => {
    const matrix: RatingMatrix = {
      matrixId: 'MAT-COMMIT-003',
      metricCode: 'compute_vcpu_hours',
      currency: 'USD',
      pricingModel: PricingModel.GRADUATED_TIERED,
      tiers: [
        { tierNumber: 1, minUnits: 0, maxUnits: null, unitRateCents: 5, flatFeeCents: 0 }, // $0.05/hr
      ],
      minimumCommitmentCents: 20000, // $200.00 minimum monthly commitment
      surgeMultiplier: 1.0,
      effectiveFrom: new Date('2026-01-01'),
      effectiveTo: null,
    };

    // Customer only consumed 1,000 hours -> 1,000 * 5 = 5,000 cents ($50.00)
    // Shortfall = $200.00 - $50.00 = 15,000 cents ($150.00)
    // Total billed must strictly be $200.00 (20,000 cents)
    const result = ratingEngine.rateUsage(1000, matrix);

    expect(result.ratedAmountCents).toBe(5000);
    expect(result.commitmentShortfallCents).toBe(15000);
    expect(result.totalBilledCents).toBe(20000);
  });

  it('should apply peak surge pricing multiplier correctly', () => {
    const matrix: RatingMatrix = {
      matrixId: 'MAT-SURGE-004',
      metricCode: 'ai_token_generation',
      currency: 'USD',
      pricingModel: PricingModel.GRADUATED_TIERED,
      tiers: [
        { tierNumber: 1, minUnits: 0, maxUnits: null, unitRateCents: 2, flatFeeCents: 0 },
      ],
      minimumCommitmentCents: 0,
      surgeMultiplier: 1.0,
      effectiveFrom: new Date('2026-01-01'),
      effectiveTo: null,
    };

    // 10,000 units at $0.02 = 20,000 cents.
    // Surge 1.5x during high congestion -> 20,000 * 1.5 = 30,000 cents.
    const result = ratingEngine.rateUsage(10000, matrix, { surgeMultiplier: 1.5 });

    expect(result.surgeApplied).toBe(true);
    expect(result.surgeMultiplier).toBe(1.5);
    expect(result.totalBilledCents).toBe(30000);
  });
});

describe('Prepaid Credit Drawdown Waterfall Engine', () => {
  let drawdownService: CreditDrawdownWaterfallService;

  beforeEach(() => {
    drawdownService = new CreditDrawdownWaterfallService();
  });

  it('should exhaust promotional credits before contractual and paid credits', () => {
    const grants: PrepaidCreditGrant[] = [
      {
        grantId: 'GRANT-PAID-001',
        customerId: 'CUST-ORG-55',
        bucketType: PrepaidCreditBucketType.PAID_ON_DEMAND,
        currency: 'USD',
        initialCreditsCents: 10000, // $100.00
        remainingCreditsCents: 10000,
        priorityRank: 30,
        grantedAt: new Date('2026-01-01'),
        expiresAt: null,
        applicableMetricCodes: [],
        isRolloverEligible: true,
      },
      {
        grantId: 'GRANT-PROMO-002',
        customerId: 'CUST-ORG-55',
        bucketType: PrepaidCreditBucketType.PROMOTIONAL_NON_REFUNDABLE,
        currency: 'USD',
        initialCreditsCents: 5000, // $50.00
        remainingCreditsCents: 5000,
        priorityRank: 10,
        grantedAt: new Date('2026-01-15'),
        expiresAt: new Date('2026-12-31'),
        applicableMetricCodes: [],
        isRolloverEligible: false,
      },
    ];

    // Charge $70.00 (7,000 cents)
    // Waterfall should draw:
    // 1. $50.00 entirely from PROMOTIONAL (exhausting it)
    // 2. Remaining $20.00 from PAID (leaving $80.00 in paid)
    const result = drawdownService.executeDrawdown('CUST-ORG-55', 7000, 'api_calls', grants);

    expect(result.totalRequestedCents).toBe(7000);
    expect(result.totalDrawnCents).toBe(7000);
    expect(result.uncoveredDeficitCents).toBe(0);
    expect(result.transactions).toHaveLength(2);

    expect(result.transactions[0].grantId).toBe('GRANT-PROMO-002');
    expect(result.transactions[0].amountDrawnCents).toBe(5000);
    expect(result.transactions[0].remainingAfterCents).toBe(0);

    expect(result.transactions[1].grantId).toBe('GRANT-PAID-001');
    expect(result.transactions[1].amountDrawnCents).toBe(2000);
    expect(result.transactions[1].remainingAfterCents).toBe(8000);

    expect(result.exhaustedGrantIds).toContain('GRANT-PROMO-002');
    expect(result.remainingTotalCreditsCents).toBe(8000);
  });

  it('should ignore expired grants and report uncovered deficit when balances are insufficient', () => {
    const now = new Date('2026-09-10T12:00:00Z');
    const grants: PrepaidCreditGrant[] = [
      {
        grantId: 'GRANT-EXPIRED',
        customerId: 'CUST-ORG-77',
        bucketType: PrepaidCreditBucketType.PROMOTIONAL_NON_REFUNDABLE,
        currency: 'USD',
        initialCreditsCents: 5000,
        remainingCreditsCents: 5000,
        priorityRank: 10,
        grantedAt: new Date('2026-01-01'),
        expiresAt: new Date('2026-06-01'), // Expired 3 months ago
        applicableMetricCodes: [],
        isRolloverEligible: false,
      },
      {
        grantId: 'GRANT-ACTIVE',
        customerId: 'CUST-ORG-77',
        bucketType: PrepaidCreditBucketType.CONTRACTUAL_INCLUDED,
        currency: 'USD',
        initialCreditsCents: 3000,
        remainingCreditsCents: 3000,
        priorityRank: 20,
        grantedAt: new Date('2026-08-01'),
        expiresAt: new Date('2026-12-31'),
        applicableMetricCodes: [],
        isRolloverEligible: true,
      },
    ];

    // Charge $100.00 (10,000 cents)
    // Only GRANT-ACTIVE ($30.00) is eligible. Deficit of $70.00 remains to be billed.
    const result = drawdownService.executeDrawdown('CUST-ORG-77', 10000, 'compute', grants, now);

    expect(result.totalRequestedCents).toBe(10000);
    expect(result.totalDrawnCents).toBe(3000);
    expect(result.uncoveredDeficitCents).toBe(7000);
    expect(result.transactions).toHaveLength(1);
    expect(result.transactions[0].grantId).toBe('GRANT-ACTIVE');
    expect(result.exhaustedGrantIds).toContain('GRANT-ACTIVE');
  });

  it('should strictly respect metric code restrictions on category-specific credits', () => {
    const grants: PrepaidCreditGrant[] = [
      {
        grantId: 'GRANT-GPU-ONLY',
        customerId: 'CUST-ORG-99',
        bucketType: PrepaidCreditBucketType.CONTRACTUAL_INCLUDED,
        currency: 'USD',
        initialCreditsCents: 20000,
        remainingCreditsCents: 20000,
        priorityRank: 10,
        grantedAt: new Date('2026-01-01'),
        expiresAt: null,
        applicableMetricCodes: ['gpu_h100_hours'], // Restricted only to GPU
        isRolloverEligible: true,
      },
    ];

    // Attempting to draw down for general storage charges -> should not use GPU credits
    const result = drawdownService.executeDrawdown('CUST-ORG-99', 5000, 'object_storage_gb', grants);

    expect(result.totalDrawnCents).toBe(0);
    expect(result.uncoveredDeficitCents).toBe(5000);
    expect(result.transactions).toHaveLength(0);
  });
});
