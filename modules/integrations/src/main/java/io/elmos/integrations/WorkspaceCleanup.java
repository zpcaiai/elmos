package io.elmos.integrations;

import java.nio.file.Path;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executor;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/** Bounded JVM-local retirement work; durable tickets survive a process restart. */
final class WorkspaceCleanup {
    private static final Semaphore CAPACITY = new Semaphore(32);
    private static final Set<Path> ACTIVE = ConcurrentHashMap.newKeySet();
    static final Executor EXECUTOR = new ThreadPoolExecutor(1, 1, 30, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(32), task -> {
                Thread thread = new Thread(task, "elmos-workspace-cleanup");
                thread.setDaemon(true);
                return thread;
            }, new ThreadPoolExecutor.AbortPolicy());

    static Reservation reserve(Path identity) {
        if (!CAPACITY.tryAcquire()) return null;
        if (!ACTIVE.add(identity)) {
            CAPACITY.release();
            return null;
        }
        return new Reservation(identity);
    }

    static final class Reservation implements AutoCloseable {
        private final Path identity;
        private boolean transferred;
        private boolean released;

        private Reservation(Path identity) { this.identity = identity; }

        void submit(Executor executor, Runnable work) {
            transferred = true;
            try {
                executor.execute(() -> {
                    try { work.run(); }
                    catch (RuntimeException failure) {
                        // Keep the durable ticket for a bounded later retry, without leaking paths.
                        System.getLogger(WorkspaceCleanup.class.getName()).log(
                                System.Logger.Level.WARNING, "Git workspace retirement requires retry");
                    } finally { release(); }
                });
            } catch (RuntimeException failure) {
                release();
                // The ticket is deliberately retained; admission never runs cleanup inline.
                System.getLogger(WorkspaceCleanup.class.getName()).log(
                        System.Logger.Level.WARNING, "Git workspace retirement queue unavailable");
            }
        }

        private synchronized void release() {
            if (released) return;
            released = true;
            ACTIVE.remove(identity);
            CAPACITY.release();
        }

        @Override public void close() { if (!transferred) release(); }
    }
}
