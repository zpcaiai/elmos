/**
 * Advanced Dunning Campaign & Behavioral Schedule Entities
 *
 * Implements granular customer dunning workflows:
 * - Distinguishes between Soft Decline (insufficient funds, temporary processor outage, rate limit)
 *   and Hard Decline (stolen card, lost card, closed account, do-not-honor).
 * - Multi-stage escalation (Day 1, 3, 5, 7, 10, 14, 21).
 * - Progressive entitlement throttling: Grace Period -> Warning Banner -> Read-Only Lock -> Cancellation.
 */

export enum DeclineType {
  SOFT = 'SOFT', // Retryable (insufficient funds, try again later)
  HARD = 'HARD', // Permanent (card stolen, invalid account, fraud)
}

export enum DunningActionType {
  EMAIL_NOTIFICATION = 'EMAIL_NOTIFICATION',
  SMS_ALERT = 'SMS_ALERT',
  IN_APP_BANNER = 'IN_APP_BANNER',
  RESTRICT_SEATS = 'RESTRICT_SEATS',
  DOWNGRADE_READONLY = 'DOWNGRADE_READONLY',
  CANCEL_SUBSCRIPTION = 'CANCEL_SUBSCRIPTION',
}

export enum CampaignStageStatus {
  SCHEDULED = 'SCHEDULED',
  EXECUTED = 'EXECUTED',
  SKIPPED = 'SKIPPED',
  FAILED = 'FAILED',
}

export interface DunningStage {
  stageNumber: number;
  offsetDays: number;
  action: DunningActionType;
  retryPayment: boolean;
  status: CampaignStageStatus;
  scheduledAt: Date;
  executedAt?: Date;
  outcomeNote?: string;
}

export enum DunningCampaignStatus {
  IN_PROGRESS = 'IN_PROGRESS',
  RECOVERED = 'RECOVERED',
  EXHAUSTED = 'EXHAUSTED',
  TERMINATED = 'TERMINATED',
}

export class DunningCampaign {
  public id: string;
  public customerId: string;
  public subscriptionId: string;
  public invoiceId: string;
  public outstandingAmount: number;
  public currency: string;
  public declineCode: string;
  public declineType: DeclineType;
  public status: DunningCampaignStatus;
  public stages: DunningStage[];
  public currentStageIndex: number;
  public attemptsCount: number;
  public recoveredAt?: Date;
  public createdAt: Date;
  public updatedAt: Date;

  constructor(params: {
    id: string;
    customerId: string;
    subscriptionId: string;
    invoiceId: string;
    outstandingAmount: number;
    currency?: string;
    declineCode: string;
    declineType: DeclineType;
  }) {
    this.id = params.id;
    this.customerId = params.customerId;
    this.subscriptionId = params.subscriptionId;
    this.invoiceId = params.invoiceId;
    this.outstandingAmount = Math.round(params.outstandingAmount * 100) / 100;
    this.currency = params.currency || 'USD';
    this.declineCode = params.declineCode;
    this.declineType = params.declineType;
    this.status = DunningCampaignStatus.IN_PROGRESS;
    this.currentStageIndex = 0;
    this.attemptsCount = 1;
    this.stages = [];
    this.createdAt = new Date();
    this.updatedAt = new Date();

    this.buildStandardSchedule();
  }

