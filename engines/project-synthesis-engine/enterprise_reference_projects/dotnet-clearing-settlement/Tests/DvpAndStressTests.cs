namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;

public static class DvpAndStressTests
{
    public static void Run()
    {
        Console.WriteLine("Running DvpAndStressTests...");
        TestAtomicDvpModel3Settlement();
        TestCollateralOptimizationCheapestToDeliver();
        TestCover1AndCover2LiquidityStress();
        Console.WriteLine("  ✓ DvpAndStressTests passed successfully.");
    }

    private static void TestAtomicDvpModel3Settlement()
    {
        var currency = Currency.USD;
        var batch = new SettlementBatch("B-DVP-01", "DVP-CYC-1", DateTime.UtcNow, currency);
        var isin = SecurityId.Parse("US0378331005");

        // Bank A buys 1,000 Apple shares from Bank B @ $100 ($100,000)
        var trade = new TradeContract("T-1", "BankA", "BankB", isin, CashAmount.FromDecimal(100m, currency), Quantity.Of(1000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1));
        batch.AddTrade(trade);
        batch.StartNovation();
        trade.MarkNovated();

        var nettingEngine = new MultilateralNettingEngine();
        nettingEngine.ExecuteMultilateralNetting(batch);

        batch.MoveToMargining();
        batch.MoveToSettling();

        // Setup Vaults:
        // Bank A needs: $100,000 cash. Has: $150,000 cash, 0 shares.
        // Bank B needs: 1,000 shares. Has: $0 cash, 1,000 shares.
        var vaults = new Dictionary<string, DvPSettlementEngine.MemberVault>
        {
            ["BankA"] = new DvPSettlementEngine.MemberVault("BankA", CashAmount.FromDecimal(150000m, currency)),
            ["BankB"] = new DvPSettlementEngine.MemberVault("BankB", CashAmount.Zero(currency))
        };
        vaults["BankB"].CreditSecurities(isin, Quantity.Of(1000));

        var dvpEngine = new DvPSettlementEngine();
        var result = dvpEngine.ExecuteDvpModel3Settlement(batch, vaults);

        if (!result.EntireBatchSettled)
            throw new Exception("Expected atomic DvP settlement to succeed");

        // Post-settlement balances:
        // Bank A: $50,000 cash remaining, 1,000 shares
        // Bank B: $100,000 cash, 0 shares
        if (vaults["BankA"].CashBalance.ToDecimal() != 50000m)
            throw new Exception($"Bank A cash balance wrong: {vaults["BankA"].CashBalance}");
        if (vaults["BankA"].SecuritiesPositions[isin].Units != 1000)
            throw new Exception("Bank A did not receive 1,000 shares");

        if (vaults["BankB"].CashBalance.ToDecimal() != 100000m)
            throw new Exception($"Bank B cash balance wrong: {vaults["BankB"].CashBalance}");
        if (vaults["BankB"].SecuritiesPositions[isin].Units != 0)
            throw new Exception("Bank B shares not debited to 0");
    }

    private static void TestCollateralOptimizationCheapestToDeliver()
    {
        var currency = Currency.USD;
        var optimizer = new CollateralOptimizationEngine();

        // Target: Post $1,000,000 in eligible margin
        CashAmount target = CashAmount.FromDecimal(1000000m, currency);

        // Inventory available:
        // 1. Equities: $600,000 nominal (Haircut 30% -> $420,000 eligible), Opportunity cost: 15 bps (very cheap)
        // 2. T-Bills: $800,000 nominal (Haircut 1.5% -> $788,000 eligible), Opportunity cost: 45 bps
        // 3. Cash: $1,000,000 nominal (Haircut 0% -> $1,000,000 eligible), Opportunity cost: 120 bps (expensive to lock up)
        var inventory = new List<CollateralOptimizationEngine.AvailableInventoryItem>
        {
            new(new CollateralAsset("EQ-1", CollateralType.EligibleEquityBlueChip, CashAmount.FromDecimal(600000m, currency)), 15m),
            new(new CollateralAsset("TB-1", CollateralType.GovernmentTreasuryBill, CashAmount.FromDecimal(800000m, currency)), 45m),
            new(new CollateralAsset("CS-1", CollateralType.Cash, CashAmount.FromDecimal(1000000m, currency)), 120m)
        };

        // Run CTD Optimization with 40% equity concentration cap (max $400,000 equity)
        var result = optimizer.OptimizeCollateralPledge("MEMBER-1", target, inventory, 0.40m);

        if (!result.RequirementSatisfied)
            throw new Exception("Expected collateral requirement to be satisfied");

        // First tranche allocated must be cheapest (Equities, capped at $400,000)
        var t1 = result.Allocations[0];
        if (t1.Asset.Type != CollateralType.EligibleEquityBlueChip || t1.EligibleValuation.ToDecimal() != 400000m)
            throw new Exception($"Tranche 1 equity allocation wrong: {t1.EligibleValuation}");

        // Second tranche allocated must be T-Bills ($600,000 remaining needed)
        var t2 = result.Allocations[1];
        if (t2.Asset.Type != CollateralType.GovernmentTreasuryBill || t2.EligibleValuation.ToDecimal() != 600000m)
            throw new Exception($"Tranche 2 T-Bills allocation wrong: {t2.EligibleValuation}");

        // Cash was not used because Equities + T-Bills covered the full $1,000,000!
        if (result.Allocations.Count != 2)
            throw new Exception("Cash should not be touched when cheaper assets suffice");
    }

    private static void TestCover1AndCover2LiquidityStress()
    {
        var currency = Currency.USD;
        var stressEngine = new LiquidityStressTestingEngine();

        // CCP has $500,000,000 in Qualifying Liquid Resources (central bank reserve + credit lines)
        CashAmount qlr = CashAmount.FromDecimal(500000000m, currency);

        // Daily member net cash draws on CCP:
        var memberDraws = new Dictionary<string, CashAmount>
        {
            ["Member-JPM"] = CashAmount.FromDecimal(220000000m, currency),   // $220M (Rank 1)
            ["Member-MS"] = CashAmount.FromDecimal(180000000m, currency),    // $180M (Rank 2)
            ["Member-CITI"] = CashAmount.FromDecimal(110000000m, currency),  // $110M (Rank 3)
            ["Member-BARC"] = CashAmount.FromDecimal(75000000m, currency)    // $75M  (Rank 4)
        };

        var report = stressEngine.RunCover1AndCover2StressTest(
            StressScenario.LehmanDefault2008_SevereMarketDownturn,
            qlr,
            memberDraws
        );

        // Cover 1 = $220M (Pass, since $500M >= $220M)
        if (!report.Cover1Compliant || report.Cover1LiquidityRequirement.ToDecimal() != 220000000m)
            throw new Exception("Cover 1 validation failed");

        // Cover 2 = $220M + $180M = $400M (Pass, since $500M >= $400M, Surplus = $100M)
        if (!report.Cover2Compliant || report.Cover2LiquidityRequirement.ToDecimal() != 400000000m)
            throw new Exception("Cover 2 validation failed");

        if (report.Cover2SurplusOrDeficit.ToDecimal() != 100000000m)
            throw new Exception($"Cover 2 surplus wrong: expected $100M, got {report.Cover2SurplusOrDeficit}");
    }
}
