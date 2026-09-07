package io.elmos.commercialapi;

public final class BillingApiException extends RuntimeException {
    private final int httpStatus;
    private final String code;
    private final boolean retryable;

    public BillingApiException(int httpStatus, String code, String message, boolean retryable) {
        super(message);
        this.httpStatus = httpStatus;
        this.code = code;
        this.retryable = retryable;
    }

    public BillingApiException(
            int httpStatus, String code, String message, boolean retryable, Throwable cause
    ) {
        super(message, cause);
        this.httpStatus = httpStatus;
        this.code = code;
        this.retryable = retryable;
    }

    public int httpStatus() {
        return httpStatus;
    }

    public String code() {
        return code;
    }

    public boolean retryable() {
        return retryable;
    }
}
