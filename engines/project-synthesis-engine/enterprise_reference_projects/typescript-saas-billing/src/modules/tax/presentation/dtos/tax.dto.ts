/**
 * Tax Presentation DTOs
 */

import { AddressDto, TaxableItemDto } from '../../domain/services/tax-engine.service';
import { ExemptionType } from '../../domain/entities/tax-exemption.entity';

export interface EstimateTaxDto {
  transactionId: string;
  customerId: string;
  customerAddress: AddressDto;
  customerVatNumber?: string;
  items: TaxableItemDto[];
}

export interface RegisterExemptionDto {
  customerId: string;
  jurisdictionCode: string;
  exemptionType: ExemptionType;
  certificateNumber: string;
  issuingState: string;
  validFrom: string; // ISO date
  validTo: string;   // ISO date
}

export interface NexusQueryDto {
  stateCode: string;
  grossSales12M: number;
  transactionCount12M: number;
  hasPhysicalEmployees?: boolean;
}
