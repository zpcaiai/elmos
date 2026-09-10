import { CustomerAggregate } from '../src/modules/billing/domain/entities/customer.entity';
import {
  SubscriptionAggregate,
  SubscriptionPlan,
  BillingCycle,
} from '../src/modules/billing/domain/entities/subscription.entity';
import { UsageAggregatorService } from '../src/modules/billing/domain/services/usage-aggregator.service';
import { InvoiceCalculatorService } from '../src/modules/billing/domain/services/invoice-calculator.service';
import {
  PricingTierDefinition,
  TierMode,
} from '../src/modules/billing/domain/entities/pricing-tier.entity';
import { InvoiceStatus } from '../src/modules/billing/domain/entities/invoice.entity';

describe('Billing Engine End-to-End Cycle', () => {
  it('should process a complete billing cycle with tiered usage, credits, and payment', () => {
    const tenantId = 'tenant_e2e';
    const customerId = 'cust_enterprise_01';

    // 1. Create Customer with $20 credit balance ($20.00 = 2000 cents)
    const customer = new CustomerAggregate({
      customerId,
      tenantId,
      email: 'finance@acme.corp',
      name: 'Acme Corporation',
      currency: 'USD',
      creditBalanceCents: 2000,
    });

    // 2. Setup Business Plan ($200/mo, 5 seats included, $20/extra seat)
    const businessPlan: SubscriptionPlan = {
      planId: 'plan_business',
      code: 'BIZ_TIER',
      name: 'Business Plan',
      billingCycle: BillingCycle.MONTHLY,
      basePriceCents: 20000, // $200.00
      includedSeats: 5,
      perSeatPriceCents: 2000, // $20.00 per extra seat
      features: [{ featureKey: 'sso', name: 'SAML SSO', limit: 1 }],
      trialDays: 0,
    };

    const periodStart = new Date('2026-05-01T00:00:00Z');
    const periodEnd = new Date('2026-06-01T00:00:00Z');

    // Customer has 8 seats allocated (3 extra seats = $60 extra)
    const subscription = new SubscriptionAggregate({
      subscriptionId: 'sub_biz_01',
      tenantId,
      customerId,
      plan: businessPlan,
      currentPeriodStart: periodStart,
      currentPeriodEnd: periodEnd,
      seats: 8,
    });

    // 3. Setup Usage Metering with Graduated Tiers:
    // First 10,000 API calls: $0.002 / call (20 cents per 100 calls)
    // Next 40,000 API calls: $0.001 / call (10 cents per 100 calls)
    const apiPricing = new PricingTierDefinition({
      metricKey: 'api_calls',
      mode: TierMode.GRADUATED,
      brackets: [
        { upToUnits: 10000, unitPriceCents: 2, flatFeeCents: 0 },
        { upToUnits: 50000, unitPriceCents: 1, flatFeeCents: 0 },
      ],
    });

    const usageAggregator = new UsageAggregatorService();
    // Simulate 25,000 API calls made during May
    // 10,000 @ 2 cents = 20,000 cents ($200)
    // 15,000 @ 1 cent = 15,000 cents ($150)
    // Total usage = 35,000 cents ($350)
    usageAggregator.ingestBatch([
      {
        eventId: 'ev_1',
        tenantId,
        customerId,
        subscriptionId: subscription.subscriptionId,
        metricKey: 'api_calls',
        value: 15000,
        timestamp: new Date('2026-05-10T12:00:00Z'),
        idempotencyKey: 'k_may_10',
      },
      {
        eventId: 'ev_2',
        tenantId,
        customerId,
        subscriptionId: subscription.subscriptionId,
        metricKey: 'api_calls',
        value: 10000,
        timestamp: new Date('2026-05-20T12:00:00Z'),
        idempotencyKey: 'k_may_20',
      },
    ]);

    // 4. Run Invoice Calculation Pipeline
    const invoiceCalculator = new InvoiceCalculatorService(usageAggregator);
    const invoice = invoiceCalculator.generateBillingCycleInvoice({
      invoiceId: 'inv_may_2026',
      invoiceNumber: 'INV-2026-05-001',
      customer,
      subscription,
      periodStart,
      periodEnd,
      meteredConfigs: [
        {
          metricKey: 'api_calls',
          description: 'API Request Volume',
          pricingTier: apiPricing,
        },
      ],
      taxRatePercent: 0, // Tax exempt for this test
    });

    // Verification:
    // Base: $200.00 (20000 cents)
    // Extra Seats (3 x $20): $60.00 (6000 cents)
    // Metered Usage (25,000 calls): $350.00 (35000 cents)
    // Subtotal: $610.00 (61000 cents)
    // Customer Credit Applied: -$20.00 (-2000 cents)
    // Net Total Due: $590.00 (59000 cents)
    expect(invoice.subtotalCents).toBe(61000);
    expect(invoice.totalCents).toBe(59000);
    expect(customer.creditBalanceCents).toBe(0); // Fully consumed
    expect(invoice.status).toBe(InvoiceStatus.OPEN);

    // 5. Pay the invoice
    invoice.recordPaymentAttempt({
      attemptId: 'pay_txn_001',
      timestamp: new Date(),
      amountCents: 59000,
      paymentMethodId: 'pm_card_visa_4242',
      status: 'SUCCESS',
      gatewayTransactionId: 'ch_stripe_mock_001',
    });

    expect(invoice.status).toBe(InvoiceStatus.PAID);
    expect(invoice.amountRemainingCents).toBe(0);
    expect(invoice.amountPaidCents).toBe(59000);
  });
});
