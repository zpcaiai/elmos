package io.elmos.productionworker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.elmos.productionruntime.JdbcProductionProviderPayloadStore;
import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
import io.elmos.productionruntime.ProductionRuntimeException;
import io.elmos.productionruntime.ProductionRuntimeModels.AttemptStatus;
import io.elmos.productionruntime.ProductionRuntimeModels.Checkpoint;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchEnvelope;
import io.elmos.productionruntime.ProductionRuntimeModels.OutputVerificationReceipt;
import io.elmos.productionruntime.ProductionWorkloadPackCatalog;
import jakarta.annotation.PreDestroy;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/** Bounded worker inbox and exact downstream workload execution protocol. */
final class ProductionWorkerAttemptService {
    private static final int MAX_ENGINE_RESPONSE_BYTES = 1_048_576;
    enum LocalStatus {
        ACKED, RUNNING, SUCCEEDED, FAILED, PROVIDER_OUTCOME_UNKNOWN,
        CHECKPOINT_OUTCOME_UNKNOWN, COMPLETION_OUTCOME_UNKNOWN
    }

    record AttemptView(
            UUID tenantId,
            UUID attemptId,
            UUID workerId,
            long fencingToken,
            String dispatchIdempotencyKey,
            LocalStatus status,
            Instant updatedAt,
            String errorCode
    ) {}
    record Acceptance(LocalStatus status, boolean existing) {}
    record CheckpointInput(
            long sequenceNo,
            String checkpointType,
            String stateObjectUri,
            String stateHash
    ) {
        CheckpointInput {
            if (sequenceNo < 1) throw new IllegalArgumentException("sequenceNo must be positive");
            requireText(checkpointType, "checkpointType", 100);
            requireText(stateObjectUri, "stateObjectUri", 2_000);
            if (stateHash == null || !stateHash.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("stateHash must be lowercase SHA-256");
            }
        }
    }

    private final ObjectMapper json;
    private final ObjectMapper canonicalJson;
    private final ProductionWorkerRouteCatalog routes;
    private final OwnerOnlyProviderCredentialFile credential;
    private final UUID workerId;
    private final URI controlPlane;
    private final int maxRetained;
    private final boolean meshHttp;
    private final HttpClient http;
    private final ProductionWorkerDurableJournal journal;
    private final ExecutorService executors;
    private final ScheduledExecutorService heartbeatScheduler;
    private final ScheduledExecutorService reconciliationScheduler;
    private final ExecutorService heartbeatExecutor;
    private final ExecutorService providerReconciliationExecutor;
    private final ExecutorService checkpointReconciliationExecutor;
    private final ExecutorService completionReconciliationExecutor;
    private final Semaphore heartbeatPermits;
    private final Set<UUID> heartbeatInFlight = ConcurrentHashMap.newKeySet();
    private final Set<UUID> providerReconciliationInFlight = ConcurrentHashMap.newKeySet();
    private final Set<UUID> checkpointReconciliationInFlight = ConcurrentHashMap.newKeySet();
    private final Set<UUID> completionReconciliationInFlight = ConcurrentHashMap.newKeySet();
    private final Map<UUID, AttemptState> attempts = new ConcurrentHashMap<>();
    private final AtomicBoolean closed = new AtomicBoolean();
    private volatile boolean journalHealthy = true;

    ProductionWorkerAttemptService(
            ObjectMapper json,
            ProductionWorkerRouteCatalog routes,
            OwnerOnlyProviderCredentialFile credential,
            UUID workerId,
            URI controlPlane,
            int concurrency,
            int maxRetained,
            Path stateDirectory,
            boolean meshHttp
    ) {
        this(json, routes, credential, workerId, controlPlane, concurrency,
                maxRetained, stateDirectory, meshHttp,
                Duration.ofSeconds(10), Duration.ofSeconds(10));
    }

    ProductionWorkerAttemptService(
            ObjectMapper json,
            ProductionWorkerRouteCatalog routes,
            OwnerOnlyProviderCredentialFile credential,
            UUID workerId,
            URI controlPlane,
            int concurrency,
            int maxRetained,
            Path stateDirectory,
            boolean meshHttp,
            Duration heartbeatInterval,
            Duration reconciliationInterval
    ) {
        this.json = Objects.requireNonNull(json, "json");
        this.canonicalJson = json.copy()
                .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
                .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
        this.routes = Objects.requireNonNull(routes, "routes");
        this.credential = Objects.requireNonNull(credential, "credential");
        this.workerId = Objects.requireNonNull(workerId, "workerId");
        this.controlPlane = validateEndpoint(controlPlane, meshHttp);
        if (concurrency < 1 || concurrency > 1024) {
            throw new IllegalArgumentException("worker concurrency must be between 1 and 1024");
        }
        if (maxRetained < concurrency || maxRetained > 1_000_000) {
            throw new IllegalArgumentException("worker retained-attempt limit is invalid");
        }
        requireMaintenanceInterval(heartbeatInterval, "heartbeatInterval");
        requireMaintenanceInterval(reconciliationInterval, "reconciliationInterval");
        this.maxRetained = maxRetained;
        this.meshHttp = meshHttp;
        this.journal = new ProductionWorkerDurableJournal(stateDirectory);
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        this.executors = boundedExecutor(
                "elmos-worker-execution-", concurrency, maxRetained);
        this.heartbeatScheduler = Executors.newSingleThreadScheduledExecutor(
                namedPlatformFactory("elmos-worker-heartbeat-scheduler-"));
        this.reconciliationScheduler = Executors.newSingleThreadScheduledExecutor(
                namedPlatformFactory("elmos-worker-reconciliation-scheduler-"));
        this.heartbeatExecutor = Executors.newThreadPerTaskExecutor(
                Thread.ofVirtual().name("elmos-worker-heartbeat-", 0).factory());
        this.heartbeatPermits = new Semaphore(concurrency);
        int reconciliationThreads = Math.max(1, Math.min(concurrency, 8));
        int reconciliationQueueCapacity = Math.max(
                1, Math.min(maxRetained, Math.max(16, concurrency * 2)));
        this.providerReconciliationExecutor = boundedExecutor(
                "elmos-worker-provider-reconciliation-",
                reconciliationThreads, reconciliationQueueCapacity);
        this.checkpointReconciliationExecutor = boundedExecutor(
                "elmos-worker-checkpoint-reconciliation-",
                reconciliationThreads, reconciliationQueueCapacity);
        this.completionReconciliationExecutor = boundedExecutor(
                "elmos-worker-completion-reconciliation-",
                reconciliationThreads, reconciliationQueueCapacity);
        restoreJournal();
        this.heartbeatScheduler.scheduleWithFixedDelay(
                this::scheduleHeartbeatsSafely,
                initialDelayMillis(heartbeatInterval), heartbeatInterval.toMillis(),
                TimeUnit.MILLISECONDS);
        this.reconciliationScheduler.scheduleWithFixedDelay(
                this::scheduleReconciliationsSafely,
                initialDelayMillis(reconciliationInterval), reconciliationInterval.toMillis(),
                TimeUnit.MILLISECONDS);
    }

