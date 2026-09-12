namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.ValueObjects;

public enum AllocationOptimizationStrategy
{
    CheapestToDeliver,       // Pledges highest haircut / lowest liquidity eligible assets first
    HighestLiquidityBuffer,  // Pledges highest quality (Cash, T-Bills) first to maximize cushion
    BalancedDiversification  // Spreads across issuers and asset classes to avoid concentration
}

public sealed class CollateralBasketEligibilityCriteria
{
    public decimal MaxSingleIssuerConcentration { get; init; } = 0.30m; // Max 30% single corporate/bank issuer
    public decimal MaxCorporatePaperLimit { get; init; } = 0.35m;       // Max 35% non-sovereign corporate bonds
    public decimal MinSovereignFloor { get; init; } = 0.40m;            // At least 40% G-10 sovereign / central bank paper
    public decimal CurrencyMismatchAddOnHaircut { get; init; } = 0.08m; // 8% BCBS-IOSCO standard FX mismatch haircut
}

public sealed class AvailableCollateralInventoryItem
{
    public string AssetId { get; }
    public string IssuerId { get; }
    public CollateralType Type { get; }
    public Currency AssetCurrency { get; }
    public CashAmount AvailableNominalValue { get; }
    public decimal BaselineHaircut { get; }

    public AvailableCollateralInventoryItem(
        string assetId,
        string issuerId,
        CollateralType type,
        Currency assetCurrency,
        CashAmount availableNominalValue,
        decimal? customHaircut = null)
    {
        AssetId = assetId ?? throw new ArgumentNullException(nameof(assetId));
        IssuerId = issuerId ?? throw new ArgumentNullException(nameof(issuerId));
        Type = type;
        AssetCurrency = assetCurrency;
        AvailableNominalValue = availableNominalValue;
        BaselineHaircut = customHaircut ?? CollateralAsset.GetDefaultHaircut(type);
    }
}

public sealed class AllocatedCollateralItem
{
    public string AssetId { get; init; } = string.Empty;
    public string IssuerId { get; init; } = string.Empty;
    public CollateralType Type { get; init; }
    public CashAmount AllocatedNominalValue { get; init; }
    public decimal AppliedHaircutPercentage { get; init; }
    public CashAmount NetEligibleValue { get; init; }
}

public sealed class TripartyAllocationResult
{
    public string MemberId { get; init; } = string.Empty;
    public CashAmount RequiredMarginAmount { get; init; }
    public CashAmount TotalAllocatedNominalValue { get; init; }
    public CashAmount TotalNetEligibleValue { get; init; }
    public CashAmount CollateralExcessDeficit { get; init; }
    public bool IsFullyCovered => CollateralExcessDeficit.Amount >= 0;
    public IReadOnlyList<AllocatedCollateralItem> AllocatedItems { get; init; } = Array.Empty<AllocatedCollateralItem>();
    public bool ConcentrationRulesPassed { get; init; }
    public List<string> RuleBreaches { get; init; } = new();
}

/// <summary>
/// Tri-party repo & securities financing transaction (SFT) collateral allocation algorithm.
/// Enforces BCBS-IOSCO margin rules, haircuts, FX mismatch add-ons, and issuer concentration limits.
/// </summary>
public sealed class TripartyCollateralAllocationEngine
{
    private readonly CollateralBasketEligibilityCriteria _criteria;

    public TripartyCollateralAllocationEngine(CollateralBasketEligibilityCriteria? criteria = null)
    {
        _criteria = criteria ?? new CollateralBasketEligibilityCriteria();
    }

