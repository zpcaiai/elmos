package io.elmos.application;

import io.elmos.domain.*;
import io.elmos.evidence.AuditEvent;
import io.elmos.evidence.Evidence;

import java.util.List;

public record DemoRecord(Repository repository, RepositorySnapshot snapshot, AssessmentRun assessment,
                         MigrationPlan plan, MigrationRun run, MigrationStepRun step,
                         Evidence evidence, List<AuditEvent> auditEvents, List<DomainEvent> domainEvents) {
    public DemoRecord { auditEvents = List.copyOf(auditEvents); domainEvents = List.copyOf(domainEvents); }
}

