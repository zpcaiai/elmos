package com.elmos.logistics.domain.model.wave;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/**
 * Aggregate root for a wave of orders batched together for simultaneous picking optimization.
 */
public class WaveBatch {
    private final String waveBatchId;
    private final String tenantId;
    private final String warehouseId;
    private final String waveNumber;
    private final Instant createdAt;
    private final Set<String> orderIds;
    private final List<WavePickTask> tasks;

    private WaveStatus status;
    private Instant releasedAt;
    private Instant completedAt;

    public WaveBatch(String waveBatchId,
                     String tenantId,
                     String warehouseId,
                     String waveNumber) {
        this.waveBatchId = Objects.requireNonNull(waveBatchId, "waveBatchId must not be null");
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId must not be null");
        this.warehouseId = Objects.requireNonNull(warehouseId, "warehouseId must not be null");
        this.waveNumber = Objects.requireNonNull(waveNumber, "waveNumber must not be null");
        this.createdAt = Instant.now();
        this.orderIds = new HashSet<>();
        this.tasks = new ArrayList<>();
        this.status = WaveStatus.PLANNING;
    }

    public String getWaveBatchId() {
        return waveBatchId;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getWarehouseId() {
        return warehouseId;
    }

    public String getWaveNumber() {
        return waveNumber;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Set<String> getOrderIds() {
        return Collections.unmodifiableSet(orderIds);
    }

    public List<WavePickTask> getTasks() {
        return Collections.unmodifiableList(tasks);
    }

    public WaveStatus getStatus() {
        return status;
    }

    public Instant getReleasedAt() {
        return releasedAt;
    }

    public Instant getCompletedAt() {
        return completedAt;
    }

    public void addOrder(String orderId) {
        if (status != WaveStatus.PLANNING) {
            throw new IllegalStateException("Cannot add orders to wave in status " + status);
        }
        this.orderIds.add(Objects.requireNonNull(orderId, "orderId must not be null"));
    }

    public void addTask(WavePickTask task) {
        Objects.requireNonNull(task, "task must not be null");
        this.tasks.add(task);
    }

    public void setStatus(WaveStatus status) {
        this.status = Objects.requireNonNull(status, "status must not be null");
    }

    public void releaseToFloor() {
        if (tasks.isEmpty()) {
            throw new IllegalStateException("Cannot release empty wave batch");
        }
        this.status = WaveStatus.RELEASED_TO_FLOOR;
        this.releasedAt = Instant.now();
    }

    public void checkCompletion() {
        boolean allComplete = tasks.stream().allMatch(WavePickTask::isCompleted);
        if (allComplete) {
            this.status = WaveStatus.PICKING_COMPLETE;
            this.completedAt = Instant.now();
        }
    }

    public int getTotalUnits() {
        return tasks.stream().mapToInt(WavePickTask::getTotalUnits).sum();
    }
}
