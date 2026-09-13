import {
  Controller,
  Get,
  Post,
  Body,
  Query,
  Headers,
  UseGuards,
} from '@nestjs/common';
import { TenantIsolationGuard } from '../guards/tenant-isolation.guard';
import { IngestMeterEventDto, QueryUsageDto } from '../dtos/usage.dto';
import { UsageAggregatorService } from '../../domain/services/usage-aggregator.service';
import { MeterEvent } from '../../domain/entities/usage-record.entity';

@Controller('api/v1/usage')
@UseGuards(TenantIsolationGuard)
export class UsageController {
  constructor(private readonly usageAggregator: UsageAggregatorService) {}

  @Post('events')
  async ingestMeterEvent(
    @Headers('x-tenant-id') tenantId: string,
    @Body() dto: IngestMeterEventDto
  ) {
    const event: MeterEvent = {
      eventId: `evt_${Date.now()}_${Math.random().toString(36).substring(7)}`,
      tenantId,
      customerId: dto.customerId,
      subscriptionId: dto.subscriptionId,
      metricKey: dto.metricKey,
      value: dto.value,
      uniqueProperty: dto.uniqueProperty,
      timestamp: new Date(),
      idempotencyKey: dto.idempotencyKey,
    };

    const accepted = this.usageAggregator.ingestEvent(event);
    return {
      success: true,
      data: {
        accepted,
        eventId: event.eventId,
      },
    };
  }

  @Get()
  async getUsage(
    @Headers('x-tenant-id') tenantId: string,
    @Query('customerId') customerId: string,
    @Query('metricKey') metricKey: string,
    @Query('from') from?: string,
    @Query('to') to?: string
  ) {
    const fromDate = from ? new Date(from) : undefined;
    const toDate = to ? new Date(to) : undefined;

    const totalUsage = this.usageAggregator.getAggregatedUsage(
      tenantId,
      customerId,
      metricKey,
      fromDate,
      toDate
    );

    return {
      success: true,
      data: {
        tenantId,
        customerId,
        metricKey,
        totalUsage,
        period: {
          from: fromDate,
          to: toDate,
        },
      },
    };
  }
}
