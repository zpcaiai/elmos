/**
 * Affiliates & Partner NestJS Module
 */

import { Module } from '@nestjs/common';
import { CommissionCalculatorService } from './domain/services/commission-calculator.service';
import { AffiliateController } from './presentation/controllers/affiliate.controller';

@Module({
  controllers: [AffiliateController],
  providers: [CommissionCalculatorService],
  exports: [CommissionCalculatorService],
})
export class AffiliatesModule {}
