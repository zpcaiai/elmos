import { ASC606ModificationService } from '../src/modules/contract-modification/domain/services/asc606-modification.service';
import {
  ASC606ModificationAccountingTreatment,
  ContractModificationAmendment,
  ContractPerformanceObligation,
} from '../src/modules/contract-modification/domain/entities/contract-modification.entity';

describe('ASC 606 Contract Modification Accounting Engine', () => {
  let modificationService: ASC606ModificationService;

  beforeEach(() => {
    modificationService = new ASC606ModificationService();
  });

  it('should account for distinct additional products at Standalone Selling Price as SEPARATE CONTRACT', () => {
    const existingObligations: ContractPerformanceObligation[] = [
      {
        obligationId: 'OBL-ORIG-01',
        name: 'Enterprise Core Subscription (Year 1)',
        isDistinct: true,
        standaloneSellingPriceCents: 1200000, // $12,000/yr
        allocatedTransactionPriceCents: 1200000,
        recognizedRevenueCents: 600000, // $6,000 recognized over 6 months
        deferredRevenueCents: 600000,
        progressPercentage: 50.0,
        totalPeriodMonths: 12,
        remainingPeriodMonths: 6,
      },
    ];

    const amendment: ContractModificationAmendment = {
      amendmentId: 'AMD-ADD-SEATS-01',
      originalContractId: 'CTR-2026-001',
      effectiveDate: new Date('2026-07-01'),
      description: 'Add 20 additional Enterprise seats at regular catalogue list price',
      additionalConsiderationCents: 300000, // $3,000 for 6 months
      addedObligations: [
        {
          name: 'Additional 20 Enterprise Seats',
          isDistinct: true,
          isAtStandaloneSellingPrice: true,
          standaloneSellingPriceCents: 300000,
          offeredPriceCents: 300000,
          periodMonths: 6,
        },
      ],
      priceConcessionOnRemainingCents: 0,
    };

    const decision = modificationService.applyModification(amendment, existingObligations);

    expect(decision.treatment).toBe(ASC606ModificationAccountingTreatment.SEPARATE_CONTRACT);
    expect(decision.cumulativeCatchUpAdjustmentCents).toBe(0);
    expect(decision.revisedObligations).toHaveLength(2);
    expect(decision.totalRevisedContractValueCents).toBe(1500000); // $15,000 total

    // Existing obligation unrecognized deferred revenue remains unchanged
    expect(decision.revisedObligations[0].deferredRevenueCents).toBe(600000);
    // New obligation created with full offered price deferred
    expect(decision.revisedObligations[1].deferredRevenueCents).toBe(300000);
  });

  it('should apply PROSPECTIVE REALLOCATION when additional distinct goods are discounted below Standalone Selling Price', () => {
    // 1-year contract: $120,000 total ($10,000/mo).
    // After 6 months, $60,000 recognized, $60,000 deferred.
    // Amendment: Add 30 additional seats for remaining 6 months (Standalone value $30,000),
    // but offered as a renewal incentive for only $15,000 (50% discount).
    const existingObligations: ContractPerformanceObligation[] = [
      {
        obligationId: 'OBL-CORE',
        name: 'Enterprise Platform Access',
        isDistinct: true,
        standaloneSellingPriceCents: 60000, // Remaining 6-mo SSP is $60,000
        allocatedTransactionPriceCents: 120000,
        recognizedRevenueCents: 60000,
        deferredRevenueCents: 60000,
        progressPercentage: 50.0,
        totalPeriodMonths: 12,
        remainingPeriodMonths: 6,
      },
    ];

    const amendment: ContractModificationAmendment = {
      amendmentId: 'AMD-DISCOUNT-02',
      originalContractId: 'CTR-2026-002',
      effectiveDate: new Date('2026-07-01'),
      description: 'Add add-on modules at discounted incentive rate',
      additionalConsiderationCents: 15000, // $15,000 added
      addedObligations: [
        {
          name: 'Discounted Add-On Seat Pack',
          isDistinct: true,
          isAtStandaloneSellingPrice: false,
          standaloneSellingPriceCents: 30000, // Regular SSP is $30,000
          offeredPriceCents: 15000,
          periodMonths: 6,
        },
      ],
      priceConcessionOnRemainingCents: 0,
    };

    const decision = modificationService.applyModification(amendment, existingObligations);

    expect(decision.treatment).toBe(ASC606ModificationAccountingTreatment.PROSPECTIVE_REALLOCATION);
    expect(decision.cumulativeCatchUpAdjustmentCents).toBe(0);

    // Total remaining consideration pool to reallocate = $60,000 deferred + $15,000 new = $75,000.
    // Total remaining SSP = $60,000 + $30,000 = $90,000.
    // Existing share: 60k/90k = 2/3 -> 2/3 * $75,000 = $50,000 deferred allocated.
    // New share: 30k/90k = 1/3 -> 1/3 * $75,000 = $25,000 deferred allocated.
    expect(decision.revisedObligations).toHaveLength(2);
    expect(decision.revisedObligations[0].deferredRevenueCents).toBe(50000);
    expect(decision.revisedObligations[1].deferredRevenueCents).toBe(25000);

    // Total contract value = $60,000 recognized + $75,000 deferred = $135,000
    expect(decision.totalRevisedContractValueCents).toBe(135000);
    // Future monthly revenue = ($50,000 + $25,000) / 6 = $12,500/month
    expect(decision.futureRatableMonthlyRevenueCents).toBe(12500);
  });

  it('should recognize CUMULATIVE CATCH-UP adjustment immediately when remaining services are NOT distinct', () => {
    // Custom system integration project contracted for $100,000.
    // 60% complete based on hours incurred -> $60,000 recognized to date, $40,000 deferred.
    // Scope expansion: Client requests complex architectural adjustments adding $20,000 in fees.
    // Because milestone deliverables are interdependent and non-distinct, cumulative catch-up applies.
    const existingObligations: ContractPerformanceObligation[] = [
      {
        obligationId: 'OBL-CUSTOM-DEV',
        name: 'Custom Banking API Integration',
        isDistinct: false, // NOT distinct from ongoing modifications
        standaloneSellingPriceCents: 10000000, // $100,000
        allocatedTransactionPriceCents: 10000000,
        recognizedRevenueCents: 6000000, // $60,000 recognized (60%)
        deferredRevenueCents: 4000000,
        progressPercentage: 60.0,
        totalPeriodMonths: 10,
        remainingPeriodMonths: 4,
      },
    ];

    const amendment: ContractModificationAmendment = {
      amendmentId: 'AMD-CUSTOM-SCOPE-03',
      originalContractId: 'CTR-2026-003',
      effectiveDate: new Date('2026-07-01'),
      description: 'Scope change adding custom ISO20022 clearing transformers',
      additionalConsiderationCents: 2000000, // +$20,000
      addedObligations: [
        {
          name: 'ISO20022 Clearing Transformers (Interdependent)',
          isDistinct: false,
          isAtStandaloneSellingPrice: false,
          standaloneSellingPriceCents: 2000000,
          offeredPriceCents: 2000000,
          periodMonths: 4,
        },
      ],
      priceConcessionOnRemainingCents: 0,
    };

    const decision = modificationService.applyModification(amendment, existingObligations);

    expect(decision.treatment).toBe(ASC606ModificationAccountingTreatment.CUMULATIVE_CATCH_UP);
    // Revised contract value = $100,000 + $20,000 = $120,000 (12,000,000 cents).
    // Progress is 60%. Cumulative revenue to date should be 60% of $120,000 = $72,000 (7,200,000 cents).
    // Cumulative catch-up adjustment = $72,000 - $60,000 = +$12,000 (1,200,000 cents) recognized in current period!
    expect(decision.cumulativeCatchUpAdjustmentCents).toBe(1200000);
    expect(decision.totalRevisedContractValueCents).toBe(12000000);
    expect(decision.revisedObligations[0].recognizedRevenueCents).toBe(7200000);
    expect(decision.revisedObligations[0].deferredRevenueCents).toBe(4800000);
  });
});
