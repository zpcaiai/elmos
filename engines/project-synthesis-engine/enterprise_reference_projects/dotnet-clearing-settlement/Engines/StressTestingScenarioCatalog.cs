namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Regulatory Macro Stress Testing & Cover-2 Capital Adequacy Engine.
/// Implements CPMI-IOSCO Principles for Financial Market Infrastructures (PFMI Principle 4 & 7).
/// Evaluates clearing house liquidity resilience against historical catastrophic market shocks
/// and executes reverse stress testing to evaluate default fund exhaustion boundaries.
/// </summary>
public sealed class StressTestingScenarioCatalog
{
    public sealed class MacroShockParameters
    {
        public string ScenarioName { get; }
        public string Description { get; }
        public decimal EquityPriceShockPercent { get; }      // e.g. -0.45 for -45%
        public decimal FixedIncomeYieldShockBps { get; }      // e.g. +300 bps
        public decimal VolatilityMultiplier { get; }          // e.g. 3.5x
        public decimal CollateralHaircutAddOnPercent { get; } // e.g. +0.15 (+15% additional haircut)
        public decimal LiquidityDryUpDiscountPercent { get; } // e.g. -0.10 (-10% liquidation discount)

        public MacroShockParameters(
            string scenarioName,
            string description,
            decimal equityPriceShockPercent,
            decimal fixedIncomeYieldShockBps,
            decimal volatilityMultiplier,
            decimal collateralHaircutAddOnPercent,
            decimal liquidityDryUpDiscountPercent)
        {
            ScenarioName = scenarioName;
            Description = description;
            EquityPriceShockPercent = equityPriceShockPercent;
            FixedIncomeYieldShockBps = fixedIncomeYieldShockBps;
            VolatilityMultiplier = volatilityMultiplier;
            CollateralHaircutAddOnPercent = collateralHaircutAddOnPercent;
            LiquidityDryUpDiscountPercent = liquidityDryUpDiscountPercent;
        }
    }

    public static readonly MacroShockParameters Lehman2008Shock = new(
        "2008_LEHMAN_GLOBAL_FINANCIAL_CRISIS",
        "Severe counterparty cascading failures, credit spread explosion (+400 bps), 45% equity collapse, liquidity freezing.",
        equityPriceShockPercent: -0.45m,
        fixedIncomeYieldShockBps: 400m,
        volatilityMultiplier: 4.0m,
        collateralHaircutAddOnPercent: 0.20m,
        liquidityDryUpDiscountPercent: 0.15m
    );

    public static readonly MacroShockParameters Covid2020DashForCash = new(
        "2020_COVID_DASH_FOR_CASH",
        "Extreme intraday volatility spikes (VIX > 80), Treasury basis widening, rapid global asset liquidation.",
        equityPriceShockPercent: -0.35m,
        fixedIncomeYieldShockBps: 200m,
        volatilityMultiplier: 3.5m,
        collateralHaircutAddOnPercent: 0.12m,
        liquidityDryUpDiscountPercent: 0.10m
    );

    public static readonly MacroShockParameters Svb2023BankingRun = new(
        "2023_SVB_REGIONAL_BANK_RUN",
        "High-velocity digital bank runs, duration mismatch losses on held-to-maturity bonds, regional contagion.",
        equityPriceShockPercent: -0.25m,
        fixedIncomeYieldShockBps: 300m,
        volatilityMultiplier: 2.8m,
        collateralHaircutAddOnPercent: 0.18m,
        liquidityDryUpDiscountPercent: 0.12m
    );

    public sealed class MemberStressedExposure
    {
        public string MemberId { get; }
        public CashAmount BaseMarginRequirement { get; }
        public CashAmount StressedLoss { get; }
        public CashAmount PostedCollateralStressedValue { get; }
        public CashAmount NetLossAfterCollateral { get; }

        public MemberStressedExposure(
            string memberId,
            CashAmount baseMarginRequirement,
            CashAmount stressedLoss,
            CashAmount postedCollateralStressedValue,
            CashAmount netLossAfterCollateral)
        {
            MemberId = memberId;
            BaseMarginRequirement = baseMarginRequirement;
            StressedLoss = stressedLoss;
            PostedCollateralStressedValue = postedCollateralStressedValue;
            NetLossAfterCollateral = netLossAfterCollateral;
        }
    }

