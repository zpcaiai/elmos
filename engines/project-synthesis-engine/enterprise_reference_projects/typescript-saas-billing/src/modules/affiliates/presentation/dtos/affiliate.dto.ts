/**
 * Affiliate & Partner Presentation DTOs
 */

import { CommissionModelType, CommissionTier } from '../../domain/entities/partner-agreement.entity';

export interface CreatePartnerAgreementDto {
  partnerId: string;
  partnerName: string;
  modelType: CommissionModelType;
  flatRatePercentage?: number;
  tiers?: CommissionTier[];
  bountyAmount?: number;
}

export interface ReferCustomerDto {
  customerId: string;
}

export interface CalculateCommissionDto {
  invoiceId: string;
  customerId: string;
  invoiceSubtotal: number;
  taxAmount: number;
  isFirstPayment: boolean;
  paymentDate: string;
  partnerMonthlyVolume?: number;
}
