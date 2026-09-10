export enum SubscriptionStatus {
  TRIALING = 'TRIALING',
  ACTIVE = 'ACTIVE',
  PAST_DUE = 'PAST_DUE',
  PAUSED = 'PAUSED',
  CANCELED = 'CANCELED',
  EXPIRED = 'EXPIRED',
}

export enum BillingCycle {
  MONTHLY = 'MONTHLY',
  QUARTERLY = 'QUARTERLY',
  ANNUAL = 'ANNUAL',
}

export interface PlanFeature {
  featureKey: string;
  name: string;
  limit: number | 'UNLIMITED';
}

export interface SubscriptionPlan {
  planId: string;
  code: string;
  name: string;
  billingCycle: BillingCycle;
  basePriceCents: number;
  includedSeats: number;
  perSeatPriceCents: number;
  features: PlanFeature[];
  trialDays: number;
}

export class SubscriptionAggregate {
  subscriptionId: string;
  tenantId: string;
  customerId: string;
  plan: SubscriptionPlan;
  status: SubscriptionStatus;
  currentPeriodStart: Date;
  currentPeriodEnd: Date;
  trialEnd?: Date;
  cancelAtPeriodEnd: boolean;
  canceledAt?: Date;
  seats: number;
  metadata: Record<string, unknown>;
  createdAt: Date;
  updatedAt: Date;

  constructor(params: {
    subscriptionId: string;
    tenantId: string;
    customerId: string;
    plan: SubscriptionPlan;
    status?: SubscriptionStatus;
    currentPeriodStart?: Date;
    currentPeriodEnd?: Date;
    trialEnd?: Date;
    cancelAtPeriodEnd?: boolean;
    seats?: number;
    metadata?: Record<string, unknown>;
  }) {
    const now = new Date();
    this.subscriptionId = params.subscriptionId;
    this.tenantId = params.tenantId;
    this.customerId = params.customerId;
    this.plan = params.plan;
    this.status = params.status ?? (params.plan.trialDays > 0 ? SubscriptionStatus.TRIALING : SubscriptionStatus.ACTIVE);
    this.currentPeriodStart = params.currentPeriodStart ?? now;
    this.currentPeriodEnd = params.currentPeriodEnd ?? this.computePeriodEnd(this.currentPeriodStart, params.plan.billingCycle);
    this.trialEnd = params.trialEnd ?? (params.plan.trialDays > 0 ? new Date(now.getTime() + params.plan.trialDays * 86400000) : undefined);
    this.cancelAtPeriodEnd = params.cancelAtPeriodEnd ?? false;
    this.seats = params.seats ?? params.plan.includedSeats;
    this.metadata = params.metadata ?? {};
    this.createdAt = now;
    this.updatedAt = now;
  }

  private computePeriodEnd(start: Date, cycle: BillingCycle): Date {
    const end = new Date(start);
    switch (cycle) {
      case BillingCycle.MONTHLY:
        end.setMonth(end.getMonth() + 1);
        break;
      case BillingCycle.QUARTERLY:
        end.setMonth(end.getMonth() + 3);
        break;
      case BillingCycle.ANNUAL:
        end.setFullYear(end.getFullYear() + 1);
        break;
    }
    return end;
  }

  activate(): void {
    if (this.status === SubscriptionStatus.CANCELED || this.status === SubscriptionStatus.EXPIRED) {
      throw new Error(`Cannot activate subscription in status ${this.status}`);
    }
    this.status = SubscriptionStatus.ACTIVE;
    this.updatedAt = new Date();
  }

  markPastDue(): void {
    if (this.status === SubscriptionStatus.ACTIVE || this.status === SubscriptionStatus.TRIALING) {
      this.status = SubscriptionStatus.PAST_DUE;
      this.updatedAt = new Date();
    }
  }

  pause(): void {
    if (this.status !== SubscriptionStatus.ACTIVE) {
      throw new Error(`Only active subscriptions can be paused (current: ${this.status})`);
    }
    this.status = SubscriptionStatus.PAUSED;
    this.updatedAt = new Date();
  }

  resume(): void {
    if (this.status !== SubscriptionStatus.PAUSED) {
      throw new Error(`Only paused subscriptions can be resumed (current: ${this.status})`);
    }
    this.status = SubscriptionStatus.ACTIVE;
    this.updatedAt = new Date();
  }

  cancel(immediately = false): void {
    const now = new Date();
    if (immediately) {
      this.status = SubscriptionStatus.CANCELED;
      this.canceledAt = now;
      this.cancelAtPeriodEnd = false;
    } else {
      this.cancelAtPeriodEnd = true;
    }
    this.updatedAt = now;
  }

  updateSeats(newSeatCount: number): void {
    if (newSeatCount < this.plan.includedSeats) {
      throw new Error(`Seat count cannot be below plan included seats (${this.plan.includedSeats})`);
    }
    this.seats = newSeatCount;
    this.updatedAt = new Date();
  }

  changePlan(newPlan: SubscriptionPlan): void {
    this.plan = newPlan;
    if (this.seats < newPlan.includedSeats) {
      this.seats = newPlan.includedSeats;
    }
    this.currentPeriodEnd = this.computePeriodEnd(this.currentPeriodStart, newPlan.billingCycle);
    this.updatedAt = new Date();
  }

  isEntitled(featureKey: string): boolean {
    if (this.status !== SubscriptionStatus.ACTIVE && this.status !== SubscriptionStatus.TRIALING) {
      return false;
    }
    return this.plan.features.some((f) => f.featureKey === featureKey);
  }

  getFeatureLimit(featureKey: string): number | 'UNLIMITED' {
    const feat = this.plan.features.find((f) => f.featureKey === featureKey);
    return feat ? feat.limit : 0;
  }
}
