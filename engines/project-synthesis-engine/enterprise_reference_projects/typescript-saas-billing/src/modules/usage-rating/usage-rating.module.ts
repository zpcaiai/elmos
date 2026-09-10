import { Module } from '@nestjs/common';
import { UsageRatingEngineService } from './domain/services/usage-rating-engine.service';
import { CreditDrawdownWaterfallService } from './domain/services/credit-drawdown-waterfall.service';
import { UsageRatingController } from './presentation/controllers/usage-rating.controller';

@Module({
  controllers: [UsageRatingController],
  providers: [UsageRatingEngineService, CreditDrawdownWaterfallService],
  exports: [UsageRatingEngineService, CreditDrawdownWaterfallService],
})
export class UsageRatingModule {}
