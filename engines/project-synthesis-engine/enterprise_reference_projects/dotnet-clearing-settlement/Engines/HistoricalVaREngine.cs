namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Historical Simulation Value-at-Risk (VaR) and Expected Shortfall (CVaR) Engine.
/// Implements Basel III / CPMI-IOSCO standards for CCP margin adequacy with decaying EWMA volatility weighting.
/// </summary>
public sealed class HistoricalVaREngine
{
    private readonly double _decayFactorLambda; // Typically 0.94 or 0.97 for EWMA
    private readonly int _lookbackDays;

    public HistoricalVaREngine(double decayFactorLambda = 0.94, int lookbackDays = 500)
    {
        if (decayFactorLambda <= 0.0 || decayFactorLambda >= 1.0)
            throw new ArgumentOutOfRangeException(nameof(decayFactorLambda), "Lambda must be between 0 and 1");
        if (lookbackDays < 100)
            throw new ArgumentOutOfRangeException(nameof(lookbackDays), "Lookback days must be at least 100");

        _decayFactorLambda = decayFactorLambda;
        _lookbackDays = lookbackDays;
    }

    public sealed record RiskMetricsResult(
        CashAmount UnweightedVaR99,
        CashAmount EwmaWeightedVaR99,
        CashAmount ExpectedShortfall975,
        CashAmount WorstScenarioPnl,
        int ScenariosEvaluated,
        DateTime CalculatedAtUtc
    );

    /// <summary>
    /// Computes historical simulation VaR at 99% and Expected Shortfall at 97.5% confidence
    /// for a member's net portfolio of cleared positions across historical return scenarios.
    /// </summary>
    public RiskMetricsResult CalculatePortfolioVaR(
        IReadOnlyCollection<ClearingObligation> netObligations,
        IReadOnlyDictionary<SecurityId, CashAmount> currentMarkPrices,
        IReadOnlyDictionary<SecurityId, IReadOnlyList<double>> historicalDailyReturns,
        Currency portfolioCurrency
    )
    {
        if (netObligations == null || netObligations.Count == 0)
        {
            return new RiskMetricsResult(
                CashAmount.Zero(portfolioCurrency),
                CashAmount.Zero(portfolioCurrency),
                CashAmount.Zero(portfolioCurrency),
                CashAmount.Zero(portfolioCurrency),
                0,
                DateTime.UtcNow
            );
        }

        // Determine scenario count from available returns
        int scenarioCount = int.MaxValue;
        foreach (var obl in netObligations)
        {
            if (historicalDailyReturns.TryGetValue(obl.SecurityId, out var returns))
            {
                scenarioCount = Math.Min(scenarioCount, returns.Count);
            }
        }

        if (scenarioCount == int.MaxValue || scenarioCount == 0)
            scenarioCount = _lookbackDays;

        scenarioCount = Math.Min(scenarioCount, _lookbackDays);

        // Calculate portfolio PnL for each historical scenario
        // Scenario PnL = Sum(NetPosition_i * CurrentPrice_i * Return_i,t)
        var scenarioPnLs = new List<(double PnL, double EwmaWeight)>(scenarioCount);
        double weightSum = 0.0;

        for (int t = 0; t < scenarioCount; t++)
        {
            double pnl = 0.0;
            foreach (var obl in netObligations)
            {
                if (!currentMarkPrices.TryGetValue(obl.SecurityId, out var markPrice))
                    continue;

                double nominalValue = (double)markPrice.ToDecimal() * obl.NetQuantity.Units;
                double ret = 0.0;
                if (historicalDailyReturns.TryGetValue(obl.SecurityId, out var returns) && t < returns.Count)
                {
                    ret = returns[t];
                }

                // If net long, positive return is gain. If net short, negative return is gain.
                pnl += nominalValue * ret;
            }

            // EWMA weight: w_t = (1 - lambda) * lambda^(t)
            double weight = (1.0 - _decayFactorLambda) * Math.Pow(_decayFactorLambda, t);
            weightSum += weight;
            scenarioPnLs.Add((pnl, weight));
        }

        // Normalize EWMA weights so they sum to 1.0
        for (int i = 0; i < scenarioPnLs.Count; i++)
        {
            var (pnl, w) = scenarioPnLs[i];
            scenarioPnLs[i] = (pnl, w / weightSum);
        }

        // Sort scenarios from worst loss (most negative PnL) to best gain
        var sortedByPnl = scenarioPnLs.OrderBy(s => s.PnL).ToList();

        // 1. Unweighted 99% VaR (1st percentile loss)
        int varIndex = (int)Math.Floor(sortedByPnl.Count * 0.01);
        double unweightedLoss = Math.Max(0.0, -sortedByPnl[varIndex].PnL);

        // 2. EWMA-Weighted 99% VaR (cumulative weight reaches 1%)
        double cumulativeWeight = 0.0;
        double weightedLoss = unweightedLoss;
        foreach (var (pnl, weight) in sortedByPnl)
        {
            cumulativeWeight += weight;
            if (cumulativeWeight >= 0.01)
            {
                weightedLoss = Math.Max(0.0, -pnl);
                break;
            }
        }

        // 3. Expected Shortfall (CVaR) at 97.5% confidence: Average loss in the worst 2.5% tail
        int esCutoffIndex = Math.Max(1, (int)Math.Floor(sortedByPnl.Count * 0.025));
        double esLossSum = 0.0;
        for (int i = 0; i < esCutoffIndex; i++)
        {
            esLossSum += Math.Max(0.0, -sortedByPnl[i].PnL);
        }
        double expectedShortfallLoss = esLossSum / esCutoffIndex;

        double worstLoss = Math.Max(0.0, -sortedByPnl[0].PnL);

        return new RiskMetricsResult(
            CashAmount.FromDecimal((decimal)unweightedLoss, portfolioCurrency),
            CashAmount.FromDecimal((decimal)weightedLoss, portfolioCurrency),
            CashAmount.FromDecimal((decimal)expectedShortfallLoss, portfolioCurrency),
            CashAmount.FromDecimal((decimal)worstLoss, portfolioCurrency),
            scenarioCount,
            DateTime.UtcNow
        );
    }
}
