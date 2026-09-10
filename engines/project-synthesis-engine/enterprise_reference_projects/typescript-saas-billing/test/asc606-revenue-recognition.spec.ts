/**
 * ASC 606 / IFRS 15 Revenue Recognition Comprehensive Unit Tests
 */

import { RevenueContract, ContractStatus, ModificationType } from '../src/modules/revenue-recognition/domain/entities/revenue-contract.entity';
import { PerformanceObligation, ObligationType, SatisfactionPattern, SSPEstimationMethod, ObligationStatus } from '../src/modules/revenue-recognition/domain/entities/performance-obligation.entity';
import { Asc606AllocationService } from '../src/modules/revenue-recognition/domain/services/asc606-allocation.service';
import { RevenueAmortizationService } from '../src/modules/revenue-recognition/domain/services/revenue-amortization.service';

describe('ASC 606 Revenue Recognition Engine', () => {
  let allocationService: Asc606AllocationService;
  let amortizationService: RevenueAmortizationService;

  beforeEach(() => {
    allocationService = new Asc606AllocationService();
    amortizationService = new RevenueAmortizationService();
  });

  it('should allocate bundled transaction price proportionally based on relative Standalone Selling Prices (SSP)', () => {
    // Contract bundle: 1-year SaaS subscription (SSP $12,000) + Implementation Service (SSP $3,000) = Total SSP $15,000
    // Discounted bundled commercial price: $10,000 (a $5,000 discount)
    const contract = new RevenueContract({
      id: 'ctr-001',
      customerId: 'cust-corp-1',
      contractNumber: 'CNT-2026-001',
      startDate: new Date('2026-01-01T00:00:00Z'),
      endDate: new Date('2026-12-31T23:59:59Z'),
      totalTransactionPrice: 10000,
    });

    const saasObl = new PerformanceObligation({
      id: 'obl-saas',
      contractId: 'ctr-001',
      name: 'Enterprise SaaS Access (12M)',
      obligationType: ObligationType.SAAS_SUBSCRIPTION,
      satisfactionPattern: SatisfactionPattern.OVER_TIME_RATABLE,
      sspMethod: SSPEstimationMethod.OBSERVABLE_PRICE,
      standaloneSellingPrice: 12000,
      startDate: new Date('2026-01-01T00:00:00Z'),
      endDate: new Date('2026-12-31T23:59:59Z'),
    });

    const psoObl = new PerformanceObligation({
      id: 'obl-pso',
      contractId: 'ctr-001',
      name: 'Implementation & Data Migration',
      obligationType: ObligationType.PROFESSIONAL_SERVICES,
      satisfactionPattern: SatisfactionPattern.OVER_TIME_MILESTONE,
      sspMethod: SSPEstimationMethod.COST_PLUS_MARGIN,
      standaloneSellingPrice: 3000,
      startDate: new Date('2026-01-01T00:00:00Z'),
      endDate: new Date('2026-03-31T23:59:59Z'),
    });

    contract.addObligation(saasObl);
    contract.addObligation(psoObl);

    const summary = allocationService.allocateTransactionPrice(contract);

    // SaaS is 12k/15k = 80% -> $8,000
    // PSO is 3k/15k = 20% -> $2,000
    expect(summary.totalTransactionPrice).toBe(10000);
    expect(summary.totalSSP).toBe(15000);
    expect(summary.totalDiscount).toBe(5000);

    const saasAlloc = summary.allocations.find(a => a.obligationId === 'obl-saas')!;
    const psoAlloc = summary.allocations.find(a => a.obligationId === 'obl-pso')!;

    expect(saasAlloc.allocatedAmount).toBe(8000);
    expect(psoAlloc.allocatedAmount).toBe(2000);

    contract.activate();
    expect(contract.status).toBe(ContractStatus.ACTIVE);
    expect(saasObl.deferredRevenueBalance).toBe(8000);
    expect(psoObl.deferredRevenueBalance).toBe(2000);
  });

  it('should generate monthly ratable straight-line schedules and reconcile to the exact penny', () => {
    const contract = new RevenueContract({
      id: 'ctr-002',
      customerId: 'cust-corp-2',
      contractNumber: 'CNT-2026-002',
      startDate: new Date('2026-01-01T00:00:00Z'),
      endDate: new Date('2026-12-31T23:59:59Z'),
      totalTransactionPrice: 10000,
    });

    const saasObl = new PerformanceObligation({
      id: 'obl-saas-ratable',
      contractId: 'ctr-002',
      name: 'Cloud Subscription',
      obligationType: ObligationType.SAAS_SUBSCRIPTION,
      satisfactionPattern: SatisfactionPattern.OVER_TIME_RATABLE,
      sspMethod: SSPEstimationMethod.OBSERVABLE_PRICE,
      standaloneSellingPrice: 10000,
      allocatedPrice: 10000,
      startDate: new Date('2026-01-01T00:00:00Z'),
      endDate: new Date('2026-12-31T23:59:59Z'),
    });

    const lines = amortizationService.generateRatableDailySchedule(saasObl);
    expect(lines.length).toBe(12); // 12 calendar months

    const sumRecognized = lines.reduce((sum, l) => sum + l.recognizedAmount, 0);
    expect(Math.round(sumRecognized * 100) / 100).toBe(10000);
    expect(lines[lines.length - 1].deferredRevenueRemaining).toBe(0);
  });

  it('should handle milestone completion and produce valid revenue waterfall report', () => {
    const contract = new RevenueContract({
      id: 'ctr-003',
      customerId: 'cust-corp-3',
      contractNumber: 'CNT-2026-003',
      startDate: new Date('2026-01-01T00:00:00Z'),
      endDate: new Date('2026-12-31T23:59:59Z'),
      totalTransactionPrice: 12000,
    });

    const psoObl = new PerformanceObligation({
      id: 'obl-pso-milestone',
      contractId: 'ctr-003',
      name: 'Custom Architecture Setup',
      obligationType: ObligationType.PROFESSIONAL_SERVICES,
      satisfactionPattern: SatisfactionPattern.OVER_TIME_MILESTONE,
      sspMethod: SSPEstimationMethod.OBSERVABLE_PRICE,
      standaloneSellingPrice: 12000,
      allocatedPrice: 12000,
      startDate: new Date('2026-01-01T00:00:00Z'),
      endDate: new Date('2026-06-30T23:59:59Z'),
    });

    contract.addObligation(psoObl);
    contract.activate();

    // 50% milestone completed in March
    const recognized50 = psoObl.updateMilestoneProgress(0.50);
    expect(recognized50).toBe(6000);
    expect(psoObl.totalRecognizedRevenue).toBe(6000);
    expect(psoObl.deferredRevenueBalance).toBe(6000);

    // Remaining 50% completed in May
    const recognized100 = psoObl.updateMilestoneProgress(1.0);
    expect(recognized100).toBe(6000);
    expect(psoObl.status).toBe(ObligationStatus.SATISFIED);
    expect(psoObl.totalRecognizedRevenue).toBe(12000);
    expect(psoObl.deferredRevenueBalance).toBe(0);

    const isFulfilled = contract.checkAndMarkFulfillment();
    expect(isFulfilled).toBe(true);
    expect(contract.status).toBe(ContractStatus.FULFILLED);
  });

  it('should accurately calculate variable consideration under conservative reversal constraints', () => {
    const result = allocationService.evaluateVariableConsideration({
      fixedPrice: 50000,
      scenarios: [
        { amount: 0, probability: 0.10 },
        { amount: 5000, probability: 0.20 },
        { amount: 10000, probability: 0.50 },
        { amount: 15000, probability: 0.20 },
      ],
      constraintFactor: 0.80,
    });

    expect(result.expectedValue).toBe(9000); // 0 + 1000 + 5000 + 3000 = 9000
    expect(result.constrainedTransactionPrice).toBe(55000); // Conservative lower band at 80% confidence
  });
});
