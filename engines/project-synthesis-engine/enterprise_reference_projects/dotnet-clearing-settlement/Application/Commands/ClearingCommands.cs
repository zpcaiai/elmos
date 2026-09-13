namespace Elmos.ClearingSettlement.Application.Commands;

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Application.Pipeline;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Repositories;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;

public sealed record SubmitTradeCommand(
    string TradeId,
    string BuyerMemberId,
    string SellerMemberId,
    string Isin,
    decimal Price,
    Currency Currency,
    long Quantity,
    DateTime ExecutedAt,
    DateTime SettlementDate
) : ICommand<TradeContract>;

public sealed record RunBatchClearingCommand(
    string BatchId
) : ICommand<MultilateralNettingEngine.NettingResult>;

public sealed record CalculateMarginsCommand(
    string MemberId,
    string BatchId,
    IReadOnlyDictionary<SecurityId, decimal> Volatilities,
    IReadOnlyDictionary<SecurityId, CashAmount> MtmPrices
) : ICommand<MarginCalculationEngine.MemberMarginReport>;

public sealed record TriggerWaterfallLiquidationCommand(
    string DefaulterMemberId,
    CashAmount TotalLoss,
    CashAmount CcpSkinInTheGame,
    CashAmount CcpEquityReserve
) : ICommand<DefaultWaterfallEngine.DefaultWaterfallExecutionResult>;

public sealed class ClearingCommandHandlers
{
    private readonly IMemberRepository _memberRepo;
    private readonly ITradeRepository _tradeRepo;
    private readonly ISettlementBatchRepository _batchRepo;
    private readonly IObligationRepository _obligationRepo;
    private readonly NovationEngine _novationEngine;
    private readonly MultilateralNettingEngine _nettingEngine;
    private readonly MarginCalculationEngine _marginEngine;
    private readonly DefaultWaterfallEngine _waterfallEngine;

    public ClearingCommandHandlers(
        IMemberRepository memberRepo,
        ITradeRepository tradeRepo,
        ISettlementBatchRepository batchRepo,
        IObligationRepository obligationRepo,
        NovationEngine novationEngine,
        MultilateralNettingEngine nettingEngine,
        MarginCalculationEngine marginEngine,
        DefaultWaterfallEngine waterfallEngine)
    {
        _memberRepo = memberRepo;
        _tradeRepo = tradeRepo;
        _batchRepo = batchRepo;
        _obligationRepo = obligationRepo;
        _novationEngine = novationEngine;
        _nettingEngine = nettingEngine;
        _marginEngine = marginEngine;
        _waterfallEngine = waterfallEngine;
    }

    public async Task<TradeContract> HandleSubmitTradeAsync(SubmitTradeCommand cmd)
    {
        var isin = SecurityId.Parse(cmd.Isin);
        var price = CashAmount.FromDecimal(cmd.Price, cmd.Currency);
        var qty = Quantity.Of(cmd.Quantity);

        var trade = new TradeContract(
            cmd.TradeId,
            cmd.BuyerMemberId,
            cmd.SellerMemberId,
            isin,
            price,
            qty,
            cmd.ExecutedAt,
            cmd.SettlementDate
        );

        await _tradeRepo.SaveAsync(trade);
        return trade;
    }

    public async Task<MultilateralNettingEngine.NettingResult> HandleRunBatchClearingAsync(RunBatchClearingCommand cmd)
    {
        var batch = await _batchRepo.GetByIdAsync(cmd.BatchId)
            ?? throw new InvalidOperationException($"Batch {cmd.BatchId} not found");

        await _novationEngine.NovateBatchTradesAsync(batch);
        var result = _nettingEngine.ExecuteMultilateralNetting(batch);
        await _obligationRepo.SaveRangeAsync(result.Obligations);
        await _batchRepo.SaveAsync(batch);

        return result;
    }

    public async Task<MarginCalculationEngine.MemberMarginReport> HandleCalculateMarginsAsync(CalculateMarginsCommand cmd)
    {
        var obligations = await _obligationRepo.GetByBatchIdAsync(cmd.BatchId);
        var memberObligations = new List<ClearingObligation>();
        foreach (var o in obligations)
        {
            if (o.MemberId == cmd.MemberId) memberObligations.Add(o);
        }

        return await _marginEngine.CalculateMemberMarginAsync(
            cmd.MemberId,
            memberObligations,
            cmd.Volatilities,
            cmd.MtmPrices,
            TimeSpan.FromHours(1)
        );
    }

    public async Task<DefaultWaterfallEngine.DefaultWaterfallExecutionResult> HandleTriggerWaterfallAsync(TriggerWaterfallLiquidationCommand cmd)
    {
        return await _waterfallEngine.ExecuteWaterfallAsync(
            cmd.DefaulterMemberId,
            cmd.TotalLoss,
            cmd.CcpSkinInTheGame,
            cmd.CcpEquityReserve
        );
    }
}
