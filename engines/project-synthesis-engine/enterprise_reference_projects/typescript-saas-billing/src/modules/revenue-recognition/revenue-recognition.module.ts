/**
 * ASC 606 Revenue Recognition NestJS Module
 */

import { Module } from '@nestjs/common';
import { Asc606AllocationService } from './domain/services/asc606-allocation.service';
import { RevenueAmortizationService } from './domain/services/revenue-amortization.service';
import { RevenueRecognitionController } from './presentation/controllers/revenue-recognition.controller';

@Module({
  controllers: [RevenueRecognitionController],
  providers: [Asc606AllocationService, RevenueAmortizationService],
  exports: [Asc606AllocationService, RevenueAmortizationService],
})
export class RevenueRecognitionModule {}
