package io.elmos.workspaceservice;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.api.exception.NotFoundException;
import com.github.dockerjava.api.model.*;
import com.github.dockerjava.core.command.ExecStartResultCallback;
import com.github.dockerjava.core.command.LogContainerResultCallback;
import io.elmos.workspace.WorkspaceInfrastructurePorts;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;

import static io.elmos.workspaceservice.SpringRuntimeModels.*;

final class RootlessSpringRuntimeService {
    private static final int PORT = 8080;
    private static final int MAX_LOG_BYTES = 4 * 1024 * 1024;
    private static final List<String> DEFAULT_HEALTH = List.of("/actuator/health", "/health");

    private final DockerClient docker;
    private final WorkspaceInfrastructurePorts.ApprovedImageRegistry images;
    private final String imageDigest;
    private final Path serviceArtifactRoot;
    private final Path hostArtifactRoot;
    private final SpringRuntimeAuthentication authentication;
    private final ObjectMapper json;

    RootlessSpringRuntimeService(
            DockerClient docker,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            String imageDigest,
            Path serviceArtifactRoot,
            Path hostArtifactRoot,
            SpringRuntimeAuthentication authentication,
            ObjectMapper json
    ) {
        this.docker = Objects.requireNonNull(docker);
        this.images = Objects.requireNonNull(images);
        if (imageDigest == null || !imageDigest.matches("sha256:[0-9a-f]{64}")) {
            throw new IllegalArgumentException("approved Java runtime image digest is required");
        }
        this.imageDigest = imageDigest;
        this.serviceArtifactRoot = serviceArtifactRoot.toAbsolutePath().normalize();
        this.hostArtifactRoot = hostArtifactRoot.toAbsolutePath().normalize();
        this.authentication = Objects.requireNonNull(authentication);
        this.json = Objects.requireNonNull(json);
    }

    Response handle(String timestamp, String nonce, String signature, byte[] body) {
        authentication.verify(timestamp, nonce, signature, body);
        Request request = parse(body);
        validate(request);
        return switch (request.action()) {
            case START -> start(request);
            case STOP -> stop(request);
            case LOGS -> logs(request);
        };
    }

    private Response start(Request request) {
        requireRootless();
        String javaExecutable = runtimeJavaExecutable(request.targetJava());
        images.requireApproved("spring-runtime-java17-java21", imageDigest);
        Path serviceArtifact = artifact(serviceArtifactRoot, request.artifactRelativePath());
        Path hostArtifact = artifact(hostArtifactRoot, request.artifactRelativePath());
        if (!request.artifactSha256().equals(sha256(serviceArtifact))) {
            throw rejected("RUNTIME_ARTIFACT_DIGEST_MISMATCH",
                    "Runtime artifact bytes differ from the independently validated candidate.");
        }
        List<String> existing = containers(request.runtimeId(), request.organizationId());
        if (existing.size() > 1) {
            throw rejected("RUNTIME_IDENTITY_AMBIGUOUS",
                    "More than one managed runtime has the requested identity.");
        }
        if (existing.size() == 1) {
            String container = existing.getFirst();
            var inspect = docker.inspectContainerCmd(container).exec();
            if (Boolean.TRUE.equals(inspect.getState().getRunning())) {
                String health = waitForHealth(
                        container, healthCandidates(request), javaExecutable);
                return response("HEALTHY", request.runtimeId(), health, container);
            }
            remove(container);
        }

        Map<String, String> labels = Map.of(
                "elmos.managed", "true",
                "elmos.resource_role", "spring-runtime",
                "elmos.runtime_id", request.runtimeId(),
                "elmos.organization_id", request.organizationId(),
                "elmos.target_java", request.targetJava(),
                "elmos.retention", "ephemeral"
        );
        HostConfig host = HostConfig.newHostConfig()
                .withPrivileged(false)
                .withReadonlyRootfs(true)
                .withCapDrop(Capability.ALL)
                .withSecurityOpts(List.of("no-new-privileges:true"))
                .withMemory(1024L * 1024 * 1024)
                .withMemorySwap(1024L * 1024 * 1024)
                .withNanoCPUs(1_000_000_000L)
                .withPidsLimit(192L)
                .withNetworkMode("none")
                .withIpcMode("private")
                .withTmpFs(Map.of("/tmp", "rw,noexec,nosuid,size=128m"))
                .withBinds(new Bind(
                        hostArtifact.toString(),
                        new Volume("/app/application.jar"),
                        com.github.dockerjava.api.model.AccessMode.ro
                ));
        String name = "elmos-spring-runtime-" + sha256(request.runtimeId().getBytes()).substring(0, 20);
        String container = docker.createContainerCmd(imageDigest)
                .withName(name)
                .withUser("10003:10003")
                .withWorkingDir("/app")
                .withEntrypoint(javaExecutable)
                .withCmd("-XX:MaxRAMPercentage=70", "-Djava.awt.headless=true", "-Duser.timezone=UTC",
                        "-jar", "/app/application.jar")
                .withEnv("SERVER_PORT=" + PORT, "MANAGEMENT_SERVER_PORT=" + PORT)
                .withHostConfig(host)
                .withLabels(labels)
                .exec()
                .getId();
        try {
            docker.startContainerCmd(container).exec();
            String health = waitForHealth(
                    container, healthCandidates(request), javaExecutable);
            return response("HEALTHY", request.runtimeId(), health, container);
        } catch (RuntimeException error) {
            try {
                remove(container);
            } catch (RuntimeException cleanup) {
                error.addSuppressed(cleanup);
            }
            throw error;
        }
    }

