package io.elmos.workspaceservice;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.api.exception.NotFoundException;
import com.github.dockerjava.api.model.Bind;
import com.github.dockerjava.api.model.Capability;
import com.github.dockerjava.api.model.HostConfig;
import com.github.dockerjava.api.model.Volume;
import io.elmos.workspace.WorkspaceInfrastructurePorts;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import static io.elmos.workspaceservice.SpringRuntimeModels.Rejected;

/**
 * Owns per-run rootless transformation containers. Long-lived Worker credentials and the Docker
 * socket stay in the broker; repository code sees only a one-time child credential and its run.
 */
final class EphemeralSpringTransformerBroker {
    private static final int MAX_REQUEST_BYTES = 128 * 1024;
    private final DockerClient docker;
    private final WorkspaceInfrastructurePorts.ApprovedImageRegistry images;
    private final String transformerImageDigest;
    private final String internalNetworkName;
    private final String egressProxyUrl;
    private final String egressProxyHost;
    private final int egressProxyPort;
    private final String allowedGitHosts;
    private final Path serviceRunRoot;
    private final Path hostRunRoot;
    private final SpringRuntimeAuthentication authentication;
    private final ObjectMapper json;
    private final Clock clock;
    private final HttpClient client;
    private final SecureRandom random = new SecureRandom();
    private final ConcurrentMap<String, String> active = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, Long> cancelled = new ConcurrentHashMap<>();

