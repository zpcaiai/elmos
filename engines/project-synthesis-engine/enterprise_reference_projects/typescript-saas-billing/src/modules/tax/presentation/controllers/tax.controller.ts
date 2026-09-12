/**
 * Tax REST Controller
 */

import { Controller, Get, Post, Body, Query, BadRequestException } from '@nestjs/common';
import { TaxEngineService } from '../../domain/services/tax-engine.service';
import { TaxNexusEvaluatorService } from '../../domain/services/tax-nexus-evaluator.service';
import { TaxExemptionCertificate, CertificateStatus } from '../../domain/entities/tax-exemption.entity';
import { EstimateTaxDto, RegisterExemptionDto, NexusQueryDto } from '../dtos/tax.dto';

@Controller('api/v1/tax')
export class TaxController {
  private exemptionRegistry: Map<string, TaxExemptionCertificate[]> = new Map();

  constructor(
    private readonly taxEngine: TaxEngineService,
    private readonly nexusEvaluator: TaxNexusEvaluatorService,
  ) {}

  @Post('estimate')
  public estimateTax(@Body() dto: EstimateTaxDto) {
    if (!dto.customerId || !dto.customerAddress || !dto.items) {
      throw new BadRequestException('Missing customerId, customerAddress, or items');
    }

    const customerCerts = this.exemptionRegistry.get(dto.customerId) || [];
    return this.taxEngine.calculateTax({
      transactionId: dto.transactionId || `tax-calc-${Date.now()}`,
      customerId: dto.customerId,
      customerAddress: dto.customerAddress,
      customerVatNumber: dto.customerVatNumber,
      items: dto.items,
      exemptionCertificates: customerCerts,
    });
  }

  @Post('exemptions')
  public registerExemption(@Body() dto: RegisterExemptionDto) {
    if (!dto.customerId || !dto.certificateNumber || !dto.jurisdictionCode) {
      throw new BadRequestException('Missing required certificate parameters');
    }

    const cert: TaxExemptionCertificate = {
      certificateId: `cert-${Date.now()}`,
      customerId: dto.customerId,
      jurisdictionCode: dto.jurisdictionCode,
      exemptionType: dto.exemptionType,
      certificateNumber: dto.certificateNumber,
      issuingState: dto.issuingState,
      validFrom: new Date(dto.validFrom),
      validTo: new Date(dto.validTo),
      status: CertificateStatus.VALID,
      verifiedAt: new Date(),
    };

    const list = this.exemptionRegistry.get(dto.customerId) || [];
    list.push(cert);
    this.exemptionRegistry.set(dto.customerId, list);

    return {
      success: true,
      certificateId: cert.certificateId,
      status: cert.status,
    };
  }

  @Get('nexus-status')
  public checkNexusStatus(@Query('state') stateCode: string, @Query('sales') sales: string, @Query('count') count: string) {
    if (!stateCode) {
      throw new BadRequestException('state query parameter is required');
    }

    return this.nexusEvaluator.evaluateStateNexus({
      stateCode,
      grossSales12M: parseFloat(sales || '0'),
      transactionCount12M: parseInt(count || '0', 10),
    });
  }
}
