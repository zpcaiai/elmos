package io.elmos.repair;

import io.elmos.repair.RepairModels.*;

public final class BudgetController {
    public BudgetReservation reserve(RepairBudget budget, String taskId, long estimatedCostMicros,
                                     int estimatedInputTokens, int estimatedOutputTokens) {
        boolean allowed = estimatedCostMicros <= budget.maximumCostMicros()
                && estimatedInputTokens <= budget.maximumInputTokens()
                && estimatedOutputTokens <= budget.maximumOutputTokens();
        String id = "reservation-" + FailureNormalizer.hash(budget.budgetId() + "\n" + taskId + "\n" + estimatedCostMicros
                + "\n" + estimatedInputTokens + "\n" + estimatedOutputTokens).substring(0, 24);
        return new BudgetReservation(id, budget.budgetId(), taskId, allowed ? estimatedCostMicros : 0,
                allowed ? estimatedInputTokens : 0, allowed ? estimatedOutputTokens : 0,
                allowed ? BudgetStatus.RESERVED : BudgetStatus.REJECTED,
                allowed ? "BUDGET_RESERVED" : "BUDGET_HARD_LIMIT_EXCEEDED");
    }

    public BudgetReservation settle(BudgetReservation reservation, RepairBudget budget, Usage usage) {
        if (reservation.status() != BudgetStatus.RESERVED) throw new IllegalStateException("only a reservation can be settled");
        long chargedCost = usage.reported() ? usage.costMicros() : Math.max(1, reservation.reservedCostMicros());
        int chargedInput = usage.reported() ? usage.inputTokens() : reservation.reservedInputTokens();
        int chargedOutput = usage.reported() ? usage.outputTokens() : reservation.reservedOutputTokens();
        if (chargedCost > budget.maximumCostMicros() || chargedInput > budget.maximumInputTokens()
                || chargedOutput > budget.maximumOutputTokens() || usage.wallSeconds() > budget.maximumWallSeconds())
            return new BudgetReservation(reservation.reservationId(), reservation.budgetId(), reservation.taskId(),
                    chargedCost, chargedInput, chargedOutput, BudgetStatus.REJECTED, "BUDGET_HARD_LIMIT_EXCEEDED_DURING_EXECUTION");
        return new BudgetReservation(reservation.reservationId(), reservation.budgetId(), reservation.taskId(),
                chargedCost, chargedInput, chargedOutput,
                usage.reported() ? BudgetStatus.SETTLED : BudgetStatus.UNKNOWN_USAGE_CHARGED,
                usage.reported() ? "USAGE_SETTLED" : "UNKNOWN_USAGE_CHARGED_CONSERVATIVELY");
    }
}
