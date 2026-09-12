namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;

public static class CompressionAndTripartyTests
{
    public static void RunAll()
    {
        Console.WriteLine("[TEST SUITE] Triparty Collateral, Compression Tear-Up & BCBS 248 Intraday Liquidity Tests");
        TestTripartyCollateralAllocationWithConcentrationLimits();
        TestMultilateralCompressionCycleTearUpAndDV01Conservation();
        TestBCBS248IntradayLiquidityStressCover2();
        Console.WriteLine("  ✓ All Triparty, Compression, and Intraday Liquidity tests passed!");
    }

    private static void TestTripartyCollateralAllocationWithConcentrationLimits()
    {
        var engine = new TripartyCollateralAllocationEngine();
        var currency = Currency.USD;

        // Clearing member needs to satisfy $10,000,000 Initial Margin requirement
        var requiredMargin = CashAmount.FromDecimal(10000000m, currency);

        var inventory = new List<AvailableCollateralInventoryItem>
        {
            new AvailableCollateralInventoryItem("ASSET-UST-10Y", "US-TREASURY", CollateralType.SovereignBondAaa, currency, CashAmount.FromDecimal(6000000m, currency), 0.04m),
            new AvailableCollateralInventoryItem("ASSET-TBILL", "US-TREASURY", CollateralType.GovernmentTreasuryBill, currency, CashAmount.FromDecimal(3000000m, currency), 0.015m),
            new AvailableCollateralInventoryItem("ASSET-CORP-AAPL", "CORP-APPLE", CollateralType.CorporateBondInvestmentGrade, currency, CashAmount.FromDecimal(3000000m, currency), 0.15m),
            new AvailableCollateralInventoryItem("ASSET-BUND-10Y", "GERMANY-MOF", CollateralType.SovereignBondAaa, Currency.EUR, CashAmount.FromDecimal(2000000m, currency), 0.04m) // FX mismatch!
        };

        // 1. Cheapest to Deliver Strategy
        var result = engine.AllocateCollateral("MEM-CITI", requiredMargin, inventory, AllocationOptimizationStrategy.CheapestToDeliver);

        if (!result.IsFullyCovered)
            throw new Exception($"Expected collateral requirement to be fully satisfied, but had deficit: {result.CollateralExcessDeficit}");

        if (result.TotalNetEligibleValue.Amount < requiredMargin.Amount)
            throw new Exception("Net eligible value must meet or exceed required margin");

        if (!result.ConcentrationRulesPassed)
            throw new Exception($"Concentration rules should pass on balanced inventory, but got: {string.Join(", ", result.RuleBreaches)}");

        // 2. Breach Concentration Limit: Member only submits single corporate bond
        var corporateHeavyInventory = new List<AvailableCollateralInventoryItem>
        {
            new AvailableCollateralInventoryItem("ASSET-CORP-TESLA", "CORP-TESLA", CollateralType.CorporateBondInvestmentGrade, currency, CashAmount.FromDecimal(12000000m, currency), 0.15m)
        };

        var breachResult = engine.AllocateCollateral("MEM-HEDGE", requiredMargin, corporateHeavyInventory);
        if (breachResult.ConcentrationRulesPassed)
            throw new Exception("Expected concentration rules failure when collateral is 100% single corporate issuer");

        if (breachResult.RuleBreaches.Count < 2)
            throw new Exception("Expected multiple rule breaches (single issuer concentration + missing sovereign floor)");
    }

