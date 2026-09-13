import { DunningService, DunningAction } from '../src/modules/billing/domain/services/dunning.service';
import { CustomerAggregate } from '../src/modules/billing/domain/entities/customer.entity';
import { SubscriptionAggregate, SubscriptionStatus, BillingCycle } from '../src/modules/billing/domain/entities/subscription.entity';
import { InvoiceAggregate } from '../src/modules/billing/domain/entities/invoice.entity';

describe('DunningService', () => {
  let dunningService: DunningService;

  beforeEach(() => {
    dunningService = new DunningService();
  });

  it('should escalate penalties over 14 days and cancel subscription on final failure', () => {
    const customer = new CustomerAggregate({
      customerId: 'c_delinquent',
      tenantId: 't_saas',
      email: 'badpayer@example.com',
      name: 'Delinquent User',
    });

    const sub = new SubscriptionAggregate({
      subscriptionId: 'sub_delinquent',
      tenantId: 't_saas',
      customerId: customer.customerId,
      plan: {
        planId: 'plan_basic',
        code: 'BASIC',
        name: 'Basic',
        billingCycle: BillingCycle.MONTHLY,
        basePriceCents: 5000,
        includedSeats: 1,
        perSeatPriceCents: 0,
        features: [],
        trialDays: 0,
      },
    });

    const invoice = new InvoiceAggregate({
      invoiceId: 'inv_delinquent',
      tenantId: 't_saas',
      customerId: customer.customerId,
      invoiceNumber: 'INV-DELINQUENT-01',
      currency: 'USD',
    });
    invoice.addLineItem({
      lineId: 'l1',
      type: 'SUBSCRIPTION_BASE' as any,
      description: 'Basic Monthly',
      quantity: 1,
      unitPriceCents: 5000,
      discountCents: 0,
      taxCents: 0,
    });
    invoice.finalize();

    // Day 1 failure: Retry payment
    const step1 = dunningService.evaluateDunningStep({
      invoice,
      subscription: sub,
      customer,
      daysSinceFailure: 1,
    });
    expect(step1.action).toBe(DunningAction.RETRY_PAYMENT);
    expect(sub.status).toBe(SubscriptionStatus.ACTIVE);

    // Day 7 failure: Mark PAST_DUE
    const step2 = dunningService.evaluateDunningStep({
      invoice,
      subscription: sub,
      customer,
      daysSinceFailure: 7,
    });
    expect(step2.action).toBe(DunningAction.MARK_PAST_DUE);
    expect(sub.status).toBe(SubscriptionStatus.PAST_DUE);

    // Day 14 failure: Cancel subscription
    const step3 = dunningService.evaluateDunningStep({
      invoice,
      subscription: sub,
      customer,
      daysSinceFailure: 14,
    });
    expect(step3.action).toBe(DunningAction.CANCEL_SUBSCRIPTION);
    expect(sub.status).toBe(SubscriptionStatus.CANCELED);
    expect(invoice.status).toBe('UNCOLLECTIBLE');
  });
});
