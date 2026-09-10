namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Dual-Curve Interest Rate Swap (IRS) Valuation &amp; Risk Sensitivity Engine.
/// Implements OIS discounting (SOFR/€STR), forward rate projection,
/// day-count fraction conventions (Actual/360, 30/360), Annuity, Par Swap Rate, and DV01 delta sensitivities.
/// </summary>
public sealed class InterestRateSwapPricer
{
    public enum DayCountConvention
    {
        Actual360,
        Actual365Fixed,
        Thirty360BondBasis
    }

    public enum SwapLegType
    {
        FixedPayer,   // Pay Fixed, Receive Floating
        FloatingPayer // Pay Floating, Receive Fixed
    }

    public sealed record SwapValuationRequest(
        string SwapId,
        CashAmount Notional,
        SwapLegType LegType,
        decimal FixedRatePercent, // e.g. 3.75%
        DateTime StartDate,
        DateTime MaturityDate,
        int PaymentFrequencyMonths, // e.g., 6 for semi-annual
        DayCountConvention FixedDayCount,
        DayCountConvention FloatingDayCount);

    public sealed record SwapCashFlowPeriod(
        int PeriodIndex,
        DateTime StartDate,
        DateTime EndDate,
        decimal YearFraction,
        decimal DiscountFactor,
        decimal ForwardRatePercent,
        decimal FixedCashFlow,
        decimal FloatingCashFlow,
        decimal NetPresentValue);

    public sealed record SwapValuationResult(
        string SwapId,
        CashAmount Notional,
        SwapLegType LegType,
        decimal FixedLegNpv,
        decimal FloatingLegNpv,
        CashAmount NetSwapNpv,
        decimal Annuity,
        decimal ParSwapRatePercent,
        decimal Dv01Amount, // Dollar value of a 1 basis point parallel shift
        IReadOnlyList<SwapCashFlowPeriod> CashFlowSchedule);

    /// <summary>
    /// Computes day count fraction between two dates according to standard financial conventions.
    /// </summary>
    public decimal CalculateYearFraction(DateTime start, DateTime end, DayCountConvention convention)
    {
        if (end <= start) return 0m;

        return convention switch
        {
            DayCountConvention.Actual360 => (decimal)(end - start).TotalDays / 360m,
            DayCountConvention.Actual365Fixed => (decimal)(end - start).TotalDays / 365m,
            DayCountConvention.Thirty360BondBasis => Calculate30360Fraction(start, end),
            _ => (decimal)(end - start).TotalDays / 360m
        };
    }

    private static decimal Calculate30360Fraction(DateTime start, DateTime end)
    {
        int d1 = Math.Min(30, start.Day);
        int d2 = (d1 == 30 && end.Day == 31) ? 30 : end.Day;
        int days = 360 * (end.Year - start.Year) + 30 * (end.Month - start.Month) + (d2 - d1);
        return (decimal)days / 360m;
    }

    /// <summary>
    /// Prices the interest rate swap using dual curves for forward projection and discounting.
    /// </summary>
    public SwapValuationResult PriceSwap(
        SwapValuationRequest request,
        Func<DateTime, decimal> oisDiscountFactorCurve,
        Func<DateTime, DateTime, decimal> forwardRateCurve)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(oisDiscountFactorCurve);
        ArgumentNullException.ThrowIfNull(forwardRateCurve);

        var currency = request.Notional.Currency;
        decimal notionalDec = request.Notional.ToDecimal();
        decimal fixedRateDecimal = request.FixedRatePercent / 100m;

        var periods = new List<SwapCashFlowPeriod>();
        DateTime currentStart = request.StartDate;
        int periodIndex = 1;

        decimal totalFixedNpv = 0m;
        decimal totalFloatingNpv = 0m;
        decimal totalAnnuity = 0m;

        while (currentStart < request.MaturityDate)
        {
            DateTime currentEnd = currentStart.AddMonths(request.PaymentFrequencyMonths);
            if (currentEnd > request.MaturityDate)
            {
                currentEnd = request.MaturityDate;
            }

            decimal fixedFraction = CalculateYearFraction(currentStart, currentEnd, request.FixedDayCount);
            decimal floatingFraction = CalculateYearFraction(currentStart, currentEnd, request.FloatingDayCount);

            decimal df = oisDiscountFactorCurve(currentEnd);
            decimal forwardRatePercent = forwardRateCurve(currentStart, currentEnd);
            decimal forwardRateDecimal = forwardRatePercent / 100m;

            decimal fixedCashFlow = notionalDec * fixedRateDecimal * fixedFraction;
            decimal floatingCashFlow = notionalDec * forwardRateDecimal * floatingFraction;

            decimal fixedPv = fixedCashFlow * df;
            decimal floatingPv = floatingCashFlow * df;

            totalFixedNpv += fixedPv;
            totalFloatingNpv += floatingPv;
            totalAnnuity += fixedFraction * df;

            decimal periodNetPv = request.LegType == SwapLegType.FixedPayer
                ? floatingPv - fixedPv
                : fixedPv - floatingPv;

            periods.Add(new SwapCashFlowPeriod(
                periodIndex++,
                currentStart,
                currentEnd,
                fixedFraction,
                Math.Round(df, 6),
                Math.Round(forwardRatePercent, 4),
                Math.Round(fixedCashFlow, 2),
                Math.Round(floatingCashFlow, 2),
                Math.Round(periodNetPv, 2)));

            currentStart = currentEnd;
        }

        decimal netNpvDec = request.LegType == SwapLegType.FixedPayer
            ? totalFloatingNpv - totalFixedNpv
            : totalFixedNpv - totalFloatingNpv;

        var netSwapNpv = CashAmount.FromDecimal(netNpvDec, currency);

        // Par Swap Rate = FloatingPV / (Notional * Annuity)
        decimal parSwapRate = totalAnnuity > 0m
            ? (totalFloatingNpv / (notionalDec * totalAnnuity)) * 100m
            : 0m;

        // DV01 = Dollar value of 1 basis point shift = Notional * Annuity * 0.0001
        decimal dv01 = notionalDec * totalAnnuity * 0.0001m;

        return new SwapValuationResult(
            request.SwapId,
            request.Notional,
            request.LegType,
            Math.Round(totalFixedNpv, 2),
            Math.Round(totalFloatingNpv, 2),
            netSwapNpv,
            Math.Round(totalAnnuity, 6),
            Math.Round(parSwapRate, 4),
            Math.Round(dv01, 2),
            periods);
    }
}
