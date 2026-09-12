namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Text;
using System.Text.RegularExpressions;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.ValueObjects;

public enum RegulatoryReportingRegime
{
    EMIR_Refit,      // European Market Infrastructure Regulation (ESMA)
    CFTC_Part43_45,  // Dodd-Frank Real-Time & Regulatory Reporting (CFTC)
    SEC_SBSDR,       // Security-Based Swap Data Repository (SEC)
    MAS_SFTR         // Monetary Authority of Singapore Reporting
}

public enum LifecycleActionType
{
    New,
    Novation,
    Modification,
    Termination,
    ValuationUpdate,
    CollateralUpdate
}

public sealed record RegulatoryTradeRecord(
    string UniqueTradeIdentifier,    // ISO 23897 UTI
    string ReportingCounterpartyLei, // ISO 17442 LEI (20 chars)
    string OtherCounterpartyLei,     // ISO 17442 LEI (20 chars)
    string CcpLei,                   // Clearing House LEI
    SecurityId InstrumentId,
    decimal NotionalAmount,
    Currency Currency,
    decimal Price,
    Quantity Quantity,
    LifecycleActionType ActionType,
    DateTime ExecutionTimestampUtc,
    DateTime ReportingTimestampUtc,
    RegulatoryReportingRegime Regime
);

/// <summary>
/// Regulatory Reporting Engine for Central Clearing Counterparties.
/// Handles UTI generation, LEI checksum verification, and EMIR / Dodd-Frank message formatting.
/// </summary>
public sealed class RegulatoryReportingEngine
{
    private readonly string _ccpLei;
    private static readonly Regex LeiFormatRegex = new("^[A-Z0-9]{18}[0-9]{2}$", RegexOptions.Compiled);

    public RegulatoryReportingEngine(string ccpLei)
    {
        if (!ValidateLeiChecksum(ccpLei))
            throw new ArgumentException($"Invalid CCP LEI checksum: {ccpLei}", nameof(ccpLei));

        _ccpLei = ccpLei;
    }

    /// <summary>
    /// Validates ISO 17442 Legal Entity Identifier (LEI) using Mod 97-10 checksum algorithm.
    /// </summary>
    public static bool ValidateLeiChecksum(string lei)
    {
        if (string.IsNullOrWhiteSpace(lei) || lei.Length != 20 || !LeiFormatRegex.IsMatch(lei))
            return false;

        // Convert letters A-Z to numbers 10-35
        var sb = new StringBuilder(40);
        foreach (char c in lei)
        {
            if (char.IsDigit(c))
            {
                sb.Append(c);
            }
            else if (char.IsAsciiLetterUpper(c))
            {
                sb.Append((int)c - (int)'A' + 10);
            }
            else
            {
                return false;
            }
        }

        // Compute mod 97 on large numeric string
        int remainder = 0;
        string numStr = sb.ToString();
        for (int i = 0; i < numStr.Length; i++)
        {
            remainder = (remainder * 10 + (numStr[i] - '0')) % 97;
        }

        return remainder == 1;
    }

    /// <summary>
    /// Generates an ISO 23897 Unique Trade Identifier (UTI) composed of CCP LEI prefix + unique transaction code.
    /// </summary>
    public string GenerateUti(string localTradeId, DateTime executionDate)
    {
        // Format: [20-char LEI][YYYYMMDD][Random/Sequence Alphanumeric up to 32 chars]
        string datePart = executionDate.ToString("yyyyMMdd");
        string cleanId = localTradeId.Replace("-", "").ToUpperInvariant();
        return $"{_ccpLei}E{datePart}{cleanId}";
    }

    /// <summary>
    /// Constructs an EMIR / Dodd-Frank compliant regulatory trade record for a cleared trade.
    /// </summary>
    public RegulatoryTradeRecord BuildTradeReport(
        TradeContract trade,
        MemberInstitution buyer,
        MemberInstitution seller,
        LifecycleActionType action,
        RegulatoryReportingRegime regime
    )
    {
        string uti = GenerateUti(trade.TradeId, trade.ExecutedAt);

        return new RegulatoryTradeRecord(
            UniqueTradeIdentifier: uti,
            ReportingCounterpartyLei: _ccpLei, // CCP reports as central party
            OtherCounterpartyLei: buyer.LegalEntityIdentifier,
            CcpLei: _ccpLei,
            InstrumentId: trade.SecurityId,
            NotionalAmount: trade.GrossSettlementAmount.ToDecimal(),
            Currency: trade.GrossSettlementAmount.Currency,
            Price: trade.PricePerUnit.ToDecimal(),
            Quantity: trade.Quantity,
            ActionType: action,
            ExecutionTimestampUtc: trade.ExecutedAt,
            ReportingTimestampUtc: DateTime.UtcNow,
            Regime: regime
        );
    }
}