    private Response stop(Request request) {
        List<String> containers = containers(request.runtimeId(), request.organizationId());
        if (containers.size() > 1) {
            throw rejected("RUNTIME_IDENTITY_AMBIGUOUS",
                    "More than one managed runtime has the requested identity.");
        }
        List<String> logs = containers.isEmpty() ? List.of() : collectLogs(containers.getFirst()).lines();
        if (!containers.isEmpty()) remove(containers.getFirst());
        return new Response("STOPPED", request.runtimeId(), imageDigest, PORT, null, logs, false);
    }

    private Response logs(Request request) {
        List<String> containers = containers(request.runtimeId(), request.organizationId());
        if (containers.size() != 1) {
            throw rejected("RUNTIME_UNAVAILABLE", "Managed runtime is not running.");
        }
        LogResult logs = collectLogs(containers.getFirst());
        var inspect = docker.inspectContainerCmd(containers.getFirst()).exec();
        String status = Boolean.TRUE.equals(inspect.getState().getRunning()) ? "HEALTHY" : "UNHEALTHY";
        return new Response(status, request.runtimeId(), imageDigest, PORT, null, logs.lines(), logs.truncated());
    }

    private String waitForHealth(
            String container,
            List<String> candidates,
            String javaExecutable
    ) {
        long deadline = System.nanoTime() + Duration.ofSeconds(75).toNanos();
        while (System.nanoTime() < deadline) {
            var inspect = docker.inspectContainerCmd(container).exec();
            if (!Boolean.TRUE.equals(inspect.getState().getRunning())) {
                throw rejected("APPLICATION_EXITED_BEFORE_HEALTHY",
                        "The application exited before becoming healthy.");
            }
            for (String path : candidates) {
                var exec = docker.execCreateCmd(container)
                        .withAttachStdout(true)
                        .withAttachStderr(true)
                        .withPrivileged(false)
                        .withCmd(
                                javaExecutable,
                                "-cp",
                                "/runner",
                                "io.elmos.runner.HealthProbe",
                                "http://127.0.0.1:" + PORT + path
                        )
                        .exec();
                try {
                    boolean done = docker.execStartCmd(exec.getId())
                            .exec(new ExecStartResultCallback(new ByteArrayOutputStream(), new ByteArrayOutputStream()))
                            .awaitCompletion(5, TimeUnit.SECONDS);
                    Long exit = done ? docker.inspectExecCmd(exec.getId()).exec().getExitCodeLong() : null;
                    if (exit != null && exit == 0L) return path;
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw rejected("HEALTH_CHECK_INTERRUPTED", "Runtime health check was interrupted.");
                }
            }
            try {
                Thread.sleep(500);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw rejected("HEALTH_CHECK_INTERRUPTED", "Runtime health check was interrupted.");
            }
        }
        throw rejected("APPLICATION_HEALTH_TIMEOUT",
                "The isolated application did not become healthy within 75 seconds.");
    }

    private Response response(String status, String runtimeId, String healthPath, String container) {
        LogResult logs = collectLogs(container);
        return new Response(status, runtimeId, imageDigest, PORT, healthPath, logs.lines(), logs.truncated());
    }

    private LogResult collectLogs(String container) {
        BoundedOutput output = new BoundedOutput(MAX_LOG_BYTES);
        try {
            docker.logContainerCmd(container)
                    .withStdOut(true)
                    .withStdErr(true)
                    .withTimestamps(true)
                    .withTail(2_000)
                    .exec(new LogContainerResultCallback() {
                        @Override
                        public void onNext(Frame item) {
                            output.write(item.getPayload());
                        }
                    })
                    .awaitCompletion(10, TimeUnit.SECONDS);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw rejected("RUNTIME_LOG_INTERRUPTED", "Runtime log collection was interrupted.");
        }
        String redacted = new String(output.bytes(), java.nio.charset.StandardCharsets.UTF_8)
                .replaceAll("(?i)(password|token|secret|authorization)([=: ]+)([^\\s]+)", "$1$2[REDACTED]");
        return new LogResult(redacted.lines().toList(), output.truncated());
    }

    private List<String> containers(String runtimeId, String organizationId) {
        return docker.listContainersCmd()
                .withShowAll(true)
                .withLabelFilter(Map.of(
                        "elmos.managed", "true",
                        "elmos.resource_role", "spring-runtime",
                        "elmos.runtime_id", runtimeId,
                        "elmos.organization_id", organizationId
                ))
                .exec()
                .stream()
                .map(com.github.dockerjava.api.model.Container::getId)
                .toList();
    }

