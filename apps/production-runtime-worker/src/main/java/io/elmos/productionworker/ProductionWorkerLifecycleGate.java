package io.elmos.productionworker;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

/** Fair ingress barrier used to drain caller-owned work during worker shutdown. */
final class ProductionWorkerLifecycleGate {
    private final ReentrantReadWriteLock gate = new ReentrantReadWriteLock(true);

    Ingress enter() {
        Lock shared = gate.readLock();
        shared.lock();
        return new Ingress(shared);
    }

    DrainResult drainUntil(long deadlineNanos) {
        Lock exclusive = gate.writeLock();
        boolean interrupted = false;
        boolean drained = false;
        while (!drained) {
            long remaining = deadlineNanos - System.nanoTime();
            if (remaining <= 0L) break;
            try {
                drained = exclusive.tryLock(remaining, TimeUnit.NANOSECONDS);
            } catch (InterruptedException ex) {
                interrupted = true;
            }
        }
        if (drained) exclusive.unlock();
        return new DrainResult(drained, interrupted);
    }

    int activeIngress() {
        return gate.getReadLockCount();
    }

    record DrainResult(boolean drained, boolean interrupted) {}

    static final class Ingress implements AutoCloseable {
        private final Lock shared;
        private boolean released;

        private Ingress(Lock shared) {
            this.shared = shared;
        }

        @Override
        public void close() {
            if (released) return;
            released = true;
            shared.unlock();
        }
    }
}
