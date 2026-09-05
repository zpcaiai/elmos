package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import static io.elmos.worker.SpringUpgradeModels.*;
import static org.junit.jupiter.api.Assertions.*;

class SpringUpgradeRunServiceTest {
    private static final Duration ASYNC_STATE_TIMEOUT = Duration.ofMinutes(3);

    @TempDir Path workspace;
    private SpringUpgradeRunService service;

    @AfterEach void close() {
        if (service != null) service.close();
    }

    @Test void independentPassIsRequiredBeforeArtifactBecomesDownloadable() throws Exception {
        service = service(new SuccessfulTransformer(), new PassingVerifier());
        StartRequest request = request("same-key");
        RunView first = service.create("org-a", request);
        RunView duplicate = service.create("org-a", request);
        assertEquals(first.runId(), duplicate.runId());

        RunView completed = awaitTerminal(first.runId(), "org-a");
        assertEquals(RunStatus.SUCCEEDED, completed.status());
        assertTrue(completed.downloadAvailable());
        assertEquals("PASS", completed.independentValidation().status());
        Path artifact = service.artifact("org-a", completed.runId());
        Path authorityRoot = workspace.resolve("spring-upgrades").resolve(completed.runId());
        assertTrue(artifact.startsWith(authorityRoot.resolve("execution")));
        assertTrue(Files.isRegularFile(authorityRoot.resolve("evidence/run-state.json")));
        assertTrue(Files.isRegularFile(authorityRoot.resolve("evidence/framework-contract-model.json")));
        assertTrue(Files.isRegularFile(authorityRoot.resolve("evidence/fcm-authority.json")));
        assertFalse(authorityRoot.resolve("evidence/run-state.json")
                .startsWith(authorityRoot.resolve("execution")));
        assertThrows(SpringUpgradeRunService.NotFound.class,
                () -> service.get("org-b", completed.runId()));
    }

    @Test void failedIndependentVerifierKeepsArtifactAndRuntimeUnavailable() {
        service = service(new SuccessfulTransformer(),
                new DisabledSpringUpgradeIndependentValidationPort("independent verifier unavailable"));
        RunView completed = awaitTerminal(service.create("org-a", request("blocked-key")).runId(), "org-a");
        assertEquals(RunStatus.BLOCKED, completed.status());
        assertEquals("INDEPENDENT_VALIDATOR_NOT_CONFIGURED", completed.failureCode());
        assertFalse(completed.downloadAvailable());
        assertThrows(SpringUpgradeRunService.Conflict.class,
                () -> service.artifact("org-a", completed.runId()));
        assertThrows(SpringUpgradeRunService.Conflict.class,
                () -> service.startRuntime("org-a", completed.runId()));
    }

    @Test void nonPassingIndependentDecisionCannotMarkRunSuccessful() {
        SpringUpgradeIndependentValidationPort inconclusive = new SpringUpgradeIndependentValidationPort() {
            @Override public IndependentValidationResult validate(
                    ExecutionResult result,
                    Path runRoot,
                    SpringUpgradeExecutionPort.Control control
            ) {
                return new IndependentValidationResult(
                        "INCONCLUSIVE",
                        "independent-test-verifier",
                        result.artifactSha256(),
                        "evidence/independent-validation.json",
                        java.time.Instant.now()
                );
            }

            @Override public boolean configured() { return true; }
            @Override public String configurationReason() { return "test"; }
        };
        service = service(new SuccessfulTransformer(), inconclusive);
        RunView completed = awaitTerminal(service.create("org-a", request("inconclusive-key")).runId(), "org-a");
        assertEquals(RunStatus.BLOCKED, completed.status());
        assertEquals("INDEPENDENT_VALIDATION_NOT_PASSING", completed.failureCode());
        assertFalse(completed.downloadAvailable());
    }

    @Test void disabledTransformerFailsClosedWithoutExecutingCustomerCode() {
        service = service(
                new DisabledSpringUpgradeExecutionPort("rootless Runner unavailable"),
                new DisabledSpringUpgradeIndependentValidationPort("verifier unavailable"));
        RunView completed = awaitTerminal(service.create("org-a", request("disabled-key")).runId(), "org-a");
        assertEquals(RunStatus.BLOCKED, completed.status());
        assertEquals("APPROVED_SPRING_UPGRADE_RUNNER_NOT_CONFIGURED", completed.failureCode());
        assertNull(completed.resolvedCommitSha());
        assertFalse(completed.downloadAvailable());
    }

