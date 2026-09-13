namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Repositories;

/// <summary>
/// Novation Engine: legally interposes the CCP between buyer and seller,
/// becoming the buyer to every seller and the seller to every buyer.
/// </summary>
public sealed class NovationEngine
{
    private readonly IMemberRepository _memberRepository;

    public NovationEngine(IMemberRepository memberRepository)
    {
        _memberRepository = memberRepository ?? throw new ArgumentNullException(nameof(memberRepository));
    }

    public async Task NovateBatchTradesAsync(SettlementBatch batch)
    {
        batch.StartNovation();

        foreach (var trade in batch.Trades)
        {
            var buyer = await _memberRepository.GetByIdAsync(trade.BuyerMemberId);
            var seller = await _memberRepository.GetByIdAsync(trade.SellerMemberId);

            if (buyer == null || !buyer.IsActive)
                throw new InvalidOperationException($"Novation rejected: Buyer member {trade.BuyerMemberId} is inactive or invalid");

            if (seller == null || !seller.IsActive)
                throw new InvalidOperationException($"Novation rejected: Seller member {trade.SellerMemberId} is inactive or invalid");

            if (buyer.IsInDefault || seller.IsInDefault)
                throw new InvalidOperationException($"Novation rejected: Participant is in declared default");

            trade.MarkNovated();
        }
    }
}
