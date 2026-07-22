package io.elmos.scm;

import java.util.Arrays;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Consumer;

public final class EphemeralCredential implements AutoCloseable {
    private final char[] value;
    private final Consumer<char[]> closeAction;
    private boolean closed;

    public EphemeralCredential(char[] value) { this(value, ignored -> {}); }
    public EphemeralCredential(char[] value, Consumer<char[]> closeAction) {
        Objects.requireNonNull(value, "value");
        if (value.length == 0) throw new IllegalArgumentException("credential must not be empty");
        this.value = value.clone();
        this.closeAction = Objects.requireNonNull(closeAction);
    }

    public synchronized <T> T use(Function<char[], T> operation) {
        if (closed) throw new IllegalStateException("credential is closed");
        char[] copy = value.clone();
        try { return operation.apply(copy); }
        finally { Arrays.fill(copy, '\0'); }
    }

    @Override public synchronized void close() {
        if (closed) return;
        char[] copy = value.clone();
        try { closeAction.accept(copy); }
        finally { Arrays.fill(copy, '\0'); Arrays.fill(value, '\0'); closed = true; }
    }

    boolean cleared() {
        return closed && new String(value).chars().allMatch(character -> character == 0);
    }

    @Override public String toString() { return "EphemeralCredential[REDACTED]"; }
}
