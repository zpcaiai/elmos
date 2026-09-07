package io.elmos.runner;

import java.util.concurrent.ThreadLocalRandom;

/**
 * Exponential backoff with full jitter.
 *
 * <p>Jitter is not cosmetic here. Twenty agents that all lose the control plane at
 * the same moment and retry on the same schedule will keep hitting it in a
 * synchronised wave the instant it recovers, which is how a brief outage turns
 * into a sustained one.</p>
 */
public final class Backoff {

    private final long baseMillis;
    private final long maxMillis;
    private int attempt;

    public Backoff(long baseMillis, long maxMillis) {
        if (baseMillis <= 0 || maxMillis < baseMillis) {
            throw new IllegalArgumentException("invalid backoff bounds");
        }
        this.baseMillis = baseMillis;
        this.maxMillis = maxMillis;
    }

    public void reset() {
        attempt = 0;
    }

    /** Returns the next delay and advances the attempt counter. */
    public long nextDelayMillis() {
        long ceiling = baseMillis;
        for (int i = 0; i < attempt && ceiling < maxMillis; i++) {
            ceiling = Math.min(ceiling * 2, maxMillis);
        }
        if (attempt < 30) {
            attempt++;
        }
        return ThreadLocalRandom.current().nextLong(baseMillis, ceiling + 1);
    }

    public int attempts() {
        return attempt;
    }

    /** Sleeps for the next delay. Returns false when the thread was interrupted. */
    public boolean sleep() {
        try {
            Thread.sleep(nextDelayMillis());
            return true;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return false;
        }
    }
}
