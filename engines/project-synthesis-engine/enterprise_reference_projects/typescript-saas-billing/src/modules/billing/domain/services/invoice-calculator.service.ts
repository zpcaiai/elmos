import { CustomerAggregate } from '../entities/customer.entity';
import { SubscriptionAggregate } from '../entities/subscription.entity';
import { InvoiceAggregate, LineItemType } from '../entities/invoice.entity';
import { PricingTierDefinition } from '../entities/pricing-tier.entity';
import { UsageAggregatorService } from './usage-aggregator.service';

export interface MeteredUsageConfig {
  metricKey: string;
  description: string;
  pricingTier: PricingTierDefinition;
}

export class InvoiceCalculatorService {
  constructor(private usageAggregator: UsageAggregatorService) {}

  generateBillingCycleInvoice(params: {
    invoiceId: string;
    invoiceNumber: string;
    customer: CustomerAggregate;
    subscription: SubscriptionAggregate;
    periodStart: Date;
    periodEnd: Date;
    meteredConfigs?: MeteredUsageConfig[];
    taxRatePercent?: number; // e.g. 8.25 for 8.25%
  }): InvoiceAggregate {
    const { customer, subscription, periodStart, periodEnd } = params;

    const invoice = new InvoiceAggregate({
      invoiceId: params.invoiceId,
      tenantId: subscription.tenantId,
      customerId: customer.customerId,
      subscriptionId: subscription.subscriptionId,
      invoiceNumber: params.invoiceNumber,
      currency: customer.currency,
      issuedAt: new Date(),
      dueDate: new Date(Date.now() + 14 * 86400000),
    });

    // 1. Base Subscription Charge
    invoice.addLineItem({
      lineId: `${params.invoiceId}_base`,
      type: LineItemType.SUBSCRIPTION_BASE,
      description: `${subscription.plan.name} (${subscription.plan.billingCycle})`,
      quantity: 1,
      unitPriceCents: subscription.plan.basePriceCents,
      discountCents: 0,
      taxCents: 0,
      periodStart,
      periodEnd,
    });

    // 2. Extra Seats Charge
    const extraSeats = Math.max(0, subscription.seats - subscription.plan.includedSeats);
    if (extraSeats > 0 && subscription.plan.perSeatPriceCents > 0) {
      invoice.addLineItem({
        lineId: `${params.invoiceId}_seats`,
        type: LineItemType.SEAT_OVERAGE,
        description: `Additional User Seats (${extraSeats} x ${subscription.plan.perSeatPriceCents / 100} ${customer.currency})`,
        quantity: extraSeats,
        unitPriceCents: subscription.plan.perSeatPriceCents,
        discountCents: 0,
        taxCents: 0,
        periodStart,
        periodEnd,
      });
    }

    // 3. Metered Usage Charges
    if (params.meteredConfigs && params.meteredConfigs.length > 0) {
      for (const config of params.meteredConfigs) {
        const units = this.usageAggregator.getAggregatedUsage(
          subscription.tenantId,
          customer.customerId,
          config.metricKey,
          periodStart,
          periodEnd
        );

        if (units > 0) {
          const tierResult = config.pricingTier.calculateCost(units);
          invoice.addLineItem({
            lineId: `${params.invoiceId}_meter_${config.metricKey}`,
            type: LineItemType.USAGE_METERED,
            description: `${config.description} (${units} units billed under ${tierResult.mode})`,
            quantity: 1,
            unitPriceCents: tierResult.totalCostCents,
            discountCents: 0,
            taxCents: 0,
            periodStart,
            periodEnd,
            metadata: { totalUnits: units, tierBreakdown: tierResult.bracketBreakdown },
          });
        }
      }
    }

    // 4. Calculate Tax
    if (!customer.taxExempt && params.taxRatePercent && params.taxRatePercent > 0) {
      const taxAmount = Math.round((invoice.subtotalCents * params.taxRatePercent) / 100);
      if (taxAmount > 0) {
        invoice.addLineItem({
          lineId: `${params.invoiceId}_tax`,
          type: LineItemType.TAX,
          description: `Sales Tax (${params.taxRatePercent}%)`,
          quantity: 1,
          unitPriceCents: taxAmount,
          discountCents: 0,
          taxCents: 0,
        });
      }
    }

    // 5. Apply Customer Credit Balance
    if (customer.creditBalanceCents > 0) {
      const creditApplied = customer.deductCredit(invoice.totalCents);
      if (creditApplied > 0) {
        invoice.addLineItem({
          lineId: `${params.invoiceId}_credit_offset`,
          type: LineItemType.DISCOUNT,
          description: `Customer Credit Balance Applied`,
          quantity: 1,
          unitPriceCents: 0,
          discountCents: creditApplied,
          taxCents: 0,
        });
      }
    }

    invoice.finalize();
    return invoice;
  }
}
