/**
 * Partner & Affiliate Agreement Entities
 *
 * Models commercial relationships with agency partners, affiliates, and resellers:
 * - Flat Rev-Share (e.g. 20% ongoing recurring revenue)
 * - Tiered Performance Commission (0-$10k MRR: 15%, $10k-$50k: 20%, >$50k: 25%)
 * - First-Year Bounty (one-off cash bounty upon customer first payment)
 * - Clawback provisions (100% clawback if customer cancels or disputes within 90 days)
 */

export enum CommissionModelType {
  FLAT_PERCENTAGE = 'FLAT_PERCENTAGE',
  TIERED_MRR = 'TIERED_MRR',
  ONE_TIME_BOUNTY = 'ONE_TIME_BOUNTY',
  HYBRID = 'HYBRID',
}

export interface CommissionTier {
  minMonthlyVolume: number;
  maxMonthlyVolume: number;
  commissionRate: number; // e.g. 0.15 for 15%
}

export interface CommissionClawbackRule {
  clawbackWindowDays: number; // e.g. 90 days
  fullClawbackOnRefund: boolean;
  fullClawbackOnChargeback: boolean;
}

export enum PartnerStatus {
  APPLIED = 'APPLIED',
  ACTIVE = 'ACTIVE',
  SUSPENDED = 'SUSPENDED',
  TERMINATED = 'TERMINATED',
}

export class PartnerAgreement {
  public id: string;
  public partnerId: string;
  public partnerName: string;
  public modelType: CommissionModelType;
  public flatRatePercentage: number;
  public tiers: CommissionTier[];
  public bountyAmount: number;
  public clawbackRule: CommissionClawbackRule;
  public status: PartnerStatus;
  public referredCustomerIds: Set<string>;
  public createdAt: Date;
  public updatedAt: Date;

  constructor(params: {
    id: string;
    partnerId: string;
    partnerName: string;
    modelType: CommissionModelType;
    flatRatePercentage?: number;
    tiers?: CommissionTier[];
    bountyAmount?: number;
    clawbackRule?: CommissionClawbackRule;
  }) {
    this.id = params.id;
    this.partnerId = params.partnerId;
    this.partnerName = params.partnerName;
    this.modelType = params.modelType;
    this.flatRatePercentage = params.flatRatePercentage ?? 0.20;
    this.tiers = params.tiers ? [...params.tiers] : [];
    this.bountyAmount = params.bountyAmount ?? 0;
    this.clawbackRule = params.clawbackRule || {
      clawbackWindowDays: 90,
      fullClawbackOnRefund: true,
      fullClawbackOnChargeback: true,
    };
    this.status = PartnerStatus.ACTIVE;
    this.referredCustomerIds = new Set();
    this.createdAt = new Date();
    this.updatedAt = new Date();
  }

  public registerReferredCustomer(customerId: string): void {
    this.referredCustomerIds.add(customerId);
    this.updatedAt = new Date();
  }

  public isCustomerReferred(customerId: string): boolean {
    return this.referredCustomerIds.has(customerId);
  }
}
