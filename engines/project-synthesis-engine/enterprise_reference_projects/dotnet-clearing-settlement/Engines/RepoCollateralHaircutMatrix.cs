namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Basel III / BCBS-IOSCO Regulatory Collateral Haircut Matrix &amp; Valuation Engine.
/// Computes dynamic haircuts across sovereign debt, corporate bonds, equities, and gold,
/// with foreign exchange (FX) currency mismatch penalties, Wrong-Way Risk (WWR) surcharges,
/// and single-issuer concentration cap adjustments.
/// </summary>
public sealed class RepoCollateralHaircutMatrix
{
    public enum CollateralAssetClass
    {
        SovereignDebt_AAA_AA,
        SovereignDebt_A_BBB,
        CorporateBond_AAA_AA,
        CorporateBond_A_BBB,
        MainIndexEquities,
        OtherLiquidEquities,
        MonetaryGold
    }

    public enum ResidualTenorBand
    {
        UnderOneYear,
        OneToThreeYears,
        ThreeToFiveYears,
        FiveToTenYears,
        OverTenYears
    }

    public sealed record CollateralValuationInput(
        string CollateralId,
        string MemberId,
        string IssuerName,
        CollateralAssetClass AssetClass,
        ResidualTenorBand TenorBand,
        CashAmount MarketValue,
        Currency ObligationCurrency,
        bool HasWrongWayRiskCorrelation,
        decimal IssuerPortfolioConcentrationRatio);

    public sealed record CollateralHaircutResult(
        string CollateralId,
        CashAmount GrossMarketValue,
        decimal BaseHaircutPercent,
        decimal FxMismatchAddOnPercent,
        decimal WrongWayRiskSurchargePercent,
        decimal ConcentrationPenaltyPercent,
        decimal TotalEffectiveHaircutPercent,
        CashAmount NetCollateralValue,
        bool IsEligibleForClearingMargin);

    /// <summary>
    /// Computes the supervisory haircut based on Basel III Table 1 haircut schedules.
    /// </summary>
    public decimal GetSupervisoryBaseHaircut(CollateralAssetClass assetClass, ResidualTenorBand tenor)
    {
        return assetClass switch
        {
            CollateralAssetClass.SovereignDebt_AAA_AA => tenor switch
            {
                ResidualTenorBand.UnderOneYear => 0.5m,
                ResidualTenorBand.OneToThreeYears => 2.0m,
                ResidualTenorBand.ThreeToFiveYears => 3.0m,
                ResidualTenorBand.FiveToTenYears => 4.0m,
                ResidualTenorBand.OverTenYears => 6.0m,
                _ => 6.0m
            },
            CollateralAssetClass.SovereignDebt_A_BBB => tenor switch
            {
                ResidualTenorBand.UnderOneYear => 1.0m,
                ResidualTenorBand.OneToThreeYears => 3.0m,
                ResidualTenorBand.ThreeToFiveYears => 4.0m,
                ResidualTenorBand.FiveToTenYears => 6.0m,
                ResidualTenorBand.OverTenYears => 12.0m,
                _ => 12.0m
            },
            CollateralAssetClass.CorporateBond_AAA_AA => tenor switch
            {
                ResidualTenorBand.UnderOneYear => 1.5m,
                ResidualTenorBand.OneToThreeYears => 4.0m,
                ResidualTenorBand.ThreeToFiveYears => 6.0m,
                ResidualTenorBand.FiveToTenYears => 8.0m,
                ResidualTenorBand.OverTenYears => 12.0m,
                _ => 12.0m
            },
            CollateralAssetClass.CorporateBond_A_BBB => tenor switch
            {
                ResidualTenorBand.UnderOneYear => 3.0m,
                ResidualTenorBand.OneToThreeYears => 6.0m,
                ResidualTenorBand.ThreeToFiveYears => 8.0m,
                ResidualTenorBand.FiveToTenYears => 12.0m,
                ResidualTenorBand.OverTenYears => 18.0m,
                _ => 20.0m
            },
            CollateralAssetClass.MainIndexEquities => 15.0m,
            CollateralAssetClass.OtherLiquidEquities => 25.0m,
            CollateralAssetClass.MonetaryGold => 15.0m,
            _ => 30.0m
        };
    }

    /// <summary>
    /// Evaluates full haircut schedule including currency mismatch, WWR, and concentration limits.
    /// </summary>
    public CollateralHaircutResult EvaluateCollateral(CollateralValuationInput input)
    {
        ArgumentNullException.ThrowIfNull(input);

        decimal baseHaircut = GetSupervisoryBaseHaircut(input.AssetClass, input.TenorBand);

        // FX Mismatch: 8% standard regulatory FX haircut if collateral currency != obligation settlement currency
        decimal fxAddOn = 0.0m;
        if (!input.MarketValue.Currency.Equals(input.ObligationCurrency))
        {
            fxAddOn = 8.0m; // 800 basis points
        }

        // Wrong-Way Risk (WWR): 50% relative markup on base haircut if credit quality correlates with member
        decimal wwrAddOn = 0.0m;
        if (input.HasWrongWayRiskCorrelation)
        {
            wwrAddOn = Math.Max(5.0m, baseHaircut * 0.5m);
        }

        // Concentration penalty: If a single issuer exceeds 20% of member's total posted collateral
        decimal concentrationAddOn = 0.0m;
        if (input.IssuerPortfolioConcentrationRatio > 0.20m)
        {
            decimal excessRatio = input.IssuerPortfolioConcentrationRatio - 0.20m;
            concentrationAddOn = Math.Round(excessRatio * 25.0m, 2); // Progressive penalty
        }

        decimal totalHaircut = Math.Min(95.0m, baseHaircut + fxAddOn + wwrAddOn + concentrationAddOn);
        decimal haircutMultiplier = (100.0m - totalHaircut) / 100.0m;

        decimal grossDec = input.MarketValue.ToDecimal();
        decimal netDec = Math.Max(0m, grossDec * haircutMultiplier);

        var netValue = CashAmount.FromDecimal(netDec, input.MarketValue.Currency);

        // Eligibility threshold: Haircut cannot exceed 50% for core initial margin eligibility
        bool eligible = totalHaircut <= 50.0m;

        return new CollateralHaircutResult(
            input.CollateralId,
            input.MarketValue,
            baseHaircut,
            fxAddOn,
            wwrAddOn,
            concentrationAddOn,
            totalHaircut,
            netValue,
            eligible);
    }
}
