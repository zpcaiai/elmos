package io.elmos.cas;

/** Failure types the CAS raises. Each maps onto one of the skill's failure classes. */
public final class CasExceptions {

    private CasExceptions() {
    }

    /** DATA. The bytes under a digest are not the bytes that digest names. */
    public static class CasCorruptionException extends RuntimeException {
        private final CasDigest expected;
        private final CasDigest actual;

        public CasCorruptionException(String store, CasDigest expected, CasDigest actual) {
            super("cache corruption in " + store + ": expected " + expected.compact()
                    + " but stored bytes hash to " + actual.compact());
            this.expected = expected;
            this.actual = actual;
        }

        public CasDigest expected() {
            return expected;
        }

        public CasDigest actual() {
            return actual;
        }
    }

    /** DATA. A referenced object is not present in any tier. */
    public static class CasNotFoundException extends RuntimeException {
        public CasNotFoundException(CasDigest digest) {
            super("object not present: " + digest.compact());
        }
    }

    /** SECURITY. The caller may not read or write this object. */
    public static class CasAccessDeniedException extends RuntimeException {
        private final String reason;

        public CasAccessDeniedException(String reason, String detail) {
            super(reason + ": " + detail);
            this.reason = reason;
        }

        public String reason() {
            return reason;
        }
    }

    /** DATA. A transfer completed with content that does not match its declared digest. */
    public static class CasQuarantinedException extends RuntimeException {
        private final String quarantineId;

        public CasQuarantinedException(String quarantineId, String detail) {
            super("transfer quarantined as " + quarantineId + ": " + detail);
            this.quarantineId = quarantineId;
        }

        public String quarantineId() {
            return quarantineId;
        }
    }
}
