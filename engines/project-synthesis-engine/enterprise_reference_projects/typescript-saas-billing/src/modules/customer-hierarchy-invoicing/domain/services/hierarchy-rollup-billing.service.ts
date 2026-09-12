import { Injectable } from '@nestjs/common';
import {
  BillingResponsibility,
  CustomerHierarchyNode,
  ConsolidatedGroupInvoice,
  SharedCreditDrawdownResult,
  SubsidiaryBillingLine,
} from '../entities/hierarchy-node.entity';

export interface RawSubsidiaryUsageInput {
  lineId: string;
  subsidiaryCustomerId: string;
  serviceDescription: string;
  unitsConsumed: number;
  unitRateUsd: number;
}

export interface VolumeDiscountTier {
  tierName: string;
  minimumUnits: number;
  discountRate: number; // e.g. 0.15 = 15%
}

@Injectable()
export class HierarchyRollupBillingService {
  private readonly volumeDiscountTiers: VolumeDiscountTier[] = [
    { tierName: 'Tier 3 Strategic Global', minimumUnits: 100_000, discountRate: 0.25 },
    { tierName: 'Tier 2 Global Enterprise', minimumUnits: 50_000, discountRate: 0.15 },
    { tierName: 'Tier 1 Regional Enterprise', minimumUnits: 10_000, discountRate: 0.10 },
    { tierName: 'Standard Base Tier', minimumUnits: 0, discountRate: 0.00 },
  ];

  public resolveGroupVolumeDiscount(totalUnits: number): VolumeDiscountTier {
    for (const tier of this.volumeDiscountTiers) {
      if (totalUnits >= tier.minimumUnits) {
        return tier;
      }
    }
    return this.volumeDiscountTiers[this.volumeDiscountTiers.length - 1];
  }

  /**
   * Consolidates multi-entity subsidiary usage into an aggregated enterprise group invoice.
   * Leverages global volume pooling while respecting decentralized, centralized, or hybrid split payment rules.
   */
  public generateConsolidatedGroupInvoice(
    rootCustomer: CustomerHierarchyNode,
    allNodesInHierarchy: CustomerHierarchyNode[],
    rawUsageLines: RawSubsidiaryUsageInput[],
    billingPeriod: string
  ): ConsolidatedGroupInvoice {
    const nodeMap = new Map<string, CustomerHierarchyNode>();
    for (const node of allNodesInHierarchy) {
      nodeMap.set(node.customerId, node);
    }

    if (!nodeMap.has(rootCustomer.customerId)) {
      nodeMap.set(rootCustomer.customerId, rootCustomer);
    }

    // 1. Calculate Total Group Units Consumed
    let totalGroupUnits = 0;
    let totalGrossCharges = 0;

    for (const input of rawUsageLines) {
      totalGroupUnits += input.unitsConsumed;
      totalGrossCharges += input.unitsConsumed * input.unitRateUsd;
    }

    // 2. Resolve Global Volume Discount Tier for the entire conglomerate
    const tier = this.resolveGroupVolumeDiscount(totalGroupUnits);
    const discountRate = tier.discountRate;

    // 3. Process each line item with volume discount and billing responsibility split
    const processedLines: SubsidiaryBillingLine[] = [];
    const perSubsidiarySummaries = new Map<string, {
      grossAmountUsd: number;
      discountedAmountUsd: number;
      parentShareUsd: number;
      selfShareUsd: number;
    }>();

    let totalBilledToParent = 0;
    let totalBilledToSubsidiaries = 0;
    let totalDiscountAmount = 0;

    for (const raw of rawUsageLines) {
      const node = nodeMap.get(raw.subsidiaryCustomerId);
      if (!node) {
        throw new Error(`Subsidiary customer ${raw.subsidiaryCustomerId} not found in registered hierarchy`);
      }

      const lineGross = Number((raw.unitsConsumed * raw.unitRateUsd).toFixed(2));
      const lineDiscount = Number((lineGross * discountRate).toFixed(2));
      const lineNet = Number((lineGross - lineDiscount).toFixed(2));

      totalDiscountAmount += lineDiscount;

      // Determine payment responsibility
      let parentShare = 0;
      let selfShare = 0;

      switch (node.billingResponsibility) {
        case 'CENTRALIZED_PARENT':
          parentShare = lineNet;
          selfShare = 0;
          break;

        case 'DECENTRALIZED_SELF':
          parentShare = 0;
          selfShare = lineNet;
          break;

        case 'HYBRID_SPLIT': {
          const split = node.splitRule || { parentPercentage: 0.5, subsidiaryPercentage: 0.5 };
          parentShare = Number((lineNet * split.parentPercentage).toFixed(2));
          selfShare = Number((lineNet - parentShare).toFixed(2)); // Exact remainder preserves cent conservation
          break;
        }
      }

      totalBilledToParent += parentShare;
      totalBilledToSubsidiaries += selfShare;

      const line: SubsidiaryBillingLine = {
        lineId: raw.lineId,
        subsidiaryCustomerId: node.customerId,
        subsidiaryName: node.legalEntityName,
        serviceDescription: raw.serviceDescription,
        unitsConsumed: raw.unitsConsumed,
        unadjustedAmountUsd: lineGross,
        effectiveVolumeDiscountRate: discountRate,
        discountedAmountUsd: lineNet,
        allocatedToParentUsd: parentShare,
        allocatedToSubsidiaryUsd: selfShare,
      };
      processedLines.push(line);

      // Accumulate per-subsidiary summary
      const existing = perSubsidiarySummaries.get(node.customerId) || {
        grossAmountUsd: 0,
        discountedAmountUsd: 0,
        parentShareUsd: 0,
        selfShareUsd: 0,
      };

      existing.grossAmountUsd = Number((existing.grossAmountUsd + lineGross).toFixed(2));
      existing.discountedAmountUsd = Number((existing.discountedAmountUsd + lineNet).toFixed(2));
      existing.parentShareUsd = Number((existing.parentShareUsd + parentShare).toFixed(2));
      existing.selfShareUsd = Number((existing.selfShareUsd + selfShare).toFixed(2));
      perSubsidiarySummaries.set(node.customerId, existing);
    }

    const netCharges = Number((totalGrossCharges - totalDiscountAmount).toFixed(2));

    return {
      invoiceId: `GRP-INV-${rootCustomer.customerId}-${billingPeriod}`,
      rootParentCustomerId: rootCustomer.customerId,
      rootParentEntityName: rootCustomer.legalEntityName,
      billingPeriod,
      totalGroupUnitsConsumed: totalGroupUnits,
      groupVolumeDiscountTierName: tier.tierName,
      groupVolumeDiscountRate: discountRate,
      totalGrossChargesUsd: Number(totalGrossCharges.toFixed(2)),
      totalGroupVolumeDiscountUsd: Number(totalDiscountAmount.toFixed(2)),
      totalNetChargesUsd: netCharges,
      totalBilledToParentHqUsd: Number(totalBilledToParent.toFixed(2)),
      totalBilledDirectToSubsidiariesUsd: Number(totalBilledToSubsidiaries.toFixed(2)),
      subsidiaryLineItems: processedLines,
      perSubsidiarySummaries,
    };
  }

