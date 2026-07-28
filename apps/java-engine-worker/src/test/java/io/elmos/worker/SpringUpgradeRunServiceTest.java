package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.HexFormat;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import static io.elmos.worker.SpringUpgradeModels.*;
import static org.junit.jupiter.api.Assertions.*;

class SpringUpgradeRunServiceTest {
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

    @Test void conflictingIdempotencyInputAndNonTerminalRetryAreRejected() {
        SpringUpgradeExecutionPort delayed = new SuccessfulTransformer() {
            @Override public ExecutionResult execute(StartRequest request, Path runRoot, Control control) {
                try {
                    Thread.sleep(250);
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                }
                return super.execute(request, runRoot, control);
            }
        };
        service = service(delayed, new PassingVerifier());
        RunView first = service.create("org-a", request("conflict-key"));
        StartRequest changed = new StartRequest("org-a", SourceMode.PUBLIC_GIT,
                "https://github.com/example/other.git", "main", null, null, null,
                false, "conflict-key");
        assertThrows(SpringUpgradeRunService.IdempotencyConflict.class,
                () -> service.create("org-a", changed));
        assertThrows(SpringUpgradeRunService.Conflict.class,
                () -> service.retry("org-a", first.runId(), "retry-key"));
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

    @Test void completedRunAndIdempotencyRecoverAfterWorkerRestartAndTamperingFailsClosed() throws Exception {
        StartRequest request = request("durable-key");
        service = service(new SuccessfulTransformer(), new PassingVerifier());
        RunView completed = awaitTerminal(service.create("org-a", request).runId(), "org-a");
        Path artifact = service.artifact("org-a", completed.runId());
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

    private SpringUpgradeRunService service(
            SpringUpgradeExecutionPort transformer,
            SpringUpgradeIndependentValidationPort verifier
    ) {
        return new SpringUpgradeRunService(
                transformer,
                verifier,
                workspace,
                new ObjectMapper().findAndRegisterModules(),
                Clock.systemUTC()
        );
    }

    private RunView awaitTerminal(String runId, String organizationId) {
        long deadline = System.nanoTime() + java.time.Duration.ofSeconds(3).toNanos();
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
        long deadline = System.nanoTime() + java.time.Duration.ofSeconds(3).toNanos();
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
        return new StartRequest(
                "org-a",
                SourceMode.PUBLIC_GIT,
                "https://github.com/example/legacy.git",
                "main",
                null,
                null,
                null,
                false,
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
}
