package io.elmos.verifier;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static io.elmos.verifier.VerificationModels.Rejected;

final class ProcessMavenVerification implements MavenVerification {
    private static final long MAX_LOG_BYTES = 16L * 1024 * 1024;
    private final Path javaHome;
    private final String mavenExecutable;
    private final Duration timeout;
    private final Path immutableDependencyCache;

    ProcessMavenVerification(Path javaHome, String mavenExecutable, int timeoutMinutes) {
        this(javaHome, mavenExecutable, timeoutMinutes, null);
    }

    ProcessMavenVerification(
            Path javaHome,
            String mavenExecutable,
            int timeoutMinutes,
            Path immutableDependencyCache
    ) {
        this.javaHome = javaHome.toAbsolutePath().normalize();
        this.mavenExecutable = requireMaven(mavenExecutable, this.javaHome);
        this.timeout = Duration.ofMinutes(timeoutMinutes);
        this.immutableDependencyCache = immutableDependencyCache == null
                ? null
                : requireDependencyCache(immutableDependencyCache);
        if (!Files.isExecutable(this.javaHome.resolve("bin/java"))) {
            throw new IllegalStateException("independent verifier Java 21 is unavailable");
        }
        if (timeoutMinutes < 1 || timeoutMinutes > 120) {
            throw new IllegalArgumentException("verifier timeout must be 1-120 minutes");
        }
    }