    private static void TestMultilateralCompressionCycleTearUpAndDV01Conservation()
    {
        var compressionEngine = new CompressionTearUpEngine();
        var maturity = new DateTime(2031, 6, 15);
        var currency = Currency.USD;

        // Create 3-member offsetting interest rate swap cycle:
        // Trade 1: JPM pays fixed to MS ($50M notional, 3.50% rate, DV01 $4,500)
        // Trade 2: MS pays fixed to BOFA ($50M notional, 3.50% rate, DV01 $4,500)
        // Trade 3: BOFA pays fixed to JPM ($50M notional, 3.50% rate, DV01 $4,500)
        // Redundant cyclical notional = $150M.
        // Also add a direct offsetting trade between JPM and MS:
        // Trade 4: MS pays fixed to JPM ($30M notional, 3.50% rate, DV01 $2,700)
        var trades = new List<CompressibleSwapTrade>
        {
            new CompressibleSwapTrade("TR-001", "JPM", "MS", currency, 50000000m, 0.0350m, 4500m, maturity),
            new CompressibleSwapTrade("TR-002", "MS", "JPM", currency, 30000000m, 0.0350m, 2700m, maturity),
            new CompressibleSwapTrade("TR-003", "BOFA", "MS", currency, 20000000m, 0.0350m, 1800m, maturity),
            new CompressibleSwapTrade("TR-004", "MS", "BOFA", currency, 20000000m, 0.0350m, 1800m, maturity),
        };

        var tolerances = new Dictionary<string, MemberRiskTolerance>
        {
            ["JPM"] = new MemberRiskTolerance { MemberId = "JPM", MaxDV01VarianceUSD = 100m },
            ["MS"] = new MemberRiskTolerance { MemberId = "MS", MaxDV01VarianceUSD = 100m },
            ["BOFA"] = new MemberRiskTolerance { MemberId = "BOFA", MaxDV01VarianceUSD = 100m },
        };

        var result = compressionEngine.ExecuteCompressionCycle("COMP-2026-Q3-01", trades, tolerances);

        if (!result.RiskTolerancesRespected)
            throw new Exception($"Risk tolerances violated: {string.Join(", ", result.ToleranceViolations)}");

        // MS <-> BOFA $20M direct pair fully cancelled ($40M gross eliminated)
        // JPM <-> MS $30M direct offsetting cancelled ($60M gross eliminated), leaving $20M residual JPM -> MS
        if (result.GrossCompressedNotionalUSD != 100000000m) // $100M total torn up
            throw new Exception($"Expected $100,000,000 compressed notional, got ${result.GrossCompressedNotionalUSD:N0}");

        if (result.GrossResidualNotionalUSD != 20000000m) // $20M residual
            throw new Exception($"Expected $20,000,000 residual notional, got ${result.GrossResidualNotionalUSD:N0}");

        // Verify DV01 invariant: post-compression net DV01 must equal pre-compression net DV01 exactly
        foreach (var member in tolerances.Keys)
        {
            decimal pre = result.PreCompressionNetDV01[member];
            decimal post = result.PostCompressionNetDV01[member];
            if (Math.Abs(post - pre) > 0.01m)
            {
                throw new Exception($"Member {member} DV01 not conserved: Pre={pre}, Post={post}");
            }
        }
    }

    private static void TestBCBS248IntradayLiquidityStressCover2()
    {
        var stressEngine = new IntradayLiquidityStressEngine();
        var currency = Currency.USD;

        var openingReserve = CashAmount.FromDecimal(50000000m, currency);    // $50M central bank cash reserve
        var committedFacility = CashAmount.FromDecimal(100000000m, currency); // $100M committed repo liquidity line

        // Schedule of scheduled intraday cash flows across standard business day
        var flows = new List<IntradayCashFlowEvent>
        {
            new IntradayCashFlowEvent("FLOW-01", "JPM", new TimeOnly(8, 30), LiquidityFlowDirection.InboundReceipt, CashAmount.FromDecimal(30000000m, currency)),
            new IntradayCashFlowEvent("FLOW-02", "MS", new TimeOnly(9, 0), LiquidityFlowDirection.InboundReceipt, CashAmount.FromDecimal(40000000m, currency)),
            new IntradayCashFlowEvent("FLOW-03", "BOFA", new TimeOnly(10, 0), LiquidityFlowDirection.InboundReceipt, CashAmount.FromDecimal(25000000m, currency)),
            new IntradayCashFlowEvent("FLOW-04", "CITI", new TimeOnly(11, 0), LiquidityFlowDirection.OutboundPayment, CashAmount.FromDecimal(75000000m, currency)),
            new IntradayCashFlowEvent("FLOW-05", "BARC", new TimeOnly(13, 0), LiquidityFlowDirection.OutboundPayment, CashAmount.FromDecimal(50000000m, currency)),
            new IntradayCashFlowEvent("FLOW-06", "JPM", new TimeOnly(15, 0), LiquidityFlowDirection.InboundReceipt, CashAmount.FromDecimal(40000000m, currency)),
        };

        // Scenario: Simultaneous default of Top-1 debtor (MS - $40M lost) and 2-hour Fedwire settlement freeze
        var scenario = new IntradayStressScenario
        {
            ScenarioName = "Cover-1 Default + 2h Rail Delay",
            DefaultedMemberIds = new HashSet<string> { "MS" },
            InboundPaymentDelayHours = 2.0m,
            OutboundSurgeMultiplier = 1.0m
        };

        var assessment = stressEngine.AssessIntradayStress(openingReserve, committedFacility, flows, scenario);

        if (assessment.HourlyTrajectory.Count != 12)
            throw new Exception($"Expected 12 hourly trajectory points, got {assessment.HourlyTrajectory.Count}");

        // Opening buffer $50M absorbed the initial stress before credit line is drawn
        if (assessment.BreachedCommittedFacilities)
            throw new Exception("Committed facilities ($100M) should have absorbed peak intraday deficit");

        if (assessment.PeakIntradayLiquidityDeficitUSD <= 0)
            throw new Exception("Expected measurable intraday deficit during outbound payment rush before delayed inflows arrive");
    }
}
