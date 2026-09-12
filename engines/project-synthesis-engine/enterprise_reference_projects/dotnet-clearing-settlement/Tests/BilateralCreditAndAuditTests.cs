namespace Elmos.ClearingSettlement.Tests;

using System;
using System.Collections.Generic;
using Elmos.ClearingSettlement.Core.ValueObjects;
using Elmos.ClearingSettlement.Engines;

public static class BilateralCreditAndAuditTests
{
    public static void RunAll()
    {
        Console.WriteLine("[TEST SUITE] BilateralCreditEngine & TradeReconstructionLedger Tests");
        TestCsaMarginCallTriggering();
        TestAuditLedgerCryptographicIntegrity();
        TestBiTemporalStateReconstruction();
        Console.WriteLine("  ✓ All Bilateral Credit and Audit Ledger tests passed!");
    }

    private static void TestCsaMarginCallTriggering()
    {
        var usd = Currency.USD;
        var csa = new BilateralCreditEngine.CsaAgreement(
            "CSA-JPM-GS-2026",
            "JPMORGAN",
            "GOLDMAN_SACHS",
            usd,
            thresholdAmount: new CashAmount(5_000_000_00, usd),        // $5,000,000 threshold
            minimumTransferAmount: new CashAmount(500_000_00, usd),    // $500,000 MTA
            independentAmount: new CashAmount(1_000_000_00, usd),      // $1,000,000 IA
            roundingIncrementMinor: 100_000_00                         // $100,000 rounding
        );

        // Position: JPM is long 50,000 shares of MSFT @ $400 ($20,000,000 MTM)
        var positions = new List<BilateralCreditEngine.BilateralPosition>
        {
            new BilateralCreditEngine.BilateralPosition(
                "POS-1",
                SecurityId.Parse("US5949181045"),
                new Quantity(50_000),
                new CashAmount(400_00, usd),
                addOnFactorPfe: 0.05m,
                isPartyALong: true
            )
        };

        var engine = new BilateralCreditEngine();

        // Current collateral held: $10,000,000
        var currentHeldA = new CashAmount(10_000_000_00, usd);
        var currentHeldB = CashAmount.Zero(usd);

        var result = engine.EvaluateExposure(csa, positions, currentHeldA, currentHeldB);

        // Net MTM = $20,000,000 to Party A
        // Exposure above threshold = $20M + $1M IA - $5M Threshold = $16,000,000
        // Collateral deficit = $16M - $10M = $6,000,000 (>= $500k MTA) -> Margin call triggered!
        if (!result.IsMarginCallTriggered)
        {
            throw new InvalidOperationException("Expected margin call to be triggered under CSA terms");
        }
        if (result.DemandingPartyId != "JPMORGAN" || result.PledgingPartyId != "GOLDMAN_SACHS")
        {
            throw new InvalidOperationException($"Unexpected parties in margin call: {result.DemandingPartyId} demanding from {result.PledgingPartyId}");
        }
        if (result.CreditSupportAmountDemanded.MinorUnits != 6_000_000_00)
        {
            throw new InvalidOperationException($"Expected $6M demand, got: {result.CreditSupportAmountDemanded}");
        }
    }

    private static void TestAuditLedgerCryptographicIntegrity()
    {
        var ledger = new TradeReconstructionLedger();
        string uti = "UTI-2026-NYSE-000123456";

        var evt1 = ledger.AppendEvent(
            uti,
            TradeReconstructionLedger.LifecycleEventType.TradeExecuted,
            DateTimeOffset.UtcNow.AddMinutes(-10),
            "MATCHING_ENGINE",
            "TRADER_1",
            "{\"price\": 150.25, \"qty\": 100}"
        );

        var evt2 = ledger.AppendEvent(
            uti,
            TradeReconstructionLedger.LifecycleEventType.NovatedToCcp,
            DateTimeOffset.UtcNow.AddMinutes(-8),
            "CCP_NOVATION",
            "CCP_OPERATOR",
            "{\"ccpStatus\": \"NOVATED\"}"
        );

        var evt3 = ledger.AppendEvent(
            uti,
            TradeReconstructionLedger.LifecycleEventType.DvPSettlementCompleted,
            DateTimeOffset.UtcNow.AddMinutes(-5),
            "CSD_GATEWAY",
            "SETTLEMENT_DAEMON",
            "{\"settlementStatus\": \"SETTLED\"}"
        );

        if (ledger.EventCount != 3)
        {
            throw new InvalidOperationException($"Expected 3 events in ledger, got {ledger.EventCount}");
        }

        bool isValid = ledger.VerifyChainIntegrity(out int corruptedIdx);
        if (!isValid || corruptedIdx != -1)
        {
            throw new InvalidOperationException($"Ledger cryptographic integrity check failed at index {corruptedIdx}");
        }

        // Test trade reconstruction by UTI
        var tradeHistory = ledger.ReconstructTradeLifecycle(uti);
        if (tradeHistory.Count != 3)
        {
            throw new InvalidOperationException($"Expected 3 lifecycle records for UTI {uti}, got {tradeHistory.Count}");
        }
    }

    private static void TestBiTemporalStateReconstruction()
    {
        var ledger = new TradeReconstructionLedger();
        var t0 = DateTimeOffset.UtcNow.AddHours(-3);
        var t1 = DateTimeOffset.UtcNow.AddHours(-2);
        var t2 = DateTimeOffset.UtcNow.AddHours(-1);

        ledger.AppendEvent("UTI-A", TradeReconstructionLedger.LifecycleEventType.TradeExecuted, t0, "SYS", "M1", "{}");
        ledger.AppendEvent("UTI-B", TradeReconstructionLedger.LifecycleEventType.TradeExecuted, t1, "SYS", "M2", "{}");
        ledger.AppendEvent("UTI-C", TradeReconstructionLedger.LifecycleEventType.TradeExecuted, t2, "SYS", "M3", "{}");

        // Reconstruct as-of t1: should only return 2 events
        var asOfT1 = ledger.ReconstructStateAsOf(t1);
        if (asOfT1.Count != 2)
        {
            throw new InvalidOperationException($"Expected 2 events as-of {t1}, got {asOfT1.Count}");
        }
    }
}
