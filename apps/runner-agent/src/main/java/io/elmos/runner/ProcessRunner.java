package io.elmos.runner;

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
        private static final int MAX_LINE_CHARS = 16 << 10;
        private final Path supervisor;

        public Os() {
            this(configuredSupervisor());
        }

        public Os(Path supervisor) {
            if (supervisor != null && (!supervisor.isAbsolute()
                    || !java.nio.file.Files.isRegularFile(supervisor)
                    || !java.nio.file.Files.isExecutable(supervisor))) {
                throw new IllegalArgumentException("RUNNER_SUPERVISOR_MUST_BE_ABSOLUTE_EXECUTABLE");
            }
            this.supervisor = supervisor;
        }

        private static Path configuredSupervisor() {
            String value = System.getenv("ELMOS_RUNNER_SUPERVISOR");
            return value == null || value.isBlank() ? null : Path.of(value);
        }

        @Override
        public Result run(List<String> command, Path workingDirectory, Map<String, String> environment, long timeoutSeconds) {
            ProcessBuilder builder = builder(command, workingDirectory, environment);
            Process process = null;
            try {
                process = builder.start();
                StringBuffer stdout = new StringBuffer();
                StringBuffer stderr = new StringBuffer();
                Thread outReader = drain(process.getInputStream(), stdout);
                Thread errReader = drain(process.getErrorStream(), stderr);
                boolean finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
                if (!finished) {
                    stop(process);
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
            } finally {
                if (process != null && process.isAlive()) stop(process);
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
                try (InputStreamReader reader = new InputStreamReader(
                        process.getInputStream(), StandardCharsets.UTF_8)) {
                    boundedLines(reader, onLine);
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
                    if (supervisor != null) {
                        process.destroy();
                        return;
                    }
                    // destroy() maps to SIGTERM. Descendants are signalled too so a
                    // shell wrapper cannot leave the real workload running.
                    try {
                        process.descendants().forEach(ProcessHandle::destroy);
                    } catch (RuntimeException ignored) {
                        // Some hardened hosts deny the process-tree query. Always
                        // signal the direct engine process anyway; ContainerRuntime
                        // follows this with engine-level kill/rm, which remains the
                        // authoritative container cleanup path.
                    } finally {
                        process.destroy();
                    }
                }

                @Override
                public void kill() {
                    if (supervisor != null) {
                        stop(process);
                        return;
                    }
                    try {
                        process.descendants().forEach(ProcessHandle::destroyForcibly);
                    } catch (RuntimeException ignored) {
                        // See terminate(): inability to enumerate descendants must
                        // not prevent direct SIGKILL and engine-level cleanup.
                    } finally {
                        process.destroyForcibly();
                    }
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

        private ProcessBuilder builder(List<String> command, Path workingDirectory, Map<String, String> environment) {
            List<String> invocation = new ArrayList<>();
            if (supervisor != null) invocation.addAll(List.of(supervisor.toString(), "--grace=1s", "--"));
            invocation.addAll(command);
            ProcessBuilder builder = new ProcessBuilder(invocation);
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

        private static void stop(Process process) {
            // Snapshot handles before the leader exits and descendants are reparented.
            List<ProcessHandle> descendants;
            try { descendants = process.descendants().toList(); }
            catch (RuntimeException unavailable) { descendants = List.of(); }
            descendants.forEach(ProcessHandle::destroy);
            process.destroy();
            boolean interrupted = Thread.interrupted();
            try {
                if (!process.waitFor(2, TimeUnit.SECONDS)) {
                    process.descendants().forEach(ProcessHandle::destroyForcibly);
                    process.destroyForcibly();
                }
            } catch (InterruptedException ex) {
                interrupted = true;
                process.destroyForcibly();
            } finally {
                descendants.stream().filter(ProcessHandle::isAlive).forEach(ProcessHandle::destroyForcibly);
                if (interrupted) Thread.currentThread().interrupt();
            }
        }

        private static void boundedLines(InputStreamReader reader, Consumer<String> onLine) throws IOException {
            char[] buffer = new char[4096];
            StringBuilder line = new StringBuilder();
            boolean oversized = false;
            int count;
            while ((count = reader.read(buffer)) != -1) {
                for (int i = 0; i < count; i++) {
                    char ch = buffer[i];
                    if (ch == '\n') {
                        // Never turn an oversized structured progress event into a valid prefix.
                        onLine.accept(oversized ? "[elmos: oversized log line omitted]" : line.toString());
                        line.setLength(0);
                        oversized = false;
                    } else if (!oversized) {
                        if (line.length() == MAX_LINE_CHARS) oversized = true;
                        else line.append(ch);
                    }
                }
            }
            if (oversized || !line.isEmpty()) {
                onLine.accept(oversized ? "[elmos: oversized log line omitted]" : line.toString());
            }
        }

        private static Thread drain(java.io.InputStream stream, StringBuffer sink) {
            return Thread.ofVirtual().start(() -> {
                try (InputStreamReader reader = new InputStreamReader(stream, StandardCharsets.UTF_8)) {
                    char[] buffer = new char[4096];
                    int count;
                    while ((count = reader.read(buffer)) != -1) {
                        int retained = Math.min(count, MAX_CAPTURED_BYTES - sink.length());
                        if (retained > 0) sink.append(buffer, 0, retained);
                    }
                } catch (IOException ignored) {
                    // Closed stream on exit.
                }
            });
        }
    }
}
