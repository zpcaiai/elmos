/**
 * Advanced Dunning REST Controller
 */

import { Controller, Get, Post, Body, Param, NotFoundException, BadRequestException } from '@nestjs/common';
import { DunningOrchestratorService } from '../../domain/services/dunning-orchestrator.service';
import { SmartRetryService } from '../../domain/services/smart-retry.service';
import { DeclineType } from '../../domain/entities/dunning-campaign.entity';

export interface TriggerDunningDto {
  customerId: string;
  subscriptionId: string;
  invoiceId: string;
  amount: number;
  declineCode: string;
  customerTzOffset?: number;
}

@Controller('api/v1/dunning')
export class DunningAdvancedController {
  constructor(
    private readonly orchestrator: DunningOrchestratorService,
    private readonly smartRetry: SmartRetryService,
  ) {}

  @Post('trigger')
  public triggerDunning(@Body() dto: TriggerDunningDto) {
    if (!dto.customerId || !dto.subscriptionId || !dto.invoiceId) {
      throw new BadRequestException('Missing required fields');
    }

    const campaign = this.orchestrator.handlePaymentFailure(dto);
    return {
      campaignId: campaign.id,
      status: campaign.status,
      declineType: campaign.declineType,
      stagesCount: campaign.stages.length,
      nextScheduledStage: campaign.stages[0],
    };
  }

  @Get(':id')
  public getCampaign(@Param('id') id: string) {
    const campaign = this.orchestrator.getCampaign(id);
    if (!campaign) {
      throw new NotFoundException(`Dunning campaign ${id} not found`);
    }

    return {
      id: campaign.id,
      customerId: campaign.customerId,
      subscriptionId: campaign.subscriptionId,
      invoiceId: campaign.invoiceId,
      amount: campaign.outstandingAmount,
      status: campaign.status,
      stages: campaign.stages,
      recoveredAt: campaign.recoveredAt,
    };
  }

  @Post(':id/advance')
  public advanceStage(@Param('id') id: string) {
    return this.orchestrator.executeNextStage(id);
  }

  @Post(':id/recover')
  public recoverPayment(@Param('id') id: string, @Body() body: { invoiceId: string }) {
    const success = this.orchestrator.handlePaymentSuccess(body.invoiceId);
    return { success };
  }
}
