namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;
using Elmos.ClearingSettlement.Infrastructure.Persistence;

public static class NovationIntegrityTests
{
    public static async Task RunAsync()
    {
        Console.WriteLine("Running NovationIntegrityTests...");
        TestIsinLuhnChecksumValidation();
        await TestNovationRejectionForInactiveMemberAsync();
        Console.WriteLine("  ✓ NovationIntegrityTests passed successfully.");
    }

    private static void TestIsinLuhnChecksumValidation()
    {
        // Valid ISINs
        string apple = "US0378331005";
        string msft = "US5949181045";
        string tesla = "US88160R1014";

        var secApple = SecurityId.Parse(apple);
        if (secApple.Value != apple || secApple.CheckDigit != 5)
            throw new Exception("Apple ISIN parse error");

        var secMsft = SecurityId.Parse(msft);
        if (secMsft.Value != msft || secMsft.CheckDigit != 5)
            throw new Exception("MSFT ISIN parse error");

        var secTesla = SecurityId.Parse(tesla);
        if (secTesla.Value != tesla || secTesla.CheckDigit != 4)
            throw new Exception("Tesla ISIN parse error");

        // Corrupted check digit ISIN
        string corrupted = "US0378331009"; // check digit should be 5
        bool caught = false;
        try
        {
            SecurityId.Parse(corrupted);
        }
        catch (ArgumentException)
        {
            caught = true;
        }

        if (!caught)
            throw new Exception("Expected ArgumentException for corrupt ISIN checksum");
    }

    private static async Task TestNovationRejectionForInactiveMemberAsync()
    {
        var memberRepo = new InMemoryMemberRepository();
        var novationEngine = new NovationEngine(memberRepo);

        var currency = Currency.USD;
        var activeMember = new MemberInstitution("ACTIVE-M", "54930011111111111111", "Active Bank", MemberRole.DirectClearingMember, CashAmount.FromDecimal(1000000m, currency));
        var suspendedMember = new MemberInstitution("SUSPENDED-M", "54930022222222222222", "Suspended Bank", MemberRole.DirectClearingMember, CashAmount.FromDecimal(1000000m, currency));
        suspendedMember.Suspend();

        await memberRepo.SaveAsync(activeMember);
        await memberRepo.SaveAsync(suspendedMember);

        var batch = new SettlementBatch("B-FAIL", "CYC-01", DateTime.UtcNow, currency);
        var trade = new TradeContract(
            "T-FAIL",
            activeMember.MemberId,
            suspendedMember.MemberId, // Seller is suspended!
            SecurityId.Parse("US0378331005"),
            CashAmount.FromDecimal(150m, currency),
            Quantity.Of(100),
            DateTime.UtcNow,
            DateTime.UtcNow.AddDays(1)
        );
        batch.AddTrade(trade);

        bool exceptionThrown = false;
        try
        {
            await novationEngine.NovateBatchTradesAsync(batch);
        }
        catch (InvalidOperationException)
        {
            exceptionThrown = true;
        }

        if (!exceptionThrown)
            throw new Exception("Expected novation rejection for suspended clearing member");
    }
}
