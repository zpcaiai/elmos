import { Injectable, BadRequestException } from '@nestjs/common';
import {
  PrepaidCreditGrant,
  DrawdownResult,
  DrawdownTransaction,
} from '../entities/prepaid-credit-grant.entity';

@Injectable()
export class CreditDrawdownWaterfallService {
  /**
   * Applies the multi-bucket FIFO/priority credit drawdown waterfall to cover usage charges.
   */
  public executeDrawdown(
    customerId: string,
    chargeAmountCents: number,
    metricCode: string,
    grants: PrepaidCreditGrant[],
    asOfDate: Date = new Date()
  ): DrawdownResult {
    if (chargeAmountCents < 0) {
      throw new BadRequestException(`Drawdown charge amount cannot be negative: ${chargeAmountCents}`);
    }

    if (chargeAmountCents === 0) {
      const remainingTotal = grants.reduce((sum, g) => sum + g.remainingCreditsCents, 0);
      return {
        customerId,
        totalRequestedCents: 0,
        totalDrawnCents: 0,
        uncoveredDeficitCents: 0,
        transactions: [],
        exhaustedGrantIds: [],
        remainingTotalCreditsCents: remainingTotal,
      };
    }

    // 1. Filter eligible grants
    const eligibleGrants = grants.filter(g => {
      // Must have positive remaining balance
      if (g.remainingCreditsCents <= 0) return false;
      // Must not be expired
      if (g.expiresAt !== null && g.expiresAt.getTime() <= asOfDate.getTime()) return false;
      // Must cover the metric code if restrictions are defined
      if (g.applicableMetricCodes && g.applicableMetricCodes.length > 0) {
        if (!g.applicableMetricCodes.includes(metricCode)) return false;
      }
      return true;
    });

    // 2. Sort by priority rank ascending, then earliest expiration date ascending
    eligibleGrants.sort((a, b) => {
      if (a.priorityRank !== b.priorityRank) {
        return a.priorityRank - b.priorityRank;
      }
      const expA = a.expiresAt ? a.expiresAt.getTime() : Infinity;
      const expB = b.expiresAt ? b.expiresAt.getTime() : Infinity;
      if (expA !== expB) {
        return expA - expB;
      }
      return a.grantId.localeCompare(b.grantId);
    });

    let remainingChargeCents = chargeAmountCents;
    let totalDrawnCents = 0;
    const transactions: DrawdownTransaction[] = [];
    const exhaustedGrantIds: string[] = [];

    for (const grant of eligibleGrants) {
      if (remainingChargeCents <= 0) break;

      const drawFromThisGrant = Math.min(grant.remainingCreditsCents, remainingChargeCents);
      grant.remainingCreditsCents -= drawFromThisGrant;
      totalDrawnCents += drawFromThisGrant;
      remainingChargeCents -= drawFromThisGrant;

      transactions.push({
        transactionId: `TX-DRAW-${grant.grantId}-${Date.now()}-${transactions.length + 1}`,
        grantId: grant.grantId,
        bucketType: grant.bucketType,
        amountDrawnCents: drawFromThisGrant,
        drawnAt: asOfDate,
        remainingAfterCents: grant.remainingCreditsCents,
      });

      if (grant.remainingCreditsCents === 0) {
        exhaustedGrantIds.push(grant.grantId);
      }
    }

    const remainingTotalCredits = grants.reduce((sum, g) => sum + g.remainingCreditsCents, 0);

    return {
      customerId,
      totalRequestedCents: chargeAmountCents,
      totalDrawnCents,
      uncoveredDeficitCents: remainingChargeCents,
      transactions,
      exhaustedGrantIds,
      remainingTotalCreditsCents: remainingTotalCredits,
    };
  }
}
