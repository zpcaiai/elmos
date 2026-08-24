package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TaskFinopsPolicyTest {
    @Test
    void fixesTheAccountWideLimitAtExactlyThree() {
        assertEquals(3, TaskFinopsPolicy.MAX_ACCOUNT_ROOT_TASKS);
        assertTrue(TaskFinopsPolicy.consumesAccountSlot(TaskFinopsPolicy.TaskState.RUNNING));
        assertTrue(TaskFinopsPolicy.consumesAccountSlot(TaskFinopsPolicy.TaskState.RECONCILING));
        assertFalse(TaskFinopsPolicy.consumesAccountSlot(TaskFinopsPolicy.TaskState.PAUSED));
        assertFalse(TaskFinopsPolicy.consumesAccountSlot(TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT));
    }

    @Test
    void stateMachineRejectsUnsafeShortcuts() {
        TaskFinopsPolicy.requireTransition(
                TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT,
                TaskFinopsPolicy.TaskState.ADMITTED);
        assertThrows(IllegalStateException.class, () -> TaskFinopsPolicy.requireTransition(
                TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT,
                TaskFinopsPolicy.TaskState.SUCCEEDED));
        assertThrows(IllegalStateException.class, () -> TaskFinopsPolicy.requireTransition(
                TaskFinopsPolicy.TaskState.SUCCEEDED,
                TaskFinopsPolicy.TaskState.RUNNING));
    }

    @Test
    void progressIsMonotonicAndOnlySuccessCanReachOneHundred() {
        var start = new TaskFinopsPolicy.Progress((short) 40, 1_000, 4_000, 8_000);
        var running = TaskFinopsPolicy.nextProgress(start, 20, 1_500, 5_000, 9_000,
                TaskFinopsPolicy.TaskState.RUNNING);
        assertEquals(40, running.percent());
        assertEquals(1_500, running.elapsedMillis());

        var capped = TaskFinopsPolicy.nextProgress(running, 100, 2_000, 5_000, 9_000,
                TaskFinopsPolicy.TaskState.RUNNING);
        assertEquals(99, capped.percent());
        var complete = TaskFinopsPolicy.nextProgress(capped, 100, 5_000, 5_000, 9_000,
                TaskFinopsPolicy.TaskState.SUCCEEDED);
        assertEquals(100, complete.percent());
        assertEquals(0, complete.etaP50Millis());
    }

    @Test
    void weightedFairOrderPreventsAHeavyTenantBacklogFromOwningTheHead() {
        Instant now = Instant.parse("2026-08-24T00:10:00Z");
        var monopolist = new TaskFinopsPolicy.QueueCandidate(
                "task-a", "tenant-a", 100, now.minusSeconds(60), 8, 1, 80);
        var newcomer = new TaskFinopsPolicy.QueueCandidate(
                "task-b", "tenant-b", 100, now.minusSeconds(30), 2, 1, 0);
        var premium = new TaskFinopsPolicy.QueueCandidate(
                "task-c", "tenant-c", 100, now.minusSeconds(20), 4, 2, 4);
        assertEquals(List.of("task-b", "task-c", "task-a"),
                TaskFinopsPolicy.weightedFairOrder(
                        List.of(monopolist, premium, newcomer), now).stream()
                        .map(TaskFinopsPolicy.QueueCandidate::taskId).toList());
    }

    @Test
    void retryAndRecoveryFailClosedForUnknownResults() {
        assertTrue(TaskFinopsPolicy.shouldRetry(
                TaskFinopsPolicy.ErrorClass.TRANSIENT, 1, 3));
        assertFalse(TaskFinopsPolicy.shouldRetry(
                TaskFinopsPolicy.ErrorClass.AUTHORIZATION, 1, 3));
        assertFalse(TaskFinopsPolicy.shouldRetry(
                TaskFinopsPolicy.ErrorClass.TRANSIENT, 3, 3));

        var identity = checkpoint("a", "b", null, "1.0");
        assertEquals(TaskFinopsPolicy.RecoveryDecision.MANUAL_RECOVERY,
                TaskFinopsPolicy.recover(identity, identity,
                        TaskFinopsPolicy.ErrorClass.UNKNOWN_RESULT, false));
        assertEquals(TaskFinopsPolicy.RecoveryDecision.RESUME_CHECKPOINT,
                TaskFinopsPolicy.recover(identity, identity,
                        TaskFinopsPolicy.ErrorClass.UNKNOWN_RESULT, true));
        assertEquals(TaskFinopsPolicy.RecoveryDecision.FORK_RUN,
                TaskFinopsPolicy.recover(identity,
                        checkpoint("c", "b", null, "1.0"),
                        TaskFinopsPolicy.ErrorClass.TRANSIENT, false));
    }

    @Test
    void exactDecimalCostMarginAndAllocationConserveMoney() {
        var cost = TaskFinopsPolicy.baseCost(
                new BigDecimal("2.5"), new BigDecimal("3.333333"),
                new BigDecimal("1.250000"), "CNY");
        assertEquals(new BigDecimal("10.416666"), cost.minorUnits());

        var revenue = new TaskFinopsPolicy.Money("CNY", new BigDecimal("20"));
        var cash = new TaskFinopsPolicy.Money("CNY", new BigDecimal("18"));
        var totals = TaskFinopsPolicy.totals(cost, revenue, cash,
                Instant.parse("2026-08-24T01:00:00Z"), true, true);
        assertEquals(new BigDecimal("9.583334"), totals.grossProfit().minorUnits());
        assertEquals(new BigDecimal("0.479166700"), totals.grossMarginRatio());
        assertTrue(totals.reconciled());

        var allocations = TaskFinopsPolicy.allocate(
                new TaskFinopsPolicy.Money("CNY", new BigDecimal("1")),
                Map.of("task-c", BigDecimal.ONE, "task-a", BigDecimal.ONE,
                        "task-b", BigDecimal.ONE));
        BigDecimal sum = allocations.values().stream()
                .map(value -> value.minorUnits()).reduce(BigDecimal.ZERO, BigDecimal::add);
        assertEquals(new BigDecimal("1.000000"), sum);
        assertEquals(new BigDecimal("0.333334"), allocations.get("task-c").minorUnits());
    }

    @Test
    void currenciesNeverMixAndZeroRevenueHasNoFabricatedMargin() {
        assertThrows(IllegalArgumentException.class, () ->
                new TaskFinopsPolicy.Money("CNY", BigDecimal.ONE)
                        .add(new TaskFinopsPolicy.Money("USD", BigDecimal.ONE)));
        var zero = new TaskFinopsPolicy.Money("CNY", BigDecimal.ZERO);
        var totals = TaskFinopsPolicy.totals(zero, zero, zero, Instant.EPOCH, false, false);
        assertNull(totals.grossMarginRatio());
        assertFalse(totals.reconciled());
    }

    private static TaskFinopsPolicy.CheckpointIdentity checkpoint(
            String inputSeed, String toolSeed, String modelSeed, String schema) {
        return new TaskFinopsPolicy.CheckpointIdentity(
                inputSeed.repeat(64), "commit-main", toolSeed.repeat(64),
                modelSeed == null ? null : modelSeed.repeat(64), schema);
    }
}
