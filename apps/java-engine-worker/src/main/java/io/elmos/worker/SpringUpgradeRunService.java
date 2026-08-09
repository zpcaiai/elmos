package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.annotation.PreDestroy;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.regex.Pattern;

import static io.elmos.worker.SpringUpgradeModels.*;

final class SpringUpgradeRunService {
    private static final int MAX_LOG_LINES = 5_000;
    private static final int MAX_EVENTS = 250;
    private static final Pattern SECRET = Pattern.compile(
            "(?i)(authorization\\s*[:=]|token\\s*[:=]|password\\s*[:=]|secret\\s*[:=])\\s*\\S+");
    private final SpringUpgradeExecutionPort transformer;
    private final SpringUpgradeIndependentValidationPort verifier;
    private final Path workspaceRoot;
    private final ObjectMapper json;
    private final Clock clock;
    private final ExecutorService tasks;
    private final ScheduledExecutorService scheduler;
    private final DurableRunLeaseStore leaseStore;
    private final ConcurrentMap<String, RunState> runs = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, IdempotencyEntry> idempotency = new ConcurrentHashMap<>();

    SpringUpgradeRunService(
            SpringUpgradeExecutionPort transformer,
            SpringUpgradeIndependentValidationPort verifier,
            Path workspaceRoot,
            ObjectMapper json,
            Clock clock
    ) {
        this(transformer, verifier, workspaceRoot, json, clock,
                2, 1, Duration.ofHours(1), Duration.ofMinutes(2));
    }

    SpringUpgradeRunService(
            SpringUpgradeExecutionPort transformer,
            SpringUpgradeIndependentValidationPort verifier,
            Path workspaceRoot,
            ObjectMapper json,
            Clock clock,
            int globalCapacity,
            int tenantCapacity,
            Duration queueTtl,
            Duration leaseTtl
    ) {
        this.transformer = Objects.requireNonNull(transformer);
        this.verifier = Objects.requireNonNull(verifier);
        this.workspaceRoot = Objects.requireNonNull(workspaceRoot).toAbsolutePath().normalize();
        this.json = Objects.requireNonNull(json);
        this.clock = Objects.requireNonNull(clock);
        this.tasks = Executors.newThreadPerTaskExecutor(
                Thread.ofVirtual().name("spring-upgrade-", 0).factory());
        this.scheduler = Executors.newSingleThreadScheduledExecutor(
                Thread.ofPlatform().daemon(true).name("spring-upgrade-queue-", 0).factory());
        createDirectory(this.workspaceRoot);
        this.leaseStore = new DurableRunLeaseStore(
                this.workspaceRoot, "spring-upgrade", globalCapacity, tenantCapacity,
                queueTtl, leaseTtl, clock);
        restoreDurableRuns();
    }

    RunView create(String authenticatedOrganizationId, StartRequest request) {
        validateRequest(authenticatedOrganizationId, request);
        String scope = authenticatedOrganizationId + "|create|" + request.idempotencyKey();
        String fingerprint = fingerprint(request);
        synchronized (idempotency) {
            IdempotencyEntry existing = idempotency.get(scope);
            if (existing != null) {
                if (!existing.fingerprint().equals(fingerprint)) throw new IdempotencyConflict();
                return view(require(authenticatedOrganizationId, existing.runId()));
            }
            RunState state = newState(request, null, 1);
            runs.put(state.runId, state);
            idempotency.put(scope, new IdempotencyEntry(state.runId, fingerprint));
            state.future = tasks.submit(() -> execute(state));
            return view(state);
        }
    }

    RunView get(String organizationId, String runId) {
        return view(require(organizationId, runId));
    }

    LogView logs(String organizationId, String runId) {
        RunState state = require(organizationId, runId);
        List<String> result;
        boolean truncated;
        synchronized (state) {
            result = new ArrayList<>(state.logs);
            truncated = state.logsTruncated;
        }
        if (state.runtimeHandle != null && state.runtimeHandle.runtimeId() != null) {
            try {
                for (String line : transformer.runtimeLogs(state.runtimeHandle)) {
                    result.add(redact(line));
                }
            } catch (RuntimeException error) {
                result.add("isolated runtime log is temporarily unavailable");
            }
        }
        Path applicationLog = state.runRoot.resolve("runtime/application.log");
        if (Files.isRegularFile(applicationLog, LinkOption.NOFOLLOW_LINKS)) {
            try {
                List<String> runtimeLines = Files.readAllLines(applicationLog, StandardCharsets.UTF_8);
                int start = Math.max(0, runtimeLines.size() - 1_000);
                if (start > 0) truncated = true;
                for (int i = start; i < runtimeLines.size(); i++) result.add(redact(runtimeLines.get(i)));
            } catch (IOException ignored) {
                result.add("runtime log is temporarily unavailable");
            }
        }
        if (result.size() > MAX_LOG_LINES) {
            result = result.subList(result.size() - MAX_LOG_LINES, result.size());
            truncated = true;
        }
        return new LogView(runId, result, truncated);
    }

    Path artifact(String organizationId, String runId) {
        RunState state = require(organizationId, runId);
        synchronized (state) {
            if (!downloadAvailable(state)) throw new Conflict("INDEPENDENT_VALIDATION_REQUIRED");
            return requireArtifactIntegrity(state);
        }
    }

    RunView startRuntime(String organizationId, String runId) {
        RunState state = require(organizationId, runId);
        synchronized (state) {
            if (!downloadAvailable(state)) throw new Conflict("INDEPENDENT_VALIDATION_REQUIRED");
            requireArtifactIntegrity(state);
            if (!transformer.runtimeConfigured()) {
                throw new Conflict("ISOLATED_APPLICATION_RUNNER_NOT_CONFIGURED");
            }
            if (state.runtimeStatus == RuntimeStatus.HEALTHY || state.runtimeStatus == RuntimeStatus.STARTING) {
                return view(state);
            }
            state.runtimeStopRequested.set(false);
            state.runtimeStatus = RuntimeStatus.STARTING;
            state.failureCode = null;
            state.failureMessage = null;
            touch(state);
            state.runtimeFuture = tasks.submit(() -> launchRuntime(state));
            return view(state);
        }
    }

