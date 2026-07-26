package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;

import static io.elmos.worker.SpringUpgradeModels.BlockedException;
import static io.elmos.worker.SpringUpgradeModels.ExecutionResult;
import static io.elmos.worker.SpringUpgradeModels.Stage;
import static io.elmos.worker.SpringUpgradeModels.StartRequest;

/**
 * One-shot transformation API used only inside an ephemeral rootless container.
 * The secret is unique to this container and cannot authorize the broker or any other run.
 */
@RestController
public final class EphemeralTransformerController {
    private static final int MAX_REQUEST_BYTES = 128 * 1024;
    private final ObjectMapper json;
    private final Clock clock;
    private final byte[] secret;
    private final long authWindowSeconds;
    private final LocalSpringUpgradeExecutionPort execution;
    private final Path runRoot;
    private final Path progress;
    private final Object progressLock = new Object();
    private final Map<String, Long> nonces = new ConcurrentHashMap<>();

    public EphemeralTransformerController(
            ObjectMapper json,
            Clock clock,
            @Value("${elmos.transformer.workspace-root:/workspace}") String workspaceRoot,
            @Value("${elmos.transformer.source-java-home:/opt/java/openjdk-17}") String sourceJavaHome,
            @Value("${elmos.transformer.target-java-home:/opt/java/openjdk}") String targetJavaHome,
            @Value("${elmos.transformer.maven-executable:/usr/share/maven/bin/mvn}") String mavenExecutable,
            @Value("${elmos.transformer.allowed-git-hosts:github.com}") String allowedGitHosts,
            @Value("${elmos.transformer.one-time-secret:}") String oneTimeSecret,
            @Value("${elmos.transformer.auth-window-seconds:90}") long authWindowSeconds
    ) {
        this.json = Objects.requireNonNull(json);
        this.clock = Objects.requireNonNull(clock);
        this.secret = Objects.toString(oneTimeSecret, "").getBytes(StandardCharsets.UTF_8);
        if (secret.length < 32 || secret.length > 4096) {
            throw new IllegalStateException("ephemeral transformer one-time secret must contain 32-4096 bytes");
        }
        if (authWindowSeconds < 30 || authWindowSeconds > 300) {
            throw new IllegalStateException("ephemeral transformer auth window must be 30-300 seconds");
        }
        this.authWindowSeconds = authWindowSeconds;
        Path root = Path.of(workspaceRoot).toAbsolutePath().normalize();
        this.runRoot = root.resolve("run").normalize();
        if (!runRoot.startsWith(root) || runRoot.equals(root)) {
            throw new IllegalStateException("ephemeral transformer run root is invalid");
        }
        this.progress = runRoot.resolve("evidence/transform-progress.jsonl");
        this.execution = new LocalSpringUpgradeExecutionPort(
                root,
                Path.of(sourceJavaHome),
                Path.of(targetJavaHome),
                mavenExecutable,
                hosts(allowedGitHosts),
                false,
                true,
                json
        );
    }

