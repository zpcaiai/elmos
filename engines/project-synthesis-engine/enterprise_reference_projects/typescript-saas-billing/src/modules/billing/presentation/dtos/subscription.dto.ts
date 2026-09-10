import { BillingCycle } from '../../domain/entities/subscription.entity';

export class CreateSubscriptionDto {
  customerId!: string;
  planId!: string;
  planCode!: string;
  planName!: string;
  billingCycle!: BillingCycle;
  basePriceCents!: number;
  includedSeats!: number;
  perSeatPriceCents!: number;
  initialSeats?: number;
}

export class UpgradePlanDto {
  newPlanId!: string;
  newPlanCode!: string;
  newPlanName!: string;
  newBillingCycle!: BillingCycle;
  newBasePriceCents!: number;
  newIncludedSeats!: number;
  newPerSeatPriceCents!: number;
}

export class AdjustSeatsDto {
  newSeatCount!: number;
}
