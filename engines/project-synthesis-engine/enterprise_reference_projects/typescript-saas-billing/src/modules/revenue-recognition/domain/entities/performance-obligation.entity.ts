/**
 * ASC 606 / IFRS 15 Performance Obligation Entity
 *
 * Represents a promised distinct good or service in a customer contract.
 */

import { RevenueScheduleLine } from './revenue-schedule.entity';

export enum ObligationType {
  SAAS_SUBSCRIPTION = 'SAAS_SUBSCRIPTION',
  PROFESSIONAL_SERVICES = 'PROFESSIONAL_SERVICES',
  PREMIUM_SUPPORT = 'PREMIUM_SUPPORT',
  TRAINING = 'TRAINING',
  CONSUMPTION_TIER = 'CONSUMPTION_TIER',
}

export enum SatisfactionPattern {
  OVER_TIME_RATABLE = 'OVER_TIME_RATABLE',     // Daily linear straight-line over service term
  OVER_TIME_MILESTONE = 'OVER_TIME_MILESTONE', // Percentage of completion / milestone deliverables
  POINT_IN_TIME = 'POINT_IN_TIME',             // Recognized upon delivery / customer acceptance
}

export enum SSPEstimationMethod {
  OBSERVABLE_PRICE = 'OBSERVABLE_PRICE',       // Standalone catalog price sold to similar customers
  ADJUSTED_MARKET = 'ADJUSTED_MARKET',         // Market competitor evaluation
  COST_PLUS_MARGIN = 'COST_PLUS_MARGIN',       // Cost plus target gross margin
  RESIDUAL = 'RESIDUAL',                       // Total price minus observable SSP of other goods
}

export enum ObligationStatus {
  PENDING = 'PENDING',
  ACTIVE = 'ACTIVE',
  SATISFIED = 'SATISFIED',
  CANCELLED = 'CANCELLED',
}

export class PerformanceObligation {
  public id: string;
  public contractId: string;
  public name: string;
  public obligationType: ObligationType;
  public satisfactionPattern: SatisfactionPattern;
  public sspMethod: SSPEstimationMethod;
  public standaloneSellingPrice: number;
  public allocatedPrice: number;
  public startDate: Date;
  public endDate: Date;
  public totalRecognizedRevenue: number;
  public deferredRevenueBalance: number;
  public unbilledReceivableBalance: number;
  public percentComplete: number; // 0.0 to 1.0 for milestone-based
  public status: ObligationStatus;
  public scheduleLines: RevenueScheduleLine[];
  public createdAt: Date;
  public updatedAt: Date;

  constructor(params: {
    id: string;
    contractId: string;
    name: string;
    obligationType: ObligationType;
    satisfactionPattern: SatisfactionPattern;
    sspMethod: SSPEstimationMethod;
    standaloneSellingPrice: number;
    allocatedPrice?: number;
    startDate: Date;
    endDate: Date;
  }) {
    this.id = params.id;
    this.contractId = params.contractId;
    this.name = params.name;
    this.obligationType = params.obligationType;
    this.satisfactionPattern = params.satisfactionPattern;
    this.sspMethod = params.sspMethod;
    this.standaloneSellingPrice = Math.round(params.standaloneSellingPrice * 100) / 100;
    this.allocatedPrice = params.allocatedPrice ? Math.round(params.allocatedPrice * 100) / 100 : 0;
    this.startDate = new Date(params.startDate);
    this.endDate = new Date(params.endDate);
    this.totalRecognizedRevenue = 0;
    this.deferredRevenueBalance = this.allocatedPrice;
    this.unbilledReceivableBalance = 0;
    this.percentComplete = 0;
    this.status = ObligationStatus.PENDING;
    this.scheduleLines = [];
    this.createdAt = new Date();
    this.updatedAt = new Date();

    if (this.endDate < this.startDate) {
      throw new Error(`Obligation ${this.name}: endDate cannot be before startDate`);
    }
  }

  /**
   * Updates allocated transaction price based on relative SSP calculation
   */
  public setAllocatedPrice(newPrice: number): void {
    this.allocatedPrice = Math.round(newPrice * 100) / 100;
    this.deferredRevenueBalance = Math.max(0, this.allocatedPrice - this.totalRecognizedRevenue);
    this.updatedAt = new Date();
  }

  /**
   * Applies revenue recognition for a specific period amount
   */
  public recognizeAmount(amount: number, line: RevenueScheduleLine): void {
    const cleanAmount = Math.round(amount * 100) / 100;
    if (cleanAmount <= 0) return;

    if (this.totalRecognizedRevenue + cleanAmount > this.allocatedPrice + 0.01) {
      throw new Error(
        `Obligation ${this.name}: recognizing $${cleanAmount} exceeds allocated price ($${this.allocatedPrice}), recognized to date: $${this.totalRecognizedRevenue}`
      );
    }

    this.totalRecognizedRevenue = Math.round((this.totalRecognizedRevenue + cleanAmount) * 100) / 100;
    this.deferredRevenueBalance = Math.round(Math.max(0, this.allocatedPrice - this.totalRecognizedRevenue) * 100) / 100;
    this.scheduleLines.push(line);

    if (Math.abs(this.totalRecognizedRevenue - this.allocatedPrice) < 0.01) {
      this.status = ObligationStatus.SATISFIED;
      this.percentComplete = 1.0;
    } else {
      this.percentComplete = this.allocatedPrice > 0 
        ? Math.round((this.totalRecognizedRevenue / this.allocatedPrice) * 10000) / 10000 
        : 1.0;
    }
    this.updatedAt = new Date();
  }

  /**
   * Record milestone progress for OVER_TIME_MILESTONE pattern
   */
  public updateMilestoneProgress(newPercent: number): number {
    if (this.satisfactionPattern !== SatisfactionPattern.OVER_TIME_MILESTONE) {
      throw new Error(`Obligation ${this.name} does not use milestone satisfaction pattern`);
    }
    const clampedPercent = Math.min(1.0, Math.max(0.0, newPercent));
    const targetRecognized = Math.round(this.allocatedPrice * clampedPercent * 100) / 100;
    const incrementalRevenue = Math.round((targetRecognized - this.totalRecognizedRevenue) * 100) / 100;

    if (incrementalRevenue > 0) {
      const scheduleLine: RevenueScheduleLine = {
        scheduleId: `sched-milestone-${Date.now()}`,
        obligationId: this.id,
        postingDate: new Date(),
        periodStartDate: this.startDate,
        periodEndDate: this.endDate,
        recognizedAmount: incrementalRevenue,
        deferredRevenueRemaining: Math.round((this.allocatedPrice - targetRecognized) * 100) / 100,
        unbilledReceivableDelta: 0,
        isPosted: true,
      };
      this.recognizeAmount(incrementalRevenue, scheduleLine);
    }
    return incrementalRevenue;
  }
}
