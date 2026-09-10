namespace Elmos.ClearingSettlement;

using System;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;
using Elmos.ClearingSettlement.Infrastructure.Persistence;
using Elmos.ClearingSettlement.Tests;

public static class Program
{
    public static async Task Main(string[] args)
    {
        Console.WriteLine("==========================================================");
        Console.WriteLine("  Central Counterparty (CCP) Clearing & Settlement (.NET)");
        Console.WriteLine("==========================================================");

        // Run all domain verification test suites
        Console.WriteLine("[CCP Autonomous Test Harness Execution]");
        MultilateralNettingTests.Run();
        await MarginCalculationTests.RunAsync();
        await DefaultWaterfallTests.RunAsync();
        await NovationIntegrityTests.RunAsync();
        DvpAndStressTests.Run();
        HistoricalVaRTests.Run();
        SimmAndRegulatoryTests.Run();

        Console.WriteLine("\n[Running Live Multi-Member Clearing Demo]");
        await RunLiveClearingDemoAsync();

        Console.WriteLine("\n==========================================================");
        Console.WriteLine("  All CCP Clearing & Settlement Suites Green (100% Passed)");
        Console.WriteLine("==========================================================");
    }

    private static async Task RunLiveClearingDemoAsync()
    {
        var memberRepo = new InMemoryMemberRepository();
        var tradeRepo = new InMemoryTradeRepository();
        var batchRepo = new InMemorySettlementBatchRepository();
        var obligationRepo = new InMemoryObligationRepository();
        var marginRepo = new InMemoryMarginAccountRepository();

        var novationEngine = new NovationEngine(memberRepo);
        var nettingEngine = new MultilateralNettingEngine();

        var currency = Currency.USD;

        // Register 3 global investment banks
        var jpm = new MemberInstitution("JPM", "7H6GLXDRUGQFU57RNE97", "JPMorgan Chase Bank, N.A.", MemberRole.GeneralClearingMember, CashAmount.FromDecimal(25000000m, currency));
        var ms = new MemberInstitution("MS", "4PQUHN3JPFGFNF3BB653", "Morgan Stanley & Co. LLC", MemberRole.GeneralClearingMember, CashAmount.FromDecimal(25000000m, currency));
        var bofa = new MemberInstitution("BOFA", "N1AP0U8F12R384501984", "BofA Securities, Inc.", MemberRole.GeneralClearingMember, CashAmount.FromDecimal(25000000m, currency));

        await memberRepo.SaveAsync(jpm);
        await memberRepo.SaveAsync(ms);
        await memberRepo.SaveAsync(bofa);

        var batch = new SettlementBatch("BATCH-2026-06-15-MAIN", "MAIN-CYCLE-01", DateTime.UtcNow, currency);

        var apple = SecurityId.Parse("US0378331005");
        var msft = SecurityId.Parse("US5949181045");

        // Bilateral trades in batch:
        // JPM buys 50,000 Apple from MS @ $150.00 ($7,500,000)
        batch.AddTrade(new TradeContract("T-01", "JPM", "MS", apple, CashAmount.FromDecimal(150.00m, currency), Quantity.Of(50000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));
        // MS buys 30,000 Apple from BOFA @ $151.00 ($4,530,000)
        batch.AddTrade(new TradeContract("T-02", "MS", "BOFA", apple, CashAmount.FromDecimal(151.00m, currency), Quantity.Of(30000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));
        // BOFA buys 20,000 Apple from JPM @ $149.50 ($2,990,000)
        batch.AddTrade(new TradeContract("T-03", "BOFA", "JPM", apple, CashAmount.FromDecimal(149.50m, currency), Quantity.Of(20000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));
        // BOFA buys 40,000 MSFT from JPM @ $310.00 ($12,400,000)
        batch.AddTrade(new TradeContract("T-04", "BOFA", "JPM", msft, CashAmount.FromDecimal(310.00m, currency), Quantity.Of(40000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));
        // MS buys 25,000 MSFT from BOFA @ $312.00 ($7,800,000)
        batch.AddTrade(new TradeContract("T-05", "MS", "BOFA", msft, CashAmount.FromDecimal(312.00m, currency), Quantity.Of(25000), DateTime.UtcNow, DateTime.UtcNow.AddDays(1)));

        await batchRepo.SaveAsync(batch);

        Console.WriteLine($"Total Gross Turnover Ingested: {batch.TotalGrossTurnover}");

        // Execute Novation
        await novationEngine.NovateBatchTradesAsync(batch);
        Console.WriteLine($"Novation completed for {batch.Trades.Count} bilateral contracts.");

        // Execute Multilateral Netting
        var nettingResult = nettingEngine.ExecuteMultilateralNetting(batch);
        Console.WriteLine($"Multilateral Netting completed: Netting Efficiency = {nettingResult.NettingEfficiencyRatio:F2}%");
        Console.WriteLine($"Total Net Cash Required: {nettingResult.TotalNetCashRequired} (vs Gross {batch.TotalGrossTurnover})");

        foreach (var obl in nettingResult.Obligations)
        {
            Console.WriteLine($"  -> {obl.MemberId,-5} | Net {obl.SecurityId} = {obl.NetQuantity,8} shares | Net Cash = {obl.NetCashAmount,14}");
        }

        batch.MoveToMargining();
        batch.MoveToSettling();
        batch.CompleteSettlement();
        Console.WriteLine($"Batch {batch.BatchId} state transitioned to {batch.State}. DvP Settlement finalized.");
    }
}
