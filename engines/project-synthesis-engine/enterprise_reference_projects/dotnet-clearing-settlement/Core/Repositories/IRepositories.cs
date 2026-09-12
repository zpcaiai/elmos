namespace Elmos.ClearingSettlement.Core.Repositories;

using System.Collections.Generic;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Core.Entities;

public interface IMemberRepository
{
    Task<MemberInstitution?> GetByIdAsync(string memberId);
    Task<MemberInstitution?> GetByLeiAsync(string lei);
    Task<IReadOnlyList<MemberInstitution>> GetAllActiveAsync();
    Task SaveAsync(MemberInstitution member);
}

public interface ITradeRepository
{
    Task<TradeContract?> GetByIdAsync(string tradeId);
    Task<IReadOnlyList<TradeContract>> GetByBatchIdAsync(string batchId);
    Task<IReadOnlyList<TradeContract>> GetPendingTradesAsync();
    Task SaveAsync(TradeContract trade);
    Task SaveRangeAsync(IEnumerable<TradeContract> trades);
}

public interface IObligationRepository
{
    Task<ClearingObligation?> GetByIdAsync(string obligationId);
    Task<IReadOnlyList<ClearingObligation>> GetByBatchIdAsync(string batchId);
    Task<IReadOnlyList<ClearingObligation>> GetByMemberIdAsync(string memberId);
    Task SaveRangeAsync(IEnumerable<ClearingObligation> obligations);
}

public interface ISettlementBatchRepository
{
    Task<SettlementBatch?> GetByIdAsync(string batchId);
    Task<SettlementBatch?> GetCurrentOpenBatchAsync();
    Task SaveAsync(SettlementBatch batch);
}

public interface IMarginAccountRepository
{
    Task<MarginAccount?> GetByMemberIdAsync(string memberId);
    Task SaveAsync(MarginAccount account);
    Task<IReadOnlyList<MarginAccount>> GetAllAccountsAsync();
}
