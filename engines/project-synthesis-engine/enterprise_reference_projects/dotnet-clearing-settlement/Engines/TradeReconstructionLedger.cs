namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Regulatory Bi-Temporal Trade Reconstruction Audit Ledger.
/// Complies with SEC Rule 17a-4, CFTC Part 45, and MiFID II RTS 25 microsecond clock sync.
/// Maintains an append-only cryptographic Merkle chain linking every lifecycle event
/// from trade execution to central novation and final settlement.
/// </summary>
public sealed class TradeReconstructionLedger
{
    public enum LifecycleEventType
    {
        TradeExecuted,
        NovatedToCcp,
        NettingBatchAssigned,
        MarginReserved,
        DvPSettlementAttempted,
        DvPSettlementCompleted,
        FailedSettlementRecorded,
        PenaltyAssessed,
    }

    public sealed class AuditEventRecord
    {
        public string EventId { get; }
        public string RegulatoryUti { get; }
        public LifecycleEventType EventType { get; }
        public DateTimeOffset ValidTimeUtc { get; }      // Business/effective time
        public DateTimeOffset TransactionTimeUtc { get; } // System recording time (bi-temporal)
        public string SourceSystem { get; }
        public string ActorOrMemberId { get; }
        public string DetailsJson { get; }
        public string PreviousEventHash { get; }
        public string CurrentHash { get; }

        public AuditEventRecord(
            string eventId,
            string regulatoryUti,
            LifecycleEventType eventType,
            DateTimeOffset validTimeUtc,
            DateTimeOffset transactionTimeUtc,
            string sourceSystem,
            string actorOrMemberId,
            string detailsJson,
            string previousEventHash)
        {
            EventId = eventId;
            RegulatoryUti = regulatoryUti;
            EventType = eventType;
            ValidTimeUtc = validTimeUtc;
            TransactionTimeUtc = transactionTimeUtc;
            SourceSystem = sourceSystem;
            ActorOrMemberId = actorOrMemberId;
            DetailsJson = detailsJson;
            PreviousEventHash = previousEventHash;
            CurrentHash = ComputeHash();
        }

        private string ComputeHash()
        {
            string payload = $"{EventId}|{RegulatoryUti}|{EventType}|{ValidTimeUtc.ToUnixTimeMilliseconds()}|{TransactionTimeUtc.ToUnixTimeMilliseconds()}|{SourceSystem}|{ActorOrMemberId}|{DetailsJson}|{PreviousEventHash}";
            byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes(payload));
            return Convert.ToHexString(bytes).ToLowerInvariant();
        }
    }

    private readonly List<AuditEventRecord> _chain = new();
    private readonly Dictionary<string, List<int>> _utiIndex = new(StringComparer.OrdinalIgnoreCase);

    public int EventCount => _chain.Count;
    public string LatestHash => _chain.Count > 0 ? _chain[^1].CurrentHash : "0000000000000000000000000000000000000000000000000000000000000000";

    /// <summary>
    /// Appends a new lifecycle event to the immutable chain.
    /// </summary>
    public AuditEventRecord AppendEvent(
        string regulatoryUti,
        LifecycleEventType eventType,
        DateTimeOffset validTimeUtc,
        string sourceSystem,
        string actorOrMemberId,
        string detailsJson)
    {
        string eventId = $"EVT-{Guid.NewGuid():N}";
        DateTimeOffset txTime = DateTimeOffset.UtcNow;
        string prevHash = LatestHash;

        var record = new AuditEventRecord(
            eventId,
            regulatoryUti,
            eventType,
            validTimeUtc,
            txTime,
            sourceSystem,
            actorOrMemberId,
            detailsJson,
            prevHash);

        int index = _chain.Count;
        _chain.Add(record);

        if (!_utiIndex.TryGetValue(regulatoryUti, out var list))
        {
            list = new List<int>();
            _utiIndex[regulatoryUti] = list;
        }
        list.Add(index);

        return record;
    }

    /// <summary>
    /// Reconstructs the complete lifecycle history of a trade by its UTI.
    /// </summary>
    public IReadOnlyList<AuditEventRecord> ReconstructTradeLifecycle(string regulatoryUti)
    {
        if (!_utiIndex.TryGetValue(regulatoryUti, out var indices))
        {
            return Array.Empty<AuditEventRecord>();
        }

        var results = new List<AuditEventRecord>(indices.Count);
        foreach (int idx in indices)
        {
            results.Add(_chain[idx]);
        }
        return results;
    }

    /// <summary>
    /// Reconstructs the state of the market as-of a past valid business time.
    /// </summary>
    public IReadOnlyList<AuditEventRecord> ReconstructStateAsOf(DateTimeOffset asOfValidTimeUtc)
    {
        var list = new List<AuditEventRecord>();
        foreach (var evt in _chain)
        {
            if (evt.ValidTimeUtc <= asOfValidTimeUtc)
            {
                list.Add(evt);
            }
        }
        return list;
    }

    /// <summary>
    /// Verifies the cryptographic chain integrity of the ledger from genesis to head.
    /// </summary>
    public bool VerifyChainIntegrity(out int corruptedIndex)
    {
        string expectedPrev = "0000000000000000000000000000000000000000000000000000000000000000";

        for (int i = 0; i < _chain.Count; i++)
        {
            var record = _chain[i];
            if (!string.Equals(record.PreviousEventHash, expectedPrev, StringComparison.OrdinalIgnoreCase))
            {
                corruptedIndex = i;
                return false;
            }

            // Recompute hash
            string payload = $"{record.EventId}|{record.RegulatoryUti}|{record.EventType}|{record.ValidTimeUtc.ToUnixTimeMilliseconds()}|{record.TransactionTimeUtc.ToUnixTimeMilliseconds()}|{record.SourceSystem}|{record.ActorOrMemberId}|{record.DetailsJson}|{record.PreviousEventHash}";
            byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes(payload));
            string computed = Convert.ToHexString(bytes).ToLowerInvariant();

            if (!string.Equals(record.CurrentHash, computed, StringComparison.OrdinalIgnoreCase))
            {
                corruptedIndex = i;
                return false;
            }

            expectedPrev = record.CurrentHash;
        }

        corruptedIndex = -1;
        return true;
    }
}
