package io.elmos.controlplane;

import io.elmos.persistence.JdbcOperationsManagementStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Clock;
import java.util.UUID;

/**
 * Optional automatic SLO evaluation. It detects, diagnoses and proposes only;
 * source mutation, approval, SCM publication and deployment remain separate.
 */
@Component
final class OperationsAutomationScheduler {
    private final JdbcOperationsManagementStore management;
    private final Clock clock;
    private final boolean enabled;
    private final boolean retentionEnabled;
    private final int retentionDays;
    private final String organizationId;
    private final String actorId;

    OperationsAutomationScheduler(
            JdbcOperationsManagementStore management,
            Clock clock,
            @Value("${elmos.operations.automation-enabled:false}") boolean enabled,
            @Value("${elmos.operations.retention-enabled:false}") boolean retentionEnabled,
            @Value("${elmos.operations.retention-days:30}") int retentionDays,
            @Value("${elmos.operations.organization-id:}") String organizationId,
            @Value("${elmos.operations.actor-id:}") String actorId
    ) {
        this.management = management;
        this.clock = clock;
        this.enabled = enabled;
        this.retentionEnabled = retentionEnabled;
        this.retentionDays = retentionDays;
        this.organizationId = organizationId == null ? "" : organizationId.trim();
        this.actorId = actorId == null ? "" : actorId.trim();
    }

    @Scheduled(fixedDelayString = "${elmos.operations.evaluation-interval-ms:300000}")
    void evaluate() {
        if (!enabled || organizationId.isBlank() || actorId.isBlank()) return;
        management.evaluate(
                organizationId,
                actorId,
                "scheduled-" + UUID.randomUUID(),
                clock.instant());
    }

    @Scheduled(fixedDelayString = "${elmos.operations.retention-interval-ms:86400000}")
    void enforceRetention() {
        if (!retentionEnabled || organizationId.isBlank() || actorId.isBlank()) return;
        management.enforceRetention(
                organizationId,
                actorId,
                "scheduled-retention-" + UUID.randomUUID(),
                retentionDays,
                clock.instant());
    }
}
