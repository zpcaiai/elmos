namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.ValueObjects;

public sealed class CompressibleSwapTrade
{
    public string TradeId { get; }
    public string PayerMemberId { get; }
    public string ReceiverMemberId { get; }
    public Currency Currency { get; }
    public decimal NotionalAmount { get; }
    public decimal FixedRate { get; }
    public decimal DV01 { get; } // Dollar Value of a Basis Point
    public DateTime MaturityDate { get; }

    public CompressibleSwapTrade(
        string tradeId,
        string payerMemberId,
        string receiverMemberId,
        Currency currency,
        decimal notionalAmount,
        decimal fixedRate,
        decimal dv01,
        DateTime maturityDate)
    {
        TradeId = tradeId ?? throw new ArgumentNullException(nameof(tradeId));
        PayerMemberId = payerMemberId ?? throw new ArgumentNullException(nameof(payerMemberId));
        ReceiverMemberId = receiverMemberId ?? throw new ArgumentNullException(nameof(receiverMemberId));
        Currency = currency;
        NotionalAmount = notionalAmount > 0 ? notionalAmount : throw new ArgumentOutOfRangeException(nameof(notionalAmount));
        FixedRate = fixedRate;
        DV01 = dv01;
        MaturityDate = maturityDate;
    }
}

public sealed class MemberRiskTolerance
{
    public string MemberId { get; init; } = string.Empty;
    public decimal MaxDV01VarianceUSD { get; init; } = 500m; // Max allowed delta risk shift ($500)
    public decimal MaxCashSettlementVarianceUSD { get; init; } = 2500m;
}

public sealed class CompressionProposalResult
{
    public string ProposalId { get; init; } = string.Empty;
    public decimal GrossInitialNotionalUSD { get; init; }
    public decimal GrossCompressedNotionalUSD { get; init; }
    public decimal GrossResidualNotionalUSD { get; init; }
    public decimal CompressionRatioPercentage => GrossInitialNotionalUSD > 0
        ? Math.Round((GrossCompressedNotionalUSD / GrossInitialNotionalUSD) * 100m, 2)
        : 0m;
    public List<string> TerminatedTradeIds { get; init; } = new();
    public List<CompressibleSwapTrade> ReplacementResidualTrades { get; init; } = new();
    public Dictionary<string, decimal> PreCompressionNetDV01 { get; init; } = new();
    public Dictionary<string, decimal> PostCompressionNetDV01 { get; init; } = new();
    public bool RiskTolerancesRespected { get; init; }
    public List<string> ToleranceViolations { get; init; } = new();
}

