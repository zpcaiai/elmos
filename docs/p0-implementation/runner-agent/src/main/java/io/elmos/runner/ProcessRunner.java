package io.elmos.runner;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/**
 * Thin, testable wrapper over {@link ProcessBuilder}.
 *
 * <p>Extracted as an interface so the self-test can substitute a fake container
 * engine. Everything the agent does to the host goes through here, which makes
 * "what can this component execute" answerable by reading one file.</p>
 */
public interface ProcessRunner {

    record Result(int exitCode, String stdout, String stderr, boolean timedOut) {
        public boolean ok() {
            return exitCode == 0 && !timedOut;
        }
    }

    /** Runs to completion, capturing output, bounded by {@code timeoutSeconds}. */
    Result run(List<String> command, Path workingDirectory, Map<String, String> environment, long timeoutSeconds);

    /**
     * Starts a long-running process, streaming stdout lines to {@code onLine}.
     * The returned handle can be signalled and awaited.
     */
    Handle start(List<String> command, Path workingDirectory, Map<String, String> environment, Consumer<String> onLine);

    interface Handle {
        boolean isAlive();

        /** Sends SIGTERM to the process group. */
        void terminate();

        /** Sends SIGKILL to the process group. */
        void kill();

        /** Waits up to the timeout. Returns the exit code, or null on timeout. */
        Integer waitFor(long timeout, TimeUnit unit) throws InterruptedException;
    }

    default String captureOrEmpty(String... command) {
        try {
            Result result = run(List.of(command), null, Map.of(), 10);
            return result.ok() ? result.stdout() : "";
        } catch (RuntimeException ex) {
            return "";
        }
    }

    /** Default implementation backed by the operating system. */
    final class Os implements ProcessRunner {

        private static final int MAX_CAPTURED_BYTES = 1 << 20;

        @Override
        public Result run(List<String> command, Path workingDirectory, Map<String, String> environment, long timeoutSeconds) {
            ProcessBuilder builder = builder(command, workingDirectory, environment);
            try {
                Process process = builder.start();
                StringBuilder stdout = new StringBuilder();
                StringBuilder stderr = new StringBuilder();
                Thread outReader = drain(process.getInputStream(), stdout);
                Thread errReader = drain(process.getErrorStream(), stderr);
                boolean finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
                if (!finished) {
                    process.destroyForcibly();
                    outReader.join(1000);
                    errReader.join(1000);
                    return new Result(-1, stdout.toString(), stderr.toString(), true);
                }
                outReader.join(2000);
                errReader.join(2000);
                return new Result(process.exitValue(), stdout.toString(), stderr.toString(), false);
            } catch (IOException ex) {
                return new Result(-1, "", "spawn failed", false);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return new Result(-1, "", "interrupted", false);
            }
        }

        @Override
        public Handle start(List<String> command, Path workingDirectory, Map<String, String> environment, Consumer<String> onLine) {
            ProcessBuilder builder = builder(command, workingDirectory, environment);
            builder.redirectErrorStream(true);
            final Process process;
            try {
                process = builder.start();
            } catch (IOException ex) {
                throw new IllegalStateException("CONTAINER_SPAWN_FAILED");
            }
            Thread pump = Thread.ofVirtual().start(() -> {
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        onLine.accept(line);
                    }
                } catch (IOException ignored) {
                    // The stream closes when the process exits; nothing to report.
                }
            });
            return new Handle() {
                @Override
                public boolean isAlive() {
                    return process.isAlive();
                }

                @Override
                public void terminate() {
                    // destroy() maps to SIGTERM. Descendants are signalled too so a
                    // shell wrapper cannot leave the real workload running.
                    process.descendants().forEach(ProcessHandle::destroy);
                    process.destroy();
                }

                @Override
                public void kill() {
                    process.descendants().forEach(ProcessHandle::destroyForcibly);
                    process.destroyForcibly();
                }

                @Override
                public Integer waitFor(long timeout, TimeUnit unit) throws InterruptedException {
                    if (process.waitFor(timeout, unit)) {
                        pump.join(2000);
                        return process.exitValue();
                    }
                    return null;
                }
            };
        }

        private static ProcessBuilder builder(List<String> command, Path workingDirectory, Map<String, String> environment) {
            ProcessBuilder builder = new ProcessBuilder(new ArrayList<>(command));
            if (workingDirectory != null) {
                builder.directory(workingDirectory.toFile());
            }
            // Start from an empty environment and add back only what was asked for.
            // Inheriting the agent's environment would hand the workload the
            // enrolment token.
            builder.environment().clear();
            builder.environment().putAll(environment);
            return builder;
        }

        private static Thread drain(java.io.InputStream stream, StringBuilder sink) {
            return Thread.ofVirtual().start(() -> {
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        if (sink.length() < MAX_CAPTURED_BYTES) {
                            sink.append(line).append('\n');
                        }
                    }
                } catch (IOException ignored) {
                    // Closed stream on exit.
                }
            });
        }
    }
}