    synchronized Acceptance accept(DispatchEnvelope envelope) {
        Objects.requireNonNull(envelope, "envelope");
        if (closed.get()) {
            throw new ProductionRuntimeException(
                    "WORKER_SHUTTING_DOWN", "worker is not accepting new work while shutting down");
        }
        if (!journalHealthy) {
            throw new ProductionRuntimeException(
                    "WORKER_DURABLE_JOURNAL_FAILURE",
                    "worker cannot accept work while its durable journal is unhealthy");
        }
        if (!workerId.equals(envelope.workerId())) {
            throw new ProductionRuntimeException(
                    "WORKER_ID_MISMATCH", "dispatch targets a different worker identity");
        }
        ProductionWorkerRouteCatalog.Route route = requireRoute(envelope);
        String digest = digest(envelope);
        AttemptState existing = attempts.get(envelope.attemptId());
        if (existing != null) {
            if (!existing.envelopeDigest.equals(digest)
                    || existing.envelope.fencingToken() != envelope.fencingToken()) {
                throw new ProductionRuntimeException(
                        "WORKER_DISPATCH_IDEMPOTENCY_CONFLICT",
                        "attempt id was reused with different dispatch bytes");
            }
            return new Acceptance(existing.status, true);
        }
        if (attempts.size() >= maxRetained) evictTerminal();
        if (attempts.size() >= maxRetained) {
            throw new ProductionRuntimeException(
                    "WORKER_INBOX_CAPACITY_EXHAUSTED",
                    "worker cannot accept another attempt without losing reconciliation state");
        }
        AttemptState created = new AttemptState(envelope, digest, route);
        persist(created);
        attempts.put(envelope.attemptId(), created);
        submitExecution(created);
        return new Acceptance(LocalStatus.ACKED, false);
    }

    AttemptView find(UUID attemptId) {
        AttemptState state = attempts.get(attemptId);
        return state == null ? null
                : new AttemptView(
                        state.envelope.tenantId(), attemptId,
                        state.envelope.workerId(), state.envelope.fencingToken(),
                        state.envelope.dispatchIdempotencyKey(), state.status,
                        state.updatedAt, state.errorCode);
    }

    boolean checkpoint(
            UUID attemptId,
            UUID presentedWorkerId,
            long presentedFencingToken,
            String presentedIdempotencyKey,
            CheckpointInput input
    ) {
        AttemptState state = attempts.get(attemptId);
        if (state == null) {
            throw new ProductionRuntimeException(
                    "WORKER_ATTEMPT_NOT_FOUND", "checkpoint references an unknown worker attempt");
        }
        synchronized (state) {
            if (!state.envelope.workerId().equals(presentedWorkerId)
                    || state.envelope.fencingToken() != presentedFencingToken
                    || !state.envelope.dispatchIdempotencyKey().equals(presentedIdempotencyKey)) {
                throw new ProductionRuntimeException(
                        "WORKER_CHECKPOINT_OWNERSHIP_MISMATCH",
                        "checkpoint headers do not match the accepted dispatch owner");
            }
            CheckpointInput existing = state.checkpoints.get(input.sequenceNo());
            if (existing != null) {
                if (!existing.equals(input)) {
                    throw new ProductionRuntimeException(
                            "WORKER_CHECKPOINT_CONFLICT",
                            "checkpoint sequence was replayed with different durable state");
                }
                return true;
            }
            if (state.status != LocalStatus.RUNNING
                    && state.status != LocalStatus.CHECKPOINT_OUTCOME_UNKNOWN) {
                throw new ProductionRuntimeException(
                        "WORKER_CHECKPOINT_STATE_INVALID",
                        "checkpoint can only be committed by a live running attempt");
            }
            long expected = state.checkpoints.isEmpty()
                    ? 1L : state.checkpoints.lastKey() + 1L;
            if (input.sequenceNo() != expected) {
                throw new ProductionRuntimeException(
                        "WORKER_CHECKPOINT_SEQUENCE_GAP",
                        "checkpoint sequence must be strictly contiguous");
            }
            if (!deliverCheckpoint(state, input)) return false;
            state.checkpoints.put(input.sequenceNo(), input);
            state.touch();
            return true;
        }
    }

    private void submitExecution(AttemptState state) {
        try {
            executors.execute(() -> executeSafely(state));
        } catch (RejectedExecutionException ex) {
            failUnhandledExecution(state, "WORKER_EXECUTION_CAPACITY_UNAVAILABLE");
            throw new ProductionRuntimeException(
                    "WORKER_EXECUTION_CAPACITY_UNAVAILABLE",
                    "worker execution queue rejected the accepted attempt", ex);
        }
    }

