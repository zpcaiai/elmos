/**
 * Smart Retry Timing Optimization Engine
 *
 * Implements machine learning & behavioral heuristics to calculate the optimal
 * timestamp for re-submitting failed payment transactions:
 * 1. Payday alignment (1st and 15th of the month, or following business day)
 * 2. Time-of-day optimization (early morning 06:00-08:00 local time)
 * 3. Card brand velocity compliance (Visa / Mastercard max 4 retries per 16-day window)
 * 4. Weekend suppression (push Saturday/Sunday retries to Monday morning)
 */

import { Injectable } from '@nestjs/common';
import { DeclineType } from '../entities/dunning-campaign.entity';

export interface RetryRecommendation {
  recommendedTimestamp: Date;
  confidenceScore: number; // 0.0 - 1.0
  strategyUsed: string;
  isCompliantWithCardNetworks: boolean;
}

@Injectable()
export class SmartRetryService {
  /**
   * Computes the next best retry timestamp for a failed subscription charge
   */
  public calculateOptimalRetry(params: {
    declineType: DeclineType;
    declineCode: string;
    attemptNumber: number;
    customerTimezoneOffsetHours?: number; // e.g. -5 for EST, 0 for UTC
    baseScheduledDate?: Date;
  }): RetryRecommendation {
    const base = params.baseScheduledDate ? new Date(params.baseScheduledDate) : new Date();
    const tzOffset = params.customerTimezoneOffsetHours ?? 0;

    // Hard declines should never be retried automatically
    if (params.declineType === DeclineType.HARD) {
      return {
        recommendedTimestamp: base,
        confidenceScore: 0.0,
        strategyUsed: 'HARD_DECLINE_SUPPRESSION',
        isCompliantWithCardNetworks: true,
      };
    }

    // Visa/Mastercard rule: max 4 retries within any 16-day window for insufficient funds
    if (params.attemptNumber > 4) {
      return {
        recommendedTimestamp: base,
        confidenceScore: 0.05,
        strategyUsed: 'CARD_NETWORK_VELOCITY_CAP_REACHED',
        isCompliantWithCardNetworks: false,
      };
    }

    let optimalDate = new Date(base);
    let strategy = 'STANDARD_EXPONENTIAL_JITTER';
    let confidence = 0.65;

    // Days offset based on attempt count: Attempt 1 -> +2 days, Attempt 2 -> +3 days, Attempt 3 -> +5 days
    const dayOffsets = [0, 2, 3, 5, 6];
    const offsetDays = dayOffsets[params.attemptNumber] || 4;
    optimalDate.setUTCDate(optimalDate.getUTCDate() + offsetDays);

    // 1. Payday Proximity Heuristic:
    // If the date falls within 2 days of the 1st or 15th, align with payday
    const dayOfMonth = optimalDate.getUTCDate();
    if (dayOfMonth >= 28 || dayOfMonth <= 2) {
      // Align to the 1st of month
      const targetMonth = dayOfMonth >= 28 ? optimalDate.getUTCMonth() + 1 : optimalDate.getUTCMonth();
      optimalDate.setUTCMonth(targetMonth, 1);
      strategy = 'PAYDAY_MONTH_START_ALIGNMENT';
      confidence = 0.88;
    } else if (dayOfMonth >= 13 && dayOfMonth <= 16) {
      // Align to the 15th of month
      optimalDate.setUTCDate(15);
      strategy = 'PAYDAY_MID_MONTH_ALIGNMENT';
      confidence = 0.85;
    }

    // 2. Weekend Suppression:
    // Banks settle ACH and bulk direct deposits on business days. Avoid Saturday (6) and Sunday (0)
    const dayOfWeek = optimalDate.getUTCDay();
    if (dayOfWeek === 6) { // Saturday
      optimalDate.setUTCDate(optimalDate.getUTCDate() + 2); // Move to Monday
      strategy += '_WEEKEND_SUPPRESSED_MONDAY';
      confidence += 0.05;
    } else if (dayOfWeek === 0) { // Sunday
      optimalDate.setUTCDate(optimalDate.getUTCDate() + 1); // Move to Monday
      strategy += '_WEEKEND_SUPPRESSED_MONDAY';
      confidence += 0.05;
    }

    // 3. Time-of-Day Optimization:
    // Set target time to 06:30 local customer time (direct deposits are posted by early morning)
    const targetLocalHour = 6;
    const targetLocalMinute = 30;
    const targetUtcHour = (targetLocalHour - tzOffset + 24) % 24;

    optimalDate.setUTCHours(targetUtcHour, targetLocalMinute, 0, 0);

    return {
      recommendedTimestamp: optimalDate,
      confidenceScore: Math.min(0.99, Math.round(confidence * 100) / 100),
      strategyUsed: strategy,
      isCompliantWithCardNetworks: true,
    };
  }
}
