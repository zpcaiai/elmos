package io.elmos.application;

import io.elmos.domain.MigrationState;
import io.elmos.domain.StepState;
import io.elmos.evidence.EvidenceStatus;

public record DemoRunResult(String repositoryId, String snapshotId, String assessmentRunId, String migrationPlanId,
                            int migrationPlanVersion, String migrationRunId, MigrationState state,
                            String stepRunId, StepState stepState, String evidenceId, EvidenceStatus evidenceStatus,
                            int auditEventCount, int outboxEventCount, boolean simulated) {}

