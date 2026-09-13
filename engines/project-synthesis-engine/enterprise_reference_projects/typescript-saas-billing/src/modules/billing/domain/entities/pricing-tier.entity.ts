export enum TierMode {
  VOLUME = 'VOLUME',           // Entire volume billed at tier reached
  GRADUATED = 'GRADUATED',     // Progressive tax-bracket style billing
  FLAT_FEE = 'FLAT_FEE',       // Flat fee per tier range
  PACKAGE = 'PACKAGE',         // Sold in discrete unit bundles
}

export interface TierBracket {
  upToUnits: number | 'UNLIMITED'; // e.g. 1000, 5000, or 'UNLIMITED'
  unitPriceCents: number;          // Minor units per single unit
  flatFeeCents: number;            // Fixed charge for entering or staying in tier
}

export interface TierCalculationResult {
  totalUnits: number;
  totalCostCents: number;
  mode: TierMode;
  bracketBreakdown: {
    bracketIndex: number;
    unitsInBracket: number;
    ratePerUnitCents: number;
    bracketCostCents: number;
  }[];
}

export class PricingTierDefinition {
  metricKey: string;
  mode: TierMode;
  brackets: TierBracket[];
  packageSize?: number;

  constructor(params: {
    metricKey: string;
    mode: TierMode;
    brackets: TierBracket[];
    packageSize?: number;
  }) {
    if (params.brackets.length === 0) {
      throw new Error('At least one pricing bracket is required');
    }
    this.metricKey = params.metricKey;
    this.mode = params.mode;
    this.brackets = [...params.brackets];
    this.packageSize = params.packageSize;
  }

  calculateCost(units: number): TierCalculationResult {
    if (units <= 0) {
      return {
        totalUnits: 0,
        totalCostCents: 0,
        mode: this.mode,
        bracketBreakdown: [],
      };
    }

    switch (this.mode) {
      case TierMode.VOLUME:
        return this.calculateVolumeCost(units);
      case TierMode.GRADUATED:
        return this.calculateGraduatedCost(units);
      case TierMode.PACKAGE:
        return this.calculatePackageCost(units);
      case TierMode.FLAT_FEE:
        return this.calculateFlatFeeCost(units);
      default:
        return this.calculateGraduatedCost(units);
    }
  }

  private calculateVolumeCost(units: number): TierCalculationResult {
    let matchedBracket = this.brackets[this.brackets.length - 1];
    let matchedIndex = this.brackets.length - 1;

    for (let i = 0; i < this.brackets.length; i++) {
      const b = this.brackets[i];
      if (b.upToUnits === 'UNLIMITED' || units <= b.upToUnits) {
        matchedBracket = b;
        matchedIndex = i;
        break;
      }
    }

    const cost = Math.round(units * matchedBracket.unitPriceCents) + matchedBracket.flatFeeCents;
    return {
      totalUnits: units,
      totalCostCents: cost,
      mode: TierMode.VOLUME,
      bracketBreakdown: [
        {
          bracketIndex: matchedIndex,
          unitsInBracket: units,
          ratePerUnitCents: matchedBracket.unitPriceCents,
          bracketCostCents: cost,
        },
      ],
    };
  }

  private calculateGraduatedCost(units: number): TierCalculationResult {
    let remaining = units;
    let previousMax = 0;
    let totalCost = 0;
    const breakdown = [];

    for (let i = 0; i < this.brackets.length; i++) {
      if (remaining <= 0) break;

      const b = this.brackets[i];
      let bracketCapacity: number;

      if (b.upToUnits === 'UNLIMITED') {
        bracketCapacity = remaining;
      } else {
        bracketCapacity = b.upToUnits - previousMax;
      }

      const unitsInThisBracket = Math.min(remaining, bracketCapacity);
      const bracketCost = Math.round(unitsInThisBracket * b.unitPriceCents) + b.flatFeeCents;

      totalCost += bracketCost;
      breakdown.push({
        bracketIndex: i,
        unitsInBracket: unitsInThisBracket,
        ratePerUnitCents: b.unitPriceCents,
        bracketCostCents: bracketCost,
      });

      remaining -= unitsInThisBracket;
      if (b.upToUnits !== 'UNLIMITED') {
        previousMax = b.upToUnits;
      }
    }

    return {
      totalUnits: units,
      totalCostCents: totalCost,
      mode: TierMode.GRADUATED,
      bracketBreakdown: breakdown,
    };
  }

  private calculatePackageCost(units: number): TierCalculationResult {
    const pkgSize = this.packageSize || 1000;
    const packagesCount = Math.ceil(units / pkgSize);
    const bracket = this.brackets[0];
    const cost = packagesCount * bracket.unitPriceCents;

    return {
      totalUnits: units,
      totalCostCents: cost,
      mode: TierMode.PACKAGE,
      bracketBreakdown: [
        {
          bracketIndex: 0,
          unitsInBracket: units,
          ratePerUnitCents: bracket.unitPriceCents,
          bracketCostCents: cost,
        },
      ],
    };
  }

  private calculateFlatFeeCost(units: number): TierCalculationResult {
    let matched = this.brackets[0];
    let matchedIdx = 0;
    for (let i = 0; i < this.brackets.length; i++) {
      const b = this.brackets[i];
      if (b.upToUnits === 'UNLIMITED' || units <= b.upToUnits) {
        matched = b;
        matchedIdx = i;
        break;
      }
    }
    return {
      totalUnits: units,
      totalCostCents: matched.flatFeeCents,
      mode: TierMode.FLAT_FEE,
      bracketBreakdown: [
        {
          bracketIndex: matchedIdx,
          unitsInBracket: units,
          ratePerUnitCents: 0,
          bracketCostCents: matched.flatFeeCents,
        },
      ],
    };
  }
}
