namespace Elmos.ClearingSettlement.Core.Entities;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Aggregate root representing a daily settlement cycle batch.
/// Coordinates trade ingestion, novation, multilateral netting, and DvP settlement.
/// </summary>
public sealed class SettlementBatch
{
    public string BatchId { get; }
    public string BatchNumber { get; }
    public DateTime CycleDate { get; }
    public Currency SettlementCurrency { get; }
    public BatchState State { get; private set; }

    private readonly List<TradeContract> _trades = new();
    public IReadOnlyList<TradeContract> Trades => _trades.AsReadOnly();

    private readonly List<ClearingObligation> _obligations = new();
    public IReadOnlyList<ClearingObligation> Obligations => _obligations.AsReadOnly();

    public CashAmount TotalGrossTurnover { get; private set; }
    public CashAmount TotalNetCashSettlement { get; private set; }
    public decimal NettingEfficiencyPercentage { get; private set; }

    public DateTime CreatedAt { get; }
    public DateTime? NovatedAt { get; private set; }
    public DateTime? NettedAt { get; private set; }
    public DateTime? SettledAt { get; private set; }

    public SettlementBatch(string batchId, string batchNumber, DateTime cycleDate, Currency settlementCurrency)
    {
        BatchId = batchId ?? throw new ArgumentNullException(nameof(batchId));
        BatchNumber = batchNumber ?? throw new ArgumentNullException(nameof(batchNumber));
        CycleDate = cycleDate.Date;
        SettlementCurrency = settlementCurrency;
        State = BatchState.Open;
        TotalGrossTurnover = CashAmount.Zero(settlementCurrency);
        TotalNetCashSettlement = CashAmount.Zero(settlementCurrency);
        NettingEfficiencyPercentage = 0m;
        CreatedAt = DateTime.UtcNow;
    }

    public void AddTrade(TradeContract trade)
    {
        if (State != BatchState.Open)
            throw new InvalidOperationException($"Cannot add trades to batch in state {State}");

        if (trade.PricePerUnit.Currency != SettlementCurrency)
            throw new ArgumentException($"Trade currency {trade.PricePerUnit.Currency} does not match batch currency {SettlementCurrency}");

        trade.AssignToBatch(BatchId);
        _trades.Add(trade);
        TotalGrossTurnover += trade.GrossSettlementAmount;
    }

    public void StartNovation()
    {
        if (State != BatchState.Open)
            throw new InvalidOperationException($"Cannot start novation in state: {State}");
        if (_trades.Count == 0)
            throw new InvalidOperationException("Cannot novate an empty trade batch");

        State = BatchState.Novating;
        NovatedAt = DateTime.UtcNow;
    }

    public void SetNettedObligations(IEnumerable<ClearingObligation> obligations)
    {
        if (State != BatchState.Novating)
            throw new InvalidOperationException($"Batch must be Novating before netting results can be set: {State}");

        _obligations.Clear();
        _obligations.AddRange(obligations);

        // Calculate total absolute net cash flow required across all members
        long sumAbsoluteNetCash = _obligations.Sum(o => Math.Abs(o.NetCashAmount.MinorUnits));
        long sumGrossCash = _trades.Sum(t => t.GrossSettlementAmount.MinorUnits);

        TotalNetCashSettlement = CashAmount.Of(sumAbsoluteNetCash / 2, SettlementCurrency); // divide by 2 because pay = receive

        if (sumGrossCash > 0)
        {
            decimal ratio = (decimal)sumAbsoluteNetCash / (2 * sumGrossCash);
            NettingEfficiencyPercentage = Math.Max(0m, (1.0m - ratio) * 100m);
        }

        State = BatchState.Netting;
        NettedAt = DateTime.UtcNow;
    }

    public void MoveToMargining()
    {
        if (State != BatchState.Netting)
            throw new InvalidOperationException($"Batch must be Netted before margining: {State}");
        State = BatchState.Margining;
    }

    public void MoveToSettling()
    {
        if (State != BatchState.Margining)
            throw new InvalidOperationException($"Batch must complete Margining before settling: {State}");
        State = BatchState.Settling;
    }

    public void CompleteSettlement()
    {
        if (State != BatchState.Settling)
            throw new InvalidOperationException($"Batch must be Settling before completion: {State}");

        foreach (var obligation in _obligations)
        {
            obligation.MarkSettled();
        }

        foreach (var trade in _trades)
        {
            trade.MarkSettled();
        }

        State = BatchState.Completed;
        SettledAt = DateTime.UtcNow;
    }

    public void DeclareDefault()
    {
        State = BatchState.DefaultDeclared;
    }
}
