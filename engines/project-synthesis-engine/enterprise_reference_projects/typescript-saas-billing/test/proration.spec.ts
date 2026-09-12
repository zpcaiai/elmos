import { ProrationService } from '../src/modules/billing/domain/services/proration.service';
import {
  SubscriptionAggregate,
  SubscriptionPlan,
  BillingCycle,
} from '../src/modules/billing/domain/entities/subscription.entity';

describe('ProrationService', () => {
  let prorationService: ProrationService;

  beforeEach(() => {
    prorationService = new ProrationService();
  });

  const starterPlan: SubscriptionPlan = {
    planId: 'plan_starter',
    code: 'STARTER',
    name: 'Starter Plan',
    billingCycle: BillingCycle.MONTHLY,
    basePriceCents: 3000, // $30/mo
    includedSeats: 2,
    perSeatPriceCents: 1000, // $10/seat
    features: [],
    trialDays: 0,
  };

  const proPlan: SubscriptionPlan = {
    planId: 'plan_pro',
    code: 'PRO',
    name: 'Pro Plan',
    billingCycle: BillingCycle.MONTHLY,
    basePriceCents: 9000, // $90/mo
    includedSeats: 5,
    perSeatPriceCents: 1500, // $15/seat
    features: [],
    trialDays: 0,
  };

  it('should correctly prorate mid-month upgrade with 50% remaining time', () => {
    const periodStart = new Date('2026-06-01T00:00:00Z');
    const periodEnd = new Date('2026-07-01T00:00:00Z'); // 30 days
    const changeDate = new Date('2026-06-16T00:00:00Z'); // Exactly 50% through

    const sub = new SubscriptionAggregate({
      subscriptionId: 'sub_test_01',
      tenantId: 'tenant_test',
      customerId: 'cust_01',
      plan: starterPlan,
      currentPeriodStart: periodStart,
      currentPeriodEnd: periodEnd,
      seats: 2,
    });

    const result = prorationService.calculatePlanChangeProration({
      subscription: sub,
      newPlan: proPlan,
      changeTimestamp: changeDate,
    });

    // 50% of starter ($30) is $15 unused credit
    expect(result.unusedCurrentPlanCents).toBe(1500);
    // 50% of pro ($90) is $45 charge
    expect(result.costNewPlanCents).toBe(4500);
    // Net amount = $45 - $15 = $30 (3000 cents)
    expect(result.netAmountCents).toBe(3000);
    expect(result.lineItems).toHaveLength(2);
  });

  it('should correctly prorate adding extra seats mid-cycle', () => {
    const periodStart = new Date('2026-06-01T00:00:00Z');
    const periodEnd = new Date('2026-07-01T00:00:00Z');
    const changeDate = new Date('2026-06-16T00:00:00Z'); // 50% remaining

    const sub = new SubscriptionAggregate({
      subscriptionId: 'sub_test_02',
      tenantId: 'tenant_test',
      customerId: 'cust_02',
      plan: starterPlan, // $10/seat
      currentPeriodStart: periodStart,
      currentPeriodEnd: periodEnd,
      seats: 2,
    });

    // Add 4 additional seats (from 2 to 6)
    const result = prorationService.calculateSeatAdjustmentProration({
      subscription: sub,
      newSeatCount: 6,
      changeTimestamp: changeDate,
    });

    // 4 seats * ($10 * 50%) = 4 * $5 = $20 (2000 cents)
    expect(result.netAmountCents).toBe(2000);
    expect(result.costNewPlanCents).toBe(2000);
  });
});
