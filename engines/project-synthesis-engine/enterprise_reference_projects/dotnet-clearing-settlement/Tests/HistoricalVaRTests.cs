namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;

public static class HistoricalVaRTests
{
    public static void Run()
    {
        Console.WriteLine("Running HistoricalVaRTests...");
        TestSingleAssetHistoricalVaR();
        TestMultiAssetPortfolioExpectedShortfall();
        Console.WriteLine("  ✓ HistoricalVaRTests passed successfully.");
    }

    private static void TestSingleAssetHistoricalVaR()
    {
        var currency = Currency.USD;
        var engine = new HistoricalVaREngine(decayFactorLambda: 0.94, lookbackDays: 200);

        var apple = SecurityId.Parse("US0378331005");
        var obligations = new List<ClearingObligation>
        {
            new("OBL-1", "BATCH-01", "JPM", apple, Quantity.Of(10000), CashAmount.Zero(currency), Quantity.Of(10000), CashAmount.Zero(currency))
        };

        var currentPrices = new Dictionary<SecurityId, CashAmount>
        {
            [apple] = CashAmount.FromDecimal(150.00m, currency) // $1,500,000 position
        };

        // Synthesize 200 daily returns with normal distribution and a tail drop (-5%)
        var returns = new List<double>(200);
        for (int i = 0; i < 200; i++)
        {
            returns.Add((i % 20 == 0) ? -0.045 : 0.002 * (i % 5 - 2));
        }
        returns[0] = -0.065; // -6.5% worst shock

        var returnMap = new Dictionary<SecurityId, IReadOnlyList<double>>
        {
            [apple] = returns
        };

        var result = engine.CalculatePortfolioVaR(obligations, currentPrices, returnMap, currency);

        if (result.ScenariosEvaluated != 200)
            throw new Exception($"Expected 200 scenarios, got {result.ScenariosEvaluated}");

        if (result.UnweightedVaR99.MinorUnits <= 0)
            throw new Exception("VaR 99 must be strictly positive");

        if (result.ExpectedShortfall975.MinorUnits < result.UnweightedVaR99.MinorUnits)
            throw new Exception("Expected Shortfall (tail mean) must be >= VaR 99");

        if (result.WorstScenarioPnl.MinorUnits <= 0)
            throw new Exception("Worst scenario loss must be strictly positive");
    }

    private static void TestMultiAssetPortfolioExpectedShortfall()
    {
        var currency = Currency.USD;
        var engine = new HistoricalVaREngine();

        var apple = SecurityId.Parse("US0378331005");
        var msft = SecurityId.Parse("US5949181045");

        // Long Apple 5,000 shares, Short MSFT 3,000 shares
        var obligations = new List<ClearingObligation>
        {
            new("OBL-A", "BATCH-01", "MS", apple, Quantity.Of(5000), CashAmount.Zero(currency), Quantity.Of(5000), CashAmount.Zero(currency)),
            new("OBL-M", "BATCH-01", "MS", msft, Quantity.Of(-3000), CashAmount.Zero(currency), Quantity.Of(3000), CashAmount.Zero(currency))
        };

        var currentPrices = new Dictionary<SecurityId, CashAmount>
        {
            [apple] = CashAmount.FromDecimal(150.00m, currency),
            [msft] = CashAmount.FromDecimal(300.00m, currency)
        };

        var returnsA = new List<double>(150);
        var returnsM = new List<double>(150);
        for (int i = 0; i < 150; i++)
        {
            returnsA.Add((i % 15 == 0) ? -0.035 : 0.001);
            returnsM.Add((i % 15 == 0) ? -0.030 : 0.001);
        }

        var returnMap = new Dictionary<SecurityId, IReadOnlyList<double>>
        {
            [apple] = returnsA,
            [msft] = returnsM
        };

        var result = engine.CalculatePortfolioVaR(obligations, currentPrices, returnMap, currency);
        if (result.ExpectedShortfall975.MinorUnits <= 0)
            throw new Exception("Portfolio Expected Shortfall should be positive");
    }
}
