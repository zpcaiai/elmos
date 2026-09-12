/**
 * Advanced Dunning NestJS Module
 */

import { Module } from '@nestjs/common';
import { SmartRetryService } from './domain/services/smart-retry.service';
import { DunningOrchestratorService } from './domain/services/dunning-orchestrator.service';
import { DunningAdvancedController } from './presentation/controllers/dunning-advanced.controller';

@Module({
  controllers: [DunningAdvancedController],
  providers: [SmartRetryService, DunningOrchestratorService],
  exports: [SmartRetryService, DunningOrchestratorService],
})
export class DunningAdvancedModule {}
