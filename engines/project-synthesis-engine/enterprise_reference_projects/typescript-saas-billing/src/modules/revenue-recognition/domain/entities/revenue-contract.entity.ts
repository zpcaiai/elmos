/**
 * ASC 606 / IFRS 15 Revenue Contract Aggregate Root
 *
 * Represents an identifiable commercial contract between the SaaS vendor and customer
 * under the 5-step revenue recognition standard:
 * 1. Identify the contract with the customer
 * 2. Identify the performance obligations in the contract
 * 3. Determine the transaction price
 * 4. Allocate the transaction price to performance obligations
 * 5. Recognize revenue when (or as) the entity satisfies a performance obligation
 */

import { PerformanceObligation, ObligationStatus } from './performance-obligation.entity';

export enum ContractStatus {
  DRAFT = 'DRAFT',
  ACTIVE = 'ACTIVE',
  MODIFIED = 'MODIFIED',
  TERMINATED = 'TERMINATED',
  FULFILLED = 'FULFILLED',
}

export enum ModificationType {
  SEPARATE_CONTRACT = 'SEPARATE_CONTRACT',       // New distinct goods at SSP
  PROSPECTIVE = 'PROSPECTIVE',                   // Remaining goods distinct, blend remaining price
  CUMULATIVE_CATCH_UP = 'CUMULATIVE_CATCH_UP',   // Goods not distinct, adjust recognized rev to date
}

export interface ContractModificationEvent {
  modificationId: string;
  effectiveDate: Date;
  modificationType: ModificationType;
  priorTotalTransactionPrice: number;
  newTotalTransactionPrice: number;
  reason: string;
  affectedObligationIds: string[];
}

export class RevenueContract {
  public id: string;
  public customerId: string;
  public contractNumber: string;
  public startDate: Date;
  public endDate: Date;
  public currency: string;
  public totalTransactionPrice: number;
  public allocatedTransactionPrice: number;
  public status: ContractStatus;
  public obligations: PerformanceObligation[];
  public modificationHistory: ContractModificationEvent[];
  public createdAt: Date;
  public updatedAt: Date;

  constructor(params: {
    id: string;
    customerId: string;
    contractNumber: string;
    startDate: Date;
    endDate: Date;
    currency?: string;
    totalTransactionPrice: number;
    obligations?: PerformanceObligation[];
  }) {
    this.id = params.id;
    this.customerId = params.customerId;
    this.contractNumber = params.contractNumber;
    this.startDate = new Date(params.startDate);
    this.endDate = new Date(params.endDate);
    this.currency = params.currency || 'USD';
    this.totalTransactionPrice = Math.round(params.totalTransactionPrice * 100) / 100;
    this.allocatedTransactionPrice = 0;
    this.status = ContractStatus.DRAFT;
    this.obligations = params.obligations ? [...params.obligations] : [];
    this.modificationHistory = [];
    this.createdAt = new Date();
    this.updatedAt = new Date();

    if (this.endDate <= this.startDate) {
      throw new Error(`Contract ${this.contractNumber}: endDate must be strictly after startDate`);
    }
    if (this.totalTransactionPrice < 0) {
      throw new Error(`Contract ${this.contractNumber}: totalTransactionPrice cannot be negative`);
    }
  }

  /**
   * Add a distinct performance obligation to the contract
   */
  public addObligation(obligation: PerformanceObligation): void {
    if (this.status === ContractStatus.FULFILLED || this.status === ContractStatus.TERMINATED) {
      throw new Error(`Cannot add obligation to finalized contract ${this.contractNumber} with status ${this.status}`);
    }
    const exists = this.obligations.some(o => o.id === obligation.id);
    if (exists) {
      throw new Error(`Obligation with ID ${obligation.id} already exists in contract ${this.contractNumber}`);
    }
    this.obligations.push(obligation);
    this.updatedAt = new Date();
  }

  /**
   * Activate contract once obligations are defined and prices allocated
   */
  public activate(): void {
    if (this.obligations.length === 0) {
      throw new Error(`Contract ${this.contractNumber} must have at least one performance obligation before activation`);
    }
    const sumAllocated = this.obligations.reduce((sum, o) => sum + o.allocatedPrice, 0);
    const roundedAllocated = Math.round(sumAllocated * 100) / 100;
    if (Math.abs(roundedAllocated - this.totalTransactionPrice) > 0.05) {
      throw new Error(
        `Contract ${this.contractNumber} allocation mismatch: sum of obligations ($${roundedAllocated}) != contract price ($${this.totalTransactionPrice})`
      );
    }
    this.allocatedTransactionPrice = roundedAllocated;
    this.status = ContractStatus.ACTIVE;
    for (const obl of this.obligations) {
      if (obl.status === ObligationStatus.PENDING) {
        obl.status = ObligationStatus.ACTIVE;
      }
    }
    this.updatedAt = new Date();
  }

  /**
   * Records an ASC 606 contract modification
   */
  public modifyContract(
    modificationId: string,
    effectiveDate: Date,
    modType: ModificationType,
    newTotalPrice: number,
    reason: string,
    affectedIds: string[]
  ): ContractModificationEvent {
    if (this.status !== ContractStatus.ACTIVE && this.status !== ContractStatus.MODIFIED) {
      throw new Error(`Contract ${this.contractNumber} cannot be modified from state ${this.status}`);
    }
    const priorPrice = this.totalTransactionPrice;
    this.totalTransactionPrice = Math.round(newTotalPrice * 100) / 100;
    this.status = ContractStatus.MODIFIED;

    const event: ContractModificationEvent = {
      modificationId,
      effectiveDate: new Date(effectiveDate),
      modificationType: modType,
      priorTotalTransactionPrice: priorPrice,
      newTotalTransactionPrice: this.totalTransactionPrice,
      reason,
      affectedObligationIds: [...affectedIds],
    };
    this.modificationHistory.push(event);
    this.updatedAt = new Date();
    return event;
  }

  /**
   * Calculate total recognized revenue to date across all obligations
   */
  public getTotalRecognizedRevenue(): number {
    const total = this.obligations.reduce((sum, o) => sum + o.totalRecognizedRevenue, 0);
    return Math.round(total * 100) / 100;
  }

  /**
   * Calculate total deferred revenue (Contract Liability) across all obligations
   */
  public getTotalDeferredRevenue(): number {
    const total = this.obligations.reduce((sum, o) => sum + o.deferredRevenueBalance, 0);
    return Math.round(total * 100) / 100;
  }

  /**
   * Checks if all performance obligations are fully satisfied
   */
  public checkAndMarkFulfillment(): boolean {
    if (this.obligations.length === 0) return false;
    const allSatisfied = this.obligations.every(o => o.status === ObligationStatus.SATISFIED);
    if (allSatisfied && this.status === ContractStatus.ACTIVE) {
      this.status = ContractStatus.FULFILLED;
      this.updatedAt = new Date();
      return true;
    }
    return false;
  }
}
