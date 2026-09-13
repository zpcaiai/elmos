namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Intraday Volatility Surge & Large Position Concentration Engine.
/// Detects sudden intraday price spikes breaching 3-sigma thresholds,
/// calculates market depth concentration penalties based on Average Daily Volume (ADV),
/// and issues emergency intraday margin calls.
/// </summary>
public sealed class IntradayMarginAndConcentrationEngine
{
    public sealed class IntradaySurgeAlert
    {
        public SecurityId SecurityId { get; }
        public CashAmount PreviousClosingPrice { get; }
        public CashAmount CurrentIntradayPrice { get; }
        public decimal PriceChangePercentage { get; }
        public decimal VolatilityZScore { get; }
        public bool IsEmergencyThresholdBreached { get; }

        public IntradaySurgeAlert(
            SecurityId securityId,
            CashAmount previousClosingPrice,
            CashAmount currentIntradayPrice,
            decimal priceChangePercentage,
            decimal volatilityZScore,
            bool isEmergencyThresholdBreached)
        {
            SecurityId = securityId;
            PreviousClosingPrice = previousClosingPrice;
            CurrentIntradayPrice = currentIntradayPrice;
            PriceChangePercentage = priceChangePercentage;
            VolatilityZScore = volatilityZScore;
            IsEmergencyThresholdBreached = isEmergencyThresholdBreached;
        }
    }

    public sealed class ConcentrationAssessment
    {
        public string MemberId { get; }
        public SecurityId SecurityId { get; }
        public Quantity MemberPosition { get; }
        public Quantity MarketAverageDailyVolume { get; }
        public decimal AdvParticipationRatio { get; }
        public decimal LiquidityMultiplier { get; }
        public CashAmount BaseMarginRequirement { get; }
        public CashAmount ConcentrationAddOnMargin { get; }
        public CashAmount TotalEffectiveMargin { get; }

        public ConcentrationAssessment(
            string memberId,
            SecurityId securityId,
            Quantity memberPosition,
            Quantity marketAverageDailyVolume,
            decimal advParticipationRatio,
            decimal liquidityMultiplier,
            CashAmount baseMarginRequirement,
            CashAmount concentrationAddOnMargin,
            CashAmount totalEffectiveMargin)
        {
            MemberId = memberId;
            SecurityId = securityId;
            MemberPosition = memberPosition;
            MarketAverageDailyVolume = marketAverageDailyVolume;
            AdvParticipationRatio = advParticipationRatio;
            LiquidityMultiplier = liquidityMultiplier;
            BaseMarginRequirement = baseMarginRequirement;
            ConcentrationAddOnMargin = concentrationAddOnMargin;
            TotalEffectiveMargin = totalEffectiveMargin;
        }
    }

    /// <summary>
    /// Evaluates intraday price tick against statistical volatility bands.
    /// </summary>
    public IntradaySurgeAlert CheckIntradayPriceSurge(
        SecurityId securityId,
        CashAmount previousClose,
        CashAmount currentPrice,
        decimal dailyStandardDeviationPercent)
    {
        if (previousClose.MinorUnits == 0 || dailyStandardDeviationPercent <= 0)
        {
            return new IntradaySurgeAlert(securityId, previousClose, currentPrice, 0, 0, false);
        }

        decimal change = (decimal)(currentPrice.MinorUnits - previousClose.MinorUnits) / (decimal)previousClose.MinorUnits;
        decimal zScore = Math.Abs(change) / dailyStandardDeviationPercent;
        bool breached = zScore >= 3.0m; // 3-sigma statistical excursion

        return new IntradaySurgeAlert(
            securityId,
            previousClose,
            currentPrice,
            Math.Round(change, 4),
            Math.Round(zScore, 2),
            breached);
    }

    /// <summary>
    /// Calculates market liquidation concentration penalty based on position / ADV.
    /// Formula: Multiplier = 1.0 + max(0, (Ratio - 0.20) * 1.5)
    /// </summary>
    public ConcentrationAssessment EvaluateConcentrationPenalty(
        string memberId,
        SecurityId securityId,
        Quantity position,
        Quantity adv,
        CashAmount baseMargin)
    {
        decimal ratio = adv.Units > 0 ? (decimal)position.Units / (decimal)adv.Units : 1.0m;
        decimal multiplier = 1.0m;

        // If member position exceeds 20% of instrument ADV, apply progressive liquidity add-on
        if (ratio > 0.20m)
        {
            multiplier += (ratio - 0.20m) * 1.5m;
        }

        long addOnMinor = (long)((multiplier - 1.0m) * baseMargin.MinorUnits);
        long totalMinor = baseMargin.MinorUnits + addOnMinor;

        var curr = baseMargin.Currency;
        return new ConcentrationAssessment(
            memberId,
            securityId,
            position,
            adv,
            Math.Round(ratio, 4),
            Math.Round(multiplier, 3),
            baseMargin,
            new CashAmount(addOnMinor, curr),
            new CashAmount(totalMinor, curr));
    }
}
