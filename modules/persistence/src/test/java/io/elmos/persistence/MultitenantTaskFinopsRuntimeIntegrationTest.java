package io.elmos.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.commercial.SelfServiceBillingPort;
import io.elmos.workflow.ExecutionJobPort;
import io.elmos.workflow.TaskFinopsAnalytics;
import io.elmos.workflow.TaskFinopsAnalyticsService;
import io.elmos.workflow.TaskFinopsFeatureRollout;
import io.elmos.workflow.TaskFinopsOperationsPort;
import io.elmos.workflow.TaskFinopsPolicy;
import io.elmos.workflow.TaskFinopsPort;
import io.elmos.workflow.TenantLifecyclePolicy;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Real PostgreSQL coverage for the V77 account-wide scheduler and task-control
 * contract. All identities, provider references, payloads and credentials in
 * this fixture are synthetic and the container database is disposable.
 */
@Testcontainers(disabledWithoutDocker = true)
class MultitenantTaskFinopsRuntimeIntegrationTest {
    private static final String ORGANIZATION = "org-mtf-runtime-it";
    private static final String OWNER_ACCOUNT = "acc-mtf-runtime-owner";
    private static final String OWNER_ACTOR = "actor-mtf-runtime-owner";
    private static final String OWNER_OIDC_SUBJECT = "oidc-subject-mtf-runtime-owner";
    private static final String MEMBER_ACCOUNT = "acc-mtf-runtime-member";
    private static final String MEMBER_ACTOR = "actor-mtf-runtime-member";
    private static final String RUNNER = "runner-mtf-runtime-1";
    private static final String REGISTERED_CAPABILITY = "generation:multi";

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:17.5-alpine");

    @Test
    void enforcesCanonicalIdentityAccountSlotsRegisteredCapabilitiesPauseAndIsolation() {
        Flyway.configure()
                .dataSource(
                        POSTGRES.getJdbcUrl(),
                        POSTGRES.getUsername(),
                        POSTGRES.getPassword())
                .defaultSchema("public")
                .load()
                .migrate();

        var dataSource = new DriverManagerDataSource(
                POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
        var jdbc = JdbcClient.create(dataSource);
        var transactions = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));

        var identities = new JdbcOrganizationSelfServiceStore(jdbc, transactions);
        provisionCanonicalIdentities(identities);

        var ownerGrant = identities.organizations(OWNER_ACCOUNT).stream()
                .filter(grant -> ORGANIZATION.equals(grant.organizationId()))
                .findFirst()
                .orElseThrow();
        var memberGrant = identities.organizations(MEMBER_ACCOUNT).stream()
                .filter(grant -> ORGANIZATION.equals(grant.organizationId()))
                .findFirst()
                .orElseThrow();
        assertEquals(OWNER_ACTOR, ownerGrant.actorId());
        assertEquals(MEMBER_ACTOR, memberGrant.actorId());
        assertNotEquals(OWNER_OIDC_SUBJECT, ownerGrant.actorId(),
                "the selected grant actor, not the raw OIDC subject, is authoritative");

        activateFiveJobOrganizationPlan(jdbc, transactions, ownerGrant.actorId());
        assertEquals(5, jdbc.sql("select elmos_execution_concurrency_limit(:organization)")
                .param("organization", ORGANIZATION)
                .query(Integer.class)
                .single(),
                "the fixture organization must not be the source of the three-slot ceiling");

        provisionAttestedRunner(jdbc, transactions, ownerGrant.actorId());

        var jobs = new JdbcExecutionJobStore(jdbc, transactions, new ObjectMapper());
        var finops = new JdbcTaskFinopsStore(jdbc, transactions);
        var operations = new JdbcTaskFinopsOperationsStore(
                jdbc, transactions, new ObjectMapper());
        var ownerContext = new TaskFinopsPort.AuthenticatedContext(
                ORGANIZATION, OWNER_ACCOUNT, ownerGrant.actorId(), "request-owner-read");
        var memberContext = new TaskFinopsPort.AuthenticatedContext(
                ORGANIZATION, MEMBER_ACCOUNT, memberGrant.actorId(), "request-member-read");
        var ownerExecutionContext = new ExecutionJobPort.AuthenticatedContext(
                ORGANIZATION, OWNER_ACCOUNT, ownerGrant.actorId(), "request-owner-execution-read");
        var memberExecutionContext = new ExecutionJobPort.AuthenticatedContext(
                ORGANIZATION, MEMBER_ACCOUNT, memberGrant.actorId(), "request-member-execution-read");

