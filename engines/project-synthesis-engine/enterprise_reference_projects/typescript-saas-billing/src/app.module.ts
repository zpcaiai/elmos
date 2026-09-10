import { Module } from '@nestjs/common';
import { BillingModule } from './modules/billing/billing.module';
import { RevenueRecognitionModule } from './modules/revenue-recognition/revenue-recognition.module';
import { TaxModule } from './modules/tax/tax.module';
import { DunningAdvancedModule } from './modules/dunning-advanced/dunning-advanced.module';
import { AffiliatesModule } from './modules/affiliates/affiliates.module';

@Module({
  imports: [
    BillingModule,
    RevenueRecognitionModule,
    TaxModule,
    DunningAdvancedModule,
    AffiliatesModule,
  ],
})
export class AppModule {}

