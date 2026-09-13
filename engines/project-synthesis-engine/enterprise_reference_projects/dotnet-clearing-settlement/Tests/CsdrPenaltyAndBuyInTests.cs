namespace Elmos.ClearingSettlement.Tests;

using System;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;

public static class CsdrPenaltyAndBuyInTests
{
    public static void RunAll()
    {
        Console.WriteLine("[TEST SUITE] CSDR Settlement Discipline Regime & Mandatory Buy-In Verification");
        TestLiquidEquityDailyPenaltyAndBuyInThreshold();
        TestSovereignDebtLowerPenaltyAndExtendedBuyInWindow();
        TestMandatoryBuyInPhysicalExecutionWithPriceDifferential();
        TestMandatoryBuyInMarketFailureCashCompensationFallback();
        Console.WriteLine("  ✓ All CSDR penalty and mandatory buy-in tests passed!");
    }

    private static void TestLiquidEquityDailyPenaltyAndBuyInThreshold()
    {
        var engine = new SettlementFailsPenaltyEngine();
        var currency = Currency.USD;

        // $10,000,000 liquid equity trade fails settlement
        var tradeValue = CashAmount.FromDecimal(10000000m, currency);
        var intendedDate = new DateOnly(2026, 6, 1);

        // Day 2 of fail: Below threshold (4 days for liquid equity)
        var failDay2 = new SettlementFailRecord(
            "FAIL-EQ-001",
            "MEM-SELLER-A",
            "MEM-BUYER-B",
            "US0378331005", // AAPL
            FinancialInstrumentAssetClass.LiquidEquity,
            tradeValue,
            intendedDate,
            daysFailed: 2
        );

        var penaltyDay2 = engine.ComputeDailyPenalty(failDay2);
        if (penaltyDay2.DailyPenaltyRateBps != 1.00m)
            throw new Exception($"Expected 1.00 bps daily penalty, got {penaltyDay2.DailyPenaltyRateBps}");

        // $10M * 0.0001 = $1,000 daily
        if (penaltyDay2.DailyPenaltyAmount.Amount != 1000.00m)
            throw new Exception($"Expected $1,000 daily penalty, got ${penaltyDay2.DailyPenaltyAmount.Amount}");

        // Cumulative 2 days = $2,000
        if (penaltyDay2.CumulativePenaltyAmount.Amount != 2000.00m)
            throw new Exception($"Expected $2,000 cumulative penalty, got ${penaltyDay2.CumulativePenaltyAmount.Amount}");

        if (penaltyDay2.BuyInWindowTriggered)
            throw new Exception("Buy-in window should not trigger on day 2 for liquid equity (threshold is 4 days)");

        // Day 4 of fail: Threshold reached
        var failDay4 = new SettlementFailRecord(
            "FAIL-EQ-001",
            "MEM-SELLER-A",
            "MEM-BUYER-B",
            "US0378331005",
            FinancialInstrumentAssetClass.LiquidEquity,
            tradeValue,
            intendedDate,
            daysFailed: 4
        );

        var penaltyDay4 = engine.ComputeDailyPenalty(failDay4);
        if (penaltyDay4.CumulativePenaltyAmount.Amount != 4000.00m)
            throw new Exception($"Expected $4,000 cumulative penalty on day 4, got ${penaltyDay4.CumulativePenaltyAmount.Amount}");

        if (!penaltyDay4.BuyInWindowTriggered)
            throw new Exception("Buy-in window must trigger on day 4 for liquid equity");
    }

    private static void TestSovereignDebtLowerPenaltyAndExtendedBuyInWindow()
    {
        var engine = new SettlementFailsPenaltyEngine();
        var currency = Currency.USD;

        // $50,000,000 US Treasury Bond fail
        var tradeValue = CashAmount.FromDecimal(50000000m, currency);
        var intendedDate = new DateOnly(2026, 6, 1);

        var failGovt = new SettlementFailRecord(
            "FAIL-SOV-001",
            "MEM-DEALER-X",
            "MEM-PENSION-Y",
            "US91282CDJ71", // US Treasury 10Y
            FinancialInstrumentAssetClass.SovereignDebtAaa,
            tradeValue,
            intendedDate,
            daysFailed: 5
        );

        var assessment = engine.ComputeDailyPenalty(failGovt);

        // Sovereign AAA penalty rate is 0.10 bps per day
        if (assessment.DailyPenaltyRateBps != 0.10m)
            throw new Exception($"Expected 0.10 bps penalty rate for sovereign debt, got {assessment.DailyPenaltyRateBps}");

        // $50M * 0.00001 = $500 daily
        if (assessment.DailyPenaltyAmount.Amount != 500.00m)
            throw new Exception($"Expected $500 daily penalty, got ${assessment.DailyPenaltyAmount.Amount}");

        // Day 5 cumulative = $2,500
        if (assessment.CumulativePenaltyAmount.Amount != 2500.00m)
            throw new Exception($"Expected $2,500 cumulative penalty, got ${assessment.CumulativePenaltyAmount.Amount}");

        // Sovereign debt has 7-day buy-in window
        if (assessment.BuyInWindowTriggered)
            throw new Exception("Buy-in window should not trigger on day 5 for sovereign debt (threshold is 7 days)");
    }

