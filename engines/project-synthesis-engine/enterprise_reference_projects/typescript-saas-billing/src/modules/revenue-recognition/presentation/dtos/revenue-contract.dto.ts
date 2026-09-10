/**
 * ASC 606 Revenue Recognition Presentation DTOs
 */

import { ObligationType, SatisfactionPattern, SSPEstimationMethod } from '../../domain/entities/performance-obligation.entity';
import { ModificationType } from '../../domain/entities/revenue-contract.entity';

export interface CreateObligationDto {
  name: string;
  obligationType: ObligationType;
  satisfactionPattern: SatisfactionPattern;
  sspMethod: SSPEstimationMethod;
  standaloneSellingPrice: number;
  startDate: string; // ISO-8601
  endDate: string;   // ISO-8601
}

export interface CreateRevenueContractDto {
  customerId: string;
  contractNumber: string;
  startDate: string; // ISO-8601
  endDate: string;   // ISO-8601
  currency: string;
  totalTransactionPrice: number;
  obligations: CreateObligationDto[];
}

export interface ModifyContractDto {
  modificationType: ModificationType;
  effectiveDate: string;
  newTotalContractPrice: number;
  reason: string;
  updatedObligations: CreateObligationDto[];
}

export interface MilestoneProgressDto {
  obligationId: string;
  newPercentComplete: number; // 0.0 - 1.0
}

export interface ClosePeriodDto {
  accountingPeriod: string; // YYYY-MM
}
