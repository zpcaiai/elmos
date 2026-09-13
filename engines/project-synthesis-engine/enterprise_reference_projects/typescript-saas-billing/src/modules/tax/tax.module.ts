/**
 * Global Tax NestJS Module
 */

import { Module } from '@nestjs/common';
import { TaxNexusEvaluatorService } from './domain/services/tax-nexus-evaluator.service';
import { TaxEngineService } from './domain/services/tax-engine.service';
import { TaxController } from './presentation/controllers/tax.controller';

@Module({
  controllers: [TaxController],
  providers: [TaxNexusEvaluatorService, TaxEngineService],
  exports: [TaxNexusEvaluatorService, TaxEngineService],
})
export class TaxModule {}
