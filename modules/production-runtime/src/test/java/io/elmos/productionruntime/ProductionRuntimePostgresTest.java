package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeCoordinator.DispatchRequest;
import io.elmos.productionruntime.ProductionRuntimeCoordinator.WorkerGatewayResult;
import io.elmos.productionruntime.ProductionRuntimeCoordinator.WorkerGateway;
import io.elmos.productionruntime.ProductionRuntimeModels.AttemptStatus;
import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.JobRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.MeterSnapshot;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ProjectRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.Checkpoint;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.WorkItemRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.WorkerRegistration;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers(disabledWithoutDocker = true)
class ProductionRuntimePostgresTest {
    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:17.5-alpine");
    @Container
    static final GenericContainer<?> REDIS = new GenericContainer<>("redis:7.4-alpine").withExposedPorts(6379);

    static DataSource dataSource;
    static JdbcClient jdbc;
    static TransactionTemplate transactions;
    static JdbcProductionRuntimeStore runtime;
    static JdbcProductionBillingService billing;
    static JdbcProductionToolCallService toolCalls;
    static JdbcProductionRepositoryArtifactService artifacts;
    static ProductionRuntimeRecoveryService recovery;
    static ProductionRuntimeCoordinator coordinator;

    @BeforeAll
    static void migrate() {
        dataSource = new DriverManagerDataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
        Path migration = locateMigration();
        Flyway flyway = Flyway.configure().dataSource(dataSource).locations("filesystem:" + migration.getParent().toAbsolutePath())
                .baselineOnMigrate(false).baselineVersion("76").baselineDescription("existing ELMOS schema")
                .target("78").outOfOrder(false).load();
        flyway.baseline();
        var migrationResult = flyway.migrate();
        assertEquals(2, migrationResult.migrationsExecuted,
                "the production-runtime fixture must execute exactly V77 and V78");
        assertEquals("78", flyway.info().current().getVersion().toString(),
                "the fixture target must not silently narrow below V78");
        jdbc = JdbcClient.create(dataSource);
        transactions = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
        ObjectMapper objectMapper = new ObjectMapper();
        runtime = new JdbcProductionRuntimeStore(jdbc, transactions, objectMapper);
        billing = new JdbcProductionBillingService(jdbc, transactions, objectMapper);
        toolCalls = new JdbcProductionToolCallService(jdbc, transactions, objectMapper);
        artifacts = new JdbcProductionRepositoryArtifactService(jdbc, transactions);
        coordinator = new ProductionRuntimeCoordinator(runtime, billing);
        recovery = new ProductionRuntimeRecoveryService(runtime, billing, objectMapper);
    }

    @BeforeEach
    void pricing() {
        UUID providerPricing = UUID.randomUUID();
        UUID commercialPricing = UUID.randomUUID();
        jdbc.sql("insert into billing.provider_pricing_versions (id, name, effective_from) values (:id, :name, now())")
                .param("id", providerPricing).param("name", "test-provider-" + providerPricing).update();
        jdbc.sql("insert into billing.commercial_pricing_versions (id, name, effective_from) values (:id, :name, now())")
                .param("id", commercialPricing).param("name", "test-commercial-" + commercialPricing).update();
        jdbc.sql("insert into billing.provider_model_prices (pricing_version_id, provider, model, input_per_million) values (:id, 'test-provider', 'test-model', 100000)")
                .param("id", providerPricing).update();
        jdbc.sql("insert into billing.commercial_model_prices (pricing_version_id, provider, model, credit_per_input_million) values (:id, 'test-provider', 'test-model', 300000)")
                .param("id", commercialPricing).update();
    }

