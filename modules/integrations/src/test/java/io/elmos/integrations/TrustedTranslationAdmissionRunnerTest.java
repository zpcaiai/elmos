package io.elmos.integrations;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;

class TrustedTranslationAdmissionRunnerTest {
    @TempDir Path repositoryRoot;
    private Path node;

    @BeforeEach void executableFixture() throws IOException {
        repositoryRoot = repositoryRoot.toRealPath();
        node = Files.createFile(repositoryRoot.resolve("node"));
        assertTrue(node.toFile().setExecutable(true, true));
    }

    @Test void launchesOnlyTheFixedCommandWithTheScrubbedEnvironment() {
        var invocation = new ArrayList<Object>();
        byte[] expected = "admitted".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        var runner = runner((command, workingDirectory, environment) -> {
            invocation.add(command);
            invocation.add(workingDirectory);
            invocation.add(environment);
            return FakeProcess.exited(expected, 0);
        });

        assertArrayEquals(expected, runner.run(node, repositoryRoot, "python", "typescript"));
        assertEquals(List.of(
                node.toString(), "--no-warnings", "--loader",
                repositoryRoot.resolve("apps/translation-runtime-runner/ts-loader.mjs").toString(),
                repositoryRoot.resolve("apps/translation-runtime-runner/admission.mjs").toString(),
                "python", "typescript"), invocation.get(0));
        assertEquals(repositoryRoot, invocation.get(1));
        assertEquals(Map.of(
                "ELMOS_REPOSITORY_ROOT", repositoryRoot.toString(),
                "NODE_ENV", "production"), invocation.get(2));
    }

    @Test void acceptsTheExactOutputLimit() {
        byte[] exact = new byte[TrustedTranslationAdmissionRunner.MAXIMUM_OUTPUT_BYTES];
        var runner = runner((command, root, environment) -> FakeProcess.exited(exact, 0));
        assertEquals(exact.length, runner.run(node, repositoryRoot, "java", "go").length);
    }

    @Test void rejectsOneBytePastTheOutputLimitAndReapsTheProcess() {
        byte[] oversized = new byte[TrustedTranslationAdmissionRunner.MAXIMUM_OUTPUT_BYTES + 1];
        var process = FakeProcess.running(new ByteArrayInputStream(oversized));
        var error = assertThrows(TrustedTranslationAdmissionRunner.AdmissionFailure.class,
                () -> runner((command, root, environment) -> process)
                        .run(node, repositoryRoot, "java", "rust"));
        assertEquals("TRANSLATION_ROUTE_ADMISSION_OUTPUT_LIMIT", error.code());
        assertFalse(process.isAlive());
        assertTrue(process.destroyed);
        assertTrue(process.waited);
    }

    @Test void deadlineClosesBlockingOutputAndReapsTheProcess() {
        var blocking = new BlockingInputStream();
        var process = FakeProcess.running(blocking);
        var error = assertThrows(TrustedTranslationAdmissionRunner.AdmissionFailure.class,
                () -> runner((command, root, environment) -> process, Duration.ofMillis(100))
                        .run(node, repositoryRoot, "python", "go"));
        assertEquals("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE", error.code());
        assertTrue(blocking.closed);
        assertFalse(process.isAlive());
        assertTrue(process.waited);
    }

    @Test void invalidIdentifierAndRuntimeFailBeforeSpawn() throws IOException {
        var starts = new AtomicInteger();
        var runner = runner((command, root, environment) -> {
            starts.incrementAndGet();
            return FakeProcess.exited(new byte[0], 0);
        });
        assertEquals("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE",
                assertThrows(TrustedTranslationAdmissionRunner.AdmissionFailure.class,
                        () -> runner.run(node, repositoryRoot, "../python", "go")).code());
        assertEquals("TRANSLATION_ADMISSION_RUNTIME_REQUIRED",
                assertThrows(TrustedTranslationAdmissionRunner.AdmissionFailure.class,
                        () -> runner.run(repositoryRoot.resolve("missing"), repositoryRoot, "python", "go")).code());
        assertEquals(0, starts.get());
    }

