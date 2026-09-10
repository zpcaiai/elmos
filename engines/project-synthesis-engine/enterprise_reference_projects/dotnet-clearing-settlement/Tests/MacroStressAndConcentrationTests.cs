namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;

public static class MacroStressAndConcentrationTests
{
    public static void RunAll()
    {
        Console.WriteLine("[TEST SUITE] Macro Stress Testing (Cover-2) & Intraday Concentration Tests");
        TestCoverTwoLehmanStressTest();
        TestIntraday3SigmaVolatilitySurge();
        TestLargePositionLiquidityConcentrationAddOn();
        Console.WriteLine("  ✓ All Macro Stress Testing and Concentration tests passed!");
    }

    private static void TestCoverTwoLehmanStressTest()
    {
        var usd = Currency.USD;
        var catalog = new StressTestingScenarioCatalog();

        // 4 Clearing Members with varying portfolios
        var portfolios = new Dictionary<string, (CashAmount GrossLongNotional, CashAmount GrossShortNotional, CashAmount PostedCollateral)>
        {
            ["MEMBER_A"] = (new CashAmount(100_000_000_00, usd), new CashAmount(10_000_000_00, usd), new CashAmount(25_000_000_00, usd)),
            ["MEMBER_B"] = (new CashAmount(80_000_000_00, usd), new CashAmount(20_000_000_00, usd), new CashAmount(20_000_000_00, usd)),
            ["MEMBER_C"] = (new CashAmount(20_000_000_00, usd), new CashAmount(5_000_000_00, usd), new CashAmount(8_000_000_00, usd)),
            ["MEMBER_D"] = (new CashAmount(10_000_000_00, usd), new CashAmount(2_000_000_00, usd), new CashAmount(5_000_000_00, usd)),
        };

        // CCP Default Fund has $100M
        var defaultFund = new CashAmount(100_000_000_00, usd);

        var result = catalog.RunCoverTwoStressTest(StressTestingScenarioCatalog.Lehman2008Shock, portfolios, defaultFund);

        if (!result.CoverTwoStandardSatisfied)
        {
            throw new InvalidOperationException($"Cover-2 standard should be satisfied by default fund of {defaultFund}");
        }
        if (result.TopMember1Id != "MEMBER_A" || result.TopMember2Id != "MEMBER_B")
        {
            throw new InvalidOperationException($"Unexpected top 2 defaulting members: {result.TopMember1Id} and {result.TopMember2Id}");
        }
    }

    private static void TestIntraday3SigmaVolatilitySurge()
    {
        var engine = new IntradayMarginAndConcentrationEngine();
        var usd = Currency.USD;
        var sec = SecurityId.Parse("US0378331005");

        var prevClose = new CashAmount(200_00, usd); // $200.00
        decimal dailyStdDev = 0.03m; // 3% daily volatility

        // Intraday price moves to $210 (5% move -> 5% / 3% = 1.67 sigma, normal)
        var alertNormal = engine.CheckIntradayPriceSurge(sec, prevClose, new CashAmount(210_00, usd), dailyStdDev);
        if (alertNormal.IsEmergencyThresholdBreached)
        {
            throw new InvalidOperationException("1.67-sigma move should not trigger emergency intraday call");
        }

        // Intraday price crashes to $178 (11% move -> 11% / 3% = 3.67 sigma >= 3.0 sigma, emergency!)
        var alertEmergency = engine.CheckIntradayPriceSurge(sec, prevClose, new CashAmount(178_00, usd), dailyStdDev);
        if (!alertEmergency.IsEmergencyThresholdBreached)
        {
            throw new InvalidOperationException("3.67-sigma move must trigger emergency intraday margin call");
        }
    }

    private static void TestLargePositionLiquidityConcentrationAddOn()
    {
        var engine = new IntradayMarginAndConcentrationEngine();
        var usd = Currency.USD;
        var sec = SecurityId.Parse("US5949181045");

        var adv = new Quantity(100_000); // 100k daily volume
        var baseMargin = new CashAmount(1_000_000_00, usd); // $1,000,000 base initial margin

        // Position 1: 10,000 shares (10% ADV <= 20% threshold -> no add-on)
        var normalAss = engine.EvaluateConcentrationPenalty("FIRM_1", sec, new Quantity(10_000), adv, baseMargin);
        if (normalAss.LiquidityMultiplier != 1.0m || normalAss.ConcentrationAddOnMargin.MinorUnits != 0)
        {
            throw new InvalidOperationException("Position under 20% ADV should have 1.0 multiplier and 0 add-on");
        }

        // Position 2: 50,000 shares (50% ADV > 20% -> (0.50 - 0.20) * 1.5 = +0.45 add-on -> 1.45x multiplier)
        var concentratedAss = engine.EvaluateConcentrationPenalty("FIRM_2", sec, new Quantity(50_000), adv, baseMargin);
        if (concentratedAss.LiquidityMultiplier != 1.45m)
        {
            throw new InvalidOperationException($"Expected 1.45 multiplier, got {concentratedAss.LiquidityMultiplier}");
        }
        if (concentratedAss.ConcentrationAddOnMargin.MinorUnits != 450_000_00) // $450k add-on
        {
            throw new InvalidOperationException($"Expected $450k add-on, got {concentratedAss.ConcentrationAddOnMargin}");
        }
    }
}
