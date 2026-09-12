import {
  Controller,
  Get,
  Post,
  Body,
  Param,
  Headers,
  UseGuards,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { TenantIsolationGuard } from '../guards/tenant-isolation.guard';
import { CreateSubscriptionDto, UpgradePlanDto, AdjustSeatsDto } from '../dtos/subscription.dto';
import { SubscriptionRepository } from '../../domain/repositories/billing-repository.interface';
import { SubscriptionAggregate, SubscriptionPlan } from '../../domain/entities/subscription.entity';
import { ProrationService } from '../../domain/services/proration.service';

@Controller('api/v1/subscriptions')
@UseGuards(TenantIsolationGuard)
export class SubscriptionController {
  constructor(
    private readonly subscriptionRepo: SubscriptionRepository,
    private readonly prorationService: ProrationService
  ) {}

  @Post()
  async createSubscription(
    @Headers('x-tenant-id') tenantId: string,
    @Body() dto: CreateSubscriptionDto
  ) {
    const plan: SubscriptionPlan = {
      planId: dto.planId,
      code: dto.planCode,
      name: dto.planName,
      billingCycle: dto.billingCycle,
      basePriceCents: dto.basePriceCents,
      includedSeats: dto.includedSeats,
      perSeatPriceCents: dto.perSeatPriceCents,
      features: [],
      trialDays: 14,
    };

    const sub = new SubscriptionAggregate({
      subscriptionId: `sub_${Date.now()}`,
      tenantId,
      customerId: dto.customerId,
      plan,
      seats: dto.initialSeats ?? dto.includedSeats,
    });

    await this.subscriptionRepo.save(sub);
    return { success: true, data: sub };
  }

  @Get(':id')
  async getSubscription(
    @Headers('x-tenant-id') tenantId: string,
    @Param('id') id: string
  ) {
    const sub = await this.subscriptionRepo.findById(tenantId, id);
    if (!sub) {
      throw new NotFoundException(`Subscription ${id} not found`);
    }
    return { success: true, data: sub };
  }

  @Post(':id/upgrade')
  async upgradePlan(
    @Headers('x-tenant-id') tenantId: string,
    @Param('id') id: string,
    @Body() dto: UpgradePlanDto
  ) {
    const sub = await this.subscriptionRepo.findById(tenantId, id);
    if (!sub) {
      throw new NotFoundException(`Subscription ${id} not found`);
    }

    const newPlan: SubscriptionPlan = {
      planId: dto.newPlanId,
      code: dto.newPlanCode,
      name: dto.newPlanName,
      billingCycle: dto.newBillingCycle,
      basePriceCents: dto.newBasePriceCents,
      includedSeats: dto.newIncludedSeats,
      perSeatPriceCents: dto.newPerSeatPriceCents,
      features: [],
      trialDays: 0,
    };

    const proration = this.prorationService.calculatePlanChangeProration({
      subscription: sub,
      newPlan,
    });

    sub.changePlan(newPlan);
    await this.subscriptionRepo.save(sub);

    return {
      success: true,
      data: {
        subscription: sub,
        proration,
      },
    };
  }

  @Post(':id/seats')
  async adjustSeats(
    @Headers('x-tenant-id') tenantId: string,
    @Param('id') id: string,
    @Body() dto: AdjustSeatsDto
  ) {
    const sub = await this.subscriptionRepo.findById(tenantId, id);
    if (!sub) {
      throw new NotFoundException(`Subscription ${id} not found`);
    }

    const proration = this.prorationService.calculateSeatAdjustmentProration({
      subscription: sub,
      newSeatCount: dto.newSeatCount,
    });

    sub.updateSeats(dto.newSeatCount);
    await this.subscriptionRepo.save(sub);

    return {
      success: true,
      data: {
        subscription: sub,
        proration,
      },
    };
  }
}