  /**
   * Constructs the multi-stage dunning progression based on decline type
   */
  private buildStandardSchedule(): void {
    const now = this.createdAt.getTime();
    const dayMs = 24 * 60 * 60 * 1000;

    if (this.declineType === DeclineType.HARD) {
      // Hard declines require immediate customer intervention; no blind retries
      this.stages = [
        {
          stageNumber: 1,
          offsetDays: 0,
          action: DunningActionType.EMAIL_NOTIFICATION,
          retryPayment: false,
          status: CampaignStageStatus.SCHEDULED,
          scheduledAt: new Date(now),
        },
        {
          stageNumber: 2,
          offsetDays: 3,
          action: DunningActionType.IN_APP_BANNER,
          retryPayment: false,
          status: CampaignStageStatus.SCHEDULED,
          scheduledAt: new Date(now + 3 * dayMs),
        },
        {
          stageNumber: 3,
          offsetDays: 7,
          action: DunningActionType.DOWNGRADE_READONLY,
          retryPayment: false,
          status: CampaignStageStatus.SCHEDULED,
          scheduledAt: new Date(now + 7 * dayMs),
        },
        {
          stageNumber: 4,
          offsetDays: 14,
          action: DunningActionType.CANCEL_SUBSCRIPTION,
          retryPayment: false,
          status: CampaignStageStatus.SCHEDULED,
          scheduledAt: new Date(now + 14 * dayMs),
        },
      ];
    } else {
      // Soft declines (e.g. insufficient funds): smart retries interleaved with notices
      this.stages = [
        {
          stageNumber: 1,
          offsetDays: 1,
          action: DunningActionType.EMAIL_NOTIFICATION,
          retryPayment: true,
          status: CampaignStageStatus.SCHEDULED,
          scheduledAt: new Date(now + 1 * dayMs),
        },
        {
          stageNumber: 2,
          offsetDays: 3,
          action: DunningActionType.EMAIL_NOTIFICATION,
          retryPayment: true,
          status: CampaignStageStatus.SCHEDULED,
          scheduledAt: new Date(now + 3 * dayMs),
        },
        {
          stageNumber: 3,
          offsetDays: 5,
          action: DunningActionType.IN_APP_BANNER,
          retryPayment: true,
          status: CampaignStageStatus.SCHEDULED,
          scheduledAt: new Date(now + 5 * dayMs),
        },
        {
          stageNumber: 4,
          offsetDays: 7,
          action: DunningActionType.RESTRICT_SEATS,
          retryPayment: true,
          status: CampaignStageStatus.SCHEDULED,
          scheduledAt: new Date(now + 7 * dayMs),
        },
        {
          stageNumber: 5,
          offsetDays: 10,
          action: DunningActionType.DOWNGRADE_READONLY,
          retryPayment: true,
          status: CampaignStageStatus.SCHEDULED,
          scheduledAt: new Date(now + 10 * dayMs),
        },
        {
          stageNumber: 6,
          offsetDays: 14,
          action: DunningActionType.CANCEL_SUBSCRIPTION,
          retryPayment: false,
          status: CampaignStageStatus.SCHEDULED,
          scheduledAt: new Date(now + 14 * dayMs),
        },
      ];
    }
  }

  /**
   * Marks campaign successfully recovered upon successful payment
   */
  public markRecovered(): void {
    this.status = DunningCampaignStatus.RECOVERED;
    this.recoveredAt = new Date();
    this.updatedAt = new Date();
    // Cancel remaining stages
    for (let i = this.currentStageIndex; i < this.stages.length; i++) {
      if (this.stages[i].status === CampaignStageStatus.SCHEDULED) {
        this.stages[i].status = CampaignStageStatus.SKIPPED;
        this.stages[i].outcomeNote = 'Payment successfully recovered';
      }
    }
  }

  /**
   * Advances the campaign to the next scheduled stage
   */
  public advanceStage(outcomeNote: string): DunningStage | null {
    if (this.status !== DunningCampaignStatus.IN_PROGRESS) return null;
    if (this.currentStageIndex >= this.stages.length) {
      this.status = DunningCampaignStatus.EXHAUSTED;
      return null;
    }

    const currentStage = this.stages[this.currentStageIndex];
    currentStage.status = CampaignStageStatus.EXECUTED;
    currentStage.executedAt = new Date();
    currentStage.outcomeNote = outcomeNote;

    this.attemptsCount++;
    this.currentStageIndex++;
    this.updatedAt = new Date();

    if (this.currentStageIndex >= this.stages.length) {
      this.status = DunningCampaignStatus.EXHAUSTED;
    }

    return currentStage;
  }
}
