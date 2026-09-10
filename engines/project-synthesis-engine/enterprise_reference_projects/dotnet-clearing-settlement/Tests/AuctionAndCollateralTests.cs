namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;

public static class AuctionAndCollateralTests
{
    public static void RunAll()
    {
        Console.WriteLine("Running AuctionAndCollateralTests (Default Auction, Haircuts, Cross-Currency, IRS)...");
        TestDefaultAuctionBidding();
        TestRepoCollateralHaircutMatrix();
        TestCrossCurrencyMarginHaircut();
        TestInterestRateSwapPricer();
        Console.WriteLine("  ✓ AuctionAndCollateralTests passed successfully.");
    }

    private static void TestDefaultAuctionBidding()
    {
        var engine = new DefaultAuctionBiddingEngine();
        var currency = Currency.USD;

        var contracts = new List<TradeContract>();
        var slice = new DefaultAuctionBiddingEngine.DefaulterPortfolioSlice(
            "AUCTION-SLICE-01",
            "DEFAULTER-LEHMAN",
            contracts,
            CashAmount.FromDecimal(100000000m, currency),
            CashAmount.FromDecimal(90000000m, currency), // Reserve floor $90M
            DateTime.UtcNow.AddHours(2));

        var mandatoryMembers = new List<string> { "JPM", "MS", "GS", "BARC" };

        var bids = new List<DefaultAuctionBiddingEngine.AuctionBid>
        {
            new("BID-01", "JPM", "AUCTION-SLICE-01", CashAmount.FromDecimal(92000000m, currency), 0.60m, DateTime.UtcNow),
            new("BID-02", "MS", "AUCTION-SLICE-01", CashAmount.FromDecimal(91000000m, currency), 0.40m, DateTime.UtcNow),
            new("BID-03", "GS", "AUCTION-SLICE-01", CashAmount.FromDecimal(88000000m, currency), 0.50m, DateTime.UtcNow)
            // Note: BARC did not submit a bid!
        };

        var result = engine.RunAuction(slice, mandatoryMembers, bids);

        if (!result.AuctionClearedSuccessfully)
        {
            throw new InvalidOperationException("Default auction should clear with combined 60% + 40% bids above reserve floor");
        }

        if (result.Allocations.Count != 2)
        {
            throw new InvalidOperationException($"Expected 2 allocations, got: {result.Allocations.Count}");
        }

        // BARC failed to bid and must be juniorized
        if (!result.JuniorizedPenalizedMembers.Contains("BARC"))
        {
            throw new InvalidOperationException("Non-bidding member BARC must be juniorized");
        }

        // JPM and MS bid competitively
        if (!result.CompliantBiddingMembers.Contains("JPM") || !result.CompliantBiddingMembers.Contains("MS"))
        {
            throw new InvalidOperationException("Winning bidders JPM and MS must be compliant");
        }
    }

    private static void TestRepoCollateralHaircutMatrix()
    {
        var matrix = new RepoCollateralHaircutMatrix();

        // Case 1: US Treasury 10Y (AAA/AA Sovereign), same currency (USD/USD), no WWR
        var inputUst = new RepoCollateralHaircutMatrix.CollateralValuationInput(
            "COL-UST-10Y", "JPM", "US Department of the Treasury",
            RepoCollateralHaircutMatrix.CollateralAssetClass.SovereignDebt_AAA_AA,
            RepoCollateralHaircutMatrix.ResidualTenorBand.FiveToTenYears,
            CashAmount.FromDecimal(10000000m, Currency.USD),
            Currency.USD, false, 0.05m);

        var resultUst = matrix.EvaluateCollateral(inputUst);

        if (resultUst.BaseHaircutPercent != 4.0m)
        {
            throw new InvalidOperationException($"Expected 4% base haircut for 5-10Y AAA sovereign, got: {resultUst.BaseHaircutPercent}%");
        }
        if (resultUst.FxMismatchAddOnPercent != 0.0m)
        {
            throw new InvalidOperationException("Expected 0% FX add-on when currencies match");
        }
        if (!resultUst.IsEligibleForClearingMargin)
        {
            throw new InvalidOperationException("US Treasury should be eligible for clearing margin");
        }

        // Case 2: EUR Corporate Bond posted for USD obligation -> 8% FX haircut + Corporate haircut
        var inputCorp = new RepoCollateralHaircutMatrix.CollateralValuationInput(
            "COL-CORP-EUR", "MS", "TotalEnergies SE",
            RepoCollateralHaircutMatrix.CollateralAssetClass.CorporateBond_AAA_AA,
            RepoCollateralHaircutMatrix.ResidualTenorBand.ThreeToFiveYears,
            CashAmount.FromDecimal(5000000m, Currency.EUR),
            Currency.USD, false, 0.10m);

        var resultCorp = matrix.EvaluateCollateral(inputCorp);

        if (resultCorp.FxMismatchAddOnPercent != 8.0m)
        {
            throw new InvalidOperationException($"Expected 8% FX mismatch add-on, got: {resultCorp.FxMismatchAddOnPercent}%");
        }
        if (resultCorp.TotalEffectiveHaircutPercent != 14.0m) // 6% base + 8% FX = 14%
        {
            throw new InvalidOperationException($"Expected 14% total haircut, got: {resultCorp.TotalEffectiveHaircutPercent}%");
        }
    }

