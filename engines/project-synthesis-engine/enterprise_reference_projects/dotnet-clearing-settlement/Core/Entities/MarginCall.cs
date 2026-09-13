namespace Elmos.ClearingSettlement.Core.Entities;

using System;
using Elmos.ClearingSettlement.Core.ValueObjects;

public enum MarginCallStatus
{
    Pending,
    Satisfied,
    DefaultDeclared
}

/// <summary>
/// A formal margin call issued to a clearing member requiring top-up collateral within strict SLA.
/// </summary>
public sealed class MarginCall
{
    public string CallId { get; }
    public string MemberId { get; }
    public CashAmount RequiredDeficitTopUp { get; }
    public DateTime IssuedAt { get; }
    public DateTime Deadline { get; }
    public MarginCallStatus Status { get; private set; }
    public DateTime? SatisfiedAt { get; private set; }

    public MarginCall(
        string callId,
        string memberId,
        CashAmount requiredDeficitTopUp,
        TimeSpan responseWindow)
    {
        CallId = callId ?? throw new ArgumentNullException(nameof(callId));
        MemberId = memberId ?? throw new ArgumentNullException(nameof(memberId));
        RequiredDeficitTopUp = requiredDeficitTopUp;
        IssuedAt = DateTime.UtcNow;
        Deadline = IssuedAt.Add(responseWindow);
        Status = MarginCallStatus.Pending;
    }

    public void MarkSatisfied()
    {
        Status = MarginCallStatus.Satisfied;
        SatisfiedAt = DateTime.UtcNow;
    }

    public void DeclareBreach()
    {
        Status = MarginCallStatus.DefaultDeclared;
    }

    public bool IsOverdue(DateTime now) => Status == MarginCallStatus.Pending && now > Deadline;
}