    @PostMapping(
            path = "/internal/v1/spring-transformations",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    TransformationResponse transform(
            @RequestHeader("X-ELMOS-Transformer-Timestamp") String timestamp,
            @RequestHeader("X-ELMOS-Transformer-Nonce") String nonce,
            @RequestHeader("X-ELMOS-Transformer-Signature") String signature,
            @RequestBody byte[] body
    ) {
        authenticate(timestamp, nonce, signature, body);
        TransformationRequest envelope = parse(body);
        if (!"TRANSFORM".equals(envelope.action()) || envelope.request() == null) {
            throw new Rejected("TRANSFORM_REQUEST_REJECTED",
                    "Only the TRANSFORM action is accepted by an ephemeral transformer.");
        }
        try {
            Files.createDirectories(progress.getParent());
            Files.deleteIfExists(progress);
        } catch (IOException error) {
            throw new Rejected("TRANSFORM_PROGRESS_UNAVAILABLE",
                    "Transformation progress Evidence could not be initialized.");
        }

        AtomicReference<Process> activeProcess = new AtomicReference<>();
        SpringUpgradeExecutionPort.Control control = new SpringUpgradeExecutionPort.Control() {
            @Override public void stage(Stage stage, String message) {
                appendProgress(Map.of(
                        "kind", "stage",
                        "stage", stage.name(),
                        "message", bounded(message),
                        "observedAt", Instant.now(clock).toString()
                ));
            }

            @Override public void log(String line) {
                appendProgress(Map.of(
                        "kind", "log",
                        "message", bounded(line),
                        "observedAt", Instant.now(clock).toString()
                ));
            }

            @Override public void process(Process process) {
                Process previous = activeProcess.getAndSet(process);
                if (previous != null && previous != process && previous.isAlive()) {
                    previous.destroyForcibly();
                }
            }

            @Override public boolean cancelled() {
                return Thread.currentThread().isInterrupted()
                        || Files.exists(runRoot.resolve(".cancel-requested"));
            }
        };

        try {
            ExecutionResult result = execution.execute(envelope.request(), runRoot, control);
            return new TransformationResponse(
                    "SUCCEEDED",
                    envelope.runId(),
                    result.resolvedCommitSha(),
                    result.snapshotId(),
                    result.snapshotDigest(),
                    result.fingerprint(),
                    result.fcmArtifact(),
                    relative(result.migratedRepository()),
                    relative(result.downloadArtifact()),
                    result.artifactSha256(),
                    result.artifactSize(),
                    result.healthCandidates()
            );
        } finally {
            Process process = activeProcess.getAndSet(null);
            if (process != null && process.isAlive()) process.destroyForcibly();
        }
    }

    @ExceptionHandler(Rejected.class)
    ResponseEntity<Map<String, String>> rejected(Rejected error) {
        HttpStatus status = "UNAUTHORIZED".equals(error.code())
                ? HttpStatus.UNAUTHORIZED
                : HttpStatus.UNPROCESSABLE_ENTITY;
        return ResponseEntity.status(status).body(Map.of(
                "status", "BLOCKED",
                "code", error.code(),
                "message", "Transformation request was rejected; use the stable code for controlled diagnostics."
        ));
    }

    @ExceptionHandler(BlockedException.class)
    ResponseEntity<Map<String, String>> blocked(BlockedException error) {
        return ResponseEntity.unprocessableEntity().body(Map.of(
                "status", "BLOCKED",
                "code", error.code(),
                "message", "Transformation is blocked; use the stable code for controlled diagnostics."
        ));
    }

    private TransformationRequest parse(byte[] body) {
        if (body.length == 0 || body.length > MAX_REQUEST_BYTES) {
            throw new Rejected("TRANSFORM_REQUEST_REJECTED", "Transformation request is invalid.");
        }
        try {
            TransformationRequest value = json.readValue(body, TransformationRequest.class);
            if (value == null || value.runId() == null
                    || !value.runId().matches("[0-9a-fA-F-]{36}")) {
                throw new Rejected("TRANSFORM_REQUEST_REJECTED", "Transformation run identity is invalid.");
            }
            UUID.fromString(value.runId());
            return value;
        } catch (Rejected error) {
            throw error;
        } catch (IOException | IllegalArgumentException error) {
            throw new Rejected("TRANSFORM_REQUEST_REJECTED", "Transformation request is invalid.");
        }
    }

    private void authenticate(String timestampValue, String nonce, String signature, byte[] body) {
        long now = clock.instant().getEpochSecond();
        long timestamp;
        try {
            timestamp = Long.parseLong(Objects.toString(timestampValue, ""));
        } catch (NumberFormatException error) {
            throw unauthorized();
        }
        if (Math.abs(now - timestamp) > authWindowSeconds
                || nonce == null
                || !nonce.matches("[0-9a-fA-F-]{36}")
                || signature == null
                || !signature.matches("[0-9a-f]{64}")) {
            throw unauthorized();
        }
        nonces.entrySet().removeIf(entry -> entry.getValue() < now - authWindowSeconds);
        if (nonces.putIfAbsent(nonce, timestamp) != null) throw unauthorized();
        String expected = sign(secret, timestampValue, nonce, body);
        if (!MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.US_ASCII),
                signature.getBytes(StandardCharsets.US_ASCII))) {
            nonces.remove(nonce, timestamp);
            throw unauthorized();
        }
    }

    private void appendProgress(Map<String, ?> value) {
        synchronized (progressLock) {
            try {
                byte[] line = (json.writeValueAsString(value) + "\n").getBytes(StandardCharsets.UTF_8);
                Files.write(progress, line, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (IOException error) {
                throw new Rejected("TRANSFORM_PROGRESS_UNAVAILABLE",
                        "Transformation progress Evidence could not be persisted.");
            }
        }
    }

    private String relative(Path value) {
        Path path = value.toAbsolutePath().normalize();
        if (!path.startsWith(runRoot) || path.equals(runRoot)) {
            throw new Rejected("TRANSFORM_RESPONSE_REJECTED",
                    "Transformation output escaped the run workspace.");
        }
        return runRoot.relativize(path).toString();
    }

    private static String bounded(String value) {
        String text = Objects.toString(value, "").replaceAll("[\\r\\n]+", " ").trim();
        return text.length() > 1_000 ? text.substring(0, 1_000) : text;
    }

    private static Set<String> hosts(String value) {
        return Arrays.stream(Objects.toString(value, "").split(","))
                .map(String::trim)
                .filter(host -> !host.isBlank())
                .map(host -> host.toLowerCase(Locale.ROOT))
                .collect(Collectors.toUnmodifiableSet());
    }

    private static String sign(byte[] secret, String timestamp, String nonce, byte[] body) {
        try {
            String bodySha = HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(body));
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(
                    (timestamp + "\n" + nonce + "\n" + bodySha).getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException("transformer request signing is unavailable", error);
        }
    }

    private static Rejected unauthorized() {
        return new Rejected("UNAUTHORIZED", "Ephemeral transformer authentication failed.");
    }

    record TransformationRequest(String action, String runId, StartRequest request) {}

    record TransformationResponse(
            String status,
            String runId,
            String resolvedCommitSha,
            String snapshotId,
            String snapshotDigest,
            SpringUpgradeModels.Fingerprint fingerprint,
            String fcmArtifact,
            String migratedRepositoryRelativePath,
            String downloadArtifactRelativePath,
            String artifactSha256,
            long artifactSize,
            List<String> healthCandidates
    ) {}

    static final class Rejected extends RuntimeException {
        private final String code;
        Rejected(String code, String message) {
            super(message);
            this.code = code;
        }
        String code() { return code; }
    }
}
