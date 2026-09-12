namespace Elmos.ClearingSettlement.Core.Entities;

using System;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// A bilateral executed trade submitted to the CCP for clearing, novation, and settlement.
/// </summary>
public sealed class TradeContract
{
    public string TradeId { get; }
    public string BuyerMemberId { get; }
    public string SellerMemberId { get; }
    public SecurityId SecurityId { get; }
    public CashAmount PricePerUnit { get; }
    public Quantity Quantity { get; }
    public CashAmount GrossSettlementAmount { get; }
    public DateTime ExecutedAt { get; }
    public DateTime SettlementDate { get; }
    public SettlementStatus Status { get; private set; }
    public string? BatchId { get; private set; }

    public TradeContract(
        string tradeId,
        string buyerMemberId,
        string sellerMemberId,
        SecurityId securityId,
        CashAmount pricePerUnit,
        Quantity quantity,
        DateTime executedAt,
        DateTime settlementDate)
    {
        if (buyerMemberId == sellerMemberId)
            throw new ArgumentException("Buyer and seller cannot be the same clearing member institution", nameof(buyerMemberId));

        if (!quantity.IsPositive)
            throw new ArgumentException("Trade quantity must be strictly positive", nameof(quantity));

        TradeId = tradeId ?? throw new ArgumentNullException(nameof(tradeId));
        BuyerMemberId = buyerMemberId ?? throw new ArgumentNullException(nameof(buyerMemberId));
        SellerMemberId = sellerMemberId ?? throw new ArgumentNullException(nameof(sellerMemberId));
        SecurityId = securityId;
        PricePerUnit = pricePerUnit;
        Quantity = quantity;
        ExecutedAt = executedAt;
        SettlementDate = settlementDate;
        Status = SettlementStatus.Matched;

        GrossSettlementAmount = pricePerUnit * quantity.Units;
    }

    public void AssignToBatch(string batchId)
    {
        BatchId = batchId ?? throw new ArgumentNullException(nameof(batchId));
    }

    public void MarkNovated()
    {
        if (Status != SettlementStatus.Matched)
            throw new InvalidOperationException($"Cannot novate trade in status: {Status}");
        Status = SettlementStatus.Novated;
    }

    public void MarkSettled()
    {
        if (Status != SettlementStatus.Novated)
            throw new InvalidOperationException($"Cannot settle trade before novation: {Status}");
        Status = SettlementStatus.Settled;
    }

    public void MarkFailed(string reason)
    {
        Status = SettlementStatus.Failed;
    }

    public override string ToString() => $"Trade {TradeId}: {BuyerMemberId} buys {Quantity} {SecurityId} from {SellerMemberId} @ {PricePerUnit} [{Status}]";
}
