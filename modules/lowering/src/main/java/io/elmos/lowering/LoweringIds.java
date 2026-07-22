package io.elmos.lowering;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class LoweringIds {
    private static final ObjectMapper JSON = new ObjectMapper().findAndRegisterModules()
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    private LoweringIds() {}
    public static String id(String prefix, Object... components) {
        return prefix + ":" + hash((Object) components).substring(0, 32);
    }
    public static String hash(Object value) {
        try {
            byte[] encoded = value instanceof byte[] bytes ? bytes : JSON.writeValueAsBytes(value);
            return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(encoded));
        } catch (Exception error) {
            throw new IllegalStateException("LOWERING_ID_HASH_FAILED", error);
        }
    }
    public static String hashText(String value) { return hash(value.getBytes(StandardCharsets.UTF_8)); }
}
