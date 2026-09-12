import { SubscriptionAggregate, SubscriptionPlan } from '../entities/subscription.entity';
import { InvoiceLineItem, LineItemType } from '../entities/invoice.entity';

export interface ProrationResult {
  unusedCurrentPlanCents: number; // Credit owed to customer for remainder of period
  costNewPlanCents: number;       // Charge owed for remainder of period on new plan
  netAmountCents: number;         // Positive = customer pays now; Negative = customer receives credit
  remainingPeriodRatio: number;   // Ratio of remaining time [0.0, 1.0]
  periodTotalSeconds: number;
  remainingSeconds: number;
  lineItems: InvoiceLineItem[];
}

export class ProrationService {
  /**
   * Calculates high-precision per-second proration when upgrading or downgrading a subscription.
   */
  calculatePlanChangeProration(params: {
    subscription: SubscriptionAggregate;
    newPlan: SubscriptionPlan;
    changeTimestamp?: Date;
  }): ProrationResult {
    const changeTime = params.changeTimestamp ?? new Date();
    const periodStart = params.subscription.currentPeriodStart;
    const periodEnd = params.subscription.currentPeriodEnd;

    const totalPeriodMs = periodEnd.getTime() - periodStart.getTime();
    if (totalPeriodMs <= 0) {
      throw new Error('Invalid subscription period: periodEnd must be after periodStart');
    }

    const remainingMs = Math.max(0, periodEnd.getTime() - changeTime.getTime());
    const periodTotalSeconds = Math.floor(totalPeriodMs / 1000);
    const remainingSeconds = Math.floor(remainingMs / 1000);

    const remainingRatio = remainingSeconds / periodTotalSeconds;

    // Current plan cost for the cycle (base + extra seats)
    const currentBase = params.subscription.plan.basePriceCents;
    const currentExtraSeats = Math.max(0, params.subscription.seats - params.subscription.plan.includedSeats);
    const currentSeatsCost = currentExtraSeats * params.subscription.plan.perSeatPriceCents;
    const currentTotalPeriodCost = currentBase + currentSeatsCost;

    // Unused credit for current plan
    const unusedCurrentPlanCents = Math.round(currentTotalPeriodCost * remainingRatio);

    // New plan cost for remaining cycle
    const newBase = params.newPlan.basePriceCents;
    const newExtraSeats = Math.max(0, params.subscription.seats - params.newPlan.includedSeats);
    const newSeatsCost = newExtraSeats * params.newPlan.perSeatPriceCents;
    const newTotalPeriodCost = newBase + newSeatsCost;

    const costNewPlanCents = Math.round(newTotalPeriodCost * remainingRatio);

    const netAmountCents = costNewPlanCents - unusedCurrentPlanCents;

    const lineItems: InvoiceLineItem[] = [
      {
        lineId: `prorate_credit_${changeTime.getTime()}`,
        type: LineItemType.PRORATION_CREDIT,
        description: `Unused time on ${params.subscription.plan.name} (${Math.round(remainingRatio * 100)}% remaining)`,
        quantity: 1,
        unitPriceCents: -unusedCurrentPlanCents,
        subtotalCents: -unusedCurrentPlanCents,
        discountCents: 0,
        taxCents: 0,
        totalCents: -unusedCurrentPlanCents,
        periodStart: changeTime,
        periodEnd: periodEnd,
      },
      {
        lineId: `prorate_charge_${changeTime.getTime()}`,
        type: LineItemType.SUBSCRIPTION_BASE,
        description: `Remaining time on ${params.newPlan.name} (${Math.round(remainingRatio * 100)}% remaining)`,
        quantity: 1,
        unitPriceCents: costNewPlanCents,
        subtotalCents: costNewPlanCents,
        discountCents: 0,
        taxCents: 0,
        totalCents: costNewPlanCents,
        periodStart: changeTime,
        periodEnd: periodEnd,
      },
    ];

    return {
      unusedCurrentPlanCents,
      costNewPlanCents,
      netAmountCents,
      remainingPeriodRatio: remainingRatio,
      periodTotalSeconds,
      remainingSeconds,
      lineItems,
    };
  }

  /**
   * Calculates proration when adding or removing seats mid-cycle.
   */
  calculateSeatAdjustmentProration(params: {
    subscription: SubscriptionAggregate;
    newSeatCount: number;
    changeTimestamp?: Date;
  }): ProrationResult {
    const changeTime = params.changeTimestamp ?? new Date();
    const periodStart = params.subscription.currentPeriodStart;
    const periodEnd = params.subscription.currentPeriodEnd;

    const totalPeriodMs = periodEnd.getTime() - periodStart.getTime();
    const remainingMs = Math.max(0, periodEnd.getTime() - changeTime.getTime());
    const remainingRatio = remainingMs / totalPeriodMs;

    const currentSeats = params.subscription.seats;
    const diffSeats = params.newSeatCount - currentSeats;

    const perSeatCyclePrice = params.subscription.plan.perSeatPriceCents;
    const proratedPerSeat = Math.round(perSeatCyclePrice * remainingRatio);
    const netAmountCents = diffSeats * proratedPerSeat;

    const lineItems: InvoiceLineItem[] = [];
    if (diffSeats !== 0) {
      lineItems.push({
        lineId: `seat_adj_${changeTime.getTime()}`,
        type: LineItemType.SEAT_OVERAGE,
        description: `${diffSeats > 0 ? 'Added' : 'Removed'} ${Math.abs(diffSeats)} seats for remaining period`,
        quantity: diffSeats,
        unitPriceCents: proratedPerSeat,
        subtotalCents: netAmountCents,
        discountCents: 0,
        taxCents: 0,
        totalCents: netAmountCents,
        periodStart: changeTime,
        periodEnd: periodEnd,
      });
    }

    return {
      unusedCurrentPlanCents: diffSeats < 0 ? Math.abs(netAmountCents) : 0,
      costNewPlanCents: diffSeats > 0 ? netAmountCents : 0,
      netAmountCents,
      remainingPeriodRatio: remainingRatio,
      periodTotalSeconds: Math.floor(totalPeriodMs / 1000),
      remainingSeconds: Math.floor(remainingMs / 1000),
      lineItems,
    };
  }
}
