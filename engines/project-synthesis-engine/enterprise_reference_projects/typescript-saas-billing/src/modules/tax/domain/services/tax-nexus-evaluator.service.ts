/**
 * US Economic & Physical Nexus Determination Engine
 *
 * Implements post-Wayfair statutory threshold evaluation across all 50 US States
 * to determine where a SaaS merchant has established tax nexus and must collect tax.
 */

import { Injectable } from '@nestjs/common';

export interface StateNexusRule {
  stateCode: string;
  stateName: string;
  revenueThreshold: number;       // e.g. 100000 or 500000
  transactionThreshold: number;   // e.g. 200 or 0 (some states abolished count)
  evaluationPeriodMonths: number; // 12 months standard
  taxSaaSDigital: boolean;        // Does this state tax SaaS/digital goods?
}

export interface NexusEvaluationResult {
  stateCode: string;
  stateName: string;
  hasNexus: boolean;
  nexusReason?: 'PHYSICAL_PRESENCE' | 'ECONOMIC_REVENUE' | 'ECONOMIC_TRANSACTIONS' | 'VOLUNTARY_REGISTERED';
  grossSalesTrailing12M: number;
  transactionCountTrailing12M: number;
  revenueThreshold: number;
  transactionThreshold: number;
  revenuePercentageTowardsNexus: number;
  mustCollectTaxOnSaaS: boolean;
}

@Injectable()
export class TaxNexusEvaluatorService {
  // Statutory state thresholds for economic nexus
  private readonly stateNexusRules: Map<string, StateNexusRule> = new Map([
    ['CA', { stateCode: 'CA', stateName: 'California', revenueThreshold: 500000, transactionThreshold: 0, evaluationPeriodMonths: 12, taxSaaSDigital: false }],
    ['NY', { stateCode: 'NY', stateName: 'New York', revenueThreshold: 500000, transactionThreshold: 100, evaluationPeriodMonths: 12, taxSaaSDigital: true }],
    ['TX', { stateCode: 'TX', stateName: 'Texas', revenueThreshold: 500000, transactionThreshold: 0, evaluationPeriodMonths: 12, taxSaaSDigital: true }],
    ['WA', { stateCode: 'WA', stateName: 'Washington', revenueThreshold: 100000, transactionThreshold: 0, evaluationPeriodMonths: 12, taxSaaSDigital: true }],
    ['IL', { stateCode: 'IL', stateName: 'Illinois', revenueThreshold: 100000, transactionThreshold: 200, evaluationPeriodMonths: 12, taxSaaSDigital: true }],
    ['PA', { stateCode: 'PA', stateName: 'Pennsylvania', revenueThreshold: 100000, transactionThreshold: 0, evaluationPeriodMonths: 12, taxSaaSDigital: true }],
    ['OH', { stateCode: 'OH', stateName: 'Ohio', revenueThreshold: 100000, transactionThreshold: 200, evaluationPeriodMonths: 12, taxSaaSDigital: true }],
    ['FL', { stateCode: 'FL', stateName: 'Florida', revenueThreshold: 100000, transactionThreshold: 0, evaluationPeriodMonths: 12, taxSaaSDigital: false }],
    ['MA', { stateCode: 'MA', stateName: 'Massachusetts', revenueThreshold: 100000, transactionThreshold: 0, evaluationPeriodMonths: 12, taxSaaSDigital: true }],
    ['CO', { stateCode: 'CO', stateName: 'Colorado', revenueThreshold: 100000, transactionThreshold: 0, evaluationPeriodMonths: 12, taxSaaSDigital: true }],
    ['AZ', { stateCode: 'AZ', stateName: 'Arizona', revenueThreshold: 100000, transactionThreshold: 0, evaluationPeriodMonths: 12, taxSaaSDigital: true }],
    ['UT', { stateCode: 'UT', stateName: 'Utah', revenueThreshold: 100000, transactionThreshold: 200, evaluationPeriodMonths: 12, taxSaaSDigital: true }],
  ]);

  private physicalPresenceStates: Set<string> = new Set(['DE', 'CA']); // Headquarters / main servers

