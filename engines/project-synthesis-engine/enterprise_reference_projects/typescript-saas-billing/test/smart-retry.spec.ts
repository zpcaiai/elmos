/**
 * Advanced Dunning & Smart Retry Unit Tests
 */

import { DeclineType, DunningActionType, DunningCampaignStatus } from '../src/modules/dunning-advanced/domain/entities/dunning-campaign.entity';
import { SmartRetryService } from '../src/modules/dunning-advanced/domain/services/smart-retry.service';
import { DunningOrchestratorService } from '../src/modules/dunning-advanced/domain/services/dunning-orchestrator.service';

describe('Advanced Dunning & Smart Retry Engine', () => {
  let smartRetry: SmartRetryService;
  let orchestrator: DunningOrchestratorService;

  beforeEach(() => {
    smartRetry = new SmartRetryService();
    orchestrator = new DunningOrchestratorService(smartRetry);
  });

  it('should suppress automated retries for hard declines and schedule customer notification', () => {
    const campaign = orchestrator.handlePaymentFailure({
      customerId: 'cust-stolen-card',
      subscriptionId: 'sub-stolen',
      invoiceId: 'inv-stolen',
      amount: 150,
      declineCode: 'stolen_card',
    });

    expect(campaign.declineType).toBe(DeclineType.HARD);
    expect(campaign.stages[0].retryPayment).toBe(false);
    expect(campaign.stages[0].action).toBe(DunningActionType.EMAIL_NOTIFICATION);

    const rec = smartRetry.calculateOptimalRetry({
      declineType: DeclineType.HARD,
      declineCode: 'stolen_card',
      attemptNumber: 1,
    });
    expect(rec.confidenceScore).toBe(0.0);
    expect(rec.strategyUsed).toBe('HARD_DECLINE_SUPPRESSION');
  });

  it('should optimize retry schedules for soft decline avoiding weekends and aligning with paydays', () => {
    // Starting on a Thursday so +2 days is Saturday -> should shift to Monday
    const baseDate = new Date('2026-03-05T12:00:00Z'); // Thursday
    const rec = smartRetry.calculateOptimalRetry({
      declineType: DeclineType.SOFT,
      declineCode: 'insufficient_funds',
      attemptNumber: 1,
      customerTimezoneOffsetHours: -5, // US Eastern
      baseScheduledDate: baseDate,
    });

    expect(rec.isCompliantWithCardNetworks).toBe(true);
    expect(rec.confidenceScore).toBeGreaterThan(0.6);
    // Should not fall on Saturday or Sunday
    const day = rec.recommendedTimestamp.getUTCDay();
    expect(day).not.toBe(6);
    expect(day).not.toBe(0);
  });

  it('should progressively degrade subscription entitlements through dunning stages and restore upon recovery', () => {
    const campaign = orchestrator.handlePaymentFailure({
      customerId: 'cust-overdue',
      subscriptionId: 'sub-overdue-1',
      invoiceId: 'inv-overdue-1',
      amount: 500,
      declineCode: 'insufficient_funds',
    });

    expect(campaign.status).toBe(DunningCampaignStatus.IN_PROGRESS);
    let ent = orchestrator.getEntitlements('sub-overdue-1')!;
    expect(ent.warningBannerActive).toBe(true);
    expect(ent.isReadOnly).toBe(false);

    // Advance 4 stages: email -> email -> banner -> restrict seats
    orchestrator.executeNextStage(campaign.id);
    orchestrator.executeNextStage(campaign.id);
    orchestrator.executeNextStage(campaign.id);
    const stage4Result = orchestrator.executeNextStage(campaign.id);

    expect(stage4Result.entitlement?.restrictedSeats).toBe(true);

    // Advance to stage 5: downgrade read-only
    const stage5Result = orchestrator.executeNextStage(campaign.id);
    expect(stage5Result.entitlement?.isReadOnly).toBe(true);

    // Customer pays invoice
    const recovered = orchestrator.handlePaymentSuccess('inv-overdue-1');
    expect(recovered).toBe(true);

    ent = orchestrator.getEntitlements('sub-overdue-1')!;
    expect(ent.isReadOnly).toBe(false);
    expect(ent.restrictedSeats).toBe(false);
    expect(ent.warningBannerActive).toBe(false);
    expect(campaign.status).toBe(DunningCampaignStatus.RECOVERED);
  });
});
