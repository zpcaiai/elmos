import { Module } from '@nestjs/common';
import { BillingModule } from './modules/billing/billing.module';
import { RevenueRecognitionModule } from './modules/revenue-recognition/revenue-recognition.module';
import { TaxModule } from './modules/tax/tax.module';
import { DunningAdvancedModule } from './modules/dunning-advanced/dunning-advanced.module';
import { AffiliatesModule } from './modules/affiliates/affiliates.module';
import { UsageRatingModule } from './modules/usage-rating/usage-rating.module';
import { ContractModificationModule } from './modules/contract-modification/contract-modification.module';
import { CrossBorderTaxModule } from './modules/cross-border-tax/cross-border-tax.module';

@Module({
  imports: [
    BillingModule,
    RevenueRecognitionModule,
    TaxModule,
    DunningAdvancedModule,
    AffiliatesModule,
    UsageRatingModule,
    ContractModificationModule,
    CrossBorderTaxModule,
  ],
})
export class AppModule {}