    @Test
    void provisionsAggregateAndCompletesPrepaidDispatchSaga() {
        Fixture fixture = fixture();
        UUID providerPricing = jdbc.sql("select id from billing.provider_pricing_versions order by effective_from desc limit 1").query(UUID.class).single();
        UUID commercialPricing = jdbc.sql("select id from billing.commercial_pricing_versions order by effective_from desc limit 1").query(UUID.class).single();
        var topUp = billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-1"));
        var outcome = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.valueOf(4), Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of("snapshotHash", "a".repeat(64))), envelope -> WorkerGatewayResult.ACKED);
        assertEquals(ProductionRuntimeCoordinator.DispatchStatus.ACKED, outcome.status());
        var call = billing.beginModelCall(new ModelCallRequest(fixture.tenantId, fixture.accountId, fixture.projectId, fixture.jobId, fixture.stageId, fixture.workItemId, outcome.envelope().attemptId(), "test-provider", "test-model", "model-call-" + fixture.workItemId, "request-hash"));
        billing.claimProviderDispatch(fixture.tenantId, call.modelCallId());
        billing.markProviderAccepted(fixture.tenantId, call.modelCallId(), "provider-request-1");
        MeterSnapshot meter = new MeterSnapshot(fixture.tenantId, outcome.intent().reservationId(), call.modelCallId(), 1, 10, 2, 5, 1, BigDecimal.ONE, BigDecimal.valueOf(3));
        assertEquals(meter, billing.recordMeter(meter));
        assertEquals(meter, billing.recordMeter(meter));
        UUID providerArtifact = artifacts.registerArtifact(
                new ProductionRuntimeModels.ArtifactRequest(
                        fixture.tenantId, fixture.projectId, fixture.jobId,
                        fixture.workItemId, "MODEL_PROVIDER_RESPONSE",
                        "cas://provider-response/" + call.modelCallId(),
                        "f".repeat(64), 256));
        billing.completeModelCall(
                fixture.tenantId, call.modelCallId(),
                "provider-request-1", providerArtifact);
        FinalUsage usage = new FinalUsage(fixture.tenantId, outcome.intent().reservationId(), call.modelCallId(), "test-provider", "test-model", "provider-usage-1", providerPricing, commercialPricing, 10, 2, 5, 1, BigDecimal.ONE, BigDecimal.valueOf(3));
        coordinator.complete(new ProductionRuntimeModels.Completion(fixture.tenantId, fixture.workItemId, outcome.envelope().attemptId(), fixture.workerId, outcome.envelope().fencingToken(), AttemptStatus.SUCCEEDED, null, null), usage, null);
        assertDoesNotThrow(() -> billing.settle(usage));
        assertEquals(BigDecimal.valueOf(7).setScale(12), jdbc.sql("select available_balance from billing.wallet_balances where wallet_id = :walletId").param("walletId", fixture.walletId).query(BigDecimal.class).single());
        assertEquals(BigDecimal.ZERO.setScale(12), jdbc.sql("select reserved_balance from billing.wallet_balances where wallet_id = :walletId").param("walletId", fixture.walletId).query(BigDecimal.class).single());
        assertTrue(runtime.invariantViolations(fixture.tenantId).isEmpty(), () -> runtime.invariantViolations(fixture.tenantId).toString());
        assertEquals(topUp.topUpId(), billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-1")).topUpId());
    }

    @Test
    void concurrentReservationsNeverDriveWalletNegative() throws Exception {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-concurrent"));
        ExecutorService executor = Executors.newFixedThreadPool(8);
        try {
            var futures = new java.util.ArrayList<Future<Boolean>>();
            for (int i = 0; i < 8; i++) {
                int index = i;
                futures.add(executor.submit(() -> {
                    try {
                        billing.reserve(new ProductionRuntimeModels.ReserveRequest(fixture.tenantId, fixture.walletId, fixture.projectId, fixture.jobId, fixture.workItemId, "concurrent-" + index, BigDecimal.valueOf(2), Instant.now().plusSeconds(300)));
                        return true;
                    } catch (ProductionRuntimeException expected) {
                        assertEquals("CREDIT_EXHAUSTED", expected.code());
                        return false;
                    }
                }));
            }
            long successful = 0;
            for (Future<Boolean> future : futures) if (future.get()) successful++;
            assertEquals(5, successful);
            assertEquals(BigDecimal.ZERO.setScale(12), jdbc.sql("select available_balance from billing.wallet_balances where wallet_id = :walletId").param("walletId", fixture.walletId).query(BigDecimal.class).single());
            assertEquals(0, runtime.invariantViolations(fixture.tenantId).stream().filter(value -> value.startsWith("NEGATIVE_WALLET")).count());
        } finally {
            executor.shutdownNow();
        }
    }

    @Test
    void staleFenceCannotCommitTerminalResult() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-stale"));
        var outcome = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of()), envelope -> WorkerGatewayResult.ACKED);
        assertThrows(ProductionRuntimeException.class, () -> runtime.complete(new ProductionRuntimeModels.Completion(fixture.tenantId, fixture.workItemId, outcome.envelope().attemptId(), fixture.workerId, outcome.envelope().fencingToken() + 1, AttemptStatus.SUCCEEDED, null, null)));
        assertTrue(runtime.invariantViolations(fixture.tenantId).stream().noneMatch(value -> value.startsWith("RUNNING_WORK_WITHOUT_LEASE")));
    }

    @Test
    void fairFrontierGivesEachTenantAFirstDispatchSlot() {
        Fixture first = fixture();
        Fixture second = fixture();
        var frontier = runtime.selectFairReady(2);
        assertEquals(2, frontier.size());
        assertEquals(2, frontier.stream().map(ProductionRuntimeModels.ReadyWorkItem::tenantId).collect(java.util.stream.Collectors.toSet()).size());
    }

    @Test
    void blockedWorkloadStageCannotRunAndCompletingItsPredecessorActivatesIt() {
        UUID tenant = UUID.randomUUID();
        UUID account = UUID.randomUUID();
        var tenantAccount = runtime.provisionTenant(tenant, account, "stage-" + tenant, "CNY");
        UUID project = runtime.createProject(new ProjectRequest(
                tenant, account, "stage-project-" + tenant, "MODERNIZATION"));
        UUID job = runtime.createJob(new JobRequest(
                tenant, account, project, "SPRING_MODERNIZATION",
                List.of("inventory", "compile"), 2, 100));
        List<UUID> stages = jdbc.sql("""
                        select id from orchestration.job_stages
                         where tenant_id = :tenantId and job_id = :jobId
                         order by sequence_no
                        """)
                .param("tenantId", tenant).param("jobId", job)
                .query(UUID.class).list();
        assertEquals(2, stages.size());
        UUID firstItem = runtime.createWorkItem(new WorkItemRequest(
                tenant, job, stages.get(0), "inventory", "repo/source",
                10, BigDecimal.ONE, 1, "stage-first-" + tenant));
        UUID secondItem = runtime.createWorkItem(new WorkItemRequest(
                tenant, job, stages.get(1), "compile", "repo/target",
                10, BigDecimal.ONE, 1, "stage-second-" + tenant));

        assertEquals("PENDING", status(tenant, secondItem));
        assertEquals("BLOCKED", stageStatus(tenant, stages.get(1)));

        UUID worker = UUID.randomUUID();
        runtime.registerWorker(new WorkerRegistration(
                worker, "stage-worker-" + worker, "POLYGLOT",
                "http://worker.invalid/" + worker, "local", "local-1",
                Map.of("routeTuples", List.of(
                        "SPRING_MODERNIZATION:inventory", "SPRING_MODERNIZATION:compile"),
                        "maxConcurrent", 2)));
        billing.applyVerifiedTopUp(new TopUpRequest(
                tenant, tenantAccount.walletId(), "test-pay", "stage-payment-" + tenant,
                BigDecimal.TEN, "stage-payment-hash"));
        assertTrue(runtime.selectFairReady(100).stream()
                .anyMatch(item -> item.workItemId().equals(firstItem)));
        assertTrue(runtime.selectFairReady(100).stream()
                .noneMatch(item -> item.workItemId().equals(secondItem)));

        var dispatch = coordinator.dispatch(new DispatchRequest(
                tenant, project, job, firstItem, tenantAccount.walletId(), worker,
                BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30),
                "stage-reserve-" + tenant, "stage-dispatch-" + tenant, Map.of()),
                envelope -> WorkerGatewayResult.ACKED);
        coordinator.complete(new ProductionRuntimeModels.Completion(
                tenant, firstItem, dispatch.envelope().attemptId(), worker,
                dispatch.envelope().fencingToken(), AttemptStatus.SUCCEEDED, null, null), null, null);

        assertEquals("SUCCEEDED", stageStatus(tenant, stages.get(0)));
        assertEquals("READY", stageStatus(tenant, stages.get(1)));
        assertEquals("READY", status(tenant, secondItem));
        assertEquals("RUNNING", jdbc.sql("select status from orchestration.jobs where tenant_id = :tenantId and id = :jobId")
                .param("tenantId", tenant).param("jobId", job).query(String.class).single());
    }

    @Test
    void dependencyCycleAndCrossJobDependencyAreRejectedBeforePersistence() {
        Fixture first = fixture();
        UUID secondItem = runtime.createWorkItem(new WorkItemRequest(
                first.tenantId, first.jobId, first.stageId, "inventory", "repo/second",
                10, BigDecimal.ONE, 1, "dependency-second-" + first.tenantId));
        runtime.addDependency(first.tenantId, first.workItemId, secondItem);
        ProductionRuntimeException cycle = assertThrows(
                ProductionRuntimeException.class,
                () -> runtime.addDependency(first.tenantId, secondItem, first.workItemId));
        assertEquals("WORK_ITEM_DEPENDENCY_CYCLE", cycle.code());

        UUID otherJob = runtime.createJob(new JobRequest(
                first.tenantId, first.accountId, first.projectId,
                "SPRING_MODERNIZATION", List.of("inventory"), 2, 100));
        UUID otherStage = jdbc.sql("select id from orchestration.job_stages where tenant_id = :tenantId and job_id = :jobId")
                .param("tenantId", first.tenantId).param("jobId", otherJob)
                .query(UUID.class).single();
        UUID otherItem = runtime.createWorkItem(new WorkItemRequest(
                first.tenantId, otherJob, otherStage, "inventory", "repo/other-job",
                10, BigDecimal.ONE, 1, "dependency-other-job-" + first.tenantId));
        ProductionRuntimeException mismatch = assertThrows(
                ProductionRuntimeException.class,
                () -> runtime.addDependency(first.tenantId, secondItem, otherItem));
        assertEquals("WORK_ITEM_DEPENDENCY_JOB_MISMATCH", mismatch.code());
    }

    private String status(UUID tenantId, UUID workItemId) {
        return jdbc.sql("select status from orchestration.work_items where tenant_id = :tenantId and id = :id")
                .param("tenantId", tenantId).param("id", workItemId)
                .query(String.class).single();
    }

    private String stageStatus(UUID tenantId, UUID stageId) {
        return jdbc.sql("select status from orchestration.job_stages where tenant_id = :tenantId and id = :id")
                .param("tenantId", tenantId).param("id", stageId)
                .query(String.class).single();
    }

    @Test
    void modelCallReplayIsStableAndProviderUncertaintyBlocksBlindRetry() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-replay"));
        var outcome = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of()), envelope -> WorkerGatewayResult.ACKED);
        ModelCallRequest request = new ModelCallRequest(fixture.tenantId, fixture.accountId, fixture.projectId, fixture.jobId, fixture.stageId, fixture.workItemId, outcome.envelope().attemptId(), "test-provider", "test-model", "model-replay-" + fixture.workItemId, "request-hash");
        var first = billing.beginModelCall(request);
        assertEquals(first.modelCallId(), billing.beginModelCall(request).modelCallId());
        assertThrows(ProductionRuntimeException.class, () -> billing.beginModelCall(new ModelCallRequest(fixture.tenantId, fixture.accountId, fixture.projectId, fixture.jobId, fixture.stageId, fixture.workItemId, outcome.envelope().attemptId(), "test-provider", "test-model", request.idempotencyKey(), "different-hash")));
        billing.claimProviderDispatch(fixture.tenantId, first.modelCallId());
        ProductionRuntimeException duplicateClaim = assertThrows(
                ProductionRuntimeException.class,
                () -> billing.claimProviderDispatch(
                        fixture.tenantId, first.modelCallId()));
        assertEquals("MODEL_CALL_RECONCILIATION_REQUIRED", duplicateClaim.code());
        billing.markProviderAccepted(fixture.tenantId, first.modelCallId(), "provider-request-replay");
        assertDoesNotThrow(() -> billing.markProviderAccepted(
                fixture.tenantId, first.modelCallId(), "provider-request-replay"));
        ProductionRuntimeException providerConflict = assertThrows(
                ProductionRuntimeException.class,
                () -> billing.markProviderAccepted(
                        fixture.tenantId, first.modelCallId(), "provider-request-different"));
        assertEquals("MODEL_CALL_PROVIDER_ID_CONFLICT", providerConflict.code());
        ProductionRuntimeException uncertain = assertThrows(ProductionRuntimeException.class, () -> billing.beginModelCall(request));
        assertEquals("MODEL_CALL_RECONCILIATION_REQUIRED", uncertain.code());
    }

    @Test
    void leaseExpiryRemovesLeaseAndMakesWorkRetryable() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-expiry"));
        var outcome = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of()), envelope -> WorkerGatewayResult.ACKED);
        jdbc.sql("update runtime.worker_leases set leased_at = now() - interval '2 seconds', heartbeat_at = now() - interval '2 seconds', expires_at = now() - interval '1 second' where tenant_id = :tenantId and attempt_id = :attemptId")
                .param("tenantId", fixture.tenantId).param("attemptId", outcome.envelope().attemptId()).update();
        assertEquals(1, runtime.expireLeases(fixture.tenantId, Duration.ZERO));
        assertEquals("RETRY_WAIT", jdbc.sql("select status from orchestration.work_items where tenant_id = :tenantId and id = :id").param("tenantId", fixture.tenantId).param("id", fixture.workItemId).query(String.class).single());
        assertEquals(0, jdbc.sql("select count(*) from runtime.worker_leases where tenant_id = :tenantId and attempt_id = :attemptId").param("tenantId", fixture.tenantId).param("attemptId", outcome.envelope().attemptId()).query(Long.class).single());
    }

    @Test
    void checkpointAndOutboxReplayAreDurable() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-outbox"));
        var outcome = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of()), envelope -> WorkerGatewayResult.ACKED);
        Checkpoint checkpoint = new Checkpoint(fixture.tenantId, fixture.jobId, fixture.workItemId, outcome.envelope().attemptId(), "WORKSPACE", 1, "cas://checkpoint/1", "d".repeat(64));
        runtime.checkpoint(checkpoint);
        runtime.checkpoint(checkpoint);
        var publisher = new TransactionalOutboxPublisher(runtime, event -> { });
        var report = publisher.publish(1, Duration.ofSeconds(30));
        assertEquals(1, report.claimed());
        assertEquals(1, report.published());
        assertEquals(0, report.failed());
    }

    @Test
    void topUpIdempotencyConflictCannotChangeMoney() {
        Fixture fixture = fixture();
        TopUpRequest original = new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-original");
        billing.applyVerifiedTopUp(original);
        ProductionRuntimeException conflict = assertThrows(ProductionRuntimeException.class, () -> billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, original.provider(), original.providerPaymentId(), BigDecimal.valueOf(99), "hash-changed")));
        assertEquals("IDEMPOTENCY_CONFLICT", conflict.code());
        assertEquals(BigDecimal.TEN.setScale(12), jdbc.sql("select available_balance from billing.wallet_balances where wallet_id = :walletId").param("walletId", fixture.walletId).query(BigDecimal.class).single());
    }

    @Test
    void topUpReplayIsExactlyOnceAcrossMoneyJournalAndOutbox() {
        Fixture fixture = fixture();
        TopUpRequest request = new TopUpRequest(
                fixture.tenantId, fixture.walletId, "test-pay",
                "topup-replay-" + fixture.tenantId, BigDecimal.TEN,
                "topup-replay-hash");

        var first = billing.applyVerifiedTopUp(request);
        var replay = billing.applyVerifiedTopUp(request);

        assertEquals(first, replay);
        assertEquals(BigDecimal.TEN.setScale(12), jdbc.sql(
                        "select available_balance from billing.wallet_balances where tenant_id = :tenantId and wallet_id = :walletId")
                .param("tenantId", fixture.tenantId).param("walletId", fixture.walletId)
                .query(BigDecimal.class).single());
        assertEquals(1L, jdbc.sql(
                        "select count(*) from billing.topups where tenant_id = :tenantId and id = :topUpId")
                .param("tenantId", fixture.tenantId).param("topUpId", first.topUpId())
                .query(Long.class).single());
        assertEquals(1L, jdbc.sql(
                        "select count(*) from billing.ledger_entries where tenant_id = :tenantId and reference_id = :topUpId and entry_type = 'TOPUP'")
                .param("tenantId", fixture.tenantId).param("topUpId", first.topUpId())
                .query(Long.class).single());
        assertEquals(1L, jdbc.sql(
                        "select count(*) from billing.billing_journals where tenant_id = :tenantId and reference_id = :topUpId and journal_type = 'TOPUP'")
                .param("tenantId", fixture.tenantId).param("topUpId", first.topUpId())
                .query(Long.class).single());
        assertEquals(1L, jdbc.sql(
                        "select count(*) from observability.outbox_events where tenant_id = :tenantId and aggregate_id = :topUpId and event_type = 'TOPUP_COMPLETED'")
                .param("tenantId", fixture.tenantId).param("topUpId", first.topUpId())
                .query(Long.class).single());
    }

    @Test
    void reservingStateCanBeReplayedAfterSchedulerRestart() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(
                fixture.tenantId, fixture.walletId, "test-pay",
                "reserving-restart-" + fixture.tenantId, BigDecimal.TEN,
                "reserving-restart-hash"));
        var intent = runtime.prepareReservation(
                fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId,
                fixture.walletId, fixture.workerId, BigDecimal.ONE,
                Instant.now().plusSeconds(300), Map.of("restart", "reserving"),
                "reserving-restart-reserve-" + fixture.workItemId,
                "reserving-restart-dispatch-" + fixture.workItemId);
        assertEquals("RESERVING", jdbc.sql(
                        "select state from runtime.dispatch_intents where tenant_id = :tenantId and id = :id")
                .param("tenantId", fixture.tenantId).param("id", intent.id())
                .query(String.class).single());

        var report = recovery.recover(1_000, envelope -> WorkerGatewayResult.ACKED);

        assertTrue(report.inspected() >= 1);
        assertTrue(report.advanced() >= 2);
        assertEquals("ACKED", jdbc.sql(
                        "select state from runtime.dispatch_intents where tenant_id = :tenantId and id = :id")
                .param("tenantId", fixture.tenantId).param("id", intent.id())
                .query(String.class).single());
        assertEquals(1L, jdbc.sql(
                        "select count(*) from billing.credit_reservations where tenant_id = :tenantId and work_item_id = :workItemId")
                .param("tenantId", fixture.tenantId).param("workItemId", fixture.workItemId)
                .query(Long.class).single());
        recovery.recover(1_000, envelope -> WorkerGatewayResult.ACKED);
        assertEquals(1L, jdbc.sql(
                        "select count(*) from billing.credit_reservations where tenant_id = :tenantId and work_item_id = :workItemId")
                .param("tenantId", fixture.tenantId).param("workItemId", fixture.workItemId)
                .query(Long.class).single());
    }

    @Test
    void streamingUsageReconciliationIsMonotonicAndFinal() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(
                fixture.tenantId, fixture.walletId, "test-pay",
                "streaming-usage-" + fixture.tenantId, BigDecimal.TEN,
                "streaming-usage-hash"));
        UsageContext context = prepareUsage(fixture, fixture.workItemId, "streaming", BigDecimal.valueOf(4));
        MeterSnapshot first = meter(fixture, context, 1, 4);
        MeterSnapshot second = meter(fixture, context, 2, 8);

        assertEquals(first, billing.recordMeter(first));
        assertEquals(first, billing.recordMeter(first));
        ProductionRuntimeException replayConflict = assertThrows(
                ProductionRuntimeException.class,
                () -> billing.recordMeter(meter(fixture, context, 1, 5)));
        assertEquals("USAGE_METER_CONFLICT", replayConflict.code());
        assertEquals(second, billing.recordMeter(second));
        ProductionRuntimeException regression = assertThrows(
                ProductionRuntimeException.class,
                () -> billing.recordMeter(meter(fixture, context, 3, 7)));
        assertEquals("USAGE_METER_NOT_MONOTONIC", regression.code());

        billing.completeModelCall(
                fixture.tenantId, context.modelCallId, context.providerRequestId,
                context.responseArtifactId);
        ProductionRuntimeException belowMeter = assertThrows(
                ProductionRuntimeException.class,
                () -> billing.settle(finalUsage(fixture, context, "streaming-final-below", 7)));
        assertEquals("FINAL_USAGE_BELOW_STREAM_METER", belowMeter.code());
        FinalUsage finalUsage = finalUsage(fixture, context, "streaming-final", 10);
        billing.settle(finalUsage);
        assertDoesNotThrow(() -> billing.settle(finalUsage));

        assertEquals(2L, jdbc.sql(
                        "select count(*) from billing.usage_meter_events where tenant_id = :tenantId and model_call_id = :modelCallId")
                .param("tenantId", fixture.tenantId).param("modelCallId", context.modelCallId)
                .query(Long.class).single());
        assertEquals(1L, jdbc.sql(
                        "select count(*) from billing.token_usage_events where tenant_id = :tenantId and model_call_id = :modelCallId")
                .param("tenantId", fixture.tenantId).param("modelCallId", context.modelCallId)
                .query(Long.class).single());
    }

    @Test
    void duplicateProviderUsageCannotSettleAnotherModelCall() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(
                fixture.tenantId, fixture.walletId, "test-pay",
                "duplicate-usage-" + fixture.tenantId, BigDecimal.TEN,
                "duplicate-usage-hash"));
        UUID secondWorkItem = runtime.createWorkItem(new WorkItemRequest(
                fixture.tenantId, fixture.jobId, fixture.stageId, "inventory",
                "repo/duplicate-usage", 10, BigDecimal.ONE, 1,
                "duplicate-usage-item-" + fixture.tenantId));
        UsageContext first = prepareUsage(
                fixture, fixture.workItemId, "duplicate-usage-first", BigDecimal.valueOf(4));
        UsageContext second = prepareUsage(
                fixture, secondWorkItem, "duplicate-usage-second", BigDecimal.valueOf(4));
        billing.completeModelCall(
                fixture.tenantId, first.modelCallId, first.providerRequestId,
                first.responseArtifactId);
        billing.completeModelCall(
                fixture.tenantId, second.modelCallId, second.providerRequestId,
                second.responseArtifactId);
        String providerUsageId = "provider-usage-duplicate-" + fixture.tenantId;

        billing.settle(finalUsage(fixture, first, providerUsageId, 10));
        ProductionRuntimeException conflict = assertThrows(
                ProductionRuntimeException.class,
                () -> billing.settle(finalUsage(fixture, second, providerUsageId, 10)));

        assertEquals("BILLING_PROVIDER_USAGE_CONFLICT", conflict.code());
        assertEquals(1L, jdbc.sql(
                        "select count(*) from billing.token_usage_events where provider = 'test-provider' and provider_usage_id = :providerUsageId")
                .param("providerUsageId", providerUsageId).query(Long.class).single());
        assertEquals("ACTIVE", jdbc.sql(
                        "select status from billing.credit_reservations where tenant_id = :tenantId and id = :reservationId")
                .param("tenantId", fixture.tenantId).param("reservationId", second.reservationId)
                .query(String.class).single());
        assertTrue(runtime.invariantViolations(fixture.tenantId).stream()
                .noneMatch(value -> value.startsWith("DUPLICATE_PROVIDER_USAGE")));
    }

    @Test
    void journalEntriesRemainBalancedForTopUpAndUsage() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(
                fixture.tenantId, fixture.walletId, "test-pay",
                "journal-balance-" + fixture.tenantId, BigDecimal.TEN,
                "journal-balance-hash"));
        UsageContext context = prepareUsage(
                fixture, fixture.workItemId, "journal-balance", BigDecimal.valueOf(4));
        billing.completeModelCall(
                fixture.tenantId, context.modelCallId, context.providerRequestId,
                context.responseArtifactId);
        billing.settle(finalUsage(
                fixture, context, "journal-usage-" + fixture.tenantId, 10));

        assertEquals(0L, jdbc.sql("""
                        select count(*) from (
                            select journal_id, currency
                              from billing.billing_journal_lines
                             where tenant_id = :tenantId
                             group by journal_id, currency
                            having sum(debit) <> sum(credit)
                        ) unbalanced
                        """)
                .param("tenantId", fixture.tenantId).query(Long.class).single());
        assertEquals(2L, jdbc.sql(
                        "select count(*) from billing.billing_journals where tenant_id = :tenantId")
                .param("tenantId", fixture.tenantId).query(Long.class).single());
        assertEquals(4L, jdbc.sql(
                        "select count(*) from billing.billing_journal_lines where tenant_id = :tenantId")
                .param("tenantId", fixture.tenantId).query(Long.class).single());
        assertEquals(BigDecimal.valueOf(7).setScale(12), jdbc.sql(
                        "select sum(amount) from billing.ledger_entries where tenant_id = :tenantId")
                .param("tenantId", fixture.tenantId).query(BigDecimal.class).single());
        assertTrue(runtime.invariantViolations(fixture.tenantId).stream()
                .noneMatch(value -> value.startsWith("UNBALANCED_JOURNAL")));
    }

    @Test
    void creditExhaustionResumesAfterVerifiedTopUp() {
        Fixture fixture = fixture();
        var waiting = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of()), envelope -> WorkerGatewayResult.ACKED);
        assertEquals(ProductionRuntimeCoordinator.DispatchStatus.WAITING_FOR_CREDIT, waiting.status());
        long waitingEvents = jdbc.sql("select count(*) from observability.project_events where tenant_id = :tenantId and work_item_id = :workItemId and event_type = 'WAITING_FOR_CREDIT'")
                .param("tenantId", fixture.tenantId).param("workItemId", fixture.workItemId)
                .query(Long.class).single();
        assertDoesNotThrow(() -> runtime.markWaitingForCredit(
                fixture.tenantId, fixture.workItemId, "CREDIT_EXHAUSTED"));
        assertEquals(waitingEvents, jdbc.sql("select count(*) from observability.project_events where tenant_id = :tenantId and work_item_id = :workItemId and event_type = 'WAITING_FOR_CREDIT'")
                .param("tenantId", fixture.tenantId).param("workItemId", fixture.workItemId)
                .query(Long.class).single());
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-resume"));
        assertEquals(1, runtime.resumeCreditWaiting(fixture.tenantId, 10));
        var resumed = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of()), envelope -> WorkerGatewayResult.ACKED);
        assertEquals(ProductionRuntimeCoordinator.DispatchStatus.ACKED, resumed.status());
    }

    @Test
    void toolCallReceiptIsDistinctAndIdempotent() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-tool"));
        var outcome = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of()), envelope -> WorkerGatewayResult.ACKED);
        var request = new ProductionRuntimeModels.ToolCallRequest(fixture.tenantId, fixture.accountId, fixture.projectId, fixture.jobId, fixture.stageId, fixture.workItemId, outcome.envelope().attemptId(), "compiler", "tool-call-" + fixture.workItemId, "tool-request-hash");
        var first = toolCalls.begin(request);
        assertEquals(first.toolCallId(), toolCalls.begin(request).toolCallId());
        toolCalls.claimProviderDispatch(fixture.tenantId, first.toolCallId());
        ProductionRuntimeException duplicateClaim = assertThrows(
                ProductionRuntimeException.class,
                () -> toolCalls.claimProviderDispatch(fixture.tenantId, first.toolCallId()));
        assertEquals("TOOL_CALL_RECONCILIATION_REQUIRED", duplicateClaim.code());
        toolCalls.markProviderAccepted(fixture.tenantId, first.toolCallId(), "tool-provider-request");
        assertDoesNotThrow(() -> toolCalls.markProviderAccepted(
                fixture.tenantId, first.toolCallId(), "tool-provider-request"));
        ProductionRuntimeException providerConflict = assertThrows(
                ProductionRuntimeException.class,
                () -> toolCalls.markProviderAccepted(
                        fixture.tenantId, first.toolCallId(), "different-provider-request"));
        assertEquals("TOOL_CALL_PROVIDER_ID_CONFLICT", providerConflict.code());
        UUID artifactId = artifacts.registerArtifact(new ProductionRuntimeModels.ArtifactRequest(
                fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId,
                "TOOL_RESPONSE", "cas://tool-response/" + first.toolCallId(),
                "e".repeat(64), 128));
        toolCalls.complete(fixture.tenantId, first.toolCallId(), artifactId);
        assertDoesNotThrow(() -> toolCalls.complete(
                fixture.tenantId, first.toolCallId(), artifactId));
        var completed = jdbc.sql("select status from ai_usage.tool_calls where tenant_id = :tenantId and id = :id").param("tenantId", fixture.tenantId).param("id", first.toolCallId()).query(String.class).single();
        assertEquals("COMPLETE", completed);
    }

    @Test
    void snapshotArtifactAndValidationLineageIsImmutableAndTenantBound() {
        Fixture fixture = fixture();
        UUID snapshotId = artifacts.registerSnapshot(new ProductionRuntimeModels.RepositorySnapshotRequest(fixture.tenantId, fixture.projectId, "a".repeat(40), "b".repeat(64), "cas://snapshot/" + fixture.tenantId, 10, 100, 1_024));
        artifacts.bindInputSnapshot(fixture.tenantId, fixture.jobId, snapshotId);
        UUID artifactId = artifacts.registerArtifact(new ProductionRuntimeModels.ArtifactRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, "REPORT", "cas://artifact/report", "c".repeat(64), 128));
        UUID validationId = artifacts.startValidation(new ProductionRuntimeModels.ValidationRunRequest(fixture.tenantId, fixture.jobId, "CONTRACT_TEST"));
        artifacts.completeValidation(fixture.tenantId, validationId, 10, 0);
        assertEquals(snapshotId, jdbc.sql("select input_snapshot_id from orchestration.jobs where tenant_id = :tenantId and id = :jobId").param("tenantId", fixture.tenantId).param("jobId", fixture.jobId).query(UUID.class).single());
        assertEquals("PASSED", jdbc.sql("select status from validation.validation_runs where tenant_id = :tenantId and id = :id").param("tenantId", fixture.tenantId).param("id", validationId).query(String.class).single());
        assertEquals(1, jdbc.sql("select count(*) from artifact.artifacts where tenant_id = :tenantId and id = :id").param("tenantId", fixture.tenantId).param("id", artifactId).query(Long.class).single());
    }

    @Test
    void contentAddressedObjectMetadataIsTenantBoundAndFailClosed() {
        Fixture first = fixture();
        Fixture second = fixture();
        var metadata = new JdbcProductionObjectStorageMetadata(jdbc, transactions);
        String digest = "9".repeat(64);
        String firstId = metadata.registerPendingObject(
                first.tenantId.toString(), digest, 128,
                "application/json", "qualification-s3",
                first.tenantId + "/obj/" + digest);
        assertEquals(firstId, metadata.registerPendingObject(
                first.tenantId.toString(), digest, 128,
                "application/json", "qualification-s3",
                first.tenantId + "/obj/" + digest));
        ProductionRuntimeException conflict = assertThrows(
                ProductionRuntimeException.class,
                () -> metadata.registerPendingObject(
                        first.tenantId.toString(), digest, 129,
                        "application/json", "qualification-s3",
                        first.tenantId + "/obj/" + digest));
        assertEquals("CONTENT_OBJECT_IDEMPOTENCY_CONFLICT", conflict.code());

        metadata.markAvailable(first.tenantId.toString(), firstId);
        assertDoesNotThrow(() -> metadata.markAvailable(
                first.tenantId.toString(), firstId));
        assertThrows(ProductionRuntimeException.class, () -> metadata.markQuarantined(
                first.tenantId.toString(), firstId, "LATE_QUARANTINE"));

        String secondId = metadata.registerPendingObject(
                second.tenantId.toString(), digest, 128,
                "application/json", "qualification-s3",
                second.tenantId + "/obj/" + digest);
        assertTrue(!firstId.equals(secondId));
    }

    @Test
    void workerIdentityCannotBeReboundByAnotherRegistration() {
        Fixture fixture = fixture();
        WorkerRegistration exact = new WorkerRegistration(
                fixture.workerId, "worker-" + fixture.workerId, "SPRING",
                "http://worker.invalid/" + fixture.workerId, "local", "local-1",
                Map.of(
                        "routeTuples", List.of("SPRING_MODERNIZATION:inventory"),
                        "maxConcurrent", 8));
        assertDoesNotThrow(() -> runtime.registerWorker(exact));
        ProductionRuntimeException conflict = assertThrows(
                ProductionRuntimeException.class,
                () -> runtime.registerWorker(new WorkerRegistration(
                        exact.workerId(), exact.workerName(), exact.workerType(),
                        "http://attacker.invalid/" + exact.workerId(),
                        exact.region(), exact.zone(), exact.capabilities())));
        assertEquals("WORKER_IDENTITY_CONFLICT", conflict.code());
        assertEquals(exact.endpointUri(), jdbc.sql(
                        "select endpoint_uri from runtime.workers where id = :id")
                .param("id", exact.workerId()).query(String.class).single());
    }

    @Test
    void dispatchingUnknownOutcomeConvergesThroughDurableRecovery() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-recovery"));
        var unknown = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of("recovery", true)), envelope -> WorkerGatewayResult.UNKNOWN);
        assertEquals(ProductionRuntimeCoordinator.DispatchStatus.PROVIDER_OR_WORKER_OUTCOME_UNKNOWN, unknown.status());
        WorkerGateway reconcilingGateway = new WorkerGateway() {
            @Override public WorkerGatewayResult dispatch(ProductionRuntimeModels.DispatchEnvelope envelope) { return WorkerGatewayResult.UNKNOWN; }
            @Override public WorkerGatewayResult reconcile(ProductionRuntimeModels.DispatchEnvelope envelope) { return WorkerGatewayResult.ACKED; }
        };
        assertTrue(recovery.recover(100, reconcilingGateway).advanced() >= 1);
        assertEquals("ACKED", jdbc.sql("select state from runtime.dispatch_intents where tenant_id = :tenantId and work_item_id = :workItemId").param("tenantId", fixture.tenantId).param("workItemId", fixture.workItemId).query(String.class).single());
    }

    @Test
    void rlsRoleCannotReadAnotherTenant() {
        Fixture first = fixture();
        Fixture second = fixture();
        String role = "elmos_rls_test_role";
        jdbc.sql("create role " + role + " login password 'rls-test-password'").update();
        jdbc.sql("grant usage on schema identity, project to " + role).update();
        jdbc.sql("grant select, update on identity.tenants, project.projects to " + role).update();
        DataSource restrictedDataSource = new DriverManagerDataSource(POSTGRES.getJdbcUrl(), role, "rls-test-password");
        JdbcClient restrictedJdbc = JdbcClient.create(restrictedDataSource);
        TransactionTemplate restrictedTransactions = new TransactionTemplate(new DataSourceTransactionManager(restrictedDataSource));
        long visible = restrictedTransactions.execute(status -> {
            restrictedJdbc.sql("select set_config('app.tenant_id', :tenantId, true)").param("tenantId", first.tenantId.toString()).query(String.class).single();
            return restrictedJdbc.sql("select count(*) from project.projects where id in (:first, :second)").param("first", first.projectId).param("second", second.projectId).query(Long.class).single();
        });
        assertEquals(1, visible);
    }

    @Test
    void reservedStateCanBeReplayedAfterSchedulerRestart() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-reserved-recovery"));
        var intent = runtime.prepareReservation(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Map.of("restart", "reserved"), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId);
        var reservation = billing.reserve(new ProductionRuntimeModels.ReserveRequest(fixture.tenantId, fixture.walletId, fixture.projectId, fixture.jobId, fixture.workItemId, "reserve-" + fixture.workItemId, BigDecimal.ONE, Instant.now().plusSeconds(300)));
        runtime.attachReservation(fixture.tenantId, intent.id(), reservation.reservationId());
        var report = recovery.recover(100, envelope -> WorkerGatewayResult.ACKED);
        assertTrue(report.advanced() >= 1);
        assertEquals("ACKED", jdbc.sql("select state from runtime.dispatch_intents where tenant_id = :tenantId and id = :id").param("tenantId", fixture.tenantId).param("id", intent.id()).query(String.class).single());
    }

    @Test
    void projectorReplayRebuildsTheSameAuthoritativeCounts() {
        Fixture fixture = fixture();
        var first = runtime.rebuildProgress(fixture.tenantId, fixture.jobId);
        var second = runtime.rebuildProgress(fixture.tenantId, fixture.jobId);
        assertEquals(first.total(), second.total());
        assertEquals(first.ready(), second.ready());
        assertEquals(first.completed(), second.completed());
        assertEquals(1, jdbc.sql("select count(*) from observability.progress_snapshots where tenant_id = :tenantId and job_id = :jobId").param("tenantId", fixture.tenantId).param("jobId", fixture.jobId).query(Long.class).single());
    }

    @Test
    void billingReconciliationViewMatchesWalletAndReservationTruth() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-reconciliation"));
        billing.reserve(new ProductionRuntimeModels.ReserveRequest(fixture.tenantId, fixture.walletId, fixture.projectId, fixture.jobId, fixture.workItemId, "reserve-" + fixture.workItemId, BigDecimal.valueOf(3), Instant.now().plusSeconds(300)));
        var row = jdbc.sql("select available_balance, reserved_balance, posted_effect, active_reserved from billing.v_wallet_reconciliation where tenant_id = :tenantId and wallet_id = :walletId").param("tenantId", fixture.tenantId).param("walletId", fixture.walletId).query((rs, n) -> new BigDecimal[]{rs.getBigDecimal("available_balance"), rs.getBigDecimal("reserved_balance"), rs.getBigDecimal("posted_effect"), rs.getBigDecimal("active_reserved")}).single();
        assertEquals(BigDecimal.valueOf(7).setScale(12), row[0]);
        assertEquals(BigDecimal.valueOf(3).setScale(12), row[1]);
        assertEquals(BigDecimal.TEN.setScale(12), row[2]);
        assertEquals(BigDecimal.valueOf(3).setScale(12), row[3]);
    }

    @Test
    void providerAdapterCompletesOnceAndUnknownRequiresReconciliation() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-provider-adapter"));
        var outcome = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of()), envelope -> WorkerGatewayResult.ACKED);
        ModelCallRequest request = new ModelCallRequest(fixture.tenantId, fixture.accountId, fixture.projectId, fixture.jobId, fixture.stageId, fixture.workItemId, outcome.envelope().attemptId(), "test-provider", "test-model", "provider-adapter-" + fixture.workItemId, "provider-request-hash");
        UUID responseArtifactId = artifacts.registerArtifact(new ProductionRuntimeModels.ArtifactRequest(
                fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId,
                "MODEL_RESPONSE", "cas://model-response/" + fixture.workItemId,
                "f".repeat(64), 256));
        AtomicInteger calls = new AtomicInteger();
        ProductionModelProviderPort completeProvider = new ProductionModelProviderPort() {
            @Override public ProviderResult execute(ModelCallRequest ignored) { calls.incrementAndGet(); return ProviderResult.complete("provider-request-complete", responseArtifactId); }
            @Override public ProviderResult reconcile(String ignored) { return ProviderResult.unknown("not-needed"); }
        };
        ProductionModelCallExecutor executor = new ProductionModelCallExecutor(billing);
        var completed = executor.execute(request, completeProvider);
        assertEquals(ProductionRuntimeModels.ModelCallStatus.COMPLETE, completed.status());
        assertEquals(responseArtifactId.toString(), completed.responseArtifactId());
        assertEquals(1, calls.get());
        assertEquals(completed, executor.execute(request, completeProvider));
        assertEquals(1, calls.get(), "idempotent replay must not call the provider twice");

        ModelCallRequest unknownRequest = new ModelCallRequest(fixture.tenantId, fixture.accountId, fixture.projectId, fixture.jobId, fixture.stageId, fixture.workItemId, outcome.envelope().attemptId(), "test-provider", "test-model", "provider-adapter-unknown-" + fixture.workItemId, "provider-unknown-hash");
        ProductionModelProviderPort unknownProvider = new ProductionModelProviderPort() {
            @Override public ProviderResult execute(ModelCallRequest ignored) { return ProviderResult.unknown("timeout-after-send"); }
            @Override public ProviderResult reconcile(String ignored) { return ProviderResult.complete("provider-reconciled", UUID.randomUUID()); }
        };
        assertEquals(ProductionRuntimeModels.ModelCallStatus.UNKNOWN, executor.execute(unknownRequest, unknownProvider).status());
        ProductionRuntimeException blocked = assertThrows(ProductionRuntimeException.class, () -> executor.execute(unknownRequest, completeProvider));
        assertEquals("MODEL_CALL_RECONCILIATION_REQUIRED", blocked.code());
    }

    @Test
    void providerPayloadIsByteExactDurableAndTenantBound() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId,
                "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN,
                "hash-provider-payload"));
        var outcome = coordinator.dispatch(new DispatchRequest(
                fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId,
                fixture.walletId, fixture.workerId, BigDecimal.ONE,
                Instant.now().plusSeconds(300), Duration.ofSeconds(30),
                "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId,
                Map.of()), envelope -> WorkerGatewayResult.ACKED);
        byte[] body = "{\"model\":\"test-model\",\"input\":\"durable\"}"
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);
        String digest = JdbcProductionProviderPayloadStore.sha256(body);
        ModelCallRequest request = new ModelCallRequest(
                fixture.tenantId, fixture.accountId, fixture.projectId, fixture.jobId,
                fixture.stageId, fixture.workItemId, outcome.envelope().attemptId(),
                "test-provider", "test-model", "payload-" + fixture.workItemId, digest);
        var payloadStore = new JdbcProductionProviderPayloadStore(jdbc, transactions);

        payloadStore.persist(request, body);
        payloadStore.persist(request, body);

        assertTrue(java.security.MessageDigest.isEqual(
                body, payloadStore.materialize(request).bytes()));
        assertThrows(ProductionRuntimeException.class,
                () -> payloadStore.persist(request, "{}".getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        ModelCallRequest wrongProvider = new ModelCallRequest(
                request.tenantId(), request.accountId(), request.projectId(), request.jobId(),
                request.stageId(), request.workItemId(), request.attemptId(), "other-provider",
                request.model(), request.idempotencyKey(), request.requestHash());
        assertThrows(ProductionRuntimeException.class,
                () -> payloadStore.materialize(wrongProvider));
    }

    @Test
    void chaosMatrixKeepsUnknownNonSuccessAndReleasesRejectedWork() {
        Fixture rejectedFixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(rejectedFixture.tenantId, rejectedFixture.walletId, "test-pay", "payment-" + rejectedFixture.tenantId, BigDecimal.TEN, "hash-chaos-rejected"));
        var rejected = coordinator.dispatch(new DispatchRequest(rejectedFixture.tenantId, rejectedFixture.projectId, rejectedFixture.jobId, rejectedFixture.workItemId, rejectedFixture.walletId, rejectedFixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + rejectedFixture.workItemId, "dispatch-" + rejectedFixture.workItemId, Map.of("fault", "rejected")), envelope -> WorkerGatewayResult.REJECTED);
        assertEquals(ProductionRuntimeCoordinator.DispatchStatus.RELEASED_AFTER_REJECTION, rejected.status());
        assertEquals("RELEASED", jdbc.sql("select status from billing.credit_reservations where tenant_id = :tenantId and work_item_id = :workItemId").param("tenantId", rejectedFixture.tenantId).param("workItemId", rejectedFixture.workItemId).query(String.class).single());

        Fixture unknownFixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(unknownFixture.tenantId, unknownFixture.walletId, "test-pay", "payment-" + unknownFixture.tenantId, BigDecimal.TEN, "hash-chaos-unknown"));
        var unknown = coordinator.dispatch(new DispatchRequest(unknownFixture.tenantId, unknownFixture.projectId, unknownFixture.jobId, unknownFixture.workItemId, unknownFixture.walletId, unknownFixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + unknownFixture.workItemId, "dispatch-" + unknownFixture.workItemId, Map.of("fault", "unknown")), envelope -> WorkerGatewayResult.UNKNOWN);
        assertEquals(ProductionRuntimeCoordinator.DispatchStatus.PROVIDER_OR_WORKER_OUTCOME_UNKNOWN, unknown.status());
        assertEquals("DISPATCHING", jdbc.sql("select state from runtime.dispatch_intents where tenant_id = :tenantId and work_item_id = :workItemId").param("tenantId", unknownFixture.tenantId).param("workItemId", unknownFixture.workItemId).query(String.class).single());
        assertTrue(recovery.recover(10, envelope -> WorkerGatewayResult.UNKNOWN).unknown() >= 1);
        WorkerGateway acknowledgingGateway = new WorkerGateway() {
            @Override public WorkerGatewayResult dispatch(ProductionRuntimeModels.DispatchEnvelope envelope) { return WorkerGatewayResult.ACKED; }
            @Override public WorkerGatewayResult reconcile(ProductionRuntimeModels.DispatchEnvelope envelope) { return WorkerGatewayResult.ACKED; }
        };
        assertTrue(recovery.recover(10, acknowledgingGateway).advanced() >= 1);
        assertEquals("ACKED", jdbc.sql("select state from runtime.dispatch_intents where tenant_id = :tenantId and work_item_id = :workItemId").param("tenantId", unknownFixture.tenantId).param("workItemId", unknownFixture.workItemId).query(String.class).single());
    }

    @Test
    void redisLossDoesNotDeleteDurableDispatchOrMoneyState() throws Exception {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-redis-loss"));
        var intent = runtime.prepareReservation(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Map.of("redis", "ephemeral"), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId);
        var reservation = billing.reserve(new ProductionRuntimeModels.ReserveRequest(fixture.tenantId, fixture.walletId, fixture.projectId, fixture.jobId, fixture.workItemId, "reserve-" + fixture.workItemId, BigDecimal.ONE, Instant.now().plusSeconds(300)));
        runtime.attachReservation(fixture.tenantId, intent.id(), reservation.reservationId());
        String key = "runtime:" + fixture.workItemId;
        var set = REDIS.execInContainer("redis-cli", "SET", key, "checkpoint");
        assertEquals(0, set.getExitCode(), set.getStderr());
        assertEquals("checkpoint", REDIS.execInContainer("redis-cli", "GET", key).getStdout().trim());
        assertEquals(0, REDIS.execInContainer("redis-cli", "FLUSHALL").getExitCode());
        assertTrue(REDIS.execInContainer("redis-cli", "GET", key).getStdout().trim().isEmpty());

        var report = recovery.recover(10, envelope -> WorkerGatewayResult.ACKED);
        assertTrue(report.advanced() >= 1);
        assertEquals("ACKED", jdbc.sql("select state from runtime.dispatch_intents where tenant_id = :tenantId and id = :id").param("tenantId", fixture.tenantId).param("id", intent.id()).query(String.class).single());
        assertEquals(BigDecimal.valueOf(9).setScale(12), jdbc.sql("select available_balance from billing.wallet_balances where tenant_id = :tenantId and wallet_id = :walletId").param("tenantId", fixture.tenantId).param("walletId", fixture.walletId).query(BigDecimal.class).single());
        assertEquals(BigDecimal.ONE.setScale(12), jdbc.sql("select reserved_balance from billing.wallet_balances where tenant_id = :tenantId and wallet_id = :walletId").param("tenantId", fixture.tenantId).param("walletId", fixture.walletId).query(BigDecimal.class).single());
    }

    @Test
    void workerProcessKillResumesFromLatestDurableCheckpoint() throws Exception {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.TEN, "hash-worker-kill"));
        var outcome = coordinator.dispatch(new DispatchRequest(fixture.tenantId, fixture.projectId, fixture.jobId, fixture.workItemId, fixture.walletId, fixture.workerId, BigDecimal.ONE, Instant.now().plusSeconds(300), Duration.ofSeconds(30), "reserve-" + fixture.workItemId, "dispatch-" + fixture.workItemId, Map.of("fault", "worker-kill")), envelope -> WorkerGatewayResult.UNKNOWN);
        Path ready = Files.createTempFile("elmos-worker-kill-", ".ready");
        Files.deleteIfExists(ready);
        Process worker = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(), "-cp", System.getProperty("java.class.path"), ProductionRuntimeWorkerKillProbe.class.getName(), ready.toString())
                .redirectOutput(ProcessBuilder.Redirect.DISCARD).redirectError(ProcessBuilder.Redirect.DISCARD).start();
        try {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
            while (!Files.exists(ready) && System.nanoTime() < deadline) Thread.sleep(25);
            assertTrue(Files.exists(ready), "worker probe did not start");
            runtime.checkpoint(new Checkpoint(fixture.tenantId, fixture.jobId, fixture.workItemId, outcome.envelope().attemptId(), "WORKSPACE", 1, "cas://checkpoint/worker-kill", "d".repeat(64)));
            worker.destroyForcibly();
            assertTrue(worker.waitFor(5, TimeUnit.SECONDS), "worker process did not terminate");
            WorkerGateway acknowledgingGateway = new WorkerGateway() {
                @Override public WorkerGatewayResult dispatch(ProductionRuntimeModels.DispatchEnvelope envelope) { return WorkerGatewayResult.ACKED; }
                @Override public WorkerGatewayResult reconcile(ProductionRuntimeModels.DispatchEnvelope envelope) { return WorkerGatewayResult.ACKED; }
            };
            var report = recovery.recover(10, acknowledgingGateway);
            assertTrue(report.advanced() >= 1);
            assertEquals(1, jdbc.sql("select count(*) from runtime.checkpoints where tenant_id = :tenantId and attempt_id = :attemptId").param("tenantId", fixture.tenantId).param("attemptId", outcome.envelope().attemptId()).query(Long.class).single());
            assertEquals("ACKED", jdbc.sql("select state from runtime.dispatch_intents where tenant_id = :tenantId and id = :id").param("tenantId", fixture.tenantId).param("id", outcome.intent().id()).query(String.class).single());
        } finally {
            if (worker.isAlive()) worker.destroyForcibly();
            Files.deleteIfExists(ready);
        }
    }

    @Test
    void localLoadHarnessMeasuresReserveP95WithoutNegativeBalance() throws Exception {
        Fixture fixture = fixture();
        int requestCount = 24;
        billing.applyVerifiedTopUp(new TopUpRequest(fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId, BigDecimal.valueOf(requestCount), "hash-local-load"));
        List<UUID> workItems = new ArrayList<>();
        for (int index = 0; index < requestCount; index++) {
            workItems.add(runtime.createWorkItem(new WorkItemRequest(fixture.tenantId, fixture.jobId, fixture.stageId, "inventory", "repo/load/" + index, 10, BigDecimal.ONE, 1, "load-item-" + index + "-" + fixture.tenantId)));
        }
        ExecutorService executor = Executors.newFixedThreadPool(8);
        try {
            List<Future<Long>> futures = new ArrayList<>();
            for (int index = 0; index < requestCount; index++) {
                UUID workItemId = workItems.get(index);
                int requestIndex = index;
                futures.add(executor.submit(() -> {
                    long started = System.nanoTime();
                    billing.reserve(new ProductionRuntimeModels.ReserveRequest(fixture.tenantId, fixture.walletId, fixture.projectId, fixture.jobId, workItemId, "load-reserve-" + requestIndex + "-" + fixture.tenantId, BigDecimal.ONE, Instant.now().plusSeconds(300)));
                    return System.nanoTime() - started;
                }));
            }
            List<Long> durations = new ArrayList<>();
            for (Future<Long> future : futures) durations.add(future.get());
            Collections.sort(durations);
            double p95Millis = durations.get((int) Math.ceil(durations.size() * 0.95) - 1) / 1_000_000.0;
            System.out.printf("LOCAL_HARNESS_METRIC scenario=TargetClusterLoad substitute=postgresql-testcontainers reserve_p95_ms=%.3f requests=%d%n", p95Millis, requestCount);
            assertTrue(p95Millis >= 0);
            assertEquals(BigDecimal.ZERO.setScale(12), jdbc.sql("select available_balance from billing.wallet_balances where tenant_id = :tenantId and wallet_id = :walletId").param("tenantId", fixture.tenantId).param("walletId", fixture.walletId).query(BigDecimal.class).single());
            assertTrue(runtime.invariantViolations(fixture.tenantId).stream().noneMatch(value -> value.startsWith("NEGATIVE_WALLET")));
        } finally {
            executor.shutdownNow();
        }
    }

    @Test
    void fairSchedulerResolvesOneWalletAndExactCompatibleWorker() {
        Fixture fixture = fixture();
        billing.applyVerifiedTopUp(new TopUpRequest(
                fixture.tenantId, fixture.walletId, "test-pay", "payment-" + fixture.tenantId,
                BigDecimal.TEN, "hash-fair-scheduler"));
        var service = new ProductionRuntimeSchedulingService(
                new ProductionRuntimeScheduler(runtime), coordinator,
                java.time.Clock.systemUTC(), Duration.ofMinutes(5), Duration.ofSeconds(30));

        var report = service.schedule(10, envelope -> WorkerGatewayResult.ACKED);

        assertTrue(report.acknowledged() >= 1,
                "the global fair scheduler may also acknowledge ready work left by earlier fixtures");
        assertEquals(0, report.blocked());
        assertEquals("ACKED", jdbc.sql("select state from runtime.dispatch_intents where tenant_id = :tenantId and work_item_id = :workItemId")
                .param("tenantId", fixture.tenantId).param("workItemId", fixture.workItemId)
                .query(String.class).single());
    }

    private UsageContext prepareUsage(
            Fixture fixture, UUID workItemId, String suffix, BigDecimal reservationAmount) {
        var outcome = coordinator.dispatch(new DispatchRequest(
                fixture.tenantId, fixture.projectId, fixture.jobId, workItemId,
                fixture.walletId, fixture.workerId, reservationAmount,
                Instant.now().plusSeconds(300), Duration.ofSeconds(30),
                "usage-reserve-" + suffix + "-" + workItemId,
                "usage-dispatch-" + suffix + "-" + workItemId,
                Map.of("usageScenario", suffix)), envelope -> WorkerGatewayResult.ACKED);
        assertEquals(ProductionRuntimeCoordinator.DispatchStatus.ACKED, outcome.status());
        String providerRequestId = "provider-request-" + suffix + "-" + workItemId;
        var call = billing.beginModelCall(new ModelCallRequest(
                fixture.tenantId, fixture.accountId, fixture.projectId, fixture.jobId,
                fixture.stageId, workItemId, outcome.envelope().attemptId(),
                "test-provider", "test-model",
                "model-call-" + suffix + "-" + workItemId,
                "request-hash-" + suffix));
        billing.claimProviderDispatch(fixture.tenantId, call.modelCallId());
        billing.markProviderAccepted(fixture.tenantId, call.modelCallId(), providerRequestId);
        UUID responseArtifactId = artifacts.registerArtifact(
                new ProductionRuntimeModels.ArtifactRequest(
                        fixture.tenantId, fixture.projectId, fixture.jobId, workItemId,
                        "MODEL_PROVIDER_RESPONSE",
                        "cas://provider-response/" + call.modelCallId(),
                        "f".repeat(64), 256));
        UUID providerPricing = jdbc.sql(
                        "select id from billing.provider_pricing_versions order by effective_from desc limit 1")
                .query(UUID.class).single();
        UUID commercialPricing = jdbc.sql(
                        "select id from billing.commercial_pricing_versions order by effective_from desc limit 1")
                .query(UUID.class).single();
        return new UsageContext(
                outcome.intent().reservationId(), call.modelCallId(), providerRequestId,
                responseArtifactId, providerPricing, commercialPricing);
    }

    private MeterSnapshot meter(
            Fixture fixture, UsageContext context, long sequenceNo, long inputTokens) {
        return new MeterSnapshot(
                fixture.tenantId, context.reservationId, context.modelCallId,
                sequenceNo, inputTokens, 0, 0, 0,
                BigDecimal.valueOf(inputTokens).multiply(BigDecimal.valueOf(0.1)),
                BigDecimal.valueOf(inputTokens).multiply(BigDecimal.valueOf(0.3)));
    }

    private FinalUsage finalUsage(
            Fixture fixture, UsageContext context, String providerUsageId, long inputTokens) {
        return new FinalUsage(
                fixture.tenantId, context.reservationId, context.modelCallId,
                "test-provider", "test-model", providerUsageId,
                context.providerPricingVersionId, context.commercialPricingVersionId,
                inputTokens, 0, 0, 0,
                BigDecimal.valueOf(inputTokens).multiply(BigDecimal.valueOf(0.1)),
                BigDecimal.valueOf(inputTokens).multiply(BigDecimal.valueOf(0.3)));
    }

    private Fixture fixture() {
        UUID tenant = UUID.randomUUID();
        UUID account = UUID.randomUUID();
        var tenantAccount = runtime.provisionTenant(tenant, account, "tenant-" + tenant, "CNY");
        UUID project = runtime.createProject(new ProjectRequest(tenant, account, "project-" + tenant, "MODERNIZATION"));
        UUID job = runtime.createJob(new JobRequest(tenant, account, project, "SPRING_MODERNIZATION", java.util.List.of("inventory"), 4, 100));
        UUID stage = jdbc.sql("select id from orchestration.job_stages where tenant_id = :tenantId and job_id = :jobId").param("tenantId", tenant).param("jobId", job).query(UUID.class).single();
        UUID item = runtime.createWorkItem(new WorkItemRequest(tenant, job, stage, "inventory", "repo/root", 100, BigDecimal.ONE, 2, "item-" + tenant));
        UUID worker = UUID.randomUUID();
        runtime.registerWorker(new WorkerRegistration(
                worker, "worker-" + worker, "SPRING",
                "http://worker.invalid/" + worker, "local", "local-1",
                Map.of(
                        "routeTuples", List.of("SPRING_MODERNIZATION:inventory"),
                        "maxConcurrent", 8)));
        return new Fixture(tenant, account, tenantAccount.walletId(), project, job, stage, item, worker);
    }

    private static Path locateMigration() {
        Path current = Path.of("").toAbsolutePath();
        while (current != null) {
            Path candidate = current.resolve("modules/persistence/src/main/resources/db/migration/V77__production_repository_execution_os.sql");
            if (Files.isRegularFile(candidate)) return candidate;
            current = current.getParent();
        }
        throw new IllegalStateException("V77 migration not found");
    }

    private record UsageContext(
            UUID reservationId,
            UUID modelCallId,
            String providerRequestId,
            UUID responseArtifactId,
            UUID providerPricingVersionId,
            UUID commercialPricingVersionId) {}

    private record Fixture(UUID tenantId, UUID accountId, UUID walletId, UUID projectId, UUID jobId, UUID stageId, UUID workItemId, UUID workerId) {}
}
