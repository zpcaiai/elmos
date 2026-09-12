import { Controller, Post, Body } from '@nestjs/common';
import { ASC606ModificationService } from '../../domain/services/asc606-modification.service';
import {
  ContractModificationAmendment,
  ModificationAccountingDecision,
  ContractPerformanceObligation,
} from '../../domain/entities/contract-modification.entity';
import { EvaluateModificationRequestDto } from '../dtos/contract-modification.dto';

@Controller('contract-modification')
export class ContractModificationController {
  constructor(private readonly modificationService: ASC606ModificationService) {}

  @Post('apply')
  public applyModification(
    @Body() dto: EvaluateModificationRequestDto
  ): ModificationAccountingDecision {
    const amendment: ContractModificationAmendment = {
      amendmentId: dto.amendmentId,
      originalContractId: dto.originalContractId,
      effectiveDate: new Date(),
      description: dto.description,
      additionalConsiderationCents: dto.additionalConsiderationCents,
      addedObligations: dto.addedObligations,
      priceConcessionOnRemainingCents: dto.priceConcessionOnRemainingCents ?? 0,
    };

    const existing: ContractPerformanceObligation[] = dto.existingObligations.map(o => ({
      obligationId: o.obligationId,
      name: o.name,
      isDistinct: o.isDistinct,
      standaloneSellingPriceCents: o.standaloneSellingPriceCents,
      allocatedTransactionPriceCents: o.allocatedTransactionPriceCents,
      recognizedRevenueCents: o.recognizedRevenueCents,
      deferredRevenueCents: o.deferredRevenueCents,
      progressPercentage: o.progressPercentage,
      totalPeriodMonths: o.totalPeriodMonths,
      remainingPeriodMonths: o.remainingPeriodMonths,
    }));

    return this.modificationService.applyModification(amendment, existing);
  }
}
