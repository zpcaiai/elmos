/**
 * ASC 606 Revenue Recognition REST Controller
 */

import { Controller, Get, Post, Put, Body, Param, Query, NotFoundException, BadRequestException } from '@nestjs/common';
import { RevenueContract, ContractStatus } from '../../domain/entities/revenue-contract.entity';
import { PerformanceObligation } from '../../domain/entities/performance-obligation.entity';
import { Asc606AllocationService } from '../../domain/services/asc606-allocation.service';
import { RevenueAmortizationService } from '../../domain/services/revenue-amortization.service';
import {
  CreateRevenueContractDto,
  ModifyContractDto,
  MilestoneProgressDto,
  ClosePeriodDto
} from '../dtos/revenue-contract.dto';

@Controller('api/v1/revenue-contracts')
export class RevenueRecognitionController {
  private contracts: Map<string, RevenueContract> = new Map();

  constructor(
    private readonly allocationService: Asc606AllocationService,
    private readonly amortizationService: RevenueAmortizationService,
  ) {}

  @Post()
  public createContract(@Body() dto: CreateRevenueContractDto) {
    if (!dto.customerId || !dto.contractNumber || !dto.startDate || !dto.endDate) {
      throw new BadRequestException('Missing required fields for revenue contract');
    }

    const contractId = `rev-ctr-${Date.now()}`;
    const contract = new RevenueContract({
      id: contractId,
      customerId: dto.customerId,
      contractNumber: dto.contractNumber,
      startDate: new Date(dto.startDate),
      endDate: new Date(dto.endDate),
      currency: dto.currency || 'USD',
      totalTransactionPrice: dto.totalTransactionPrice,
    });

    if (dto.obligations && dto.obligations.length > 0) {
      for (let i = 0; i < dto.obligations.length; i++) {
        const oDto = dto.obligations[i];
        const obligation = new PerformanceObligation({
          id: `obl-${contractId}-${i + 1}`,
          contractId,
          name: oDto.name,
          obligationType: oDto.obligationType,
          satisfactionPattern: oDto.satisfactionPattern,
          sspMethod: oDto.sspMethod,
          standaloneSellingPrice: oDto.standaloneSellingPrice,
          startDate: new Date(oDto.startDate),
          endDate: new Date(oDto.endDate),
        });
        contract.addObligation(obligation);
      }
      // Allocate transaction price across obligations based on relative SSP
      this.allocationService.allocateTransactionPrice(contract);
      contract.activate();

      // Pre-generate ratable schedules
      for (const obl of contract.obligations) {
        if (obl.satisfactionPattern === 'OVER_TIME_RATABLE') {
          const lines = this.amortizationService.generateRatableDailySchedule(obl);
          for (const line of lines) {
            obl.recognizeAmount(line.recognizedAmount, line);
          }
        }
      }
    }

    this.contracts.set(contract.id, contract);
    return {
      success: true,
      contractId: contract.id,
      status: contract.status,
      totalTransactionPrice: contract.totalTransactionPrice,
      allocatedTransactionPrice: contract.allocatedTransactionPrice,
      obligationsCount: contract.obligations.length,
    };
  }

  @Get(':id')
  public getContract(@Param('id') id: string) {
    const contract = this.contracts.get(id);
    if (!contract) {
      throw new NotFoundException(`Revenue contract ${id} not found`);
    }

    return {
      id: contract.id,
      contractNumber: contract.contractNumber,
      customerId: contract.customerId,
      status: contract.status,
      startDate: contract.startDate,
      endDate: contract.endDate,
      totalTransactionPrice: contract.totalTransactionPrice,
      totalRecognized: contract.getTotalRecognizedRevenue(),
      totalDeferred: contract.getTotalDeferredRevenue(),
      obligations: contract.obligations.map(o => ({
        id: o.id,
        name: o.name,
        type: o.obligationType,
        pattern: o.satisfactionPattern,
        ssp: o.standaloneSellingPrice,
        allocatedPrice: o.allocatedPrice,
        recognized: o.totalRecognizedRevenue,
        deferredBalance: o.deferredRevenueBalance,
        percentComplete: o.percentComplete,
        status: o.status,
      })),
      modificationHistory: contract.modificationHistory,
    };
  }

  @Get(':id/waterfall')
  public getWaterfallReport(@Param('id') id: string, @Query('asOf') asOf?: string) {
    const contract = this.contracts.get(id);
    if (!contract) {
      throw new NotFoundException(`Revenue contract ${id} not found`);
    }
    const asOfDate = asOf ? new Date(asOf) : new Date();
    return this.amortizationService.generateWaterfallReport(contract, asOfDate);
  }

  @Post(':id/milestone')
  public updateMilestone(@Param('id') id: string, @Body() dto: MilestoneProgressDto) {
    const contract = this.contracts.get(id);
    if (!contract) {
      throw new NotFoundException(`Revenue contract ${id} not found`);
    }

    const obl = contract.obligations.find(o => o.id === dto.obligationId);
    if (!obl) {
      throw new NotFoundException(`Obligation ${dto.obligationId} not found in contract ${id}`);
    }

    const incrementalRevenue = obl.updateMilestoneProgress(dto.newPercentComplete);
    contract.checkAndMarkFulfillment();

    return {
      obligationId: obl.id,
      percentComplete: obl.percentComplete,
      incrementalRevenueRecognized: incrementalRevenue,
      totalRecognizedRevenue: obl.totalRecognizedRevenue,
      deferredRevenueRemaining: obl.deferredRevenueBalance,
      obligationStatus: obl.status,
      contractStatus: contract.status,
    };
  }

  @Post(':id/close-period')
  public closeAccountingPeriod(@Param('id') id: string, @Body() dto: ClosePeriodDto) {
    const contract = this.contracts.get(id);
    if (!contract) {
      throw new NotFoundException(`Revenue contract ${id} not found`);
    }

    const result = this.amortizationService.postPeriodRevenue(contract, dto.accountingPeriod);
    return {
      period: dto.accountingPeriod,
      postedLinesCount: result.postedLinesCount,
      totalPostedRevenue: result.totalPostedAmount,
      contractRecognizedToDate: contract.getTotalRecognizedRevenue(),
      contractDeferredRemaining: contract.getTotalDeferredRevenue(),
    };
  }
}
