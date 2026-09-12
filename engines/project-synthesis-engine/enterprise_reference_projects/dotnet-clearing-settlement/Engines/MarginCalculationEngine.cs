namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Repositories;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Margin Calculation Engine.
/// Implements Parametric Value-at-Risk (VaR) 99% confidence level Initial Margin (IM)
/// and Mark-to-Market Variation Margin (VM) across member portfolios.
/// </summary>
public sealed class MarginCalculationEngine
{
    private readonly IMarginAccountRepository _marginRepository;

    // Normal distribution 99% one-tailed critical value Z = 2.326
    private const decimal ZScore99 = 2.3263479m;

    // 2-day margin period of risk (MPOR) sqrt(2) ≈ 1.41421356
    private const decimal SqrtMpor2Days = 1.41421356m;

    public MarginCalculationEngine(IMarginAccountRepository marginRepository)
    {
        _marginRepository = marginRepository ?? throw new ArgumentNullException(nameof(marginRepository));
    }

    public sealed class MemberMarginReport
    {
        public string MemberId { get; }
        public CashAmount InitialMarginRequired { get; }
        public CashAmount VariationMarginRequired { get; }
        public CashAmount TotalRequirement { get; }
        public CashAmount TotalEligibleCollateral { get; }
        public CashAmount MarginDeficit { get; }
        public MarginCall? IssuedMarginCall { get; }

        public MemberMarginReport(
            string memberId,
            CashAmount initialMarginRequired,
            CashAmount variationMarginRequired,
            CashAmount totalEligibleCollateral,
            CashAmount marginDeficit,
            MarginCall? issuedMarginCall)
        {
            MemberId = memberId;
            InitialMarginRequired = initialMarginRequired;
            VariationMarginRequired = variationMarginRequired;
            TotalRequirement = initialMarginRequired + variationMarginRequired;
            TotalEligibleCollateral = totalEligibleCollateral;
            MarginDeficit = marginDeficit;
            IssuedMarginCall = issuedMarginCall;
        }
    }

    /// <summary>
    /// Computes IM and VM for a member given their netted obligations and market parameters.
    /// </summary>
    public async Task<MemberMarginReport> CalculateMemberMarginAsync(
        string memberId,
        IEnumerable<ClearingObligation> obligations,
        IReadOnlyDictionary<SecurityId, decimal> dailyVolatilities,
        IReadOnlyDictionary<SecurityId, CashAmount> currentMarkToMarketPrices,
        TimeSpan marginCallSlaWindow)
    {
        var account = await _marginRepository.GetByMemberIdAsync(memberId)
            ?? throw new InvalidOperationException($"Margin account not found for member: {memberId}");

        var currency = account.BaseCurrency;
        CashAmount totalInitialMargin = CashAmount.Zero(currency);
        CashAmount totalVariationMargin = CashAmount.Zero(currency);

        foreach (var obl in obligations)
        {
            if (obl.NetQuantity.IsZero) continue;

            if (!currentMarkToMarketPrices.TryGetValue(obl.SecurityId, out var currentPrice))
                throw new InvalidOperationException($"Missing mark-to-market price for security: {obl.SecurityId}");

            decimal volatility = dailyVolatilities.TryGetValue(obl.SecurityId, out var vol) ? vol : 0.025m; // Default 2.5% daily vol

            // Gross position value at current market price
            long absUnits = obl.NetQuantity.Abs().Units;
            CashAmount positionMarketValue = currentPrice * absUnits;

            // Parametric VaR (99% confidence, 2-day liquidation holding period):
            // IM = MarketValue * Z * sigma * sqrt(T)
            decimal riskFactor = ZScore99 * volatility * SqrtMpor2Days;
            CashAmount positionIm = positionMarketValue * riskFactor;
            totalInitialMargin += positionIm;

            // Variation margin: MTM difference between trade executed price and current MTM price
            CashAmount netCashObligation = obl.NetCashAmount;
            // Value of delivered security minus cash payable
            CashAmount currentContractValue = currentPrice * obl.NetQuantity.Units;
            CashAmount pnl = currentContractValue + netCashObligation;

            if (pnl.IsNegative)
            {
                // Unfavorable MtM creates variation margin liability
                totalVariationMargin += pnl.Abs();
            }
        }

        account.SetMarginRequirements(totalInitialMargin, totalVariationMargin);
        await _marginRepository.SaveAsync(account);

        CashAmount eligibleCollateral = account.CalculateTotalEligibleCollateral();
        CashAmount deficit = account.CalculateMarginDeficit();

        MarginCall? call = null;
        if (deficit.IsPositive)
        {
            string callId = $"MCALL-{memberId}-{DateTime.UtcNow.Ticks}";
            call = new MarginCall(callId, memberId, deficit, marginCallSlaWindow);
        }

        return new MemberMarginReport(
            memberId,
            totalInitialMargin,
            totalVariationMargin,
            eligibleCollateral,
            deficit,
            call
        );
    }
}