    @Test void spawnAndNonzeroFailuresRemainFailClosed() {
        assertEquals("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE",
                assertThrows(TrustedTranslationAdmissionRunner.AdmissionFailure.class,
                        () -> runner((command, root, environment) -> { throw new IOException("spawn"); })
                                .run(node, repositoryRoot, "python", "go")).code());
        assertEquals("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE",
                assertThrows(TrustedTranslationAdmissionRunner.AdmissionFailure.class,
                        () -> runner((command, root, environment) -> FakeProcess.exited("no".getBytes(), 9))
                                .run(node, repositoryRoot, "python", "go")).code());
    }

    @Test void interruptionIsRestoredAfterCleanup() throws InterruptedException {
        var process = FakeProcess.running(new BlockingInputStream());
        var startEntered = new CountDownLatch(1);
        var failure = new AtomicReference<TrustedTranslationAdmissionRunner.AdmissionFailure>();
        Thread caller = Thread.ofVirtual().start(() -> {
            try {
                runner((command, root, environment) -> {
                    startEntered.countDown();
                    return process;
                }).run(node, repositoryRoot, "python", "go");
            } catch (TrustedTranslationAdmissionRunner.AdmissionFailure error) {
                failure.set(error);
            }
        });

        assertTrue(startEntered.await(1, TimeUnit.SECONDS));
        caller.interrupt();
        caller.join(Duration.ofSeconds(2));

        assertFalse(caller.isAlive());
        assertNotNull(failure.get());
        assertEquals("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE", failure.get().code());
        assertTrue(caller.isInterrupted());
        assertFalse(process.isAlive());
    }

    @Test void cleanupStopsDescendantsBeforeTheirLeader() {
        var events = new ArrayList<String>();
        var first = new FakeHandle(101, "first", events);
        var second = new FakeHandle(102, "second", events);
        var process = FakeProcess.running(new ByteArrayInputStream(new byte[0]));
        process.events = events;
        process.descendants = List.of(first, second);

        assertTrue(TrustedTranslationAdmissionRunner.stopTreeAndReap(
                process, Duration.ofMillis(50)));
        assertEquals(List.of("term:second", "term:first", "term:leader"), events);
        assertTrue(process.waited);
    }

    @Test void cleanupFailureCannotBecomeSuccessfulAdmission() {
        var process = FakeProcess.exited(
                "admitted".getBytes(java.nio.charset.StandardCharsets.UTF_8), 0);
        process.descendantEnumerationFailure = true;
        var error = assertThrows(TrustedTranslationAdmissionRunner.AdmissionFailure.class,
                () -> runner((command, root, environment) -> process)
                        .run(node, repositoryRoot, "python", "go"));
        assertEquals("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE", error.code());
    }

    @Test void cleanupWaitsForInFlightTreeObservationBeforeTakingItsSnapshot()
            throws InterruptedException {
        byte[] expected = "admitted".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        var observerEntered = new CountDownLatch(1);
        var observerInterrupted = new CountDownLatch(1);
        var releaseObserver = new CountDownLatch(1);
        var events = new ArrayList<String>();
        var lateDescendant = new FakeHandle(201, "late", events);
        var process = new FakeProcess(new AwaitingInputStream(observerEntered, expected), 0, true);
        process.exitOnTimedWait = true;
        process.events = events;
        process.descendants = List.of(lateDescendant);
        process.delayedObserverEnumeration = new DelayedEnumeration(
                1, observerEntered, observerInterrupted, releaseObserver);

        Thread releaser = Thread.ofVirtual().start(() -> {
            try {
                observerInterrupted.await(1, TimeUnit.SECONDS);
                Thread.sleep(Duration.ofMillis(100));
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            } finally {
                releaseObserver.countDown();
            }
        });
        try {
            assertArrayEquals(expected, runner((command, root, environment) -> process)
                    .run(node, repositoryRoot, "python", "go"));
        } finally {
            releaseObserver.countDown();
            releaser.join();
        }

        assertEquals(0, observerInterrupted.getCount());
        assertFalse(lateDescendant.isAlive());
        assertEquals(List.of("term:late"), events);
    }

