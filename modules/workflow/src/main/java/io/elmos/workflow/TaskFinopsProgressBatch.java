package io.elmos.workflow;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;

/**
 * Bounded, deterministic progress/heartbeat batching contract.
 *
 * <p>The accumulator only validates an authenticated task stream and produces
 * a content digest. Event-bus, SSE, object-store, and database delivery remain
 * adapter effects; a flushed batch is not a delivery receipt.</p>
 */
public final class TaskFinopsProgressBatch {
    public static final int DEFAULT_MAX_BATCH_SIZE = 128;
    public static final String DELIVERY_STATE = "NOT_RUN";

    public record Update(
            TaskFinopsPort.AuthenticatedContext context,
            String taskId,
            long eventSequence,
            TaskFinopsPolicy.TaskState taskState,
            short progressPercent,
            long elapsedMillis,
            long etaP50Millis,
            long etaP90Millis,
            String stage,
            Instant occurredAt,
            String evidenceDigest
    ) {
        public Update {
            Objects.requireNonNull(context, "context");
            taskId = identifier(taskId, "TASK", 96);
            if (eventSequence < 1 || progressPercent < 0 || progressPercent > 100
                    || elapsedMillis < 0 || etaP50Millis < 0 || etaP90Millis < etaP50Millis) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_UPDATE_INVALID");
            }
            Objects.requireNonNull(taskState, "taskState");
            if (taskState == TaskFinopsPolicy.TaskState.SUCCEEDED && progressPercent != 100) {
                throw new IllegalArgumentException("ELMOS_MTF_SUCCESS_PROGRESS_INVALID");
            }
            if (taskState != TaskFinopsPolicy.TaskState.SUCCEEDED && progressPercent == 100) {
                throw new IllegalArgumentException("ELMOS_MTF_NON_SUCCESS_PROGRESS_INVALID");
            }
            stage = optional(stage, 64, "STAGE");
            Objects.requireNonNull(occurredAt, "occurredAt");
            evidenceDigest = optionalDigest(evidenceDigest, "EVIDENCE");
        }
    }

    public record Batch(
            TaskFinopsPort.AuthenticatedContext context,
            String taskId,
            List<Update> updates,
            String digest,
            String deliveryState
    ) {
        public Batch {
            Objects.requireNonNull(context, "context");
            taskId = identifier(taskId, "TASK", 96);
            updates = List.copyOf(Objects.requireNonNull(updates, "updates"));
            String normalizedTaskId = taskId;
            if (updates.isEmpty() || updates.stream().anyMatch(update ->
                    !update.context().equals(context) || !update.taskId().equals(normalizedTaskId))) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_BATCH_SCOPE_INVALID");
            }
            digest = TaskFinopsProgressBatch.digest(digest, "BATCH");
            if (!digest.equals(sha256(canonical(context, taskId, updates)))) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_BATCH_DIGEST_MISMATCH");
            }
            if (!"NOT_RUN".equals(deliveryState)) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_DELIVERY_STATE_INVALID");
            }
            validateOrder(updates);
        }
    }

    public record FlushResult(Batch flushed, List<Update> remaining) {
        public FlushResult {
            Objects.requireNonNull(flushed, "flushed");
            remaining = List.copyOf(Objects.requireNonNull(remaining, "remaining"));
            if (remaining.stream().anyMatch(update ->
                    !update.context().equals(flushed.context())
                            || !update.taskId().equals(flushed.taskId()))) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_REMAINDER_SCOPE_INVALID");
            }
            if (!remaining.isEmpty()
                    && remaining.getFirst().eventSequence() <= flushed.updates().getLast().eventSequence()) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_REMAINDER_ORDER_INVALID");
            }
        }
    }

    public static final class Accumulator {
        private final TaskFinopsPort.AuthenticatedContext context;
        private final String taskId;
        private final int maxBatchSize;
        private final List<Update> pending = new ArrayList<>();

        public Accumulator(
                TaskFinopsPort.AuthenticatedContext context,
                String taskId,
                int maxBatchSize
        ) {
            this.context = Objects.requireNonNull(context, "context");
            this.taskId = identifier(taskId, "TASK", 96);
            if (maxBatchSize < 1 || maxBatchSize > 10_000) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_BATCH_SIZE_INVALID");
            }
            this.maxBatchSize = maxBatchSize;
        }

        public void append(Update update) {
            Objects.requireNonNull(update, "update");
            if (!update.context().equals(context) || !update.taskId().equals(taskId)) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_SCOPE_MISMATCH");
            }
            if (!pending.isEmpty()) {
                Update previous = pending.getLast();
                if (update.eventSequence() != previous.eventSequence() + 1
                        || update.progressPercent() < previous.progressPercent()
                        || update.elapsedMillis() < previous.elapsedMillis()
                        || update.occurredAt().isBefore(previous.occurredAt())) {
                    throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_ORDER_INVALID");
                }
            }
            if (pending.size() >= maxBatchSize) {
                throw new IllegalStateException("ELMOS_MTF_PROGRESS_BATCH_FULL");
            }
            pending.add(update);
        }

        public int size() {
            return pending.size();
        }

        public boolean isFull() {
            return pending.size() == maxBatchSize;
        }

        public FlushResult flush() {
            if (pending.isEmpty()) {
                throw new IllegalStateException("ELMOS_MTF_PROGRESS_BATCH_EMPTY");
            }
            Batch batch = batch(context, taskId, pending);
            pending.clear();
            return new FlushResult(batch, List.of());
        }

        public FlushResult flush(int count) {
            if (count < 1 || count > pending.size()) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_FLUSH_COUNT_INVALID");
            }
            Batch batch = batch(context, taskId, pending.subList(0, count));
            List<Update> remaining = List.copyOf(pending.subList(count, pending.size()));
            pending.clear();
            pending.addAll(remaining);
            return new FlushResult(batch, remaining);
        }
    }

    private TaskFinopsProgressBatch() {}

    public static Batch batch(
            TaskFinopsPort.AuthenticatedContext context,
            String taskId,
            List<Update> updates
    ) {
        List<Update> copy = List.copyOf(Objects.requireNonNull(updates, "updates"));
        return new Batch(context, taskId, copy,
                sha256(canonical(context, taskId, copy)), DELIVERY_STATE);
    }

    private static void validateOrder(List<Update> updates) {
        for (int index = 1; index < updates.size(); index++) {
            Update previous = updates.get(index - 1);
            Update current = updates.get(index);
            if (current.eventSequence() != previous.eventSequence() + 1
                    || current.progressPercent() < previous.progressPercent()
                    || current.elapsedMillis() < previous.elapsedMillis()
                    || current.occurredAt().isBefore(previous.occurredAt())) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_ORDER_INVALID");
            }
        }
    }

    private static String canonical(
            TaskFinopsPort.AuthenticatedContext context,
            String taskId,
            List<Update> updates
    ) {
        StringBuilder builder = new StringBuilder("elmos.task-finops.progress.v1\n")
                .append(context.organizationId()).append('|')
                .append(context.accountId()).append('|').append(taskId).append('\n');
        for (Update update : updates) {
            builder.append(update.eventSequence()).append('|')
                    .append(update.taskState()).append('|').append(update.progressPercent()).append('|')
                    .append(update.elapsedMillis()).append('|').append(update.etaP50Millis()).append('|')
                    .append(update.etaP90Millis()).append('|').append(update.stage()).append('|')
                    .append(update.occurredAt()).append('|').append(update.evidenceDigest()).append('\n');
        }
        return builder.toString();
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("ELMOS_MTF_SHA256_UNAVAILABLE", exception);
        }
    }

    private static String optional(String value, int maxLength, String field) {
        if (value == null) return null;
        return identifier(value, field, maxLength);
    }

    private static String optionalDigest(String value, String field) {
        if (value == null) return null;
        if (!value.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_DIGEST_INVALID");
        }
        return value;
    }

    private static String digest(String value, String field) {
        if (value == null || !value.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_DIGEST_INVALID");
        }
        return value;
    }

    private static String identifier(String value, String field, int maxLength) {
        if (value == null || value.isBlank() || value.length() > maxLength
                || !value.matches("[A-Za-z0-9][A-Za-z0-9._:@/-]*")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
        return value;
    }
}