/// <summary>
/// Central Counterparty Multilateral Portfolio Compression & Risk-Neutral Tear-Up Engine.
/// Extinguishes redundant derivative gross notional while conserving net market risk within bounds.
/// </summary>
public sealed class CompressionTearUpEngine
{
    public CompressionProposalResult ExecuteCompressionCycle(
        string proposalId,
        IReadOnlyList<CompressibleSwapTrade> trades,
        IReadOnlyDictionary<string, MemberRiskTolerance> memberTolerances)
    {
        if (string.IsNullOrWhiteSpace(proposalId))
            throw new ArgumentNullException(nameof(proposalId));

        if (trades == null || trades.Count == 0)
        {
            return new CompressionProposalResult
            {
                ProposalId = proposalId,
                RiskTolerancesRespected = true
            };
        }

        decimal initialGross = trades.Sum(t => t.NotionalAmount);

        // 1. Calculate Pre-Compression Net DV01 per member
        // Payer pays fixed (receives floating) -> positive or negative DV01 convention
        var members = trades.Select(t => t.PayerMemberId)
            .Concat(trades.Select(t => t.ReceiverMemberId))
            .Distinct()
            .ToList();

        var preDV01 = new Dictionary<string, decimal>();
        foreach (var m in members)
        {
            decimal net = 0m;
            foreach (var t in trades)
            {
                if (t.PayerMemberId == m) net -= t.DV01;
                if (t.ReceiverMemberId == m) net += t.DV01;
            }
            preDV01[m] = net;
        }

        // 2. Multilateral Netting of Bilateral Pairs
        // Group trades by directed pair and maturity/rate bucket
        var terminatedTradeIds = new List<string>();
        var replacementTrades = new List<CompressibleSwapTrade>();
        decimal totalTornUpNotional = 0m;

        var buckets = trades.GroupBy(t => new { t.Currency, t.FixedRate, t.MaturityDate });

        int residualCounter = 1;
        foreach (var bucket in buckets)
        {
            // Build bilateral matrix for this bucket
            var bilateralFlows = new Dictionary<(string Payer, string Receiver), decimal>();
            var bucketTrades = bucket.ToList();

            foreach (var t in bucketTrades)
            {
                var key = (t.PayerMemberId, t.ReceiverMemberId);
                bilateralFlows[key] = bilateralFlows.GetValueOrDefault(key, 0m) + t.NotionalAmount;
            }

            // Detect offsetting pairs: (A -> B) and (B -> A)
            var processedPairs = new HashSet<(string, string)>();
            foreach (var key in bilateralFlows.Keys.ToList())
            {
                var reverseKey = (Payer: key.Receiver, Receiver: key.Payer);
                if (processedPairs.Contains(key) || processedPairs.Contains(reverseKey)) continue;

                if (bilateralFlows.TryGetValue(reverseKey, out decimal reverseNotional))
                {
                    decimal directNotional = bilateralFlows[key];
                    decimal offsetting = Math.Min(directNotional, reverseNotional);

                    if (offsetting > 0)
                    {
                        totalTornUpNotional += (offsetting * 2m); // Both legs compressed

                        // Mark original trades in this bucket between these two as terminated
                        var relevantTrades = bucketTrades
                            .Where(t => (t.PayerMemberId == key.Payer && t.ReceiverMemberId == key.Receiver) ||
                                        (t.PayerMemberId == key.Receiver && t.ReceiverMemberId == key.Payer))
                            .Select(t => t.TradeId)
                            .ToList();

                        terminatedTradeIds.AddRange(relevantTrades);

                        // If there is residual notional, create replacement trade
                        decimal residual = Math.Abs(directNotional - reverseNotional);
                        if (residual > 0)
                        {
                            string residualPayer = directNotional > reverseNotional ? key.Payer : key.Receiver;
                            string residualReceiver = directNotional > reverseNotional ? key.Receiver : key.Payer;
                            decimal unitDV01 = bucketTrades[0].DV01 / bucketTrades[0].NotionalAmount;

                            replacementTrades.Add(new CompressibleSwapTrade(
                                $"RESID-{proposalId}-{residualCounter++}",
                                residualPayer,
                                residualReceiver,
                                bucket.Key.Currency,
                                residual,
                                bucket.Key.FixedRate,
                                residual * unitDV01,
                                bucket.Key.MaturityDate
                            ));
                        }

                        processedPairs.Add(key);
                        processedPairs.Add(reverseKey);
                    }
                }
            }
        }

        // Add untouched trades that were not part of compressed pairs
        var uncompressedTrades = trades.Where(t => !terminatedTradeIds.Contains(t.TradeId)).ToList();
        var allPostTrades = uncompressedTrades.Concat(replacementTrades).ToList();

        // 3. Calculate Post-Compression Net DV01 per member
        var postDV01 = new Dictionary<string, decimal>();
        var violations = new List<string>();

        foreach (var m in members)
        {
            decimal net = 0m;
            foreach (var t in allPostTrades)
            {
                if (t.PayerMemberId == m) net -= t.DV01;
                if (t.ReceiverMemberId == m) net += t.DV01;
            }
            postDV01[m] = net;

            decimal dv01Shift = Math.Abs(net - preDV01[m]);
            decimal allowedTolerance = memberTolerances.TryGetValue(m, out var tol)
                ? tol.MaxDV01VarianceUSD
                : 500m;

            if (dv01Shift > allowedTolerance)
            {
                violations.Add($"Member {m} DV01 shift of ${dv01Shift:F2} exceeds tolerance ${allowedTolerance:F2}");
            }
        }

        decimal residualGross = allPostTrades.Sum(t => t.NotionalAmount);

        return new CompressionProposalResult
        {
            ProposalId = proposalId,
            GrossInitialNotionalUSD = initialGross,
            GrossCompressedNotionalUSD = totalTornUpNotional,
            GrossResidualNotionalUSD = residualGross,
            TerminatedTradeIds = terminatedTradeIds.Distinct().ToList(),
            ReplacementResidualTrades = replacementTrades,
            PreCompressionNetDV01 = preDV01,
            PostCompressionNetDV01 = postDV01,
            RiskTolerancesRespected = violations.Count == 0,
            ToleranceViolations = violations
        };
    }
}
