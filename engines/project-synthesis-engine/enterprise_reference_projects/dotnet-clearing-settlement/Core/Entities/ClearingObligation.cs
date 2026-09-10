namespace Elmos.ClearingSettlement.Core.Entities;

using System;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// A novated legal obligation between a clearing member and the CCP.
/// Resulting from bilateral novation or multilateral netting matrix reduction.
/// </summary>
public sealed class ClearingObligation
{
    public string ObligationId { get; }
    public string BatchId { get; }
    public string MemberId { get; }
    public SecurityId SecurityId { get; }
    
    // Net positions:
    // NetQuantity > 0: Member receives securities from CCP (buyer)
    // NetQuantity < 0: Member delivers securities to CCP (seller)
    public Quantity NetQuantity { get; }

    // NetCashAmount > 0: Member receives cash from CCP
    // NetCashAmount < 0: Member pays cash to CCP
    public CashAmount NetCashAmount { get; }

    public Quantity GrossQuantity { get; }
    public CashAmount GrossCashAmount { get; }

    public SettlementStatus Status { get; private set; }
    public DateTime CreatedAt { get; }
    public DateTime? SettledAt { get; private set; }

    public ClearingObligation(
        string obligationId,
        string batchId,
        string memberId,
        SecurityId securityId,
        Quantity netQuantity,
        CashAmount netCashAmount,
        Quantity grossQuantity,
        CashAmount grossCashAmount)
    {
        ObligationId = obligationId ?? throw new ArgumentNullException(nameof(obligationId));
        BatchId = batchId ?? throw new ArgumentNullException(nameof(batchId));
        MemberId = memberId ?? throw new ArgumentNullException(nameof(memberId));
        SecurityId = securityId;
        NetQuantity = netQuantity;
        NetCashAmount = netCashAmount;
        GrossQuantity = grossQuantity;
        GrossCashAmount = grossCashAmount;
        Status = SettlementStatus.Novated;
        CreatedAt = DateTime.UtcNow;
    }

    public void MarkSettled()
    {
        Status = SettlementStatus.Settled;
        SettledAt = DateTime.UtcNow;
    }

    public void MarkFailed(string reason)
    {
        Status = SettlementStatus.Failed;
    }

    public override string ToString() => $"Obligation {ObligationId}: Member={MemberId}, NetSec={NetQuantity} {SecurityId}, NetCash={NetCashAmount} [{Status}]";
}
