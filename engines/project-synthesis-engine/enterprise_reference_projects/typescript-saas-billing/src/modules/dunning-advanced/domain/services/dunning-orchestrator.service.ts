/**
 * Dunning Campaign Orchestration Service
 *
 * Coordinates execution of dunning campaigns, communicating with payment gateways,
 * updating subscription entitlement tiers, and notifying customers.
 */

import { Injectable } from '@nestjs/common';
import {
  DunningCampaign,
  DeclineType,
  DunningActionType,
  DunningCampaignStatus,
  CampaignStageStatus,
} from '../entities/dunning-campaign.entity';
import { SmartRetryService } from './smart-retry.service';

export interface EntitlementStatus {
  subscriptionId: string;
  isReadOnly: boolean;
  isCancelled: boolean;
  warningBannerActive: boolean;
  restrictedSeats: boolean;
}

@Injectable()
export class DunningOrchestratorService {
  private campaigns: Map<string, DunningCampaign> = new Map();
  private entitlements: Map<string, EntitlementStatus> = new Map();

  constructor(private readonly smartRetry: SmartRetryService) {}

  /**
   * Initializes or fetches an active dunning campaign upon payment failure
   */
  public handlePaymentFailure(params: {
    customerId: string;
    subscriptionId: string;
    invoiceId: string;
    amount: number;
    declineCode: string;
    customerTzOffset?: number;
  }): DunningCampaign {
    // Classify decline code
    const hardDeclineCodes = new Set(['stolen_card', 'lost_card', 'pickup_card', 'invalid_account', 'fraudulent']);
    const isHard = hardDeclineCodes.has(params.declineCode.toLowerCase());

    const campaignId = `dunn-${params.invoiceId}`;
    const campaign = new DunningCampaign({
      id: campaignId,
      customerId: params.customerId,
      subscriptionId: params.subscriptionId,
      invoiceId: params.invoiceId,
      outstandingAmount: params.amount,
      declineCode: params.declineCode,
      declineType: isHard ? DeclineType.HARD : DeclineType.SOFT,
    });

    // Initialize entitlement status (still normal in initial grace period)
    this.entitlements.set(params.subscriptionId, {
      subscriptionId: params.subscriptionId,
      isReadOnly: false,
      isCancelled: false,
      warningBannerActive: true,
      restrictedSeats: false,
    });

    // Schedule optimal retry for soft decline stages
    if (!isHard) {
      for (const stage of campaign.stages) {
        if (stage.retryPayment) {
          const rec = this.smartRetry.calculateOptimalRetry({
            declineType: DeclineType.SOFT,
            declineCode: params.declineCode,
            attemptNumber: stage.stageNumber,
            customerTimezoneOffsetHours: params.customerTzOffset ?? 0,
            baseScheduledDate: stage.scheduledAt,
          });
          stage.scheduledAt = rec.recommendedTimestamp;
        }
      }
    }

    this.campaigns.set(campaign.id, campaign);
    return campaign;
  }

  /**
   * Executes the next due stage of a dunning campaign
   */
  public executeNextStage(campaignId: string): {
    actionExecuted: DunningActionType | null;
    campaignStatus: DunningCampaignStatus;
    entitlement: EntitlementStatus | undefined;
  } {
    const campaign = this.campaigns.get(campaignId);
    if (!campaign) {
      throw new Error(`Campaign ${campaignId} not found`);
    }

    const stage = campaign.advanceStage('Stage action executed successfully');
    if (!stage) {
      return {
        actionExecuted: null,
        campaignStatus: campaign.status,
        entitlement: this.entitlements.get(campaign.subscriptionId),
      };
    }

    // Apply entitlement changes based on action
    const ent = this.entitlements.get(campaign.subscriptionId) || {
      subscriptionId: campaign.subscriptionId,
      isReadOnly: false,
      isCancelled: false,
      warningBannerActive: true,
      restrictedSeats: false,
    };

    switch (stage.action) {
      case DunningActionType.RESTRICT_SEATS:
        ent.restrictedSeats = true;
        break;
      case DunningActionType.DOWNGRADE_READONLY:
        ent.isReadOnly = true;
        break;
      case DunningActionType.CANCEL_SUBSCRIPTION:
        ent.isCancelled = true;
        ent.isReadOnly = true;
        campaign.status = DunningCampaignStatus.TERMINATED;
        break;
      default:
        break;
    }

    this.entitlements.set(campaign.subscriptionId, ent);

    return {
      actionExecuted: stage.action,
      campaignStatus: campaign.status,
      entitlement: ent,
    };
  }

  /**
   * Resolves campaign when customer successfully updates card or payment succeeds
   */
  public handlePaymentSuccess(invoiceId: string): boolean {
    const campaignId = `dunn-${invoiceId}`;
    const campaign = this.campaigns.get(campaignId);
    if (!campaign || campaign.status !== DunningCampaignStatus.IN_PROGRESS) {
      return false;
    }

    campaign.markRecovered();

    // Restore full entitlements
    const ent = this.entitlements.get(campaign.subscriptionId);
    if (ent) {
      ent.isReadOnly = false;
      ent.isCancelled = false;
      ent.warningBannerActive = false;
      ent.restrictedSeats = false;
      this.entitlements.set(campaign.subscriptionId, ent);
    }

    return true;
  }

  public getCampaign(id: string): DunningCampaign | undefined {
    return this.campaigns.get(id);
  }

  public getEntitlements(subscriptionId: string): EntitlementStatus | undefined {
    return this.entitlements.get(subscriptionId);
  }
}
