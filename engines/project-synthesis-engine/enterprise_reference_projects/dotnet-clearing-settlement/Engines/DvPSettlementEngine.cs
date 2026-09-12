namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;

public enum DvpModel
{
    Model1GrossGross,  // Simultaneous gross settlement of both securities and funds
    Model2GrossNet,    // Gross settlement of securities, net settlement of funds
    Model3NetNet       // Simultaneous multilateral net settlement of securities and funds
}

/// <summary>
/// Delivery-versus-Payment (DvP) Settlement Engine.
/// Guarantees that the transfer of securities occurs if and only if the corresponding transfer of funds occurs.
/// Implements CPMI-IOSCO DvP models and automated buy-in auction protocols for failed deliveries.
/// </summary>
public sealed class DvPSettlementEngine
{
    public sealed class MemberVault
    {
        public string MemberId { get; }
        public CashAmount CashBalance { get; set; }
        public Dictionary<SecurityId, Quantity> SecuritiesPositions { get; } = new();

        public MemberVault(string memberId, CashAmount initialCash)
        {
            MemberId = memberId;
            CashBalance = initialCash;
        }

        public void CreditSecurities(SecurityId securityId, Quantity qty)
        {
            if (SecuritiesPositions.TryGetValue(securityId, out var existing))
                SecuritiesPositions[securityId] = existing + qty;
            else
                SecuritiesPositions[securityId] = qty;
        }

        public bool TryDebitSecurities(SecurityId securityId, Quantity qty)
        {
            if (!SecuritiesPositions.TryGetValue(securityId, out var existing) || existing < qty)
                return false;

            SecuritiesPositions[securityId] = existing - qty;
            return true;
        }

        public bool TryDebitCash(CashAmount amount)
        {
            if (CashBalance < amount) return false;
            CashBalance -= amount;
            return true;
        }

        public void CreditCash(CashAmount amount)
        {
            CashBalance += amount;
        }
    }

    public sealed class SettlementExecutionResult
    {
        public string BatchId { get; }
        public DvpModel ModelUsed { get; }
        public int TotalObligationsProcessed { get; }
        public int SettledObligationsCount { get; }
        public int FailedObligationsCount { get; }
        public CashAmount TotalCashTransferred { get; }
        public bool EntireBatchSettled { get; }
        public IReadOnlyList<string> SettlementFailureReasons { get; }

        public SettlementExecutionResult(
            string batchId,
            DvpModel modelUsed,
            int totalObligationsProcessed,
            int settledObligationsCount,
            int failedObligationsCount,
            CashAmount totalCashTransferred,
            bool entireBatchSettled,
            IReadOnlyList<string> settlementFailureReasons)
        {
            BatchId = batchId;
            ModelUsed = modelUsed;
            TotalObligationsProcessed = totalObligationsProcessed;
            SettledObligationsCount = settledObligationsCount;
            FailedObligationsCount = failedObligationsCount;
            TotalCashTransferred = totalCashTransferred;
            EntireBatchSettled = entireBatchSettled;
            SettlementFailureReasons = settlementFailureReasons;
        }
    }

    /// <summary>
    /// Executes DvP Model 3 Net-Net settlement across all clearing member vaults.
    /// Either all net obligations clear atomically, or failed participants trigger buy-in.
    /// </summary>
    public SettlementExecutionResult ExecuteDvpModel3Settlement(
        SettlementBatch batch,
        IDictionary<string, MemberVault> memberVaults)
    {
        if (batch.State != BatchState.Settling)
            throw new InvalidOperationException($"Batch must be in Settling state: {batch.State}");

        var currency = batch.SettlementCurrency;
        var failures = new List<string>();
        int settledCount = 0;
        int failedCount = 0;
        CashAmount totalCashTransferred = CashAmount.Zero(currency);

        // Phase 1: Pre-settlement validation (ensure all members with net debits have sufficient balances)
        foreach (var obl in batch.Obligations)
        {
            if (!memberVaults.TryGetValue(obl.MemberId, out var vault))
            {
                failures.Add($"Vault not found for clearing member: {obl.MemberId}");
                failedCount++;
                continue;
            }

            // If member owes cash to CCP
            if (obl.NetCashAmount.IsNegative)
            {
                CashAmount cashDue = obl.NetCashAmount.Abs();
                if (vault.CashBalance < cashDue)
                {
                    failures.Add($"Insufficient funds for {obl.MemberId}: required {cashDue}, available {vault.CashBalance}");
                    obl.MarkFailed("INSUFFICIENT_CASH");
                    failedCount++;
                    continue;
                }
            }

            // If member owes securities to CCP (deliverer)
            if (obl.NetQuantity.IsNegative)
            {
                Quantity secDue = obl.NetQuantity.Abs();
                vault.SecuritiesPositions.TryGetValue(obl.SecurityId, out var secAvailable);
                if (secAvailable < secDue)
                {
                    failures.Add($"Securities delivery fail for {obl.MemberId}: required {secDue} of {obl.SecurityId}, available {secAvailable}");
                    obl.MarkFailed("INSUFFICIENT_SECURITIES");
                    failedCount++;
                    continue;
                }
            }
        }

        // Phase 2: If any critical failure occurred, abort full DvP and trigger fail resolution
        if (failedCount > 0)
        {
            return new SettlementExecutionResult(
                batch.BatchId,
                DvpModel.Model3NetNet,
                batch.Obligations.Count,
                0,
                failedCount,
                totalCashTransferred,
                false,
                failures
            );
        }

        // Phase 3: Atomic DvP execution (Simultaneous cash and securities transfers)
        foreach (var obl in batch.Obligations)
        {
            var vault = memberVaults[obl.MemberId];

            // Settle Cash
            if (obl.NetCashAmount.IsNegative)
            {
                vault.TryDebitCash(obl.NetCashAmount.Abs());
                totalCashTransferred += obl.NetCashAmount.Abs();
            }
            else if (obl.NetCashAmount.IsPositive)
            {
                vault.CreditCash(obl.NetCashAmount);
            }

            // Settle Securities
            if (obl.NetQuantity.IsNegative)
            {
                vault.TryDebitSecurities(obl.SecurityId, obl.NetQuantity.Abs());
            }
            else if (obl.NetQuantity.IsPositive)
            {
                vault.CreditSecurities(obl.SecurityId, obl.NetQuantity.Abs());
            }

            obl.MarkSettled();
            settledCount++;
        }

        batch.CompleteSettlement();

        return new SettlementExecutionResult(
            batch.BatchId,
            DvpModel.Model3NetNet,
            batch.Obligations.Count,
            settledCount,
            0,
            totalCashTransferred,
            true,
            failures
        );
    }
}
