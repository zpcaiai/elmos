namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.ValueObjects;

public enum SettlementFailReason
{
    LackOfSecurities,   // LACK
    LackOfCash,         // CASH
    InstructionMismatch,// MISM
    AccountBlocked,     // BLOK
    SettlementCutoff    // CLAT
}

public sealed record SettlementPenaltyRecord(
    string PenaltyId,
    string BatchId,
    string FailingMemberId,
    string ReceivingMemberId,
    SecurityId SecurityId,
    CashAmount PenaltyAmount,
    SettlementFailReason Reason,
    int DaysFailed,
    DateTime CalculationDateUtc
);

public sealed record BuyInNotice(
    string NoticeId,
    string FailingMemberId,
    SecurityId SecurityId,
    Quantity OutstandingQuantity,
    DateTime BuyInExecutionDeadlineUtc,
    CashAmount MaximumTolerablePrice
);

/// <summary>
/// CSDR Article 7 Cash Penalty and Buy-in Engine for failed clearing and settlement instructions.
/// </summary>
public sealed class SettlementFailPenaltyEngine
{
    private readonly decimal _ecbReferenceRateBps; // E.g., 375 bps (3.75%)
    private readonly decimal _liquidSharesPenaltyRateBps; // 1.0 bps per day
    private readonly decimal _governmentBondsPenaltyRateBps; // 0.5 bps per day

    public SettlementFailPenaltyEngine(
        decimal ecbReferenceRateBps = 375m,
        decimal liquidSharesPenaltyRateBps = 1.0m,
        decimal governmentBondsPenaltyRateBps = 0.5m
    )
    {
        _ecbReferenceRateBps = ecbReferenceRateBps;
        _liquidSharesPenaltyRateBps = liquidSharesPenaltyRateBps;
        _governmentBondsPenaltyRateBps = governmentBondsPenaltyRateBps;
    }

    /// <summary>
    /// Computes CSDR daily cash penalty assessed against failing member to compensate non-defaulting receiving member.
    /// </summary>
    public SettlementPenaltyRecord CalculateDailyPenalty(
        string batchId,
        ClearingObligation failedObligation,
        string failingMemberId,
        string receivingMemberId,
        CashAmount referencePrice,
        SettlementFailReason reason,
        int daysOverdue
    )
    {
        // Daily rate = Base Penalty Bps / 10,000 / 360
        decimal dailyBps = _liquidSharesPenaltyRateBps;
        if (reason == SettlementFailReason.LackOfCash)
        {
            // For cash fail, ECB interest rate is applied
            dailyBps = _ecbReferenceRateBps / 360m;
        }

        decimal notional = referencePrice.ToDecimal() * Math.Abs(failedObligation.NetQuantity.Units);
        decimal penaltyDecimal = notional * (dailyBps / 10000m);
        // Minimum penalty floor of $25.00
        decimal finalPenalty = Math.Max(25.00m, Math.Round(penaltyDecimal, 2));

        return new SettlementPenaltyRecord(
            PenaltyId: $"PEN-{batchId}-{failingMemberId}-{DateTime.UtcNow:yyyyMMdd}",
            BatchId: batchId,
            FailingMemberId: failingMemberId,
            ReceivingMemberId: receivingMemberId,
            SecurityId: failedObligation.SecurityId,
            PenaltyAmount: CashAmount.FromDecimal(finalPenalty, referencePrice.Currency),
            Reason: reason,
            DaysFailed: daysOverdue,
            CalculationDateUtc: DateTime.UtcNow
        );
    }

    /// <summary>
    /// Issues mandatory buy-in notice when settlement fails beyond grace period (4 business days for liquid shares).
    /// </summary>
    public BuyInNotice IssueMandatoryBuyInNotice(
        ClearingObligation failedObligation,
        string failingMemberId,
        CashAmount currentMarketPrice,
        int gracePeriodDays = 4
    )
    {
        // Maximum buy-in price is capped at current price + 10% premium
        var maxPrice = CashAmount.FromDecimal(currentMarketPrice.ToDecimal() * 1.10m, currentMarketPrice.Currency);

        return new BuyInNotice(
            NoticeId: $"BUYIN-{failedObligation.SecurityId}-{failingMemberId}-{Guid.NewGuid():N}",
            FailingMemberId: failingMemberId,
            SecurityId: failedObligation.SecurityId,
            OutstandingQuantity: Quantity.Of(Math.Abs(failedObligation.NetQuantity.Units)),
            BuyInExecutionDeadlineUtc: DateTime.UtcNow.AddDays(gracePeriodDays),
            MaximumTolerablePrice: maxPrice
        );
    }
}
