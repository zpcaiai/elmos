import { Injectable, BadRequestException } from '@nestjs/common';
import {
  RatingMatrix,
  RatingResult,
  PricingModel,
  TierBreakdownItem,
  RatingTier,
} from '../entities/rating-matrix.entity';

@Injectable()
export class UsageRatingEngineService {
  /**
   * Evaluates and rates raw consumption volume against a contractual pricing matrix.
   */
  public rateUsage(
    units: number,
    matrix: RatingMatrix,
    options?: { surgeMultiplier?: number }
  ): RatingResult {
    if (units < 0) {
      throw new BadRequestException(`Usage units cannot be negative, got: ${units}`);
    }

    this.validateTierSanity(matrix.tiers);

    let ratedAmountCents = 0;
    const breakdown: TierBreakdownItem[] = [];

    switch (matrix.pricingModel) {
      case PricingModel.GRADUATED_TIERED:
        ratedAmountCents = this.calculateGraduatedTiered(units, matrix.tiers, breakdown);
        break;

      case PricingModel.VOLUME:
        ratedAmountCents = this.calculateVolumePricing(units, matrix.tiers, breakdown);
        break;

      case PricingModel.FLAT_FEE_WITH_OVERAGE:
        ratedAmountCents = this.calculateFlatFeeWithOverage(units, matrix.tiers, breakdown);
        break;

      case PricingModel.STAIR_STEP:
        ratedAmountCents = this.calculateStairStep(units, matrix.tiers, breakdown);
        break;

      default:
        throw new BadRequestException(`Unsupported pricing model: ${matrix.pricingModel}`);
    }

    // Apply surge multiplier if applicable
    const effectiveSurge = options?.surgeMultiplier ?? matrix.surgeMultiplier ?? 1.0;
    const surgeApplied = effectiveSurge > 1.0;
    if (surgeApplied) {
      ratedAmountCents = Math.round(ratedAmountCents * effectiveSurge);
    }

    // Evaluate minimum spend commitment shortfall
    let commitmentShortfallCents = 0;
    let totalBilledCents = ratedAmountCents;

    if (matrix.minimumCommitmentCents > 0 && ratedAmountCents < matrix.minimumCommitmentCents) {
      commitmentShortfallCents = matrix.minimumCommitmentCents - ratedAmountCents;
      totalBilledCents = matrix.minimumCommitmentCents;
    }

    return {
      matrixId: matrix.matrixId,
      metricCode: matrix.metricCode,
      currency: matrix.currency,
      rawUnits: units,
      ratedAmountCents,
      commitmentShortfallCents,
      totalBilledCents,
      breakdown,
      surgeApplied,
      surgeMultiplier: effectiveSurge,
    };
  }

  private calculateGraduatedTiered(
    units: number,
    tiers: RatingTier[],
    breakdown: TierBreakdownItem[]
  ): number {
    let remainingUnits = units;
    let totalCents = 0;

    for (const tier of tiers) {
      if (remainingUnits <= 0) break;

      const tierCapacity = tier.maxUnits !== null
        ? tier.maxUnits - tier.minUnits
        : Infinity;

      const unitsInThisTier = Math.min(remainingUnits, tierCapacity);
      const subtotalCents = Math.round(unitsInThisTier * tier.unitRateCents) + tier.flatFeeCents;

      breakdown.push({
        tierNumber: tier.tierNumber,
        unitsAllocated: unitsInThisTier,
        unitRateCents: tier.unitRateCents,
        flatFeeCents: tier.flatFeeCents,
        subtotalCents,
      });

      totalCents += subtotalCents;
      remainingUnits -= unitsInThisTier;
    }

    return totalCents;
  }

  private calculateVolumePricing(
    units: number,
    tiers: RatingTier[],
    breakdown: TierBreakdownItem[]
  ): number {
    // Find the single tier where total units fall
    let matchedTier = tiers[0];
    for (const tier of tiers) {
      if (units >= tier.minUnits && (tier.maxUnits === null || units <= tier.maxUnits)) {
        matchedTier = tier;
        break;
      }
    }

    const subtotalCents = Math.round(units * matchedTier.unitRateCents) + matchedTier.flatFeeCents;
    breakdown.push({
      tierNumber: matchedTier.tierNumber,
      unitsAllocated: units,
      unitRateCents: matchedTier.unitRateCents,
      flatFeeCents: matchedTier.flatFeeCents,
      subtotalCents,
    });

    return subtotalCents;
  }

  private calculateFlatFeeWithOverage(
    units: number,
    tiers: RatingTier[],
    breakdown: TierBreakdownItem[]
  ): number {
    const baseTier = tiers[0];
    const baseAllowance = baseTier.maxUnits ?? 0;
    const baseCost = baseTier.flatFeeCents;

    let overageCost = 0;
    const overageUnits = Math.max(0, units - baseAllowance);

    breakdown.push({
      tierNumber: baseTier.tierNumber,
      unitsAllocated: Math.min(units, baseAllowance),
      unitRateCents: 0,
      flatFeeCents: baseTier.flatFeeCents,
      subtotalCents: baseCost,
    });

    if (overageUnits > 0 && tiers.length > 1) {
      const overageTier = tiers[1];
      overageCost = Math.round(overageUnits * overageTier.unitRateCents);
      breakdown.push({
        tierNumber: overageTier.tierNumber,
        unitsAllocated: overageUnits,
        unitRateCents: overageTier.unitRateCents,
        flatFeeCents: 0,
        subtotalCents: overageCost,
      });
    }

    return baseCost + overageCost;
  }

  private calculateStairStep(
    units: number,
    tiers: RatingTier[],
    breakdown: TierBreakdownItem[]
  ): number {
    let matchedTier = tiers[0];
    for (const tier of tiers) {
      if (units >= tier.minUnits && (tier.maxUnits === null || units <= tier.maxUnits)) {
        matchedTier = tier;
        break;
      }
    }

    const subtotalCents = matchedTier.flatFeeCents;
    breakdown.push({
      tierNumber: matchedTier.tierNumber,
      unitsAllocated: units,
      unitRateCents: 0,
      flatFeeCents: matchedTier.flatFeeCents,
      subtotalCents,
    });

    return subtotalCents;
  }

  private validateTierSanity(tiers: RatingTier[]): void {
    if (!tiers || tiers.length === 0) {
      throw new BadRequestException('Rating matrix must define at least one tier');
    }

    for (let i = 0; i < tiers.length; i++) {
      const tier = tiers[i];
      if (tier.minUnits < 0) {
        throw new BadRequestException(`Tier ${tier.tierNumber} minUnits cannot be negative`);
      }
      if (tier.maxUnits !== null && tier.maxUnits < tier.minUnits) {
        throw new BadRequestException(`Tier ${tier.tierNumber} maxUnits cannot be less than minUnits`);
      }
      if (i > 0) {
        const prevTier = tiers[i - 1];
        if (prevTier.maxUnits !== null && tier.minUnits !== prevTier.maxUnits) {
          throw new BadRequestException(
            `Tier discontinuity: Tier ${tier.tierNumber} begins at ${tier.minUnits} but Tier ${prevTier.tierNumber} ends at ${prevTier.maxUnits}`
          );
        }
      }
    }
  }
}
