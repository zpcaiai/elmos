import {
  CustomerHierarchyNode,
} from '../src/modules/customer-hierarchy-invoicing/domain/entities/hierarchy-node.entity';
import {
  HierarchyRollupBillingService,
  RawSubsidiaryUsageInput,
} from '../src/modules/customer-hierarchy-invoicing/domain/services/hierarchy-rollup-billing.service';

describe('Customer Hierarchy Invoicing & Group Volume Rollup', () => {
  let service: HierarchyRollupBillingService;

  beforeEach(() => {
    service = new HierarchyRollupBillingService();
  });

  it('should resolve volume discount tiers based on aggregated group consumption', () => {
    expect(service.resolveGroupVolumeDiscount(5_000).discountRate).toBe(0.00);
    expect(service.resolveGroupVolumeDiscount(15_000).discountRate).toBe(0.10);
    expect(service.resolveGroupVolumeDiscount(60_000).discountRate).toBe(0.15);
    expect(service.resolveGroupVolumeDiscount(120_000).discountRate).toBe(0.25);
  });

  it('should consolidate multi-subsidiary billing, apply global volume discount, and split centralized vs decentralized charges', () => {
    const parentHq: CustomerHierarchyNode = {
      customerId: 'CUST-PARENT-HQ',
      legalEntityName: 'Acme Global Holdings Inc.',
      country: 'USA',
      hierarchyLevel: 0,
      billingResponsibility: 'CENTRALIZED_PARENT',
    };

    const subUk: CustomerHierarchyNode = {
      customerId: 'CUST-SUB-UK',
      legalEntityName: 'Acme UK Technologies Ltd.',
      country: 'GBR',
      parentCustomerId: 'CUST-PARENT-HQ',
      hierarchyLevel: 1,
      billingResponsibility: 'CENTRALIZED_PARENT', // 100% paid by HQ
    };

    const subDe: CustomerHierarchyNode = {
      customerId: 'CUST-SUB-DE',
      legalEntityName: 'Acme Germany GmbH',
      country: 'DEU',
      parentCustomerId: 'CUST-PARENT-HQ',
      hierarchyLevel: 1,
      billingResponsibility: 'DECENTRALIZED_SELF', // 100% paid by German entity
    };

    const subJp: CustomerHierarchyNode = {
      customerId: 'CUST-SUB-JP',
      legalEntityName: 'Acme Japan KK',
      country: 'JPN',
      parentCustomerId: 'CUST-PARENT-HQ',
      hierarchyLevel: 1,
      billingResponsibility: 'HYBRID_SPLIT', // 70% parent, 30% subsidiary
      splitRule: { parentPercentage: 0.70, subsidiaryPercentage: 0.30 },
    };

    const nodes = [parentHq, subUk, subDe, subJp];

    // Raw usage across subsidiaries:
    // UK: 30,000 units @ $0.50 = $15,000
    // DE: 20,000 units @ $0.50 = $10,000
    // JP: 10,000 units @ $0.50 = $5,000
    // Total Units = 60,000 -> unlocks Tier 2 Global Enterprise (15% discount)
    const rawUsage: RawSubsidiaryUsageInput[] = [
      {
        lineId: 'LINE-UK-01',
        subsidiaryCustomerId: 'CUST-SUB-UK',
        serviceDescription: 'Compute Core Usage (London)',
        unitsConsumed: 30_000,
        unitRateUsd: 0.50,
      },
      {
        lineId: 'LINE-DE-01',
        subsidiaryCustomerId: 'CUST-SUB-DE',
        serviceDescription: 'Data Pipeline Processing (Frankfurt)',
        unitsConsumed: 20_000,
        unitRateUsd: 0.50,
      },
      {
        lineId: 'LINE-JP-01',
        subsidiaryCustomerId: 'CUST-SUB-JP',
        serviceDescription: 'API Gateway Ingress (Tokyo)',
        unitsConsumed: 10_000,
        unitRateUsd: 0.50,
      },
    ];

    const groupInvoice = service.generateConsolidatedGroupInvoice(
      parentHq,
      nodes,
      rawUsage,
      '2026-06'
    );

    expect(groupInvoice.totalGroupUnitsConsumed).toBe(60_000);
    expect(groupInvoice.groupVolumeDiscountTierName).toBe('Tier 2 Global Enterprise');
    expect(groupInvoice.groupVolumeDiscountRate).toBe(0.15);

    // Gross total: $30,000.00
    expect(groupInvoice.totalGrossChargesUsd).toBe(30000.00);
    // 15% discount: $4,500.00
    expect(groupInvoice.totalGroupVolumeDiscountUsd).toBe(4500.00);
    // Net total: $25,500.00
    expect(groupInvoice.totalNetChargesUsd).toBe(25500.00);

    // Breakdown:
    // UK Line: Gross $15k - 15% ($2,250) = Net $12,750.00 -> 100% Parent ($12,750.00)
    // DE Line: Gross $10k - 15% ($1,500) = Net $8,500.00 -> 100% Self ($8,500.00)
    // JP Line: Gross $5k - 15% ($750) = Net $4,250.00 -> 70% Parent ($2,975.00), 30% Self ($1,275.00)

    // Total Parent Billed: $12,750 + $2,975 = $15,725.00
    expect(groupInvoice.totalBilledToParentHqUsd).toBe(15725.00);
    // Total Subsidiary Direct Billed: $8,500 + $1,275 = $9,775.00
    expect(groupInvoice.totalBilledDirectToSubsidiariesUsd).toBe(9775.00);

    // Cent conservation check:
    expect(groupInvoice.totalBilledToParentHqUsd + groupInvoice.totalBilledDirectToSubsidiariesUsd).toBe(groupInvoice.totalNetChargesUsd);

    // Per-subsidiary summaries
    const ukSummary = groupInvoice.perSubsidiarySummaries.get('CUST-SUB-UK');
    expect(ukSummary?.discountedAmountUsd).toBe(12750.00);
    expect(ukSummary?.parentShareUsd).toBe(12750.00);
    expect(ukSummary?.selfShareUsd).toBe(0.00);

    const deSummary = groupInvoice.perSubsidiarySummaries.get('CUST-SUB-DE');
    expect(deSummary?.discountedAmountUsd).toBe(8500.00);
    expect(deSummary?.parentShareUsd).toBe(0.00);
    expect(deSummary?.selfShareUsd).toBe(8500.00);
  });

  it('should manage shared enterprise credit pool drawdown with per-subsidiary quota limits', () => {
    const openingBalance = 50_000.00; // $50,000 credit pool

    const requests = [
      { subsidiaryId: 'SUB-A', requestedAmountUsd: 30_000.00, maxQuotaUsd: 20_000.00 }, // Capped at $20k quota
      { subsidiaryId: 'SUB-B', requestedAmountUsd: 25_000.00 },                         // Takes $25k ($5k remaining)
      { subsidiaryId: 'SUB-C', requestedAmountUsd: 10_000.00 },                         // Only $5k left -> partial fill
    ];

    const result = service.drawdownSharedCreditPool(openingBalance, requests);

    expect(result.creditPoolOpeningBalanceUsd).toBe(50000.00);
    expect(result.totalDrawnUsd).toBe(50000.00);
    expect(result.creditPoolClosingBalanceUsd).toBe(0.00);
    expect(result.exhaustionStatus).toBe('POOL_EXHAUSTED');

    expect(result.subsidiaryAllocations.get('SUB-A')).toBe(20000.00);
    expect(result.subsidiaryAllocations.get('SUB-B')).toBe(25000.00);
    expect(result.subsidiaryAllocations.get('SUB-C')).toBe(5000.00);
  });
});