    @Test void legacyBootOnlyPendingPackWithoutFingerprintNormalizesWithoutInventingARoute() throws Exception {
        SpringUpgradeExecutionPort disabled =
                new DisabledSpringUpgradeExecutionPort("rootless Runner unavailable");
        SpringUpgradeIndependentValidationPort verifier =
                new DisabledSpringUpgradeIndependentValidationPort("verifier unavailable");
        service = service(disabled, verifier);
        RunView blocked = awaitTerminal(
                service.create("org-a", request("legacy-pending-pack")).runId(), "org-a");
        assertNull(blocked.fingerprint());
        Path stateFile = workspace.resolve("spring-upgrades").resolve(blocked.runId())
                .resolve("evidence/run-state.json");
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        com.fasterxml.jackson.databind.node.ObjectNode persisted =
                (com.fasterxml.jackson.databind.node.ObjectNode) mapper.readTree(stateFile.toFile());
        persisted.put("schema_version", "1.0");
        persisted.put("pack_key", SpringUpgradeModels.PACK_KEY);
        mapper.writerWithDefaultPrettyPrinter().writeValue(stateFile.toFile(), persisted);
        service.close();

        service = service(disabled, verifier);
        RunView restored = service.get("org-a", blocked.runId());
        assertEquals("PENDING_ROUTE_SELECTION", restored.packKey());
        JsonNode normalized = mapper.readTree(stateFile.toFile());
        assertEquals("1.1", normalized.path("schema_version").asText());
        assertEquals("PENDING_ROUTE_SELECTION", normalized.path("pack_key").asText());
    }

    @Test void conflictingIdempotencyInputAndNonTerminalRetryAreRejected() throws Exception {
        CountDownLatch executionEntered = new CountDownLatch(1);
        CountDownLatch executionReleased = new CountDownLatch(1);
        SpringUpgradeExecutionPort delayed = new SuccessfulTransformer() {
            @Override public ExecutionResult execute(StartRequest request, Path runRoot, Control control) {
                executionEntered.countDown();
                try {
                    if (!executionReleased.await(
                            ASYNC_STATE_TIMEOUT.toSeconds(), TimeUnit.SECONDS)) {
                        throw new IllegalStateException("test execution release timed out");
                    }
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("test execution was interrupted", error);
                }
                return super.execute(request, runRoot, control);
            }
        };
        service = service(delayed, new PassingVerifier());
        RunView first = service.create("org-a", request("conflict-key"));
        assertTrue(executionEntered.await(
                ASYNC_STATE_TIMEOUT.toSeconds(), TimeUnit.SECONDS));
        StartRequest changed = new StartRequest("org-a", SourceMode.PUBLIC_GIT,
                "https://github.com/example/other.git", "main", null, null, null,
                false, "conflict-key");
        try {
            assertThrows(SpringUpgradeRunService.IdempotencyConflict.class,
                    () -> service.create("org-a", changed));
            assertThrows(SpringUpgradeRunService.Conflict.class,
                    () -> service.retry("org-a", first.runId(), "retry-key"));
        } finally {
            executionReleased.countDown();
        }
        assertEquals(RunStatus.SUCCEEDED,
                awaitTerminal(first.runId(), "org-a").status());
    }

    @Test void terminalFailureCanBeRetriedAsANewTraceableAttempt() {
        service = service(
                new DisabledSpringUpgradeExecutionPort("rootless Runner unavailable"),
                new DisabledSpringUpgradeIndependentValidationPort("verifier unavailable"));
        RunView first = awaitTerminal(service.create("org-a", request("first")).runId(), "org-a");
        RunView retry = service.retry("org-a", first.runId(), "retry-1");
        assertNotEquals(first.runId(), retry.runId());
        assertEquals(first.runId(), retry.retryOfRunId());
        assertEquals(2, retry.attempt());
    }

