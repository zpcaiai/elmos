package io.elmos.workspaceservice;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.api.exception.NotFoundException;
import com.github.dockerjava.api.model.*;
import io.elmos.workspace.WorkspaceInfrastructurePorts;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.util.*;

import static io.elmos.workspaceservice.SpringRuntimeModels.Rejected;

/**
 * Rootless verifier broker. Each verification gets a short-lived container, an exact read-only
 * candidate mount, a run-scoped evidence mount and a one-time HMAC secret. Customer build code
 * never receives the long-lived Worker-to-broker credential or access to another run.
 */
final class EphemeralSpringVerifierBroker {
    private final DockerClient docker;
    private final WorkspaceInfrastructurePorts.ApprovedImageRegistry images;
    private final String verifierImageDigest;
    private final String verifierId;
    private final String internalNetworkName;
    private final String egressProxyUrl;
    private final Path serviceInputRoot;
    private final Path hostInputRoot;
    private final Path serviceEvidenceRoot;
    private final Path hostEvidenceRoot;
    private final SpringRuntimeAuthentication authentication;
    private final ObjectMapper json;
    private final Clock clock;
    private final HttpClient client;
    private final SecureRandom random = new SecureRandom();

    EphemeralSpringVerifierBroker(
            DockerClient docker,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            String verifierImageDigest,
            String verifierId,
            String internalNetworkName,
            String egressProxyUrl,
            Path serviceInputRoot,
            Path hostInputRoot,
            Path serviceEvidenceRoot,
            Path hostEvidenceRoot,
            SpringRuntimeAuthentication authentication,
            ObjectMapper json,
            Clock clock
    ) {
        this.docker = Objects.requireNonNull(docker);
        this.images = Objects.requireNonNull(images);
        if (verifierImageDigest == null || !verifierImageDigest.matches("sha256:[0-9a-f]{64}")) {
            throw new IllegalArgumentException("approved verifier image digest is required");
        }
        if (verifierId == null || !verifierId.matches("[A-Za-z0-9._-]{3,96}")) {
            throw new IllegalArgumentException("verifier ID is invalid");
        }
        if (internalNetworkName == null || !internalNetworkName.matches("[A-Za-z0-9._-]{3,128}")) {
            throw new IllegalArgumentException("verifier internal network name is invalid");
        }
        URI proxy = URI.create(egressProxyUrl);
        if (!"http".equals(proxy.getScheme()) || proxy.getHost() == null || proxy.getUserInfo() != null) {
            throw new IllegalArgumentException("verifier egress proxy URL is invalid");
        }
        this.verifierImageDigest = verifierImageDigest;
        this.verifierId = verifierId;
        this.internalNetworkName = internalNetworkName;
        this.egressProxyUrl = egressProxyUrl;
        this.serviceInputRoot = serviceInputRoot.toAbsolutePath().normalize();
        this.hostInputRoot = hostInputRoot.toAbsolutePath().normalize();
        this.serviceEvidenceRoot = serviceEvidenceRoot.toAbsolutePath().normalize();
        this.hostEvidenceRoot = hostEvidenceRoot.toAbsolutePath().normalize();
        this.authentication = Objects.requireNonNull(authentication);
        this.json = Objects.requireNonNull(json);
        this.clock = Objects.requireNonNull(clock);
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        try {
            Files.createDirectories(this.serviceEvidenceRoot);
        } catch (IOException error) {
            throw new IllegalStateException("ephemeral verifier roots are unavailable", error);
        }
    }