    public TripartyAllocationResult AllocateCollateral(
        string memberId,
        CashAmount requiredMargin,
        IReadOnlyList<AvailableCollateralInventoryItem> inventory,
        AllocationOptimizationStrategy strategy = AllocationOptimizationStrategy.CheapestToDeliver)
    {
        if (string.IsNullOrWhiteSpace(memberId))
            throw new ArgumentNullException(nameof(memberId));

        if (requiredMargin.Amount <= 0)
        {
            return new TripartyAllocationResult
            {
                MemberId = memberId,
                RequiredMarginAmount = requiredMargin,
                TotalAllocatedNominalValue = CashAmount.Zero(requiredMargin.Currency),
                TotalNetEligibleValue = CashAmount.Zero(requiredMargin.Currency),
                CollateralExcessDeficit = CashAmount.Zero(requiredMargin.Currency),
                ConcentrationRulesPassed = true
            };
        }

        // Sort candidate inventory according to selected strategy
        var sortedInventory = SortInventory(inventory, requiredMargin.Currency, strategy);

        var allocatedItems = new List<AllocatedCollateralItem>();
        decimal remainingRequirement = requiredMargin.Amount;
        decimal totalAllocatedNominal = 0m;
        decimal totalAllocatedEligible = 0m;

        foreach (var item in sortedInventory)
        {
            if (remainingRequirement <= 0) break;

            // Calculate total effective haircut including FX mismatch
            decimal effectiveHaircut = item.BaselineHaircut;
            if (item.AssetCurrency != requiredMargin.Currency)
            {
                effectiveHaircut += _criteria.CurrencyMismatchAddOnHaircut;
            }
            effectiveHaircut = Math.Min(effectiveHaircut, 0.99m); // Cap below 100%

            decimal netFactor = 1.0m - effectiveHaircut;
            decimal maxEligibleFromItem = item.AvailableNominalValue.Amount * netFactor;

            decimal neededFromItem = Math.Min(remainingRequirement, maxEligibleFromItem);
            decimal nominalToAllocate = Math.Ceiling((neededFromItem / netFactor) * 100m) / 100m;
            nominalToAllocate = Math.Min(nominalToAllocate, item.AvailableNominalValue.Amount);

            decimal eligibleFromNominal = Math.Round(nominalToAllocate * netFactor, 2);

            allocatedItems.Add(new AllocatedCollateralItem
            {
                AssetId = item.AssetId,
                IssuerId = item.IssuerId,
                Type = item.Type,
                AllocatedNominalValue = CashAmount.FromDecimal(nominalToAllocate, requiredMargin.Currency),
                AppliedHaircutPercentage = effectiveHaircut,
                NetEligibleValue = CashAmount.FromDecimal(eligibleFromNominal, requiredMargin.Currency)
            });

            totalAllocatedNominal += nominalToAllocate;
            totalAllocatedEligible += eligibleFromNominal;
            remainingRequirement -= eligibleFromNominal;
        }

        // Verify concentration limits
        var breaches = new List<string>();
        if (totalAllocatedEligible > 0)
        {
            // 1. Single non-sovereign issuer concentration (sovereigns are governed by sovereign floor)
            var issuerGroups = allocatedItems
                .Where(i => i.Type != CollateralType.Cash &&
                            i.Type != CollateralType.GovernmentTreasuryBill &&
                            i.Type != CollateralType.SovereignBondAaa)
                .GroupBy(i => i.IssuerId);

            foreach (var grp in issuerGroups)
            {
                decimal issuerTotal = grp.Sum(i => i.NetEligibleValue.Amount);
                decimal share = issuerTotal / totalAllocatedEligible;
                if (share > _criteria.MaxSingleIssuerConcentration)
                {
                    breaches.Add($"Issuer '{grp.Key}' exceeds concentration limit of {_criteria.MaxSingleIssuerConcentration:P0} with {share:P1}");
                }
            }

            // 2. Corporate paper limit
            decimal corpTotal = allocatedItems
                .Where(i => i.Type == CollateralType.CorporateBondInvestmentGrade || i.Type == CollateralType.EligibleEquityBlueChip)
                .Sum(i => i.NetEligibleValue.Amount);
            decimal corpShare = corpTotal / totalAllocatedEligible;
            if (corpShare > _criteria.MaxCorporatePaperLimit)
            {
                breaches.Add($"Corporate collateral exceeds ceiling of {_criteria.MaxCorporatePaperLimit:P0} with {corpShare:P1}");
            }

            // 3. Sovereign debt floor
            decimal sovereignTotal = allocatedItems
                .Where(i => i.Type == CollateralType.Cash || i.Type == CollateralType.GovernmentTreasuryBill || i.Type == CollateralType.SovereignBondAaa)
                .Sum(i => i.NetEligibleValue.Amount);
            decimal sovereignShare = sovereignTotal / totalAllocatedEligible;
            if (sovereignShare < _criteria.MinSovereignFloor)
            {
                breaches.Add($"Sovereign collateral fails floor of {_criteria.MinSovereignFloor:P0} with {sovereignShare:P1}");
            }
        }

        decimal netExcess = totalAllocatedEligible - requiredMargin.Amount;

        return new TripartyAllocationResult
        {
            MemberId = memberId,
            RequiredMarginAmount = requiredMargin,
            TotalAllocatedNominalValue = CashAmount.FromDecimal(totalAllocatedNominal, requiredMargin.Currency),
            TotalNetEligibleValue = CashAmount.FromDecimal(totalAllocatedEligible, requiredMargin.Currency),
            CollateralExcessDeficit = CashAmount.FromDecimal(netExcess, requiredMargin.Currency),
            AllocatedItems = allocatedItems,
            ConcentrationRulesPassed = breaches.Count == 0,
            RuleBreaches = breaches
        };
    }

    private static List<AvailableCollateralInventoryItem> SortInventory(
        IEnumerable<AvailableCollateralInventoryItem> inventory,
        Currency obligationCurrency,
        AllocationOptimizationStrategy strategy)
    {
        return strategy switch
        {
            AllocationOptimizationStrategy.CheapestToDeliver => inventory
                .OrderByDescending(i => i.BaselineHaircut)
                .ThenBy(i => i.AssetCurrency == obligationCurrency ? 1 : 0)
                .ToList(),

            AllocationOptimizationStrategy.HighestLiquidityBuffer => inventory
                .OrderBy(i => i.BaselineHaircut)
                .ThenBy(i => i.AssetCurrency == obligationCurrency ? 0 : 1)
                .ToList(),

            AllocationOptimizationStrategy.BalancedDiversification => inventory
                .OrderBy(i => i.IssuerId)
                .ThenBy(i => i.BaselineHaircut)
                .ToList(),

            _ => inventory.ToList()
        };
    }
}
