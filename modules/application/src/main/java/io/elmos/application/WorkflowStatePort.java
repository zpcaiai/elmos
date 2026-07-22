package io.elmos.application;

import io.elmos.domain.MigrationRunId;
import io.elmos.domain.MigrationState;

public interface WorkflowStatePort {
    Snapshot load(MigrationRunId runId);
    Snapshot compareAndSet(MigrationRunId runId, long expectedVersion, MigrationState expectedState,
                           MigrationState nextState, String eventType);
    record Snapshot(MigrationRunId runId, MigrationState state, long version) {}
}