    public sealed class CoverTwoStressTestResult
    {
        public string ScenarioName { get; }
        public IReadOnlyList<MemberStressedExposure> MemberExposures { get; }
        public string TopMember1Id { get; }
        public string TopMember2Id { get; }
        public CashAmount CoverTwoCombinedShortfall { get; }
        public CashAmount CcpDefaultFundResources { get; }
        public CashAmount SurplusOrDeficit { get; }
        public bool CoverTwoStandardSatisfied { get; }

        public CoverTwoStressTestResult(
            string scenarioName,
            IReadOnlyList<MemberStressedExposure> memberExposures,
            string topMember1Id,
            string topMember2Id,
            CashAmount coverTwoCombinedShortfall,
            CashAmount ccpDefaultFundResources,
            CashAmount surplusOrDeficit,
            bool coverTwoStandardSatisfied)
        {
            ScenarioName = scenarioName;
            MemberExposures = memberExposures;
            TopMember1Id = topMember1Id;
            TopMember2Id = topMember2Id;
            CoverTwoCombinedShortfall = coverTwoCombinedShortfall;
            CcpDefaultFundResources = ccpDefaultFundResources;
            SurplusOrDeficit = surplusOrDeficit;
            CoverTwoStandardSatisfied = coverTwoStandardSatisfied;
        }
    }

    /// <summary>
    /// Evaluates the CCP against Cover-2 standard: Must withstand simultaneous default
    /// of the two members generating the largest aggregate stressed credit exposure.
    /// </summary>
    public CoverTwoStressTestResult RunCoverTwoStressTest(
        MacroShockParameters scenario,
        IReadOnlyDictionary<string, (CashAmount GrossLongNotional, CashAmount GrossShortNotional, CashAmount PostedCollateral)> memberPortfolios,
        CashAmount ccpTotalDefaultFund)
    {
        var exposures = new List<MemberStressedExposure>();
        var curr = ccpTotalDefaultFund.Currency;

        foreach (var (memberId, data) in memberPortfolios)
        {
            // Shocked net loss: Short positions benefit, Long positions suffer equity/yield shocks
            decimal longLoss = data.GrossLongNotional.MinorUnits * Math.Abs(scenario.EquityPriceShockPercent);
            decimal liquidationCost = (data.GrossLongNotional.MinorUnits + data.GrossShortNotional.MinorUnits) * scenario.LiquidityDryUpDiscountPercent;
            long totalStressedLossMinor = (long)(longLoss + liquidationCost);

            // Collateral stressed value after additional haircut
            decimal haircutFactor = Math.Max(0m, 1.0m - scenario.CollateralHaircutAddOnPercent);
            long stressedCollatMinor = (long)(data.PostedCollateral.MinorUnits * haircutFactor);

            long netLossMinor = Math.Max(0, totalStressedLossMinor - stressedCollatMinor);

            exposures.Add(new MemberStressedExposure(
                memberId,
                data.PostedCollateral,
                new CashAmount(totalStressedLossMinor, curr),
                new CashAmount(stressedCollatMinor, curr),
                new CashAmount(netLossMinor, curr)));
        }

        // Sort members by NetLossAfterCollateral descending
        var sorted = exposures.OrderByDescending(e => e.NetLossAfterCollateral.MinorUnits).ToList();
        var top1 = sorted.Count > 0 ? sorted[0] : null;
        var top2 = sorted.Count > 1 ? sorted[1] : null;

        long top1Loss = top1?.NetLossAfterCollateral.MinorUnits ?? 0;
        long top2Loss = top2?.NetLossAfterCollateral.MinorUnits ?? 0;
        long cover2CombinedMinor = top1Loss + top2Loss;

        long surplusMinor = ccpTotalDefaultFund.MinorUnits - cover2CombinedMinor;
        bool satisfied = surplusMinor >= 0;

        return new CoverTwoStressTestResult(
            scenario.ScenarioName,
            exposures,
            top1?.MemberId ?? "N/A",
            top2?.MemberId ?? "N/A",
            new CashAmount(cover2CombinedMinor, curr),
            ccpTotalDefaultFund,
            new CashAmount(surplusMinor, curr),
            satisfied);
    }
}
