namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Multi-Currency Portfolio Margining &amp; Cross-Currency Basis Risk Engine.
/// Computes multi-asset clearing margin with currency basis risk add-ons,
/// Cholesky correlation matrix portfolio diversification, and Margin Period of Risk (MPOR) scaling.
/// </summary>
public sealed class CrossCurrencyMarginHaircutEngine
{
    public sealed record CurrencyPosition(
        Currency PositionCurrency,
        decimal ExposureAmountBase, // Expressed in Base Reporting Currency (e.g. USD)
        decimal AnnualizedVolatilityPercent,
        bool IsEmergingMarketCurrency);

    public sealed record CrossCurrencyMarginResult(
        Currency BaseCurrency,
        decimal GrossStandaloneMargin,
        decimal CorrelationDiversifiedMargin,
        decimal CurrencyBasisAddOn,
        decimal LiquidityMporScalingAddOn,
        decimal NetTotalMarginRequired,
        decimal DiversificationBenefitPercent);

    /// <summary>
    /// Computes multi-currency portfolio margin using correlation matrix variance-covariance model.
    /// </summary>
    public CrossCurrencyMarginResult CalculatePortfolioMargin(
        Currency baseCurrency,
        IReadOnlyList<CurrencyPosition> positions,
        double[,] correlationMatrix,
        decimal crossCurrencyBasisSpreadBps = 15.0m, // 15 bps standard basis spread
        decimal confidenceIntervalZ = 2.326m) // 99% one-tailed normal quantile
    {
        if (positions is null) throw new ArgumentNullException(nameof(positions));
        if (correlationMatrix is null) throw new ArgumentNullException(nameof(correlationMatrix));

        int n = positions.Count;
        if (n == 0)
        {
            return new CrossCurrencyMarginResult(baseCurrency, 0m, 0m, 0m, 0m, 0m, 0m);
        }

        if (correlationMatrix.GetLength(0) != n || correlationMatrix.GetLength(1) != n)
        {
            throw new ArgumentException("Correlation matrix dimensions must match positions count", nameof(correlationMatrix));
        }

        // Standalone VaR sum (no diversification)
        decimal grossStandaloneSum = 0m;
        decimal[] standaloneVars = new decimal[n];
        decimal mporAddOnTotal = 0m;

        for (int i = 0; i < n; i++)
        {
            var pos = positions[i];
            // Daily volatility = Annualized / sqrt(252)
            decimal dailyVol = pos.AnnualizedVolatilityPercent / (decimal)Math.Sqrt(252);
            decimal oneDayVar = Math.Abs(pos.ExposureAmountBase) * (dailyVol / 100m) * confidenceIntervalZ;

            // MPOR scaling: G10 = 5 days (sqrt(5)), Emerging = 10 days (sqrt(10))
            decimal mporMultiplier = pos.IsEmergingMarketCurrency
                ? (decimal)Math.Sqrt(10.0)
                : (decimal)Math.Sqrt(5.0);

            decimal scaledVar = oneDayVar * mporMultiplier;
            standaloneVars[i] = scaledVar;
            grossStandaloneSum += scaledVar;

            if (pos.IsEmergingMarketCurrency)
            {
                mporAddOnTotal += scaledVar * 0.15m; // 15% extra liquidity horizon add-on
            }
        }

        // Portfolio Variance = V^T * Corr * V
        double portfolioVariance = 0.0;
        for (int i = 0; i < n; i++)
        {
            for (int j = 0; j < n; j++)
            {
                double vi = (double)standaloneVars[i];
                double vj = (double)standaloneVars[j];
                double rho = correlationMatrix[i, j];
                portfolioVariance += vi * vj * rho;
            }
        }

        decimal diversifiedMargin = (decimal)Math.Sqrt(Math.Max(0.0, portfolioVariance));

        // Cross-currency basis swap risk add-on
        decimal grossNotional = positions.Sum(p => Math.Abs(p.ExposureAmountBase));
        decimal basisAddOn = grossNotional * (crossCurrencyBasisSpreadBps / 10000m);

        decimal netRequired = diversifiedMargin + basisAddOn + mporAddOnTotal;

        decimal diversificationBenefit = grossStandaloneSum > 0m
            ? Math.Max(0m, (grossStandaloneSum - diversifiedMargin) / grossStandaloneSum * 100m)
            : 0m;

        return new CrossCurrencyMarginResult(
            baseCurrency,
            Math.Round(grossStandaloneSum, 2),
            Math.Round(diversifiedMargin, 2),
            Math.Round(basisAddOn, 2),
            Math.Round(mporAddOnTotal, 2),
            Math.Round(netRequired, 2),
            Math.Round(diversificationBenefit, 2));
    }

    /// <summary>
    /// Performs Cholesky decomposition L * L^T = A for a symmetric positive-definite correlation matrix.
    /// Used for Monte Carlo correlated FX scenario generation.
    /// </summary>
    public double[,] ComputeCholeskyLowerTriangular(double[,] matrix)
    {
        int n = matrix.GetLength(0);
        double[,] l = new double[n, n];

        for (int i = 0; i < n; i++)
        {
            for (int j = 0; j <= i; j++)
            {
                double sum = 0.0;
                for (int k = 0; k < j; k++)
                {
                    sum += l[i, k] * l[j, k];
                }

                if (i == j)
                {
                    double diff = matrix[i, i] - sum;
                    if (diff <= 0.0)
                    {
                        // Regularization for near-singular matrices
                        diff = 1e-6;
                    }
                    l[i, j] = Math.Sqrt(diff);
                }
                else
                {
                    l[i, j] = (matrix[i, j] - sum) / l[j, j];
                }
            }
        }

        return l;
    }
}
