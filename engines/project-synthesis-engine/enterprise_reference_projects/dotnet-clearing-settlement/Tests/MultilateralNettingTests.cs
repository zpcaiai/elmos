namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Linq;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;

public static class MultilateralNettingTests
{
    public static void Run()
    {
        Console.WriteLine("Running MultilateralNettingTests...");
        TestZeroSumConservationInvariants();
        TestHighNettingEfficiencyRatio();
        Console.WriteLine("  ✓ MultilateralNettingTests passed successfully.");
    }

    private static void TestZeroSumConservationInvariants()
    {
        var currency = Currency.USD;
        var batch = new SettlementBatch("BATCH-001", "CYC-2026-06-15-01", DateTime.UtcNow, currency);

        // Apple Inc. valid ISIN: US0378331005
        var isinApple = SecurityId.Parse("US0378331005");
        // Microsoft Corp valid ISIN: US5949181045
        var isinMsft = SecurityId.Parse("US5949181045");

        // 4 Financial Institutions: BankA, BankB, BankC, BankD
        // Trade 1: BankA buys 1,000 Apple from BankB @ $150.00 ($150,000)
        batch.AddTrade(new TradeContract("T1", "BankA", "BankB", isinApple, CashAmount.FromDecimal(150.00m, currency), Quantity.Of(1000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));

        // Trade 2: BankB buys 800 Apple from BankC @ $152.00 ($121,600)
        batch.AddTrade(new TradeContract("T2", "BankB", "BankC", isinApple, CashAmount.FromDecimal(152.00m, currency), Quantity.Of(800), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));

        // Trade 3: BankC buys 500 Apple from BankA @ $148.00 ($74,000)
        batch.AddTrade(new TradeContract("T3", "BankC", "BankA", isinApple, CashAmount.FromDecimal(148.00m, currency), Quantity.Of(500), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));

        // Trade 4: BankD buys 2,000 MSFT from BankA @ $300.00 ($600,000)
        batch.AddTrade(new TradeContract("T4", "BankD", "BankA", isinMsft, CashAmount.FromDecimal(300.00m, currency), Quantity.Of(2000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));

        // Trade 5: BankB buys 1,500 MSFT from BankD @ $302.00 ($453,000)
        batch.AddTrade(new TradeContract("T5", "BankB", "BankD", isinMsft, CashAmount.FromDecimal(302.00m, currency), Quantity.Of(1500), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));

        batch.StartNovation();

        var nettingEngine = new MultilateralNettingEngine();
        var result = nettingEngine.ExecuteMultilateralNetting(batch);

        if (!result.InvariantCheckPassed)
            throw new Exception("Mathematical invariant check failed");

        // Mathematical Proof Verification:
        // 1. Sum of all Net Cash Obligations across all members must be exactly 0
        long sumNetCashMinor = result.Obligations.Sum(o => o.NetCashAmount.MinorUnits);
        if (sumNetCashMinor != 0)
            throw new Exception($"Cash conservation violated! Sum is {sumNetCashMinor}, expected 0.");

        // 2. Sum of all Net Apple Shares must be exactly 0
        long sumAppleUnits = result.Obligations.Where(o => o.SecurityId == isinApple).Sum(o => o.NetQuantity.Units);
        if (sumAppleUnits != 0)
            throw new Exception($"Securities conservation violated for Apple! Sum is {sumAppleUnits}, expected 0.");

        // 3. Sum of all Net MSFT Shares must be exactly 0
        long sumMsftUnits = result.Obligations.Where(o => o.SecurityId == isinMsft).Sum(o => o.NetQuantity.Units);
        if (sumMsftUnits != 0)
            throw new Exception($"Securities conservation violated for MSFT! Sum is {sumMsftUnits}, expected 0.");

        // Verify individual net position for BankA on Apple:
        // Bought 1,000 (+1,000 shares, -$150,000 cash), Sold 500 (-500 shares, +$74,000 cash)
        // Net Apple: +500 shares. Net Apple Cash: -$76,000 (-7,600,000 minor units).
        var bankAAppleObl = result.Obligations.First(o => o.MemberId == "BankA" && o.SecurityId == isinApple);
        if (bankAAppleObl.NetQuantity.Units != 500)
            throw new Exception($"BankA Net Apple shares wrong: expected 500, got {bankAAppleObl.NetQuantity.Units}");
        if (bankAAppleObl.NetCashAmount.MinorUnits != -7600000)
            throw new Exception($"BankA Net Apple cash wrong: expected -7600000, got {bankAAppleObl.NetCashAmount.MinorUnits}");
    }

    private static void TestHighNettingEfficiencyRatio()
    {
        var currency = Currency.USD;
        var batch = new SettlementBatch("BATCH-002", "CYC-CIRCULAR", DateTime.UtcNow, currency);
        var isin = SecurityId.Parse("US0378331005");

        // Perfect circular trade ring:
        // A -> B: $1,000,000
        // B -> C: $1,000,000
        // C -> A: $1,000,000
        batch.AddTrade(new TradeContract("TC1", "BankA", "BankB", isin, CashAmount.FromDecimal(100.00m, currency), Quantity.Of(10000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));
        batch.AddTrade(new TradeContract("TC2", "BankB", "BankC", isin, CashAmount.FromDecimal(100.00m, currency), Quantity.Of(10000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));
        batch.AddTrade(new TradeContract("TC3", "BankC", "BankA", isin, CashAmount.FromDecimal(100.00m, currency), Quantity.Of(10000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));

        batch.StartNovation();

        var nettingEngine = new MultilateralNettingEngine();
        var result = nettingEngine.ExecuteMultilateralNetting(batch);

        // Circular trades completely cancel out! Netting efficiency must be 100%
        if (result.NettingEfficiencyRatio != 100.0m)
            throw new Exception($"Expected 100% netting efficiency for circular ring, got: {result.NettingEfficiencyRatio}%");

        if (!result.TotalNetCashRequired.IsZero)
            throw new Exception($"Expected zero net cash required, got: {result.TotalNetCashRequired}");
    }
}