    private static void TestMandatoryBuyInPhysicalExecutionWithPriceDifferential()
    {
        var engine = new SettlementFailsPenaltyEngine();
        var currency = Currency.USD;

        var tradeValue = CashAmount.FromDecimal(10000000m, currency); // Original price $10,000,000
        var fail = new SettlementFailRecord(
            "FAIL-BUYIN-01",
            "MEM-SELLER-A",
            "MEM-BUYER-B",
            "US0378331005",
            FinancialInstrumentAssetClass.LiquidEquity,
            tradeValue,
            new DateOnly(2026, 6, 1),
            daysFailed: 4
        );

        // Buy-in executed by appointed agent at higher market price: $10,250,000
        var executionPrice = CashAmount.FromDecimal(10250000m, currency);

        var result = engine.ExecuteMandatoryBuyIn(
            fail,
            marketLiquidityAvailable: true,
            actualBuyInExecutionPrice: executionPrice
        );

        if (!result.BuyInSuccessful)
            throw new Exception("Expected successful physical buy-in execution");

        if (result.ResolutionType != "PHYSICAL_BUY_IN")
            throw new Exception($"Expected PHYSICAL_BUY_IN resolution, got {result.ResolutionType}");

        // Failing seller must compensate buyer for the $250,000 price rise
        if (result.PriceDifferenceCompensationToReceiver.Amount != 250000m)
            throw new Exception($"Expected $250,000 price differential compensation, got ${result.PriceDifferenceCompensationToReceiver.Amount}");
    }

    private static void TestMandatoryBuyInMarketFailureCashCompensationFallback()
    {
        var engine = new SettlementFailsPenaltyEngine();
        var currency = Currency.USD;

        var tradeValue = CashAmount.FromDecimal(5000000m, currency); // Original price $5,000,000
        var fail = new SettlementFailRecord(
            "FAIL-BUYIN-02",
            "MEM-SELLER-DEF",
            "MEM-BUYER-REC",
            "US88160R1014", // TSLA
            FinancialInstrumentAssetClass.LiquidEquity,
            tradeValue,
            new DateOnly(2026, 6, 1),
            daysFailed: 4
        );

        // Buy-in agent cannot find shares in the market (liquidity unavailable)
        var refPrice = CashAmount.FromDecimal(5200000m, currency);

        var result = engine.ExecuteMandatoryBuyIn(
            fail,
            marketLiquidityAvailable: false,
            referenceMarketPriceForCashComp: refPrice
        );

        if (result.BuyInSuccessful)
            throw new Exception("Expected failed buy-in falling back to cash compensation");

        if (result.ResolutionType != "CASH_COMPENSATION")
            throw new Exception($"Expected CASH_COMPENSATION resolution, got {result.ResolutionType}");

        // Statutory cash compensation: reference price ($5,200,000) * 1.10 = $5,720,000
        decimal expectedComp = Math.Round(5200000m * 1.10m, 2);
        if (result.ExecutionOrCashCompensationValue.Amount != expectedComp)
            throw new Exception($"Expected ${expectedComp:N2} cash compensation, got ${result.ExecutionOrCashCompensationValue.Amount:N2}");

        // Differential over original $5,000,000 contract value = $720,000
        decimal expectedDiff = expectedComp - 5000000m;
        if (result.PriceDifferenceCompensationToReceiver.Amount != expectedDiff)
            throw new Exception($"Expected ${expectedDiff:N2} compensation differential to receiver, got ${result.PriceDifferenceCompensationToReceiver.Amount:N2}");
    }
}
