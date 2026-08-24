package io.elmos.cas;

import java.util.Collection;

/** Argument checks shared across the module. Kept deliberately small and dependency free. */
final class CasText {

    private CasText() {
    }

    static String required(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return withoutNul(value, field);
    }

    static String withoutNul(String value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        if (value.indexOf('\0') >= 0) {
            // PostgreSQL text/varchar rejects NUL. Refusing it on the heap path also prevents
            // delimiter-key aliases such as tenant "a" + id "b\\0c" versus "a\\0b" + "c".
            throw new IllegalArgumentException(field + " must not contain NUL");
        }
        return value;
    }

    static void requireNonEmpty(Collection<?> value, String field) {
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be empty");
        }
    }

    static void requirePositive(long value, String field) {
        if (value <= 0) {
            throw new IllegalArgumentException(field + " must be positive, was " + value);
        }
    }
}