    @Test void verifiedArtifactCanStartExposeLogsAndStop() {
        LifecycleTransformer transformer = new LifecycleTransformer();
        service = service(transformer, new PassingVerifier());
        RunView completed = awaitTerminal(
                service.create("org-a", request("lifecycle")).runId(), "org-a");

        RunView starting = service.startRuntime("org-a", completed.runId());
        assertEquals(RuntimeStatus.STARTING, starting.runtimeStatus());
        RunView healthy = awaitRuntime(completed.runId(), RuntimeStatus.HEALTHY);
        assertEquals("/actuator/health", healthy.healthPath());
        assertEquals(18081, healthy.runtimePort());
        assertTrue(service.logs("org-a", completed.runId()).lines().stream()
                .anyMatch(line -> line.contains("runtime healthy")));

        RunView stopped = service.stopRuntime("org-a", completed.runId());
        assertEquals(RuntimeStatus.STOPPED, stopped.runtimeStatus());
        assertTrue(transformer.stopped.get());
    }

    @Test void remoteRuntimeExplicitStopIsIdempotent() {
        RemoteLifecycleTransformer transformer = new RemoteLifecycleTransformer(false);
        service = service(transformer, new PassingVerifier());
        RunView completed = awaitTerminal(
                service.create("org-a", request("remote-stop")).runId(), "org-a");

        service.startRuntime("org-a", completed.runId());
        awaitRuntime(completed.runId(), RuntimeStatus.HEALTHY);
        assertEquals(RuntimeStatus.STOPPED,
                service.stopRuntime("org-a", completed.runId()).runtimeStatus());
        assertEquals(RuntimeStatus.STOPPED,
                service.stopRuntime("org-a", completed.runId()).runtimeStatus());

        assertEquals(1, transformer.stopCalls.get());
    }

    @Test void failedRemoteStopRetainsHandleForIdempotentRetry() {
        RemoteLifecycleTransformer transformer = new RemoteLifecycleTransformer(false);
        transformer.failNextStop.set(true);
        service = service(transformer, new PassingVerifier());
        RunView completed = awaitTerminal(
                service.create("org-a", request("remote-stop-retry")).runId(), "org-a");
        service.startRuntime("org-a", completed.runId());
        awaitRuntime(completed.runId(), RuntimeStatus.HEALTHY);

        BlockedException failure = assertThrows(BlockedException.class,
                () -> service.stopRuntime("org-a", completed.runId()));
        assertEquals("ISOLATED_RUNTIME_STOP_FAILED", failure.code());
        assertEquals(RuntimeStatus.UNHEALTHY,
                service.get("org-a", completed.runId()).runtimeStatus());

        assertEquals(RuntimeStatus.STOPPED,
                service.stopRuntime("org-a", completed.runId()).runtimeStatus());
        service.stopRuntime("org-a", completed.runId());
        assertEquals(2, transformer.stopCalls.get());
    }

    @Test void cancellationStopsRemoteHandleReturnedAfterCancellation() throws Exception {
        RemoteLifecycleTransformer transformer = new RemoteLifecycleTransformer(true);
        service = service(transformer, new PassingVerifier());
        StartRequest request = request("remote-cancel", true);
        RunView run = service.create("org-a", request);
        assertTrue(transformer.startEntered.await(
                ASYNC_STATE_TIMEOUT.toSeconds(), TimeUnit.SECONDS));

        assertEquals(RunStatus.CANCELLED,
                service.cancel("org-a", run.runId()).status());
        assertTrue(transformer.stopped.await(
                ASYNC_STATE_TIMEOUT.toSeconds(), TimeUnit.SECONDS));
        assertEquals(1, transformer.stopCalls.get());
        assertEquals(RunStatus.CANCELLED,
                awaitTerminal(run.runId(), "org-a").status());
    }

    @Test void preDestroyStopsEveryRemoteHandleOnce() {
        RemoteLifecycleTransformer transformer = new RemoteLifecycleTransformer(false);
        service = service(transformer, new PassingVerifier());
        RunView completed = awaitTerminal(
                service.create("org-a", request("remote-close")).runId(), "org-a");
        service.startRuntime("org-a", completed.runId());
        awaitRuntime(completed.runId(), RuntimeStatus.HEALTHY);

        service.close();
        service.close();

        assertEquals(1, transformer.stopCalls.get());
    }

