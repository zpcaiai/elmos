package io.elmos.domain;

import java.time.Instant;
import java.util.List;

public record AssessmentRun(String id, OrganizationId organizationId, SnapshotId snapshotId, Status status, Instant startedAt, Instant completedAt, List<String> findingIds) {
    public enum Status { RUNNING, COMPLETED, FAILED }
    public AssessmentRun { id = Identifiers.require(id, "assessmentRunId"); if (organizationId == null || snapshotId == null || status == null || startedAt == null) throw new IllegalArgumentException("assessment fields are required"); findingIds = List.copyOf(findingIds == null ? List.of() : findingIds); }
    public static AssessmentRun completed(OrganizationId organizationId, SnapshotId snapshotId, Instant now) { return new AssessmentRun(Identifiers.random(), organizationId, snapshotId, Status.COMPLETED, now, now, List.of()); }
}