    private static void TestCrossCurrencyMarginHaircut()
    {
        var engine = new CrossCurrencyMarginHaircutEngine();

        var positions = new List<CrossCurrencyMarginHaircutEngine.CurrencyPosition>
        {
            new(Currency.EUR, 10000000m, 7.5m, false), // EUR/USD
            new(Currency.GBP, 8000000m, 8.2m, false)   // GBP/USD
        };

        // Correlation between EUR and GBP vs USD is historically positive (+0.65)
        double[,] correlation = new double[,]
        {
            { 1.00, 0.65 },
            { 0.65, 1.00 }
        };

        var margin = engine.CalculatePortfolioMargin(Currency.USD, positions, correlation);

        if (margin.GrossStandaloneMargin <= 0m)
        {
            throw new InvalidOperationException("Gross standalone margin should be positive");
        }

        if (margin.CorrelationDiversifiedMargin >= margin.GrossStandaloneMargin)
        {
            throw new InvalidOperationException("Diversified margin should be strictly less than standalone sum with correlation < 1.0");
        }

        if (margin.CurrencyBasisAddOn <= 0m)
        {
            throw new InvalidOperationException("Currency basis add-on must be positive");
        }

        // Verify Cholesky decomposition L * L^T = A
        double[,] l = engine.ComputeCholeskyLowerTriangular(correlation);
        double reconstructedCorr12 = l[1, 0] * l[0, 0];
        if (Math.Abs(reconstructedCorr12 - 0.65) > 1e-4)
        {
            throw new InvalidOperationException($"Cholesky reconstruction failed: got {reconstructedCorr12}, expected 0.65");
        }
    }

    private static void TestInterestRateSwapPricer()
    {
        var pricer = new InterestRateSwapPricer();
        var currency = Currency.USD;

        var request = new InterestRateSwapPricer.SwapValuationRequest(
            "IRS-10Y-001",
            CashAmount.FromDecimal(50000000m, currency), // $50M notional
            InterestRateSwapPricer.SwapLegType.FixedPayer,
            3.50m, // 3.5% fixed
            new DateTime(2026, 1, 1),
            new DateTime(2031, 1, 1), // 5 Year swap
            6, // Semi-annual
            InterestRateSwapPricer.DayCountConvention.Thirty360BondBasis,
            InterestRateSwapPricer.DayCountConvention.Actual360);

        // Simple flat 3.5% continuous discounting curve: df(t) = exp(-0.035 * t)
        Func<DateTime, decimal> discountCurve = dt =>
        {
            decimal tYears = (decimal)(dt - new DateTime(2026, 1, 1)).TotalDays / 365.25m;
            return (decimal)Math.Exp(-0.035 * (double)tYears);
        };

        // Forward rate curve = 3.5% par
        Func<DateTime, DateTime, decimal> forwardCurve = (s, e) => 3.50m;

        var valuation = pricer.PriceSwap(request, discountCurve, forwardCurve);

        if (valuation.CashFlowSchedule.Count != 10)
        {
            throw new InvalidOperationException($"Expected 10 semi-annual periods for 5Y swap, got: {valuation.CashFlowSchedule.Count}");
        }

        if (valuation.Annuity <= 0m)
        {
            throw new InvalidOperationException("Annuity must be positive");
        }

        if (valuation.Dv01Amount <= 0m)
        {
            throw new InvalidOperationException("DV01 must be positive");
        }

        // Par swap rate should be close to 3.5%
        if (Math.Abs(valuation.ParSwapRatePercent - 3.50m) > 0.10m)
        {
            throw new InvalidOperationException($"Expected par swap rate near 3.50%, got: {valuation.ParSwapRatePercent}%");
        }
    }
}
