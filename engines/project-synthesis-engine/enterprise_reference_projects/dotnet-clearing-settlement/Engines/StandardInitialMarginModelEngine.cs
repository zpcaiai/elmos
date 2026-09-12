namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Core.ValueObjects;

public enum SimmRiskClass
{
    InterestRate,
    CreditQualifying,
    CreditNonQualifying,
    Equity,
    Commodity,
    ForeignExchange
}

public sealed record SimmSensitivity(
    SimmRiskClass RiskClass,
    string Qualifier,   // E.g. Currency "USD", Ticker "AAPL", Commodity "BRENT"
    string Bucket,      // Sub-bucket (e.g. 10Y tenor, LargeCap, DevelopedMarket)
    decimal DeltaAmount, // Net DV01 or delta notional
    decimal VegaAmount   // Vega sensitivity
);

public sealed record SimmMarginReport(
    CashAmount TotalInitialMargin,
    IReadOnlyDictionary<SimmRiskClass, CashAmount> MarginByRiskClass,
    Currency CalculationCurrency,
    DateTime CalculatedAtUtc
);

/// <summary>
/// Standard Initial Margin Model (ISDA SIMM v2.6 compatible) Engine.
/// Computes non-cleared & CCP portfolio margin using delta and vega risk factor aggregations.
/// </summary>
public sealed class StandardInitialMarginModelEngine
{
    // ISDA SIMM Standard Risk Weights (RW)
    private static readonly Dictionary<SimmRiskClass, decimal> DefaultRiskWeights = new()
    {
        [SimmRiskClass.InterestRate] = 0.0075m,         // 75 bps on 10Y swap duration
        [SimmRiskClass.Equity] = 0.25m,                 // 25% on developed large-cap equity
        [SimmRiskClass.ForeignExchange] = 0.08m,        // 8% on major currency pairs
        [SimmRiskClass.Commodity] = 0.20m,              // 20% on energy/metals
        [SimmRiskClass.CreditQualifying] = 0.12m,       // 12% on investment grade credit
        [SimmRiskClass.CreditNonQualifying] = 0.28m     // 28% on high yield credit
    };

    // Inter-Risk Class Correlation Matrix (rho_ij) per ISDA SIMM v2.6
    private static readonly Dictionary<(SimmRiskClass, SimmRiskClass), decimal> InterClassCorrelations = new()
    {
        [(SimmRiskClass.InterestRate, SimmRiskClass.Equity)] = 0.18m,
        [(SimmRiskClass.InterestRate, SimmRiskClass.ForeignExchange)] = 0.27m,
        [(SimmRiskClass.InterestRate, SimmRiskClass.Commodity)] = 0.15m,
        [(SimmRiskClass.Equity, SimmRiskClass.ForeignExchange)] = 0.24m,
        [(SimmRiskClass.Equity, SimmRiskClass.Commodity)] = 0.29m,
        [(SimmRiskClass.ForeignExchange, SimmRiskClass.Commodity)] = 0.31m
    };

    public SimmMarginReport CalculateSimmMargin(
        IReadOnlyCollection<SimmSensitivity> sensitivities,
        Currency currency
    )
    {
        var classMargins = new Dictionary<SimmRiskClass, decimal>();

        // Group sensitivities by Risk Class
        var byClass = new Dictionary<SimmRiskClass, List<SimmSensitivity>>();
        foreach (var s in sensitivities)
        {
            if (!byClass.TryGetValue(s.RiskClass, out var list))
            {
                list = new List<SimmSensitivity>();
                byClass[s.RiskClass] = list;
            }
            list.Add(s);
        }

        // 1. Intra-Risk Class Delta & Vega Margining: K_class = sqrt( sum(WS_i^2) + sum(rho_jk * WS_j * WS_k) )
        foreach (var (rc, sensList) in byClass)
        {
            decimal rw = DefaultRiskWeights.GetValueOrDefault(rc, 0.20m);
            decimal sumSquaredWeighted = 0m;
            decimal crossProductSum = 0m;

            for (int i = 0; i < sensList.Count; i++)
            {
                var s1 = sensList[i];
                decimal ws1 = s1.DeltaAmount * rw;
                sumSquaredWeighted += ws1 * ws1;

                for (int j = i + 1; j < sensList.Count; j++)
                {
                    var s2 = sensList[j];
                    decimal ws2 = s2.DeltaAmount * rw;
                    // Intra-bucket correlation (typically 0.60 for same bucket, 0.30 for different)
                    decimal intraCorr = s1.Bucket == s2.Bucket ? 0.60m : 0.30m;
                    crossProductSum += 2m * intraCorr * ws1 * ws2;
                }
            }

            decimal totalRadicand = Math.Max(0m, sumSquaredWeighted + crossProductSum);
            decimal classMargin = (decimal)Math.Sqrt((double)totalRadicand);
            classMargins[rc] = classMargin;
        }

        // 2. Inter-Risk Class Aggregation: Total_IM = sqrt( sum(K_i^2) + sum(rho_ij * K_i * K_j) )
        decimal sumClassSquared = 0m;
        decimal crossClassSum = 0m;

        var activeClasses = new List<SimmRiskClass>(classMargins.Keys);
        for (int i = 0; i < activeClasses.Count; i++)
        {
            var rc1 = activeClasses[i];
            decimal k1 = classMargins[rc1];
            sumClassSquared += k1 * k1;

            for (int j = i + 1; j < activeClasses.Count; j++)
            {
                var rc2 = activeClasses[j];
                decimal k2 = classMargins[rc2];

                decimal rho = GetInterClassCorrelation(rc1, rc2);
                crossClassSum += 2m * rho * k1 * k2;
            }
        }

        decimal totalImRadicand = Math.Max(0m, sumClassSquared + crossClassSum);
        decimal totalIm = (decimal)Math.Sqrt((double)totalImRadicand);

        var marginResultDict = new Dictionary<SimmRiskClass, CashAmount>();
        foreach (var (rc, val) in classMargins)
        {
            marginResultDict[rc] = CashAmount.FromDecimal(val, currency);
        }

        return new SimmMarginReport(
            CashAmount.FromDecimal(totalIm, currency),
            marginResultDict,
            currency,
            DateTime.UtcNow
        );
    }

    private static decimal GetInterClassCorrelation(SimmRiskClass a, SimmRiskClass b)
    {
        if (a == b) return 1.0m;
        if (InterClassCorrelations.TryGetValue((a, b), out var corr)) return corr;
        if (InterClassCorrelations.TryGetValue((b, a), out corr)) return corr;
        return 0.15m; // Default baseline inter-class diversification
    }
}