        Boolean forgedGucAccepted = transactions.execute(status -> {
            jdbc.sql("""
                    select set_config('app.organization_id', :organization, true),
                           set_config('app.account_id', :account, true),
                           set_config('app.actor_id', :actor, true),
                           set_config('app.request_id', :request, true)
                    """)
                    .param("organization", ORGANIZATION)
                    .param("account", OWNER_ACCOUNT)
                    .param("actor", ownerGrant.actorId())
                    .param("request", "forged-guc-only")
                    .query().singleRow();
            return jdbc.sql("""
                    select elmos_mtf_context_matches(:organization, :account)
                    """)
                    .param("organization", ORGANIZATION)
                    .param("account", OWNER_ACCOUNT)
                    .query(Boolean.class).single();
        });
        assertFalse(Boolean.TRUE.equals(forgedGucAccepted),
                "custom GUC values alone must never establish tenant authority");

        var rawSubjectRejected = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> jobs.enqueue(enqueueCommand(
                        "job-mtf-invalid-identity", OWNER_ACCOUNT, OWNER_OIDC_SUBJECT)));
        assertEquals("ELMOS_MTF_IDENTITY_CONTEXT_INVALID", rawSubjectRejected.code());

        var jobIds = List.of(
                "job-mtf-owner-1",
                "job-mtf-owner-2",
                "job-mtf-owner-3",
                "job-mtf-owner-4");
        for (String jobId : jobIds) {
            assertEquals(jobId, jobs.enqueue(
                    enqueueCommand(jobId, OWNER_ACCOUNT, ownerGrant.actorId())));
        }
        var canonicalJob = jobs.find(ownerExecutionContext, jobIds.getFirst()).orElseThrow();
        assertEquals(OWNER_ACCOUNT, canonicalJob.accountId());
        assertEquals(ownerGrant.actorId(), canonicalJob.actorId());
        assertEquals(4, jobs.list(ownerExecutionContext, null, 100, 0).size());

        // The request deliberately advertises a different capability. V77 keeps
        // that argument only for compatibility and schedules from the DB-registered
        // runner capabilities instead. V77 owns this repository compatibility
        // boundary; the packaged V100-V102 references remain NOT_APPLIED.
        var firstClaims = jobs.claim(
                RUNNER, List.of("translation:multi"), 4, 120);
        assertEquals(3, firstClaims.size(),
                "an account may occupy exactly three root-task slots");
        assertEquals(
                Set.of(jobIds.get(0), jobIds.get(1), jobIds.get(2)),
                Set.copyOf(firstClaims.stream().map(ExecutionJobPort.LeaseGrant::jobId).toList()));

        var saturated = finops.concurrencyStatus(ownerContext);
        assertEquals(3, saturated.rootTaskLimit());
        assertEquals(3, saturated.activeRootTasks());
        assertEquals(1, saturated.waitingRootTasks());
        assertEquals(0, saturated.availableRootSlots());
        var waiting = jobs.find(ownerExecutionContext, jobIds.get(3)).orElseThrow();
        assertEquals("WAITING_FOR_SLOT", waiting.admissionState());
        assertEquals(1, waiting.queuePosition());

        var controlledLease = firstClaims.stream()
                .filter(grant -> grant.jobId().equals(jobIds.getFirst()))
                .findFirst()
                .orElseThrow();
        var firstHeartbeat = jobs.heartbeat(heartbeat(controlledLease, (short) 25, "checkpoint-25"));
        assertFalse(firstHeartbeat.cancelRequested());
        assertFalse(firstHeartbeat.pauseRequested());
        var firstProgress = finops.progress(ownerContext, controlledLease.jobId()).orElseThrow();
        assertEquals(25, firstProgress.progressPercent());
        assertTrue(firstProgress.etaP90Millis() >= firstProgress.etaP50Millis());

        var secondHeartbeat = jobs.heartbeat(heartbeat(controlledLease, (short) 50, "checkpoint-50"));
        assertFalse(secondHeartbeat.pauseRequested());
        var secondProgress = finops.progress(ownerContext, controlledLease.jobId()).orElseThrow();
        assertEquals(50, secondProgress.progressPercent());
        assertTrue(secondProgress.elapsedMillis() >= firstProgress.elapsedMillis());
        assertTrue(secondProgress.etaP50Millis() >= 0);
        assertTrue(secondProgress.etaP90Millis() >= secondProgress.etaP50Millis());
        assertTrue(secondProgress.lastEventSequence() > firstProgress.lastEventSequence());

        var regressionRejected = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> jobs.heartbeat(heartbeat(controlledLease, (short) 49, "stale-checkpoint")));
        assertEquals("ELMOS_MTF_PROGRESS_NOT_MONOTONIC", regressionRejected.code());
        assertEquals(50, finops.progress(ownerContext, controlledLease.jobId())
                .orElseThrow().progressPercent());

        assertEquals(
                TaskFinopsPolicy.TaskState.PAUSE_REQUESTED,
                finops.pause(new TaskFinopsPort.ControlCommand(
                        ownerContext,
                        controlledLease.jobId(),
                        "USER_REQUESTED_SAFE_STOP",
                        "pause-idempotency-1",
                        sha256("pause:" + controlledLease.jobId()))));
        var pauseHeartbeat = jobs.heartbeat(
                heartbeat(controlledLease, (short) 50, "checkpoint-50"));
        assertTrue(pauseHeartbeat.pauseRequested());
        assertTrue(jobs.complete(new ExecutionJobPort.CompletionCommand(
                controlledLease.leaseId(),
                RUNNER,
                controlledLease.leaseToken(),
                ExecutionJobPort.Status.PAUSED,
                ExecutionJobPort.ResultStatus.NOT_RUN,
                null)));

        var paused = jobs.find(ownerExecutionContext, controlledLease.jobId()).orElseThrow();
        assertEquals(ExecutionJobPort.Status.PAUSED, paused.status());
        assertEquals(ExecutionJobPort.ResultStatus.NOT_RUN, paused.resultStatus());
        assertEquals("checkpoint-50", jdbc.sql("""
                select checkpoint_cursor ->> 'cursor'
                  from execution_jobs
                 where job_id = :job
                """)
                .param("job", controlledLease.jobId())
                .query(String.class)
                .single(),
                "safe pause completion must preserve the latest checkpoint cursor");
        var pausedProgress = finops.progress(ownerContext, controlledLease.jobId()).orElseThrow();
        assertEquals(TaskFinopsPolicy.TaskState.PAUSED, pausedProgress.taskState());
        assertEquals(50, pausedProgress.progressPercent());

        var afterRelease = finops.concurrencyStatus(ownerContext);
        assertEquals(2, afterRelease.activeRootTasks());
        assertEquals(1, afterRelease.waitingRootTasks());
        assertEquals(1, afterRelease.availableRootSlots());
        var fourthClaim = jobs.claim(RUNNER, List.of("untrusted:body-value"), 1, 120);
        assertEquals(1, fourthClaim.size());
        assertEquals(jobIds.get(3), fourthClaim.getFirst().jobId(),
                "releasing a slot must admit the fourth account task");

        assertTrue(finops.progress(memberContext, controlledLease.jobId()).isEmpty(),
                "an account-bound read must not expose another account's task");
        assertTrue(finops.events(memberContext, controlledLease.jobId(), 0, 100).isEmpty());
        assertTrue(jobs.find(memberExecutionContext, controlledLease.jobId()).isEmpty(),
                "execution-job find must not expose another account in the same organization");
        assertTrue(jobs.list(memberExecutionContext, null, 100, 0).isEmpty(),
                "execution-job list must remain account-bound inside one organization");
        Integer hiddenQueuePosition = transactions.execute(status -> {
            bindIdentity(jdbc, memberExecutionContext);
            return jdbc.sql("select elmos_mtf_queue_position(:job)")
                    .param("job", controlledLease.jobId())
                    .query(Integer.class)
                    .optional()
                    .orElse(null);
        });
        assertNull(hiddenQueuePosition,
                "the database queue projection must hide another account's job");
        RuntimeException directCancelRejected = assertThrows(
                RuntimeException.class,
                () -> transactions.execute(status -> {
                    bindIdentity(jdbc, memberExecutionContext);
                    return jdbc.sql("""
                            select elmos_mtf_request_execution_cancel(
                                :organization, :account, :job, :actor)
                            """)
                            .param("organization", ORGANIZATION)
                            .param("account", OWNER_ACCOUNT)
                            .param("job", controlledLease.jobId())
                            .param("actor", memberGrant.actorId())
                            .query(String.class)
                            .single();
                }));
        assertTrue(directCancelRejected.getMessage()
                        .contains("ELMOS_MTF_IDENTITY_CONTEXT_INVALID"),
                "the database cancel wrapper must reject a mismatched bound account");
        var crossAccountCancel = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> jobs.requestCancel(
                        new ExecutionJobPort.AuthenticatedContext(
                                ORGANIZATION,
                                MEMBER_ACCOUNT,
                                memberGrant.actorId(),
                                "request-member-cross-account-cancel"),
                        controlledLease.jobId()));
        assertEquals("ELMOS_EXECUTION_JOB_UNKNOWN", crossAccountCancel.code());
        assertFalse(jobs.find(ownerExecutionContext, controlledLease.jobId())
                .orElseThrow().cancelRequested(),
                "a cross-account cancel attempt must not mutate the owning account's task");
        var memberConcurrency = finops.concurrencyStatus(memberContext);
        assertEquals(0, memberConcurrency.activeRootTasks());
        assertEquals(0, memberConcurrency.waitingRootTasks());
        assertEquals(3, memberConcurrency.availableRootSlots());
        assertTrue(finops.progress(ownerContext, controlledLease.jobId()).isPresent(),
                "the owning account must retain access to its paused task");

        assertEquals(1L, operations.setFeatureRollout(
                new TaskFinopsOperationsPort.FeatureRolloutCommand(
                        ownerContext,
                        TaskFinopsFeatureRollout.Environment.DEVELOPMENT,
                        TaskFinopsFeatureRollout.Feature
                                .AUTHENTICATED_ACCOUNT_BINDING.name(),
                        TaskFinopsFeatureRollout.Stage.SHADOW,
                        0,
                        0,
                        "rollout-idempotency-1",
                        sha256("rollout:authenticated-account-binding:shadow"))));

        Instant lifecycleCutoff = Instant.now().minus(1, ChronoUnit.DAYS);
        assertEquals("lifecycle-mtf-delete-1", operations.requestLifecycle(
                new TaskFinopsOperationsPort.LifecycleRequestCommand(
                        ownerContext,
                        "lifecycle-mtf-delete-1",
                        TenantLifecyclePolicy.Operation.DELETE,
                        TenantLifecyclePolicy.ExportFormat.JSON,
                        lifecycleCutoff,
                        "lifecycle-idempotency-1",
                        sha256("lifecycle:delete:1"))));
        var lifecycle = operations.lifecycleStatus(
                ownerContext, "lifecycle-mtf-delete-1").orElseThrow();
        assertEquals("REQUESTED", lifecycle.state());
        assertEquals(TenantLifecyclePolicy.ProviderResult.NOT_RUN,
                lifecycle.providerResult());
        assertTrue(operations.lifecycleStatus(
                memberContext, "lifecycle-mtf-delete-1").isEmpty(),
                "lifecycle jobs must remain account isolated");

        Instant analyticsEnd = Instant.now().plusSeconds(60);
        var analyticsReceipt = new TaskFinopsAnalyticsService(operations).rebuild(
                new TaskFinopsAnalyticsService.RebuildCommand(
                        new TaskFinopsPort.AuthenticatedContext(
                                ORGANIZATION, OWNER_ACCOUNT, ownerGrant.actorId(),
                                "request-owner-analytics"),
                        "rebuild-mtf-1",
                        analyticsEnd.minus(1, ChronoUnit.DAYS),
                        analyticsEnd,
                        0,
                        "analytics-idempotency-1",
                        sha256("analytics:rebuild:1")));
        assertEquals(1, analyticsReceipt.generation());
        assertEquals(TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN,
                analyticsReceipt.externalEvidence());
        assertEquals(TaskFinopsAnalytics.ProviderOutcome.UNKNOWN,
                analyticsReceipt.providerOutcome());
        assertEquals(TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED,
                analyticsReceipt.productionCertification());
        assertEquals(0L, operations.currentProjectionGeneration(memberContext),
                "another account must not observe the projection head");
    }

    private static void bindIdentity(
            JdbcClient jdbc,
            ExecutionJobPort.AuthenticatedContext context
    ) {
        jdbc.sql("""
                select elmos_mtf_bind_identity(
                    cast(:organization as varchar), cast(:account as varchar),
                    cast(:actor as varchar), cast(:request as varchar))
                """)
                .param("organization", context.organizationId())
                .param("account", context.accountId())
                .param("actor", context.actorId())
                .param("request", context.requestId())
                .query()
                .singleRow();
    }

    private static void provisionCanonicalIdentities(
            JdbcOrganizationSelfServiceStore identities
    ) {
        assertEquals(OWNER_ACCOUNT, identities.resolveOidcAccount(
                OWNER_ACCOUNT,
                "https://issuer.integration.test",
                OWNER_OIDC_SUBJECT,
                "owner@integration.test",
                true,
                "Runtime Owner"));
        assertEquals(ORGANIZATION, identities.createOrganization(
                OWNER_ACCOUNT,
                ORGANIZATION,
                "MTF Runtime Integration",
                OWNER_ACTOR,
                "cn-north",
                sha256("owner-verified-subject")));

        assertEquals(MEMBER_ACCOUNT, identities.resolveOidcAccount(
                MEMBER_ACCOUNT,
                "https://issuer.integration.test",
                "oidc-subject-mtf-runtime-member",
                "member@integration.test",
                true,
                "Runtime Member"));
        String destination = sha256("member-destination");
        String token = sha256("member-invitation-token");
        assertEquals("invite-mtf-runtime-member", identities.createInvitation(
                "invite-mtf-runtime-member",
                ORGANIZATION,
                OWNER_ACCOUNT,
                OWNER_ACTOR,
                destination,
                "m***@integration.test",
                "MEMBER",
                token,
                900));
        assertEquals(ORGANIZATION, identities.acceptInvitation(
                token, destination, MEMBER_ACCOUNT, MEMBER_ACTOR));
    }

    private static void activateFiveJobOrganizationPlan(
            JdbcClient jdbc,
            TransactionTemplate transactions,
            String actorId
    ) {
        var billing = new JdbcSelfServiceBillingStore(jdbc, transactions);
        Instant periodStart = Instant.now().minus(1, ChronoUnit.MINUTES);
        Instant periodEnd = periodStart.plus(365, ChronoUnit.DAYS);
        assertTrue(billing.applyProviderEvent(
                ORGANIZATION,
                actorId,
                new SelfServiceBillingPort.ProviderEvent(
                        "evt-mtf-runtime-paid",
                        "invoice.paid",
                        "invoice-mtf-runtime-paid",
                        "provider-sub-mtf-runtime",
                        "provider-customer-mtf-runtime",
                        "invoice-mtf-runtime-paid",
                        new BigDecimal("129000"),
                        "CNY",
                        Instant.now(),
                        sha256("synthetic-provider-event"),
                        "APPLIED",
                        "provider-event-idempotency-mtf-runtime"),
                "elmos-pro-annual",
                "subscription-mtf-runtime",
                "quota-mtf-runtime",
                periodStart,
                periodEnd));
        assertEquals("elmos-pro-annual",
                billing.currentSubscription(ORGANIZATION, actorId).planId());
    }

    private static void provisionAttestedRunner(
            JdbcClient jdbc,
            TransactionTemplate transactions,
            String verifierActorId
    ) {
        var runners = new JdbcRunnerRegistrationStore(jdbc, transactions);
        var enrollment = runners.issueEnrollment(
                ORGANIZATION, "pool-mtf-runtime", verifierActorId, 900);
        String nodeToken = runnerNodeToken();
        assertEquals(RUNNER, runners.register(
                RUNNER,
                "pool-mtf-runtime",
                "integration-1.0",
                List.of(REGISTERED_CAPABILITY),
                8,
                enrollment.token(),
                sha256(nodeToken),
                true,
                true,
                true,
                true,
                "allowlist-mtf-runtime-v1").runnerNodeId());
        runners.verifyAttestation(RUNNER, verifierActorId);
        assertFalse(runners.heartbeat(RUNNER, nodeToken));
        assertEquals(REGISTERED_CAPABILITY, jdbc.sql("""
                select capabilities[1]
                  from runner_nodes
                 where runner_node_id = :runner
                """)
                .param("runner", RUNNER)
                .query(String.class)
                .single());
    }

    private static ExecutionJobPort.EnqueueCommand enqueueCommand(
            String jobId,
            String accountId,
            String actorId
    ) {
        return new ExecutionJobPort.EnqueueCommand(
                jobId,
                ORGANIZATION,
                accountId,
                actorId,
                ExecutionJobPort.BusinessLine.GENERATION,
                "integration-generation",
                "idempotency-" + jobId,
                sha256("request:" + jobId),
                Map.of("fixture", "synthetic", "jobId", jobId),
                REGISTERED_CAPABILITY,
                "registry.integration.test/elmos/generation@sha256:" + "a".repeat(64),
                (short) 100,
                3600,
                (short) 1,
                "request-" + jobId,
                "GENERATION",
                2);
    }

    private static ExecutionJobPort.HeartbeatCommand heartbeat(
            ExecutionJobPort.LeaseGrant lease,
            short progress,
            String cursor
    ) {
        return new ExecutionJobPort.HeartbeatCommand(
                lease.leaseId(),
                RUNNER,
                lease.leaseToken(),
                "generating",
                progress,
                Map.of("cursor", cursor),
                120);
    }

    private static String runnerNodeToken() {
        return "node-token-mtf-runtime-" + "n".repeat(40);
    }

    private static String sha256(String value) {
        try {
            return java.util.HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }
}
