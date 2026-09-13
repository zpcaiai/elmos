/**
 * Affiliate REST Controller
 */

import { Controller, Get, Post, Body, Param, NotFoundException, BadRequestException } from '@nestjs/common';
import { CommissionCalculatorService } from '../../domain/services/commission-calculator.service';
import { PartnerAgreement } from '../../domain/entities/partner-agreement.entity';
import { CreatePartnerAgreementDto, ReferCustomerDto, CalculateCommissionDto } from '../dtos/affiliate.dto';

@Controller('api/v1/partners')
export class AffiliateController {
  private agreements: Map<string, PartnerAgreement> = new Map();

  constructor(private readonly commissionCalculator: CommissionCalculatorService) {}

  @Post()
  public createAgreement(@Body() dto: CreatePartnerAgreementDto) {
    if (!dto.partnerId || !dto.partnerName || !dto.modelType) {
      throw new BadRequestException('Missing required fields');
    }

    const agreement = new PartnerAgreement({
      id: `agr-${dto.partnerId}`,
      partnerId: dto.partnerId,
      partnerName: dto.partnerName,
      modelType: dto.modelType,
      flatRatePercentage: dto.flatRatePercentage,
      tiers: dto.tiers,
      bountyAmount: dto.bountyAmount,
    });

    this.agreements.set(dto.partnerId, agreement);
    return {
      success: true,
      partnerId: dto.partnerId,
      status: agreement.status,
    };
  }

  @Post(':partnerId/referrals')
  public referCustomer(@Param('partnerId') partnerId: string, @Body() dto: ReferCustomerDto) {
    const agreement = this.agreements.get(partnerId);
    if (!agreement) {
      throw new NotFoundException(`Partner agreement ${partnerId} not found`);
    }

    agreement.registerReferredCustomer(dto.customerId);
    return {
      partnerId,
      customerId: dto.customerId,
      isReferred: true,
    };
  }

  @Post(':partnerId/commissions')
  public calculateCommission(@Param('partnerId') partnerId: string, @Body() dto: CalculateCommissionDto) {
    const agreement = this.agreements.get(partnerId);
    if (!agreement) {
      throw new NotFoundException(`Partner agreement ${partnerId} not found`);
    }

    const result = this.commissionCalculator.calculateInvoiceCommission(
      agreement,
      {
        invoiceId: dto.invoiceId,
        customerId: dto.customerId,
        invoiceSubtotal: dto.invoiceSubtotal,
        taxAmount: dto.taxAmount,
        isFirstPayment: dto.isFirstPayment,
        paymentDate: new Date(dto.paymentDate),
      },
      dto.partnerMonthlyVolume || 0
    );

    return result;
  }
}
