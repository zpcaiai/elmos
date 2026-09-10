/**
 * ASC 606 / IFRS 15 Revenue Amortization & Waterfall Engine
 *
 * Implements Step 5 of ASC 606:
 * Handles straight-line ratable recognition, milestone percent-of-completion,
 * contract modifications (prospective and cumulative catch-up), and
 * multi-period waterfall cohort roll-forward analysis.
 */

import { Injectable } from '@nestjs/common';
import { PerformanceObligation, SatisfactionPattern, ObligationStatus } from '../entities/performance-obligation.entity';
import { RevenueContract, ModificationType } from '../entities/revenue-contract.entity';
import {
  RevenueScheduleLine,
  RevenueWaterfallReport,
  MonthlyWaterfallCohort,
  RevenueScheduleHelper
} from '../entities/revenue-schedule.entity';

@Injectable()
export class RevenueAmortizationService {
  /**
   * Generates amortization schedule for all obligations in a contract
   */
  public generateFullContractSchedule(contract: RevenueContract): RevenueScheduleLine[] {
    const allLines: RevenueScheduleLine[] = [];

    for (const obl of contract.obligations) {
      if (obl.status === ObligationStatus.CANCELLED) continue;

      if (obl.satisfactionPattern === SatisfactionPattern.OVER_TIME_RATABLE) {
        const lines = this.generateRatableDailySchedule(obl);
        allLines.push(...lines);
      } else if (obl.satisfactionPattern === SatisfactionPattern.POINT_IN_TIME) {
        const line = this.generatePointInTimeSchedule(obl);
        allLines.push(line);
      }
      // MILESTONE is triggered dynamically upon milestone completion
    }

    return allLines;
  }

  /**
   * Generates daily ratable straight-line amortization schedule lines aggregated by calendar month
   */
  public generateRatableDailySchedule(obligation: PerformanceObligation): RevenueScheduleLine[] {
    const totalAllocated = obligation.allocatedPrice;
    if (totalAllocated <= 0) return [];

    const totalDays = RevenueScheduleHelper.daysBetweenInclusive(obligation.startDate, obligation.endDate);
    const dailyRate = totalAllocated / totalDays;
    const monthlyRanges = RevenueScheduleHelper.splitIntoMonthlyRanges(obligation.startDate, obligation.endDate);

    const lines: RevenueScheduleLine[] = [];
    let recognizedAccumulator = 0;

    for (let i = 0; i < monthlyRanges.length; i++) {
      const range = monthlyRanges[i];
      const daysInRange = RevenueScheduleHelper.daysBetweenInclusive(range.start, range.end);

      let periodAmount: number;
      if (i === monthlyRanges.length - 1) {
        // Last period absorbs any fractional cents to ensure exact sum match
        periodAmount = Math.round((totalAllocated - recognizedAccumulator) * 100) / 100;
      } else {
        periodAmount = Math.round(dailyRate * daysInRange * 100) / 100;
      }

      recognizedAccumulator += periodAmount;
      const remainingDeferred = Math.max(0, Math.round((totalAllocated - recognizedAccumulator) * 100) / 100);

      const line: RevenueScheduleLine = {
        scheduleId: `sched-${obligation.id}-${range.monthKey}`,
        obligationId: obligation.id,
        postingDate: new Date(range.end),
        periodStartDate: new Date(range.start),
        periodEndDate: new Date(range.end),
        recognizedAmount: periodAmount,
        deferredRevenueRemaining: remainingDeferred,
        unbilledReceivableDelta: 0,
        isPosted: false,
      };

      lines.push(line);
    }

    return lines;
  }

  /**
   * Generates single point-in-time recognition line on end date / delivery date
   */
  public generatePointInTimeSchedule(obligation: PerformanceObligation): RevenueScheduleLine {
    return {
      scheduleId: `sched-pit-${obligation.id}`,
      obligationId: obligation.id,
      postingDate: new Date(obligation.endDate),
      periodStartDate: new Date(obligation.startDate),
      periodEndDate: new Date(obligation.endDate),
      recognizedAmount: obligation.allocatedPrice,
      deferredRevenueRemaining: 0,
      unbilledReceivableDelta: 0,
      isPosted: false,
    };
  }