    EphemeralSpringTransformerBroker(
            DockerClient docker,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            String transformerImageDigest,
            String internalNetworkName,
            String egressProxyUrl,
            String allowedGitHosts,
            Path serviceRunRoot,
            Path hostRunRoot,
            SpringRuntimeAuthentication authentication,
            ObjectMapper json,
            Clock clock
    ) {
        this.docker = Objects.requireNonNull(docker);
        this.images = Objects.requireNonNull(images);
        if (transformerImageDigest == null
                || !transformerImageDigest.matches("sha256:[0-9a-f]{64}")) {
            throw new IllegalArgumentException("approved transformer image digest is required");
        }
        if (internalNetworkName == null
                || !internalNetworkName.matches("[A-Za-z0-9._-]{3,128}")) {
            throw new IllegalArgumentException("transformer internal network name is invalid");
        }
        URI proxy = URI.create(egressProxyUrl);
        if (!"http".equals(proxy.getScheme())
                || proxy.getHost() == null
                || proxy.getUserInfo() != null
                || proxy.getQuery() != null
                || proxy.getFragment() != null
                || !(proxy.getPath() == null || proxy.getPath().isEmpty()
                || "/".equals(proxy.getPath()))
                || proxy.getPort() < 1
                || proxy.getPort() > 65535) {
            throw new IllegalArgumentException("transformer egress proxy URL is invalid");
        }
        if (allowedGitHosts == null
                || !allowedGitHosts.matches("[A-Za-z0-9.,_-]{3,512}")) {
            throw new IllegalArgumentException("transformer Git host policy is invalid");
        }
        this.transformerImageDigest = transformerImageDigest;
        this.internalNetworkName = internalNetworkName;
        this.egressProxyUrl = egressProxyUrl;
        this.egressProxyHost = proxy.getHost();
        this.egressProxyPort = proxy.getPort();
        this.allowedGitHosts = allowedGitHosts;
        this.serviceRunRoot = serviceRunRoot.toAbsolutePath().normalize();
        this.hostRunRoot = hostRunRoot.toAbsolutePath().normalize();
        this.authentication = Objects.requireNonNull(authentication);
        this.json = Objects.requireNonNull(json);
        this.clock = Objects.requireNonNull(clock);
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    BrokerResponse handle(String timestamp, String nonce, String signature, byte[] body) {
        authentication.verify(timestamp, nonce, signature, body);
        Envelope envelope = parse(body);
        pruneCancelled();
        if ("CANCEL".equals(envelope.action())) return cancel(envelope.runId());
        if (!"TRANSFORM".equals(envelope.action())) {
            throw rejected("TRANSFORM_REQUEST_REJECTED", "Transformation action is unsupported.");
        }
        if (cancelled.remove(envelope.runId()) != null) {
            throw rejected("TRANSFORMATION_CANCELLED",
                    "Transformation was cancelled before its container started.");
        }
        Path serviceRun = runPath(serviceRunRoot, envelope.runId(), true);
        Path hostRun = runPath(hostRunRoot, envelope.runId(), false);
        Path hostMaterialized = null;
        byte[] childBody = body;
        if ("MATERIALIZED_SNAPSHOT".equals(envelope.sourceMode())) {
            if (envelope.materializedRelativePath() == null
                    || envelope.snapshotId() == null
                    || envelope.expectedCommitSha() == null) {
                throw rejected("MATERIALIZED_SNAPSHOT_IDENTITY_REQUIRED",
                        "Materialized Snapshot ID, path and exact Commit are required.");
            }
            Path serviceMaterialized = materializedPath(
                    serviceRunRoot,
                    envelope.materializedRelativePath()
            );
            hostMaterialized = materializedPath(
                    hostRunRoot,
                    envelope.materializedRelativePath(),
                    false
            );
            childBody = materializedChildBody(body);
            if (serviceMaterialized.startsWith(serviceRun)) {
                throw rejected("MATERIALIZED_SNAPSHOT_PATH_REJECTED",
                        "Source Snapshot cannot be stored inside its output Run.");
            }
        }
        requireRootless();
        images.requireApproved(
                "spring-transformer-java8-java11-java17-java21-maven",
                transformerImageDigest);

        byte[] oneTimeSecret = new byte[48];
        random.nextBytes(oneTimeSecret);
        String secretValue = Base64.getUrlEncoder().withoutPadding().encodeToString(oneTimeSecret);
        java.util.Arrays.fill(oneTimeSecret, (byte) 0);
        String containerName = "elmos-spring-transformer-" + envelope.runId().replace("-", "");
        String container = null;
        try {
            java.util.ArrayList<Bind> binds = new java.util.ArrayList<>();
            binds.add(new Bind(
                    hostRun.toString(),
                    new Volume("/workspace/run"),
                    com.github.dockerjava.api.model.AccessMode.rw
            ));
            if (hostMaterialized != null) {
                binds.add(new Bind(
                        hostMaterialized.toString(),
                        new Volume("/workspace/materialized-source"),
                        com.github.dockerjava.api.model.AccessMode.ro
                ));
            }
            HostConfig host = HostConfig.newHostConfig()
                    .withPrivileged(false)
                    .withReadonlyRootfs(true)
                    .withCapDrop(Capability.ALL)
                    .withSecurityOpts(List.of("no-new-privileges:true"))
                    .withMemory(6L * 1024 * 1024 * 1024)
                    .withMemorySwap(6L * 1024 * 1024 * 1024)
                    .withNanoCPUs(4_000_000_000L)
                    .withPidsLimit(768L)
                    .withNetworkMode(internalNetworkName)
                    .withIpcMode("private")
                    .withTmpFs(Map.of(
                            "/tmp", "rw,noexec,nosuid,size=512m,uid=10001,gid=10001",
                            "/home/elmos/.m2", "rw,noexec,nosuid,size=1536m,uid=10001,gid=10001"
                    ))
                    .withBinds(binds);
            container = docker.createContainerCmd(transformerImageDigest)
                    .withName(containerName)
                    .withUser("10001:10001")
                    .withEnv(
                            "ELMOS_TRANSFORMER_HMAC_SECRET_VALUE=" + secretValue,
                            "ELMOS_ALLOWED_GIT_HOSTS=" + allowedGitHosts,
                            "HTTPS_PROXY=" + egressProxyUrl,
                            "https_proxy=" + egressProxyUrl,
                            "HTTP_PROXY=" + egressProxyUrl,
                            "http_proxy=" + egressProxyUrl,
                            "JAVA_TOOL_OPTIONS=-Dhttp.proxyHost=" + egressProxyHost
                                    + " -Dhttp.proxyPort=" + egressProxyPort
                                    + " -Dhttps.proxyHost=" + egressProxyHost
                                    + " -Dhttps.proxyPort=" + egressProxyPort
                                    + " -Dhttp.nonProxyHosts=localhost|127.*|[::1]"
                                    + " -Dhttps.nonProxyHosts=localhost|127.*|[::1]",
                            "NO_PROXY=127.0.0.1,localhost",
                            "no_proxy=127.0.0.1,localhost"
                    )
                    .withHostConfig(host)
                    .withLabels(Map.of(
                            "elmos.managed", "true",
                            "elmos.resource_role", "spring-transformer",
                            "elmos.run_id", envelope.runId(),
                            "elmos.retention", "ephemeral"
                    ))
                    .exec()
                    .getId();
            if (active.putIfAbsent(envelope.runId(), container) != null) {
                throw rejected("TRANSFORM_RUN_ALREADY_ACTIVE",
                        "A transformation container already owns this run.");
            }
            docker.startContainerCmd(container).exec();
            waitForTransformer(containerName);
            byte[] responseBody = callTransformer(containerName, childBody, secretValue);
            return new BrokerResponse(200, responseBody);
        } finally {
            if (container != null) active.remove(envelope.runId(), container);
            if (container != null) remove(container);
        }
    }

    private BrokerResponse cancel(String runId) {
        cancelled.put(runId, clock.instant().getEpochSecond());
        String container = active.remove(runId);
        if (container != null) remove(container);
        try {
            return new BrokerResponse(200, json.writeValueAsBytes(Map.of(
                    "status", "CANCELLED",
                    "runId", runId
            )));
        } catch (IOException error) {
            throw new IllegalStateException("cancellation receipt could not be encoded", error);
        }
    }

    private byte[] callTransformer(String containerName, byte[] body, String secret) {
        String timestamp = Long.toString(clock.instant().getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        byte[] secretBytes = secret.getBytes(StandardCharsets.UTF_8);
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://" + containerName + ":8083/internal/v1/spring-transformations"))
                .timeout(Duration.ofMinutes(95))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .header("X-ELMOS-Transformer-Timestamp", timestamp)
                .header("X-ELMOS-Transformer-Nonce", nonce)
                .header("X-ELMOS-Transformer-Signature",
                        SpringRuntimeAuthentication.sign(secretBytes, timestamp, nonce, body))
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        try {
            HttpResponse<byte[]> response =
                    client.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.body().length > 512 * 1024) {
                throw rejected("EPHEMERAL_TRANSFORMER_PROTOCOL_ERROR",
                        "Ephemeral transformer response exceeded policy.");
            }
            if (response.statusCode() != 200) {
                throw transformerFailure(response.body());
            }
            validateSuccess(response.body());
            return response.body();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw rejected("TRANSFORMATION_CANCELLED",
                    "Ephemeral transformation was interrupted.");
        } catch (IOException error) {
            throw rejected("EPHEMERAL_TRANSFORMER_UNAVAILABLE",
                    "Ephemeral transformer is unavailable.");
        }
    }

    private void validateSuccess(byte[] body) {
        try {
            JsonNode value = json.readTree(body);
            if (!"SUCCEEDED".equals(value.path("status").asText())
                    || !value.path("artifactSha256").asText().matches("[0-9a-f]{64}")
                    || value.path("artifactSize").asLong() <= 0) {
                throw rejected("EPHEMERAL_TRANSFORMER_PROTOCOL_ERROR",
                        "Ephemeral transformer returned an invalid success receipt.");
            }
        } catch (IOException error) {
            throw rejected("EPHEMERAL_TRANSFORMER_PROTOCOL_ERROR",
                    "Ephemeral transformer returned invalid JSON.");
        }
    }

    private void waitForTransformer(String containerName) {
        long deadline = System.nanoTime() + Duration.ofSeconds(60).toNanos();
        URI health = URI.create("http://" + containerName + ":8083/actuator/health/readiness");
        while (System.nanoTime() < deadline) {
            try {
                HttpResponse<Void> response = client.send(
                        HttpRequest.newBuilder(health).timeout(Duration.ofSeconds(2)).GET().build(),
                        HttpResponse.BodyHandlers.discarding()
                );
                if (response.statusCode() == 200) return;
            } catch (IOException ignored) {
                // Retry inside the bounded startup window.
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw rejected("TRANSFORMATION_CANCELLED",
                        "Ephemeral transformer startup was interrupted.");
            }
            try {
                Thread.sleep(250);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw rejected("TRANSFORMATION_CANCELLED",
                        "Ephemeral transformer startup was interrupted.");
            }
        }
        throw rejected("EPHEMERAL_TRANSFORMER_START_TIMEOUT",
                "Ephemeral transformer did not become ready.");
    }

    private Envelope parse(byte[] body) {
        if (body.length == 0 || body.length > MAX_REQUEST_BYTES) {
            throw rejected("TRANSFORM_REQUEST_REJECTED", "Transformation request is invalid.");
        }
        try {
            JsonNode value = json.readTree(body);
            String action = value.path("action").asText();
            String runId = value.path("runId").asText();
            if (!List.of("TRANSFORM", "CANCEL").contains(action)
                    || !runId.matches("[0-9a-fA-F-]{36}")) {
                throw rejected("TRANSFORM_REQUEST_REJECTED", "Transformation request is invalid.");
            }
            UUID.fromString(runId);
            String sourceMode = value.path("request").path("sourceMode").asText();
            if ("TRANSFORM".equals(action)
                    && !List.of("PUBLIC_GIT", "MATERIALIZED_SNAPSHOT").contains(sourceMode)) {
                throw rejected("TRANSFORM_REQUEST_REJECTED",
                        "Transformation source mode is invalid.");
            }
            String materializedRelativePath = value.path("request")
                    .path("materializedRelativePath").asText(null);
            String snapshotId = value.path("request").path("snapshotId").asText(null);
            String expectedCommitSha = value.path("request")
                    .path("expectedCommitSha").asText(null);
            if ("MATERIALIZED_SNAPSHOT".equals(sourceMode)
                    && (materializedRelativePath == null
                    || materializedRelativePath.isBlank()
                    || snapshotId == null
                    || !snapshotId.matches("[A-Za-z0-9._-]{3,160}")
                    || expectedCommitSha == null
                    || !expectedCommitSha.matches("[0-9a-f]{40}"))) {
                throw rejected("MATERIALIZED_SNAPSHOT_IDENTITY_REQUIRED",
                        "Materialized Snapshot identity is invalid.");
            }
            return new Envelope(
                    action,
                    runId,
                    sourceMode,
                    materializedRelativePath,
                    snapshotId,
                    expectedCommitSha
            );
        } catch (Rejected error) {
            throw error;
        } catch (IOException | IllegalArgumentException error) {
            throw rejected("TRANSFORM_REQUEST_REJECTED", "Transformation request is invalid.");
        }
    }

    private byte[] materializedChildBody(byte[] original) {
        try {
            JsonNode value = json.readTree(original);
            if (!(value instanceof com.fasterxml.jackson.databind.node.ObjectNode root)
                    || !(root.path("request")
                    instanceof com.fasterxml.jackson.databind.node.ObjectNode request)) {
                throw rejected("TRANSFORM_REQUEST_REJECTED",
                        "Materialized transformation request is invalid.");
            }
            request.put("materializedRelativePath", "materialized-source");
            return json.writeValueAsBytes(root);
        } catch (Rejected error) {
            throw error;
        } catch (IOException error) {
            throw rejected("TRANSFORM_REQUEST_REJECTED",
                    "Materialized transformation request is invalid.");
        }
    }

    private static Path materializedPath(Path root, String relativeValue) {
        return materializedPath(root, relativeValue, true);
    }

    private static Path materializedPath(
            Path root,
            String relativeValue,
            boolean mustExist
    ) {
        try {
            Path relative = Path.of(relativeValue);
            Path value = root.resolve(relative).normalize();
            if (relative.isAbsolute()
                    || relative.normalize().startsWith("..")
                    || !value.startsWith(root)
                    || value.equals(root)
                    || (mustExist && (!Files.isDirectory(value, LinkOption.NOFOLLOW_LINKS)
                    || Files.isSymbolicLink(value)))) {
                throw rejected("MATERIALIZED_SNAPSHOT_PATH_REJECTED",
                        "Materialized Snapshot path is unavailable or outside policy.");
            }
            return value;
        } catch (java.nio.file.InvalidPathException error) {
            throw rejected("MATERIALIZED_SNAPSHOT_PATH_REJECTED",
                    "Materialized Snapshot path is invalid.");
        }
    }

    private Path runPath(Path root, String runId, boolean mustExist) {
        Path value = root.resolve("spring-upgrades").resolve(runId).resolve("execution").normalize();
        if (!value.startsWith(root) || value.equals(root)) {
            throw rejected("TRANSFORM_RUN_PATH_REJECTED",
                    "Transformation run path escaped its root.");
        }
        if (mustExist && (!Files.isDirectory(value, LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(value))) {
            throw rejected("TRANSFORM_RUN_PATH_REJECTED",
                    "Transformation run path is unavailable.");
        }
        return value;
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

    private void remove(String container) {
        try {
            docker.stopContainerCmd(container).withTimeout(10).exec();
        } catch (NotFoundException ignored) {
            return;
        } catch (RuntimeException ignored) {
            // Force removal below.
        }
        try {
            docker.removeContainerCmd(container).withForce(true).exec();
        } catch (NotFoundException ignored) {
            // Idempotent cleanup.
        }
    }

    private void pruneCancelled() {
        long cutoff = clock.instant().minus(Duration.ofHours(2)).getEpochSecond();
        cancelled.entrySet().removeIf(entry -> entry.getValue() < cutoff);
    }

    private Rejected transformerFailure(byte[] body) {
        try {
            JsonNode value = json.readTree(body);
            String code = value.path("code").asText("TRANSFORMATION_FAILED");
            String message = value.path("message").asText("Ephemeral transformation failed.");
            if (!code.matches("[A-Z0-9_]{3,80}")) code = "TRANSFORMATION_FAILED";
            if (message.length() > 500) message = "Ephemeral transformation failed.";
            return rejected(code, message);
        } catch (IOException error) {
            return rejected("TRANSFORMATION_FAILED",
                    "Ephemeral transformation failed without a valid receipt.");
        }
    }

    private static Rejected rejected(String code, String message) {
        return new Rejected(code, message);
    }

    record BrokerResponse(int status, byte[] body) {}
    private record Envelope(
            String action,
            String runId,
            String sourceMode,
            String materializedRelativePath,
            String snapshotId,
            String expectedCommitSha
    ) {}
}
