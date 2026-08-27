package io.elmos.productionruntime;

/** Stable error codes consumed by HTTP clients, workers, and recovery automation. */
public final class ProductionRuntimeException extends RuntimeException {
    private final String code;

    public ProductionRuntimeException(String code, String message) {
        super(message);
        this.code = code;
    }

    public ProductionRuntimeException(String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    public String code() { return code; }
    public boolean isConflict() { return code.endsWith("_CONFLICT") || code.contains("STALE"); }
}
