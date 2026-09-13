namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;
using Elmos.ClearingSettlement.Infrastructure.Persistence;

public static class DefaultWaterfallTests
{
    public static async Task RunAsync()
    {
        Console.WriteLine("Running DefaultWaterfallTests...");
        await TestCpssIoscoDefaultWaterfallLiquidationAsync();
        Console.WriteLine("  ✓ DefaultWaterfallTests passed successfully.");
    }

    private static async Task TestCpssIoscoDefaultWaterfallLiquidationAsync()
    {
        var memberRepo = new InMemoryMemberRepository();
        var marginRepo = new InMemoryMarginAccountRepository();
        var engine = new DefaultWaterfallEngine(memberRepo, marginRepo);

        var currency = Currency.USD;

        // 1. Defaulter: Lehman-like hedge fund clearing member
        string defaulterId = "MEM-DEFAULTER";
        var defaulter = new MemberInstitution(defaulterId, "5493006MHB84DD0ZWV18", "Insolvent Capital LLC", MemberRole.DirectClearingMember, CashAmount.FromDecimal(2000000m, currency)); // $2M DF
        await memberRepo.SaveAsync(defaulter);

        // Defaulter's Margin Account has $10,000,000 in posted cash
        var defaulterAccount = new MarginAccount("ACC-DEF", defaulterId, currency);
        defaulterAccount.DepositCollateral(new CollateralAsset("DEF-CASH", CollateralType.Cash, CashAmount.FromDecimal(10000000m, currency)));
        await marginRepo.SaveAsync(defaulterAccount);

        // 2. Surviving Members (Bank Alpha & Bank Beta, each with $5M DF contributions)
        var survivingA = new MemberInstitution("MEM-SURVIVOR-A", "5493008MHB84DD0ZWV20", "Bank Alpha", MemberRole.GeneralClearingMember, CashAmount.FromDecimal(5000000m, currency));
        var survivingB = new MemberInstitution("MEM-SURVIVOR-B", "5493009MHB84DD0ZWV21", "Bank Beta", MemberRole.GeneralClearingMember, CashAmount.FromDecimal(5000000m, currency));
        await memberRepo.SaveAsync(survivingA);
        await memberRepo.SaveAsync(survivingB);

        // 3. CCP Capital parameters:
        // CCP Skin in the Game: $5,000,000
        // CCP Equity Reserve: $10,000,000
        CashAmount ccpSitg = CashAmount.FromDecimal(5000000m, currency);
        CashAmount ccpEquity = CashAmount.FromDecimal(10000000m, currency);

        // 4. Default Event: $25,000,000 closeout auction loss
        CashAmount totalLoss = CashAmount.FromDecimal(25000000m, currency);

        var result = await engine.ExecuteWaterfallAsync(defaulterId, totalLoss, ccpSitg, ccpEquity);

        if (!result.FullyAbsorbed)
            throw new Exception("Expected loss to be fully absorbed across the waterfall");

        if (result.UnabsorbedResidualLoss.MinorUnits != 0)
            throw new Exception($"Expected 0 residual loss, got {result.UnabsorbedResidualLoss}");

        // Trace absorption order:
        // Tranche 1 (Defaulter Margin): $10M absorbed (Remaining = $15M)
        var t1 = result.Tranches[0];
        if (t1.Tranche != WaterfallTranche.DefaulterInitialMargin || t1.AbsorbedAmount.ToDecimal() != 10000000m)
            throw new Exception($"T1 Defaulter Margin error: {t1.AbsorbedAmount}");

        // Tranche 2 (Defaulter DF): $2M absorbed (Remaining = $13M)
        var t2 = result.Tranches[1];
        if (t2.Tranche != WaterfallTranche.DefaulterDefaultFundContribution || t2.AbsorbedAmount.ToDecimal() != 2000000m)
            throw new Exception($"T2 Defaulter DF error: {t2.AbsorbedAmount}");

        // Tranche 3 (CCP SITG): $5M absorbed (Remaining = $8M)
        var t3 = result.Tranches[2];
        if (t3.Tranche != WaterfallTranche.CcpSkinInTheGameFirstLoss || t3.AbsorbedAmount.ToDecimal() != 5000000m)
            throw new Exception($"T3 CCP SITG error: {t3.AbsorbedAmount}");

        // Tranche 4 (Surviving Members DF): $8M absorbed of $10M available (Remaining = $0M)
        var t4 = result.Tranches[3];
        if (t4.Tranche != WaterfallTranche.SurvivingMembersDefaultFund || t4.AbsorbedAmount.ToDecimal() != 8000000m)
            throw new Exception($"T4 Surviving DF error: {t4.AbsorbedAmount}");

        // Tranche 5 (CCP Equity Reserve): Untouched! (Absorbed = $0)
        if (result.Tranches.Count > 4)
        {
            var t5 = result.Tranches[4];
            if (t5.AbsorbedAmount.ToDecimal() != 0m)
                throw new Exception("Tranche 5 should not be touched when Tranche 4 absorbed all remaining loss");
        }

        // Defaulter marked in default
        if (!defaulter.IsInDefault)
            throw new Exception("Defaulter institution should be flagged IsInDefault=true");
    }
}
