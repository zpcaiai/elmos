import { Injectable, BadRequestException } from '@nestjs/common';
import {
  ASC606ModificationAccountingTreatment,
  ContractPerformanceObligation,
  ContractModificationAmendment,
  ModificationAccountingDecision,
} from '../entities/contract-modification.entity';

@Injectable()
export class ASC606ModificationService {
  /**
   * Evaluates contract amendment characteristics against ASC 606-10-25-12/13 decision criteria.
   */
  public evaluateTreatment(
    amendment: ContractModificationAmendment,
    existingObligations: ContractPerformanceObligation[]
  ): ASC606ModificationAccountingTreatment {
    if (!amendment.addedObligations || amendment.addedObligations.length === 0) {
      if (amendment.priceConcessionOnRemainingCents !== 0) {
        // Pure price concession on existing remaining services
        const anyNonDistinct = existingObligations.some(o => !o.isDistinct);
        return anyNonDistinct
          ? ASC606ModificationAccountingTreatment.CUMULATIVE_CATCH_UP
          : ASC606ModificationAccountingTreatment.PROSPECTIVE_REALLOCATION;
      }
      throw new BadRequestException('Contract amendment must provide additional obligations or price adjustments');
    }

    const allAddedAreDistinct = amendment.addedObligations.every(o => o.isDistinct);
    const allRemainingAreDistinct = existingObligations
      .filter(o => o.remainingPeriodMonths > 0)
      .every(o => o.isDistinct);

    // Criteria 1: Distinct goods/services at Standalone Selling Price (SSP)
    const allAtSSP = amendment.addedObligations.every(
      o => o.isAtStandaloneSellingPrice && o.offeredPriceCents === o.standaloneSellingPriceCents
    );

    if (allAddedAreDistinct && allAtSSP && amendment.priceConcessionOnRemainingCents === 0) {
      return ASC606ModificationAccountingTreatment.SEPARATE_CONTRACT;
    }

    // Criteria 2: Goods are distinct, but consideration does not reflect standalone selling prices
    if (allAddedAreDistinct && allRemainingAreDistinct) {
      return ASC606ModificationAccountingTreatment.PROSPECTIVE_REALLOCATION;
    }

    // Criteria 3: Goods are NOT distinct (bundled custom implementation / interdependent milestones)
    return ASC606ModificationAccountingTreatment.CUMULATIVE_CATCH_UP;
  }

  /**
   * Applies the determined ASC 606 accounting treatment and recalculates revenue schedules.
   */
  public applyModification(
    amendment: ContractModificationAmendment,
    existingObligations: ContractPerformanceObligation[]
  ): ModificationAccountingDecision {
    const treatment = this.evaluateTreatment(amendment, existingObligations);

    switch (treatment) {
      case ASC606ModificationAccountingTreatment.SEPARATE_CONTRACT:
        return this.processSeparateContract(amendment, existingObligations);

      case ASC606ModificationAccountingTreatment.PROSPECTIVE_REALLOCATION:
        return this.processProspectiveReallocation(amendment, existingObligations);

      case ASC606ModificationAccountingTreatment.CUMULATIVE_CATCH_UP:
        return this.processCumulativeCatchUp(amendment, existingObligations);

      default:
        throw new BadRequestException(`Unsupported ASC 606 treatment: ${treatment}`);
    }
  }

  private processSeparateContract(
    amendment: ContractModificationAmendment,
    existingObligations: ContractPerformanceObligation[]
  ): ModificationAccountingDecision {
    const revised: ContractPerformanceObligation[] = [...existingObligations];

    for (let i = 0; i < amendment.addedObligations.length; i++) {
      const added = amendment.addedObligations[i];
      revised.push({
        obligationId: `OBL-NEW-${amendment.amendmentId}-${i + 1}`,
        name: added.name,
        isDistinct: true,
        standaloneSellingPriceCents: added.standaloneSellingPriceCents,
        allocatedTransactionPriceCents: added.offeredPriceCents,
        recognizedRevenueCents: 0,
        deferredRevenueCents: added.offeredPriceCents,
        progressPercentage: 0.0,
        totalPeriodMonths: added.periodMonths,
        remainingPeriodMonths: added.periodMonths,
      });
    }

    const totalValue = revised.reduce((sum, o) => sum + o.allocatedTransactionPriceCents, 0);
    const futureMonthly = revised.reduce((sum, o) => {
      return o.remainingPeriodMonths > 0
        ? sum + Math.round(o.deferredRevenueCents / o.remainingPeriodMonths)
        : sum;
    }, 0);

    return {
      amendmentId: amendment.amendmentId,
      treatment: ASC606ModificationAccountingTreatment.SEPARATE_CONTRACT,
      rationale: 'Added distinct goods/services at standalone selling price accounted for as separate independent contract.',
      cumulativeCatchUpAdjustmentCents: 0,
      revisedObligations: revised,
      totalRevisedContractValueCents: totalValue,
      futureRatableMonthlyRevenueCents: futureMonthly,
    };
  }

