namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;

public static class SimmAndRegulatoryTests
{
    public static void Run()
    {
        Console.WriteLine("Running SimmAndRegulatoryTests...");
        TestSimmMarginCalculation();
        TestLeiChecksumValidation();
        TestCsdrSettlementPenaltyCalculation();
        Console.WriteLine("  ✓ SimmAndRegulatoryTests passed successfully.");
    }

    private static void TestSimmMarginCalculation()
    {
        var engine = new StandardInitialMarginModelEngine();
        var currency = Currency.USD;

        var sensitivities = new List<SimmSensitivity>
        {
            // Interest Rate 10Y duration sensitivity: $500,000 DV01
            new(SimmRiskClass.InterestRate, "USD", "10Y", 500000m, 0m),
            // Equity Delta sensitivity: $2,000,000 in Tech stocks
            new(SimmRiskClass.Equity, "AAPL", "Tech", 2000000m, 0m),
            // FX Delta sensitivity: $1,500,000 in EUR/USD
            new(SimmRiskClass.ForeignExchange, "EUR", "G10", 1500000m, 0m)
        };

        var report = engine.CalculateSimmMargin(sensitivities, currency);

        if (report.TotalInitialMargin.ToDecimal() <= 0m)
            throw new Exception("Total SIMM margin must be positive");

        if (!report.MarginByRiskClass.ContainsKey(SimmRiskClass.Equity))
            throw new Exception("Equity risk class margin missing");

        // Diversification test: Total IM must be strictly less than sum of standalone margins
        decimal sumStandalone = 0m;
        foreach (var (_, val) in report.MarginByRiskClass)
        {
            sumStandalone += val.ToDecimal();
        }

        if (report.TotalInitialMargin.ToDecimal() >= sumStandalone)
            throw new Exception("Sub-additivity failed: Cross-asset diversification must reduce total margin");
    }

    private static void TestLeiChecksumValidation()
    {
        // Valid LEI: 7H6GLXDRUGQFU57RNE97 (JPMorgan Chase Bank, N.A.)
        if (!RegulatoryReportingEngine.ValidateLeiChecksum("7H6GLXDRUGQFU57RNE97"))
            throw new Exception("Valid LEI checksum rejected: 7H6GLXDRUGQFU57RNE97");

        // Invalid LEI (altered digit)
        if (RegulatoryReportingEngine.ValidateLeiChecksum("7H6GLXDRUGQFU57RNE99"))
            throw new Exception("Corrupted LEI checksum unexpectedly accepted");

        var reportingEngine = new RegulatoryReportingEngine("7H6GLXDRUGQFU57RNE97");
        var uti = reportingEngine.GenerateUti("TRD-9001", new DateTime(2026, 6, 15));

        if (!uti.StartsWith("7H6GLXDRUGQFU57RNE97"))
            throw new Exception("Generated UTI must begin with CCP LEI");
    }

    private static void TestCsdrSettlementPenaltyCalculation()
    {
        var penaltyEngine = new SettlementFailPenaltyEngine();
        var currency = Currency.USD;
        var apple = SecurityId.Parse("US0378331005");

        var failedObl = new ClearingObligation(
            "OBL-FAIL", "BATCH-01", "MEMBER-A", apple,
            Quantity.Of(-5000), CashAmount.Zero(currency),
            Quantity.Of(5000), CashAmount.Zero(currency)
        );
        var refPrice = CashAmount.FromDecimal(150.00m, currency);

        var penalty = penaltyEngine.CalculateDailyPenalty(
            "BATCH-01",
            failedObl,
            "MEMBER-A",
            "MEMBER-B",
            refPrice,
            SettlementFailReason.LackOfSecurities,
            1
        );

        if (penalty.PenaltyAmount.ToDecimal() <= 0m)
            throw new Exception("Daily penalty amount must be positive");

        var buyInNotice = penaltyEngine.IssueMandatoryBuyInNotice(failedObl, "MEMBER-A", refPrice, 4);
        if (buyInNotice.OutstandingQuantity.Units != 5000)
            throw new Exception("Buy-in notice quantity wrong");
    }
}