    BrokerResponse verify(String timestamp, String nonce, String signature, byte[] body) {
        authentication.verify(timestamp, nonce, signature, body);
        VerificationRequest request = parse(body);
        Path serviceArtifact = artifact(serviceInputRoot, request.artifactRelativePath());
        Path hostArtifact = hostArtifact(hostInputRoot, request.artifactRelativePath());
        if (!request.artifactSha256().equals(sha256(serviceArtifact))) {
            throw rejected("ARTIFACT_DIGEST_MISMATCH",
                    "Candidate Artifact differs from the transformation digest.");
        }
        requireRootless();
        images.requireApproved("spring-verifier-java17-java21-maven", verifierImageDigest);

        Path serviceRunEvidence = confined(serviceEvidenceRoot, request.runId());
        Path hostRunEvidence = confined(hostEvidenceRoot, request.runId());
        byte[] oneTimeSecret = new byte[48];
        random.nextBytes(oneTimeSecret);
        String secretValue = Base64.getUrlEncoder().withoutPadding().encodeToString(oneTimeSecret);
        Arrays.fill(oneTimeSecret, (byte) 0);

        String containerName = "elmos-spring-verifier-" + request.runId().replace("-", "");
        String container = null;
        try {
            Files.createDirectories(serviceRunEvidence);
            makeEphemeralContainerWritable(serviceRunEvidence);
            removeExisting(containerName);
            HostConfig host = HostConfig.newHostConfig()
                    .withPrivileged(false)
                    .withReadonlyRootfs(true)
                    .withCapDrop(Capability.ALL)
                    .withSecurityOpts(List.of("no-new-privileges:true"))
                    .withMemory(3L * 1024 * 1024 * 1024)
                    .withMemorySwap(3L * 1024 * 1024 * 1024)
                    .withNanoCPUs(3_000_000_000L)
                    .withPidsLimit(512L)
                    .withNetworkMode(internalNetworkName)
                    .withIpcMode("private")
                    .withTmpFs(Map.of("/tmp", "rw,noexec,nosuid,size=256m"))
                    .withBinds(
                            new Bind(hostArtifact.toString(),
                                    new Volume("/input/runs/" + request.artifactRelativePath()),
                                    com.github.dockerjava.api.model.AccessMode.ro),
                            new Bind(hostRunEvidence.toString(),
                                    new Volume("/verification/" + request.runId()),
                                    com.github.dockerjava.api.model.AccessMode.rw)
                    );
            Map<String, String> labels = Map.of(
                    "elmos.managed", "true",
                    "elmos.resource_role", "spring-verifier",
                    "elmos.run_id", request.runId(),
                    "elmos.retention", "ephemeral"
            );
            container = docker.createContainerCmd(verifierImageDigest)
                    .withName(containerName)
                    .withUser("10002:10002")
                    .withEnv(
                            "ELMOS_VERIFIER_ID=" + verifierId,
                            "ELMOS_VERIFIER_INPUT_ROOT=/input/runs",
                            "ELMOS_VERIFIER_EVIDENCE_ROOT=/verification/" + request.runId(),
                            "ELMOS_VERIFIER_HMAC_SECRET_VALUE=" + secretValue,
                            "HTTPS_PROXY=" + egressProxyUrl,
                            "https_proxy=" + egressProxyUrl,
                            "NO_PROXY=127.0.0.1,localhost",
                            "no_proxy=127.0.0.1,localhost"
                    )
                    .withHostConfig(host)
                    .withLabels(labels)
                    .exec()
                    .getId();
            docker.startContainerCmd(container).exec();
            waitForVerifier(containerName);
            byte[] responseBody = callVerifier(
                    containerName,
                    body,
                    secretValue.getBytes(StandardCharsets.UTF_8)
            );
            VerificationResponse response = json.readValue(responseBody, VerificationResponse.class);
            VerificationResponse normalized = normalizeAndVerifyResponse(request, response);
            return new BrokerResponse(200, json.writeValueAsBytes(normalized));
        } catch (Rejected error) {
            throw error;
        } catch (IOException error) {
            throw rejected("EPHEMERAL_VERIFIER_PROTOCOL_ERROR",
                    "Ephemeral verifier returned invalid data.");
        } finally {
            if (container != null) remove(container);
            makeBrokerPrivate(serviceRunEvidence);
        }
    }

