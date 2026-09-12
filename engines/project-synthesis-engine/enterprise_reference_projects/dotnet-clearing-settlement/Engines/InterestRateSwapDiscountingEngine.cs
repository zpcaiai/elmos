namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.ValueObjects;

public enum SwapLegType
{
    PayFixedReceiveFloating,
    ReceiveFixedPayFloating
}

public enum DayCountBasis
{
    Actual360,
    Actual365,
    Thirty360
}

public sealed record CurvePillar(decimal TenorYears, decimal ZeroRate);

public sealed class ZeroRateYieldCurve
{
    public string CurveName { get; }
    private readonly List<CurvePillar> _pillars;

    public ZeroRateYieldCurve(string curveName, IEnumerable<CurvePillar> pillars)
    {
        CurveName = curveName ?? throw new ArgumentNullException(nameof(curveName));
        _pillars = pillars.OrderBy(p => p.TenorYears).ToList();
        if (_pillars.Count == 0)
            throw new ArgumentException("Curve must have at least one pillar point");
    }

    public decimal GetZeroRate(decimal tenorYears)
    {
        if (tenorYears <= _pillars[0].TenorYears)
            return _pillars[0].ZeroRate;
        if (tenorYears >= _pillars[^1].TenorYears)
            return _pillars[^1].ZeroRate;

        // Linear interpolation between adjacent tenors
        for (int i = 0; i < _pillars.Count - 1; i++)
        {
            if (tenorYears >= _pillars[i].TenorYears && tenorYears <= _pillars[i + 1].TenorYears)
            {
                decimal t0 = _pillars[i].TenorYears;
                decimal t1 = _pillars[i + 1].TenorYears;
                decimal r0 = _pillars[i].ZeroRate;
                decimal r1 = _pillars[i + 1].ZeroRate;

                decimal fraction = (tenorYears - t0) / (t1 - t0);
                return r0 + fraction * (r1 - r0);
            }
        }
        return _pillars[^1].ZeroRate;
    }

    /// <summary>
    /// Computes the zero-coupon discount factor P(0, T) = exp(-r(T) * T).
    /// </summary>
    public decimal GetDiscountFactor(decimal tenorYears)
    {
        if (tenorYears <= 0m)
            return 1.0m;

        decimal r = GetZeroRate(tenorYears);
        double exponent = -(double)(r * tenorYears);
        return (decimal)Math.Exp(exponent);
    }

    /// <summary>
    /// Computes the forward interest rate F(t0, t1) between two future time points:
    /// F(t0, t1) = (P(0, t0) / P(0, t1) - 1) / (t1 - t0).
    /// </summary>
    public decimal GetForwardRate(decimal t0, decimal t1)
    {
        if (t1 <= t0)
            throw new ArgumentException("Forward end tenor t1 must be strictly greater than start t0");

        decimal p0 = GetDiscountFactor(t0);
        decimal p1 = GetDiscountFactor(t1);
        decimal tau = t1 - t0;

        return (p0 / p1 - 1.0m) / tau;
    }

    /// <summary>
    /// Creates a parallel shifted yield curve by specified basis points (+1 bp = +0.0001).
    /// </summary>
    public ZeroRateYieldCurve ShiftParallel(decimal shiftBps)
    {
        decimal rateDelta = shiftBps / 10000m;
        var shiftedPillars = _pillars.Select(p => new CurvePillar(p.TenorYears, p.ZeroRate + rateDelta));
        return new ZeroRateYieldCurve($"{CurveName}_Shift_{shiftBps}bp", shiftedPillars);
    }
}

public sealed class VanillaInterestRateSwap
{
    public string SwapId { get; }
    public string ClearingMemberPayerId { get; }
    public string ClearingMemberReceiverId { get; }
    public decimal NotionalAmountUSD { get; }
    public decimal FixedRate { get; } // e.g. 0.0375 for 3.75%
    public SwapLegType LegType { get; }
    public decimal TenorYears { get; } // e.g. 5.0m for 5-year swap
    public int FixedPaymentFrequencyMonths { get; } // e.g. 6 for semi-annual
    public int FloatingPaymentFrequencyMonths { get; } // e.g. 3 for quarterly
    public DayCountBasis DayCount { get; }