    RunView stopRuntime(String organizationId, String runId) {
        RunState state = require(organizationId, runId);
        RuntimeHandle handle;
        Process activeProcess;
        Future<?> runtimeFuture;
        synchronized (state) {
            if (state.runtimeStatus == RuntimeStatus.NOT_STARTED || state.runtimeStatus == RuntimeStatus.STOPPED) {
                return view(state);
            }
            state.runtimeStopRequested.set(true);
            handle = state.runtimeHandle;
            activeProcess = state.activeProcess.getAndSet(null);
            runtimeFuture = state.runtimeFuture;
        }
        if (runtimeFuture != null) runtimeFuture.cancel(true);
        if (activeProcess != null && activeProcess.isAlive()) activeProcess.destroyForcibly();
        transformer.stop(handle, control(state));
        synchronized (state) {
            state.runtimeHandle = null;
            state.runtimeStatus = RuntimeStatus.STOPPED;
            state.activeProcess.set(null);
            touch(state);
            return view(state);
        }
    }

    RunView cancel(String organizationId, String runId) {
        RunState state = require(organizationId, runId);
        synchronized (state) {
            if (terminal(state.status)) throw new Conflict("RUN_ALREADY_TERMINAL");
            state.cancelled.set(true);
            Process process = state.activeProcess.getAndSet(null);
            if (process != null) process.destroyForcibly();
            if (state.future != null) state.future.cancel(true);
            state.status = RunStatus.CANCELLED;
            appendEvent(state, state.stage, "CANCELLED", "Migration run cancelled");
            touch(state);
            return view(state);
        }
    }

    RunView retry(String organizationId, String runId, String retryIdempotencyKey) {
        RunState source = require(organizationId, runId);
        if (retryIdempotencyKey == null || retryIdempotencyKey.isBlank() || retryIdempotencyKey.length() > 128) {
            throw new InvalidRequest("A bounded retry idempotency key is required.");
        }
        synchronized (source) {
            if (!terminal(source.status)) throw new Conflict("RUN_NOT_TERMINAL");
        }
        String scope = organizationId + "|retry|" + runId + "|" + retryIdempotencyKey;
        synchronized (idempotency) {
            IdempotencyEntry existing = idempotency.get(scope);
            if (existing != null) return view(require(organizationId, existing.runId()));
            StartRequest request = new StartRequest(
                    source.request.organizationId(),
                    source.request.sourceMode(),
                    source.request.repositoryUrl(),
                    source.request.requestedRef(),
                    source.request.expectedCommitSha(),
                    source.request.snapshotId(),
                    source.request.materializedRelativePath(),
                    source.request.startAfterVerification(),
                    retryIdempotencyKey,
                    source.request.targetSpringBoot(),
                    source.request.targetJava()
            );
            RunState state = newState(request, runId, source.attempt + 1);
            runs.put(state.runId, state);
            idempotency.put(scope, new IdempotencyEntry(state.runId, fingerprint(request)));
            state.future = tasks.submit(() -> execute(state));
            return view(state);
        }
    }

    Map<String, Object> capabilities() {
        return Map.ofEntries(
                Map.entry("packKey", PACK_KEY),
                Map.entry("sourceTuple", Map.of("springBoot", SOURCE_BOOT, "java", SOURCE_JAVA, "build", "Maven 3.9.11")),
                Map.entry("targetTuple", Map.of("springBoot", TARGET_BOOT, "java", TARGET_JAVA, "build", "Maven 3.9.11")),
                Map.entry("openRewrite", Map.of("rewriteSpring", REWRITE_SPRING, "mavenPlugin", REWRITE_MAVEN_PLUGIN)),
                // The full catalog of legacy source lines the engine can attempt.
                // sourceTuple above remains the single tuple with recorded evidence.
                Map.entry("routes", SpringRouteCatalog.routes().stream().map(route -> Map.ofEntries(
                        Map.entry("routeId", route.routeId()),
                        Map.entry("packKey", route.packKey()),
                        Map.entry("label", route.label()),
                        Map.entry("sourceFrameworkFamily", route.sourceFamily().contractValue()),
                        Map.entry("buildTool", route.buildTool()),
                        Map.entry("sourceBootMinInclusive", route.sourceBootMinInclusive()),
                        Map.entry("sourceBootMaxExclusive", route.sourceBootMaxExclusive()),
                        Map.entry("sourceJavaVersions",
                                route.sourceJavaVersions().stream().sorted().toList()),
                        Map.entry("targetSpringBoot", route.targetBoot()),
                        Map.entry("targetJava", route.targetJava()),
                        Map.entry("recipeId", route.recipeId()),
                        Map.entry("evidenceStatus", route.routeEvidence().name()),
                        Map.entry("verifiedSourceSpringBoot", route.verifiedSourceBoot()),
                        Map.entry("verifiedSourceJava", route.verifiedSourceJava()),
                        Map.entry("notes", route.notes())
                )).toList()),
                Map.entry("experimentalRoutesRequireOptIn", true),
                Map.entry("transformerConfigured", transformer.configured()),
                Map.entry("transformerReason", transformer.configurationReason()),
                Map.entry("runtimeRunnerConfigured", transformer.runtimeConfigured()),
                Map.entry("runtimeRunnerReason", transformer.runtimeConfigurationReason()),
                Map.entry("independentVerifierConfigured", verifier.configured()),
                Map.entry("independentVerifierReason", verifier.configurationReason()),
                Map.entry("downloadRequiresIndependentPass", true),
                Map.entry("runtimeRequiresIndependentPass", true),
                Map.entry("stateAuthority", "DURABLE_WORKSPACE_STATE_WITH_CONTROL_PLANE_RECONCILIATION"),
                Map.entry("restartRecovery", "TERMINAL_RUNS_RESTORED_ACTIVE_RUNS_BLOCKED_FOR_EXPLICIT_RETRY")
        );
    }

