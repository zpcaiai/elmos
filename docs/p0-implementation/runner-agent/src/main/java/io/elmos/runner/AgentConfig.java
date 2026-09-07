package io.elmos.runner;

import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

/**
 * Runner Agent configuration, resolved from the environment and validated once at
 * startup.
 *
 * <p>Every check here fails closed. The agent refuses to start rather than run in
 * a weaker mode, because a runner that silently degrades - host execution instead
 * of a container, a mutable image instead of a digest - is exactly the failure
 * that turns "temporary workaround" into production.</p>
 */
public record AgentConfig(
        String controlPlaneBaseUrl,
        String runnerNodeId,
        String poolId,
        String enrolmentToken,
        List<String> capabilities,
        int maxConcurrency,
        Path workRoot,
        String containerEngine,
        int claimBatchSize,
        int leaseSeconds,
        int heartbeatIntervalSeconds,
        int cancelGraceSeconds,
        int metricsPort,
        boolean allowHostExecution,
        int workloadUid,
        int workloadGid
) {

    public static final class ConfigException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        public ConfigException(String message) {
            super(message);
        }
    }

    public static AgentConfig fromEnvironment(Map<String, String> env) {
        String baseUrl = required(env, "ELMOS_CONTROL_PLANE_BASE_URL");
        if (!baseUrl.startsWith("http://") && !baseUrl.startsWith("https://")) {
            throw new ConfigException("ELMOS_CONTROL_PLANE_BASE_URL must be an absolute http(s) URL");
        }
        // Plain http is acceptable only for loopback development.
        if (baseUrl.startsWith("http://")
                && !(baseUrl.contains("://localhost") || baseUrl.contains("://127.0.0.1"))) {
            throw new ConfigException("ELMOS_CONTROL_PLANE_BASE_URL must use https outside loopback");
        }

        String nodeId = required(env, "ELMOS_RUNNER_NODE_ID");
        if (!nodeId.matches("^[a-z0-9][a-z0-9._-]{2,95}$")) {
            throw new ConfigException("ELMOS_RUNNER_NODE_ID has an unsupported shape");
        }

        String enrolment = resolveSecret(env, "ELMOS_RUNNER_ENROLMENT_TOKEN");
        if (enrolment.length() < 32) {
            throw new ConfigException("ELMOS_RUNNER_ENROLMENT_TOKEN must be at least 32 characters");
        }

        List<String> capabilities = new ArrayList<>();
        for (String raw : required(env, "ELMOS_RUNNER_CAPABILITIES").split(",")) {
            String value = raw.trim();
            if (!value.isEmpty()) {
                if (!value.matches("^[a-z0-9][a-z0-9:._-]{1,95}$")) {
                    throw new ConfigException("capability has an unsupported shape: " + value);
                }
                capabilities.add(value);
            }
        }
        if (capabilities.isEmpty() || capabilities.size() > 32) {
            throw new ConfigException("ELMOS_RUNNER_CAPABILITIES must declare 1..32 capabilities");
        }

        int maxConcurrency = bounded(env, "ELMOS_RUNNER_MAX_CONCURRENCY", 2, 1, 16);

        Path workRoot = Path.of(required(env, "ELMOS_RUNNER_WORK_ROOT")).toAbsolutePath().normalize();
        validateWorkRoot(workRoot);

        boolean allowHost = "true".equalsIgnoreCase(env.getOrDefault("ELMOS_RUNNER_ALLOW_HOST_EXECUTION", "false"));
        String engine = env.getOrDefault("ELMOS_RUNNER_CONTAINER_ENGINE", "").trim();
        if (!allowHost) {
            if (engine.isEmpty()) {
                throw new ConfigException("ELMOS_RUNNER_CONTAINER_ENGINE is required unless host execution is explicitly allowed");
            }
            Path enginePath = Path.of(engine);
            if (!enginePath.isAbsolute()) {
                // A relative engine name resolves through PATH, which the operator
                // may not control on a shared node.
                throw new ConfigException("ELMOS_RUNNER_CONTAINER_ENGINE must be an absolute path");
            }
            if (!Files.isExecutable(enginePath)) {
                throw new ConfigException("ELMOS_RUNNER_CONTAINER_ENGINE is not executable: " + engine);
            }
        } else if (isProductionLike(env)) {
            throw new ConfigException("host execution is refused when ELMOS_ENVIRONMENT is production");
        }

        return new AgentConfig(
                stripTrailingSlash(baseUrl),
                nodeId,
                required(env, "ELMOS_RUNNER_POOL_ID"),
                enrolment,
                List.copyOf(capabilities),
                maxConcurrency,
                workRoot,
                engine,
                bounded(env, "ELMOS_RUNNER_CLAIM_BATCH", Math.min(maxConcurrency, 4), 1, 16),
                bounded(env, "ELMOS_RUNNER_LEASE_SECONDS", 120, 30, 600),
                bounded(env, "ELMOS_RUNNER_HEARTBEAT_SECONDS", 30, 5, 120),
                bounded(env, "ELMOS_RUNNER_CANCEL_GRACE_SECONDS", 30, 5, 300),
                bounded(env, "ELMOS_RUNNER_METRICS_PORT", 9464, 1024, 65535),
                allowHost,
                // Defaults to the agent's own uid. Under rootless podman with
                // --userns=keep-id that is the only uid which maps 1:1 to the host,
                // and therefore the only one that can write into a workspace the
                // agent created. Overriding it requires the operator to have
                // arranged matching ownership themselves.
                bounded(env, "ELMOS_RUNNER_WORKLOAD_UID", currentUid(), 1, 4294967),
                bounded(env, "ELMOS_RUNNER_WORKLOAD_GID", currentGid(), 1, 4294967));
    }

    /**
     * The heartbeat must fire several times inside one lease. If it only fired once
     * a single dropped request would expire the lease and the control plane would
     * hand the job to a second runner.
     */
    public void validateTimings() {
        if (heartbeatIntervalSeconds * 3 > leaseSeconds) {
            throw new ConfigException(
                    "lease must cover at least three heartbeat intervals: lease=" + leaseSeconds
                            + "s heartbeat=" + heartbeatIntervalSeconds + "s");
        }
    }

    private static void validateWorkRoot(Path workRoot) {
        if (workRoot.getNameCount() == 0 || workRoot.equals(workRoot.getRoot())) {
            throw new ConfigException("ELMOS_RUNNER_WORK_ROOT must not be the filesystem root");
        }
        if (Files.exists(workRoot, LinkOption.NOFOLLOW_LINKS) && !Files.isDirectory(workRoot, LinkOption.NOFOLLOW_LINKS)) {
            throw new ConfigException("ELMOS_RUNNER_WORK_ROOT exists and is not a directory");
        }
        if (Files.isSymbolicLink(workRoot)) {
            // A symlinked work root lets whoever controls the link redirect every
            // job workspace somewhere else.
            throw new ConfigException("ELMOS_RUNNER_WORK_ROOT must not be a symbolic link");
        }
    }

    private static boolean isProductionLike(Map<String, String> env) {
        String environment = env.getOrDefault("ELMOS_ENVIRONMENT", "").toLowerCase(Locale.ROOT);
        return environment.equals("production") || environment.equals("prod");
    }

    /** Prefers a file-backed secret so the token never appears in the process environment. */
    private static String resolveSecret(Map<String, String> env, String name) {
        String file = env.get(name + "_FILE");
        String inline = env.get(name);
        if (file != null && !file.isBlank()) {
            if (inline != null && !inline.isBlank()) {
                throw new ConfigException(name + " and " + name + "_FILE are mutually exclusive");
            }
            Path path = Path.of(file);
            if (!path.isAbsolute() || Files.isSymbolicLink(path)) {
                throw new ConfigException(name + "_FILE must be an absolute, non-symlink path");
            }
            try {
                return Files.readString(path).trim();
            } catch (Exception ex) {
                throw new ConfigException("cannot read " + name + "_FILE");
            }
        }
        if (inline == null || inline.isBlank()) {
            throw new ConfigException(name + " is required");
        }
        return inline.trim();
    }

    private static String required(Map<String, String> env, String name) {
        String value = env.get(name);
        if (value == null || value.isBlank()) {
            throw new ConfigException(name + " is required");
        }
        return value.trim();
    }

    private static int bounded(Map<String, String> env, String name, int fallback, int min, int max) {
        String raw = env.get(name);
        int value = fallback;
        if (raw != null && !raw.isBlank()) {
            try {
                value = Integer.parseInt(raw.trim());
            } catch (NumberFormatException ex) {
                throw new ConfigException(name + " must be an integer");
            }
        }
        if (value < min || value > max) {
            throw new ConfigException(name + " must be within [" + min + "," + max + "]");
        }
        return value;
    }

    /**
     * The agent's own uid, or 65532 when it cannot be read.
     *
     * <p>Running the workload as a different uid than the one that created the
     * workspace produces a "Permission denied" on the first artifact write - and
     * because a shell redirection failure does not always set a non-zero exit
     * code, that surfaces as a job that succeeded and produced nothing.</p>
     */
    private static int currentUid() {
        int uid = posixId("uid", 65532);
        // A workload must never run as root, so uid 0 is never a valid default for
        // it. When the agent itself is root - development, or a misconfigured
        // deployment - fall back to the conventional non-root id and let the
        // workspace probe decide whether that is actually usable.
        return uid == 0 ? 65532 : uid;
    }

    private static int currentGid() {
        int gid = posixId("gid", 65532);
        return gid == 0 ? 65532 : gid;
    }

    private static int posixId(String kind, int fallback) {
        try {
            Object value = Class.forName("com.sun.security.auth.module.UnixSystem")
                    .getDeclaredConstructor().newInstance();
            java.lang.reflect.Method method = value.getClass()
                    .getMethod(kind.equals("uid") ? "getUid" : "getGid");
            return (int) (long) (Long) method.invoke(value);
        } catch (Exception ex) {
            return fallback;
        }
    }

    private static String stripTrailingSlash(String value) {
        String result = value;
        while (result.endsWith("/")) {
            result = result.substring(0, result.length() - 1);
        }
        return result;
    }

    public AgentConfig {
        Objects.requireNonNull(controlPlaneBaseUrl);
        Objects.requireNonNull(runnerNodeId);
        Objects.requireNonNull(capabilities);
        Objects.requireNonNull(workRoot);
    }
}