    @Test void blockingTreeEnumerationCannotHoldTheCallerPastTheCleanupBudget() {
        var observerEntered = new CountDownLatch(1);
        var observerInterrupted = new CountDownLatch(1);
        var releaseObserver = new CountDownLatch(1);
        var process = FakeProcess.exited("admitted".getBytes(), 0);
        process.delayedObserverEnumeration = new DelayedEnumeration(
                1, observerEntered, observerInterrupted, releaseObserver);

        try {
            assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
                var error = assertThrows(TrustedTranslationAdmissionRunner.AdmissionFailure.class,
                        () -> runner(
                                (command, root, environment) -> process,
                                Duration.ofSeconds(1),
                                Duration.ofMillis(50))
                                .run(node, repositoryRoot, "python", "go"));
                assertEquals("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE", error.code());
            });
            assertEquals(0, observerEntered.getCount());
            assertEquals(0, observerInterrupted.getCount());
        } finally {
            releaseObserver.countDown();
        }
    }

    @Test void blockingStartIsBoundedAndItsLateProcessIsTerminated() {
        var startEntered = new CountDownLatch(1);
        var startInterrupted = new CountDownLatch(1);
        var releaseStart = new CountDownLatch(1);
        var lateProcess = new AtomicReference<FakeProcess>();

        var runner = runner((command, root, environment) -> {
            startEntered.countDown();
            boolean restoreInterrupt = false;
            while (true) {
                try {
                    releaseStart.await();
                    break;
                } catch (InterruptedException error) {
                    restoreInterrupt = true;
                    startInterrupted.countDown();
                }
            }
            var process = FakeProcess.running(new ByteArrayInputStream(new byte[0]));
            lateProcess.set(process);
            if (restoreInterrupt) {
                Thread.currentThread().interrupt();
            }
            return process;
        }, Duration.ofMillis(250), Duration.ofMillis(50));

        try {
            assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
                var error = assertThrows(
                        TrustedTranslationAdmissionRunner.AdmissionFailure.class,
                        () -> runner.run(node, repositoryRoot, "python", "go"));
                assertEquals("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE", error.code());
            });
            assertEquals(0, startEntered.getCount());
        } finally {
            releaseStart.countDown();
        }

        assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
            while (lateProcess.get() == null || lateProcess.get().isAlive()) {
                Thread.sleep(Duration.ofMillis(10));
            }
        });
        assertEquals(0, startInterrupted.getCount());
        assertTrue(lateProcess.get().destroyed);
    }

    @Test void launchBulkheadFailsFastInsteadOfAccumulatingUninterruptibleStarts()
            throws InterruptedException {
        var startsEntered = new CountDownLatch(
                TrustedTranslationAdmissionRunner.MAXIMUM_CONCURRENT_STARTS);
        var releaseStarts = new CountDownLatch(1);
        var callerFailures = new ArrayList<AtomicReference<Throwable>>();
        var callers = new ArrayList<Thread>();

        for (int index = 0;
                index < TrustedTranslationAdmissionRunner.MAXIMUM_CONCURRENT_STARTS;
                index++) {
            var failure = new AtomicReference<Throwable>();
            callerFailures.add(failure);
            callers.add(Thread.ofVirtual().start(() -> {
                try {
                    runner((command, root, environment) -> {
                        startsEntered.countDown();
                        boolean restoreInterrupt = false;
                        while (true) {
                            try {
                                releaseStarts.await();
                                break;
                            } catch (InterruptedException error) {
                                restoreInterrupt = true;
                            }
                        }
                        if (restoreInterrupt) {
                            Thread.currentThread().interrupt();
                        }
                        return FakeProcess.exited("admitted".getBytes(), 0);
                    }, Duration.ofSeconds(5), Duration.ofMillis(100))
                            .run(node, repositoryRoot, "python", "go");
                } catch (Throwable error) {
                    failure.set(error);
                }
            }));
        }

        try {
            assertTrue(startsEntered.await(2, TimeUnit.SECONDS));
            var rejectedStarts = new AtomicInteger();
            assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
                var error = assertThrows(
                        TrustedTranslationAdmissionRunner.AdmissionFailure.class,
                        () -> runner((command, root, environment) -> {
                            rejectedStarts.incrementAndGet();
                            return FakeProcess.exited(new byte[0], 0);
                        }, Duration.ofSeconds(1), Duration.ofMillis(50))
                                .run(node, repositoryRoot, "java", "rust"));
                assertEquals("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE", error.code());
            });
            assertEquals(0, rejectedStarts.get());
        } finally {
            releaseStarts.countDown();
            for (Thread caller : callers) {
                caller.join(Duration.ofSeconds(2));
            }
        }

        assertTrue(callers.stream().noneMatch(Thread::isAlive));
        assertTrue(callerFailures.stream().allMatch(failure -> failure.get() == null));
    }

    @Test void cleanupDeadlineFailsClosedWhenLeaderCannotBeReaped() {
        var process = FakeProcess.running(new ByteArrayInputStream(new byte[0]));
        process.unkillable = true;
        assertFalse(TrustedTranslationAdmissionRunner.stopTreeAndReap(
                process, Duration.ofMillis(40)));
        assertTrue(process.isAlive());
        process.unkillable = false;
        process.destroyForcibly();
    }

    private static TrustedTranslationAdmissionRunner runner(
            TrustedTranslationAdmissionRunner.ProcessStarter starter
    ) {
        return runner(starter, Duration.ofSeconds(10));
    }

    private static TrustedTranslationAdmissionRunner runner(
            TrustedTranslationAdmissionRunner.ProcessStarter starter,
            Duration deadline
    ) {
        return runner(starter, deadline, Duration.ofSeconds(2));
    }

    private static TrustedTranslationAdmissionRunner runner(
            TrustedTranslationAdmissionRunner.ProcessStarter starter,
            Duration deadline,
            Duration terminationGrace
    ) {
        return new TrustedTranslationAdmissionRunner(
                starter, deadline, Duration.ofSeconds(2), terminationGrace);
    }

    private static final class BlockingInputStream extends InputStream {
        private boolean closed;

        @Override public synchronized int read() throws IOException {
            while (!closed) {
                try {
                    wait();
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw new IOException("interrupted", error);
                }
            }
            return -1;
        }

        @Override public synchronized void close() {
            closed = true;
            notifyAll();
        }
    }

    private static final class AwaitingInputStream extends InputStream {
        private final CountDownLatch ready;
        private final ByteArrayInputStream delegate;

        private AwaitingInputStream(CountDownLatch ready, byte[] output) {
            this.ready = ready;
            this.delegate = new ByteArrayInputStream(output);
        }

        @Override public int read() throws IOException {
            awaitReady();
            return delegate.read();
        }

        @Override public int read(byte[] bytes, int offset, int length) throws IOException {
            awaitReady();
            return delegate.read(bytes, offset, length);
        }

        private void awaitReady() throws IOException {
            try {
                if (!ready.await(2, TimeUnit.SECONDS)) {
                    throw new IOException("tree observer did not start");
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new IOException("interrupted", error);
            }
        }
    }

    private record DelayedEnumeration(
            int ordinal,
            CountDownLatch entered,
            CountDownLatch interrupted,
            CountDownLatch release
    ) {}

    private static final class FakeProcess extends Process {
        private final InputStream output;
        private final int exitCode;
        private boolean alive;
        private boolean destroyed;
        private boolean waited;
        private boolean unkillable;
        private boolean exitOnTimedWait;
        private boolean descendantEnumerationFailure;
        private DelayedEnumeration delayedObserverEnumeration;
        private final AtomicInteger descendantEnumerations = new AtomicInteger();
        private List<ProcessHandle> descendants = List.of();
        private List<String> events = new ArrayList<>();

        private FakeProcess(InputStream output, int exitCode, boolean alive) {
            this.output = output;
            this.exitCode = exitCode;
            this.alive = alive;
        }

        static FakeProcess exited(byte[] output, int exitCode) {
            return new FakeProcess(new ByteArrayInputStream(output), exitCode, false);
        }

        static FakeProcess running(InputStream output) {
            return new FakeProcess(output, 137, true);
        }

        @Override public OutputStream getOutputStream() { return new ByteArrayOutputStream(); }
        @Override public InputStream getInputStream() { return output; }
        @Override public InputStream getErrorStream() { return InputStream.nullInputStream(); }

        @Override public synchronized int waitFor() throws InterruptedException {
            waited = true;
            while (alive) {
                wait();
            }
            return exitCode;
        }

        @Override public synchronized boolean waitFor(long timeout, TimeUnit unit)
                throws InterruptedException {
            waited = true;
            if (!alive) {
                return true;
            }
            if (exitOnTimedWait) {
                alive = false;
                notifyAll();
                return true;
            }
            long millis = Math.max(1, unit.toMillis(timeout));
            wait(millis);
            return !alive;
        }

        @Override public synchronized int exitValue() {
            if (alive) {
                throw new IllegalThreadStateException("alive");
            }
            return exitCode;
        }

        @Override public synchronized void destroy() {
            destroyed = true;
            events.add("term:leader");
            if (unkillable) {
                return;
            }
            alive = false;
            try {
                output.close();
            } catch (IOException ignored) {
                // Test fixture cleanup.
            }
            notifyAll();
        }

        @Override public synchronized Process destroyForcibly() {
            if (unkillable) {
                destroyed = true;
                events.add("kill:leader");
                return this;
            }
            destroy();
            return this;
        }

        @Override public synchronized boolean isAlive() { return alive; }
        @Override public Stream<ProcessHandle> descendants() {
            if (descendantEnumerationFailure) {
                throw new UnsupportedOperationException("tree unavailable");
            }
            if (delayedObserverEnumeration != null) {
                int enumeration = descendantEnumerations.incrementAndGet();
                if (enumeration == delayedObserverEnumeration.ordinal()) {
                    delayedObserverEnumeration.entered().countDown();
                    boolean restoreInterrupt = false;
                    while (true) {
                        try {
                            delayedObserverEnumeration.release().await();
                            break;
                        } catch (InterruptedException error) {
                            restoreInterrupt = true;
                            delayedObserverEnumeration.interrupted().countDown();
                        }
                    }
                    if (restoreInterrupt) {
                        Thread.currentThread().interrupt();
                    }
                    return descendants.stream();
                }
                return Stream.empty();
            }
            return descendants.stream();
        }
    }

    private static final class FakeHandle implements ProcessHandle {
        private final long pid;
        private final String name;
        private final List<String> events;
        private boolean alive = true;

        private FakeHandle(long pid, String name, List<String> events) {
            this.pid = pid;
            this.name = name;
            this.events = events;
        }

        @Override public long pid() { return pid; }
        @Override public Optional<ProcessHandle> parent() { return Optional.empty(); }
        @Override public Stream<ProcessHandle> children() { return Stream.empty(); }
        @Override public Stream<ProcessHandle> descendants() { return Stream.empty(); }
        @Override public Info info() { return ProcessHandle.current().info(); }
        @Override public CompletableFuture<ProcessHandle> onExit() {
            return alive ? new CompletableFuture<>() : CompletableFuture.completedFuture(this);
        }
        @Override public boolean supportsNormalTermination() { return true; }
        @Override public boolean destroy() {
            events.add("term:" + name);
            alive = false;
            return true;
        }
        @Override public boolean destroyForcibly() {
            events.add("kill:" + name);
            alive = false;
            return true;
        }
        @Override public boolean isAlive() { return alive; }
        @Override public int compareTo(ProcessHandle other) { return Long.compare(pid, other.pid()); }
    }
}
