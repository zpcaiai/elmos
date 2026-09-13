namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;
using Elmos.ClearingSettlement.Infrastructure.Persistence;

public static class MarginCalculationTests
{
    public static async Task RunAsync()
    {
        Console.WriteLine("Running MarginCalculationTests...");
        await TestParametricVarAndDeficitCalculationAsync();
        Console.WriteLine("  ✓ MarginCalculationTests passed successfully.");
    }

    private static async Task TestParametricVarAndDeficitCalculationAsync()
    {
        var marginRepo = new InMemoryMarginAccountRepository();
        var engine = new MarginCalculationEngine(marginRepo);

        var currency = Currency.USD;
        string memberId = "MEM-GOLDMAN";
        var account = new MarginAccount("ACC-01", memberId, currency);

        // Pledge $500,000 Nominal of US Treasury Bills (1.5% Haircut -> $492,500 eligible)
        account.DepositCollateral(new CollateralAsset(
            "ASSET-TBILL", CollateralType.GovernmentTreasuryBill, CashAmount.FromDecimal(500000m, currency)
        ));

        // Pledge $200,000 Nominal of Blue Chip Equities (30.0% Haircut -> $140,000 eligible)
        account.DepositCollateral(new CollateralAsset(
            "ASSET-EQUITY", CollateralType.EligibleEquityBlueChip, CashAmount.FromDecimal(200000m, currency)
        ));

        await marginRepo.SaveAsync(account);

        CashAmount eligibleCollateral = account.CalculateTotalEligibleCollateral();
        // $492,500 + $140,000 = $632,500.00
        decimal expectedEligible = 492500m + 140000m;
        if (Math.Abs(eligibleCollateral.ToDecimal() - expectedEligible) > 0.01m)
        {
            throw new Exception($"Eligible collateral haircut calculation wrong: expected {expectedEligible}, got {eligibleCollateral.ToDecimal()}");
        }

        // Setup Member with a net short position of 10,000 shares of Apple (US0378331005)
        var isinApple = SecurityId.Parse("US0378331005");
        var appleObligation = new ClearingObligation(
            "OBL-01", "BATCH-1", memberId, isinApple,
            Quantity.Of(-10000), // Short 10,000 shares
            CashAmount.FromDecimal(1500000m, currency), // Received $1,500,000 ($150/share)
            Quantity.Of(10000),
            CashAmount.FromDecimal(1500000m, currency)
        );

        // Apple current market price increased to $165 (unfavorable MtM = loss of $15 * 10,000 = $150,000)
        var mtmPrices = new Dictionary<SecurityId, CashAmount>
        {
            [isinApple] = CashAmount.FromDecimal(165.00m, currency)
        };

        // 3.0% daily volatility
        var vols = new Dictionary<SecurityId, decimal>
        {
            [isinApple] = 0.03m
        };

        var report = await engine.CalculateMemberMarginAsync(
            memberId,
            new[] { appleObligation },
            vols,
            mtmPrices,
            TimeSpan.FromHours(2)
        );

        // Verification:
        // Position value = 10,000 * 165 = $1,650,000
        // VaR 99% 2-day = $1,650,000 * 2.3263479 * 0.03 * sqrt(2) ≈ $1,650,000 * 0.098711 ≈ $162,873.15
        if (report.InitialMarginRequired.ToDecimal() < 160000m || report.InitialMarginRequired.ToDecimal() > 165000m)
        {
            throw new Exception($"Initial Margin unexpected value: {report.InitialMarginRequired}");
        }

        // Variation Margin = MtM loss of $150,000 ($1,500,000 cash - $1,650,000 current liability)
        if (Math.Abs(report.VariationMarginRequired.ToDecimal() - 150000m) > 0.01m)
        {
            throw new Exception($"Variation Margin unexpected value: {report.VariationMarginRequired}");
        }

        // Total Margin required = ~$312,873.
        // Eligible collateral = $632,500.
        // Since eligible ($632,500) > required (~$312,873), deficit must be 0 and no margin call issued.
        if (!report.MarginDeficit.IsZero)
        {
            throw new Exception($"Expected zero margin deficit, got {report.MarginDeficit}");
        }
        if (report.IssuedMarginCall != null)
        {
            throw new Exception("Unexpected margin call issued when collateral is sufficient");
        }
    }
}
