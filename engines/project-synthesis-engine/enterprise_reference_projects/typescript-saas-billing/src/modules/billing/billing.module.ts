import { Module } from '@nestjs/common';
import { SubscriptionController } from './presentation/controllers/subscription.controller';
import { UsageController } from './presentation/controllers/usage.controller';
import { InvoiceController } from './presentation/controllers/invoice.controller';
import { ProrationService } from './domain/services/proration.service';
import { UsageAggregatorService } from './domain/services/usage-aggregator.service';
import { InvoiceCalculatorService } from './domain/services/invoice-calculator.service';
import { DunningService } from './domain/services/dunning.service';
import {
  InMemoryCustomerRepository,
  InMemorySubscriptionRepository,
  InMemoryInvoiceRepository,
} from './infrastructure/persistence/in-memory-billing.repository';
import { DistributedLockService } from './infrastructure/locks/redis-cluster-lock.service';
import { XFetchCacheService } from './infrastructure/locks/xfetch-stampede.service';
import { WebhookDispatcher } from './infrastructure/queues/webhook-dispatcher';

@Module({
  controllers: [SubscriptionController, UsageController, InvoiceController],
  providers: [
    ProrationService,
    UsageAggregatorService,
    {
      provide: InvoiceCalculatorService,
      useFactory: (usageAgg: UsageAggregatorService) => new InvoiceCalculatorService(usageAgg),
      inject: [UsageAggregatorService],
    },
    DunningService,
    {
      provide: 'CustomerRepository',
      useClass: InMemoryCustomerRepository,
    },
    {
      provide: 'SubscriptionRepository',
      useClass: InMemorySubscriptionRepository,
    },
    {
      provide: 'InvoiceRepository',
      useClass: InMemoryInvoiceRepository,
    },
    DistributedLockService,
    XFetchCacheService,
    WebhookDispatcher,
  ],
  exports: [
    ProrationService,
    UsageAggregatorService,
    InvoiceCalculatorService,
    DunningService,
    'CustomerRepository',
    'SubscriptionRepository',
    'InvoiceRepository',
    DistributedLockService,
    XFetchCacheService,
    WebhookDispatcher,
  ],
})
export class BillingModule {}
