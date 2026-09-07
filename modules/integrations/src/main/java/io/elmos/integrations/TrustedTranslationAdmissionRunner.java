package io.elmos.integrations;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.LockSupport;

/**
 * Runs the fixed, repository-owned translation admission command.
 *
 * <p>The control plane supplies only two validated language identifiers. It
 * cannot supply an executable, argument list, environment variable, working
 * directory, or shell fragment through this boundary. The process-tree cleanup
 * is a best-effort Java fallback for this trusted command; customer commands
 * still require the Runner's OS supervisor or container boundary.</p>
 */
public final class TrustedTranslationAdmissionRunner {
    static final int MAXIMUM_OUTPUT_BYTES = 64 * 1024;
    static final int MAXIMUM_CONCURRENT_STARTS = 2;
    private static final Duration DEADLINE = Duration.ofSeconds(30);
    private static final Duration EXIT_AFTER_OUTPUT = Duration.ofSeconds(5);
    private static final Duration TERMINATION_GRACE = Duration.ofSeconds(1);
    private static final ExecutorService LAUNCH_TASKS = launchTasks();

    private final ProcessStarter starter;
    private final Duration deadline;
    private final Duration exitAfterOutput;
    private final Duration terminationGrace;

    public TrustedTranslationAdmissionRunner() {
        this(TrustedTranslationAdmissionRunner::startProcess,
                DEADLINE, EXIT_AFTER_OUTPUT, TERMINATION_GRACE);
    }

    TrustedTranslationAdmissionRunner(
            ProcessStarter starter,
            Duration deadline,
            Duration exitAfterOutput,
            Duration terminationGrace
    ) {
        this.starter = java.util.Objects.requireNonNull(starter, "starter");
        this.deadline = requirePositive(deadline, "deadline");
        this.exitAfterOutput = requirePositive(exitAfterOutput, "exitAfterOutput");
        this.terminationGrace = requirePositive(terminationGrace, "terminationGrace");
    }