    private void execute(RunState state) {
        DurableRunLeaseStore.Lease lease;
        try {
            lease = leaseStore.acquire(
                    state.request.organizationId(), state.runId, state.createdAt,
                    fingerprint(state.request));
        } catch (DurableRunLeaseStore.LeaseException error) {
            synchronized (state) {
                if (state.cancelled.get()) return;
                if (error.failure().retryable()) {
                    state.status = RunStatus.QUEUED;
                    if (!error.failure().name().equals(state.failureCode)) {
                        appendEvent(state, Stage.IMPORT_GIT, "QUEUED",
                                "Durable queue admission delayed: " + error.failure().name());
                    }
                    state.failureCode = error.failure().name();
                    state.failureMessage = "Waiting for tenant-bound durable execution capacity.";
                    touch(state);
                    long delay = 1 + ThreadLocalRandom.current().nextLong(3);
                    state.future = scheduler.schedule(
                            () -> state.future = tasks.submit(() -> execute(state)),
                            delay,
                            TimeUnit.SECONDS);
                } else {
                    state.status = RunStatus.BLOCKED;
                    state.failureCode = error.failure().name();
                    state.failureMessage = "Durable queue policy blocked this run.";
                    appendEvent(state, Stage.IMPORT_GIT, "BLOCKED", state.failureMessage);
                    touch(state);
                }
            }
            return;
        }
        ScheduledFuture<?> heartbeat = scheduler.scheduleAtFixedRate(() -> {
            try {
                lease.heartbeat();
            } catch (RuntimeException error) {
                state.cancelled.set(true);
                Process process = state.activeProcess.getAndSet(null);
                if (process != null) process.destroyForcibly();
            }
        }, lease.heartbeatInterval().toSeconds(), lease.heartbeatInterval().toSeconds(),
                TimeUnit.SECONDS);
        synchronized (state) {
            if (state.cancelled.get()) {
                heartbeat.cancel(false);
                lease.release("CANCELLED");
                return;
            }
            state.status = RunStatus.RUNNING;
            state.failureCode = null;
            state.failureMessage = null;
            touch(state);
        }
        try {
            Path executionRoot = state.runRoot.resolve("execution");
            createDirectory(executionRoot);
            ExecutionResult result = promoteTransformerResult(
                    state,
                    executionRoot,
                    transformer.execute(state.request, executionRoot, control(state))
            );
            synchronized (state) {
                state.result = result;
                state.resolvedCommitSha = result.resolvedCommitSha();
                state.snapshotId = result.snapshotId();
                state.snapshotDigest = result.snapshotDigest();
                state.fingerprint = result.fingerprint();
                state.fcmArtifact = result.fcmArtifact();
                state.artifactSha256 = result.artifactSha256();
                state.artifactSize = result.artifactSize();
                touch(state);
            }
            IndependentValidationResult decision = verifier.validate(result, state.runRoot, control(state));
            if (!"PASS".equals(decision.status())
                    || !result.artifactSha256().equals(decision.artifactSha256())) {
                throw new BlockedException(
                        "INDEPENDENT_VALIDATION_NOT_PASSING",
                        "Independent validation did not return a digest-bound PASS decision.");
            }
            synchronized (state) {
                state.independentValidation = decision;
                state.stage = Stage.READY;
                state.status = RunStatus.SUCCEEDED;
                appendEvent(state, Stage.READY, "PASS",
                        "Migration artifact passed independent validation and is ready to download");
                touch(state);
            }
            if (state.request.startAfterVerification()) {
                synchronized (state) {
                    state.runtimeStatus = RuntimeStatus.STARTING;
                    touch(state);
                }
                launchRuntime(state);
            }
        } catch (BlockedException error) {
            synchronized (state) {
                if (state.cancelled.get() || "RUN_CANCELLED".equals(error.code())) {
                    state.status = RunStatus.CANCELLED;
                } else {
                    state.status = RunStatus.BLOCKED;
                }
                state.failureCode = error.code();
                state.failureMessage = error.getMessage();
                appendEvent(state, state.stage, state.status.name(), error.getMessage());
                touch(state);
            }
        } catch (RuntimeException error) {
            synchronized (state) {
                state.status = RunStatus.FAILED;
                state.failureCode = "SPRING_UPGRADE_INTERNAL_FAILURE";
                state.failureMessage = "The migration worker failed safely; inspect the redacted logs.";
                appendEvent(state, state.stage, "FAILED", state.failureMessage);
                touch(state);
            }
        } finally {
            heartbeat.cancel(false);
            String outcome = switch (state.status) {
                case SUCCEEDED -> "SUCCEEDED";
                case CANCELLED -> "CANCELLED";
                case BLOCKED -> "BLOCKED";
                default -> "FAILED";
            };
            try {
                lease.release(outcome);
            } catch (RuntimeException error) {
                synchronized (state) {
                    state.status = RunStatus.BLOCKED;
                    state.failureCode = "QUEUE_LEASE_RELEASE_FAILED";
                    state.failureMessage = "Durable execution lease could not be reconciled.";
                    appendEvent(state, state.stage, "BLOCKED", state.failureMessage);
                    touch(state);
                }
            }
        }
    }

