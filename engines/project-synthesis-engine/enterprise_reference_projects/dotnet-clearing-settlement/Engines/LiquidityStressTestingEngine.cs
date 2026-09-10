namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.ValueObjects;

public enum StressScenario
{
    LehmanDefault2008_SevereMarketDownturn,
    CovidMarch2020_LiquidityFreezout,
    HistoricalRateShock_300BpsParallelShift,
    IdiosyncraticTechSelloff_50PercentDrop
}

/// <summary>
/// CCP Liquidity Stress Testing Engine conforming to CPSS-IOSCO Principle 7 (Liquidity Risk).
/// Evaluates 'Cover 1' (largest member default) and 'Cover 2' (two largest members default)
/// under extreme-but-plausible market stress conditions.
/// </summary>
public sealed class LiquidityStressTestingEngine
{
    public sealed class StressTestReport
    {
        public StressScenario Scenario { get; }
        public CashAmount TotalQualifyingLiquidResources { get; }
        public string LargestDefaulterId { get; }
        public CashAmount Cover1LiquidityRequirement { get; }
        public bool Cover1Compliant { get; }
        public string SecondLargestDefaulterId { get; }
        public CashAmount Cover2LiquidityRequirement { get; }
        public bool Cover2Compliant { get; }
        public CashAmount Cover2SurplusOrDeficit { get; }

        public StressTestReport(
            StressScenario scenario,
            CashAmount totalQualifyingLiquidResources,
            string largestDefaulterId,
            CashAmount cover1LiquidityRequirement,
            bool cover1Compliant,
            string secondLargestDefaulterId,
            CashAmount cover2LiquidityRequirement,
            bool cover2Compliant,
            CashAmount cover2SurplusOrDeficit)
        {
            Scenario = scenario;
            TotalQualifyingLiquidResources = totalQualifyingLiquidResources;
            LargestDefaulterId = largestDefaulterId;
            Cover1LiquidityRequirement = cover1LiquidityRequirement;
            Cover1Compliant = cover1Compliant;
            SecondLargestDefaulterId = secondLargestDefaulterId;
            Cover2LiquidityRequirement = cover2LiquidityRequirement;
            Cover2Compliant = cover2Compliant;
            Cover2SurplusOrDeficit = cover2SurplusOrDeficit;
        }
    }

    public StressTestReport RunCover1AndCover2StressTest(
        StressScenario scenario,
        CashAmount qualifyingLiquidResources,
        IReadOnlyDictionary<string, CashAmount> memberPaymentObligations)
    {
        if (memberPaymentObligations.Count < 2)
            throw new ArgumentException("Stress test requires at least 2 clearing members", nameof(memberPaymentObligations));

        var currency = qualifyingLiquidResources.Currency;

        // Sort members by gross cash payment obligation descending (largest cash draw on CCP)
        var rankedMembers = memberPaymentObligations
            .OrderByDescending(kv => kv.Value.MinorUnits)
            .ToList();

        var top1 = rankedMembers[0];
        var top2 = rankedMembers[1];

        // Cover 1 requirement: liquidity needed to settle the single largest participant's obligations
        CashAmount cover1Req = top1.Value;
        bool cover1Pass = qualifyingLiquidResources >= cover1Req;

        // Cover 2 requirement: liquidity needed to settle the two largest participants simultaneously
        CashAmount cover2Req = top1.Value + top2.Value;
        bool cover2Pass = qualifyingLiquidResources >= cover2Req;

        CashAmount surplusOrDeficit = qualifyingLiquidResources - cover2Req;

        return new StressTestReport(
            scenario,
            qualifyingLiquidResources,
            top1.Key,
            cover1Req,
            cover1Pass,
            top2.Key,
            cover2Req,
            cover2Pass,
            surplusOrDeficit
        );
    }
}