    public byte[] run(Path nodeExecutable, Path repositoryRoot, String source, String target) {
        validateIdentifier(source);
        validateIdentifier(target);
        Path root = trustedDirectory(repositoryRoot);
        if (nodeExecutable == null || !nodeExecutable.isAbsolute()
                || !Files.isRegularFile(nodeExecutable) || !Files.isExecutable(nodeExecutable)) {
            throw failure("TRANSLATION_ADMISSION_RUNTIME_REQUIRED");
        }
        List<String> command = List.of(
                nodeExecutable.toString(), "--no-warnings", "--loader",
                root.resolve("apps/translation-runtime-runner/ts-loader.mjs").toString(),
                root.resolve("apps/translation-runtime-runner/admission.mjs").toString(),
                source, target);
        Map<String, String> environment = Map.of(
                "ELMOS_REPOSITORY_ROOT", root.toString(),
                "NODE_ENV", "production");

        Process process = null;
        ExecutorService tasks = null;
        Future<Process> processStart = null;
        Future<byte[]> output = null;
        Thread treeObserver = null;
        ProcessTreeTracker processTree = null;
        AtomicBoolean observeTree = new AtomicBoolean();
        AtomicBoolean abandonStart = new AtomicBoolean();
        AtomicReference<Process> startedProcess = new AtomicReference<>();
        boolean successful = false;
        boolean restoreInterrupt = false;
        long absoluteDeadline = System.nanoTime() + deadline.toNanos();
        try {
            tasks = Executors.newThreadPerTaskExecutor(
                    Thread.ofVirtual().name("translation-admission-task-", 0).factory());
            processStart = LAUNCH_TASKS.submit(() -> {
                Process started = starter.start(command, root, environment);
                if (started == null) {
                    throw new IOException("translation admission returned no process");
                }
                startedProcess.set(started);
                if (abandonStart.get()) {
                    terminateLateStart(started);
                }
                return started;
            });
            try {
                process = processStart.get(
                        remainingNanos(absoluteDeadline), TimeUnit.NANOSECONDS);
            } catch (InterruptedException | TimeoutException error) {
                abandonStart.set(true);
                processStart.cancel(true);
                terminateLateStart(startedProcess.get());
                throw error;
            }
            processTree = new ProcessTreeTracker();
            process.getOutputStream().close();
            Process child = process;
            ProcessTreeTracker trackedTree = processTree;
            observeTree.set(true);
            treeObserver = Thread.ofVirtual()
                    .name("translation-admission-tree-observer")
                    .start(() -> {
                        while (true) {
                            trackedTree.capture(child);
                            if (!observeTree.get() || !child.isAlive()) {
                                return;
                            }
                            LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(10));
                        }
                    });
            output = tasks.submit(() -> {
                try (InputStream stream = child.getInputStream()) {
                    return stream.readNBytes(MAXIMUM_OUTPUT_BYTES + 1);
                }
            });

            byte[] bytes = output.get(remainingNanos(absoluteDeadline), TimeUnit.NANOSECONDS);
            if (bytes.length > MAXIMUM_OUTPUT_BYTES) {
                throw failure("TRANSLATION_ROUTE_ADMISSION_OUTPUT_LIMIT");
            }
            long exitWait = Math.min(exitAfterOutput.toNanos(), remainingNanos(absoluteDeadline));
            if (exitWait <= 0 || !process.waitFor(exitWait, TimeUnit.NANOSECONDS)
                    || process.exitValue() != 0) {
                throw failure("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE");
            }
            successful = true;
            return bytes;
        } catch (AdmissionFailure error) {
            throw error;
        } catch (InterruptedException error) {
            restoreInterrupt = true;
            throw failure("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE");
        } catch (TimeoutException | ExecutionException | IOException | RuntimeException error) {
            throw failure("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE");
        } finally {
            long cleanupDeadline = System.nanoTime() + terminationGrace.toNanos();
            if (process == null) {
                abandonStart.set(true);
                if (processStart != null) {
                    processStart.cancel(true);
                }
                terminateLateStart(startedProcess.get());
            }
            observeTree.set(false);
            boolean observerStopped = stopTreeObserver(treeObserver, cleanupDeadline, true);
            if (output != null) {
                output.cancel(true);
            }
            boolean treeCleaned = process == null
                    || stopTreeAndReap(process, processTree, cleanupDeadline);
            boolean cleaned = observerStopped && treeCleaned;
            if (tasks != null) {
                tasks.shutdownNow();
                try {
                    long remaining = cleanupDeadline - System.nanoTime();
                    if (remaining <= 0
                            || !tasks.awaitTermination(remaining, TimeUnit.NANOSECONDS)) {
                        cleaned = false;
                    }
                } catch (InterruptedException error) {
                    restoreInterrupt = true;
                    cleaned = false;
                }
            }
            if (restoreInterrupt) {
                Thread.currentThread().interrupt();
            }
            if (successful && !cleaned) {
                throw failure("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE");
            }
        }
    }

    /** Bounds a tree observation without ever waiting past the shared cleanup deadline. */
    private static boolean stopTreeObserver(
            Thread observer,
            long cleanupDeadline,
            boolean interruptFirst
    ) {
        if (observer == null) {
            return true;
        }
        boolean restoreInterrupt = Thread.interrupted();
        if (interruptFirst) {
            observer.interrupt();
        }
        try {
            while (observer.isAlive()) {
                long remaining = cleanupDeadline - System.nanoTime();
                if (remaining <= 0) {
                    observer.interrupt();
                    return false;
                }
                long millis = TimeUnit.NANOSECONDS.toMillis(remaining);
                int nanos = (int) (remaining - TimeUnit.MILLISECONDS.toNanos(millis));
                try {
                    observer.join(millis, nanos);
                } catch (InterruptedException error) {
                    restoreInterrupt = true;
                    observer.interrupt();
                }
            }
            return true;
        } finally {
            if (restoreInterrupt) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private static Process startProcess(
            List<String> command,
            Path workingDirectory,
            Map<String, String> environment
    ) throws IOException {
        ProcessBuilder builder = new ProcessBuilder(command)
                .directory(workingDirectory.toFile())
                .redirectErrorStream(true);
        builder.environment().clear();
        builder.environment().putAll(environment);
        return builder.start();
    }

    /**
     * Bounds starts that ignore interruption without queueing more work behind them.
     *
     * <p>A cancelled start keeps its worker until the starter actually returns, so
     * repeated timed-out requests cannot accumulate an unbounded number of stuck
     * launch tasks. Daemon workers belong to the process lifecycle rather than to
     * an individual request.</p>
     */
    private static ExecutorService launchTasks() {
        var executor = new ThreadPoolExecutor(
                MAXIMUM_CONCURRENT_STARTS,
                MAXIMUM_CONCURRENT_STARTS,
                30,
                TimeUnit.SECONDS,
                new SynchronousQueue<>(),
                Thread.ofPlatform()
                        .daemon(true)
                        .name("translation-admission-launch-", 0)
                        .factory(),
                new ThreadPoolExecutor.AbortPolicy());
        executor.allowCoreThreadTimeOut(true);
        return executor;
    }

    /** Owns a process that appeared after its caller had already abandoned start. */
    private static void terminateLateStart(Process process) {
        if (process == null) {
            return;
        }
        destroy(process);
        closeStreams(process);
        try {
            if (process.isAlive()) {
                process.destroyForcibly();
            }
        } catch (RuntimeException ignored) {
            // The start task has no authority to wait beyond the caller's deadline.
        }
    }

    /** Stops descendants before their leader, closes inherited pipes, and reaps the leader. */
    static boolean stopTreeAndReap(Process process, Duration grace) {
        ProcessTreeTracker processTree = new ProcessTreeTracker();
        long cleanupDeadline = System.nanoTime() + grace.toNanos();
        Thread capture = Thread.ofVirtual()
                .name("translation-admission-tree-snapshot")
                .start(() -> processTree.capture(process));
        boolean captureStopped = stopTreeObserver(capture, cleanupDeadline, false);
        boolean treeCleaned = stopTreeAndReap(process, processTree, cleanupDeadline);
        return captureStopped && treeCleaned;
    }

    private static boolean stopTreeAndReap(
            Process process,
            ProcessTreeTracker processTree,
            long cleanupDeadline
    ) {
        boolean restoreInterrupt = Thread.interrupted();
        List<ProcessHandle> descendants = processTree.handles();
        try {
            reverse(descendants).forEach(TrustedTranslationAdmissionRunner::destroy);
            destroy(process);
            closeStreams(process);

            long remainingForSoftWait = cleanupDeadline - System.nanoTime();
            if (remainingForSoftWait > 0) {
                long softWait = Math.max(1, remainingForSoftWait / 2);
                try {
                    // Calling waitFor even after isAlive() turns false makes the
                    // reaping boundary explicit for both real and fake processes.
                    process.waitFor(softWait, TimeUnit.NANOSECONDS);
                } catch (InterruptedException error) {
                    restoreInterrupt = true;
                }
            }

            List<ProcessHandle> remaining = processTree.handles();
            reverse(remaining).stream().filter(TrustedTranslationAdmissionRunner::alive)
                    .forEach(TrustedTranslationAdmissionRunner::destroyForcibly);
            if (process.isAlive()) {
                process.destroyForcibly();
            }

            while ((process.isAlive()
                    || remaining.stream().anyMatch(TrustedTranslationAdmissionRunner::alive))
                    && System.nanoTime() < cleanupDeadline) {
                remaining.stream().filter(TrustedTranslationAdmissionRunner::alive)
                        .forEach(TrustedTranslationAdmissionRunner::destroyForcibly);
                if (process.isAlive()) {
                    process.destroyForcibly();
                }
                long wait = Math.min(
                        TimeUnit.MILLISECONDS.toNanos(10),
                        Math.max(1, cleanupDeadline - System.nanoTime()));
                try {
                    process.waitFor(wait, TimeUnit.NANOSECONDS);
                } catch (InterruptedException error) {
                    restoreInterrupt = true;
                }
            }
            return processTree.enumerationAvailable()
                    && processTree.enumerationCompleted()
                    && !process.isAlive()
                    && remaining.stream().noneMatch(TrustedTranslationAdmissionRunner::alive);
        } finally {
            if (restoreInterrupt) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private static List<ProcessHandle> reverse(List<ProcessHandle> handles) {
        List<ProcessHandle> reversed = new ArrayList<>(handles);
        Collections.reverse(reversed);
        return reversed;
    }

    private static void destroy(Process process) {
        try {
            if (process.isAlive()) {
                process.destroy();
            }
        } catch (RuntimeException ignored) {
            // The force/reap phase still runs.
        }
    }

    private static void destroy(ProcessHandle process) {
        try {
            if (process.isAlive()) {
                process.destroy();
            }
        } catch (RuntimeException ignored) {
            // The force phase still runs.
        }
    }

    private static void destroyForcibly(ProcessHandle process) {
        try {
            process.destroyForcibly();
        } catch (RuntimeException ignored) {
            // The final liveness check makes cleanup failure fail closed.
        }
    }

    private static boolean alive(ProcessHandle process) {
        try {
            return process.isAlive();
        } catch (RuntimeException unavailable) {
            return true;
        }
    }

    private static final class ProcessTreeTracker {
        private final Map<Long, ProcessHandle> observed = new ConcurrentHashMap<>();
        private final AtomicBoolean enumerationAvailable = new AtomicBoolean(true);
        private final AtomicBoolean enumerationCompleted = new AtomicBoolean();

        void capture(Process process) {
            try (var descendants = process.descendants()) {
                descendants.forEach(handle -> observed.putIfAbsent(handle.pid(), handle));
                enumerationCompleted.set(true);
            } catch (RuntimeException unavailable) {
                enumerationAvailable.set(false);
            }
        }

        List<ProcessHandle> handles() {
            return observed.values().stream()
                    .sorted(java.util.Comparator.comparingLong(ProcessHandle::pid))
                    .toList();
        }

        boolean enumerationAvailable() {
            return enumerationAvailable.get();
        }

        boolean enumerationCompleted() {
            return enumerationCompleted.get();
        }
    }

    private static void closeStreams(Process process) {
        try {
            process.getOutputStream().close();
        } catch (IOException ignored) {
            // Continue closing process-owned descriptors.
        }
        try {
            process.getInputStream().close();
        } catch (IOException ignored) {
            // Continue closing process-owned descriptors.
        }
        try {
            process.getErrorStream().close();
        } catch (IOException ignored) {
            // Cleanup liveness, not stream close, determines success.
        }
    }

    private static long remainingNanos(long absoluteDeadline) throws TimeoutException {
        long remaining = absoluteDeadline - System.nanoTime();
        if (remaining <= 0) {
            throw new TimeoutException("translation admission deadline expired");
        }
        return remaining;
    }

    private static Duration requirePositive(Duration value, String name) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(name + " must be positive");
        }
        return value;
    }

    private static Path trustedDirectory(Path value) {
        try {
            if (value == null || !value.isAbsolute() || value.getParent() == null) {
                throw failure("TRANSLATION_ADMISSION_RUNTIME_REQUIRED");
            }
            Path normalized = value.normalize();
            if (!normalized.toRealPath().equals(normalized)) {
                throw failure("TRANSLATION_ADMISSION_RUNTIME_REQUIRED");
            }
            return normalized;
        } catch (AdmissionFailure error) {
            throw error;
        } catch (IOException error) {
            throw failure("TRANSLATION_ADMISSION_RUNTIME_REQUIRED");
        }
    }

    private static void validateIdentifier(String value) {
        if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")) {
            throw failure("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE");
        }
    }

    private static AdmissionFailure failure(String code) {
        return new AdmissionFailure(code);
    }

    @FunctionalInterface
    interface ProcessStarter {
        Process start(List<String> command, Path workingDirectory, Map<String, String> environment)
                throws IOException;
    }

    public static final class AdmissionFailure extends RuntimeException {
        private final String code;

        AdmissionFailure(String code) {
            super(code);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }
}
