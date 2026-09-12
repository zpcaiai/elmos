/**
 * Partner & Affiliate Commission Calculation Engine
 *
 * Implements precise calculation of partner rev-share, first-year bounties,
 * discount coupon deductions, and refund/chargeback clawbacks.
 */

import { Injectable } from '@nestjs/common';
import { PartnerAgreement, CommissionModelType } from '../entities/partner-agreement.entity';

export interface InvoiceCommissionEvent {
  invoiceId: string;
  customerId: string;
  invoiceSubtotal: number; // Software net amount (excluding tax and pass-through)
  taxAmount: number;
  isFirstPayment: boolean;
  paymentDate: Date;
}

export interface CalculatedCommission {
  payoutId: string;
  partnerId: string;
  invoiceId: string;
  commissionableBase: number;
  commissionRate: number;
  revShareAmount: number;
  bountyAmount: number;
  totalCommissionEarned: number;
  calculatedAt: Date;
}

export interface ClawbackCalculation {
  clawbackId: string;
  originalPayoutId: string;
  partnerId: string;
  refundAmount: number;
  clawbackAmount: number;
  reason: string;
  calculatedAt: Date;
}

@Injectable()
export class CommissionCalculatorService {
  private earnedCommissions: Map<string, CalculatedCommission> = new Map();

  /**
   * Calculates commission for a settled customer invoice under an active partner agreement
   */
  public calculateInvoiceCommission(
    agreement: PartnerAgreement,
    event: InvoiceCommissionEvent,
    partnerMonthlyVolume: number = 0
  ): CalculatedCommission {
    if (!agreement.isCustomerReferred(event.customerId)) {
      throw new Error(`Customer ${event.customerId} is not registered under partner ${agreement.partnerName}`);
    }

    const commissionableBase = Math.round(event.invoiceSubtotal * 100) / 100;
    let rate = 0;
    let revShare = 0;
    let bounty = 0;

    switch (agreement.modelType) {
      case CommissionModelType.FLAT_PERCENTAGE:
        rate = agreement.flatRatePercentage;
        revShare = Math.round(commissionableBase * rate * 100) / 100;
        break;

      case CommissionModelType.TIERED_MRR:
        // Find tier corresponding to current month aggregate volume
        const matchingTier = agreement.tiers.find(
          t => partnerMonthlyVolume >= t.minMonthlyVolume && partnerMonthlyVolume < t.maxMonthlyVolume
        );
        rate = matchingTier ? matchingTier.commissionRate : agreement.flatRatePercentage;
        revShare = Math.round(commissionableBase * rate * 100) / 100;
        break;

      case CommissionModelType.ONE_TIME_BOUNTY:
        if (event.isFirstPayment) {
          bounty = agreement.bountyAmount;
        }
        break;

      case CommissionModelType.HYBRID:
        rate = agreement.flatRatePercentage;
        revShare = Math.round(commissionableBase * rate * 100) / 100;
        if (event.isFirstPayment) {
          bounty = agreement.bountyAmount;
        }
        break;
    }

    const total = Math.round((revShare + bounty) * 100) / 100;
    const result: CalculatedCommission = {
      payoutId: `payout-${Date.now()}-${event.invoiceId}`,
      partnerId: agreement.partnerId,
      invoiceId: event.invoiceId,
      commissionableBase,
      commissionRate: rate,
      revShareAmount: revShare,
      bountyAmount: bounty,
      totalCommissionEarned: total,
      calculatedAt: new Date(),
    };

    this.earnedCommissions.set(event.invoiceId, result);
    return result;
  }

  /**
   * Computes commission clawback when an invoice is refunded or disputed
   */
  public calculateClawback(params: {
    agreement: PartnerAgreement;
    invoiceId: string;
    refundAmount: number;
    refundDate: Date;
    isDispute?: boolean;
  }): ClawbackCalculation | null {
    const prior = this.earnedCommissions.get(params.invoiceId);
    if (!prior) return null;

    const daysElapsed = Math.round((params.refundDate.getTime() - prior.calculatedAt.getTime()) / (24 * 60 * 60 * 1000));
    const rule = params.agreement.clawbackRule;

    if (daysElapsed > rule.clawbackWindowDays) {
      // Past clawback liability window
      return null;
    }

    // Proportionate or full clawback
    let clawbackAmount = 0;
    if (params.isDispute && rule.fullClawbackOnChargeback) {
      clawbackAmount = prior.totalCommissionEarned;
    } else {
      const refundRatio = prior.commissionableBase > 0 ? Math.min(1.0, params.refundAmount / prior.commissionableBase) : 1.0;
      clawbackAmount = Math.round(prior.totalCommissionEarned * refundRatio * 100) / 100;
    }

    return {
      clawbackId: `clawback-${Date.now()}-${prior.payoutId}`,
      originalPayoutId: prior.payoutId,
      partnerId: params.agreement.partnerId,
      refundAmount: params.refundAmount,
      clawbackAmount,
      reason: params.isDispute ? 'CHARGEBACK_CLAWBACK' : 'REFUND_PROPORTIONAL_CLAWBACK',
      calculatedAt: new Date(),
    };
  }
}
