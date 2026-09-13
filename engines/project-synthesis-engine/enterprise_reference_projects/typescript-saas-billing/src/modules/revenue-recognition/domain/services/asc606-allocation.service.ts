/**
 * ASC 606 / IFRS 15 Allocation Service
 *
 * Implements Step 4 of ASC 606:
 * Allocates the transaction price to each performance obligation in proportion
 * to their relative Standalone Selling Prices (SSP).
 */

import { Injectable } from '@nestjs/common';
import { PerformanceObligation } from '../entities/performance-obligation.entity';
import { RevenueContract } from '../entities/revenue-contract.entity';

export interface AllocationResult {
  obligationId: string;
  obligationName: string;
  standaloneSellingPrice: number;
  sspRatio: number;
  allocatedAmount: number;
  discountAllocated: number;
}

export interface ContractAllocationSummary {
  contractId: string;
  totalTransactionPrice: number;
  totalSSP: number;
  totalDiscount: number;
  allocations: AllocationResult[];
  pennyDiscrepancyReconciled: number;
}

@Injectable()
export class Asc606AllocationService {
  /**
   * Allocates the contract transaction price across all obligations using relative SSP
   */
  public allocateTransactionPrice(contract: RevenueContract): ContractAllocationSummary {
    const obligations = contract.obligations;
    if (!obligations || obligations.length === 0) {
      throw new Error(`Cannot allocate price for contract ${contract.contractNumber}: no obligations defined`);
    }

    const transactionPrice = contract.totalTransactionPrice;
    const totalSSP = obligations.reduce((sum, obl) => sum + obl.standaloneSellingPrice, 0);

    if (totalSSP <= 0) {
      throw new Error(`Cannot allocate price: total SSP for contract ${contract.contractNumber} must be greater than 0`);
    }

    const totalDiscount = Math.round(Math.max(0, totalSSP - transactionPrice) * 100) / 100;
    const allocations: AllocationResult[] = [];
    let cumulativeAllocated = 0;

    for (let i = 0; i < obligations.length; i++) {
      const obl = obligations[i];
      const sspRatio = obl.standaloneSellingPrice / totalSSP;

      // Unrounded allocation
      const rawAllocated = transactionPrice * sspRatio;
      const roundedAllocated = Math.round(rawAllocated * 100) / 100;
      const discount = Math.round((obl.standaloneSellingPrice - roundedAllocated) * 100) / 100;

      cumulativeAllocated += roundedAllocated;
      allocations.push({
        obligationId: obl.id,
        obligationName: obl.name,
        standaloneSellingPrice: obl.standaloneSellingPrice,
        sspRatio: Math.round(sspRatio * 10000) / 10000,
        allocatedAmount: roundedAllocated,
        discountAllocated: discount,
      });
    }

    // Exact penny rounding reconciliation
    // The sum of allocated amounts must exactly equal the total transaction price.
    const discrepancy = Math.round((transactionPrice - cumulativeAllocated) * 100) / 100;
    if (Math.abs(discrepancy) > 0.001) {
      // Find the obligation with the largest allocation to absorb the penny difference
      let maxIdx = 0;
      let maxVal = allocations[0].allocatedAmount;
      for (let i = 1; i < allocations.length; i++) {
        if (allocations[i].allocatedAmount > maxVal) {
          maxVal = allocations[i].allocatedAmount;
          maxIdx = i;
        }
      }
      allocations[maxIdx].allocatedAmount = Math.round((allocations[maxIdx].allocatedAmount + discrepancy) * 100) / 100;
      allocations[maxIdx].discountAllocated = Math.round((allocations[maxIdx].discountAllocated - discrepancy) * 100) / 100;
    }

    // Apply allocated prices to the domain entities
    for (const alloc of allocations) {
      const obl = obligations.find(o => o.id === alloc.obligationId);
      if (obl) {
        obl.setAllocatedPrice(alloc.allocatedAmount);
      }
    }

    return {
      contractId: contract.id,
      totalTransactionPrice: transactionPrice,
      totalSSP: Math.round(totalSSP * 100) / 100,
      totalDiscount,
      allocations,
      pennyDiscrepancyReconciled: discrepancy,
    };
  }

  /**
   * Evaluates variable consideration under ASC 606-10-32-5
   * Constrains consideration to the amount for which it is probable that a
   * significant reversal will NOT occur when uncertainty is resolved.
   */
  public evaluateVariableConsideration(params: {
    fixedPrice: number;
    scenarios: Array<{ amount: number; probability: number }>;
    constraintFactor: number; // e.g. 0.85 (confidence threshold required)
  }): { expectedValue: number; constrainedTransactionPrice: number; unconstrainedAmount: number } {
    const totalProb = params.scenarios.reduce((sum, s) => sum + s.probability, 0);
    if (Math.abs(totalProb - 1.0) > 0.01) {
      throw new Error(`Scenario probabilities must sum to 1.0, got ${totalProb}`);
    }

    // Calculate expected value
    const expectedVariable = params.scenarios.reduce((sum, s) => sum + (s.amount * s.probability), 0);
    const unconstrainedTotal = params.fixedPrice + expectedVariable;

    // Apply conservative reversal constraint
    // Only include variable consideration up to the percentile satisfying constraintFactor
    // Sort scenarios by amount ascending
    const sorted = [...params.scenarios].sort((a, b) => a.amount - b.amount);
    let cumulativeProb = 0;
    let constrainedVariable = 0;

    for (const s of sorted) {
      cumulativeProb += s.probability;
      if (cumulativeProb >= (1.0 - params.constraintFactor)) {
        constrainedVariable = s.amount;
        break;
      }
    }

    const constrainedTotal = params.fixedPrice + constrainedVariable;

    return {
      expectedValue: Math.round(expectedVariable * 100) / 100,
      constrainedTransactionPrice: Math.round(constrainedTotal * 100) / 100,
      unconstrainedAmount: Math.round(unconstrainedTotal * 100) / 100,
    };
  }

  /**
   * Adjusts for significant financing component (ASC 606-10-32-15)
   * Imputes interest expense / income if customer payment is > 1 year in advance or arrears.
   */
  public calculateFinancingComponent(params: {
    nominalPrice: number;
    annualDiscountRate: number; // e.g. 0.06 for 6%
    monthsDifference: number;   // timing difference between payment and transfer
    isPaymentInAdvance: boolean;
  }): { presentValue: number; totalInterestAdjustment: number } {
    if (params.monthsDifference <= 12) {
      // Practical expedient: do not adjust if contract term is 1 year or less
      return {
        presentValue: params.nominalPrice,
        totalInterestAdjustment: 0,
      };
    }

    const years = params.monthsDifference / 12;
    if (params.isPaymentInAdvance) {
      // Vendor received cash upfront: interest expense recognized over service term
      // Future value of transfer = Nominal Cash * (1 + r)^t
      const futureValue = params.nominalPrice * Math.pow(1 + params.annualDiscountRate, years);
      const interestExpense = futureValue - params.nominalPrice;
      return {
        presentValue: Math.round(params.nominalPrice * 100) / 100,
        totalInterestAdjustment: Math.round(interestExpense * 100) / 100,
      };
    } else {
      // Customer pays in arrears: Vendor recognizes financing income
      // Present Value = Nominal Cash / (1 + r)^t
      const presentValue = params.nominalPrice / Math.pow(1 + params.annualDiscountRate, years);
      const interestIncome = params.nominalPrice - presentValue;
      return {
        presentValue: Math.round(presentValue * 100) / 100,
        totalInterestAdjustment: Math.round(interestIncome * 100) / 100,
      };
    }
  }
}
