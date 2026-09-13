import { Module } from '@nestjs/common';
import { CrossBorderTaxService } from './domain/services/cross-border-tax.service';
import { CrossBorderTaxController } from './presentation/controllers/cross-border-tax.controller';

@Module({
  controllers: [CrossBorderTaxController],
  providers: [CrossBorderTaxService],
  exports: [CrossBorderTaxService],
})
export class CrossBorderTaxModule {}
