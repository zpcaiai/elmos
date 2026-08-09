package io.elmos.worker;

import java.time.Instant;
import java.util.List;
import java.util.Map;

final class SpringUpgradeModels {
    private SpringUpgradeModels() {}

    /*
     * These constants describe the one route that carries recorded end-to-end
     * local execution evidence. Every other supported source line lives in
     * SpringRouteCatalog; nothing in the pipeline may assume the source tuple
     * equals the constants below.
     */
    static final String PACK_KEY = "spring-boot-2-7-18-to-3-5-3";
    static final String SOURCE_BOOT = "2.7.18";
    static final String SOURCE_JAVA = "17";
    static final String TARGET_BOOT = SpringRouteCatalog.TARGET_BOOT;
    static final String TARGET_JAVA = SpringRouteCatalog.TARGET_JAVA;
    static final String REWRITE_SPRING = SpringRouteCatalog.REWRITE_SPRING;
    static final String REWRITE_MAVEN_PLUGIN = SpringRouteCatalog.REWRITE_MAVEN_PLUGIN;

    enum SourceMode { PUBLIC_GIT, MATERIALIZED_SNAPSHOT }
    enum RunStatus { QUEUED, RUNNING, SUCCEEDED, FAILED, BLOCKED, CANCELLED }
    enum RuntimeStatus { NOT_STARTED, STARTING, HEALTHY, UNHEALTHY, STOPPED }
    enum Stage {
        IMPORT_GIT,
        LOCK_SNAPSHOT,
        FINGERPRINT,
        SOURCE_BASELINE,
        EXTRACT_FCM,
        OPENREWRITE,
        BUILD_AND_TEST,
        DETERMINISTIC_REPAIR,
        INDEPENDENT_VALIDATION,
        PACKAGE_ARTIFACT,
        READY,
        START_APPLICATION,
        HEALTH_CHECK,
        STOP_APPLICATION
    }

    record StartRequest(
            String organizationId,
            SourceMode sourceMode,
            String repositoryUrl,
            String requestedRef,
            String expectedCommitSha,
            String snapshotId,
            String materializedRelativePath,
            boolean startAfterVerification,
            String idempotencyKey,
            String targetSpringBoot,
            String targetJava
    ) {
        StartRequest {
            targetSpringBoot = targetSpringBoot == null || targetSpringBoot.isBlank()
                    ? TARGET_BOOT : targetSpringBoot.trim();
            targetJava = targetJava == null || targetJava.isBlank()
                    ? TARGET_JAVA : SpringRouteCatalog.normalizeJava(targetJava);
        }

        /** Keep durable runs and older API clients on the original 3.5.3 / Java 21 default. */
        StartRequest(
                String organizationId,
                SourceMode sourceMode,
                String repositoryUrl,
                String requestedRef,
                String expectedCommitSha,
                String snapshotId,
                String materializedRelativePath,
                boolean startAfterVerification,
                String idempotencyKey
        ) {
            this(organizationId, sourceMode, repositoryUrl, requestedRef, expectedCommitSha,
                    snapshotId, materializedRelativePath, startAfterVerification, idempotencyKey,
                    TARGET_BOOT, TARGET_JAVA);
        }
    }

    record ExactTuple(
            String sourceSpringBoot,
            String sourceJava,
            String sourceBuildTool,
            String targetSpringBoot,
            String targetJava,
            String targetBuildTool,
            String rewriteSpring,
            String rewriteMavenPlugin
    ) {
        static ExactTuple supported(String sourceBuildTool, String targetBuildTool) {
            return new ExactTuple(SOURCE_BOOT, SOURCE_JAVA, sourceBuildTool, TARGET_BOOT, TARGET_JAVA,
                    targetBuildTool, REWRITE_SPRING, REWRITE_MAVEN_PLUGIN);
        }
    }

    record Fingerprint(
            String springBootVersion,
            String javaVersion,
            String buildTool,
            List<String> modules,
            List<String> activeCapabilities,
            List<String> unknowns,
            Map<String, List<String>> sourceTraces,
            String sourceFrameworkFamily,
            String sourceFrameworkVersion
    ) {
        Fingerprint {
            modules = List.copyOf(modules);
            activeCapabilities = List.copyOf(activeCapabilities);
            unknowns = List.copyOf(unknowns);
            sourceTraces = Map.copyOf(sourceTraces);
            sourceFrameworkFamily = sourceFrameworkFamily == null || sourceFrameworkFamily.isBlank()
                    ? inferredFamily(springBootVersion) : sourceFrameworkFamily.trim();
            sourceFrameworkVersion = sourceFrameworkVersion == null || sourceFrameworkVersion.isBlank()
                    ? springBootVersion : sourceFrameworkVersion.trim();
        }

        Fingerprint(
                String springBootVersion,
                String javaVersion,
                String buildTool,
                List<String> modules,
                List<String> activeCapabilities,
                List<String> unknowns,
                Map<String, List<String>> sourceTraces
        ) {
            this(springBootVersion, javaVersion, buildTool, modules, activeCapabilities,
                    unknowns, sourceTraces, inferredFamily(springBootVersion), springBootVersion);
        }

        private static String inferredFamily(String springBootVersion) {
            return springBootVersion == null || springBootVersion.isBlank()
                    || "UNKNOWN".equalsIgnoreCase(springBootVersion)
                    ? "unknown" : "spring-boot";
        }
    }

    record Event(long sequence, Stage stage, String status, String message, Instant observedAt) {}

    record RunView(
            String runId,
            String retryOfRunId,
            String organizationId,
            String packKey,
            RunStatus status,
            Stage stage,
            RuntimeStatus runtimeStatus,
            int attempt,
            String repositoryUrl,
            String requestedRef,
            String resolvedCommitSha,
            String snapshotId,
            String snapshotDigest,
            ExactTuple exactTuple,
            Fingerprint fingerprint,
            String fcmArtifact,
            boolean downloadAvailable,
            String artifactSha256,
            Long artifactSize,
            String healthPath,
            Integer runtimePort,
            String failureCode,
            String failureMessage,
            IndependentValidationResult independentValidation,
            List<Event> events,
            Instant createdAt,
            Instant updatedAt
    ) {
        RunView {
            events = List.copyOf(events);
        }
    }

    record LogView(String runId, List<String> lines, boolean truncated) {
        LogView { lines = List.copyOf(lines); }
    }

    record ExecutionResult(
            String resolvedCommitSha,
            String snapshotId,
            String snapshotDigest,
            Fingerprint fingerprint,
            String fcmArtifact,
            java.nio.file.Path migratedRepository,
            java.nio.file.Path downloadArtifact,
            String artifactSha256,
            long artifactSize,
            List<String> healthCandidates
    ) {
        ExecutionResult { healthCandidates = List.copyOf(healthCandidates); }
    }

    record RuntimeHandle(
            Process process,
            String runtimeId,
            String organizationId,
            int port,
            String healthPath
    ) {}

    record IndependentValidationResult(
            String status,
            String verifierId,
            String artifactSha256,
            String evidencePath,
            Instant decidedAt
    ) {}

    static final class BlockedException extends RuntimeException {
        private final String code;
        BlockedException(String code, String message) { super(message); this.code = code; }
        String code() { return code; }
    }
}