  private processProspectiveReallocation(
    amendment: ContractModificationAmendment,
    existingObligations: ContractPerformanceObligation[]
  ): ModificationAccountingDecision {
    // 1. Existing recognized revenue is locked and preserved
    const previouslyRecognized = existingObligations.reduce((sum, o) => sum + o.recognizedRevenueCents, 0);

    // 2. Compute pool of remaining unallocated consideration:
    // Unrecognized consideration from existing + additional consideration from amendment - concessions
    const existingDeferredPool = existingObligations.reduce((sum, o) => sum + o.deferredRevenueCents, 0);
    const additionalPool = amendment.additionalConsiderationCents - amendment.priceConcessionOnRemainingCents;
    const remainingConsiderationPool = existingDeferredPool + additionalPool;

    // 3. Collect active obligations eligible for reallocation (remaining period > 0)
    const activeExisting = existingObligations.filter(o => o.remainingPeriodMonths > 0);
    const newItems = amendment.addedObligations;

    // Calculate relative SSP for remaining obligations
    const totalRemainingSSP =
      activeExisting.reduce((sum, o) => sum + o.standaloneSellingPriceCents, 0) +
      newItems.reduce((sum, o) => sum + o.standaloneSellingPriceCents, 0);

    const revised: ContractPerformanceObligation[] = [];

    // Keep fully fulfilled obligations as-is
    for (const obl of existingObligations) {
      if (obl.remainingPeriodMonths === 0) {
        revised.push({ ...obl });
      }
    }

    // Allocate remaining consideration pool across active existing obligations
    let allocatedSoFar = 0;
    for (const obl of activeExisting) {
      const share = obl.standaloneSellingPriceCents / totalRemainingSSP;
      const allocatedPortion = Math.round(remainingConsiderationPool * share);
      allocatedSoFar += allocatedPortion;

      revised.push({
        ...obl,
        allocatedTransactionPriceCents: obl.recognizedRevenueCents + allocatedPortion,
        deferredRevenueCents: allocatedPortion,
      });
    }

    // Allocate remaining consideration pool to newly added obligations
    for (let i = 0; i < newItems.length; i++) {
      const item = newItems[i];
      const isLast = i === newItems.length - 1;
      const share = item.standaloneSellingPriceCents / totalRemainingSSP;
      // Reconcile exact penny difference on last item
      const allocatedPortion = isLast
        ? remainingConsiderationPool - allocatedSoFar
        : Math.round(remainingConsiderationPool * share);
      allocatedSoFar += allocatedPortion;

      revised.push({
        obligationId: `OBL-MOD-${amendment.amendmentId}-${i + 1}`,
        name: item.name,
        isDistinct: true,
        standaloneSellingPriceCents: item.standaloneSellingPriceCents,
        allocatedTransactionPriceCents: allocatedPortion,
        recognizedRevenueCents: 0,
        deferredRevenueCents: allocatedPortion,
        progressPercentage: 0.0,
        totalPeriodMonths: item.periodMonths,
        remainingPeriodMonths: item.periodMonths,
      });
    }

    const totalContractValue = previouslyRecognized + remainingConsiderationPool;
    const futureMonthly = revised.reduce((sum, o) => {
      return o.remainingPeriodMonths > 0
        ? sum + Math.round(o.deferredRevenueCents / o.remainingPeriodMonths)
        : sum;
    }, 0);

    return {
      amendmentId: amendment.amendmentId,
      treatment: ASC606ModificationAccountingTreatment.PROSPECTIVE_REALLOCATION,
      rationale: 'Remaining goods/services are distinct but not priced at SSP; prospective reallocation of remaining consideration applied.',
      cumulativeCatchUpAdjustmentCents: 0,
      revisedObligations: revised,
      totalRevisedContractValueCents: totalContractValue,
      futureRatableMonthlyRevenueCents: futureMonthly,
    };
  }

  private processCumulativeCatchUp(
    amendment: ContractModificationAmendment,
    existingObligations: ContractPerformanceObligation[]
  ): ModificationAccountingDecision {
    // Goods/services are part of a single partially satisfied performance obligation
    const originalTotalAllocated = existingObligations.reduce((sum, o) => sum + o.allocatedTransactionPriceCents, 0);
    const previouslyRecognized = existingObligations.reduce((sum, o) => sum + o.recognizedRevenueCents, 0);

    const revisedTotalConsideration = originalTotalAllocated + amendment.additionalConsiderationCents - amendment.priceConcessionOnRemainingCents;

    // Average progress percentage weighted by original allocated price
    const overallProgress = originalTotalAllocated > 0
      ? previouslyRecognized / originalTotalAllocated
      : 0.0;

    // Cumulative revenue that should be recognized to date under new contract value
    const revisedCumulativeRecognized = Math.round(revisedTotalConsideration * overallProgress);
    const cumulativeAdjustmentCents = revisedCumulativeRecognized - previouslyRecognized;

    const revised: ContractPerformanceObligation[] = existingObligations.map(o => {
      const shareOfTotal = originalTotalAllocated > 0 ? o.allocatedTransactionPriceCents / originalTotalAllocated : 1.0;
      const revisedAllocated = Math.round(revisedTotalConsideration * shareOfTotal);
      const newRecognized = Math.round(revisedAllocated * overallProgress);
      return {
        ...o,
        allocatedTransactionPriceCents: revisedAllocated,
        recognizedRevenueCents: newRecognized,
        deferredRevenueCents: revisedAllocated - newRecognized,
      };
    });

    const futureMonthly = revised.reduce((sum, o) => {
      return o.remainingPeriodMonths > 0
        ? sum + Math.round(o.deferredRevenueCents / o.remainingPeriodMonths)
        : sum;
    }, 0);

    return {
      amendmentId: amendment.amendmentId,
      treatment: ASC606ModificationAccountingTreatment.CUMULATIVE_CATCH_UP,
      rationale: 'Remaining goods/services are not distinct; cumulative catch-up adjustment recognized immediately in current period.',
      cumulativeCatchUpAdjustmentCents: cumulativeAdjustmentCents,
      revisedObligations: revised,
      totalRevisedContractValueCents: revisedTotalConsideration,
      futureRatableMonthlyRevenueCents: futureMonthly,
    };
  }
}
