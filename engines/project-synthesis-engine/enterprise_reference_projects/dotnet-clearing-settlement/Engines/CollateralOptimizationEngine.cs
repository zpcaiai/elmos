namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Cheapest-to-Deliver (CTD) Collateral Allocation and Optimization Engine.
/// Formulates optimal collateral posting choices to minimize opportunity cost of capital
/// while satisfying post-haircut CCP margin requirements and concentration limits.
/// </summary>
public sealed class CollateralOptimizationEngine
{
    public sealed class PledgedAllocation
    {
        public CollateralAsset Asset { get; }
        public CashAmount PledgedNominal { get; }
        public CashAmount EligibleValuation { get; }
        public decimal OpportunityCostBps { get; } // Basis points annualized funding cost

        public PledgedAllocation(CollateralAsset asset, CashAmount pledgedNominal, CashAmount eligibleValuation, decimal opportunityCostBps)
        {
            Asset = asset;
            PledgedNominal = pledgedNominal;
            EligibleValuation = eligibleValuation;
            OpportunityCostBps = opportunityCostBps;
        }
    }

    public sealed class OptimizationResult
    {
        public string MemberId { get; }
        public CashAmount TargetMarginRequirement { get; }
        public CashAmount TotalEligiblePledged { get; }
        public decimal TotalWeightedCostBps { get; }
        public bool RequirementSatisfied { get; }
        public IReadOnlyList<PledgedAllocation> Allocations { get; }

        public OptimizationResult(
            string memberId,
            CashAmount targetMarginRequirement,
            CashAmount totalEligiblePledged,
            decimal totalWeightedCostBps,
            bool requirementSatisfied,
            IReadOnlyList<PledgedAllocation> allocations)
        {
            MemberId = memberId;
            TargetMarginRequirement = targetMarginRequirement;
            TotalEligiblePledged = totalEligiblePledged;
            TotalWeightedCostBps = totalWeightedCostBps;
            RequirementSatisfied = requirementSatisfied;
            Allocations = allocations;
        }
    }

    public sealed class AvailableInventoryItem
    {
        public CollateralAsset Asset { get; }
        public decimal FundingOpportunityCostBps { get; }

        public AvailableInventoryItem(CollateralAsset asset, decimal fundingOpportunityCostBps)
        {
            Asset = asset;
            FundingOpportunityCostBps = fundingOpportunityCostBps;
        }
    }

    /// <summary>
    /// Solves the collateral selection problem: allocates assets with lowest funding cost first,
    /// accounting for haircuts and maximum concentration caps (e.g. max 40% equity).
    /// </summary>
    public OptimizationResult OptimizeCollateralPledge(
        string memberId,
        CashAmount targetRequirement,
        IEnumerable<AvailableInventoryItem> availableInventory,
        decimal maxEquityConcentrationRatio = 0.40m)
    {
        var currency = targetRequirement.Currency;
        // Sort inventory by effective cost: Cost per eligible unit of margin = FundingCost / (1 - Haircut)
        var sortedInventory = availableInventory
            .OrderBy(item =>
            {
                decimal effectiveEfficiency = 1.0m - item.Asset.HaircutPercentage;
                return effectiveEfficiency > 0 ? item.FundingOpportunityCostBps / effectiveEfficiency : decimal.MaxValue;
            })
            .ToList();

        var allocations = new List<PledgedAllocation>();
        CashAmount cumulativeEligible = CashAmount.Zero(currency);
        decimal cumulativeCostNumerator = 0m;
        CashAmount totalEquityEligible = CashAmount.Zero(currency);

        foreach (var item in sortedInventory)
        {
            if (cumulativeEligible >= targetRequirement) break;

            CashAmount eligibleValue = item.Asset.GetEligibleCollateralValue();

            // Enforce equity concentration limits
            if (item.Asset.Type == CollateralType.EligibleEquityBlueChip)
            {
                CashAmount maxAllowedEquity = targetRequirement * maxEquityConcentrationRatio;
                if (totalEquityEligible >= maxAllowedEquity)
                {
                    continue; // Skip equity because concentration cap is reached
                }

                CashAmount remainingEquityCap = maxAllowedEquity - totalEquityEligible;
                if (eligibleValue > remainingEquityCap)
                {
                    // Scale down eligible value
                    decimal scale = (decimal)remainingEquityCap.MinorUnits / eligibleValue.MinorUnits;
                    eligibleValue = remainingEquityCap;
                }
                totalEquityEligible += eligibleValue;
            }

            CashAmount needed = targetRequirement - cumulativeEligible;
            CashAmount allocatedEligible = (eligibleValue <= needed) ? eligibleValue : needed;

            decimal pledgeRatio = (decimal)allocatedEligible.MinorUnits / item.Asset.GetEligibleCollateralValue().MinorUnits;
            CashAmount pledgedNominal = item.Asset.NominalMarketValue * pledgeRatio;

            allocations.Add(new PledgedAllocation(
                item.Asset,
                pledgedNominal,
                allocatedEligible,
                item.FundingOpportunityCostBps
            ));

            cumulativeEligible += allocatedEligible;
            cumulativeCostNumerator += (allocatedEligible.ToDecimal() * item.FundingOpportunityCostBps);
        }

        bool satisfied = cumulativeEligible >= targetRequirement;
        decimal weightedCostBps = cumulativeEligible.MinorUnits > 0
            ? cumulativeCostNumerator / cumulativeEligible.ToDecimal()
            : 0m;

        return new OptimizationResult(
            memberId,
            targetRequirement,
            cumulativeEligible,
            weightedCostBps,
            satisfied,
            allocations
        );
    }
}
