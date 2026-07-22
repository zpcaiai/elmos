package io.elmos.uir;

import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

final class UirIds {
    private static final ObjectMapper CANONICAL_JSON = JsonMapper.builder().findAndAddModules()
            .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
            .build();
    private UirIds() {}
    static String id(String prefix, Object... parts) {
        StringBuilder canonical = new StringBuilder("uir-id-v1");
        for (Object part : parts) canonical.append('\0').append(part == null ? "<null>" : part);
        try { return prefix + ":" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical.toString().getBytes(StandardCharsets.UTF_8))); }
        catch (Exception error) { throw new IllegalStateException(error); }
    }
    static String hash(Object... parts) { return id("sha256", parts); }
    static String contentHash(Object value) {
        try { return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(CANONICAL_JSON.writeValueAsBytes(value))); }
        catch (Exception error) { throw new IllegalStateException("UIR_CONTENT_HASH_FAILED", error); }
    }
}
