package io.elmos.secret;

import java.util.Arrays;
import java.util.Objects;
import java.util.function.Function;

public final class SecretValue implements AutoCloseable {
    private final char[] value;
    private boolean closed;
    public SecretValue(char[] value) {
        Objects.requireNonNull(value); if (value.length == 0) throw new IllegalArgumentException("secret value is empty");
        this.value = value.clone();
    }
    public synchronized <T> T use(Function<char[], T> action) {
        if (closed) throw new IllegalStateException("secret value is closed");
        return action.apply(value);
    }
    @Override public synchronized void close() { Arrays.fill(value, '\0'); closed = true; }
    boolean cleared() { return closed && value[0] == '\0' && new String(value).chars().allMatch(c -> c == 0); }
    @Override public String toString() { return "SecretValue[REDACTED]"; }
}
