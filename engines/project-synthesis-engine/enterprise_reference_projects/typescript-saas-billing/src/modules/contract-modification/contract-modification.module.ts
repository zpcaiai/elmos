import { Module } from '@nestjs/common';
import { ASC606ModificationService } from './domain/services/asc606-modification.service';
import { ContractModificationController } from './presentation/controllers/contract-modification.controller';

@Module({
  controllers: [ContractModificationController],
  providers: [ASC606ModificationService],
  exports: [ASC606ModificationService],
})
export class ContractModificationModule {}