    public VanillaInterestRateSwap(
        string swapId,
        string payerId,
        string receiverId,
        decimal notionalUSD,
        decimal fixedRate,
        SwapLegType legType,
        decimal tenorYears,
        int fixedFreqMonths = 6,
        int floatingFreqMonths = 3,
        DayCountBasis dayCount = DayCountBasis.Actual360)
    {
        SwapId = swapId ?? throw new ArgumentNullException(nameof(swapId));
        ClearingMemberPayerId = payerId ?? throw new ArgumentNullException(nameof(payerId));
        ClearingMemberReceiverId = receiverId ?? throw new ArgumentNullException(nameof(receiverId));
        NotionalAmountUSD = notionalUSD > 0 ? notionalUSD : throw new ArgumentOutOfRangeException(nameof(notionalUSD));
        FixedRate = fixedRate;
        LegType = legType;
        TenorYears = tenorYears > 0 ? tenorYears : throw new ArgumentOutOfRangeException(nameof(tenorYears));
        FixedPaymentFrequencyMonths = fixedFreqMonths;
        FloatingPaymentFrequencyMonths = floatingFreqMonths;
        DayCount = dayCount;
    }
}

public sealed class SwapValuationResult
{
    public string SwapId { get; init; } = string.Empty;
    public decimal PresentValueFixedLegUSD { get; init; }
    public decimal PresentValueFloatingLegUSD { get; init; }
    public decimal NetPresentValueUSD { get; init; } // MtM from perspective of Payer
    public decimal ParSwapRate { get; init; }
    public decimal DV01USD { get; init; } // Dollar value of 1 basis point shift
    public decimal AnnuityFactor { get; init; } // PV01 per $1 notional
}

public sealed class DailyVariationMarginSettlement
{
    public string SwapId { get; init; } = string.Empty;
    public string PayerMemberId { get; init; } = string.Empty;
    public string ReceiverMemberId { get; init; } = string.Empty;
    public CashAmount VariationMarginCashFlow { get; init; }
    public decimal PreviousDayMtMUSD { get; init; }
    public decimal CurrentDayMtMUSD { get; init; }
}

/// <summary>
/// Multi-Curve Interest Rate Swap Discounting & Pricing Engine for CCP derivatives clearing.
/// Computes Present Value, Par Swap Rates, DV01 risk factor sensitivities, and daily Variation Margin settlement cash flows.
/// </summary>
public sealed class InterestRateSwapDiscountingEngine
{
    public SwapValuationResult PriceSwap(
        VanillaInterestRateSwap swap,
        ZeroRateYieldCurve oisDiscountCurve,
        ZeroRateYieldCurve sofrForwardCurve)
    {
        // 1. Value Fixed Leg: N * FixedRate * Sum(tau_i * P_disc(0, T_i))
        decimal fixedIntervalYears = swap.FixedPaymentFrequencyMonths / 12.0m;
        int fixedPaymentsCount = (int)Math.Round(swap.TenorYears / fixedIntervalYears);
        decimal cumulativeDiscountedAnnuity = 0m;

        for (int i = 1; i <= fixedPaymentsCount; i++)
        {
            decimal t = i * fixedIntervalYears;
            decimal df = oisDiscountCurve.GetDiscountFactor(t);
            cumulativeDiscountedAnnuity += fixedIntervalYears * df;
        }

        decimal pvFixedLeg = swap.NotionalAmountUSD * swap.FixedRate * cumulativeDiscountedAnnuity;

        // 2. Value Floating Leg: N * Sum(tau_j * F(T_{j-1}, T_j) * P_disc(0, T_j))
        decimal floatingIntervalYears = swap.FloatingPaymentFrequencyMonths / 12.0m;
        int floatingPaymentsCount = (int)Math.Round(swap.TenorYears / floatingIntervalYears);
        decimal pvFloatingLeg = 0m;

        for (int j = 1; j <= floatingPaymentsCount; j++)
        {
            decimal t0 = (j - 1) * floatingIntervalYears;
            decimal t1 = j * floatingIntervalYears;
            decimal forwardRate = sofrForwardCurve.GetForwardRate(t0, t1);
            decimal dfDiscount = oisDiscountCurve.GetDiscountFactor(t1);

            decimal periodFloatingCashFlow = swap.NotionalAmountUSD * forwardRate * floatingIntervalYears;
            pvFloatingLeg += periodFloatingCashFlow * dfDiscount;
        }

        // Net Present Value from perspective of Fixed Payer (Pay Fixed, Receive Floating)
        decimal netPayerPV = pvFloatingLeg - pvFixedLeg;
        if (swap.LegType == SwapLegType.ReceiveFixedPayFloating)
        {
            netPayerPV = -netPayerPV;
        }

        // Par Swap Rate: rate that equates PV(Fixed) = PV(Floating) -> S_par = PV_flt / (N * Annuity)
        decimal parRate = cumulativeDiscountedAnnuity > 0m
            ? pvFloatingLeg / (swap.NotionalAmountUSD * cumulativeDiscountedAnnuity)
            : 0m;

        // 3. Compute DV01 (Dollar Value of a 1bp curve shock)
        var shiftedOis = oisDiscountCurve.ShiftParallel(1.0m);
        var shiftedSofr = sofrForwardCurve.ShiftParallel(1.0m);
        var shiftedResult = PriceSwapInternal(swap, shiftedOis, shiftedSofr);
        decimal dv01 = shiftedResult.NetPresentValueUSD - netPayerPV;

        return new SwapValuationResult
        {
            SwapId = swap.SwapId,
            PresentValueFixedLegUSD = Math.Round(pvFixedLeg, 2),
            PresentValueFloatingLegUSD = Math.Round(pvFloatingLeg, 2),
            NetPresentValueUSD = Math.Round(netPayerPV, 2),
            ParSwapRate = parRate,
            DV01USD = Math.Round(dv01, 2),
            AnnuityFactor = Math.Round(cumulativeDiscountedAnnuity, 6)
        };
    }