    private byte[] callVerifier(String containerName, byte[] body, byte[] secret) {
        String timestamp = Long.toString(clock.instant().getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = SpringRuntimeAuthentication.sign(secret, timestamp, nonce, body);
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://" + containerName + ":8082/internal/v1/spring-verifications"))
                .timeout(Duration.ofMinutes(35))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .header("X-ELMOS-Verifier-Timestamp", timestamp)
                .header("X-ELMOS-Verifier-Nonce", nonce)
                .header("X-ELMOS-Verifier-Signature", signature)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        try {
            HttpResponse<byte[]> response = client.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.body().length > 256 * 1024) {
                throw rejected("EPHEMERAL_VERIFIER_PROTOCOL_ERROR",
                        "Ephemeral verifier response exceeded policy.");
            }
            if (response.statusCode() != 200) {
                throw rejected("INDEPENDENT_VALIDATION_FAILED",
                        "Ephemeral independent verifier rejected the candidate.");
            }
            return response.body();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw rejected("INDEPENDENT_VALIDATION_INTERRUPTED",
                    "Ephemeral independent verification was interrupted.");
        } catch (IOException error) {
            throw rejected("EPHEMERAL_VERIFIER_UNAVAILABLE",
                    "Ephemeral independent verifier is unavailable.");
        }
    }

    private VerificationResponse normalizeAndVerifyResponse(
            VerificationRequest request,
            VerificationResponse response
    ) {
        if (response == null
                || !"PASS".equals(response.status())
                || !verifierId.equals(response.verifierId())
                || !request.artifactSha256().equals(response.artifactSha256())
                || !request.targetSpringBoot().equals(response.targetSpringBoot())
                || !request.targetJava().equals(response.targetJava())
                || !response.physicallySeparateVerifierService()
                || response.transformCapability()) {
            throw rejected("EPHEMERAL_VERIFIER_PROTOCOL_ERROR",
                    "Ephemeral verifier decision violates the independent verification contract.");
        }
        String evidencePath = prefixed(request.runId(), response.evidenceRelativePath());
        String logPath = prefixed(request.runId(), response.logRelativePath());
        String runtimePath = prefixed(request.runId(), response.runtimeArtifactRelativePath());
        verifyEvidence(evidencePath, response.evidenceSha256(), response.evidenceBytes());
        verifyEvidence(logPath, response.logSha256(), response.logBytes());
        verifyEvidence(runtimePath, response.runtimeArtifactSha256(), response.runtimeArtifactBytes());
        return new VerificationResponse(
                response.status(),
                response.verifierId(),
                response.artifactSha256(),
                response.targetSpringBoot(),
                response.targetJava(),
                response.freshArtifactWorkspace(),
                response.transformCapability(),
                response.physicallySeparateVerifierService(),
                evidencePath,
                logPath,
                response.evidenceSha256(),
                response.evidenceBytes(),
                response.logSha256(),
                response.logBytes(),
                runtimePath,
                response.runtimeArtifactSha256(),
                response.runtimeArtifactBytes(),
                response.command(),
                response.decidedAt()
        );
    }

    private void verifyEvidence(String relative, String expectedSha, long expectedBytes) {
        Path path = serviceEvidenceRoot.resolve(relative).normalize();
        try {
            if (!path.startsWith(serviceEvidenceRoot)
                    || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                    || Files.isSymbolicLink(path)
                    || expectedBytes != Files.size(path)
                    || !expectedSha.equals(sha256(path))) {
                throw rejected("VERIFIER_EVIDENCE_DIGEST_MISMATCH",
                        "Ephemeral verifier Evidence differs from its decision receipt.");
            }
        } catch (IOException error) {
            throw rejected("VERIFIER_EVIDENCE_UNAVAILABLE",
                    "Ephemeral verifier Evidence is unavailable.");
        }
    }