    @Test void completedRunAndIdempotencyRecoverAfterWorkerRestartAndTamperingFailsClosed() throws Exception {
        StartRequest request = request("durable-key");
        service = service(new SuccessfulTransformer(), new PassingVerifier());
        RunView completed = awaitTerminal(service.create("org-a", request).runId(), "org-a");
        Path artifact = service.artifact("org-a", completed.runId());
        Path leaseReceipts = workspace.resolve(".durable-queue/receipts/spring-upgrade");
        try (var receipts = Files.walk(leaseReceipts)) {
            assertEquals(1, receipts.filter(Files::isRegularFile).count(),
                    "a terminal run must not be observable before its lease receipt is durable");
        }
        service.close();

        service = service(new SuccessfulTransformer(), new PassingVerifier());
        RunView recovered = service.get("org-a", completed.runId());
        assertEquals(RunStatus.SUCCEEDED, recovered.status());
        assertTrue(recovered.downloadAvailable());
        assertEquals(completed.runId(), service.create("org-a", request).runId());
        assertEquals(artifact, service.artifact("org-a", completed.runId()));

        Files.writeString(artifact, "tampered", StandardCharsets.UTF_8);
        SpringUpgradeRunService.Conflict conflict = assertThrows(
                SpringUpgradeRunService.Conflict.class,
                () -> service.artifact("org-a", completed.runId()));
        assertEquals("DOWNLOAD_ARTIFACT_DIGEST_MISMATCH", conflict.code());
        assertThrows(SpringUpgradeRunService.Conflict.class,
                () -> service.startRuntime("org-a", completed.runId()));
    }

    @Test void mvcRunPersistsAndRestoresItsSelectedPackAndHonestExactTuple() throws Exception {
        StartRequest request = request("mvc-durable-key");
        service = service(new MvcTransformer(), new PassingVerifier());
        RunView completed = awaitTerminal(service.create("org-a", request).runId(), "org-a");

        assertEquals(RunStatus.SUCCEEDED, completed.status());
        assertEquals("spring-framework-5-3-mvc-to-spring-boot-3-5-3", completed.packKey());
        assertNull(completed.exactTuple().sourceSpringBoot());
        assertEquals("spring-mvc", completed.exactTuple().sourceFrameworkFamily());
        assertEquals("5.3.39", completed.exactTuple().sourceFrameworkVersion());
        Path stateFile = workspace.resolve("spring-upgrades").resolve(completed.runId())
                .resolve("evidence/run-state.json");
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        com.fasterxml.jackson.databind.node.ObjectNode persisted =
                (com.fasterxml.jackson.databind.node.ObjectNode) mapper.readTree(stateFile.toFile());
        assertEquals("1.1", persisted.path("schema_version").asText());
        assertEquals(completed.packKey(), persisted.path("pack_key").asText());
        service.close();

        persisted.put("schema_version", "1.0");
        mapper.writerWithDefaultPrettyPrinter().writeValue(stateFile.toFile(), persisted);
        service = service(new MvcTransformer(), new PassingVerifier());
        RunView recovered = service.get("org-a", completed.runId());
        assertEquals(completed.packKey(), recovered.packKey());
        assertNull(recovered.exactTuple().sourceSpringBoot());
        assertEquals("spring-mvc", recovered.exactTuple().sourceFrameworkFamily());
        assertEquals("1.1", mapper.readTree(stateFile.toFile()).path("schema_version").asText());

        assertThrows(IllegalStateException.class,
                () -> SpringUpgradeRunService.requirePersistedPackKey(
                        SpringUpgradeModels.PACK_KEY, recovered.fingerprint(), request));
        assertThrows(IllegalStateException.class,
                () -> SpringUpgradeRunService.requirePersistedPackKey(
                        null, recovered.fingerprint(), request));
        Fingerprint adjacentMvc = new Fingerprint(
                "UNKNOWN", "11", "maven", List.of(), List.of("spring-mvc"), List.of(),
                Map.of("spring-mvc", List.of("Controller.java")),
                "spring-mvc", "5.3.38");
        assertThrows(BlockedException.class,
                () -> SpringUpgradeRunService.requirePersistedPackKey(
                        completed.packKey(), adjacentMvc, request));
    }

    @Test void mvcFcmCannotAliasSpringFrameworkVersionAsSpringBoot() {
        service = service(new MvcTransformer(true), new PassingVerifier());
        RunView blocked = awaitTerminal(
                service.create("org-a", request("mvc-dishonest-boot")).runId(), "org-a");

        assertEquals(RunStatus.BLOCKED, blocked.status());
        assertEquals("FCM_MVC_SOURCE_BOOT_FORBIDDEN", blocked.failureCode());
        assertFalse(blocked.downloadAvailable());
    }

