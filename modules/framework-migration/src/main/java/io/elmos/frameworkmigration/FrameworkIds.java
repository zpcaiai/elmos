package io.elmos.frameworkmigration;

import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

final class FrameworkIds {
    private static final ObjectMapper CANONICAL = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

    private FrameworkIds() {}

    static String id(String prefix, Object... parts) {
        return prefix + ":" + hash(parts);
    }

    static String hash(Object value) {
        try {
            byte[] input = CANONICAL.writeValueAsBytes(value);
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(input);
            return java.util.HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        } catch (java.io.IOException error) {
            throw new IllegalArgumentException("AFSM_CANONICALIZATION_FAILED", error);
        }
    }

    static String hashText(String value) {
        try {
            return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
