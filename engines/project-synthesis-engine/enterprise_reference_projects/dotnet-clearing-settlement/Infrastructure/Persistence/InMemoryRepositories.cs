namespace Elmos.ClearingSettlement.Infrastructure.Persistence;

using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.Repositories;

public sealed class InMemoryMemberRepository : IMemberRepository
{
    private readonly ConcurrentDictionary<string, MemberInstitution> _members = new();

    public Task<MemberInstitution?> GetByIdAsync(string memberId)
    {
        _members.TryGetValue(memberId, out var member);
        return Task.FromResult(member);
    }

    public Task<MemberInstitution?> GetByLeiAsync(string lei)
    {
        var member = _members.Values.FirstOrDefault(m => m.LegalEntityIdentifier == lei);
        return Task.FromResult(member);
    }

    public Task<IReadOnlyList<MemberInstitution>> GetAllActiveAsync()
    {
        IReadOnlyList<MemberInstitution> list = _members.Values.Where(m => m.IsActive).ToList();
        return Task.FromResult(list);
    }

    public Task SaveAsync(MemberInstitution member)
    {
        _members[member.MemberId] = member;
        return Task.CompletedTask;
    }
}

public sealed class InMemoryTradeRepository : ITradeRepository
{
    private readonly ConcurrentDictionary<string, TradeContract> _trades = new();

    public Task<TradeContract?> GetByIdAsync(string tradeId)
    {
        _trades.TryGetValue(tradeId, out var trade);
        return Task.FromResult(trade);
    }

    public Task<IReadOnlyList<TradeContract>> GetByBatchIdAsync(string batchId)
    {
        IReadOnlyList<TradeContract> list = _trades.Values.Where(t => t.BatchId == batchId).ToList();
        return Task.FromResult(list);
    }

    public Task<IReadOnlyList<TradeContract>> GetPendingTradesAsync()
    {
        IReadOnlyList<TradeContract> list = _trades.Values.Where(t => t.Status == SettlementStatus.Matched).ToList();
        return Task.FromResult(list);
    }

    public Task SaveAsync(TradeContract trade)
    {
        _trades[trade.TradeId] = trade;
        return Task.CompletedTask;
    }

    public Task SaveRangeAsync(IEnumerable<TradeContract> trades)
    {
        foreach (var t in trades)
        {
            _trades[t.TradeId] = t;
        }
        return Task.CompletedTask;
    }
}

public sealed class InMemoryObligationRepository : IObligationRepository
{
    private readonly ConcurrentDictionary<string, ClearingObligation> _obligations = new();

    public Task<ClearingObligation?> GetByIdAsync(string obligationId)
    {
        _obligations.TryGetValue(obligationId, out var obligation);
        return Task.FromResult(obligation);
    }

    public Task<IReadOnlyList<ClearingObligation>> GetByBatchIdAsync(string batchId)
    {
        IReadOnlyList<ClearingObligation> list = _obligations.Values.Where(o => o.BatchId == batchId).ToList();
        return Task.FromResult(list);
    }

    public Task<IReadOnlyList<ClearingObligation>> GetByMemberIdAsync(string memberId)
    {
        IReadOnlyList<ClearingObligation> list = _obligations.Values.Where(o => o.MemberId == memberId).ToList();
        return Task.FromResult(list);
    }

    public Task SaveRangeAsync(IEnumerable<ClearingObligation> obligations)
    {
        foreach (var o in obligations)
        {
            _obligations[o.ObligationId] = o;
        }
        return Task.CompletedTask;
    }
}

public sealed class InMemorySettlementBatchRepository : ISettlementBatchRepository
{
    private readonly ConcurrentDictionary<string, SettlementBatch> _batches = new();

    public Task<SettlementBatch?> GetByIdAsync(string batchId)
    {
        _batches.TryGetValue(batchId, out var batch);
        return Task.FromResult(batch);
    }

    public Task<SettlementBatch?> GetCurrentOpenBatchAsync()
    {
        var batch = _batches.Values.FirstOrDefault(b => b.State == BatchState.Open);
        return Task.FromResult(batch);
    }

    public Task SaveAsync(SettlementBatch batch)
    {
        _batches[batch.BatchId] = batch;
        return Task.CompletedTask;
    }
}

public sealed class InMemoryMarginAccountRepository : IMarginAccountRepository
{
    private readonly ConcurrentDictionary<string, MarginAccount> _accounts = new();

    public Task<MarginAccount?> GetByMemberIdAsync(string memberId)
    {
        _accounts.TryGetValue(memberId, out var account);
        return Task.FromResult(account);
    }

    public Task SaveAsync(MarginAccount account)
    {
        _accounts[account.MemberId] = account;
        return Task.CompletedTask;
    }

    public Task<IReadOnlyList<MarginAccount>> GetAllAccountsAsync()
    {
        IReadOnlyList<MarginAccount> list = _accounts.Values.ToList();
        return Task.FromResult(list);
    }
}
