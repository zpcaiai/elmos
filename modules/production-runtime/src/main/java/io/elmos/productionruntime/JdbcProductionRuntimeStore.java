package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeModels.AttemptStatus;
import io.elmos.productionruntime.ProductionRuntimeModels.Checkpoint;
import io.elmos.productionruntime.ProductionRuntimeModels.Completion;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchEnvelope;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchIntent;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchState;
import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.JobRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.OutputVerificationReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ProjectRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ProgressSnapshot;
import io.elmos.productionruntime.ProductionRuntimeModels.ReadyWorkItem;
import io.elmos.productionruntime.ProductionRuntimeModels.TenantAccount;
import io.elmos.productionruntime.ProductionRuntimeModels.WorkItemRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.WorkItemStatus;
import io.elmos.productionruntime.ProductionRuntimeModels.WorkerRegistration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/** PostgreSQL adapter for the durable execution, worker, and projection contexts. */
public final class JdbcProductionRuntimeStore implements ProductionRuntimeStore {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;
    private final ObjectMapper json;

    public JdbcProductionRuntimeStore(JdbcClient jdbc, TransactionTemplate transactions, ObjectMapper json) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
        this.json = Objects.requireNonNull(json, "json");
    }

    @Override
    public TenantAccount provisionTenant(UUID tenantId, UUID accountId, String tenantName, String currency) {
        ProductionRuntimeModels.require(tenantId, "tenantId");
        ProductionRuntimeModels.require(accountId, "accountId");
        ProductionRuntimeModels.requireText(tenantName, "tenantName", 200);
        if (currency == null || !currency.matches("[A-Z]{3}")) throw new IllegalArgumentException("currency must be an uppercase ISO-4217 code");
        return transactions.execute(status -> {
            jdbc.sql("select set_config('app.tenant_id', :tenantId, true)").param("tenantId", tenantId.toString()).query(String.class).single();
            jdbc.sql("insert into identity.tenants (id, name) values (:id, :name) on conflict (id) do update set name = excluded.name")
                    .param("id", tenantId).param("name", tenantName).update();
            jdbc.sql("insert into identity.accounts (id, tenant_id, status) values (:id, :tenantId, 'ACTIVE') on conflict (id) do nothing")
                    .param("id", accountId).param("tenantId", tenantId).update();
            UUID billingAccountId = jdbc.sql("insert into billing.billing_accounts (tenant_id, account_id, billing_type) values (:tenantId, :accountId, 'PREPAID') on conflict (tenant_id, account_id) do update set status = 'ACTIVE' returning id")
                    .param("tenantId", tenantId).param("accountId", accountId).query(UUID.class).single();
            UUID walletId = jdbc.sql("insert into billing.wallets (tenant_id, billing_account_id, currency) values (:tenantId, :billingAccountId, :currency) on conflict (billing_account_id, currency) do update set status = 'ACTIVE' returning id")
                    .param("tenantId", tenantId).param("billingAccountId", billingAccountId).param("currency", currency).query(UUID.class).single();
            jdbc.sql("insert into billing.wallet_balances (wallet_id, tenant_id) values (:walletId, :tenantId) on conflict (wallet_id) do nothing").param("walletId", walletId).param("tenantId", tenantId).update();
            jdbc.sql("insert into orchestration.admission_policies (tenant_id) values (:tenantId) on conflict (tenant_id) do nothing")
                    .param("tenantId", tenantId).update();
            return new TenantAccount(tenantId, accountId, billingAccountId, walletId, currency);
        });
    }

    @Override
    public void upsertAdmissionPolicy(ProductionRuntimeModels.AdmissionPolicy policy) {
        inTenant(policy.tenantId(), () -> {
            jdbc.sql("""
                    insert into orchestration.admission_policies
                      (tenant_id, max_active_jobs, max_active_work_items,
                       max_project_active_work_items, max_concurrent_model_calls,
                       max_compile_test_slots, max_provider_calls_per_minute,
                       daily_token_cap, daily_credit_cap, updated_at)
                    values (:tenantId, :jobs, :work, :projectWork, :modelCalls,
                            :compileTest, :providerCalls, :tokens, :credits, now())
                    on conflict (tenant_id) do update set
                      max_active_jobs = excluded.max_active_jobs,
                      max_active_work_items = excluded.max_active_work_items,
                      max_project_active_work_items = excluded.max_project_active_work_items,
                      max_concurrent_model_calls = excluded.max_concurrent_model_calls,
                      max_compile_test_slots = excluded.max_compile_test_slots,
                      max_provider_calls_per_minute = excluded.max_provider_calls_per_minute,
                      daily_token_cap = excluded.daily_token_cap,
                      daily_credit_cap = excluded.daily_credit_cap,
                      updated_at = now()
                    """)
                    .param("tenantId", policy.tenantId())
                    .param("jobs", policy.maxActiveJobs())
                    .param("work", policy.maxActiveWorkItems())
                    .param("projectWork", policy.maxProjectActiveWorkItems())
                    .param("modelCalls", policy.maxConcurrentModelCalls())
                    .param("compileTest", policy.maxCompileTestSlots())
                    .param("providerCalls", policy.maxProviderCallsPerMinute())
                    .param("tokens", policy.dailyTokenCap())
                    .param("credits", policy.dailyCreditCap())
                    .update();
            return null;
        });
    }

    @Override
    public UUID createProject(ProjectRequest request) {
        return inTenant(request.tenantId(), () -> {
            assertAccount(request.tenantId(), request.accountId());
            UUID projectId = UUID.randomUUID();
            jdbc.sql("insert into project.projects (id, tenant_id, account_id, name, project_type) values (:id, :tenantId, :accountId, :name, :type)")
                    .param("id", projectId).param("tenantId", request.tenantId()).param("accountId", request.accountId()).param("name", request.name()).param("type", request.projectType()).update();
            return projectId;
        });
    }

    @Override
    public UUID createJob(JobRequest request) {
        return inTenant(request.tenantId(), () -> {
            ProductionWorkloadPackCatalog.require(request.jobType(), request.stageTypes());
            assertProjectAccount(request.tenantId(), request.accountId(), request.projectId());
            UUID jobId = UUID.randomUUID();
            jdbc.sql("insert into orchestration.jobs (id, tenant_id, account_id, project_id, job_type, max_parallelism, priority) values (:id, :tenantId, :accountId, :projectId, :jobType, :parallelism, :priority)")
                    .param("id", jobId).param("tenantId", request.tenantId()).param("accountId", request.accountId()).param("projectId", request.projectId()).param("jobType", request.jobType()).param("parallelism", request.maxParallelism()).param("priority", request.priority()).update();
            int sequence = 0;
            for (String stageType : request.stageTypes()) {
                jdbc.sql("insert into orchestration.job_stages (tenant_id, job_id, stage_type, name, status, sequence_no, max_parallelism) values (:tenantId, :jobId, :stageType, :name, :status, :sequence, :parallelism)")
                        .param("tenantId", request.tenantId()).param("jobId", jobId).param("stageType", stageType).param("name", stageType).param("status", sequence == 0 ? "READY" : "BLOCKED").param("sequence", sequence++).param("parallelism", request.maxParallelism()).update();
            }
            return jobId;
        });
    }

    @Override
    public int advanceJobStages(UUID tenantId, UUID jobId) {
        ProductionRuntimeModels.require(tenantId, "tenantId");
        ProductionRuntimeModels.require(jobId, "jobId");
        return inTenant(tenantId, () -> jdbc.sql(
                        "select orchestration.advance_job_stages(:tenantId, :jobId)")
                .param("tenantId", tenantId)
                .param("jobId", jobId)
                .query(Integer.class)
                .single());
    }

    @Override
    public UUID createWorkItem(WorkItemRequest request) {
        return inTenant(request.tenantId(), () -> {
            assertStageJob(request.tenantId(), request.jobId(), request.stageId());
            String stageStatus = jdbc.sql("select status from orchestration.job_stages where tenant_id = :tenantId and id = :stageId for update")
                    .param("tenantId", request.tenantId())
                    .param("stageId", request.stageId())
                    .query(String.class)
                    .single();
            if (stageStatus.equals("SUCCEEDED") || stageStatus.equals("FAILED")
                    || stageStatus.equals("CANCELLED")) {
                throw new ProductionRuntimeException(
                        "STAGE_NOT_OPEN", "cannot add work to a terminal workload stage");
            }
            String initialStatus = stageStatus.equals("READY") || stageStatus.equals("RUNNING")
                    ? "READY" : "PENDING";
            UUID itemId = UUID.randomUUID();
            jdbc.sql("""
                    insert into orchestration.work_items
                      (id, tenant_id, job_id, stage_id, work_type, resource_key, status,
                       estimated_tokens, estimated_cost, max_retries, idempotency_key, ready_at)
                    values (:id, :tenantId, :jobId, :stageId, :workType, :resourceKey, :status,
                            :estimatedTokens, :estimatedCredits, :maxRetries, :idempotencyKey,
                            case when :status = 'READY' then now() else null end)
                    """).param("id", itemId).param("tenantId", request.tenantId()).param("jobId", request.jobId()).param("stageId", request.stageId()).param("workType", request.workType()).param("resourceKey", request.resourceKey()).param("status", initialStatus).param("estimatedTokens", request.estimatedTokens()).param("estimatedCredits", request.estimatedCredits()).param("maxRetries", request.maxRetries()).param("idempotencyKey", request.idempotencyKey()).update();
            jdbc.sql("select orchestration.advance_job_stages(:tenantId, :jobId)")
                    .param("tenantId", request.tenantId())
                    .param("jobId", request.jobId())
                    .query(Integer.class)
                    .single();
            return itemId;
        });
    }

    @Override
    public void addDependency(UUID tenantId, UUID workItemId, UUID dependsOnWorkItemId) {
        inTenant(tenantId, () -> {
            if (workItemId.equals(dependsOnWorkItemId)) throw new ProductionRuntimeException("WORK_ITEM_DEPENDENCY_CYCLE", "work item cannot depend on itself");
            assertWorkItemTenant(tenantId, workItemId);
            assertWorkItemTenant(tenantId, dependsOnWorkItemId);
            var jobs = jdbc.sql("select wi.id, wi.job_id from orchestration.work_items wi where wi.tenant_id = :tenantId and wi.id in (:workItemId, :dependsOn)")
                    .param("tenantId", tenantId).param("workItemId", workItemId).param("dependsOn", dependsOnWorkItemId)
                    .query((rs, row) -> Map.entry(rs.getObject("id", UUID.class), rs.getObject("job_id", UUID.class))).list();
            if (jobs.size() != 2 || !jobs.get(0).getValue().equals(jobs.get(1).getValue())) {
                throw new ProductionRuntimeException(
                        "WORK_ITEM_DEPENDENCY_JOB_MISMATCH",
                        "work item dependencies must belong to the same job");
            }
            Boolean cycle = jdbc.sql("""
                    with recursive reachable(id) as (
                        select depends_on_work_item_id
                          from orchestration.work_item_dependencies
                         where tenant_id = :tenantId and work_item_id = :workItemId
                        union
                        select dep.depends_on_work_item_id
                          from orchestration.work_item_dependencies dep
                          join reachable r on r.id = dep.work_item_id
                         where dep.tenant_id = :tenantId
                    )
                    select exists (select 1 from reachable where id = :dependsOn)
                    """)
                    .param("tenantId", tenantId)
                    .param("workItemId", dependsOnWorkItemId)
                    .param("dependsOn", workItemId)
                    .query(Boolean.class)
                    .single();
            if (Boolean.TRUE.equals(cycle)) {
                throw new ProductionRuntimeException(
                        "WORK_ITEM_DEPENDENCY_CYCLE",
                        "dependency would create a cycle");
            }
            jdbc.sql("insert into orchestration.work_item_dependencies (tenant_id, work_item_id, depends_on_work_item_id) values (:tenantId, :workItemId, :dependsOn) on conflict do nothing")
                    .param("tenantId", tenantId).param("workItemId", workItemId).param("dependsOn", dependsOnWorkItemId).update();
            jdbc.sql("update orchestration.work_items set status = 'PENDING', ready_at = null, updated_at = now() where tenant_id = :tenantId and id = :id and status = 'READY'")
                    .param("tenantId", tenantId).param("id", workItemId).update();
            advanceJobStages(tenantId, jobs.get(0).getValue());
            return null;
        });
    }

    @Override
    public void registerWorker(WorkerRegistration registration) {
        transactions.execute(status -> {
            try {
                int changed = jdbc.sql("""
                        insert into runtime.workers
                            (id, worker_name, worker_type, endpoint_uri, region, zone,
                             capabilities, status, last_heartbeat_at)
                        values
                            (:id, :name, :type, :endpoint, :region, :zone,
                             cast(:capabilities as jsonb), 'ACTIVE', now())
                        on conflict (id) do update
                           set status = 'ACTIVE', last_heartbeat_at = now()
                         where runtime.workers.worker_name = excluded.worker_name
                           and runtime.workers.worker_type = excluded.worker_type
                           and runtime.workers.endpoint_uri = excluded.endpoint_uri
                           and runtime.workers.region is not distinct from excluded.region
                           and runtime.workers.zone is not distinct from excluded.zone
                           and runtime.workers.capabilities = excluded.capabilities
                        """)
                        .param("id", registration.workerId())
                        .param("name", registration.workerName())
                        .param("type", registration.workerType())
                        .param("endpoint", registration.endpointUri())
                        .param("region", registration.region())
                        .param("zone", registration.zone())
                        .param("capabilities", json.writeValueAsString(registration.capabilities()))
                        .update();
                if (changed != 1) {
                    throw new ProductionRuntimeException(
                            "WORKER_IDENTITY_CONFLICT",
                            "worker id is already bound to different immutable registration data");
                }
                return null;
            } catch (ProductionRuntimeException ex) {
                throw ex;
            } catch (Exception ex) {
                throw new ProductionRuntimeException("WORKER_REGISTRATION_INVALID", "worker capabilities are not valid JSON", ex);
            }
        });
    }

    @Override
    public DispatchIntent prepareReservation(UUID tenantId, UUID projectId, UUID jobId, UUID workItemId, UUID walletId, UUID workerId, BigDecimal estimatedCredits, Instant reservationExpiresAt, Map<String, Object> payload, String reservationIdempotencyKey, String dispatchIdempotencyKey) {
        return inTenant(tenantId, () -> {
            var existing = jdbc.sql("select * from runtime.dispatch_intents where tenant_id = :tenantId and work_item_id = :workItemId and dispatch_idempotency_key = :key for update")
                    .param("tenantId", tenantId).param("workItemId", workItemId).param("key", dispatchIdempotencyKey).query(this::readIntent).optional();
            if (existing.isPresent()) return existing.get();
            assertAdmissionAvailable(tenantId, projectId, jobId, workItemId);
            String status = jdbc.sql("select status from orchestration.work_items where tenant_id = :tenantId and id = :id for update").param("tenantId", tenantId).param("id", workItemId).query(String.class).optional().orElseThrow(() -> new ProductionRuntimeException("WORK_ITEM_NOT_FOUND", "work item not found"));
            if (!status.equals("READY") && !status.equals("RETRY_WAIT")) throw new ProductionRuntimeException("WORK_ITEM_NOT_READY", "work item is not eligible for reservation: " + status);
            UUID intentId = UUID.randomUUID();
            try {
                jdbc.sql("insert into runtime.dispatch_intents (id, tenant_id, project_id, job_id, work_item_id, wallet_id, worker_id, estimated_credits, reservation_expires_at, dispatch_payload, state, reservation_idempotency_key, dispatch_idempotency_key) values (:id, :tenantId, :projectId, :jobId, :workItemId, :walletId, :workerId, :estimatedCredits, :expiresAt, cast(:payload as jsonb), 'RESERVING', :reservationKey, :dispatchKey)")
                        .param("id", intentId).param("tenantId", tenantId).param("projectId", projectId).param("jobId", jobId).param("workItemId", workItemId).param("walletId", walletId).param("workerId", workerId).param("estimatedCredits", estimatedCredits).param("expiresAt", java.time.OffsetDateTime.ofInstant(reservationExpiresAt, java.time.ZoneOffset.UTC)).param("payload", json.writeValueAsString(payload == null ? Map.of() : payload)).param("reservationKey", reservationIdempotencyKey).param("dispatchKey", dispatchIdempotencyKey).update();
            } catch (Exception ex) {
                throw new ProductionRuntimeException("DISPATCH_PAYLOAD_INVALID", "dispatch payload is not valid JSON", ex);
            }
            jdbc.sql("update orchestration.work_items set status = 'RESERVING', updated_at = now() where id = :id and tenant_id = :tenantId")
                    .param("id", workItemId).param("tenantId", tenantId).update();
            event(tenantId, "WORK_ITEM", workItemId, "RESERVATION_STARTED", Map.of("dispatchIntentId", intentId));
            return jdbc.sql("select * from runtime.dispatch_intents where id = :id").param("id", intentId).query(this::readIntent).single();
        });
    }

    @Override
    public void markWaitingForCredit(UUID tenantId, UUID workItemId, String reason) {
        inTenant(tenantId, () -> {
            String current = jdbc.sql("select status from orchestration.work_items where tenant_id = :tenantId and id = :id for update")
                    .param("tenantId", tenantId).param("id", workItemId)
                    .query(String.class).optional()
                    .orElseThrow(() -> new ProductionRuntimeException(
                            "WORK_ITEM_NOT_FOUND", "work item not found"));
            if ("WAITING_FOR_CREDIT".equals(current)) return null;
            if (!"RESERVING".equals(current)) {
                throw new ProductionRuntimeException(
                        "STALE_WORK_ITEM_CREDIT_WAIT",
                        "only the current RESERVING owner may pause for credit");
            }
            updateOrThrow("STALE_WORK_ITEM_CREDIT_WAIT", jdbc.sql("update orchestration.work_items set status = 'WAITING_FOR_CREDIT', ready_at = null, updated_at = now() where tenant_id = :tenantId and id = :id and status = 'RESERVING'")
                    .param("tenantId", tenantId).param("id", workItemId));
            event(tenantId, "WORK_ITEM", workItemId, "WAITING_FOR_CREDIT", Map.of("reason", reason == null ? "CREDIT_EXHAUSTED" : reason));
            return null;
        });
    }

    @Override
    public DispatchIntent attachReservation(UUID tenantId, UUID dispatchIntentId, UUID reservationId) {
        return inTenant(tenantId, () -> {
            var intent = lockIntent(tenantId, dispatchIntentId);
            if (intent.reservationId() != null && intent.reservationId().equals(reservationId)) return intent;
            if (intent.state() != DispatchState.RESERVING) throw new ProductionRuntimeException("DISPATCH_INTENT_STATE_CONFLICT", "intent is not reserving");
            updateOrThrow("STALE_DISPATCH_INTENT", jdbc.sql("update runtime.dispatch_intents set reservation_id = :reservationId, state = 'RESERVED', updated_at = now() where id = :id and tenant_id = :tenantId and state = 'RESERVING'")
                    .param("reservationId", reservationId).param("id", dispatchIntentId).param("tenantId", tenantId));
            updateOrThrow("STALE_WORK_ITEM", jdbc.sql("update orchestration.work_items set status = 'RESERVED', updated_at = now() where tenant_id = :tenantId and id = :workItemId and status in ('RESERVING','READY')")
                    .param("tenantId", tenantId).param("workItemId", intent.workItemId()));
            event(tenantId, "WORK_ITEM", intent.workItemId(), "CREDIT_RESERVED", Map.of("reservationId", reservationId));
            return lockIntent(tenantId, dispatchIntentId);
        });
    }

    @Override
    public DispatchEnvelope createAttempt(UUID tenantId, UUID dispatchIntentId, UUID workerId, Duration leaseDuration, Map<String, Object> payload) {
        if (leaseDuration == null || leaseDuration.compareTo(Duration.ofSeconds(5)) < 0 || leaseDuration.compareTo(Duration.ofHours(1)) > 0) throw new IllegalArgumentException("leaseDuration out of range");
        return inTenant(tenantId, () -> {
            var intent = lockIntent(tenantId, dispatchIntentId);
            if (intent.state() == DispatchState.DISPATCHING || intent.state() == DispatchState.ATTEMPT_CREATED) {
                long activeLease = jdbc.sql("select count(*) from runtime.worker_leases where tenant_id = :tenantId and work_item_id = :workItemId and attempt_id = :attemptId and fencing_token = :fence")
                        .param("tenantId", tenantId).param("workItemId", intent.workItemId()).param("attemptId", intent.attemptId()).param("fence", intent.fencingToken()).query(Long.class).single();
                if (activeLease == 1) return existingEnvelope(tenantId, intent, payload);
                jdbc.sql("update runtime.dispatch_intents set state = 'RESERVED', attempt_id = null, fencing_token = null, last_error = 'LEASE_LOST', updated_at = now() where tenant_id = :tenantId and id = :id and state in ('DISPATCHING','ATTEMPT_CREATED')")
                        .param("tenantId", tenantId).param("id", dispatchIntentId).update();
                jdbc.sql("update orchestration.work_items set status = 'RESERVED', updated_at = now() where tenant_id = :tenantId and id = :workItemId and status in ('DISPATCHING','RETRY_WAIT')")
                        .param("tenantId", tenantId).param("workItemId", intent.workItemId()).update();
                intent = lockIntent(tenantId, dispatchIntentId);
            }
            if (intent.state() != DispatchState.RESERVED) throw new ProductionRuntimeException("DISPATCH_INTENT_STATE_CONFLICT", "intent is not reserved");
            var worker = jdbc.sql("select endpoint_uri, status, capabilities from runtime.workers where id = :workerId for update").param("workerId", workerId).query((rs, row) -> new WorkerRow(rs.getString("endpoint_uri"), rs.getString("status"), rs.getString("capabilities"))).optional().orElseThrow(() -> new ProductionRuntimeException("WORKER_NOT_FOUND", "worker is not registered"));
            if (!worker.status().equals("ACTIVE")) throw new ProductionRuntimeException("WORKER_NOT_ACTIVE", "worker is not active");
            assertWorkerCapacity(workerId, worker.capabilitiesJson());
            long fence = jdbc.sql("select runtime.allocate_fence(:workItemId)").param("workItemId", intent.workItemId()).query(Long.class).single();
            int attemptNo = jdbc.sql("select coalesce(max(attempt_no), 0) + 1 from runtime.execution_attempts where tenant_id = :tenantId and work_item_id = :workItemId").param("tenantId", tenantId).param("workItemId", intent.workItemId()).query(Integer.class).single();
            UUID attemptId = UUID.randomUUID();
            Map<String, Object> attemptPayload = resumePayload(
                    tenantId, intent.workItemId(), payload);
            jdbc.sql("insert into runtime.execution_attempts (id, tenant_id, work_item_id, attempt_no, worker_id, fencing_token) values (:id, :tenantId, :workItemId, :attemptNo, :workerId, :fence)").param("id", attemptId).param("tenantId", tenantId).param("workItemId", intent.workItemId()).param("attemptNo", attemptNo).param("workerId", workerId).param("fence", fence).update();
            jdbc.sql("insert into runtime.worker_leases (work_item_id, tenant_id, worker_id, attempt_id, fencing_token, leased_at, expires_at, heartbeat_at) values (:workItemId, :tenantId, :workerId, :attemptId, :fence, now(), now() + cast(:leaseDuration as interval), now())")
                    .param("workItemId", intent.workItemId()).param("tenantId", tenantId).param("workerId", workerId).param("attemptId", attemptId).param("fence", fence).param("leaseDuration", leaseDuration.toSeconds() + " seconds").update();
            updateOrThrow("STALE_DISPATCH_INTENT", jdbc.sql("update runtime.dispatch_intents set attempt_id = :attemptId, worker_id = :workerId, fencing_token = :fence, state = 'DISPATCHING', updated_at = now() where id = :id and state = 'RESERVED'")
                    .param("attemptId", attemptId).param("workerId", workerId).param("fence", fence).param("id", dispatchIntentId));
            updateOrThrow("STALE_WORK_ITEM", jdbc.sql("update orchestration.work_items set status = 'DISPATCHING', started_at = coalesce(started_at, now()), updated_at = now() where id = :id and tenant_id = :tenantId and status = 'RESERVED'")
                    .param("id", intent.workItemId()).param("tenantId", tenantId));
            event(tenantId, "WORK_ITEM", intent.workItemId(), "DISPATCHING", Map.of("attemptId", attemptId, "workerId", workerId, "fencingToken", fence));
            return new DispatchEnvelope(tenantId, intent.workItemId(), attemptId, workerId, fence, worker.endpointUri(), intent.dispatchIdempotencyKey(), attemptPayload);
        });
    }

    @Override
    public void acknowledge(UUID tenantId, UUID attemptId, UUID workerId, long fencingToken) {
        inTenant(tenantId, () -> {
            updateOrThrow("STALE_ATTEMPT_ACK", jdbc.sql("update runtime.execution_attempts set status = 'RUNNING', started_at = coalesce(started_at, now()), heartbeat_at = now() where tenant_id = :tenantId and id = :attemptId and worker_id = :workerId and fencing_token = :fence and status = 'CREATED'")
                    .param("tenantId", tenantId).param("attemptId", attemptId).param("workerId", workerId).param("fence", fencingToken));
            updateOrThrow("STALE_WORK_ITEM_ACK", jdbc.sql("update orchestration.work_items wi set status = 'RUNNING', updated_at = now() from runtime.execution_attempts ea where wi.id = ea.work_item_id and wi.tenant_id = :tenantId and ea.id = :attemptId")
                    .param("tenantId", tenantId).param("attemptId", attemptId));
            updateOrThrow("STALE_DISPATCH_ACK", jdbc.sql("update runtime.dispatch_intents di set state = 'ACKED', updated_at = now() from runtime.execution_attempts ea where di.work_item_id = ea.work_item_id and di.attempt_id = ea.id and di.tenant_id = :tenantId and ea.id = :attemptId and di.state = 'DISPATCHING'")
                    .param("tenantId", tenantId).param("attemptId", attemptId));
            return null;
        });
    }

    @Override
    public void heartbeat(UUID tenantId, UUID attemptId, UUID workerId, long fencingToken, Duration leaseDuration) {
        if (leaseDuration == null || leaseDuration.isNegative() || leaseDuration.isZero()) throw new IllegalArgumentException("leaseDuration must be positive");
        inTenant(tenantId, () -> {
            updateOrThrow("STALE_LEASE_HEARTBEAT", jdbc.sql("update runtime.worker_leases set heartbeat_at = now(), expires_at = now() + cast(:leaseDuration as interval) where tenant_id = :tenantId and attempt_id = :attemptId and worker_id = :workerId and fencing_token = :fence and expires_at > now()")
                    .param("tenantId", tenantId).param("attemptId", attemptId).param("workerId", workerId).param("fence", fencingToken).param("leaseDuration", leaseDuration.toSeconds() + " seconds"));
            updateOrThrow("STALE_ATTEMPT_HEARTBEAT", jdbc.sql("update runtime.execution_attempts set heartbeat_at = now() where tenant_id = :tenantId and id = :attemptId and worker_id = :workerId and fencing_token = :fence and status = 'RUNNING'")
                    .param("tenantId", tenantId).param("attemptId", attemptId).param("workerId", workerId).param("fence", fencingToken));
            return null;
        });
    }

    @Override
    public void checkpoint(Checkpoint checkpoint) {
        inTenant(checkpoint.tenantId(), () -> {
            commitCheckpoint(checkpoint);
            return null;
        });
    }

    @Override
    public void checkpoint(Checkpoint checkpoint, UUID workerId, long fencingToken) {
        ProductionRuntimeModels.require(workerId, "workerId");
        if (fencingToken < 1) throw new IllegalArgumentException("fencingToken must be positive");
        inTenant(checkpoint.tenantId(), () -> {
            long owned = jdbc.sql("""
                    select count(*)
                      from runtime.execution_attempts ea
                      join runtime.worker_leases wl
                        on wl.tenant_id = ea.tenant_id
                       and wl.work_item_id = ea.work_item_id
                       and wl.attempt_id = ea.id
                       and wl.worker_id = ea.worker_id
                       and wl.fencing_token = ea.fencing_token
                     where ea.tenant_id = :tenantId
                       and ea.id = :attemptId
                       and ea.work_item_id = :workItemId
                       and ea.worker_id = :workerId
                       and ea.fencing_token = :fence
                       and ea.status = 'RUNNING'
                       and wl.expires_at > now()
                    """)
                    .param("tenantId", checkpoint.tenantId())
                    .param("attemptId", checkpoint.attemptId())
                    .param("workItemId", checkpoint.workItemId())
                    .param("workerId", workerId)
                    .param("fence", fencingToken)
                    .query(Long.class).single();
            if (owned != 1) {
                throw new ProductionRuntimeException(
                        "STALE_CHECKPOINT_FENCE",
                        "checkpoint rejected because the worker no longer owns the live lease");
            }
            commitCheckpoint(checkpoint);
            return null;
        });
    }

    private void commitCheckpoint(Checkpoint checkpoint) {
        if (!checkpoint.stateHash().matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("checkpoint stateHash must be lowercase SHA-256");
        }
        jdbc.sql("insert into runtime.checkpoints (tenant_id, job_id, work_item_id, attempt_id, checkpoint_type, sequence_no, state_object_uri, state_hash) values (:tenantId, :jobId, :workItemId, :attemptId, :type, :sequence, :uri, :hash) on conflict (attempt_id, sequence_no) do nothing")
                .param("tenantId", checkpoint.tenantId()).param("jobId", checkpoint.jobId())
                .param("workItemId", checkpoint.workItemId()).param("attemptId", checkpoint.attemptId())
                .param("type", checkpoint.checkpointType()).param("sequence", checkpoint.sequenceNo())
                .param("uri", checkpoint.stateObjectUri()).param("hash", checkpoint.stateHash()).update();
        var stored = jdbc.sql("select checkpoint_type, state_object_uri, state_hash from runtime.checkpoints where tenant_id = :tenantId and attempt_id = :attemptId and sequence_no = :sequence")
                .param("tenantId", checkpoint.tenantId()).param("attemptId", checkpoint.attemptId())
                .param("sequence", checkpoint.sequenceNo())
                .query((rs, row) -> List.of(
                        rs.getString("checkpoint_type"),
                        rs.getString("state_object_uri"),
                        rs.getString("state_hash"))).single();
        if (!stored.equals(List.of(
                checkpoint.checkpointType(), checkpoint.stateObjectUri(), checkpoint.stateHash()))) {
            throw new ProductionRuntimeException(
                    "CHECKPOINT_CONFLICT",
                    "checkpoint sequence was replayed with different durable state");
        }
    }

    @Override
    public void complete(Completion completion) {
        inTenant(completion.tenantId(), () -> {
            completeWithinTenant(completion);
            return null;
        });
    }

    @Override
    public void completeVerified(
            Completion completion,
            OutputVerificationReceipt receipt
    ) {
        Objects.requireNonNull(receipt, "receipt");
        if (completion.status() != AttemptStatus.SUCCEEDED) {
            throw new IllegalArgumentException(
                    "completeVerified is only valid for successful completions");
        }
        inTenant(completion.tenantId(), () -> {
            WorkloadIdentity identity = jdbc.sql("""
                    select j.job_type, wi.work_type
                      from orchestration.work_items wi
                      join orchestration.jobs j
                        on j.tenant_id = wi.tenant_id and j.id = wi.job_id
                     where wi.tenant_id = :tenantId and wi.id = :workItemId
                     for update of wi
                    """)
                    .param("tenantId", completion.tenantId())
                    .param("workItemId", completion.workItemId())
                    .query((rs, row) -> new WorkloadIdentity(
                            rs.getString("job_type"),
                            rs.getString("work_type")))
                    .optional().orElseThrow(() -> new ProductionRuntimeException(
                            "OUTPUT_VERIFICATION_WORK_ITEM_NOT_FOUND",
                            "output verification references an unknown work item"));
            ProductionWorkloadPackCatalog.verifyOutput(
                    identity.jobType(), identity.workType(), receipt);
            String checksJson = outputChecksJson(receipt);
            int inserted = jdbc.sql("""
                    insert into runtime.output_verification_receipts
                      (tenant_id, work_item_id, attempt_id, schema_version,
                       pack_id, job_type, work_type, artifact_uri,
                       artifact_sha256, verifier, verification_status,
                       certification_status, checks)
                    values
                      (:tenantId, :workItemId, :attemptId, :schemaVersion,
                       :packId, :jobType, :workType, :artifactUri,
                       :artifactSha256, :verifier, :verificationStatus,
                       :certificationStatus, cast(:checks as jsonb))
                    on conflict (attempt_id) do nothing
                    """)
                    .param("tenantId", completion.tenantId())
                    .param("workItemId", completion.workItemId())
                    .param("attemptId", completion.attemptId())
                    .param("schemaVersion", receipt.schemaVersion())
                    .param("packId", receipt.packId())
                    .param("jobType", receipt.jobType())
                    .param("workType", receipt.workType())
                    .param("artifactUri", receipt.artifactUri())
                    .param("artifactSha256", receipt.artifactSha256())
                    .param("verifier", receipt.verifier())
                    .param("verificationStatus", receipt.verificationStatus())
                    .param("certificationStatus", receipt.certificationStatus())
                    .param("checks", checksJson)
                    .update();
            boolean exactReplay = jdbc.sql("""
                    select count(*) = 1
                      from runtime.output_verification_receipts
                     where tenant_id = :tenantId
                       and work_item_id = :workItemId
                       and attempt_id = :attemptId
                       and schema_version = :schemaVersion
                       and pack_id = :packId
                       and job_type = :jobType
                       and work_type = :workType
                       and artifact_uri = :artifactUri
                       and artifact_sha256 = :artifactSha256
                       and verifier = :verifier
                       and verification_status = :verificationStatus
                       and certification_status = :certificationStatus
                       and checks = cast(:checks as jsonb)
                    """)
                    .param("tenantId", completion.tenantId())
                    .param("workItemId", completion.workItemId())
                    .param("attemptId", completion.attemptId())
                    .param("schemaVersion", receipt.schemaVersion())
                    .param("packId", receipt.packId())
                    .param("jobType", receipt.jobType())
                    .param("workType", receipt.workType())
                    .param("artifactUri", receipt.artifactUri())
                    .param("artifactSha256", receipt.artifactSha256())
                    .param("verifier", receipt.verifier())
                    .param("verificationStatus", receipt.verificationStatus())
                    .param("certificationStatus", receipt.certificationStatus())
                    .param("checks", checksJson)
                    .query(Boolean.class)
                    .single();
            if (!exactReplay) {
                throw new ProductionRuntimeException(
                        "OUTPUT_VERIFICATION_REPLAY_CONFLICT",
                        "attempt output verification was replayed with different evidence");
            }
            if (inserted == 1) {
                event(completion.tenantId(), "WORK_ITEM", completion.workItemId(),
                        "OUTPUT_VERIFICATION_RECORDED", Map.of(
                                "attemptId", completion.attemptId(),
                                "artifactSha256", receipt.artifactSha256(),
                                "packId", receipt.packId(),
                                "certificationStatus", receipt.certificationStatus()));
            }
            completeWithinTenant(completion);
            return null;
        });
    }

    private void completeWithinTenant(Completion completion) {
            var existing = jdbc.sql("""
                    select status, work_item_id, worker_id, fencing_token,
                           error_code, error_message
                      from runtime.execution_attempts
                     where tenant_id = :tenantId and id = :attemptId
                     for update
                    """)
                    .param("tenantId", completion.tenantId())
                    .param("attemptId", completion.attemptId())
                    .query((rs, row) -> new ExistingCompletion(
                            AttemptStatus.valueOf(rs.getString("status")),
                            rs.getObject("work_item_id", UUID.class),
                            rs.getObject("worker_id", UUID.class),
                            rs.getLong("fencing_token"),
                            rs.getString("error_code"),
                            rs.getString("error_message")))
                    .optional().orElseThrow(() -> new ProductionRuntimeException(
                            "STALE_FENCE_CONFLICT", "terminal commit references an unknown attempt"));
            if (switch (existing.status()) {
                case SUCCEEDED, FAILED, TIMED_OUT, LOST, CANCELLED -> true;
                default -> false;
            }) {
                boolean exactReplay = existing.status() == completion.status()
                        && existing.workItemId().equals(completion.workItemId())
                        && existing.workerId().equals(completion.workerId())
                        && existing.fencingToken() == completion.fencingToken()
                        && Objects.equals(existing.errorCode(), completion.errorCode())
                        && Objects.equals(existing.errorMessage(), completion.errorMessage());
                if (exactReplay) return;
                throw new ProductionRuntimeException(
                        "TERMINAL_COMPLETION_CONFLICT",
                        "attempt terminal state was replayed with different fields");
            }
            String terminal = completion.status() == AttemptStatus.SUCCEEDED ? "SUCCEEDED" : completion.status() == AttemptStatus.CANCELLED ? "CANCELLED" : "FAILED";
            int updated = jdbc.sql("""
                    update runtime.execution_attempts ea
                       set status = :attemptStatus, completed_at = now(), error_code = :errorCode, error_message = :errorMessage
                     where ea.tenant_id = :tenantId and ea.id = :attemptId and ea.work_item_id = :workItemId
                       and ea.worker_id = :workerId and ea.fencing_token = :fence
                       and ea.status in ('CREATED','RUNNING')
                       and exists (select 1 from runtime.worker_leases wl where wl.attempt_id = ea.id and wl.work_item_id = ea.work_item_id and wl.worker_id = ea.worker_id and wl.fencing_token = ea.fencing_token and wl.tenant_id = ea.tenant_id)
                    """).param("attemptStatus", completion.status().name()).param("errorCode", completion.errorCode()).param("errorMessage", completion.errorMessage()).param("tenantId", completion.tenantId()).param("attemptId", completion.attemptId()).param("workItemId", completion.workItemId()).param("workerId", completion.workerId()).param("fence", completion.fencingToken()).update();
            if (updated != 1) throw new ProductionRuntimeException("STALE_FENCE_CONFLICT", "terminal commit rejected for stale worker ownership");
            String next = terminal.equals("SUCCEEDED") || terminal.equals("CANCELLED") ? terminal : "RETRY_WAIT";
            updateOrThrow("STALE_WORK_ITEM_COMPLETION", jdbc.sql("update orchestration.work_items set status = case when :next = 'RETRY_WAIT' and retry_count < max_retries then 'RETRY_WAIT' when :next = 'RETRY_WAIT' then 'FAILED' else :next end, retry_count = case when :next = 'RETRY_WAIT' then retry_count + 1 else retry_count end, completed_at = case when :next <> 'RETRY_WAIT' or retry_count + 1 >= max_retries then now() else null end, ready_at = case when :next = 'RETRY_WAIT' and retry_count < max_retries then now() else null end, updated_at = now() where tenant_id = :tenantId and id = :workItemId")
                    .param("next", next).param("tenantId", completion.tenantId()).param("workItemId", completion.workItemId()));
            jdbc.sql("delete from runtime.worker_leases where tenant_id = :tenantId and attempt_id = :attemptId and worker_id = :workerId and fencing_token = :fence")
                    .param("tenantId", completion.tenantId()).param("attemptId", completion.attemptId()).param("workerId", completion.workerId()).param("fence", completion.fencingToken()).update();
            if (next.equals("SUCCEEDED") || next.equals("CANCELLED") || next.equals("FAILED")) {
                jdbc.sql("update runtime.dispatch_intents set state = 'COMPLETED', updated_at = now() where tenant_id = :tenantId and attempt_id = :attemptId and state in ('ACKED','DISPATCHING')")
                        .param("tenantId", completion.tenantId()).param("attemptId", completion.attemptId()).update();
            } else {
                jdbc.sql("update runtime.dispatch_intents set state = 'ABORTED', last_error = :error, updated_at = now() where tenant_id = :tenantId and attempt_id = :attemptId and state in ('ACKED','DISPATCHING')")
                        .param("tenantId", completion.tenantId()).param("attemptId", completion.attemptId()).param("error", completion.errorCode()).update();
            }
            event(completion.tenantId(), "WORK_ITEM", completion.workItemId(), "ATTEMPT_COMPLETED", Map.of("attemptId", completion.attemptId(), "status", completion.status().name()));
            UUID jobId = jdbc.sql("select job_id from orchestration.work_items where tenant_id = :tenantId and id = :workItemId")
                    .param("tenantId", completion.tenantId())
                    .param("workItemId", completion.workItemId())
                    .query(UUID.class)
                    .single();
            jdbc.sql("select orchestration.advance_job_stages(:tenantId, :jobId)")
                    .param("tenantId", completion.tenantId())
                    .param("jobId", jobId)
                    .query(Integer.class)
                    .single();
    }

    private String outputChecksJson(OutputVerificationReceipt receipt) {
        try {
            return json.writeValueAsString(receipt.checks());
        } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
            throw new ProductionRuntimeException(
                    "OUTPUT_VERIFICATION_SERIALIZATION_FAILED",
                    "output verification checks could not be serialized", ex);
        }
    }

    @Override
    public void applyFinalUsage(UUID tenantId, UUID workItemId, ProductionRuntimeModels.FinalUsage usage) {
        inTenant(tenantId, () -> {
            jdbc.sql("insert into runtime.settlement_requests (tenant_id, work_item_id, reservation_id, model_call_id, provider, model, provider_usage_id, provider_pricing_version_id, commercial_pricing_version_id, input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, provider_total_cost, customer_credit_cost) values (:tenantId, :workItemId, :reservationId, :modelCallId, :provider, :model, :providerUsageId, :providerPricing, :commercialPricing, :inputTokens, :cachedInputTokens, :outputTokens, :reasoningTokens, :providerCost, :creditCost) on conflict (tenant_id, work_item_id) do nothing")
                    .param("tenantId", tenantId).param("workItemId", workItemId).param("reservationId", usage.reservationId()).param("modelCallId", usage.modelCallId()).param("provider", usage.provider()).param("model", usage.model()).param("providerUsageId", usage.providerUsageId()).param("providerPricing", usage.providerPricingVersionId()).param("commercialPricing", usage.commercialPricingVersionId()).param("inputTokens", usage.inputTokens()).param("cachedInputTokens", usage.cachedInputTokens()).param("outputTokens", usage.outputTokens()).param("reasoningTokens", usage.reasoningTokens()).param("providerCost", usage.providerTotalCost()).param("creditCost", usage.customerCreditCost()).update();
            var persisted = jdbc.sql("select reservation_id, model_call_id, provider, model, provider_usage_id, provider_pricing_version_id, commercial_pricing_version_id, input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, provider_total_cost, customer_credit_cost from runtime.settlement_requests where tenant_id = :tenantId and work_item_id = :workItemId")
                    .param("tenantId", tenantId).param("workItemId", workItemId).query((rs, row) -> new FinalUsage(tenantId, rs.getObject("reservation_id", UUID.class), rs.getObject("model_call_id", UUID.class), rs.getString("provider"), rs.getString("model"), rs.getString("provider_usage_id"), rs.getObject("provider_pricing_version_id", UUID.class), rs.getObject("commercial_pricing_version_id", UUID.class), rs.getLong("input_tokens"), rs.getLong("cached_input_tokens"), rs.getLong("output_tokens"), rs.getLong("reasoning_tokens"), rs.getBigDecimal("provider_total_cost"), rs.getBigDecimal("customer_credit_cost"))).single();
            if (!persisted.equals(usage)) throw new ProductionRuntimeException("FINAL_USAGE_CONFLICT", "work item final usage was replayed with different values");
            long tokens = usage.inputTokens() + usage.outputTokens() + usage.reasoningTokens();
            updateOrThrow("STALE_WORK_ITEM_USAGE", jdbc.sql("update orchestration.work_items set consumed_tokens = :tokens, actual_cost = :credits, updated_at = now() where tenant_id = :tenantId and id = :workItemId")
                    .param("tokens", tokens).param("credits", usage.customerCreditCost()).param("tenantId", tenantId).param("workItemId", workItemId));
            return null;
        });
    }

    @Override
    public List<ProductionRuntimeModels.SettlementRequest> pendingSettlementRequests(UUID tenantId, int limit) {
        int bounded = Math.max(1, Math.min(limit, 1_000));
        return inTenant(tenantId, () -> jdbc.sql("select work_item_id, reservation_id, model_call_id, provider, model, provider_usage_id, provider_pricing_version_id, commercial_pricing_version_id, input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, provider_total_cost, customer_credit_cost from runtime.settlement_requests where tenant_id = :tenantId and settled_at is null order by created_at, work_item_id limit :limit")
                .param("tenantId", tenantId).param("limit", bounded).query((rs, row) -> {
                    UUID workItemId = rs.getObject("work_item_id", UUID.class);
                    FinalUsage usage = new FinalUsage(tenantId, rs.getObject("reservation_id", UUID.class), rs.getObject("model_call_id", UUID.class), rs.getString("provider"), rs.getString("model"), rs.getString("provider_usage_id"), rs.getObject("provider_pricing_version_id", UUID.class), rs.getObject("commercial_pricing_version_id", UUID.class), rs.getLong("input_tokens"), rs.getLong("cached_input_tokens"), rs.getLong("output_tokens"), rs.getLong("reasoning_tokens"), rs.getBigDecimal("provider_total_cost"), rs.getBigDecimal("customer_credit_cost"));
                    return new ProductionRuntimeModels.SettlementRequest(workItemId, usage);
                }).list());
    }

    @Override
    public void markSettlementSettled(UUID tenantId, UUID workItemId) {
        inTenant(tenantId, () -> {
            jdbc.sql("update runtime.settlement_requests set settled_at = now() where tenant_id = :tenantId and work_item_id = :workItemId and settled_at is null")
                    .param("tenantId", tenantId).param("workItemId", workItemId).update();
            return null;
        });
    }

    @Override
    public java.util.Optional<UUID> activeReservationForWorkItem(UUID tenantId, UUID workItemId) {
        return inTenant(tenantId, () -> jdbc.sql("select id from billing.credit_reservations where tenant_id = :tenantId and work_item_id = :workItemId and status = 'ACTIVE' order by created_at desc limit 1")
                .param("tenantId", tenantId).param("workItemId", workItemId).query(UUID.class).optional());
    }

    @Override
    public int resumeCreditWaiting(UUID tenantId, int limit) {
        int bounded = Math.max(1, Math.min(limit, 1_000));
        return inTenant(tenantId, () -> jdbc.sql("""
                with candidates as (
                    select id from orchestration.work_items
                     where tenant_id = :tenantId and status = 'WAITING_FOR_CREDIT'
                     order by priority desc, created_at, id
                     limit :limit for update skip locked
                )
                update orchestration.work_items wi
                   set status = 'READY', ready_at = now(), updated_at = now()
                 where wi.id in (select id from candidates)
                """).param("tenantId", tenantId).param("limit", bounded).update());
    }

    @Override
    public int expireLeases(Duration gracePeriod) {
        return expireLeases(null, gracePeriod);
    }

    @Override
    public int expireLeases(UUID tenantId, Duration gracePeriod) {
        Duration grace = gracePeriod == null ? Duration.ZERO : gracePeriod;
        return transactions.execute(status -> {
            if (tenantId != null) {
                jdbc.sql("select set_config('app.tenant_id', :tenantId, true)")
                        .param("tenantId", tenantId.toString()).query(String.class).single();
            }
            String leaseQuery = tenantId == null
                    ? "select tenant_id, work_item_id, attempt_id, worker_id, fencing_token from runtime.worker_leases where expires_at < now() - cast(:grace as interval) for update skip locked"
                    : "select tenant_id, work_item_id, attempt_id, worker_id, fencing_token from runtime.worker_leases where tenant_id = :tenantId and expires_at < now() - cast(:grace as interval) for update skip locked";
            var leaseStatement = jdbc.sql(leaseQuery).param("grace", grace.toSeconds() + " seconds");
            if (tenantId != null) {
                leaseStatement = leaseStatement.param("tenantId", tenantId);
            }
            List<ExpiredLease> expired = leaseStatement.query((rs, row) -> new ExpiredLease(rs.getObject("tenant_id", UUID.class), rs.getObject("work_item_id", UUID.class), rs.getObject("attempt_id", UUID.class), rs.getObject("worker_id", UUID.class), rs.getLong("fencing_token"))).list();
            for (ExpiredLease lease : expired) {
                jdbc.sql("update runtime.execution_attempts set status = 'LOST', completed_at = now(), error_code = 'LEASE_EXPIRED' where id = :attemptId and status in ('CREATED','RUNNING')")
                        .param("attemptId", lease.attemptId()).update();
                jdbc.sql("update orchestration.work_items set status = case when retry_count < max_retries then 'RETRY_WAIT' else 'FAILED' end, retry_count = retry_count + 1, ready_at = case when retry_count < max_retries then now() else null end, updated_at = now() where tenant_id = :tenantId and id = :workItemId")
                        .param("tenantId", lease.tenantId()).param("workItemId", lease.workItemId()).update();
                jdbc.sql("delete from runtime.worker_leases where tenant_id = :tenantId and attempt_id = :attemptId and fencing_token = :fence")
                        .param("tenantId", lease.tenantId()).param("attemptId", lease.attemptId()).param("fence", lease.fencingToken()).update();
            }
            return expired.size();
        });
    }

    @Override
    public int abortDispatch(UUID tenantId, UUID dispatchIntentId, String reason) {
        return inTenant(tenantId, () -> {
            String boundedReason = reason == null ? "UNSPECIFIED" : reason.substring(0, Math.min(500, reason.length()));
            int updated = jdbc.sql("update runtime.dispatch_intents set state = 'ABORTED', last_error = :reason, updated_at = now() where tenant_id = :tenantId and id = :id and state not in ('COMPLETED','ABORTED')")
                    .param("tenantId", tenantId).param("id", dispatchIntentId).param("reason", boundedReason).update();
            if (updated == 1) {
                jdbc.sql("update runtime.execution_attempts ea set status = 'FAILED', completed_at = now(), error_code = 'DISPATCH_ABORTED', error_message = :reason where ea.tenant_id = :tenantId and ea.id = (select di.attempt_id from runtime.dispatch_intents di where di.tenant_id = :tenantId and di.id = :id) and ea.status in ('CREATED','RUNNING')")
                        .param("tenantId", tenantId).param("id", dispatchIntentId).param("reason", boundedReason).update();
                jdbc.sql("delete from runtime.worker_leases where tenant_id = :tenantId and work_item_id = (select work_item_id from runtime.dispatch_intents where tenant_id = :tenantId and id = :id)")
                        .param("tenantId", tenantId).param("id", dispatchIntentId).update();
                jdbc.sql("update orchestration.work_items wi set status = case when wi.retry_count < wi.max_retries then 'RETRY_WAIT' else 'FAILED' end, retry_count = wi.retry_count + 1, ready_at = case when wi.retry_count < wi.max_retries then now() else null end, completed_at = case when wi.retry_count < wi.max_retries then null else now() end, updated_at = now() where wi.tenant_id = :tenantId and wi.id = (select work_item_id from runtime.dispatch_intents where tenant_id = :tenantId and id = :id) and wi.status in ('RESERVING','RESERVED','DISPATCHING')")
                        .param("tenantId", tenantId).param("id", dispatchIntentId).update();
                event(tenantId, "DISPATCH_INTENT", dispatchIntentId, "DISPATCH_ABORTED", Map.of("reason", boundedReason));
            }
            return updated;
        });
    }

    @Override
    public List<DispatchIntent> recoveryCandidates(int limit) {
        int bounded = Math.max(1, Math.min(limit, 500));
        return jdbc.sql("select * from runtime.recovery_candidates(:limit)").param("limit", bounded).query(this::readIntent).list();
    }

    @Override
    public List<ReadyWorkItem> selectFairReady(int limit) {
        int bounded = Math.max(1, Math.min(limit, 1_000));
        return jdbc.sql("select * from runtime.select_fair_ready_work_items(:limit)")
                .param("limit", bounded)
                .query((rs, row) -> new ReadyWorkItem(
                        rs.getObject("tenant_id", UUID.class),
                        rs.getObject("account_id", UUID.class),
                        rs.getObject("project_id", UUID.class),
                        rs.getObject("job_id", UUID.class),
                        rs.getObject("stage_id", UUID.class),
                        rs.getObject("work_item_id", UUID.class),
                        rs.getObject("wallet_id", UUID.class),
                        rs.getObject("worker_id", UUID.class),
                        rs.getString("job_type"),
                        rs.getString("work_type"),
                        rs.getString("resource_key"),
                        rs.getInt("priority"),
                        rs.getInt("retry_count"),
                        rs.getBigDecimal("estimated_credits"),
                        rs.getObject("ready_at", OffsetDateTime.class).toInstant(),
                        rs.getObject("created_at", OffsetDateTime.class).toInstant()))
                .list();
    }

    @Override
    public List<UUID> pendingSettlementTenants(int limit) {
        int bounded = Math.max(1, Math.min(limit, 1_000));
        return jdbc.sql("select tenant_id from runtime.pending_settlement_tenants(:limit)")
                .param("limit", bounded).query(UUID.class).list();
    }

    @Override
    public List<ProductionRuntimeModels.JobProjectionCandidate> projectionCandidates(int limit) {
        int bounded = Math.max(1, Math.min(limit, 1_000));
        return jdbc.sql("select * from observability.projection_candidates(:limit)")
                .param("limit", bounded)
                .query((rs, row) -> new ProductionRuntimeModels.JobProjectionCandidate(
                        rs.getObject("tenant_id", UUID.class),
                        rs.getObject("job_id", UUID.class)))
                .list();
    }

    @Override
    public Duration projectionFreshness(UUID tenantId, UUID jobId) {
        return inTenant(tenantId, () -> jdbc.sql("""
                        select greatest(0, extract(epoch from (
                                   greatest(j.updated_at, coalesce(max(wi.updated_at), j.updated_at))
                                   - ps.updated_at
                               )) * 1000)
                          from orchestration.jobs j
                          left join orchestration.work_items wi
                            on wi.tenant_id = j.tenant_id and wi.job_id = j.id
                          left join observability.progress_snapshots ps
                            on ps.tenant_id = j.tenant_id and ps.job_id = j.id
                         where j.tenant_id = :tenantId and j.id = :jobId
                         group by j.updated_at, ps.updated_at
                        """)
                .param("tenantId", tenantId).param("jobId", jobId)
                .query(BigDecimal.class).optional()
                .map(value -> Duration.ofMillis(value.longValue()))
                .orElse(Duration.ofDays(36500)));
    }

    @Override
    public java.util.Optional<ProductionRuntimeModels.WorkloadOutputStatus>
            workloadOutputStatus(UUID tenantId, UUID jobId, UUID workItemId) {
        ProductionRuntimeModels.require(tenantId, "tenantId");
        ProductionRuntimeModels.require(jobId, "jobId");
        ProductionRuntimeModels.require(workItemId, "workItemId");
        return inTenant(tenantId, () -> jdbc.sql("""
                        select j.id as job_id, wi.id as work_item_id,
                               j.job_type, wi.work_type,
                               j.status as job_status,
                               wi.status as work_item_status,
                               receipt.artifact_sha256,
                               receipt.verification_status,
                               receipt.certification_status,
                               receipt.created_at as verified_at
                          from orchestration.jobs j
                          join orchestration.work_items wi
                            on wi.tenant_id = j.tenant_id and wi.job_id = j.id
                          left join lateral (
                               select r.artifact_sha256,
                                      r.verification_status,
                                      r.certification_status,
                                      r.created_at
                                 from runtime.output_verification_receipts r
                                where r.tenant_id = wi.tenant_id
                                  and r.work_item_id = wi.id
                                order by r.created_at desc, r.id desc
                                limit 1
                          ) receipt on true
                         where j.tenant_id = :tenantId
                           and j.id = :jobId
                           and wi.id = :workItemId
                        """)
                .param("tenantId", tenantId)
                .param("jobId", jobId)
                .param("workItemId", workItemId)
                .query((rs, row) -> {
                    OffsetDateTime verifiedAt = rs.getObject(
                            "verified_at", OffsetDateTime.class);
                    return new ProductionRuntimeModels.WorkloadOutputStatus(
                            rs.getObject("job_id", UUID.class),
                            rs.getObject("work_item_id", UUID.class),
                            rs.getString("job_type"),
                            rs.getString("work_type"),
                            rs.getString("job_status"),
                            rs.getString("work_item_status"),
                            rs.getString("artifact_sha256"),
                            rs.getString("verification_status"),
                            rs.getString("certification_status"),
                            verifiedAt == null ? null : verifiedAt.toInstant());
                })
                .optional());
    }

    @Override
    public ProgressSnapshot rebuildProgress(UUID tenantId, UUID jobId) {
        return inTenant(tenantId, () -> {
            var counts = jdbc.sql("""
                    select j.project_id,
                           count(wi.id) total,
                           count(*) filter (where wi.status in ('READY','RETRY_WAIT','RESERVING','WAITING_FOR_CREDIT','RESERVED','DISPATCHING')) ready,
                           count(*) filter (where wi.status = 'RUNNING') running,
                           count(*) filter (where wi.status = 'SUCCEEDED') completed,
                           count(*) filter (where wi.status in ('FAILED','CANCELLED')) failed,
                           coalesce(sum(wi.consumed_tokens), 0) tokens,
                           coalesce(sum(wi.actual_cost), 0) credits
                      from orchestration.jobs j
                      left join orchestration.work_items wi on wi.job_id = j.id and wi.tenant_id = j.tenant_id
                     where j.tenant_id = :tenantId and j.id = :jobId
                     group by j.project_id
                    """).param("tenantId", tenantId).param("jobId", jobId).query((rs, row) -> new ProgressCounts(rs.getObject("project_id", UUID.class), rs.getLong("total"), rs.getLong("ready"), rs.getLong("running"), rs.getLong("completed"), rs.getLong("failed"), rs.getLong("tokens"), rs.getBigDecimal("credits"))).single();
            BigDecimal progress = counts.total() == 0 ? BigDecimal.ZERO : BigDecimal.valueOf(counts.completed()).multiply(BigDecimal.valueOf(100)).divide(BigDecimal.valueOf(counts.total()), 2, java.math.RoundingMode.HALF_UP);
            jdbc.sql("""
                    insert into observability.progress_snapshots
                      (job_id, project_id, tenant_id, total_work_items, ready_work_items,
                       running_work_items, completed_work_items, failed_work_items, progress,
                       tokens_consumed, credits_consumed, metered_credits, updated_at)
                    values (:jobId, :projectId, :tenantId, :total, :ready, :running, :completed,
                            :failed, :progress, :tokens, :credits, :credits, now())
                    on conflict (job_id) do update set total_work_items = excluded.total_work_items,
                      ready_work_items = excluded.ready_work_items, running_work_items = excluded.running_work_items,
                      completed_work_items = excluded.completed_work_items, failed_work_items = excluded.failed_work_items,
                      progress = excluded.progress, tokens_consumed = excluded.tokens_consumed,
                      credits_consumed = excluded.credits_consumed, metered_credits = excluded.metered_credits,
                      updated_at = now()
                    """).param("jobId", jobId).param("projectId", counts.projectId()).param("tenantId", tenantId).param("total", counts.total()).param("ready", counts.ready()).param("running", counts.running()).param("completed", counts.completed()).param("failed", counts.failed()).param("progress", progress).param("tokens", counts.tokens()).param("credits", counts.credits()).update();
            return new ProgressSnapshot(tenantId, counts.projectId(), jobId, counts.total(), counts.ready(), counts.running(), counts.completed(), counts.failed(), progress, counts.tokens(), counts.credits(), Instant.now());
        });
    }

    @Override
    public List<ProductionRuntimeModels.OutboxMessage> claimOutbox(int limit, Duration claimDuration) {
        int bounded = Math.max(1, Math.min(limit, 1_000));
        Duration duration = claimDuration == null ? Duration.ofSeconds(30) : claimDuration;
        if (duration.isNegative() || duration.isZero() || duration.compareTo(Duration.ofHours(1)) > 0) throw new IllegalArgumentException("claimDuration out of range");
        return transactions.execute(status -> {
            UUID claimToken = UUID.randomUUID();
            return jdbc.sql("select * from observability.claim_outbox(:limit, :claimToken, cast(:claimSeconds as integer))")
                    .param("limit", bounded).param("claimToken", claimToken).param("claimSeconds", duration.toSeconds())
                    .query((rs, row) -> new ProductionRuntimeModels.OutboxMessage(rs.getLong("id"), rs.getObject("tenant_id", UUID.class), rs.getString("aggregate_type"), rs.getObject("aggregate_id", UUID.class), rs.getString("event_type"), rs.getString("payload_json"), rs.getObject("claim_token", UUID.class))).list();
        });
    }

    @Override
    public void markOutboxPublished(UUID claimToken, long eventId) {
        updateOutboxClaim(claimToken, eventId, true, null);
    }

    @Override
    public void markOutboxFailed(UUID claimToken, long eventId, String error) {
        updateOutboxClaim(claimToken, eventId, false, error);
    }

    private void updateOutboxClaim(UUID claimToken, long eventId, boolean published, String error) {
        transactions.execute(status -> {
            String function = published ? "observability.mark_outbox_published(:claimToken, :id)" : "observability.mark_outbox_failed(:claimToken, :id, :error)";
            var statement = jdbc.sql("select " + function).param("claimToken", claimToken).param("id", eventId);
            if (!published) statement = statement.param("error", error == null ? null : error.substring(0, Math.min(error.length(), 1_000)));
            Boolean updated = statement.query(Boolean.class).single();
            if (!Boolean.TRUE.equals(updated)) throw new ProductionRuntimeException("OUTBOX_CLAIM_CONFLICT", "outbox event is no longer owned by publisher");
            return null;
        });
    }

    @Override
    public List<String> invariantViolations(UUID tenantId) {
        return inTenant(tenantId, () -> jdbc.sql(
                        "select code, violation_count from observability.tenant_invariant_violations(:tenantId)")
                .param("tenantId", tenantId)
                .query((rs, row) -> rs.getString("code") + ":" + rs.getLong("violation_count"))
                .list());
    }

    private DispatchEnvelope existingEnvelope(UUID tenantId, DispatchIntent intent, Map<String, Object> payload) {
        if (intent.attemptId() == null || intent.workerId() == null) throw new ProductionRuntimeException("DISPATCH_INTENT_INCOMPLETE", "dispatching intent has no attempt");
        String endpoint = jdbc.sql("select endpoint_uri from runtime.workers where id = :workerId").param("workerId", intent.workerId()).query(String.class).single();
        return new DispatchEnvelope(tenantId, intent.workItemId(), intent.attemptId(), intent.workerId(), intent.fencingToken(), endpoint, intent.dispatchIdempotencyKey(), payload == null ? Map.of() : Map.copyOf(payload));
    }

    private Map<String, Object> resumePayload(
            UUID tenantId,
            UUID workItemId,
            Map<String, Object> payload
    ) {
        Map<String, Object> result = new LinkedHashMap<>(
                payload == null ? Map.of() : payload);
        // A caller cannot manufacture a trusted resume pointer. Only the
        // latest PostgreSQL-committed checkpoint may populate this field.
        result.remove("resumeCheckpoint");
        jdbc.sql("""
                select attempt_id, checkpoint_type, sequence_no,
                       state_object_uri, state_hash, created_at
                  from runtime.checkpoints
                 where tenant_id = :tenantId and work_item_id = :workItemId
                 order by created_at desc, sequence_no desc, attempt_id desc
                 limit 1
                """)
                .param("tenantId", tenantId)
                .param("workItemId", workItemId)
                .query((rs, row) -> Map.<String, Object>of(
                        "sourceAttemptId", rs.getObject("attempt_id", UUID.class).toString(),
                        "checkpointType", rs.getString("checkpoint_type"),
                        "sequenceNo", rs.getLong("sequence_no"),
                        "stateObjectUri", rs.getString("state_object_uri"),
                        "stateHash", rs.getString("state_hash"),
                        "committedAt", rs.getObject("created_at", OffsetDateTime.class)
                                .toInstant().toString()))
                .optional()
                .ifPresent(checkpoint -> result.put("resumeCheckpoint", checkpoint));
        return Map.copyOf(result);
    }

    private DispatchIntent lockIntent(UUID tenantId, UUID intentId) { return jdbc.sql("select * from runtime.dispatch_intents where tenant_id = :tenantId and id = :id for update").param("tenantId", tenantId).param("id", intentId).query(this::readIntent).single(); }

    private DispatchIntent readIntent(ResultSet rs, int row) throws java.sql.SQLException {
        return new DispatchIntent(rs.getObject("id", UUID.class), rs.getObject("tenant_id", UUID.class), rs.getObject("work_item_id", UUID.class), DispatchState.valueOf(rs.getString("state")), rs.getObject("reservation_id", UUID.class), rs.getObject("worker_id", UUID.class), rs.getObject("attempt_id", UUID.class), rs.getObject("fencing_token") == null ? 0 : rs.getLong("fencing_token"), rs.getString("reservation_idempotency_key"), rs.getString("dispatch_idempotency_key"), rs.getObject("project_id", UUID.class), rs.getObject("job_id", UUID.class), rs.getObject("wallet_id", UUID.class), rs.getBigDecimal("estimated_credits"), rs.getObject("reservation_expires_at", OffsetDateTime.class).toInstant(), rs.getString("dispatch_payload"));
    }

    private void assertAccount(UUID tenantId, UUID accountId) { jdbc.sql("select 1 from identity.accounts where tenant_id = :tenantId and id = :accountId").param("tenantId", tenantId).param("accountId", accountId).query(Integer.class).optional().orElseThrow(() -> new ProductionRuntimeException("ACCOUNT_TENANT_MISMATCH", "account is not owned by tenant")); }
    private void assertProjectAccount(UUID tenantId, UUID accountId, UUID projectId) { jdbc.sql("select 1 from project.projects where tenant_id = :tenantId and account_id = :accountId and id = :projectId").param("tenantId", tenantId).param("accountId", accountId).param("projectId", projectId).query(Integer.class).optional().orElseThrow(() -> new ProductionRuntimeException("PROJECT_TENANT_MISMATCH", "project is not owned by account and tenant")); }
    private void assertStageJob(UUID tenantId, UUID jobId, UUID stageId) { jdbc.sql("select 1 from orchestration.job_stages where tenant_id = :tenantId and job_id = :jobId and id = :stageId").param("tenantId", tenantId).param("jobId", jobId).param("stageId", stageId).query(Integer.class).optional().orElseThrow(() -> new ProductionRuntimeException("STAGE_JOB_MISMATCH", "stage is not owned by job and tenant")); }
    private void assertWorkItemTenant(UUID tenantId, UUID id) { jdbc.sql("select 1 from orchestration.work_items where tenant_id = :tenantId and id = :id").param("tenantId", tenantId).param("id", id).query(Integer.class).optional().orElseThrow(() -> new ProductionRuntimeException("WORK_ITEM_TENANT_MISMATCH", "work item is not owned by tenant")); }

    private void assertAdmissionAvailable(
            UUID tenantId, UUID projectId, UUID jobId, UUID workItemId
    ) {
        jdbc.sql("select tenant_id from orchestration.admission_policies where tenant_id = :tenantId for update")
                .param("tenantId", tenantId).query(UUID.class).optional()
                .orElseThrow(() -> new ProductionRuntimeException(
                        "ADMISSION_POLICY_MISSING", "tenant has no durable admission policy"));
        List<String> blockers = jdbc.sql(
                        "select code from orchestration.admission_blockers(:tenantId, :projectId, :jobId, :workItemId)")
                .param("tenantId", tenantId).param("projectId", projectId)
                .param("jobId", jobId).param("workItemId", workItemId)
                .query(String.class).list();
        if (!blockers.isEmpty()) {
            throw new ProductionRuntimeException(
                    "ADMISSION_LIMIT_EXCEEDED", String.join(",", blockers));
        }
    }

    private void assertWorkerCapacity(UUID workerId, String capabilitiesJson) {
        try {
            int maximum = json.readTree(capabilitiesJson).path("maxConcurrent").asInt(0);
            if (maximum < 1 || maximum > 1024) {
                throw new ProductionRuntimeException(
                        "WORKER_CAPACITY_INVALID", "worker maxConcurrent is missing or invalid");
            }
            long active = jdbc.sql("select count(*) from runtime.worker_leases where worker_id = :workerId")
                    .param("workerId", workerId).query(Long.class).single();
            if (active >= maximum) {
                throw new ProductionRuntimeException(
                        "WORKER_CAPACITY_EXHAUSTED", "worker has no available lease slot");
            }
        } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
            throw new ProductionRuntimeException(
                    "WORKER_CAPACITY_INVALID", "worker capability document is invalid", ex);
        }
    }

    private void event(UUID tenantId, String aggregateType, UUID aggregateId, String type, Map<String, Object> payload) {
        try { jdbc.sql("insert into observability.outbox_events (tenant_id, aggregate_type, aggregate_id, event_type, payload) values (:tenantId, :aggregateType, :aggregateId, :type, cast(:payload as jsonb))").param("tenantId", tenantId).param("aggregateType", aggregateType).param("aggregateId", aggregateId).param("type", type).param("payload", json.writeValueAsString(payload)).update(); }
        catch (Exception ex) { throw new ProductionRuntimeException("OUTBOX_SERIALIZATION_FAILED", "could not serialize runtime event", ex); }
    }

    private void updateOrThrow(String code, JdbcClient.StatementSpec statement) { if (statement.update() != 1) throw new ProductionRuntimeException(code, "expected exactly one current owner row"); }
    private <T> T inTenant(UUID tenantId, java.util.function.Supplier<T> body) { return transactions.execute(status -> { jdbc.sql("select set_config('app.tenant_id', :tenantId, true)").param("tenantId", tenantId.toString()).query(String.class).single(); return body.get(); }); }

    private record WorkerRow(String endpointUri, String status, String capabilitiesJson) {}
    private record WorkloadIdentity(String jobType, String workType) {}
    private record ExistingCompletion(
            AttemptStatus status,
            UUID workItemId,
            UUID workerId,
            long fencingToken,
            String errorCode,
            String errorMessage
    ) {}
    private record ExpiredLease(UUID tenantId, UUID workItemId, UUID attemptId, UUID workerId, long fencingToken) {}
    private record ProgressCounts(UUID projectId, long total, long ready, long running, long completed, long failed, long tokens, BigDecimal credits) {}
}