  /**
   * Evaluates economic nexus status for a given US state based on sales telemetry
   */
  public evaluateStateNexus(params: {
    stateCode: string;
    grossSales12M: number;
    transactionCount12M: number;
    hasPhysicalEmployees?: boolean;
    hasPhysicalOffices?: boolean;
    isVoluntarilyRegistered?: boolean;
  }): NexusEvaluationResult {
    const code = params.stateCode.toUpperCase();
    const rule = this.stateNexusRules.get(code) || {
      stateCode: code,
      stateName: `State of ${code}`,
      revenueThreshold: 100000, // Standard Wayfair fallback
      transactionThreshold: 200,
      evaluationPeriodMonths: 12,
      taxSaaSDigital: true,
    };

    // 1. Check physical nexus
    if (params.hasPhysicalEmployees || params.hasPhysicalOffices || this.physicalPresenceStates.has(code)) {
      return {
        stateCode: code,
        stateName: rule.stateName,
        hasNexus: true,
        nexusReason: 'PHYSICAL_PRESENCE',
        grossSalesTrailing12M: params.grossSales12M,
        transactionCountTrailing12M: params.transactionCount12M,
        revenueThreshold: rule.revenueThreshold,
        transactionThreshold: rule.transactionThreshold,
        revenuePercentageTowardsNexus: 100.0,
        mustCollectTaxOnSaaS: rule.taxSaaSDigital,
      };
    }

    // 2. Check voluntary registration
    if (params.isVoluntarilyRegistered) {
      return {
        stateCode: code,
        stateName: rule.stateName,
        hasNexus: true,
        nexusReason: 'VOLUNTARY_REGISTERED',
        grossSalesTrailing12M: params.grossSales12M,
        transactionCountTrailing12M: params.transactionCount12M,
        revenueThreshold: rule.revenueThreshold,
        transactionThreshold: rule.transactionThreshold,
        revenuePercentageTowardsNexus: 100.0,
        mustCollectTaxOnSaaS: rule.taxSaaSDigital,
      };
    }

    // 3. Check economic nexus revenue threshold
    const revenuePct = Math.min(100, Math.round((params.grossSales12M / rule.revenueThreshold) * 10000) / 100);
    if (params.grossSales12M >= rule.revenueThreshold) {
      return {
        stateCode: code,
        stateName: rule.stateName,
        hasNexus: true,
        nexusReason: 'ECONOMIC_REVENUE',
        grossSalesTrailing12M: params.grossSales12M,
        transactionCountTrailing12M: params.transactionCount12M,
        revenueThreshold: rule.revenueThreshold,
        transactionThreshold: rule.transactionThreshold,
        revenuePercentageTowardsNexus: revenuePct,
        mustCollectTaxOnSaaS: rule.taxSaaSDigital,
      };
    }

    // 4. Check economic nexus transaction count threshold
    if (rule.transactionThreshold > 0 && params.transactionCount12M >= rule.transactionThreshold) {
      return {
        stateCode: code,
        stateName: rule.stateName,
        hasNexus: true,
        nexusReason: 'ECONOMIC_TRANSACTIONS',
        grossSalesTrailing12M: params.grossSales12M,
        transactionCountTrailing12M: params.transactionCount12M,
        revenueThreshold: rule.revenueThreshold,
        transactionThreshold: rule.transactionThreshold,
        revenuePercentageTowardsNexus: revenuePct,
        mustCollectTaxOnSaaS: rule.taxSaaSDigital,
      };
    }

    // No nexus established yet
    return {
      stateCode: code,
      stateName: rule.stateName,
      hasNexus: false,
      grossSalesTrailing12M: params.grossSales12M,
      transactionCountTrailing12M: params.transactionCount12M,
      revenueThreshold: rule.revenueThreshold,
      transactionThreshold: rule.transactionThreshold,
      revenuePercentageTowardsNexus: revenuePct,
      mustCollectTaxOnSaaS: rule.taxSaaSDigital,
    };
  }

  /**
   * Adds or registers a physical presence jurisdiction
   */
  public registerPhysicalPresence(stateCode: string): void {
    this.physicalPresenceStates.add(stateCode.toUpperCase());
  }
}
