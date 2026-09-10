package com.elmos.logistics.domain.model.wave;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * A discrete workload task assigned to a warehouse picker or automated guided vehicle (AGV).
 */
public class WavePickTask {
    private final String taskId;
    private final String waveBatchId;
    private final int priority;
    private final List<PickItem> items;

    private String assignedWorkerId;
    private PickPath optimizedPath;
    private boolean completed;
    private Instant startedAt;
    private Instant completedAt;

    public WavePickTask(String taskId, String waveBatchId, int priority, List<PickItem> items) {
        this.taskId = Objects.requireNonNull(taskId, "taskId must not be null");
        this.waveBatchId = Objects.requireNonNull(waveBatchId, "waveBatchId must not be null");
        this.priority = priority;
        this.items = new ArrayList<>(items);
        this.completed = false;
    }

    public String getTaskId() {
        return taskId;
    }

    public String getWaveBatchId() {
        return waveBatchId;
    }

    public int getPriority() {
        return priority;
    }

    public List<PickItem> getItems() {
        return Collections.unmodifiableList(items);
    }

    public String getAssignedWorkerId() {
        return assignedWorkerId;
    }

    public PickPath getOptimizedPath() {
        return optimizedPath;
    }

    public boolean isCompleted() {
        return completed;
    }

    public Instant getStartedAt() {
        return startedAt;
    }

    public Instant getCompletedAt() {
        return completedAt;
    }

    public void assignWorker(String workerId) {
        this.assignedWorkerId = Objects.requireNonNull(workerId, "workerId must not be null");
    }

    public void setOptimizedPath(PickPath optimizedPath) {
        this.optimizedPath = Objects.requireNonNull(optimizedPath, "optimizedPath must not be null");
    }

    public void start() {
        this.startedAt = Instant.now();
    }

    public void complete() {
        boolean allPicked = items.stream().allMatch(PickItem::isPicked);
        if (!allPicked) {
            throw new IllegalStateException("Cannot complete wave pick task when unpicked items remain");
        }
        this.completed = true;
        this.completedAt = Instant.now();
    }

    public int getTotalUnits() {
        return items.stream().mapToInt(PickItem::getQuantity).sum();
    }
}
