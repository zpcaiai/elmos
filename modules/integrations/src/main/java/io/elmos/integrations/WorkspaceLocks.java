package io.elmos.integrations;

import java.nio.file.Path;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;

/** JVM-wide keyed coordination, including waiters and nested service calls.
 * Workspace roots remain single-host storage; this is not a distributed lease.
 */
final class WorkspaceLocks {
    private static final ConcurrentHashMap<Path, Entry> ENTRIES = new ConcurrentHashMap<>();

    private static final class Entry {
        final ReentrantLock lock = new ReentrantLock();
        int references;
    }

    static Guard acquire(Path key) {
        return acquire(key, false);
    }

    static Guard tryAcquire(Path key) {
        return acquire(key, true);
    }

    private static Guard acquire(Path path, boolean nonblocking) {
        Path key = path.toAbsolutePath().normalize();
        Entry entry = ENTRIES.compute(key, (ignored, existing) -> {
            Entry value = existing == null ? new Entry() : existing;
            value.references++;
            return value;
        });
        if (nonblocking && !entry.lock.tryLock()) {
            releaseReference(key, entry);
            return null;
        }
        if (!nonblocking) entry.lock.lock();
        return new Guard(key, entry);
    }

    private static void releaseReference(Path key, Entry entry) {
        ENTRIES.compute(key, (ignored, current) -> {
            if (current != entry) throw new IllegalStateException("Workspace lock ownership lost");
            return --current.references == 0 ? null : current;
        });
    }

    static final class Guard implements AutoCloseable {
        private final Path key;
        private final Entry entry;
        private boolean closed;

        private Guard(Path key, Entry entry) {
            this.key = key;
            this.entry = entry;
        }

        @Override public void close() {
            if (closed) return;
            entry.lock.unlock();
            closed = true;
            releaseReference(key, entry);
        }
    }
}