    private void waitForVerifier(String containerName) {
        long deadline = System.nanoTime() + Duration.ofSeconds(45).toNanos();
        URI health = URI.create("http://" + containerName + ":8082/actuator/health/readiness");
        while (System.nanoTime() < deadline) {
            try {
                HttpResponse<Void> response = client.send(
                        HttpRequest.newBuilder(health).timeout(Duration.ofSeconds(2)).GET().build(),
                        HttpResponse.BodyHandlers.discarding()
                );
                if (response.statusCode() == 200) return;
            } catch (IOException ignored) {
                // Retry within the bounded startup window.
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw rejected("EPHEMERAL_VERIFIER_START_INTERRUPTED",
                        "Ephemeral verifier startup was interrupted.");
            }
            try {
                Thread.sleep(250);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw rejected("EPHEMERAL_VERIFIER_START_INTERRUPTED",
                        "Ephemeral verifier startup was interrupted.");
            }
        }
        throw rejected("EPHEMERAL_VERIFIER_START_TIMEOUT",
                "Ephemeral verifier did not become ready.");
    }

    private void removeExisting(String name) {
        List<String> ids = docker.listContainersCmd()
                .withShowAll(true)
                .withNameFilter(List.of(name))
                .exec()
                .stream()
                .filter(container -> Arrays.asList(container.getNames()).contains("/" + name))
                .map(com.github.dockerjava.api.model.Container::getId)
                .toList();
        if (ids.size() > 1) {
            throw rejected("EPHEMERAL_VERIFIER_IDENTITY_AMBIGUOUS",
                    "Ephemeral verifier container identity is ambiguous.");
        }
        ids.forEach(this::remove);
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

    private void requireRootless() {
        List<String> options = docker.infoCmd().exec().getSecurityOptions();
        if (options == null
                || options.stream().map(String::toLowerCase)
                .noneMatch(value -> value.contains("rootless"))) {
            throw rejected("ROOTLESS_DAEMON_REQUIRED",
                    "Docker daemon did not prove rootless mode.");
        }
    }

    private VerificationRequest parse(byte[] body) {
        try {
            if (body.length == 0 || body.length > 64 * 1024) {
                throw rejected("VERIFIER_REQUEST_REJECTED", "Verifier request is invalid.");
            }
            VerificationRequest request = json.readValue(body, VerificationRequest.class);
            if (request.runId() == null
                    || !request.runId().matches("[0-9a-fA-F-]{36}")
                    || request.artifactRelativePath() == null
                    || request.artifactSha256() == null
                    || !request.artifactSha256().matches("[0-9a-f]{64}")
                    || !supportedTarget(request.targetSpringBoot(), request.targetJava())) {
                throw rejected("VERIFIER_REQUEST_REJECTED", "Verifier request fields are invalid.");
            }
            UUID.fromString(request.runId());
            return request;
        } catch (Rejected error) {
            throw error;
        } catch (IOException | IllegalArgumentException error) {
            throw rejected("VERIFIER_REQUEST_REJECTED", "Verifier request is invalid.");
        }
    }

    private static Path artifact(Path root, String relativeValue) {
        try {
            Path relative = Path.of(relativeValue);
            Path candidate = root.resolve(relative).normalize();
            if (relative.isAbsolute()
                    || relative.normalize().startsWith("..")
                    || !candidate.startsWith(root)
                    || !Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS)
                    || Files.isSymbolicLink(candidate)) {
                throw rejected("ARTIFACT_PATH_REJECTED",
                        "Candidate Artifact path is unavailable or outside policy.");
            }
            return candidate;
        } catch (InvalidPathException error) {
            throw rejected("ARTIFACT_PATH_REJECTED", "Candidate Artifact path is invalid.");
        }
    }