    @SuppressWarnings("unchecked")
    @Test void capabilitiesPublishAuthoritativeExactMvcSourceConstraint() {
        service = service(new SuccessfulTransformer(), new PassingVerifier());
        List<Map<String, Object>> routes =
                (List<Map<String, Object>>) service.capabilities().get("routes");
        Map<String, Object> mvc = routes.stream()
                .filter(route -> "spring-framework-5.3-mvc-maven-to-boot-3.5.3-java-21"
                        .equals(route.get("routeId")))
                .findFirst().orElseThrow();

        assertEquals("exact:5.3.39", mvc.get("sourceConstraint"));
        assertEquals("EXACT", mvc.get("sourceVersionMatch"));
        assertEquals("5.3.39", mvc.get("exactSourceVersion"));
        assertEquals("EXPERIMENTAL", mvc.get("launchStatus"));
        Map<String, Object> launch = routes.stream()
                .filter(route -> SpringRouteCatalog.LAUNCH_ROUTE_ID.equals(route.get("routeId")))
                .findFirst().orElseThrow();
        assertEquals("DESIGN_PARTNER", launch.get("launchStatus"));
        assertEquals(false, service.capabilities().get("operatorExperimentalRoutesEnabled"));
    }

    private SpringUpgradeRunService service(
            SpringUpgradeExecutionPort transformer,
            SpringUpgradeIndependentValidationPort verifier
    ) {
        return service(transformer, verifier, Clock.systemUTC());
    }

    private SpringUpgradeRunService service(
            SpringUpgradeExecutionPort transformer,
            SpringUpgradeIndependentValidationPort verifier,
            Clock clock
    ) {
        return new SpringUpgradeRunService(
                transformer,
                verifier,
                workspace,
                new ObjectMapper().findAndRegisterModules(),
                clock
        );
    }

    /** Readable by the run's virtual threads, so the instant must be volatile. */
    private static final class MovableClock extends Clock {
        private volatile Instant current;
        private MovableClock(Instant current) { this.current = current; }
        void advance(Duration amount) { current = current.plus(amount); }
        @Override public ZoneId getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(ZoneId zone) { return this; }
        @Override public Instant instant() { return current; }
    }

    @Test void terminalRunsAndTheirIdempotencyKeysAgeOutTogether() throws Exception {
        MovableClock clock = new MovableClock(Instant.parse("2026-07-29T00:00:00Z"));
        service = service(new SuccessfulTransformer(), new PassingVerifier(), clock);
        StartRequest request = request("aged-key");
        RunView first = service.create("org-a", request);
        awaitTerminal(first.runId(), "org-a");

        // Inside the window nothing is dropped and the key still replays the run.
        clock.advance(Duration.ofHours(23));
        service.evictAgedTerminalRuns();
        assertEquals(first.runId(), service.create("org-a", request).runId());

        // Past it the run and its key go together, so the replay starts a new run
        // instead of failing to find the one the key points at.
        clock.advance(Duration.ofHours(2));
        service.evictAgedTerminalRuns();
        assertThrows(SpringUpgradeRunService.NotFound.class,
                () -> service.get("org-a", first.runId()));
        assertNotEquals(first.runId(), service.create("org-a", request).runId());
    }

    private RunView awaitTerminal(String runId, String organizationId) {
        long deadline = System.nanoTime() + ASYNC_STATE_TIMEOUT.toNanos();
        RunView current;
        do {
            current = service.get(organizationId, runId);
            if (List.of(RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.BLOCKED, RunStatus.CANCELLED)
                    .contains(current.status())) return current;
            try {
                Thread.sleep(10);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                fail("test interrupted");
            }
        } while (System.nanoTime() < deadline);
        return fail("run did not reach a terminal state");
    }

    private RunView awaitRuntime(String runId, RuntimeStatus expected) {
        long deadline = System.nanoTime() + ASYNC_STATE_TIMEOUT.toNanos();
        do {
            RunView current = service.get("org-a", runId);
            if (current.runtimeStatus() == expected) return current;
            try {
                Thread.sleep(10);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                fail("test interrupted");
            }
        } while (System.nanoTime() < deadline);
        return fail("runtime did not reach " + expected);
    }

    private static StartRequest request(String key) {
        return request(key, false);
    }

    private static StartRequest request(String key, boolean startAfterVerification) {
        return new StartRequest(
                "org-a",
                SourceMode.PUBLIC_GIT,
                "https://github.com/example/legacy.git",
                "main",
                null,
                null,
                null,
                startAfterVerification,
                key
        );
    }

