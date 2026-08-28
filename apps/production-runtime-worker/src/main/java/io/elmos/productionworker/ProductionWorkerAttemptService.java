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
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

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
    private final ScheduledExecutorService heartbeats;
    private final Map<UUID, AttemptState> attempts = new ConcurrentHashMap<>();
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
        this.maxRetained = maxRetained;
        this.meshHttp = meshHttp;
        this.journal = new ProductionWorkerDurableJournal(stateDirectory);
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        this.executors = Executors.newFixedThreadPool(concurrency);
        this.heartbeats = Executors.newSingleThreadScheduledExecutor();
        restoreJournal();
        this.heartbeats.scheduleWithFixedDelay(
                this::maintenanceSafely, 1, 10, TimeUnit.SECONDS);
    }

    synchronized Acceptance accept(DispatchEnvelope envelope) {
        Objects.requireNonNull(envelope, "envelope");
        if (!journalHealthy) {
            throw new ProductionRuntimeException(
                    "WORKER_DURABLE_JOURNAL_FAILURE",
                    "worker cannot accept work while its durable journal is unhealthy");
        }
        if (!workerId.equals(envelope.workerId())) {
            throw new ProductionRuntimeException(
                    "WORKER_ID_MISMATCH", "dispatch targets a different worker identity");
        }
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
        AttemptState created = new AttemptState(envelope, digest);
        persist(created);
        attempts.put(envelope.attemptId(), created);
        executors.submit(() -> execute(created));
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

    private void execute(AttemptState state) {
        state.transition(LocalStatus.RUNNING, null);
        Map<String, Object> payload = state.envelope.payload();
        String jobType = required(payload, "jobType", 80);
        String workType = required(payload, "workType", 120);
        ProductionWorkerRouteCatalog.Route route;
        try {
            route = routes.require(jobType, workType);
        } catch (ProductionRuntimeException ex) {
            callback(state, AttemptStatus.FAILED, ex.code(), null);
            return;
        }
        try {
            byte[] body = json.writeValueAsBytes(state.envelope);
            HttpRequest request = authorized(
                    route.endpoint(), route.timeout(), state.envelope)
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
            callback(state, AttemptStatus.FAILED, "ENGINE_RESPONSE_INVALID", null);
        }
    }

    private void callback(
            AttemptState state,
            AttemptStatus status,
            String errorCode,
            JsonNode usage
    ) {
        state.rememberCompletion(status, errorCode, usage);
        deliverCompletion(state);
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
                        return;
                    }
                }
            }
            state.pendingEngineResult = null;
            JsonNode usage = result.get("usage");
            callback(state, AttemptStatus.SUCCEEDED, null, usage);
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

    private void maintenance() {
        heartbeatRunning();
        attempts.values().stream()
                .filter(state -> state.status == LocalStatus.PROVIDER_OUTCOME_UNKNOWN)
                .forEach(this::reconcileEngine);
        attempts.values().stream()
                .filter(state -> state.status == LocalStatus.CHECKPOINT_OUTCOME_UNKNOWN)
                .forEach(state -> {
                    JsonNode pending = state.pendingEngineResult;
                    if (pending == null) return;
                    try {
                        processEngineResult(state, pending);
                    } catch (RuntimeException ex) {
                        callback(state, AttemptStatus.FAILED,
                                "CHECKPOINT_RECONCILIATION_FAILED", null);
                    }
                });
        attempts.values().stream()
                .filter(state -> state.status == LocalStatus.COMPLETION_OUTCOME_UNKNOWN)
                .forEach(this::deliverCompletion);
    }

    private void maintenanceSafely() {
        try {
            maintenance();
        } catch (RuntimeException ignored) {
            // ScheduledExecutorService suppresses every future run when an
            // exception escapes. Durable-journal failures already mark the
            // worker unhealthy in persist/eviction; all other failures remain
            // retryable on the next bounded reconciliation pass.
        }
    }

    private void reconcileEngine(AttemptState state) {
        try {
            String jobType = required(state.envelope.payload(), "jobType", 80);
            String workType = required(state.envelope.payload(), "workType", 120);
            ProductionWorkerRouteCatalog.Route route = routes.require(jobType, workType);
            HttpRequest request = authorized(
                    route.reconciliationEndpoint(), route.timeout(), state.envelope)
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
                executors.submit(() -> execute(state));
                return;
            }
            if (response.status() < 200 || response.status() >= 300) {
                String error = "ENGINE_RECONCILIATION_HTTP_" + response.status();
                callback(state, AttemptStatus.FAILED, error, null);
                return;
            }
            processEngineResult(state, json.readTree(response.body()));
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
                .forEach(this::heartbeat);
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
                case ACKED -> executors.submit(() -> execute(state));
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
            AttemptState state = new AttemptState(envelope, storedDigest);
            state.status = LocalStatus.valueOf(root.path("status").asText(""));
            state.updatedAt = Instant.parse(root.path("updatedAt").asText(""));
            state.errorCode = nullableText(root.get("errorCode"), 200);
            String completionStatus = nullableText(root.get("completionStatus"), 40);
            state.completionStatus = completionStatus == null
                    ? null : AttemptStatus.valueOf(completionStatus);
            state.completionErrorCode = nullableText(
                    root.get("completionErrorCode"), 200);
            state.completionUsage = nullableNode(root.get("completionUsage"));
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
        heartbeats.shutdownNow();
        executors.shutdownNow();
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
        private volatile LocalStatus status = LocalStatus.ACKED;
        private volatile Instant updatedAt = Instant.now();
        private volatile String errorCode;
        private volatile AttemptStatus completionStatus;
        private volatile String completionErrorCode;
        private volatile JsonNode completionUsage;
        private volatile JsonNode pendingEngineResult;
        private final java.util.NavigableMap<Long, CheckpointInput> checkpoints =
                new java.util.TreeMap<>();

        private AttemptState(DispatchEnvelope envelope, String envelopeDigest) {
            this.envelope = envelope;
            this.envelopeDigest = envelopeDigest;
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
                JsonNode usage
        ) {
            this.completionStatus = status;
            this.completionErrorCode = error;
            this.completionUsage = usage == null ? null : usage.deepCopy();
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
