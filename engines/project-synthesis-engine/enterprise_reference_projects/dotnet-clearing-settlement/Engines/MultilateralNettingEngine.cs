namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Multilateral Netting Matrix Reduction Engine.
/// Collapses an N x N matrix of bilateral settlement obligations into an N x 1 vector
/// of net obligations to the Central Counterparty (CCP).
/// Mathematically verifies the zero-sum conservation laws.
/// </summary>
public sealed class MultilateralNettingEngine
{
    public sealed class NettingResult
    {
        public IReadOnlyList<ClearingObligation> Obligations { get; }
        public CashAmount TotalGrossTurnover { get; }
        public CashAmount TotalNetCashRequired { get; }
        public decimal NettingEfficiencyRatio { get; }
        public bool InvariantCheckPassed { get; }

        public NettingResult(
            IReadOnlyList<ClearingObligation> obligations,
            CashAmount totalGrossTurnover,
            CashAmount totalNetCashRequired,
            decimal nettingEfficiencyRatio,
            bool invariantCheckPassed)
        {
            Obligations = obligations;
            TotalGrossTurnover = totalGrossTurnover;
            TotalNetCashRequired = totalNetCashRequired;
            NettingEfficiencyRatio = nettingEfficiencyRatio;
            InvariantCheckPassed = invariantCheckPassed;
        }
    }

    private sealed class MemberPositionAccumulator
    {
        public string MemberId { get; }
        public SecurityId SecurityId { get; }
        public Currency Currency { get; }

        public long NetUnits { get; set; }
        public long NetCashMinorUnits { get; set; }
        public long GrossUnits { get; set; }
        public long GrossCashMinorUnits { get; set; }

        public MemberPositionAccumulator(string memberId, SecurityId securityId, Currency currency)
        {
            MemberId = memberId;
            SecurityId = securityId;
            Currency = currency;
        }
    }

    public NettingResult ExecuteMultilateralNetting(SettlementBatch batch)
    {
        if (batch == null) throw new ArgumentNullException(nameof(batch));
        var currency = batch.SettlementCurrency;

        // Group accumulators by (MemberId, SecurityId)
        var accumulators = new Dictionary<(string MemberId, SecurityId SecurityId), MemberPositionAccumulator>();

        long totalGrossMinorUnits = 0;

        foreach (var trade in batch.Trades)
        {
            totalGrossMinorUnits += trade.GrossSettlementAmount.MinorUnits;

            // Buyer: Net Securities (+), Net Cash (-) [pays cash to receive security]
            var buyerKey = (trade.BuyerMemberId, trade.SecurityId);
            if (!accumulators.TryGetValue(buyerKey, out var buyerAcc))
            {
                buyerAcc = new MemberPositionAccumulator(trade.BuyerMemberId, trade.SecurityId, currency);
                accumulators[buyerKey] = buyerAcc;
            }
            buyerAcc.NetUnits += trade.Quantity.Units;
            buyerAcc.NetCashMinorUnits -= trade.GrossSettlementAmount.MinorUnits;
            buyerAcc.GrossUnits += trade.Quantity.Units;
            buyerAcc.GrossCashMinorUnits += trade.GrossSettlementAmount.MinorUnits;

            // Seller: Net Securities (-), Net Cash (+) [delivers security to receive cash]
            var sellerKey = (trade.SellerMemberId, trade.SecurityId);
            if (!accumulators.TryGetValue(sellerKey, out var sellerAcc))
            {
                sellerAcc = new MemberPositionAccumulator(trade.SellerMemberId, trade.SecurityId, currency);
                accumulators[sellerKey] = sellerAcc;
            }
            sellerAcc.NetUnits -= trade.Quantity.Units;
            sellerAcc.NetCashMinorUnits += trade.GrossSettlementAmount.MinorUnits;
            sellerAcc.GrossUnits += trade.Quantity.Units;
            sellerAcc.GrossCashMinorUnits += trade.GrossSettlementAmount.MinorUnits;
        }

        // Mathematical Invariant Verification:
        // 1. Total Net Cash across all members must strictly equal ZERO (Cash Conservation).
        long sumNetCashAcrossAllMembers = accumulators.Values.Sum(a => a.NetCashMinorUnits);
        if (sumNetCashAcrossAllMembers != 0)
        {
            throw new InvalidOperationException($"Conservation of Cash invariant breached: sum of net cash is {sumNetCashAcrossAllMembers} minor units (expected 0)");
        }

        // 2. For each SecurityId, total Net Units across all members must strictly equal ZERO (Securities Conservation).
        var securitiesGroups = accumulators.Values.GroupBy(a => a.SecurityId);
        foreach (var secGroup in securitiesGroups)
        {
            long sumNetSec = secGroup.Sum(a => a.NetUnits);
            if (sumNetSec != 0)
            {
                throw new InvalidOperationException($"Conservation of Securities invariant breached for {secGroup.Key}: sum is {sumNetSec} (expected 0)");
            }
        }

        // Convert accumulators to ClearingObligations
        var obligations = new List<ClearingObligation>();
        foreach (var acc in accumulators.Values)
        {
            string obligationId = $"OBL-{batch.BatchId}-{acc.MemberId}-{acc.SecurityId.Value}";
            var obligation = new ClearingObligation(
                obligationId,
                batch.BatchId,
                acc.MemberId,
                acc.SecurityId,
                Quantity.Of(acc.NetUnits),
                CashAmount.Of(acc.NetCashMinorUnits, currency),
                Quantity.Of(acc.GrossUnits),
                CashAmount.Of(acc.GrossCashMinorUnits, currency)
            );
            obligations.Add(obligation);
        }

        // Calculate netting metrics
        long sumAbsNetCash = accumulators.Values.Sum(a => Math.Abs(a.NetCashMinorUnits));
        CashAmount totalGrossTurnover = CashAmount.Of(totalGrossMinorUnits, currency);
        CashAmount totalNetCashRequired = CashAmount.Of(sumAbsNetCash / 2, currency);

        decimal efficiency = 0m;
        if (totalGrossMinorUnits > 0)
        {
            decimal netRatio = (decimal)sumAbsNetCash / (2m * totalGrossMinorUnits);
            efficiency = Math.Max(0m, (1.0m - netRatio) * 100m);
        }

        batch.SetNettedObligations(obligations);

        return new NettingResult(
            obligations,
            totalGrossTurnover,
            totalNetCashRequired,
            efficiency,
            true
        );
    }
}