    private void remove(String container) {
        try {
            docker.stopContainerCmd(container).withTimeout(15).exec();
        } catch (NotFoundException ignored) {
            return;
        } catch (RuntimeException ignored) {
            // Force removal below is the bounded cleanup fallback.
        }
        try {
            docker.removeContainerCmd(container).withForce(true).exec();
        } catch (NotFoundException ignored) {
            // Idempotent stop.
        }
    }

    private void requireRootless() {
        List<String> options = docker.infoCmd().exec().getSecurityOptions();
        if (options == null
                || options.stream().map(String::toLowerCase)
                .noneMatch(value -> value.contains("rootless"))) {
            throw rejected("ROOTLESS_DAEMON_REQUIRED",
                    "Docker daemon did not prove rootless mode.");
        }
    }

    private Request parse(byte[] body) {
        try {
            if (body.length == 0 || body.length > 64 * 1024) {
                throw rejected("RUNTIME_REQUEST_REJECTED", "Runtime Runner request is invalid.");
            }
            return json.readValue(body, Request.class);
        } catch (Rejected error) {
            throw error;
        } catch (IOException error) {
            throw rejected("RUNTIME_REQUEST_REJECTED", "Runtime Runner request is invalid.");
        }
    }

    private static void validate(Request request) {
        if (request == null
                || request.action() == null
                || request.runtimeId() == null
                || !request.runtimeId().matches("[0-9a-fA-F-]{36}")
                || request.organizationId() == null
                || !request.organizationId().matches("[A-Za-z0-9._:-]{1,128}")) {
            throw rejected("RUNTIME_REQUEST_REJECTED", "Runtime Runner identity fields are invalid.");
        }
        try {
            UUID.fromString(request.runtimeId());
        } catch (IllegalArgumentException error) {
            throw rejected("RUNTIME_REQUEST_REJECTED", "Runtime ID is invalid.");
        }
        if (request.action() == Action.START
                && (request.artifactRelativePath() == null
                || request.artifactSha256() == null
                || !request.artifactSha256().matches("[0-9a-f]{64}")
                || !("17".equals(request.targetJava()) || "21".equals(request.targetJava())))) {
            throw rejected("RUNTIME_REQUEST_REJECTED", "Runtime Artifact fields are invalid.");
        }
        for (String path : healthCandidates(request)) {
            if (!path.matches("/[A-Za-z0-9/_-]{1,128}") || path.contains("//")) {
                throw rejected("HEALTH_PATH_REJECTED", "Runtime health path is invalid.");
            }
        }
    }

    private static List<String> healthCandidates(Request request) {
        return request.healthCandidates().isEmpty() ? DEFAULT_HEALTH : request.healthCandidates();
    }

    private static String runtimeJavaExecutable(String targetJava) {
        return switch (Objects.toString(targetJava, "")) {
            case "17" -> "/opt/java/openjdk-17/bin/java";
            case "21" -> "/opt/java/openjdk/bin/java";
            default -> throw rejected(
                    "TARGET_JDK_NOT_PROVISIONED",
                    "Rootless Runtime does not provide the exact requested target JDK.");
        };
    }

    private static Path artifact(Path root, String relativeValue) {
        try {
            Path relative = Path.of(relativeValue);
            Path candidate = root.resolve(relative).normalize();
            if (relative.isAbsolute()
                    || relative.normalize().startsWith("..")
                    || !candidate.startsWith(root)) {
                throw rejected("RUNTIME_ARTIFACT_PATH_REJECTED",
                        "Runtime Artifact path escapes its approved root.");
            }
            if (root.equals(candidate)) {
                throw rejected("RUNTIME_ARTIFACT_PATH_REJECTED", "Runtime Artifact path is invalid.");
            }
            if (Files.exists(root) && (!Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS)
                    || Files.isSymbolicLink(candidate))) {
                throw rejected("RUNTIME_ARTIFACT_UNAVAILABLE", "Runtime Artifact is unavailable.");
            }
            return candidate;
        } catch (InvalidPathException error) {
            throw rejected("RUNTIME_ARTIFACT_PATH_REJECTED", "Runtime Artifact path is invalid.");
        }
    }

    private static String sha256(Path path) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (var input = Files.newInputStream(path)) {
                byte[] buffer = new byte[64 * 1024];
                int count;
                while ((count = input.read(buffer)) >= 0) digest.update(buffer, 0, count);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (Exception error) {
            throw rejected("RUNTIME_ARTIFACT_DIGEST_UNAVAILABLE",
                    "Runtime Artifact digest could not be calculated.");
        }
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static Rejected rejected(String code, String message) {
        return new Rejected(code, message);
    }

    private record LogResult(List<String> lines, boolean truncated) {}

    private static final class BoundedOutput {
        private final int limit;
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        private boolean truncated;
        private BoundedOutput(int limit) { this.limit = limit; }
        void write(byte[] value) {
            int accepted = Math.min(value.length, limit - bytes.size());
            if (accepted > 0) bytes.write(value, 0, accepted);
            if (accepted < value.length) truncated = true;
        }
        byte[] bytes() { return bytes.toByteArray(); }
        boolean truncated() { return truncated; }
    }
}
