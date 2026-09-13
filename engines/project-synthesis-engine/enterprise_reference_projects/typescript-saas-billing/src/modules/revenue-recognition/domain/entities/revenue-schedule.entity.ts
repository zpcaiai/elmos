/**
 * ASC 606 / IFRS 15 Revenue Amortization Schedule & Waterfall Entities
 */

export interface RevenueScheduleLine {
  scheduleId: string;
  obligationId: string;
  postingDate: Date;
  periodStartDate: Date;
  periodEndDate: Date;
  recognizedAmount: number;
  deferredRevenueRemaining: number;
  unbilledReceivableDelta: number;
  isPosted: boolean;
  journalEntryRef?: string;
}

export interface MonthlyWaterfallCohort {
  cohortMonth: string; // YYYY-MM
  beginningDeferredRevenue: number;
  newBillings: number;
  recognizedRevenue: number;
  contractModifications: number;
  endingDeferredRevenue: number;
}

export interface RevenueWaterfallReport {
  contractId: string;
  currency: string;
  asOfDate: Date;
  totalContractValue: number;
  totalRecognizedToDate: number;
  totalDeferredRemaining: number;
  monthlyCohorts: MonthlyWaterfallCohort[];
}

export class RevenueScheduleHelper {
  /**
   * Generates YYYY-MM string representation for standard date
   */
  public static getMonthKey(d: Date): string {
    const year = d.getUTCFullYear();
    const month = String(d.getUTCMonth() + 1).padStart(2, '0');
    return `${year}-${month}`;
  }

  /**
   * Computes number of days between two dates inclusive
   */
  public static daysBetweenInclusive(start: Date, end: Date): number {
    const msPerDay = 1000 * 60 * 60 * 24;
    const s = Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate());
    const e = Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate());
    return Math.max(1, Math.round((e - s) / msPerDay) + 1);
  }

  /**
   * Splits a date range into monthly sub-ranges
   */
  public static splitIntoMonthlyRanges(startDate: Date, endDate: Date): Array<{ start: Date; end: Date; monthKey: string }> {
    const ranges: Array<{ start: Date; end: Date; monthKey: string }> = [];
    let current = new Date(startDate);

    while (current <= endDate) {
      const year = current.getUTCFullYear();
      const month = current.getUTCMonth();
      // End of this calendar month
      const lastDayOfMonth = new Date(Date.UTC(year, month + 1, 0, 23, 59, 59, 999));
      const rangeEnd = lastDayOfMonth < endDate ? lastDayOfMonth : new Date(endDate);

      ranges.push({
        start: new Date(current),
        end: new Date(rangeEnd),
        monthKey: RevenueScheduleHelper.getMonthKey(current),
      });

      // Advance to next month 1st day 00:00:00
      current = new Date(Date.UTC(year, month + 1, 1, 0, 0, 0, 0));
    }

    return ranges;
  }
}
