import { Controller, Post, Body, Get, Param, NotFoundException } from '@nestjs/common';
import { UsageRatingEngineService } from '../../domain/services/usage-rating-engine.service';
import { CreditDrawdownWaterfallService } from '../../domain/services/credit-drawdown-waterfall.service';
import { RatingMatrix, RatingResult } from '../../domain/entities/rating-matrix.entity';
import { PrepaidCreditGrant, DrawdownResult } from '../../domain/entities/prepaid-credit-grant.entity';
import {
  CreateRatingMatrixDto,
  RateUsageRequestDto,
  GrantPrepaidCreditsDto,
  ApplyDrawdownRequestDto,
} from '../dtos/usage-rating.dto';

@Controller('rating')
export class UsageRatingController {
  private readonly matrices = new Map<string, RatingMatrix>();
  private readonly customerGrants = new Map<string, PrepaidCreditGrant[]>();

  constructor(
    private readonly ratingEngine: UsageRatingEngineService,
    private readonly drawdownService: CreditDrawdownWaterfallService
  ) {}

  @Post('matrices')
  public createMatrix(@Body() dto: CreateRatingMatrixDto): { status: string; matrixId: string } {
    const matrix: RatingMatrix = {
      matrixId: dto.matrixId,
      metricCode: dto.metricCode,
      currency: dto.currency,
      pricingModel: dto.pricingModel,
      tiers: dto.tiers,
      minimumCommitmentCents: dto.minimumCommitmentCents ?? 0,
      surgeMultiplier: dto.surgeMultiplier ?? 1.0,
      effectiveFrom: new Date(dto.effectiveFrom),
      effectiveTo: dto.effectiveTo ? new Date(dto.effectiveTo) : null,
    };

    this.matrices.set(matrix.matrixId, matrix);
    return { status: 'CREATED', matrixId: matrix.matrixId };
  }

  @Post('rate')
  public rateUsage(@Body() dto: RateUsageRequestDto): RatingResult {
    const matrix = this.matrices.get(dto.matrixId);
    if (!matrix) {
      throw new NotFoundException(`Pricing matrix ${dto.matrixId} not found`);
    }

    return this.ratingEngine.rateUsage(dto.units, matrix, {
      surgeMultiplier: dto.surgeMultiplier,
    });
  }

  @Post('credits/grant')
  public grantCredits(@Body() dto: GrantPrepaidCreditsDto): { status: string; grantId: string } {
    const grant: PrepaidCreditGrant = {
      grantId: dto.grantId,
      customerId: dto.customerId,
      bucketType: dto.bucketType,
      currency: dto.currency,
      initialCreditsCents: dto.amountCents,
      remainingCreditsCents: dto.amountCents,
      priorityRank: dto.priorityRank ?? 20,
      grantedAt: new Date(),
      expiresAt: dto.expiresAt ? new Date(dto.expiresAt) : null,
      applicableMetricCodes: dto.applicableMetricCodes ?? [],
      isRolloverEligible: true,
    };

    const existing = this.customerGrants.get(dto.customerId) ?? [];
    existing.push(grant);
    this.customerGrants.set(dto.customerId, existing);

    return { status: 'GRANTED', grantId: grant.grantId };
  }

  @Post('credits/drawdown')
  public applyDrawdown(@Body() dto: ApplyDrawdownRequestDto): DrawdownResult {
    const grants = this.customerGrants.get(dto.customerId) ?? [];
    return this.drawdownService.executeDrawdown(
      dto.customerId,
      dto.chargeAmountCents,
      dto.metricCode,
      grants
    );
  }

  @Get('credits/:customerId')
  public getCustomerCreditBalance(@Param('customerId') customerId: string): {
    customerId: string;
    totalBalanceCents: number;
    activeGrantsCount: number;
  } {
    const grants = this.customerGrants.get(customerId) ?? [];
    const totalBalanceCents = grants.reduce((sum, g) => sum + g.remainingCreditsCents, 0);
    return {
      customerId,
      totalBalanceCents,
      activeGrantsCount: grants.filter(g => g.remainingCreditsCents > 0).length,
    };
  }
}