    @Override
    public List<String> verify(Path projectRoot, Path logFile) {
        List<String> command = immutableDependencyCache == null
                ? List.of(mavenExecutable, "-B", "--no-transfer-progress", "verify")
                : List.of(mavenExecutable, "-B", "--no-transfer-progress", "--offline", "verify");
        Path home = logFile.getParent().resolve("maven-home");
        Process process = null;
        Thread output = null;
        AtomicReference<Throwable> outputFailure = new AtomicReference<>();
        try {
            Files.createDirectories(home);
            Files.createDirectories(logFile.getParent());
            ProcessBuilder builder = new ProcessBuilder(command)
                    .directory(projectRoot.toFile())
                    .redirectErrorStream(true);
            Map<String, String> inherited = Map.copyOf(builder.environment());
            builder.environment().clear();
            builder.environment().put("JAVA_HOME", javaHome.toString());
            builder.environment().put("HOME", home.toString());
            builder.environment().put("LANG", "C.UTF-8");
            builder.environment().put("LC_ALL", "C.UTF-8");
            builder.environment().put("MAVEN_OPTS",
                    mavenOptions(inherited, home, immutableDependencyCache));
            copyProxy(inherited, builder.environment(), "HTTPS_PROXY");
            copyProxy(inherited, builder.environment(), "https_proxy");
            copyProxy(inherited, builder.environment(), "NO_PROXY");
            copyProxy(inherited, builder.environment(), "no_proxy");
            process = builder.start();
            Process observedProcess = process;
            output = Thread.ofVirtual().start(() -> {
                try {
                    copyBounded(observedProcess.getInputStream(), logFile);
                } catch (Throwable error) {
                    outputFailure.set(error);
                }
            });
            boolean completed = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!completed) {
                process.destroyForcibly();
                output.join(5_000);
                throw rejected("INDEPENDENT_VALIDATION_TIMEOUT",
                        "Independent Maven verification exceeded its execution budget.");
            }
            output.join(5_000);
            if (output.isAlive() || outputFailure.get() != null
                    || !Files.isRegularFile(logFile)
                    || Files.size(logFile) == 0) {
                throw rejected("INDEPENDENT_EVIDENCE_LOG_FAILED",
                        "Independent Maven Evidence log is incomplete.");
            }
            if (process.exitValue() != 0) {
                throw rejected("INDEPENDENT_VALIDATION_FAILED",
                        "Independent Maven verification failed.");
            }
            return command;
        } catch (Rejected error) {
            throw error;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw rejected("INDEPENDENT_VALIDATION_INTERRUPTED",
                    "Independent Maven verification was interrupted.");
        } catch (IOException error) {
            throw rejected("INDEPENDENT_VALIDATOR_UNAVAILABLE",
                    "Independent Maven verification toolchain could not be started.");
        } finally {
            if (process != null && process.isAlive()) process.destroyForcibly();
            if (output != null && output.isAlive()) {
                try {
                    output.join(5_000);
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                }
            }
        }
    }

    private static String mavenOptions(
            Map<String, String> environment,
            Path home,
            Path immutableDependencyCache
    ) {
        String base = "-Djava.awt.headless=true -Duser.timezone=UTC -Duser.home=" + home;
        if (immutableDependencyCache != null) {
            return base + " -Dmaven.repo.local=" + immutableDependencyCache;
        }
        String proxyValue = firstNonBlank(
                environment.get("HTTPS_PROXY"),
                environment.get("https_proxy")
        );
        if (proxyValue == null) return base;
        try {
            URI proxy = URI.create(proxyValue);
            String host = proxy.getHost();
            int port = proxy.getPort() < 0 ? 80 : proxy.getPort();
            if (!"http".equalsIgnoreCase(proxy.getScheme())
                    || host == null
                    || !host.matches("[A-Za-z0-9.-]{1,253}")
                    || port < 1
                    || port > 65535
                    || proxy.getUserInfo() != null
                    || proxy.getQuery() != null
                    || proxy.getFragment() != null
                    || !(proxy.getPath() == null || proxy.getPath().isEmpty()
                    || "/".equals(proxy.getPath()))) {
                throw new IllegalArgumentException("invalid proxy");
            }
            return base
                    + " -Dhttps.proxyHost=" + host
                    + " -Dhttps.proxyPort=" + port
                    + " -Dhttp.proxyHost=" + host
                    + " -Dhttp.proxyPort=" + port
                    + " -Dhttp.nonProxyHosts=localhost|127.*|[::1]"
                    + " -Dhttps.nonProxyHosts=localhost|127.*|[::1]";
        } catch (IllegalArgumentException error) {
            throw rejected("VERIFIER_EGRESS_PROXY_INVALID",
                    "Independent verifier egress proxy configuration is invalid.");
        }
    }

    private static String firstNonBlank(String first, String second) {
        if (first != null && !first.isBlank()) return first;
        if (second != null && !second.isBlank()) return second;
        return null;
    }

    private static Path requireDependencyCache(Path raw) {
        Path path = raw.toAbsolutePath().normalize();
        if (!Files.isDirectory(path, java.nio.file.LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(path)
                || !Files.isDirectory(
                path.resolve("org/apache/maven/plugins/maven-surefire-plugin"),
                java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
            throw new IllegalStateException(
                    "approved immutable verifier Maven dependency cache is unavailable");
        }
        return path;
    }

    private static String requireMaven(String command, Path javaHome) {
        if (command == null || command.isBlank() || command.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("Maven executable is required");
        }
        ProcessBuilder builder = new ProcessBuilder(command, "-version").redirectErrorStream(true);
        builder.environment().put("JAVA_HOME", javaHome.toString());
        try {
            Process process = builder.start();
            String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            if (!process.waitFor(15, TimeUnit.SECONDS)
                    || process.exitValue() != 0
                    || !output.contains("Apache Maven 3.9.11")) {
                process.destroyForcibly();
                throw new IllegalStateException("approved verifier Maven executable must be exactly 3.9.11");
            }
            return command;
        } catch (IOException | InterruptedException error) {
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            throw new IllegalStateException("approved verifier Maven executable could not be verified", error);
        }
    }

    private static void copyBounded(InputStream input, Path logFile) {
        long written = 0;
        byte[] buffer = new byte[32 * 1024];
        try (input;
             OutputStream output = Files.newOutputStream(
                     logFile, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            int count;
            while ((count = input.read(buffer)) >= 0) {
                int allowed = (int) Math.min(count, MAX_LOG_BYTES - written);
                if (allowed > 0) {
                    output.write(redact(buffer, allowed));
                    written += allowed;
                }
                if (written >= MAX_LOG_BYTES) {
                    output.write("\n[ELMOS log truncated at 16 MiB]\n".getBytes(StandardCharsets.UTF_8));
                    while (input.read(buffer) >= 0) {
                        // Drain to avoid blocking the child process; discarded bytes are never evidence.
                    }
                    return;
                }
            }
        } catch (IOException error) {
            throw new IllegalStateException("independent verifier log collection failed", error);
        }
    }

    private static byte[] redact(byte[] source, int count) {
        String value = new String(source, 0, count, StandardCharsets.UTF_8)
                .replaceAll("(?i)(authorization:\\s*)([^\\r\\n]+)", "$1[REDACTED]")
                .replaceAll("(?i)(password|token|secret)=([^\\s&]+)", "$1=[REDACTED]");
        return value.getBytes(StandardCharsets.UTF_8);
    }

    private static void copyProxy(Map<String, String> source, Map<String, String> target, String name) {
        String value = source.get(name);
        if (value != null && !value.isBlank()) target.put(name, value);
    }

    private static Rejected rejected(String code, String message) {
        return new Rejected(code, message);
    }
}
