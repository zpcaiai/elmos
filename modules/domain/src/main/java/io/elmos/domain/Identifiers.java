package io.elmos.domain;

import java.util.UUID;

final class Identifiers {
    private Identifiers() {}
    static String require(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " must not be blank");
        return value;
    }
    static String random() { return UUID.randomUUID().toString(); }
}

