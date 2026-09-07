package io.elmos.cas;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;

/** Per-object coordination. Waiters retain their lock identity until retirement. */
final class CasObjectLocks {
    private final ConcurrentHashMap<CasDigest, Entry> ENTRIES = new ConcurrentHashMap<>();

    private static final class Entry {
        final ReentrantLock lock = new ReentrantLock();
        int references;
    }

    Guard acquire(CasDigest key) {
        return acquire(key, false);
    }

    Guard tryAcquire(CasDigest key) {
        return acquire(key, true);
    }

    private Guard acquire(CasDigest path, boolean nonblocking) {
        CasDigest key = path;
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

    private void releaseReference(CasDigest key, Entry entry) {
        ENTRIES.compute(key, (ignored, current) -> {
            if (current != entry) throw new IllegalStateException("CAS object lock ownership lost");
            return --current.references == 0 ? null : current;
        });
    }

    final class Guard implements AutoCloseable {
        private final CasDigest key;
        private final Entry entry;
        private boolean closed;

        private Guard(CasDigest key, Entry entry) {
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
