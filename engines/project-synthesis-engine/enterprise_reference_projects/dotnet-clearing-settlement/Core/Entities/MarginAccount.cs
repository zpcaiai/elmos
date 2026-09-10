namespace Elmos.ClearingSettlement.Core.Entities;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Member's collateral and margin ledger with real-time haircut valuation and deficit monitoring.
/// </summary>
public sealed class MarginAccount
{
    public string AccountId { get; }
    public string MemberId { get; }
    public Currency BaseCurrency { get; }

    private readonly List<CollateralAsset> _postedCollateral = new();
    public IReadOnlyList<CollateralAsset> PostedCollateral => _postedCollateral.AsReadOnly();

    public CashAmount RequiredInitialMargin { get; private set; }
    public CashAmount RequiredVariationMargin { get; private set; }

    public MarginAccount(string accountId, string memberId, Currency baseCurrency)
    {
        AccountId = accountId ?? throw new ArgumentNullException(nameof(accountId));
        MemberId = memberId ?? throw new ArgumentNullException(nameof(memberId));
        BaseCurrency = baseCurrency;
        RequiredInitialMargin = CashAmount.Zero(baseCurrency);
        RequiredVariationMargin = CashAmount.Zero(baseCurrency);
    }

    public void DepositCollateral(CollateralAsset asset)
    {
        if (asset.NominalMarketValue.Currency != BaseCurrency)
            throw new ArgumentException($"Collateral currency {asset.NominalMarketValue.Currency} does not match margin account base currency {BaseCurrency}");

        _postedCollateral.Add(asset);
    }

    public void WithdrawCollateral(string assetId)
    {
        int index = _postedCollateral.FindIndex(a => a.AssetId == assetId);
        if (index < 0)
            throw new ArgumentException($"Asset {assetId} not found in margin account");

        CollateralAsset asset = _postedCollateral[index];
        CashAmount eligibleValueAfterRemoval = CalculateTotalEligibleCollateral().Subtract(asset.GetEligibleCollateralValue());
        CashAmount totalRequired = GetTotalMarginRequirement();

        if (eligibleValueAfterRemoval < totalRequired)
        {
            throw new InvalidOperationException($"Cannot withdraw collateral: remaining eligible value {eligibleValueAfterRemoval} would be below total requirement {totalRequired}");
        }

        _postedCollateral.RemoveAt(index);
    }

    public void SetMarginRequirements(CashAmount initialMargin, CashAmount variationMargin)
    {
        RequiredInitialMargin = initialMargin;
        RequiredVariationMargin = variationMargin;
    }

    public CashAmount CalculateTotalEligibleCollateral()
    {
        CashAmount total = CashAmount.Zero(BaseCurrency);
        foreach (var asset in _postedCollateral)
        {
            total += asset.GetEligibleCollateralValue();
        }
        return total;
    }

    public CashAmount GetTotalMarginRequirement() => RequiredInitialMargin + RequiredVariationMargin;

    public CashAmount CalculateMarginDeficit()
    {
        CashAmount eligibleCollateral = CalculateTotalEligibleCollateral();
        CashAmount required = GetTotalMarginRequirement();

        if (eligibleCollateral < required)
        {
            return required - eligibleCollateral;
        }
        return CashAmount.Zero(BaseCurrency);
    }

    public bool HasDeficit() => CalculateMarginDeficit().IsPositive;
}
