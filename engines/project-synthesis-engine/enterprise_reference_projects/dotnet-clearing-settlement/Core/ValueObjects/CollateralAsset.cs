namespace Elmos.ClearingSettlement.Core.ValueObjects;

using System;

public enum CollateralType
{
    Cash,
    GovernmentTreasuryBill,
    SovereignBondAaa,
    CorporateBondInvestmentGrade,
    EligibleEquityBlueChip
}

/// <summary>
/// A collateral asset pledged by a clearing member with regulatory valuation haircuts.
/// </summary>
public sealed class CollateralAsset
{
    public string AssetId { get; }
    public CollateralType Type { get; }
    public CashAmount NominalMarketValue { get; }
    public decimal HaircutPercentage { get; } // e.g. 0.05m = 5% haircut

    public CollateralAsset(string assetId, CollateralType type, CashAmount nominalMarketValue, decimal? customHaircut = null)
    {
        AssetId = assetId ?? throw new ArgumentNullException(nameof(assetId));
        Type = type;
        NominalMarketValue = nominalMarketValue;
        HaircutPercentage = customHaircut ?? GetDefaultHaircut(type);

        if (HaircutPercentage < 0m || HaircutPercentage > 1m)
            throw new ArgumentOutOfRangeException(nameof(HaircutPercentage), "Haircut must be between 0.0 (0%) and 1.0 (100%)");
    }

    /// <summary>
    /// Regulatory baseline haircuts mandated by CPSS-IOSCO PFMI principles.
    /// </summary>
    public static decimal GetDefaultHaircut(CollateralType type) => type switch
    {
        CollateralType.Cash => 0.00m,                        // 0% haircut for domestic sovereign fiat
        CollateralType.GovernmentTreasuryBill => 0.015m,     // 1.5% haircut for ultra-short T-bills
        CollateralType.SovereignBondAaa => 0.04m,           // 4.0% haircut for AAA sovereign debt
        CollateralType.CorporateBondInvestmentGrade => 0.15m,// 15.0% haircut for IG corporate paper
        CollateralType.EligibleEquityBlueChip => 0.30m,      // 30.0% haircut for liquid index equities
        _ => 0.50m
    };

    /// <summary>
    /// Calculates the net eligible value of this collateral after applying risk haircut.
    /// Net Value = Nominal * (1 - Haircut)
    /// </summary>
    public CashAmount GetEligibleCollateralValue()
    {
        decimal factor = 1.0m - HaircutPercentage;
        return NominalMarketValue * factor;
    }
}
