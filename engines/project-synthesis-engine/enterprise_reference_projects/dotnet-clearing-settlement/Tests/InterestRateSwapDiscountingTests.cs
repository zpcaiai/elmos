namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Engines;

public static class InterestRateSwapDiscountingTests
{
    public static void RunAll()
    {
        Console.WriteLine("[TEST SUITE] Multi-Curve IRS Discounting, Par Rates, DV01 & Variation Margin Tests");
        TestYieldCurveDiscountFactorAndForwardRateInterpolation();
        TestAtTheMarketParSwapHasZeroNetPresentValue();
        TestPayFixedSwapDV01SensitivityInRisingRateEnvironment();
        TestDailyVariationMarginSettlementCashFlow();
        Console.WriteLine("  ✓ All Interest Rate Swap Discounting tests passed!");
    }

    private static void TestYieldCurveDiscountFactorAndForwardRateInterpolation()
    {
        var pillars = new List<CurvePillar>
        {
            new CurvePillar(0.5m, 0.0400m), // 6M @ 4.00%
            new CurvePillar(1.0m, 0.0425m), // 1Y @ 4.25%
            new CurvePillar(2.0m, 0.0450m), // 2Y @ 4.50%
            new CurvePillar(5.0m, 0.0475m), // 5Y @ 4.75%
            new CurvePillar(10.0m, 0.0500m) // 10Y @ 5.00%
        };

        var curve = new ZeroRateYieldCurve("USD-SOFR-DISCOUNT", pillars);

        // Tenor 0 must have discount factor exactly 1.0
        if (curve.GetDiscountFactor(0.0m) != 1.0m)
            throw new Exception("Discount factor at tenor 0 must be exactly 1.0");

        // Intermediate tenor 1.5Y interpolated rate: halfway between 4.25% and 4.50% = 4.375%
        decimal rate1_5 = curve.GetZeroRate(1.5m);
        if (Math.Abs(rate1_5 - 0.04375m) > 0.0001m)
            throw new Exception($"Expected interpolated rate of 0.04375, got {rate1_5}");

        // Discount factor at 1Y: exp(-0.0425 * 1.0) ~ 0.95839
        decimal df1 = curve.GetDiscountFactor(1.0m);
        if (df1 <= 0.90m || df1 >= 1.0m)
            throw new Exception($"Discount factor out of reasonable bounds: {df1}");

        // Forward rate between 1Y and 2Y must be positive
        decimal fwd1_2 = curve.GetForwardRate(1.0m, 2.0m);
        if (fwd1_2 <= 0.04m || fwd1_2 >= 0.06m)
            throw new Exception($"Forward rate out of expected range: {fwd1_2}");
    }

    private static void TestAtTheMarketParSwapHasZeroNetPresentValue()
    {
        var engine = new InterestRateSwapDiscountingEngine();

        var pillars = new List<CurvePillar>
        {
            new CurvePillar(0.25m, 0.0350m),
            new CurvePillar(0.5m, 0.0360m),
            new CurvePillar(1.0m, 0.0375m),
            new CurvePillar(2.0m, 0.0400m),
            new CurvePillar(3.0m, 0.0420m),
            new CurvePillar(5.0m, 0.0450m)
        };

        var oisCurve = new ZeroRateYieldCurve("USD-OIS", pillars);
        var forwardCurve = new ZeroRateYieldCurve("USD-SOFR-FWD", pillars);

        // $100,000,000 notional, 5-year swap with dummy fixed rate first
        var dummySwap = new VanillaInterestRateSwap(
            "SWAP-ATM-01",
            "JPM",
            "MS",
            100000000m, // $100M
            0.0400m,
            SwapLegType.PayFixedReceiveFloating,
            5.0m, // 5 years
            fixedFreqMonths: 6,
            floatingFreqMonths: 3
        );

        var initialVal = engine.PriceSwap(dummySwap, oisCurve, forwardCurve);
        decimal parRate = initialVal.ParSwapRate;

        // Reprice swap using exact computed Par Rate
        var atTheMarketSwap = new VanillaInterestRateSwap(
            "SWAP-ATM-PAR",
            "JPM",
            "MS",
            100000000m,
            parRate,
            SwapLegType.PayFixedReceiveFloating,
            5.0m,
            fixedFreqMonths: 6,
            floatingFreqMonths: 3
        );

        var parVal = engine.PriceSwap(atTheMarketSwap, oisCurve, forwardCurve);

        // At-the-market swap NPV must be approximately zero (within $100 on a $100M notional swap)
        if (Math.Abs(parVal.NetPresentValueUSD) > 100m)
            throw new Exception($"ATM Par swap must have near-zero NPV, got: ${parVal.NetPresentValueUSD:N2}");
    }

    private static void TestPayFixedSwapDV01SensitivityInRisingRateEnvironment()
    {
        var engine = new InterestRateSwapDiscountingEngine();

        var pillars = new List<CurvePillar>
        {
            new CurvePillar(0.5m, 0.0400m),
            new CurvePillar(1.0m, 0.0420m),
            new CurvePillar(3.0m, 0.0440m),
            new CurvePillar(5.0m, 0.0460m),
            new CurvePillar(10.0m, 0.0480m)
        };

        var oisCurve = new ZeroRateYieldCurve("USD-OIS", pillars);
        var fwdCurve = new ZeroRateYieldCurve("USD-SOFR", pillars);

        // Pay Fixed @ 4.00% on $50,000,000 5-Year Swap
        var swap = new VanillaInterestRateSwap(
            "SWAP-DV01-01",
            "CITI",
            "BARC",
            50000000m,
            0.0400m,
            SwapLegType.PayFixedReceiveFloating,
            5.0m
        );

        var val = engine.PriceSwap(swap, oisCurve, fwdCurve);

        // In a Pay Fixed / Receive Floating swap, higher floating rates increase floating cash inflows -> positive DV01
        if (val.DV01USD <= 0m)
            throw new Exception($"Pay Fixed swap must exhibit positive DV01, got ${val.DV01USD:N2}");

        // For a $50M 5Y swap with annuity ~4.3, 1bp shift should yield approximately $50M * 0.0001 * 4.3 ~ $21,000 DV01
        if (val.DV01USD < 15000m || val.DV01USD > 30000m)
            throw new Exception($"DV01 out of expected empirical range: ${val.DV01USD:N2}");
    }

    private static void TestDailyVariationMarginSettlementCashFlow()
    {
        var engine = new InterestRateSwapDiscountingEngine();

        var swap = new VanillaInterestRateSwap(
            "SWAP-VM-01",
            "JPM",
            "BOFA",
            100000000m,
            0.0450m,
            SwapLegType.PayFixedReceiveFloating,
            3.0m
        );

        // Day T-1: Net MtM was +$450,000
        // Day T: Rates rose further, Net MtM is now +$620,000
        decimal prevMtM = 450000m;
        decimal currMtM = 620000m;

        var vmSettlement = engine.SettleDailyVariationMargin(swap, prevMtM, currMtM);

        if (vmSettlement.VariationMarginCashFlow.Amount != 170000m) // $620k - $450k = $170k cash call
            throw new Exception($"Expected $170,000 VM cash settlement, got ${vmSettlement.VariationMarginCashFlow.Amount:N2}");

        if (vmSettlement.PayerMemberId != "JPM" || vmSettlement.ReceiverMemberId != "BOFA")
            throw new Exception("Clearing member IDs not preserved in VM record");
    }
}