    /**
     * Repository-controlled Maven plugins run in the Transformer, so its writable directory is not
     * an authority directory. Validate all returned paths and the exact FCM, then promote only the
     * FCM bytes into Worker-owned Evidence after the Transformer execution port has returned.
     */
    private ExecutionResult promoteTransformerResult(
            RunState state,
            Path executionRoot,
            ExecutionResult candidate
    ) {
        Objects.requireNonNull(candidate, "transformer result");
        Path migrated = requireExecutionOutput(executionRoot, candidate.migratedRepository(), true);
        Path artifact = requireExecutionOutput(executionRoot, candidate.downloadArtifact(), false);
        Path transformerFcm = resolveExecutionOutput(
                executionRoot, candidate.fcmArtifact(), false);
        if (!candidate.artifactSha256().equals(sha256(artifact))) {
            throw new BlockedException(
                    "TRANSFORM_ARTIFACT_DIGEST_MISMATCH",
                    "Transformation Artifact changed before authority promotion.");
        }
        try {
            byte[] fcmBytes = Files.readAllBytes(transformerFcm);
            if (fcmBytes.length == 0 || fcmBytes.length > 2 * 1024 * 1024) {
                throw new BlockedException(
                        "FCM_AUTHORITY_PROMOTION_REJECTED",
                        "Framework Contract Model exceeded its bounded authority policy.");
            }
            JsonNode fcm = json.readTree(fcmBytes);
            requireFcmText(fcm, "schema_version", "1.0");
            requireFcmText(fcm, "source_commit", candidate.resolvedCommitSha());
            requireFcmText(fcm, "source_snapshot_sha256", candidate.snapshotDigest());
            requireFcmText(fcm, "extraction_status", "STATIC_AND_SOURCE_BASELINE");
            /*
             * The Transformer selects the route, so the Worker must resolve the
             * declared route id against its own catalog and validate the tuple
             * against that route. Accepting the Transformer's version claims
             * without re-resolving them would let a compromised Transformer
             * declare any tuple it wanted.
             */
            String declaredRouteId = fcm.path("route_id").asText("");
            SpringRouteCatalog.Selection authoritativeSelection =
                    selectRoute(candidate.fingerprint(), state.request);
            SpringRouteCatalog.SpringRoute route = authoritativeSelection.route();
            if (!route.routeId().equals(declaredRouteId)) {
                throw new BlockedException(
                        "FCM_ROUTE_MISMATCH",
                        "Framework Contract Model route does not match the requested exact target tuple.");
            }
            requireFcmText(fcm, "pack_key", route.packKey());
            JsonNode tuple = fcm.path("exact_tuple");
            String declaredSourceBoot = tuple.path("sourceSpringBoot").asText("");
            String declaredSourceJava = tuple.path("sourceJava").asText("");
            if (!Objects.equals(candidate.fingerprint().sourceFrameworkVersion(), declaredSourceBoot)
                    || !SpringRouteCatalog.withinRange(declaredSourceBoot,
                            route.sourceBootMinInclusive(), route.sourceBootMaxExclusive())) {
                throw new BlockedException("FCM_SOURCE_BOOT_OUTSIDE_ROUTE",
                        "Framework Contract Model source version differs from the fingerprint or route range.");
            }
            if (!Objects.equals(SpringRouteCatalog.normalizeJava(candidate.fingerprint().javaVersion()),
                            SpringRouteCatalog.normalizeJava(declaredSourceJava))
                    || !route.sourceJavaVersions().contains(SpringRouteCatalog.normalizeJava(declaredSourceJava))) {
                throw new BlockedException("FCM_SOURCE_JAVA_OUTSIDE_ROUTE",
                        "Framework Contract Model source Java differs from the fingerprint or route set.");
            }
            SpringUpgradeModels.ExactTuple exact = route.tuple(
                    declaredSourceBoot, SpringRouteCatalog.normalizeJava(declaredSourceJava));
            requireFcmText(tuple, "sourceBuildTool", exact.sourceBuildTool());
            requireFcmText(tuple, "targetSpringBoot", route.targetBoot());
            requireFcmText(tuple, "targetJava", route.targetJava());
            requireFcmText(tuple, "targetBuildTool", exact.targetBuildTool());
            requireFcmText(tuple, "rewriteSpring", route.rewriteSpring());
            requireFcmText(tuple, "rewriteMavenPlugin", route.rewriteMavenPlugin());

            Path authorityFcm = state.runRoot.resolve("evidence/framework-contract-model.json");
            atomicBytes(authorityFcm, fcmBytes);
            Map<String, Object> receipt = new LinkedHashMap<>();
            receipt.put("schema_version", "1.0");
            receipt.put("producer_role", "TRANSFORMER_EXECUTION_PORT");
            receipt.put("authority_role", "CONTROL_WORKER");
            receipt.put("run_id", state.runId);
            receipt.put("source_snapshot_sha256", candidate.snapshotDigest());
            receipt.put("fcm_sha256", sha256(authorityFcm));
            receipt.put("transformer_writable_subtree", "execution/");
            receipt.put("authority_state_outside_subtree", true);
            receipt.put("product_bind_boundary_required", true);
            receipt.put("authority_path", "evidence/framework-contract-model.json");
            receipt.put("promoted_at", clock.instant());
            atomicJson(state.runRoot.resolve("evidence/fcm-authority.json"), receipt);
            return new ExecutionResult(
                    candidate.resolvedCommitSha(),
                    candidate.snapshotId(),
                    candidate.snapshotDigest(),
                    candidate.fingerprint(),
                    state.runRoot.relativize(authorityFcm).toString(),
                    migrated,
                    artifact,
                    candidate.artifactSha256(),
                    candidate.artifactSize(),
                    candidate.healthCandidates()
            );
        } catch (BlockedException error) {
            throw error;
        } catch (IOException | RuntimeException error) {
            if (error instanceof BlockedException blocked) throw blocked;
            throw new BlockedException(
                    "FCM_AUTHORITY_PROMOTION_REJECTED",
                    "Framework Contract Model could not be promoted into authoritative Evidence.");
        }
    }

    private static Path requireExecutionOutput(Path executionRoot, Path raw, boolean directory) {
        Path value = Objects.requireNonNull(raw, "transformer output").toAbsolutePath().normalize();
        Path expectedRoot;
        Path real;
        try {
            expectedRoot = executionRoot.toRealPath(LinkOption.NOFOLLOW_LINKS);
            real = value.toRealPath(LinkOption.NOFOLLOW_LINKS);
        } catch (IOException error) {
            throw new BlockedException(
                    "TRANSFORM_OUTPUT_PATH_REJECTED",
                    "Transformation output is unavailable.");
        }
        boolean expectedType = directory
                ? Files.isDirectory(real, LinkOption.NOFOLLOW_LINKS)
                : Files.isRegularFile(real, LinkOption.NOFOLLOW_LINKS);
        if (!real.startsWith(expectedRoot)
                || real.equals(expectedRoot)
                || Files.isSymbolicLink(value)
                || !expectedType) {
            throw new BlockedException(
                    "TRANSFORM_OUTPUT_PATH_REJECTED",
                    "Transformation output escaped its isolated execution workspace.");
        }
        return value;
    }

    private static Path resolveExecutionOutput(Path executionRoot, String relativeValue, boolean directory) {
        try {
            Path relative = Path.of(relativeValue);
            if (relative.isAbsolute() || relative.normalize().startsWith("..")) {
                throw new BlockedException(
                        "TRANSFORM_OUTPUT_PATH_REJECTED",
                        "Transformation output path escaped its isolated execution workspace.");
            }
            return requireExecutionOutput(executionRoot, executionRoot.resolve(relative), directory);
        } catch (InvalidPathException error) {
            throw new BlockedException(
                    "TRANSFORM_OUTPUT_PATH_REJECTED",
                    "Transformation output path is invalid.");
        }
    }

    private static void requireFcmText(JsonNode node, String field, String expected) {
        if (!expected.equals(node.path(field).asText())) {
            throw new BlockedException(
                    "FCM_AUTHORITY_PROMOTION_REJECTED",
                    "Framework Contract Model does not match the exact migration route.");
        }
    }

