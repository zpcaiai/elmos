package io.elmos.workflow;

import io.elmos.application.WorkflowStatePort;
import io.elmos.domain.DomainException;
import io.elmos.domain.MigrationRunId;
import io.elmos.domain.MigrationState;

import java.util.Map;
import java.util.Set;

public final class DurableWorkflowService {
    private static final Map<MigrationState, Set<MigrationState>> ALLOWED = Map.ofEntries(
            Map.entry(MigrationState.CREATED, Set.of(MigrationState.REPOSITORY_PREPARING, MigrationState.CANCELLED)),
            Map.entry(MigrationState.REPOSITORY_PREPARING, Set.of(MigrationState.FINGERPRINTING, MigrationState.FAILED, MigrationState.CANCELLED)),
            Map.entry(MigrationState.FINGERPRINTING, Set.of(MigrationState.BASELINING, MigrationState.FAILED, MigrationState.CANCELLED)),
            Map.entry(MigrationState.BASELINING, Set.of(MigrationState.PLAN_GENERATING, MigrationState.BASELINE_BROKEN, MigrationState.CANCELLED)),
            Map.entry(MigrationState.PLAN_GENERATING, Set.of(MigrationState.AWAITING_PLAN_APPROVAL, MigrationState.FAILED, MigrationState.CANCELLED)),
            Map.entry(MigrationState.AWAITING_PLAN_APPROVAL, Set.of(MigrationState.MIGRATING, MigrationState.POLICY_BLOCKED, MigrationState.CANCELLED)),
            Map.entry(MigrationState.MIGRATING, Set.of(MigrationState.VALIDATING, MigrationState.MANUAL_INTERVENTION_REQUIRED, MigrationState.BUDGET_EXCEEDED, MigrationState.CANCELLED)),
            Map.entry(MigrationState.VALIDATING, Set.of(MigrationState.AWAITING_FINAL_REVIEW, MigrationState.VALIDATION_FAILED, MigrationState.CANCELLED)),
            Map.entry(MigrationState.AWAITING_FINAL_REVIEW, Set.of(MigrationState.PUBLISHING, MigrationState.CANCELLED)),
            Map.entry(MigrationState.PUBLISHING, Set.of(MigrationState.DELIVERED, MigrationState.FAILED)));
    private final WorkflowStatePort store;
    public DurableWorkflowService(WorkflowStatePort store) { this.store=store; }
    public WorkflowStatePort.Snapshot transition(MigrationRunId runId, MigrationState nextState, String eventType) {
        var current=store.load(runId);
        if (!ALLOWED.getOrDefault(current.state(),Set.of()).contains(nextState)) throw new DomainException("illegal workflow transition: "+current.state()+" -> "+nextState);
        return store.compareAndSet(runId,current.version(),current.state(),nextState,eventType);
    }
}