    private void executeSafely(AttemptState state) {
        try {
            execute(state);
        } catch (RuntimeException ex) {
            String code = ex instanceof ProductionRuntimeException runtime
                    ? runtime.code() : "WORKER_EXECUTION_UNHANDLED";
            failUnhandledExecution(state, code);
        }
    }

    private void execute(AttemptState state) {
        state.transition(LocalStatus.RUNNING, null);
        try {
            byte[] body = json.writeValueAsBytes(state.envelope);
            HttpRequest request = authorized(
                    state.route.endpoint(), state.route.timeout(), state.envelope)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();
            EngineResponse response = sendEngine(request);
            if (response.status() >= 500 || response.status() == 408
                    || response.status() == 429) {
                state.transition(LocalStatus.PROVIDER_OUTCOME_UNKNOWN, "ENGINE_HTTP_" + response.status());
                return;
            }
            if (response.status() < 200 || response.status() >= 300) {
                callback(state, AttemptStatus.FAILED,
                        "ENGINE_HTTP_" + response.status(), null);
                return;
            }
            processEngineResult(state, json.readTree(response.body()));
        } catch (java.net.http.HttpTimeoutException ex) {
            state.transition(LocalStatus.PROVIDER_OUTCOME_UNKNOWN, "ENGINE_TIMEOUT_AFTER_SEND");
        } catch (IOException ex) {
            state.transition(LocalStatus.PROVIDER_OUTCOME_UNKNOWN, "ENGINE_TRANSPORT_UNKNOWN");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            state.transition(LocalStatus.PROVIDER_OUTCOME_UNKNOWN, "ENGINE_INTERRUPTED");
        } catch (RuntimeException ex) {
            String code = ex instanceof ProductionRuntimeException runtime
                    ? runtime.code() : "ENGINE_RESPONSE_INVALID";
            callback(state, AttemptStatus.FAILED, bounded(code, 120), null);
        }
    }

    private void failUnhandledExecution(AttemptState state, String code) {
        if (state.status == LocalStatus.SUCCEEDED || state.status == LocalStatus.FAILED
                || state.completionStatus != null) {
            return;
        }
        try {
            callback(state, AttemptStatus.FAILED, bounded(code, 120), null);
        } catch (RuntimeException ignored) {
            // rememberCompletion persists COMPLETION_OUTCOME_UNKNOWN before any
            // delivery attempt. If even that write failed, persist() has marked
            // the worker unhealthy so registration and new accepts fail closed.
        }
    }

    private void callback(
            AttemptState state,
            AttemptStatus status,
            String errorCode,
            JsonNode usage
    ) {
        callback(state, status, errorCode, usage, null);
    }

    private void callback(
            AttemptState state,
            AttemptStatus status,
            String errorCode,
            JsonNode usage,
            OutputVerificationReceipt outputVerification
    ) {
        state.rememberCompletion(
                status, errorCode, usage, outputVerification);
        submitCompletionReconciliation(state);
    }

    private void processEngineResult(AttemptState state, JsonNode result) {
        if (result == null || !result.isObject()) {
            throw new ProductionRuntimeException(
                    "ENGINE_RESPONSE_INVALID", "engine response must be a JSON object");
        }
        String status = result.path("status").asText("");
        if ("SUCCEEDED".equals(status)) {
            JsonNode checkpoints = result.path("checkpoints");
            if (!checkpoints.isMissingNode() && !checkpoints.isArray()) {
                throw new ProductionRuntimeException(
                        "ENGINE_CHECKPOINTS_INVALID", "engine checkpoints must be an array");
            }
            if (checkpoints.isArray()) {
                for (JsonNode value : checkpoints) {
                    CheckpointInput input = checkpointInput(value);
                    if (!checkpoint(
                            state.envelope.attemptId(), state.envelope.workerId(),
                            state.envelope.fencingToken(),
                            state.envelope.dispatchIdempotencyKey(), input)) {
                        state.pendingEngineResult = result.deepCopy();
                        state.transition(
                                LocalStatus.CHECKPOINT_OUTCOME_UNKNOWN,
                                "CHECKPOINT_DELIVERY_UNKNOWN");
                        submitCheckpointReconciliation(state);
                        return;
                    }
                }
            }
            state.pendingEngineResult = null;
            JsonNode usage = result.get("usage");
            OutputVerificationReceipt outputVerification = outputVerification(
                    state, result.get("outputVerification"));
            callback(state, AttemptStatus.SUCCEEDED, null, usage,
                    outputVerification);
            return;
        }
        if ("FAILED".equals(status)) {
            String error = bounded(
                    result.path("errorCode").asText("ENGINE_REPORTED_FAILURE"), 120);
            state.pendingEngineResult = null;
            callback(state, AttemptStatus.FAILED, error, null);
            return;
        }
        if ("RUNNING".equals(status) || "PENDING".equals(status)) {
            state.transition(LocalStatus.PROVIDER_OUTCOME_UNKNOWN, "ENGINE_STILL_RUNNING");
            return;
        }
        state.transition(LocalStatus.PROVIDER_OUTCOME_UNKNOWN, "ENGINE_RESPONSE_STATUS_UNKNOWN");
    }