  /**
   * Applies ASC 606 Contract Modification to schedules
   */
  public applyContractModification(params: {
    contract: RevenueContract;
    modificationType: ModificationType;
    effectiveDate: Date;
    newTotalContractPrice: number;
    reallocatedObligations: PerformanceObligation[];
  }): {
    catchUpAdjustment: number;
    updatedContract: RevenueContract;
  } {
    const { contract, modificationType, effectiveDate, newTotalContractPrice, reallocatedObligations } = params;

    let catchUpAdjustment = 0;

    if (modificationType === ModificationType.CUMULATIVE_CATCH_UP) {
      // Step: Recalculate cumulative revenue to date under new terms
      let targetRecognizedToDate = 0;
      const priorRecognizedToDate = contract.getTotalRecognizedRevenue();

      for (const obl of reallocatedObligations) {
        const totalDays = RevenueScheduleHelper.daysBetweenInclusive(obl.startDate, obl.endDate);
        const elapsedDays = Math.min(
          totalDays,
          Math.max(0, RevenueScheduleHelper.daysBetweenInclusive(obl.startDate, effectiveDate))
        );
        const progressRatio = totalDays > 0 ? elapsedDays / totalDays : 1.0;
        targetRecognizedToDate += obl.allocatedPrice * progressRatio;
      }

      targetRecognizedToDate = Math.round(targetRecognizedToDate * 100) / 100;
      catchUpAdjustment = Math.round((targetRecognizedToDate - priorRecognizedToDate) * 100) / 100;

      contract.modifyContract(
        `mod-catchup-${Date.now()}`,
        effectiveDate,
        modificationType,
        newTotalContractPrice,
        `Cumulative catch-up adjustment of $${catchUpAdjustment} applied on ${effectiveDate.toISOString().slice(0, 10)}`,
        reallocatedObligations.map(o => o.id)
      );

      // Re-assign obligations with updated allocated prices
      contract.obligations = [...reallocatedObligations];

    } else if (modificationType === ModificationType.PROSPECTIVE) {
      // Step: Blend remaining allocated price over remaining performance periods
      contract.modifyContract(
        `mod-prospective-${Date.now()}`,
        effectiveDate,
        modificationType,
        newTotalContractPrice,
        `Prospective rate adjustment applied from ${effectiveDate.toISOString().slice(0, 10)} forward`,
        reallocatedObligations.map(o => o.id)
      );

      contract.obligations = [...reallocatedObligations];
    } else {
      // SEPARATE_CONTRACT
      contract.modifyContract(
        `mod-separate-${Date.now()}`,
        effectiveDate,
        modificationType,
        newTotalContractPrice,
        `Treated as distinct separate contract goods`,
        reallocatedObligations.map(o => o.id)
      );
    }

    return {
      catchUpAdjustment,
      updatedContract: contract,
    };
  }

  /**
   * Generates a multi-month Deferred Revenue Waterfall Report
   * Demonstrates roll-forward balance integrity:
   * Beginning Balance + Billings - Recognized Revenue + Modifications = Ending Balance
   */
  public generateWaterfallReport(contract: RevenueContract, asOfDate: Date): RevenueWaterfallReport {
    const monthlyCohorts: MonthlyWaterfallCohort[] = [];
    const monthlyRanges = RevenueScheduleHelper.splitIntoMonthlyRanges(contract.startDate, contract.endDate);

    let rollingDeferred = 0;
    let totalRecognized = 0;

    // In period 0, new billings equals the contract transaction price
    let initialBilled = false;

    for (const range of monthlyRanges) {
      const beginning = rollingDeferred;
      const newBillings = !initialBilled ? contract.totalTransactionPrice : 0;
      initialBilled = true;

      // Sum all revenue recognized in this month across obligations
      let monthRecognized = 0;
      for (const obl of contract.obligations) {
        for (const line of obl.scheduleLines) {
          if (line.periodStartDate <= range.end && line.periodEndDate >= range.start) {
            monthRecognized += line.recognizedAmount;
          }
        }
      }
      monthRecognized = Math.round(monthRecognized * 100) / 100;

      // Check for contract modification adjustments in this month
      let monthModifications = 0;
      for (const mod of contract.modificationHistory) {
        const modMonth = RevenueScheduleHelper.getMonthKey(mod.effectiveDate);
        if (modMonth === range.monthKey) {
          monthModifications += (mod.newTotalTransactionPrice - mod.priorTotalTransactionPrice);
        }
      }
      monthModifications = Math.round(monthModifications * 100) / 100;

      const ending = Math.round((beginning + newBillings - monthRecognized + monthModifications) * 100) / 100;

      monthlyCohorts.push({
        cohortMonth: range.monthKey,
        beginningDeferredRevenue: beginning,
        newBillings,
        recognizedRevenue: monthRecognized,
        contractModifications: monthModifications,
        endingDeferredRevenue: ending,
      });

      rollingDeferred = ending;
      totalRecognized = Math.round((totalRecognized + monthRecognized) * 100) / 100;
    }

    return {
      contractId: contract.id,
      currency: contract.currency,
      asOfDate,
      totalContractValue: contract.totalTransactionPrice,
      totalRecognizedToDate: totalRecognized,
      totalDeferredRemaining: rollingDeferred,
      monthlyCohorts,
    };
  }

  /**
   * Posts revenue schedule lines for a specific closed accounting period
   */
  public postPeriodRevenue(contract: RevenueContract, targetMonth: string): {
    postedLinesCount: number;
    totalPostedAmount: number;
  } {
    let count = 0;
    let total = 0;

    for (const obl of contract.obligations) {
      for (const line of obl.scheduleLines) {
        const lineMonth = RevenueScheduleHelper.getMonthKey(line.postingDate);
        if (lineMonth === targetMonth && !line.isPosted) {
          line.isPosted = true;
          line.journalEntryRef = `JE-REV-${contract.contractNumber}-${lineMonth}`;
          count++;
          total += line.recognizedAmount;
        }
      }
    }

    return {
      postedLinesCount: count,
      totalPostedAmount: Math.round(total * 100) / 100,
    };
  }
}