  /**
   * Draws down enterprise prepaid credits from a pooled parent account across subsidiary requests.
   * Enforces optional subsidiary quota caps and preserves positive remaining balances.
   */
  public drawdownSharedCreditPool(
    openingPoolBalanceUsd: number,
    requests: Array<{ subsidiaryId: string; requestedAmountUsd: number; maxQuotaUsd?: number }>
  ): SharedCreditDrawdownResult {
    let currentBalance = openingPoolBalanceUsd;
    let totalDrawn = 0;
    const allocations = new Map<string, number>();

    for (const req of requests) {
      if (currentBalance <= 0) {
        allocations.set(req.subsidiaryId, 0);
        continue;
      }

      let allowable = req.requestedAmountUsd;
      if (req.maxQuotaUsd !== undefined && req.maxQuotaUsd < allowable) {
        allowable = req.maxQuotaUsd;
      }

      const drawn = Math.min(currentBalance, allowable);
      allocations.set(req.subsidiaryId, Number(drawn.toFixed(2)));
      currentBalance = Number((currentBalance - drawn).toFixed(2));
      totalDrawn = Number((totalDrawn + drawn).toFixed(2));
    }

    let status: 'FULLY_SATISFIED' | 'PARTIALLY_SATISFIED' | 'POOL_EXHAUSTED';
    const totalRequested = requests.reduce((acc, r) => acc + r.requestedAmountUsd, 0);

    if (totalDrawn >= totalRequested) {
      status = 'FULLY_SATISFIED';
    } else if (currentBalance === 0) {
      status = 'POOL_EXHAUSTED';
    } else {
      status = 'PARTIALLY_SATISFIED';
    }

    return {
      creditPoolOpeningBalanceUsd: openingPoolBalanceUsd,
      totalDrawnUsd: totalDrawn,
      creditPoolClosingBalanceUsd: currentBalance,
      subsidiaryAllocations: allocations,
      exhaustionStatus: status,
    };
  }
}
