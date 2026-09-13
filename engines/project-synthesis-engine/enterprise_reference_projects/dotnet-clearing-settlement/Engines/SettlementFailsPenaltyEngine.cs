namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.ValueObjects;

public enum FinancialInstrumentAssetClass
{
    LiquidEquity,              // 1.00 bps daily penalty
    IlliquidEquityOrSme,       // 1.00 bps daily penalty, 7-day buy-in window
    SovereignDebtAaa,          // 0.10 bps daily penalty
    CorporateBondInvestmentGrade // 0.50 bps daily penalty
}

public sealed class SettlementFailRecord
{
    public string FailId { get; }
    public string FailingMemberId { get; }
    public string ReceivingMemberId { get; }
    public string SecurityIsin { get; }
    public FinancialInstrumentAssetClass AssetClass { get; }
    public CashAmount TradeMarketValue { get; }
    public DateOnly IntendedSettlementDate { get; }
    public int DaysFailed { get; }

    public SettlementFailRecord(
        string failId,
        string failingMemberId,
        string receivingMemberId,
        string securityIsin,
        FinancialInstrumentAssetClass assetClass,
        CashAmount tradeMarketValue,
        DateOnly intendedSettlementDate,
        int daysFailed)
    {
        FailId = failId ?? throw new ArgumentNullException(nameof(failId));
        FailingMemberId = failingMemberId ?? throw new ArgumentNullException(nameof(failingMemberId));
        ReceivingMemberId = receivingMemberId ?? throw new ArgumentNullException(nameof(receivingMemberId));
        SecurityIsin = securityIsin ?? throw new ArgumentNullException(nameof(securityIsin));
        AssetClass = assetClass;
        TradeMarketValue = tradeMarketValue;
        IntendedSettlementDate = intendedSettlementDate;
        DaysFailed = daysFailed >= 0 ? daysFailed : throw new ArgumentOutOfRangeException(nameof(daysFailed));
    }
}

public sealed class DailyFailPenaltyAssessment
{
    public string FailId { get; init; } = string.Empty;
    public string FailingMemberId { get; init; } = string.Empty;
    public string ReceivingMemberId { get; init; } = string.Empty;
    public decimal DailyPenaltyRateBps { get; init; }
    public CashAmount DailyPenaltyAmount { get; init; }
    public CashAmount CumulativePenaltyAmount { get; init; }
    public bool BuyInWindowTriggered { get; init; }
}

public sealed class MandatoryBuyInResult
{
    public string FailId { get; init; } = string.Empty;
    public bool BuyInSuccessful { get; init; }
    public CashAmount OriginalSettlementValue { get; init; }
    public CashAmount ExecutionOrCashCompensationValue { get; init; }
    public CashAmount PriceDifferenceCompensationToReceiver { get; init; }
    public string ResolutionType { get; init; } = string.Empty; // "PHYSICAL_BUY_IN" or "CASH_COMPENSATION"
}

/// <summary>
/// CSDR (Central Securities Depositories Regulation) Settlement Discipline Regime & Buy-In Engine.
/// Computes daily fail penalties and mandatory buy-in / cash compensation settlements.
/// </summary>
public sealed class SettlementFailsPenaltyEngine
{
    public decimal GetStatutoryDailyPenaltyBps(FinancialInstrumentAssetClass assetClass) => assetClass switch
    {
        FinancialInstrumentAssetClass.LiquidEquity => 1.00m,               // 1 bp per day
        FinancialInstrumentAssetClass.IlliquidEquityOrSme => 1.00m,        // 1 bp per day
        FinancialInstrumentAssetClass.SovereignDebtAaa => 0.10m,           // 0.1 bp per day
        FinancialInstrumentAssetClass.CorporateBondInvestmentGrade => 0.50m,// 0.5 bp per day
        _ => 1.00m
    };

    public int GetMandatoryBuyInThresholdDays(FinancialInstrumentAssetClass assetClass) => assetClass switch
    {
        FinancialInstrumentAssetClass.LiquidEquity => 4,              // 4 business days
        FinancialInstrumentAssetClass.IlliquidEquityOrSme => 7,       // 7 business days
        FinancialInstrumentAssetClass.SovereignDebtAaa => 7,
        FinancialInstrumentAssetClass.CorporateBondInvestmentGrade => 7,
        _ => 4
    };

    public DailyFailPenaltyAssessment ComputeDailyPenalty(SettlementFailRecord fail)
    {
        decimal rateBps = GetStatutoryDailyPenaltyBps(fail.AssetClass);
        decimal rateFraction = rateBps / 10000m;

        decimal dailyPenalty = Math.Round(fail.TradeMarketValue.Amount * rateFraction, 2);
        decimal cumulative = dailyPenalty * fail.DaysFailed;

        int buyInDays = GetMandatoryBuyInThresholdDays(fail.AssetClass);
        bool buyInTriggered = fail.DaysFailed >= buyInDays;

        var currency = fail.TradeMarketValue.Currency;

        return new DailyFailPenaltyAssessment
        {
            FailId = fail.FailId,
            FailingMemberId = fail.FailingMemberId,
            ReceivingMemberId = fail.ReceivingMemberId,
            DailyPenaltyRateBps = rateBps,
            DailyPenaltyAmount = CashAmount.FromDecimal(dailyPenalty, currency),
            CumulativePenaltyAmount = CashAmount.FromDecimal(cumulative, currency),
            BuyInWindowTriggered = buyInTriggered
        };
    }

    public MandatoryBuyInResult ExecuteMandatoryBuyIn(
        SettlementFailRecord fail,
        bool marketLiquidityAvailable,
        CashAmount? actualBuyInExecutionPrice = null,
        CashAmount? referenceMarketPriceForCashComp = null)
    {
        var currency = fail.TradeMarketValue.Currency;

        if (marketLiquidityAvailable && actualBuyInExecutionPrice.HasValue)
        {
            var buyInValue = actualBuyInExecutionPrice.Value;
            // If buy-in price was higher than original contract price, failing seller pays difference
            decimal diff = Math.Max(0m, buyInValue.Amount - fail.TradeMarketValue.Amount);

            return new MandatoryBuyInResult
            {
                FailId = fail.FailId,
                BuyInSuccessful = true,
                OriginalSettlementValue = fail.TradeMarketValue,
                ExecutionOrCashCompensationValue = buyInValue,
                PriceDifferenceCompensationToReceiver = CashAmount.FromDecimal(diff, currency),
                ResolutionType = "PHYSICAL_BUY_IN"
            };
        }
        else
        {
            // Cash Compensation: reference price + 10% penalty fee
            var refPrice = referenceMarketPriceForCashComp ?? fail.TradeMarketValue;
            decimal compValue = Math.Round(refPrice.Amount * 1.10m, 2);
            decimal compDiff = Math.Max(0m, compValue - fail.TradeMarketValue.Amount);

            return new MandatoryBuyInResult
            {
                FailId = fail.FailId,
                BuyInSuccessful = false,
                OriginalSettlementValue = fail.TradeMarketValue,
                ExecutionOrCashCompensationValue = CashAmount.FromDecimal(compValue, currency),
                PriceDifferenceCompensationToReceiver = CashAmount.FromDecimal(compDiff, currency),
                ResolutionType = "CASH_COMPENSATION"
            };
        }
    }
}