    private void atomicJson(Path path, Object value) throws IOException {
        atomicBytes(path, json.writerWithDefaultPrettyPrinter().writeValueAsBytes(value));
    }

    private static void atomicBytes(Path path, byte[] value) throws IOException {
        Files.createDirectories(path.getParent());
        Path temporary = Files.createTempFile(path.getParent(), path.getFileName().toString(), ".tmp");
        try {
            Files.write(temporary, value, StandardOpenOption.TRUNCATE_EXISTING);
            try {
                Files.move(temporary, path,
                        StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private void launchRuntime(RunState state) {
        try {
            RuntimeHandle handle = transformer.start(state.result, state.request, state.runRoot, control(state));
            if (state.runtimeStopRequested.get()) {
                transformer.stop(handle, control(state));
                synchronized (state) {
                    state.runtimeHandle = null;
                    state.runtimeStatus = RuntimeStatus.STOPPED;
                    state.activeProcess.set(null);
                    touch(state);
                }
                return;
            }
            synchronized (state) {
                state.runtimeHandle = handle;
                state.runtimePort = handle.port();
                state.healthPath = handle.healthPath();
                state.runtimeStatus = RuntimeStatus.HEALTHY;
                state.failureCode = null;
                state.failureMessage = null;
                touch(state);
            }
        } catch (BlockedException error) {
            synchronized (state) {
                if (state.runtimeStopRequested.get()) {
                    state.runtimeStatus = RuntimeStatus.STOPPED;
                    state.failureCode = null;
                    state.failureMessage = null;
                } else {
                    state.runtimeStatus = RuntimeStatus.UNHEALTHY;
                    state.failureCode = error.code();
                    state.failureMessage = error.getMessage();
                    appendEvent(state, state.stage, "BLOCKED", error.getMessage());
                }
                touch(state);
            }
        } catch (RuntimeException error) {
            synchronized (state) {
                if (state.runtimeStopRequested.get()) {
                    state.runtimeStatus = RuntimeStatus.STOPPED;
                    state.failureCode = null;
                    state.failureMessage = null;
                } else {
                    state.runtimeStatus = RuntimeStatus.UNHEALTHY;
                    state.failureCode = "APPLICATION_RUNTIME_FAILURE";
                    state.failureMessage = "The isolated application runtime failed safely.";
                    appendEvent(state, state.stage, "FAILED", state.failureMessage);
                }
                touch(state);
            }
        }
    }

    private SpringUpgradeExecutionPort.Control control(RunState state) {
        return new SpringUpgradeExecutionPort.Control() {
            @Override public void stage(Stage stage, String message) {
                synchronized (state) {
                    state.stage = stage;
                    appendEvent(state, stage, "RUNNING", message);
                    appendLog(state, stage.name() + " " + message);
                    touch(state);
                }
            }

            @Override public void log(String line) {
                synchronized (state) {
                    appendLog(state, line);
                }
            }

            @Override public void process(Process process) {
                state.activeProcess.set(process);
            }

            @Override public boolean cancelled() {
                return state.cancelled.get() || Thread.currentThread().isInterrupted();
            }
        };
    }

    private void restoreDurableRuns() {
        Path root = workspaceRoot.resolve("spring-upgrades");
        createDirectory(root);
        try (DirectoryStream<Path> directories = Files.newDirectoryStream(root)) {
            for (Path runRoot : directories) {
                if (!Files.isDirectory(runRoot, LinkOption.NOFOLLOW_LINKS)) continue;
                String runId = runRoot.getFileName().toString();
                if (!runId.matches("[0-9a-fA-F-]{36}")) {
                    throw new IllegalStateException("durable Spring run directory has an invalid identity: " + runRoot);
                }
                Path stateFile = runRoot.resolve("evidence/run-state.json");
                if (!Files.isRegularFile(stateFile, LinkOption.NOFOLLOW_LINKS)) continue;
                restoreDurableRun(runId, runRoot.toAbsolutePath().normalize(), stateFile);
            }
        } catch (IOException error) {
            throw new IllegalStateException("durable Spring upgrade state could not be enumerated", error);
        }
    }

    private void restoreDurableRun(String expectedRunId, Path runRoot, Path stateFile) {
        try {
            JsonNode node = json.readTree(stateFile.toFile());
            requirePersistedText(node, "run_id", expectedRunId);
            StartRequest request = json.treeToValue(node.path("request"), StartRequest.class);
            if (request == null) throw new IllegalStateException("persisted request is missing");
            Instant createdAt = json.treeToValue(node.path("created_at"), Instant.class);
            RunState state = new RunState(
                    expectedRunId,
                    nullableText(node, "retry_of_run_id"),
                    request,
                    node.path("attempt").asInt(1),
                    runRoot,
                    createdAt
            );
            state.updatedAt = json.treeToValue(node.path("updated_at"), Instant.class);
            state.status = RunStatus.valueOf(node.path("status").asText());
            state.stage = Stage.valueOf(node.path("stage").asText());
            state.runtimeStatus = RuntimeStatus.valueOf(node.path("runtime_status").asText());
            state.resolvedCommitSha = nullableText(node, "resolved_commit_sha");
            state.snapshotId = nullableText(node, "snapshot_id");
            state.snapshotDigest = nullableText(node, "snapshot_digest");
            state.fcmArtifact = nullableText(node, "fcm_artifact");
            state.artifactSha256 = nullableText(node, "artifact_sha256");
            state.artifactSize = node.path("artifact_size").isNumber()
                    ? node.path("artifact_size").longValue() : null;
            state.healthPath = nullableText(node, "health_path");
            state.runtimePort = node.path("runtime_port").isInt()
                    ? node.path("runtime_port").intValue() : null;
            state.failureCode = nullableText(node, "failure_code");
            state.failureMessage = nullableText(node, "failure_message");
            state.logsTruncated = node.path("logs_truncated").asBoolean(false);
            if (!node.path("fingerprint").isMissingNode() && !node.path("fingerprint").isNull()) {
                state.fingerprint = json.treeToValue(node.path("fingerprint"), Fingerprint.class);
            }
            if (!node.path("independent_validation").isMissingNode()
                    && !node.path("independent_validation").isNull()) {
                state.independentValidation = json.treeToValue(
                        node.path("independent_validation"), IndependentValidationResult.class);
            }
            if (node.path("events").isArray()) {
                for (JsonNode event : node.path("events")) {
                    Event restored = json.treeToValue(event, Event.class);
                    state.events.addLast(restored);
                    state.eventSequence.accumulateAndGet(restored.sequence(), Math::max);
                }
            }
            if (node.path("logs").isArray()) {
                for (JsonNode line : node.path("logs")) {
                    if (state.logs.size() >= MAX_LOG_LINES) {
                        state.logs.removeFirst();
                        state.logsTruncated = true;
                    }
                    state.logs.addLast(redact(line.asText()));
                }
            }
            String artifactRelative = nullableText(node, "artifact_relative_path");
            String migratedRelative = nullableText(node, "migrated_relative_path");
            if (artifactRelative != null && migratedRelative != null && state.fingerprint != null
                    && state.resolvedCommitSha != null && state.snapshotId != null
                    && state.snapshotDigest != null && state.artifactSha256 != null
                    && state.artifactSize != null) {
                Path artifact = resolvePersistedPath(runRoot, artifactRelative);
                Path migrated = resolvePersistedPath(runRoot, migratedRelative);
                List<String> healthCandidates = new ArrayList<>();
                if (node.path("health_candidates").isArray()) {
                    node.path("health_candidates").forEach(value -> healthCandidates.add(value.asText()));
                }
                state.result = new ExecutionResult(
                        state.resolvedCommitSha,
                        state.snapshotId,
                        state.snapshotDigest,
                        state.fingerprint,
                        Objects.toString(state.fcmArtifact, ""),
                        migrated,
                        artifact,
                        state.artifactSha256,
                        state.artifactSize,
                        healthCandidates
                );
            }
            boolean normalized = false;
            if (state.status == RunStatus.QUEUED || state.status == RunStatus.RUNNING) {
                state.status = RunStatus.BLOCKED;
                state.failureCode = "WORKER_RESTARTED_RETRY_REQUIRED";
                state.failureMessage = "The worker restarted during migration; use retry to create a traceable new attempt.";
                appendEvent(state, state.stage, "BLOCKED", state.failureMessage);
                normalized = true;
            }
            String remoteRuntimeId = nullableText(node, "remote_runtime_id");
            if (remoteRuntimeId != null) {
                UUID.fromString(remoteRuntimeId);
                state.runtimeHandle = new RuntimeHandle(
                        null,
                        remoteRuntimeId,
                        request.organizationId(),
                        state.runtimePort == null ? 8080 : state.runtimePort,
                        state.healthPath
                );
            }
            if (state.runtimeStatus == RuntimeStatus.STARTING || state.runtimeStatus == RuntimeStatus.HEALTHY) {
                state.runtimeStatus = RuntimeStatus.UNHEALTHY;
                state.failureCode = "RUNTIME_RECONCILIATION_REQUIRED";
                state.failureMessage = "Worker restarted; re-run health reconciliation or stop the isolated runtime.";
                appendEvent(state, Stage.HEALTH_CHECK, "BLOCKED", state.failureMessage);
                normalized = true;
            }
            if (state.result != null && downloadAvailable(state)) {
                requireArtifactIntegrity(state);
            }
            RunState duplicate = runs.putIfAbsent(expectedRunId, state);
            if (duplicate != null) throw new IllegalStateException("duplicate durable Spring run identity");
            String scope = state.retryOfRunId == null
                    ? request.organizationId() + "|create|" + request.idempotencyKey()
                    : request.organizationId() + "|retry|" + state.retryOfRunId + "|" + request.idempotencyKey();
            IdempotencyEntry existing = idempotency.putIfAbsent(
                    scope, new IdempotencyEntry(expectedRunId, fingerprint(request)));
            if (existing != null && !existing.runId().equals(expectedRunId)) {
                throw new IllegalStateException("durable Spring idempotency identity collision");
            }
            if (normalized) touch(state);
        } catch (RuntimeException | IOException error) {
            throw new IllegalStateException(
                    "durable Spring upgrade state could not be restored from " + stateFile, error);
        }
    }

    private static Path resolvePersistedPath(Path runRoot, String relative) {
        Path value = runRoot.resolve(relative).normalize();
        if (!value.startsWith(runRoot) || value.equals(runRoot)) {
            throw new IllegalStateException("persisted Spring run path escaped its workspace");
        }
        return value;
    }

    private static void requirePersistedText(JsonNode node, String field, String expected) {
        if (!expected.equals(node.path(field).asText())) {
            throw new IllegalStateException("persisted " + field + " does not match its durable identity");
        }
    }

    private static String nullableText(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isMissingNode() || value.isNull() || value.asText().isBlank()
                ? null : value.asText();
    }

    private RunState newState(StartRequest request, String retryOfRunId, int attempt) {
        String runId = UUID.randomUUID().toString();
        Path runRoot = workspaceRoot.resolve("spring-upgrades").resolve(runId).normalize();
        if (!runRoot.startsWith(workspaceRoot)) throw new IllegalStateException("run workspace escaped root");
        createDirectory(runRoot);
        Instant now = clock.instant();
        RunState state = new RunState(runId, retryOfRunId, request, attempt, runRoot, now);
        appendEvent(state, Stage.IMPORT_GIT, "QUEUED", "Migration run queued");
        persist(state);
        return state;
    }

    private RunState require(String organizationId, String runId) {
        RunState state = runs.get(runId);
        if (state == null || !state.request.organizationId().equals(organizationId)) throw new NotFound();
        return state;
    }

    private RunView view(RunState state) {
        synchronized (state) {
            return new RunView(
                    state.runId,
                    state.retryOfRunId,
                    state.request.organizationId(),
                    packKey(state),
                    state.status,
                    state.stage,
                    state.runtimeStatus,
                    state.attempt,
                    state.request.repositoryUrl(),
                    state.request.requestedRef(),
                    state.resolvedCommitSha,
                    state.snapshotId,
                    state.snapshotDigest,
                    exactTuple(state.fingerprint, state.request),
                    state.fingerprint,
                    state.fcmArtifact,
                    downloadAvailable(state),
                    state.artifactSha256,
                    state.artifactSize,
                    state.healthPath,
                    state.runtimePort,
                    state.failureCode,
                    state.failureMessage,
                    state.independentValidation,
                    List.copyOf(state.events),
                    state.createdAt,
                    state.updatedAt
            );
        }
    }

    private static boolean downloadAvailable(RunState state) {
        return state.result != null
                && state.independentValidation != null
                && "PASS".equals(state.independentValidation.status())
                && state.result.artifactSha256().equals(state.independentValidation.artifactSha256());
    }

    private static ExactTuple exactTuple(Fingerprint fingerprint, StartRequest request) {
        if (fingerprint == null) {
            return new ExactTuple(
                    "UNKNOWN", "UNKNOWN", "UNKNOWN",
                    request.targetSpringBoot(), request.targetJava(), "UNKNOWN",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN);
        }
        try {
            SpringRouteCatalog.Selection selection = selectRoute(fingerprint, request);
            return selection.route().tuple(
                    fingerprint.sourceFrameworkVersion(), fingerprint.javaVersion());
        } catch (RuntimeException ignored) {
            // A queued or blocked run may not have a complete route tuple yet.
            // Preserve the requested target without fabricating a source tuple.
            return new ExactTuple(
                    Objects.toString(fingerprint.sourceFrameworkVersion(), "UNKNOWN"),
                    Objects.toString(fingerprint.javaVersion(), "UNKNOWN"),
                    Objects.toString(fingerprint.buildTool(), "UNKNOWN"),
                    request.targetSpringBoot(), request.targetJava(), "UNKNOWN",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN);
        }
    }

    private static String packKey(RunState state) {
        if (state.fingerprint == null) return "PENDING_ROUTE_SELECTION";
        try {
            return selectRoute(state.fingerprint, state.request).route().packKey();
        } catch (RuntimeException ignored) {
            return "PENDING_ROUTE_SELECTION";
        }
    }

    private static SpringRouteCatalog.Selection selectRoute(
            Fingerprint fingerprint,
            StartRequest request
    ) {
        if ("spring-mvc".equals(fingerprint.sourceFrameworkFamily())) {
            return SpringRouteCatalog.selectSpringMvc(
                    fingerprint.sourceFrameworkVersion(),
                    fingerprint.javaVersion(),
                    fingerprint.buildTool(),
                    request.targetSpringBoot(),
                    request.targetJava());
        }
        return SpringRouteCatalog.select(
                fingerprint.springBootVersion(),
                fingerprint.javaVersion(),
                fingerprint.buildTool(),
                request.targetSpringBoot(),
                request.targetJava());
    }

    private static Path requireArtifactIntegrity(RunState state) {
        Path artifact = state.result.downloadArtifact().toAbsolutePath().normalize();
        if (!artifact.startsWith(state.runRoot)
                || !Files.isRegularFile(artifact, LinkOption.NOFOLLOW_LINKS)) {
            throw new Conflict("DOWNLOAD_ARTIFACT_UNAVAILABLE");
        }
        if (!state.result.artifactSha256().equals(sha256(artifact))) {
            throw new Conflict("DOWNLOAD_ARTIFACT_DIGEST_MISMATCH");
        }
        return artifact;
    }

    private void touch(RunState state) {
        state.updatedAt = clock.instant();
        persist(state);
    }

    private void persist(RunState state) {
        try {
            Path evidence = state.runRoot.resolve("evidence");
            Files.createDirectories(evidence);
            Path temporary = evidence.resolve("run-state.json.tmp");
            json.writerWithDefaultPrettyPrinter().writeValue(temporary.toFile(), viewWithoutRecursion(state));
            try {
                Files.move(temporary, evidence.resolve("run-state.json"),
                        StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(temporary, evidence.resolve("run-state.json"), StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException error) {
            throw new IllegalStateException("durable Spring run state persistence failed", error);
        }
    }

    private Map<String, Object> viewWithoutRecursion(RunState state) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("schema_version", "1.0");
        value.put("run_id", state.runId);
        value.put("retry_of_run_id", state.retryOfRunId);
        value.put("organization_id", state.request.organizationId());
        value.put("pack_key", PACK_KEY);
        value.put("status", state.status);
        value.put("stage", state.stage);
        value.put("runtime_status", state.runtimeStatus);
        value.put("attempt", state.attempt);
        value.put("request", state.request);
        value.put("resolved_commit_sha", state.resolvedCommitSha);
        value.put("snapshot_id", state.snapshotId);
        value.put("snapshot_digest", state.snapshotDigest);
        value.put("fingerprint", state.fingerprint);
        value.put("fcm_artifact", state.fcmArtifact);
        value.put("artifact_sha256", state.artifactSha256);
        value.put("artifact_size", state.artifactSize);
        value.put("artifact_relative_path", state.result == null
                ? null : state.runRoot.relativize(state.result.downloadArtifact()).toString());
        value.put("migrated_relative_path", state.result == null
                ? null : state.runRoot.relativize(state.result.migratedRepository()).toString());
        value.put("health_candidates", state.result == null ? List.of() : state.result.healthCandidates());
        value.put("independent_validation", state.independentValidation);
        value.put("failure_code", state.failureCode);
        value.put("failure_message", state.failureMessage);
        value.put("health_path", state.healthPath);
        value.put("runtime_port", state.runtimePort);
        value.put("remote_runtime_id", state.runtimeHandle == null ? null : state.runtimeHandle.runtimeId());
        value.put("created_at", state.createdAt);
        value.put("updated_at", state.updatedAt);
        value.put("events", List.copyOf(state.events));
        value.put("logs", List.copyOf(state.logs));
        value.put("logs_truncated", state.logsTruncated);
        return value;
    }

    private static void appendEvent(RunState state, Stage stage, String status, String message) {
        if (state.events.size() >= MAX_EVENTS) state.events.removeFirst();
        state.events.addLast(new Event(
                state.eventSequence.incrementAndGet(),
                stage,
                status,
                redact(message),
                Instant.now()
        ));
    }

    private static void appendLog(RunState state, String raw) {
        for (String line : Objects.toString(raw, "").split("\\R", -1)) {
            if (state.logs.size() >= MAX_LOG_LINES) {
                state.logs.removeFirst();
                state.logsTruncated = true;
            }
            state.logs.addLast(redact(line));
        }
    }

    private static String redact(String value) {
        String bounded = Objects.toString(value, "");
        if (bounded.length() > 4_000) bounded = bounded.substring(0, 4_000) + "…";
        return SECRET.matcher(bounded).replaceAll("$1 [REDACTED]");
    }

    private static void validateRequest(String organizationId, StartRequest request) {
        if (request == null) throw new InvalidRequest("Request is required.");
        if (organizationId == null || organizationId.isBlank()
                || !organizationId.equals(request.organizationId())
                || organizationId.length() > 128) {
            throw new InvalidRequest("Authenticated organization does not match the request boundary.");
        }
        if (request.sourceMode() == null) throw new InvalidRequest("Source mode is required.");
        if (request.idempotencyKey() == null || request.idempotencyKey().isBlank()
                || request.idempotencyKey().length() > 128) {
            throw new InvalidRequest("A bounded idempotency key is required.");
        }
        if (request.targetSpringBoot() == null
                || !request.targetSpringBoot().matches("[0-9]+\\.[0-9]+\\.[0-9]+(?:[-.][A-Za-z0-9]+)*")
                || request.targetJava() == null
                || !request.targetJava().matches("[0-9]{1,2}")) {
            throw new InvalidRequest("An exact target Spring Boot and Java tuple is required.");
        }
        if (request.sourceMode() == SourceMode.PUBLIC_GIT
                && (request.repositoryUrl() == null || request.repositoryUrl().isBlank())) {
            throw new InvalidRequest("Public Git repository URL is required.");
        }
        if (request.expectedCommitSha() != null
                && !request.expectedCommitSha().isBlank()
                && !request.expectedCommitSha().matches("[0-9a-f]{40}")) {
            throw new InvalidRequest("Expected Commit must be an exact lowercase 40-character SHA.");
        }
        if (request.sourceMode() == SourceMode.MATERIALIZED_SNAPSHOT) {
            if (request.expectedCommitSha() == null
                    || !request.expectedCommitSha().matches("[0-9a-f]{40}")
                    || request.snapshotId() == null
                    || !request.snapshotId().matches("[A-Za-z0-9._-]{3,160}")
                    || request.materializedRelativePath() == null
                    || request.materializedRelativePath().isBlank()
                    || request.materializedRelativePath().length() > 512) {
                throw new InvalidRequest(
                        "Materialized Snapshot requires an exact Snapshot ID, Commit SHA and bounded relative path.");
            }
            try {
                Path relative = Path.of(request.materializedRelativePath());
                if (relative.isAbsolute() || relative.normalize().startsWith("..")) {
                    throw new InvalidRequest("Materialized Snapshot path must stay below the Runner workspace.");
                }
            } catch (InvalidPathException error) {
                throw new InvalidRequest("Materialized Snapshot path is invalid.");
            }
        }
        if (request.requestedRef() == null || request.requestedRef().isBlank()) {
            throw new InvalidRequest("An exact Git branch or tag ref is required.");
        }
    }

    private static String fingerprint(StartRequest request) {
        String value = String.join("\n",
                Objects.toString(request.organizationId(), ""),
                Objects.toString(request.sourceMode(), ""),
                Objects.toString(request.repositoryUrl(), ""),
                Objects.toString(request.requestedRef(), ""),
                Objects.toString(request.expectedCommitSha(), ""),
                Objects.toString(request.snapshotId(), ""),
                Objects.toString(request.materializedRelativePath(), ""),
                Boolean.toString(request.startAfterVerification()),
                Objects.toString(request.targetSpringBoot(), ""),
                Objects.toString(request.targetJava(), ""));
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static void createDirectory(Path path) {
        try {
            Files.createDirectories(path);
        } catch (IOException error) {
            throw new IllegalStateException("Spring upgrade workspace is unavailable", error);
        }
    }

    private static String sha256(Path path) {
        try (var input = Files.newInputStream(path)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) >= 0) {
                digest.update(buffer, 0, count);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (Exception error) {
            throw new Conflict("DOWNLOAD_ARTIFACT_DIGEST_UNAVAILABLE");
        }
    }

    private static boolean terminal(RunStatus status) {
        return status == RunStatus.SUCCEEDED || status == RunStatus.FAILED
                || status == RunStatus.BLOCKED || status == RunStatus.CANCELLED;
    }

    @PreDestroy
    void close() {
        for (RunState state : runs.values()) {
            state.cancelled.set(true);
            Process process = state.activeProcess.getAndSet(null);
            if (process != null) process.destroyForcibly();
        }
        tasks.shutdownNow();
        scheduler.shutdownNow();
        try {
            if (!tasks.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Spring upgrade tasks did not terminate during shutdown");
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }
        try {
            if (!scheduler.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Spring queue scheduler did not terminate during shutdown");
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }
    }

    private record IdempotencyEntry(String runId, String fingerprint) {}

    static final class NotFound extends RuntimeException {}
    static final class Conflict extends RuntimeException {
        private final String code;
        Conflict(String code) { this.code = code; }
        String code() { return code; }
    }
    static final class IdempotencyConflict extends RuntimeException {}
    static final class InvalidRequest extends RuntimeException {
        InvalidRequest(String message) { super(message); }
    }

    private static final class RunState {
        final String runId;
        final String retryOfRunId;
        final StartRequest request;
        final int attempt;
        final Path runRoot;
        final Instant createdAt;
        final AtomicBoolean cancelled = new AtomicBoolean();
        final AtomicBoolean runtimeStopRequested = new AtomicBoolean();
        final AtomicReference<Process> activeProcess = new AtomicReference<>();
        final AtomicLong eventSequence = new AtomicLong();
        final Deque<Event> events = new ArrayDeque<>();
        final Deque<String> logs = new ArrayDeque<>();
        RunStatus status = RunStatus.QUEUED;
        Stage stage = Stage.IMPORT_GIT;
        RuntimeStatus runtimeStatus = RuntimeStatus.NOT_STARTED;
        Instant updatedAt;
        boolean logsTruncated;
        int runtimePortValue;
        Future<?> future;
        Future<?> runtimeFuture;
        ExecutionResult result;
        RuntimeHandle runtimeHandle;
        IndependentValidationResult independentValidation;
        Fingerprint fingerprint;
        String resolvedCommitSha;
        String snapshotId;
        String snapshotDigest;
        String fcmArtifact;
        String artifactSha256;
        Long artifactSize;
        String healthPath;
        Integer runtimePort;
        String failureCode;
        String failureMessage;

        RunState(String runId, String retryOfRunId, StartRequest request, int attempt, Path runRoot, Instant createdAt) {
            this.runId = runId;
            this.retryOfRunId = retryOfRunId;
            this.request = request;
            this.attempt = attempt;
            this.runRoot = runRoot;
            this.createdAt = createdAt;
            this.updatedAt = createdAt;
        }
    }
}