    private SwapValuationResult PriceSwapInternal(
        VanillaInterestRateSwap swap,
        ZeroRateYieldCurve oisDiscountCurve,
        ZeroRateYieldCurve sofrForwardCurve)
    {
        decimal fixedIntervalYears = swap.FixedPaymentFrequencyMonths / 12.0m;
        int fixedPaymentsCount = (int)Math.Round(swap.TenorYears / fixedIntervalYears);
        decimal cumulativeDiscountedAnnuity = 0m;

        for (int i = 1; i <= fixedPaymentsCount; i++)
        {
            decimal t = i * fixedIntervalYears;
            decimal df = oisDiscountCurve.GetDiscountFactor(t);
            cumulativeDiscountedAnnuity += fixedIntervalYears * df;
        }

        decimal pvFixed = swap.NotionalAmountUSD * swap.FixedRate * cumulativeDiscountedAnnuity;

        decimal floatingIntervalYears = swap.FloatingPaymentFrequencyMonths / 12.0m;
        int floatingPaymentsCount = (int)Math.Round(swap.TenorYears / floatingIntervalYears);
        decimal pvFloating = 0m;

        for (int j = 1; j <= floatingPaymentsCount; j++)
        {
            decimal t0 = (j - 1) * floatingIntervalYears;
            decimal t1 = j * floatingIntervalYears;
            decimal forwardRate = sofrForwardCurve.GetForwardRate(t0, t1);
            decimal dfDiscount = oisDiscountCurve.GetDiscountFactor(t1);
            pvFloating += swap.NotionalAmountUSD * forwardRate * floatingIntervalYears * dfDiscount;
        }

        decimal net = swap.LegType == SwapLegType.PayFixedReceiveFloating
            ? (pvFloating - pvFixed)
            : (pvFixed - pvFloating);

        return new SwapValuationResult
        {
            SwapId = swap.SwapId,
            PresentValueFixedLegUSD = pvFixed,
            PresentValueFloatingLegUSD = pvFloating,
            NetPresentValueUSD = net
        };
    }

    /// <summary>
    /// Computes daily CCP Variation Margin cash call or payment based on change in swap MtM.
    /// </summary>
    public DailyVariationMarginSettlement SettleDailyVariationMargin(
        VanillaInterestRateSwap swap,
        decimal previousDayMtMUSD,
        decimal currentDayMtMUSD)
    {
        decimal mtmDelta = currentDayMtMUSD - previousDayMtMUSD;
        var currency = Currency.USD;

        return new DailyVariationMarginSettlement
        {
            SwapId = swap.SwapId,
            PayerMemberId = swap.ClearingMemberPayerId,
            ReceiverMemberId = swap.ClearingMemberReceiverId,
            PreviousDayMtMUSD = previousDayMtMUSD,
            CurrentDayMtMUSD = currentDayMtMUSD,
            VariationMarginCashFlow = CashAmount.FromDecimal(Math.Abs(mtmDelta), currency)
        };
    }
}
