namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.Repositories;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// CPSS-IOSCO Principles for Financial Market Infrastructures (PFMI) Default Waterfall Engine.
/// Governs sequential liquidation and mutualized loss absorption in clearing member defaults.
/// </summary>
public sealed class DefaultWaterfallEngine
{
    private readonly IMemberRepository _memberRepository;
    private readonly IMarginAccountRepository _marginRepository;

    public sealed class WaterfallTrancheAbsorption
    {
        public WaterfallTranche Tranche { get; }
        public CashAmount AvailableCapacity { get; }
        public CashAmount AbsorbedAmount { get; }
        public CashAmount RemainingLoss { get; }

        public WaterfallTrancheAbsorption(
            WaterfallTranche tranche,
            CashAmount availableCapacity,
            CashAmount absorbedAmount,
            CashAmount remainingLoss)
        {
            Tranche = tranche;
            AvailableCapacity = availableCapacity;
            AbsorbedAmount = absorbedAmount;
            RemainingLoss = remainingLoss;
        }
    }

    public sealed class DefaultWaterfallExecutionResult
    {
        public string DefaulterMemberId { get; }
        public CashAmount TotalUncoveredDefaultLoss { get; }
        public CashAmount TotalAbsorbedLoss { get; }
        public CashAmount UnabsorbedResidualLoss { get; }
        public bool FullyAbsorbed { get; }
        public IReadOnlyList<WaterfallTrancheAbsorption> Tranches { get; }

        public DefaultWaterfallExecutionResult(
            string defaulterMemberId,
            CashAmount totalUncoveredDefaultLoss,
            CashAmount totalAbsorbedLoss,
            CashAmount unabsorbedResidualLoss,
            bool fullyAbsorbed,
            IReadOnlyList<WaterfallTrancheAbsorption> tranches)
        {
            DefaulterMemberId = defaulterMemberId;
            TotalUncoveredDefaultLoss = totalUncoveredDefaultLoss;
            TotalAbsorbedLoss = totalAbsorbedLoss;
            UnabsorbedResidualLoss = unabsorbedResidualLoss;
            FullyAbsorbed = fullyAbsorbed;
            Tranches = tranches;
        }
    }

    public DefaultWaterfallEngine(
        IMemberRepository memberRepository,
        IMarginAccountRepository marginRepository)
    {
        _memberRepository = memberRepository ?? throw new ArgumentNullException(nameof(memberRepository));
        _marginRepository = marginRepository ?? throw new ArgumentNullException(nameof(marginRepository));
    }

    /// <summary>
    /// Executes the complete CPM-IOSCO waterfall sequence to absorb closeout losses.
    /// </summary>
    public async Task<DefaultWaterfallExecutionResult> ExecuteWaterfallAsync(
        string defaulterMemberId,
        CashAmount totalCloseoutLoss,
        CashAmount ccpSkinInTheGame,
        CashAmount ccpEquityCapitalReserve)
    {
        var defaulter = await _memberRepository.GetByIdAsync(defaulterMemberId)
            ?? throw new InvalidOperationException($"Defaulter member {defaulterMemberId} not found");

        var defaulterMarginAccount = await _marginRepository.GetByMemberIdAsync(defaulterMemberId)
            ?? throw new InvalidOperationException($"Margin account for defaulter {defaulterMemberId} not found");

        var currency = totalCloseoutLoss.Currency;
        var activeMembers = await _memberRepository.GetAllActiveAsync();
        var survivingMembers = activeMembers.Where(m => m.MemberId != defaulterMemberId).ToList();

        defaulter.DeclareDefault("Closeout loss liquidation triggered");
        await _memberRepository.SaveAsync(defaulter);

        var tranches = new List<WaterfallTrancheAbsorption>();
        CashAmount remainingLoss = totalCloseoutLoss;

        // Tranche 1: Defaulter's Initial Margin & Collateral
        CashAmount defaulterCollateral = defaulterMarginAccount.CalculateTotalEligibleCollateral();
        CashAmount t1Absorbed = AbsorbTranche(ref remainingLoss, defaulterCollateral);
        tranches.Add(new WaterfallTrancheAbsorption(WaterfallTranche.DefaulterInitialMargin, defaulterCollateral, t1Absorbed, remainingLoss));

        // Tranche 2: Defaulter's Contribution to Default Fund
        if (remainingLoss.IsPositive)
        {
            CashAmount defaulterDfContribution = defaulter.DefaultFundContribution;
            CashAmount t2Absorbed = AbsorbTranche(ref remainingLoss, defaulterDfContribution);
            tranches.Add(new WaterfallTrancheAbsorption(WaterfallTranche.DefaulterDefaultFundContribution, defaulterDfContribution, t2Absorbed, remainingLoss));
        }

        // Tranche 3: CCP Skin-in-the-Game (First-Loss CCP Capital tranche)
        if (remainingLoss.IsPositive)
        {
            CashAmount t3Absorbed = AbsorbTranche(ref remainingLoss, ccpSkinInTheGame);
            tranches.Add(new WaterfallTrancheAbsorption(WaterfallTranche.CcpSkinInTheGameFirstLoss, ccpSkinInTheGame, t3Absorbed, remainingLoss));
        }

        // Tranche 4: Surviving Members' Mutualized Default Fund
        if (remainingLoss.IsPositive)
        {
            CashAmount totalSurvivingDf = CashAmount.Zero(currency);
            foreach (var sm in survivingMembers)
            {
                totalSurvivingDf += sm.DefaultFundContribution;
            }

            CashAmount t4Absorbed = AbsorbTranche(ref remainingLoss, totalSurvivingDf);
            tranches.Add(new WaterfallTrancheAbsorption(WaterfallTranche.SurvivingMembersDefaultFund, totalSurvivingDf, t4Absorbed, remainingLoss));
        }

        // Tranche 5: CCP Equity Capital Reserve (Second-Loss)
        if (remainingLoss.IsPositive)
        {
            CashAmount t5Absorbed = AbsorbTranche(ref remainingLoss, ccpEquityCapitalReserve);
            tranches.Add(new WaterfallTrancheAbsorption(WaterfallTranche.CcpCapitalReserve, ccpEquityCapitalReserve, t5Absorbed, remainingLoss));
        }

        CashAmount totalAbsorbed = totalCloseoutLoss - remainingLoss;
        bool fullyAbsorbed = remainingLoss.IsZero;

        return new DefaultWaterfallExecutionResult(
            defaulterMemberId,
            totalCloseoutLoss,
            totalAbsorbed,
            remainingLoss,
            fullyAbsorbed,
            tranches
        );
    }

    private static CashAmount AbsorbTranche(ref CashAmount remainingLoss, CashAmount trancheCapacity)
    {
        if (remainingLoss <= trancheCapacity)
        {
            CashAmount absorbed = remainingLoss;
            remainingLoss = CashAmount.Zero(remainingLoss.Currency);
            return absorbed;
        }
        else
        {
            CashAmount absorbed = trancheCapacity;
            remainingLoss -= trancheCapacity;
            return absorbed;
        }
    }
}