    private static class SuccessfulTransformer implements SpringUpgradeExecutionPort {
        @Override public ExecutionResult execute(StartRequest request, Path runRoot, Control control) {
            try {
                assertEquals("execution", runRoot.getFileName().toString());
                control.stage(Stage.IMPORT_GIT, "import");
                control.stage(Stage.LOCK_SNAPSHOT, "snapshot");
                control.stage(Stage.FINGERPRINT, "fingerprint");
                control.stage(Stage.EXTRACT_FCM, "fcm");
                control.stage(Stage.OPENREWRITE, "rewrite");
                control.stage(Stage.BUILD_AND_TEST, "test");
                control.stage(Stage.PACKAGE_ARTIFACT, "artifact");
                Path migrated = runRoot.resolve("migrated");
                Path artifact = runRoot.resolve("artifacts/project.zip");
                Files.createDirectories(migrated);
                Files.createDirectories(artifact.getParent());
                Path fcm = runRoot.resolve("evidence/framework-contract-model.json");
                Files.createDirectories(fcm.getParent());
                Files.writeString(fcm, """
                        {
                          "schema_version": "1.0",
                          "pack_key": "spring-boot-2-7-18-to-3-5-3",
                          "route_id": "boot-2.7-maven-to-boot-3.5.3-java-21",
                          "route_evidence": "PASSED_LOCAL",
                          "source_commit": "%s",
                          "source_snapshot_sha256": "%s",
                          "extraction_status": "STATIC_AND_SOURCE_BASELINE",
                          "exact_tuple": {
                            "sourceSpringBoot": "2.7.18",
                            "sourceJava": "17",
                            "sourceBuildTool": "maven-3.9.11",
                            "targetSpringBoot": "3.5.3",
                            "targetJava": "21",
                            "targetBuildTool": "maven-3.9.11",
                            "rewriteSpring": "6.35.0",
                            "rewriteMavenPlugin": "6.44.0"
                          },
                          "capabilities": [],
                          "unknowns": []
                        }
                        """.formatted("a".repeat(40), "b".repeat(64)));
                byte[] candidate = "verified candidate".getBytes(StandardCharsets.UTF_8);
                Files.write(artifact, candidate);
                return new ExecutionResult(
                        "a".repeat(40),
                        "snapshot-1",
                        "b".repeat(64),
                        new Fingerprint(SOURCE_BOOT, SOURCE_JAVA, "maven",
                                List.of(), List.of("web"), List.of(), java.util.Map.of("web", List.of("pom.xml"))),
                        "evidence/framework-contract-model.json",
                        migrated,
                        artifact,
                        HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(candidate)),
                        Files.size(artifact),
                        List.of("/actuator/health")
                );
            } catch (Exception error) {
                throw new RuntimeException(error);
            }
        }

        @Override public RuntimeHandle start(
                ExecutionResult result,
                StartRequest request,
                Path runRoot,
                Control control
        ) {
            throw new AssertionError("runtime must not start in this test");
        }