    private OutputVerificationReceipt outputVerification(
            AttemptState state,
            JsonNode value
    ) {
        if (value == null || !value.isObject()) {
            throw new ProductionRuntimeException(
                    "ENGINE_OUTPUT_VERIFICATION_REQUIRED",
                    "successful engine response requires outputVerification");
        }
        try {
            OutputVerificationReceipt receipt = json.treeToValue(
                    value, OutputVerificationReceipt.class);
            ProductionWorkloadPackCatalog.verifyOutput(
                    state.route.jobType(), state.route.workType(), receipt);
            return receipt;
        } catch (ProductionRuntimeException ex) {
            throw ex;
        } catch (IOException | IllegalArgumentException ex) {
            throw new ProductionRuntimeException(
                    "ENGINE_OUTPUT_VERIFICATION_INVALID",
                    "engine outputVerification is invalid", ex);
        }
    }

    private CheckpointInput checkpointInput(JsonNode value) {
        if (value == null || !value.isObject()) {
            throw new ProductionRuntimeException(
                    "ENGINE_CHECKPOINT_INVALID", "engine checkpoint must be an object");
        }
        return new CheckpointInput(
                value.path("sequenceNo").asLong(0),
                value.path("checkpointType").asText(""),
                value.path("stateObjectUri").asText(""),
                value.path("stateHash").asText(""));
    }

    private boolean deliverCheckpoint(AttemptState state, CheckpointInput input) {
        Object jobId = state.envelope.payload().get("jobId");
        if (!(jobId instanceof String value)) {
            throw new ProductionRuntimeException(
                    "WORKER_DISPATCH_PAYLOAD_INVALID", "dispatch payload is missing jobId");
        }
        Checkpoint checkpoint;
        try {
            checkpoint = new Checkpoint(
                    state.envelope.tenantId(), UUID.fromString(value),
                    state.envelope.workItemId(), state.envelope.attemptId(),
                    input.checkpointType(), input.sequenceNo(),
                    input.stateObjectUri(), input.stateHash());
        } catch (IllegalArgumentException ex) {
            throw new ProductionRuntimeException(
                    "WORKER_CHECKPOINT_INVALID", "checkpoint fields are invalid", ex);
        }
        Map<String, Object> body = Map.of(
                "checkpoint", checkpoint,
                "workerId", state.envelope.workerId(),
                "fencingToken", state.envelope.fencingToken());
        try {
            URI endpoint = controlPlane.resolve("/internal/v1/production-runtime/checkpoints");
            HttpRequest request = authorized(
                    endpoint, Duration.ofSeconds(15), state.envelope)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(json.writeValueAsBytes(body)))
                    .build();
            HttpResponse<Void> response = http.send(
                    request, HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() >= 200 && response.statusCode() < 300) return true;
            if (response.statusCode() == 409 || response.statusCode() == 410) {
                throw new ProductionRuntimeException(
                        "WORKER_CHECKPOINT_STALE_FENCE",
                        "scheduler rejected checkpoint ownership");
            }
            if (response.statusCode() >= 500 || response.statusCode() == 408
                    || response.statusCode() == 429) return false;
            throw new ProductionRuntimeException(
                    "WORKER_CHECKPOINT_REJECTED_HTTP_" + response.statusCode(),
                    "scheduler rejected checkpoint content");
        } catch (java.net.http.HttpTimeoutException ex) {
            return false;
        } catch (IOException ex) {
            return false;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    private void deliverCompletion(AttemptState state) {
        AttemptStatus status = state.completionStatus;
        String errorCode = state.completionErrorCode;
        JsonNode usage = state.completionUsage;
        if (status == null) return;
        Map<String, Object> completion = new LinkedHashMap<>();
        completion.put("tenantId", state.envelope.tenantId());
        completion.put("workItemId", state.envelope.workItemId());
        completion.put("attemptId", state.envelope.attemptId());
        completion.put("workerId", state.envelope.workerId());
        completion.put("fencingToken", state.envelope.fencingToken());
        completion.put("status", status.name());
        completion.put("errorCode", errorCode);
        completion.put("errorMessage", null);
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("completion", completion);
        request.put("outputVerification", state.completionOutputVerification);
        request.put("usage", usage);
        request.put("failureReason", errorCode);
        try {
            URI endpoint = controlPlane.resolve("/internal/v1/production-runtime/completions");
            HttpRequest callback = authorized(
                    endpoint, Duration.ofSeconds(15), state.envelope)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(json.writeValueAsBytes(request)))
                    .build();
            HttpResponse<Void> response = http.send(callback, HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() >= 200 && response.statusCode() < 300) {
                state.transition(
                        status == AttemptStatus.SUCCEEDED
                                ? LocalStatus.SUCCEEDED : LocalStatus.FAILED,
                        errorCode);
            } else if (response.statusCode() == 409 || response.statusCode() == 410) {
                state.transition(LocalStatus.FAILED, "COMPLETION_REJECTED_STALE_FENCE");
            } else if (response.statusCode() >= 500 || response.statusCode() == 408
                    || response.statusCode() == 429) {
                state.transition(LocalStatus.COMPLETION_OUTCOME_UNKNOWN,
                        "COMPLETION_HTTP_" + response.statusCode());
            } else {
                state.transition(LocalStatus.FAILED,
                        "COMPLETION_REJECTED_HTTP_" + response.statusCode());
            }
        } catch (IOException ex) {
            state.transition(LocalStatus.COMPLETION_OUTCOME_UNKNOWN, "COMPLETION_TRANSPORT_UNKNOWN");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            state.transition(LocalStatus.COMPLETION_OUTCOME_UNKNOWN, "COMPLETION_INTERRUPTED");
        }
    }

    private void scheduleHeartbeatsSafely() {
        try {
            if (!closed.get()) heartbeatRunning();
        } catch (RuntimeException ignored) {
            // A scheduler exception must never suppress future lease heartbeats.
        }
    }

