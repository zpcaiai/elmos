import { Module } from '@nestjs/common';
import { HierarchyRollupBillingService } from './domain/services/hierarchy-rollup-billing.service';

@Module({
  providers: [HierarchyRollupBillingService],
  exports: [HierarchyRollupBillingService],
})
export class CustomerHierarchyInvoicingModule {}