    private static Path hostArtifact(Path root, String relativeValue) {
        try {
            Path relative = Path.of(relativeValue);
            Path candidate = root.resolve(relative).normalize();
            if (relative.isAbsolute()
                    || relative.normalize().startsWith("..")
                    || !candidate.startsWith(root)
                    || candidate.equals(root)) {
                throw rejected("ARTIFACT_PATH_REJECTED",
                        "Candidate Artifact host path is outside policy.");
            }
            return candidate;
        } catch (InvalidPathException error) {
            throw rejected("ARTIFACT_PATH_REJECTED", "Candidate Artifact host path is invalid.");
        }
    }

    private static Path confined(Path root, String child) {
        Path value = root.resolve(child).normalize();
        if (!value.startsWith(root) || value.equals(root)) {
            throw rejected("BROKER_PATH_REJECTED", "Ephemeral verifier path escapes its root.");
        }
        return value;
    }

    private static String prefixed(String runId, String value) {
        if (value == null || !value.matches("[A-Za-z0-9._/-]{3,512}")
                || value.startsWith("/") || value.contains("..")) {
            throw rejected("EPHEMERAL_VERIFIER_PROTOCOL_ERROR",
                    "Ephemeral verifier Evidence path is invalid.");
        }
        return runId + "/" + value;
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
            throw rejected("DIGEST_UNAVAILABLE", "Content digest could not be calculated.");
        }
    }

    private static void makeEphemeralContainerWritable(Path path) {
        try {
            Files.setPosixFilePermissions(path, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE,
                    PosixFilePermission.OWNER_EXECUTE,
                    PosixFilePermission.GROUP_READ,
                    PosixFilePermission.GROUP_WRITE,
                    PosixFilePermission.GROUP_EXECUTE,
                    PosixFilePermission.OTHERS_READ,
                    PosixFilePermission.OTHERS_WRITE,
                    PosixFilePermission.OTHERS_EXECUTE
            ));
        } catch (IOException error) {
            throw rejected("VERIFIER_EVIDENCE_PERMISSION_FAILED",
                    "Ephemeral verifier Evidence directory permissions could not be prepared.");
        } catch (UnsupportedOperationException ignored) {
            // The deployment gate must validate equivalent ACL isolation.
        }
    }

    private static void makeBrokerPrivate(Path path) {
        if (!Files.exists(path, LinkOption.NOFOLLOW_LINKS)) return;
        try {
            Files.setPosixFilePermissions(path, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE,
                    PosixFilePermission.OWNER_EXECUTE
            ));
        } catch (IOException error) {
            throw new IllegalStateException(
                    "ephemeral verifier Evidence directory could not be made private", error);
        } catch (UnsupportedOperationException ignored) {
            // The deployment gate must validate equivalent ACL isolation.
        }
    }

    record BrokerResponse(int status, byte[] body) {}

    private record VerificationRequest(
            String runId,
            String artifactRelativePath,
            String artifactSha256,
            String targetSpringBoot,
            String targetJava
    ) {
        VerificationRequest {
            if (targetSpringBoot == null || targetSpringBoot.isBlank()) targetSpringBoot = "3.5.3";
            if (targetJava == null || targetJava.isBlank()) targetJava = "21";
        }
    }

    private record VerificationResponse(
            String status,
            String verifierId,
            String artifactSha256,
            String targetSpringBoot,
            String targetJava,
            boolean freshArtifactWorkspace,
            boolean transformCapability,
            boolean physicallySeparateVerifierService,
            String evidenceRelativePath,
            String logRelativePath,
            String evidenceSha256,
            long evidenceBytes,
            String logSha256,
            long logBytes,
            String runtimeArtifactRelativePath,
            String runtimeArtifactSha256,
            long runtimeArtifactBytes,
            List<String> command,
            java.time.Instant decidedAt
    ) {}

    private static Rejected rejected(String code, String message) {
        return new Rejected(code, message);
    }

    private static boolean supportedTarget(String boot, String java) {
        return ("2.7.18".equals(boot) && "17".equals(java))
                || ("3.2.12".equals(boot) && "17".equals(java))
                || ("3.5.3".equals(boot) && "21".equals(java));
    }
}