    private void scheduleReconciliationsSafely() {
        try {
            if (closed.get()) return;
            attempts.values().forEach(state -> {
                switch (state.status) {
                    case PROVIDER_OUTCOME_UNKNOWN -> submitProviderReconciliation(state);
                    case CHECKPOINT_OUTCOME_UNKNOWN -> submitCheckpointReconciliation(state);
                    case COMPLETION_OUTCOME_UNKNOWN -> submitCompletionReconciliation(state);
                    default -> {
                        // ACKED/RUNNING are owned by execution; terminal states
                        // are retained only for exact replay.
                    }
                }
            });
        } catch (RuntimeException ignored) {
            // Individual submissions are bounded and retry on the next pass.
            // Durable-journal failures already mark this worker unhealthy.
        }
    }

    private void submitProviderReconciliation(AttemptState state) {
        submitOnce(
                state, providerReconciliationInFlight,
                providerReconciliationExecutor,
                () -> {
                    if (state.status == LocalStatus.PROVIDER_OUTCOME_UNKNOWN) {
                        reconcileEngine(state);
                    }
                });
    }

    private void submitCheckpointReconciliation(AttemptState state) {
        submitOnce(
                state, checkpointReconciliationInFlight,
                checkpointReconciliationExecutor,
                () -> {
                    if (state.status != LocalStatus.CHECKPOINT_OUTCOME_UNKNOWN) return;
                    JsonNode pending = state.pendingEngineResult;
                    if (pending == null) {
                        callback(state, AttemptStatus.FAILED,
                                "CHECKPOINT_RECONCILIATION_STATE_MISSING", null);
                        return;
                    }
                    try {
                        processEngineResult(state, pending);
                    } catch (RuntimeException ex) {
                        callback(state, AttemptStatus.FAILED,
                                "CHECKPOINT_RECONCILIATION_FAILED", null);
                    }
                });
    }

    private void submitCompletionReconciliation(AttemptState state) {
        submitOnce(
                state, completionReconciliationInFlight,
                completionReconciliationExecutor,
                () -> {
                    if (state.status == LocalStatus.COMPLETION_OUTCOME_UNKNOWN) {
                        deliverCompletion(state);
                    }
                });
    }

    private void submitOnce(
            AttemptState state,
            Set<UUID> inFlight,
            ExecutorService executor,
            Runnable operation
    ) {
        UUID attemptId = state.envelope.attemptId();
        if (closed.get() || !inFlight.add(attemptId)) return;
        try {
            executor.execute(() -> {
                try {
                    operation.run();
                } catch (RuntimeException ignored) {
                    // The durable state remains retryable or persist() has
                    // already made the worker fail closed.
                } finally {
                    inFlight.remove(attemptId);
                }
            });
        } catch (RejectedExecutionException ignored) {
            inFlight.remove(attemptId);
        }
    }