        @Override public void stop(RuntimeHandle handle, Control control) {}
        @Override public boolean configured() { return true; }
        @Override public String configurationReason() { return "test"; }
    }

    private static class MvcTransformer extends SuccessfulTransformer {
        private final boolean aliasesFrameworkAsBoot;

        MvcTransformer() {
            this(false);
        }

        MvcTransformer(boolean aliasesFrameworkAsBoot) {
            this.aliasesFrameworkAsBoot = aliasesFrameworkAsBoot;
        }

        @Override public ExecutionResult execute(StartRequest request, Path runRoot, Control control) {
            ExecutionResult boot = super.execute(request, runRoot, control);
            try {
                Files.writeString(runRoot.resolve("evidence/framework-contract-model.json"), """
                        {
                          "schema_version": "1.0",
                          "pack_key": "spring-framework-5-3-mvc-to-spring-boot-3-5-3",
                          "route_id": "spring-framework-5.3-mvc-maven-to-boot-3.5.3-java-21",
                          "route_evidence": "NOT_RUN",
                          "source_commit": "%s",
                          "source_snapshot_sha256": "%s",
                          "extraction_status": "STATIC_AND_SOURCE_BASELINE",
                          "source_framework": {"family": "spring-mvc", "version": "5.3.39"},
                          "exact_tuple": {
                            "sourceSpringBoot": %s,
                            "sourceFrameworkFamily": "spring-mvc",
                            "sourceFrameworkVersion": "5.3.39",
                            "sourceJava": "11",
                            "sourceBuildTool": "maven-3.9.11",
                            "targetSpringBoot": "3.5.3",
                            "targetJava": "21",
                            "targetBuildTool": "maven-3.9.11",
                            "rewriteSpring": "6.35.0",
                            "rewriteMavenPlugin": "6.44.0"
                          },
                          "capabilities": [],
                          "unknowns": []
                        }
                        """.formatted(
                        boot.resolvedCommitSha(), boot.snapshotDigest(),
                        aliasesFrameworkAsBoot ? "\"5.3.39\"" : "null"));
                Fingerprint mvc = new Fingerprint(
                        "UNKNOWN", "11", "maven", List.of(), List.of("spring-mvc"), List.of(),
                        java.util.Map.of("spring-mvc", List.of("Controller.java")),
                        "spring-mvc", "5.3.39");
                return new ExecutionResult(
                        boot.resolvedCommitSha(), boot.snapshotId(), boot.snapshotDigest(), mvc,
                        boot.fcmArtifact(), boot.migratedRepository(), boot.downloadArtifact(),
                        boot.artifactSha256(), boot.artifactSize(), boot.healthCandidates());
            } catch (Exception error) {
                throw new RuntimeException(error);
            }
        }
    }

    private static final class PassingVerifier implements SpringUpgradeIndependentValidationPort {
        @Override public IndependentValidationResult validate(
                ExecutionResult result,
                Path runRoot,
                SpringUpgradeExecutionPort.Control control
        ) {
            control.stage(Stage.INDEPENDENT_VALIDATION, "independent verify");
            return new IndependentValidationResult(
                    "PASS",
                    "independent-test-verifier",
                    result.artifactSha256(),
                    "evidence/independent-validation.json",
                    java.time.Instant.now()
            );
        }

        @Override public boolean configured() { return true; }
        @Override public String configurationReason() { return "test"; }
    }

    private static final class LifecycleTransformer extends SuccessfulTransformer {
        private final AtomicBoolean stopped = new AtomicBoolean();

        @Override public RuntimeHandle start(
                ExecutionResult result,
                StartRequest request,
                Path runRoot,
                Control control
        ) {
            control.stage(Stage.START_APPLICATION, "runtime start");
            control.stage(Stage.HEALTH_CHECK, "runtime health");
            control.log("runtime healthy");
            try {
                Thread.sleep(50);
                Process process = new ProcessBuilder(
                        Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                        "-version"
                ).start();
                return new RuntimeHandle(process, null, request.organizationId(), 18081, "/actuator/health");
            } catch (Exception error) {
                throw new RuntimeException(error);
            }
        }

        @Override public void stop(RuntimeHandle handle, Control control) {
            stopped.set(true);
            control.stage(Stage.STOP_APPLICATION, "runtime stop");
        }

        @Override public boolean runtimeConfigured() { return true; }
        @Override public String runtimeConfigurationReason() { return "test runtime"; }
    }

    private static final class RemoteLifecycleTransformer extends SuccessfulTransformer {
        private final boolean blockUntilInterrupted;
        private final AtomicInteger stopCalls = new AtomicInteger();
        private final AtomicBoolean failNextStop = new AtomicBoolean();
        private final CountDownLatch startEntered = new CountDownLatch(1);
        private final CountDownLatch stopped = new CountDownLatch(1);

        private RemoteLifecycleTransformer(boolean blockUntilInterrupted) {
            this.blockUntilInterrupted = blockUntilInterrupted;
        }

        @Override public RuntimeHandle start(
                ExecutionResult result,
                StartRequest request,
                Path runRoot,
                Control control
        ) {
            startEntered.countDown();
            if (blockUntilInterrupted) {
                try {
                    new CountDownLatch(1).await();
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                }
            }
            return new RuntimeHandle(
                    null,
                    runRoot.getFileName().toString(),
                    request.organizationId(),
                    8080,
                    "/actuator/health");
        }

        @Override public void stop(RuntimeHandle handle, Control control) {
            stopCalls.incrementAndGet();
            if (failNextStop.compareAndSet(true, false)) {
                throw new BlockedException(
                        "ISOLATED_RUNTIME_STOP_FAILED",
                        "remote runtime stop outcome is unknown");
            }
            stopped.countDown();
        }

        @Override public boolean runtimeConfigured() { return true; }
        @Override public String runtimeConfigurationReason() { return "remote test runtime"; }
    }
}
