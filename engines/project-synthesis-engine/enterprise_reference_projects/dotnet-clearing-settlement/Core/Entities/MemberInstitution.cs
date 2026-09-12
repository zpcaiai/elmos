namespace Elmos.ClearingSettlement.Core.Entities;

using System;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// A financial institution admitted as a clearing participant of the Central Counterparty (CCP).
/// </summary>
public sealed class MemberInstitution
{
    public string MemberId { get; }
    public string LegalEntityIdentifier { get; } // 20-character ISO 17442 LEI
    public string Name { get; }
    public MemberRole Role { get; }
    public CashAmount DefaultFundContribution { get; private set; }
    public bool IsActive { get; private set; }
    public bool IsInDefault { get; private set; }
    public DateTime AdmittedAt { get; }
    public DateTime? DefaultDeclaredAt { get; private set; }

    public MemberInstitution(
        string memberId,
        string legalEntityIdentifier,
        string name,
        MemberRole role,
        CashAmount defaultFundContribution)
    {
        MemberId = memberId ?? throw new ArgumentNullException(nameof(memberId));
        LegalEntityIdentifier = legalEntityIdentifier ?? throw new ArgumentNullException(nameof(legalEntityIdentifier));
        Name = name ?? throw new ArgumentNullException(nameof(name));
        Role = role;
        DefaultFundContribution = defaultFundContribution;
        IsActive = true;
        IsInDefault = false;
        AdmittedAt = DateTime.UtcNow;
    }

    public void UpdateDefaultFundContribution(CashAmount newContribution)
    {
        DefaultFundContribution = newContribution;
    }

    public void DeclareDefault(string reason)
    {
        if (IsInDefault) return;
        IsInDefault = true;
        IsActive = false;
        DefaultDeclaredAt = DateTime.UtcNow;
    }

    public void Suspend()
    {
        IsActive = false;
    }

    public void Reactivate()
    {
        if (IsInDefault)
            throw new InvalidOperationException("Cannot reactivate an institution currently in default");
        IsActive = true;
    }

    public override string ToString() => $"{Name} ({MemberId}) [{Role}] Active={IsActive}";
}