    private void reconcileEngine(AttemptState state) {
        try {
            HttpRequest request = authorized(
                    state.route.reconciliationEndpoint(), state.route.timeout(), state.envelope)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(
                            json.writeValueAsBytes(state.envelope)))
                    .build();
            EngineResponse response = sendEngine(request);
            if (response.status() == 202
                    || response.status() >= 500 || response.status() == 408
                    || response.status() == 429) return;
            if (response.status() == 404) {
                // The dedicated reconciliation endpoint defines 404 as an
                // authoritative "execution was never accepted". Reusing the
                // exact original idempotency key is therefore safe.
                state.transition(LocalStatus.ACKED, "ENGINE_RECONCILED_NOT_ACCEPTED");
                submitExecution(state);
                return;
            }
            if (response.status() < 200 || response.status() >= 300) {
                String error = "ENGINE_RECONCILIATION_HTTP_" + response.status();
                callback(state, AttemptStatus.FAILED, error, null);
                return;
            }
            JsonNode reconciled = json.readTree(response.body());
            state.pendingEngineResult = reconciled == null ? null : reconciled.deepCopy();
            state.transition(
                    LocalStatus.CHECKPOINT_OUTCOME_UNKNOWN,
                    "ENGINE_RECONCILED_RESULT_PENDING");
            submitCheckpointReconciliation(state);
        } catch (java.net.http.HttpTimeoutException ex) {
            // Outcome remains unknown; never resend the original execution.
        } catch (IOException ex) {
            // Outcome remains unknown; never resend the original execution.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } catch (RuntimeException ex) {
            callback(state, AttemptStatus.FAILED,
                    "ENGINE_RECONCILIATION_INVALID", null);
        }
    }

    private void heartbeatRunning() {
        attempts.values().stream()
                .filter(state -> switch (state.status) {
                    case RUNNING, PROVIDER_OUTCOME_UNKNOWN,
                         CHECKPOINT_OUTCOME_UNKNOWN, COMPLETION_OUTCOME_UNKNOWN -> true;
                    default -> false;
                })
                .forEach(this::submitHeartbeat);
    }

    private void submitHeartbeat(AttemptState state) {
        UUID attemptId = state.envelope.attemptId();
        if (closed.get() || !heartbeatInFlight.add(attemptId)) return;
        if (!heartbeatPermits.tryAcquire()) {
            heartbeatInFlight.remove(attemptId);
            return;
        }
        try {
            heartbeatExecutor.execute(() -> {
                try {
                    if (switch (state.status) {
                        case RUNNING, PROVIDER_OUTCOME_UNKNOWN,
                             CHECKPOINT_OUTCOME_UNKNOWN,
                             COMPLETION_OUTCOME_UNKNOWN -> true;
                        default -> false;
                    }) heartbeat(state);
                } finally {
                    heartbeatPermits.release();
                    heartbeatInFlight.remove(attemptId);
                }
            });
        } catch (RejectedExecutionException ignored) {
            heartbeatPermits.release();
            heartbeatInFlight.remove(attemptId);
        }
    }

    private void heartbeat(AttemptState state) {
        try {
            Map<String, Object> body = Map.of(
                    "tenantId", state.envelope.tenantId(),
                    "attemptId", state.envelope.attemptId(),
                    "workerId", state.envelope.workerId(),
                    "fencingToken", state.envelope.fencingToken(),
                    "leaseDuration", "PT30S");
            URI endpoint = controlPlane.resolve(
                    "/internal/v1/production-runtime/attempts/"
                            + state.envelope.attemptId() + "/heartbeat");
            HttpRequest request = authorized(endpoint, Duration.ofSeconds(5), state.envelope)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(json.writeValueAsBytes(body)))
                    .build();
            HttpResponse<Void> response = http.send(request, HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() == 409 || response.statusCode() == 410) {
                state.transition(LocalStatus.FAILED, "LEASE_OWNERSHIP_LOST");
            }
        } catch (Exception ignored) {
            // A missed heartbeat never creates local ownership. PostgreSQL will
            // expire the lease and fence this process if connectivity remains lost.
        }
    }

    private HttpRequest.Builder authorized(
            URI endpoint, Duration timeout, DispatchEnvelope envelope
    ) {
        validateEndpoint(endpoint, meshHttp);
        return HttpRequest.newBuilder(endpoint)
                .timeout(timeout)
                .header("Accept", "application/json")
                .header("Authorization", "Bearer " + credential.read())
                .header("X-ELMOS-Tenant-Id", envelope.tenantId().toString())
                .header("X-ELMOS-Attempt-Id", envelope.attemptId().toString())
                .header("X-ELMOS-Fencing-Token", Long.toString(envelope.fencingToken()))
                .header("Idempotency-Key", envelope.dispatchIdempotencyKey());
    }

    private String digest(DispatchEnvelope envelope) {
        try {
            return JdbcProductionProviderPayloadStore.sha256(
                    canonicalJson.writeValueAsBytes(envelope));
        } catch (IOException ex) {
            throw new ProductionRuntimeException(
                    "WORKER_DISPATCH_INVALID", "dispatch envelope cannot be serialized", ex);
        }
    }

    private ProductionWorkerRouteCatalog.Route requireRoute(DispatchEnvelope envelope) {
        Map<String, Object> payload = envelope.payload();
        String jobType = required(payload, "jobType", 80);
        String workType = required(payload, "workType", 120);
        return routes.require(jobType, workType);
    }

    private static void requireMaintenanceInterval(Duration interval, String field) {
        if (interval == null || interval.compareTo(Duration.ofMillis(10)) < 0
                || interval.compareTo(Duration.ofMinutes(1)) > 0) {
            throw new IllegalArgumentException(field + " must be within [10ms, 1m]");
        }
    }

    private static long initialDelayMillis(Duration interval) {
        return Math.min(1_000L, interval.toMillis());
    }

    private static ExecutorService boundedExecutor(
            String threadPrefix,
            int threads,
            int queueCapacity
    ) {
        return new ThreadPoolExecutor(
                threads, threads, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(queueCapacity),
                namedPlatformFactory(threadPrefix),
                new ThreadPoolExecutor.AbortPolicy());
    }

    private static ThreadFactory namedPlatformFactory(String prefix) {
        AtomicInteger sequence = new AtomicInteger();
        return task -> Thread.ofPlatform()
                .name(prefix + sequence.incrementAndGet())
                .unstarted(task);
    }

    private void evictTerminal() {
        attempts.entrySet().stream()
                .filter(entry -> switch (entry.getValue().status) {
                    case SUCCEEDED, FAILED -> true;
                    default -> false;
                })
                .sorted(Map.Entry.comparingByValue(
                        java.util.Comparator.comparing(state -> state.updatedAt)))
                .limit(Math.max(1, maxRetained / 10L))
                .map(Map.Entry::getKey)
                .toList()
                .forEach(attemptId -> {
                    try {
                        journal.delete(attemptId);
                    } catch (RuntimeException ex) {
                        journalHealthy = false;
                        throw ex;
                    }
                    attempts.remove(attemptId);
                });
    }

    private void restoreJournal() {
        for (var entry : journal.load(maxRetained).entrySet()) {
            AttemptState state = restore(entry.getKey(), entry.getValue());
            if (attempts.putIfAbsent(entry.getKey(), state) != null) {
                throw new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE",
                        "duplicate attempt exists in the durable worker journal");
            }
        }
        for (AttemptState state : attempts.values()) {
            switch (state.status) {
                case ACKED -> submitExecution(state);
                case RUNNING -> state.transition(
                        LocalStatus.PROVIDER_OUTCOME_UNKNOWN,
                        "WORKER_RESTART_REQUIRES_ENGINE_RECONCILIATION");
                case SUCCEEDED, FAILED, PROVIDER_OUTCOME_UNKNOWN,
                     CHECKPOINT_OUTCOME_UNKNOWN, COMPLETION_OUTCOME_UNKNOWN -> {
                    // Terminal states are retained for exact replay. Unknown
                    // states are resumed by the maintenance loop.
                }
            }
        }
    }

    private AttemptState restore(UUID expectedAttemptId, byte[] payload) {
        try {
            JsonNode root = json.readTree(payload);
            if (root == null || !root.isObject()
                    || root.path("schemaVersion").asInt() != 1) {
                throw new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE",
                        "worker journal schema is invalid");
            }
            UUID attemptId = UUID.fromString(root.path("attemptId").asText(""));
            if (!expectedAttemptId.equals(attemptId)) {
                throw new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE",
                        "worker journal filename and payload attempt differ");
            }
            DispatchEnvelope envelope = json.treeToValue(
                    root.path("envelope"), DispatchEnvelope.class);
            if (!attemptId.equals(envelope.attemptId())
                    || !workerId.equals(envelope.workerId())) {
                throw new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE",
                        "worker journal envelope ownership is invalid");
            }
            String storedDigest = root.path("envelopeDigest").asText("");
            if (!storedDigest.matches("[0-9a-f]{64}")
                    || !storedDigest.equals(digest(envelope))) {
                throw new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE",
                        "worker journal envelope digest mismatch");
            }
            ProductionWorkerRouteCatalog.Route route;
            try {
                route = requireRoute(envelope);
            } catch (ProductionRuntimeException ex) {
                throw new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE",
                        "worker journal references an unavailable exact route", ex);
            }
            AttemptState state = new AttemptState(envelope, storedDigest, route);
            state.status = LocalStatus.valueOf(root.path("status").asText(""));
            state.updatedAt = Instant.parse(root.path("updatedAt").asText(""));
            state.errorCode = nullableText(root.get("errorCode"), 200);
            String completionStatus = nullableText(root.get("completionStatus"), 40);
            state.completionStatus = completionStatus == null
                    ? null : AttemptStatus.valueOf(completionStatus);
            state.completionErrorCode = nullableText(
                    root.get("completionErrorCode"), 200);
            state.completionUsage = nullableNode(root.get("completionUsage"));
            JsonNode outputVerification = root.get("completionOutputVerification");
            state.completionOutputVerification = outputVerification == null
                    || outputVerification.isNull()
                    ? null
                    : json.treeToValue(
                            outputVerification, OutputVerificationReceipt.class);
            if (state.completionOutputVerification != null) {
                ProductionWorkloadPackCatalog.verifyOutput(
                        route.jobType(), route.workType(),
                        state.completionOutputVerification);
            }
            state.pendingEngineResult = nullableNode(root.get("pendingEngineResult"));
            JsonNode checkpoints = root.path("checkpoints");
            if (!checkpoints.isArray()) {
                throw new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE",
                        "worker journal checkpoints are invalid");
            }
            long expectedSequence = 1;
            for (JsonNode value : checkpoints) {
                CheckpointInput input = json.treeToValue(value, CheckpointInput.class);
                if (input.sequenceNo() != expectedSequence++) {
                    throw new ProductionRuntimeException(
                            "WORKER_DURABLE_JOURNAL_FAILURE",
                            "worker journal checkpoint sequence is not contiguous");
                }
                state.checkpoints.put(input.sequenceNo(), input);
            }
            if (state.status == LocalStatus.CHECKPOINT_OUTCOME_UNKNOWN
                    && state.pendingEngineResult == null) {
                throw new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE",
                        "checkpoint recovery state has no pending engine result");
            }
            if (state.status == LocalStatus.COMPLETION_OUTCOME_UNKNOWN
                    && state.completionStatus == null) {
                throw new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE",
                        "completion recovery state has no completion payload");
            }
            if (state.status == LocalStatus.COMPLETION_OUTCOME_UNKNOWN
                    && state.completionStatus == AttemptStatus.SUCCEEDED
                    && state.completionOutputVerification == null) {
                throw new ProductionRuntimeException(
                        "WORKER_DURABLE_JOURNAL_FAILURE",
                        "successful completion recovery has no output verification");
            }
            return state;
        } catch (IOException | IllegalArgumentException ex) {
            if (ex instanceof ProductionRuntimeException runtime) throw runtime;
            throw new ProductionRuntimeException(
                    "WORKER_DURABLE_JOURNAL_FAILURE",
                    "worker journal record cannot be decoded", ex);
        }
    }

    private void persist(AttemptState state) {
        try {
            Map<String, Object> snapshot = new LinkedHashMap<>();
            snapshot.put("schemaVersion", 1);
            snapshot.put("attemptId", state.envelope.attemptId());
            snapshot.put("envelope", state.envelope);
            snapshot.put("envelopeDigest", state.envelopeDigest);
            snapshot.put("status", state.status.name());
            snapshot.put("updatedAt", state.updatedAt.toString());
            snapshot.put("errorCode", state.errorCode);
            snapshot.put("completionStatus", state.completionStatus == null
                    ? null : state.completionStatus.name());
            snapshot.put("completionErrorCode", state.completionErrorCode);
            snapshot.put("completionUsage", state.completionUsage);
            snapshot.put("completionOutputVerification",
                    state.completionOutputVerification);
            snapshot.put("pendingEngineResult", state.pendingEngineResult);
            snapshot.put("checkpoints", List.copyOf(state.checkpoints.values()));
            journal.write(
                    state.envelope.attemptId(),
                    canonicalJson.writeValueAsBytes(snapshot));
        } catch (RuntimeException | IOException ex) {
            journalHealthy = false;
            if (ex instanceof ProductionRuntimeException runtime) throw runtime;
            throw new ProductionRuntimeException(
                    "WORKER_DURABLE_JOURNAL_FAILURE",
                    "worker state could not be persisted", ex);
        }
    }

    private EngineResponse sendEngine(HttpRequest request)
            throws IOException, InterruptedException {
        HttpResponse<InputStream> response = http.send(
                request, HttpResponse.BodyHandlers.ofInputStream());
        byte[] body;
        try (InputStream input = response.body()) {
            body = input.readNBytes(MAX_ENGINE_RESPONSE_BYTES + 1);
        }
        if (body.length > MAX_ENGINE_RESPONSE_BYTES) {
            throw new IOException("engine response exceeds bounded protocol");
        }
        return new EngineResponse(response.statusCode(), body);
    }

    private static String nullableText(JsonNode value, int maximum) {
        if (value == null || value.isNull()) return null;
        String text = value.asText();
        if (text.isBlank() || text.length() > maximum
                || text.indexOf('\n') >= 0 || text.indexOf('\r') >= 0) {
            throw new IllegalArgumentException("worker journal text field is invalid");
        }
        return text;
    }

    private static JsonNode nullableNode(JsonNode value) {
        return value == null || value.isNull() ? null : value.deepCopy();
    }

    @PreDestroy
    void close() {
        if (!closed.compareAndSet(false, true)) return;
        List<ExecutorService> ownedExecutors = List.of(
                heartbeatScheduler,
                reconciliationScheduler,
                heartbeatExecutor,
                providerReconciliationExecutor,
                checkpointReconciliationExecutor,
                completionReconciliationExecutor,
                executors);
        ownedExecutors.forEach(ExecutorService::shutdownNow);
        awaitTermination(ownedExecutors, Duration.ofSeconds(10));
    }

    private static void awaitTermination(
            List<ExecutorService> ownedExecutors,
            Duration timeout
    ) {
        long deadline = System.nanoTime() + timeout.toNanos();
        for (ExecutorService executor : ownedExecutors) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) return;
            try {
                executor.awaitTermination(remaining, TimeUnit.NANOSECONDS);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    boolean executorsShutdown() {
        return closed.get()
                && heartbeatScheduler.isShutdown()
                && reconciliationScheduler.isShutdown()
                && heartbeatExecutor.isShutdown()
                && providerReconciliationExecutor.isShutdown()
                && checkpointReconciliationExecutor.isShutdown()
                && completionReconciliationExecutor.isShutdown()
                && executors.isShutdown();
    }

    boolean executorsTerminated() {
        return heartbeatScheduler.isTerminated()
                && reconciliationScheduler.isTerminated()
                && heartbeatExecutor.isTerminated()
                && providerReconciliationExecutor.isTerminated()
                && checkpointReconciliationExecutor.isTerminated()
                && completionReconciliationExecutor.isTerminated()
                && executors.isTerminated();
    }

    boolean journalHealthy() {
        return journalHealthy;
    }

    long attemptsWithStatus(LocalStatus status) {
        Objects.requireNonNull(status, "status");
        return attempts.values().stream().filter(state -> state.status == status).count();
    }

    private static String required(Map<String, Object> payload, String field, int max) {
        Object value = payload.get(field);
        if (!(value instanceof String text) || text.isBlank() || text.length() > max) {
            throw new ProductionRuntimeException(
                    "WORKER_DISPATCH_PAYLOAD_INVALID", "dispatch payload is missing " + field);
        }
        return text;
    }

    private static String bounded(String value, int max) {
        return value.length() <= max ? value : value.substring(0, max);
    }

    private static void requireText(String value, String field, int max) {
        if (value == null || value.isBlank() || value.length() > max
                || value.indexOf('\n') >= 0 || value.indexOf('\r') >= 0) {
            throw new IllegalArgumentException(field + " is invalid");
        }
    }

    private static URI validateEndpoint(URI endpoint, boolean meshHttp) {
        Objects.requireNonNull(endpoint, "endpoint");
        if (endpoint.getHost() == null || endpoint.getUserInfo() != null
                || endpoint.getQuery() != null || endpoint.getFragment() != null) {
            throw new IllegalArgumentException("worker endpoint is malformed");
        }
        boolean secure = "https".equalsIgnoreCase(endpoint.getScheme());
        boolean mesh = "http".equalsIgnoreCase(endpoint.getScheme()) && meshHttp
                && (endpoint.getHost().endsWith(".svc")
                || endpoint.getHost().endsWith(".svc.cluster.local")
                || loopback(endpoint.getHost()));
        if (!secure && !mesh) throw new IllegalArgumentException("worker endpoint must use HTTPS or approved mesh HTTP");
        return endpoint;
    }

    private static boolean loopback(String host) {
        try { return InetAddress.getByName(host).isLoopbackAddress(); }
        catch (Exception ex) { return false; }
    }

    private record EngineResponse(int status, byte[] body) {}

    private final class AttemptState {
        private final DispatchEnvelope envelope;
        private final String envelopeDigest;
        private final ProductionWorkerRouteCatalog.Route route;
        private volatile LocalStatus status = LocalStatus.ACKED;
        private volatile Instant updatedAt = Instant.now();
        private volatile String errorCode;
        private volatile AttemptStatus completionStatus;
        private volatile String completionErrorCode;
        private volatile JsonNode completionUsage;
        private volatile OutputVerificationReceipt completionOutputVerification;
        private volatile JsonNode pendingEngineResult;
        private final java.util.NavigableMap<Long, CheckpointInput> checkpoints =
                new java.util.TreeMap<>();

        private AttemptState(
                DispatchEnvelope envelope,
                String envelopeDigest,
                ProductionWorkerRouteCatalog.Route route
        ) {
            this.envelope = envelope;
            this.envelopeDigest = envelopeDigest;
            this.route = route;
        }

        private synchronized void transition(LocalStatus next, String error) {
            this.status = next;
            this.errorCode = error;
            this.updatedAt = Instant.now();
            persist(this);
        }

        private synchronized void rememberCompletion(
                AttemptStatus status,
                String error,
                JsonNode usage,
                OutputVerificationReceipt outputVerification
        ) {
            if (status == AttemptStatus.SUCCEEDED && outputVerification == null) {
                throw new ProductionRuntimeException(
                        "ENGINE_OUTPUT_VERIFICATION_REQUIRED",
                        "successful completion requires output verification");
            }
            if (status != AttemptStatus.SUCCEEDED && outputVerification != null) {
                throw new ProductionRuntimeException(
                        "ENGINE_OUTPUT_VERIFICATION_ON_FAILURE",
                        "failed completion cannot attach passing output verification");
            }
            this.completionStatus = status;
            this.completionErrorCode = error;
            this.completionUsage = usage == null ? null : usage.deepCopy();
            this.completionOutputVerification = outputVerification;
            this.status = LocalStatus.COMPLETION_OUTCOME_UNKNOWN;
            this.errorCode = error;
            this.updatedAt = Instant.now();
            persist(this);
        }

        private synchronized void touch() {
            this.updatedAt = Instant.now();
            persist(this);
        }
    }
}
