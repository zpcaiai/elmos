package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TaskFinopsProgressBatchTest {
    private static final Instant START = Instant.parse("2026-08-26T02:00:00Z");

    @Test
    void flushesAContiguousMonotonicBatchWithAStableDigest() {
        var context = context("request-1");
        var accumulator = new TaskFinopsProgressBatch.Accumulator(context, "task-1", 2);
        accumulator.append(update(context, 1, 10, 1_000));
        accumulator.append(update(context, 2, 20, 2_000));

        assertTrue(accumulator.isFull());
        var flushed = accumulator.flush();
        assertEquals(2, flushed.flushed().updates().size());
        assertEquals(64, flushed.flushed().digest().length());
        assertEquals("NOT_RUN", flushed.flushed().deliveryState());
        assertEquals(0, accumulator.size());
    }

    @Test
    void partialFlushRetainsOnlyTheUnflushedSuffix() {
        var context = context("request-2");
        var accumulator = new TaskFinopsProgressBatch.Accumulator(context, "task-1", 4);
        for (int sequence = 1; sequence <= 3; sequence++) {
            accumulator.append(update(context, sequence, sequence * 10L, sequence * 1_000L));
        }

        var result = accumulator.flush(2);
        assertEquals(List.of(1L, 2L), result.flushed().updates().stream()
                .map(TaskFinopsProgressBatch.Update::eventSequence).toList());
        assertEquals(List.of(3L), result.remaining().stream()
                .map(TaskFinopsProgressBatch.Update::eventSequence).toList());
        assertEquals(1, accumulator.size());
    }

    @Test
    void rejectsGapsRegressionsAndCrossAccountUpdates() {
        var context = context("request-3");
        var accumulator = new TaskFinopsProgressBatch.Accumulator(context, "task-1", 4);
        accumulator.append(update(context, 1, 10, 1_000));
        assertThrows(IllegalArgumentException.class,
                () -> accumulator.append(update(context, 3, 20, 2_000)));
        assertThrows(IllegalArgumentException.class,
                () -> accumulator.append(update(context, 2, 9, 2_000)));
        var other = new TaskFinopsPort.AuthenticatedContext(
                "org-1", "acct-2", "actor-1", "request-4");
        assertThrows(IllegalArgumentException.class,
                () -> accumulator.append(update(other, 2, 20, 2_000)));
    }

    @Test
    void batchSinkCanObserveLocalBytesWithoutManufacturingDelivery() {
        var context = context("request-5");
        List<TaskFinopsProgressBatch.Batch> observed = new ArrayList<>();
        observed.add(TaskFinopsProgressBatch.batch(context, "task-1",
                List.of(update(context, 1, 10, 1_000))));
        assertEquals(1, observed.size());
        assertEquals("NOT_RUN", observed.getFirst().deliveryState());
    }

    private static TaskFinopsPort.AuthenticatedContext context(String requestId) {
        return new TaskFinopsPort.AuthenticatedContext("org-1", "acct-1", "actor-1", requestId);
    }

    private static TaskFinopsProgressBatch.Update update(
            TaskFinopsPort.AuthenticatedContext context,
            long sequence,
            long progress,
            long elapsed
    ) {
        return new TaskFinopsProgressBatch.Update(
                context, "task-1", sequence, TaskFinopsPolicy.TaskState.RUNNING,
                (short) progress, elapsed, 5_000, 10_000,
                "running", START.plusSeconds(sequence), null);
    }
}
