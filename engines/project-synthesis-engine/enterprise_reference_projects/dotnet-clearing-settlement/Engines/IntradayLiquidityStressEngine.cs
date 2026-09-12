namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.ValueObjects;

public enum LiquidityFlowDirection
{
    InboundReceipt,   // Cash paid into CCP by members
    OutboundPayment   // Cash disbursed by CCP to members/settlement banks
}

public sealed class IntradayCashFlowEvent
{
    public string FlowId { get; }
    public string MemberId { get; }
    public TimeOnly ScheduledTime { get; }
    public LiquidityFlowDirection Direction { get; }
    public CashAmount Amount { get; }
    public string SettlementRail { get; } // Fedwire, TARGET2, CHAPS

    public IntradayCashFlowEvent(
        string flowId,
        string memberId,
        TimeOnly scheduledTime,
        LiquidityFlowDirection direction,
        CashAmount amount,
        string settlementRail = "Fedwire")
    {
        FlowId = flowId ?? throw new ArgumentNullException(nameof(flowId));
        MemberId = memberId ?? throw new ArgumentNullException(nameof(memberId));
        ScheduledTime = scheduledTime;
        Direction = direction;
        Amount = amount;
        SettlementRail = settlementRail;
    }
}

public sealed class IntradayStressScenario
{
    public string ScenarioName { get; init; } = string.Empty;
    public HashSet<string> DefaultedMemberIds { get; init; } = new(); // Inflows completely cut off
    public decimal InboundPaymentDelayHours { get; init; } = 0m;      // Rail freeze delaying inflows
    public decimal OutboundSurgeMultiplier { get; init; } = 1.0m;     // Extreme market volatility surge
}

public sealed class HourlyLiquidityPoint
{
    public TimeOnly Hour { get; init; }
    public decimal CumulativeInflow { get; init; }
    public decimal CumulativeOutflow { get; init; }
    public decimal NetLiquidityPosition { get; init; } // Available opening liquidity + cumulative net
    public decimal LiquidityBufferDeficit { get; init; } // Negative if buffer exhausted
}

public sealed class IntradayLiquidityAssessmentResult
{
    public string ScenarioName { get; init; } = string.Empty;
    public CashAmount OpeningCentralBankReserve { get; init; }
    public CashAmount CommittedCreditLines { get; init; }
    public decimal TotalAvailableLiquidityFacilityUSD { get; init; }
    public decimal PeakIntradayLiquidityDeficitUSD { get; init; }
    public TimeOnly PeakDeficitTime { get; init; }
    public decimal MinimumRemainingLiquidityUSD { get; init; }
    public bool BreachedCommittedFacilities { get; init; }
    public List<HourlyLiquidityPoint> HourlyTrajectory { get; init; } = new();
    public string RegulatoryAssessmentSummary { get; init; } = string.Empty;
}

/// <summary>
/// BCBS 248 Intraday Liquidity Monitoring & Stress Testing Engine for CCPs.
/// Simulates member default contagion, payment rail cutoffs, and intraday margin stress.
/// </summary>
public sealed class IntradayLiquidityStressEngine
{
    public IntradayLiquidityAssessmentResult AssessIntradayStress(
        CashAmount openingReserve,
        CashAmount committedCreditLines,
        IReadOnlyList<IntradayCashFlowEvent> scheduledFlows,
        IntradayStressScenario scenario)
    {
        if (openingReserve.Currency != committedCreditLines.Currency)
            throw new ArgumentException("Reserve and credit lines currency mismatch");

        decimal totalFacility = openingReserve.Amount + committedCreditLines.Amount;

        // Apply scenario stress modifications to flows
        var activeFlows = new List<(TimeOnly Time, decimal AmountDelta)>();

        foreach (var flow in scheduledFlows)
        {
            if (flow.Direction == LiquidityFlowDirection.InboundReceipt)
            {
                // If member has defaulted, inbound payments are lost
                if (scenario.DefaultedMemberIds.Contains(flow.MemberId))
                {
                    continue; // Zero inflow
                }

                // If rail delay applies, push inflow back
                var effectiveTime = flow.ScheduledTime;
                if (scenario.InboundPaymentDelayHours > 0)
                {
                    int delayMinutes = (int)(scenario.InboundPaymentDelayHours * 60m);
                    effectiveTime = flow.ScheduledTime.AddMinutes(delayMinutes);
                }

                activeFlows.Add((effectiveTime, flow.Amount.Amount));
            }
            else // Outbound payment
            {
                // Outbound obligations cannot be delayed by the CCP without systemic failure
                decimal stressedOutflow = flow.Amount.Amount * scenario.OutboundSurgeMultiplier;
                activeFlows.Add((flow.ScheduledTime, -stressedOutflow));
            }
        }

        // Evaluate trajectory from 07:00 to 18:00 hourly
        var trajectory = new List<HourlyLiquidityPoint>();
        decimal currentBalance = openingReserve.Amount;
        decimal peakDeficit = 0m;
        TimeOnly peakDeficitTime = new TimeOnly(7, 0);
        decimal minRemaining = currentBalance;
        decimal cumIn = 0m;
        decimal cumOut = 0m;

        for (int h = 7; h <= 18; h++)
        {
            var hourStart = new TimeOnly(h, 0);
            var hourEnd = new TimeOnly(h, 59, 59);

            var flowsInHour = activeFlows.Where(f => f.Time >= hourStart && f.Time <= hourEnd).ToList();
            foreach (var f in flowsInHour)
            {
                if (f.AmountDelta > 0) cumIn += f.AmountDelta;
                else cumOut += Math.Abs(f.AmountDelta);

                currentBalance += f.AmountDelta;

                if (currentBalance < minRemaining)
                {
                    minRemaining = currentBalance;
                    peakDeficitTime = f.Time;
                }
            }

            decimal deficitUnderZero = currentBalance < 0 ? Math.Abs(currentBalance) : 0m;
            if (deficitUnderZero > peakDeficit)
            {
                peakDeficit = deficitUnderZero;
            }

            trajectory.Add(new HourlyLiquidityPoint
            {
                Hour = hourStart,
                CumulativeInflow = cumIn,
                CumulativeOutflow = cumOut,
                NetLiquidityPosition = currentBalance,
                LiquidityBufferDeficit = deficitUnderZero
            });
        }

        bool breached = peakDeficit > committedCreditLines.Amount;
        string summary = breached
            ? $"REGULATORY BREACH: Peak deficit of ${peakDeficit:N0} exhausts total facilities (${totalFacility:N0}). Requires discount window emergency injection."
            : $"COMPLIANT: Peak deficit of ${peakDeficit:N0} fully absorbed by committed liquidity buffer (${committedCreditLines.Amount:N0}).";

        return new IntradayLiquidityAssessmentResult
        {
            ScenarioName = scenario.ScenarioName,
            OpeningCentralBankReserve = openingReserve,
            CommittedCreditLines = committedCreditLines,
            TotalAvailableLiquidityFacilityUSD = totalFacility,
            PeakIntradayLiquidityDeficitUSD = peakDeficit,
            PeakDeficitTime = peakDeficitTime,
            MinimumRemainingLiquidityUSD = minRemaining,
            BreachedCommittedFacilities = breached,
            HourlyTrajectory = trajectory,
            RegulatoryAssessmentSummary = summary
        };
    }
}
