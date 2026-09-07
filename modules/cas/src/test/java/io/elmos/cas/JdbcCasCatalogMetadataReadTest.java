package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Proxy;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class JdbcCasCatalogMetadataReadTest {

    @Test
    void everyPersistedMetadataFieldRoundTripsIncludingLabelsAndProvenanceSize() throws Exception {
        CasDigest object = CasDigest.ofUtf8("catalog object");
        CasDigest provenance = CasDigest.ofUtf8("non-empty provenance record");
        Map<String, Object> row = completeRow(object, provenance);

        CasCatalog.CatalogEntry entry = JdbcCasCatalog.readEntry("tenant-a", resultSet(row));

        assertEquals(object, entry.digest());
        assertEquals(CasObjectModel.ObjectKind.MANIFEST, entry.kind());
        assertEquals("application/vnd.elmos.manifest+json", entry.mediaType());
        assertEquals("snapshot-service", entry.sourceSystem());
        assertEquals("2.7", entry.schemaVersion());
        assertEquals(CasObjectModel.Sensitivity.GENERATED_OUTPUT, entry.sensitivity());
        assertEquals(CasObjectModel.RetentionClass.EVIDENCE, entry.retentionClass());
        assertEquals("eu-west", entry.dataResidency());
        assertEquals(CasAccessPolicy.SecurityTier.CONFIDENTIAL, entry.securityTier());
        assertEquals(provenance, entry.provenanceDigest().orElseThrow());
        assertEquals(Map.of("format", "tar+zstd", "repository", "repo-\u4e00"), entry.labels());
        assertEquals(true, entry.legalHold());
        assertEquals(true, entry.metadata().legalHold());
        assertEquals(1_800_000_000_000L, entry.createdAtEpochMillis());
    }

    @Test
    void aLegacyProvenanceDigestWithoutItsSizeFailsClosed() {
        CasDigest object = CasDigest.ofUtf8("catalog object");
        CasDigest provenance = CasDigest.ofUtf8("provenance");
        Map<String, Object> row = completeRow(object, provenance);
        row.put("provenance_size_bytes", null);

        assertThrows(SQLException.class,
                () -> JdbcCasCatalog.readEntry("tenant-a", resultSet(row)));
    }

    @Test
    void aProvenanceSizeWithoutItsDigestAlsoFailsClosed() {
        CasDigest object = CasDigest.ofUtf8("catalog object");
        CasDigest provenance = CasDigest.ofUtf8("provenance");
        Map<String, Object> row = completeRow(object, provenance);
        row.put("provenance_digest_hex", null);

        assertThrows(SQLException.class,
                () -> JdbcCasCatalog.readEntry("tenant-a", resultSet(row)));
    }

    private static Map<String, Object> completeRow(CasDigest object, CasDigest provenance) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("digest_hex", object.hex());
        row.put("size_bytes", object.sizeBytes());
        row.put("object_kind", "MANIFEST");
        row.put("media_type", "application/vnd.elmos.manifest+json");
        row.put("source_system", "snapshot-service");
        row.put("schema_version", "2.7");
        row.put("sensitivity", "GENERATED_OUTPUT");
        row.put("retention_class", "EVIDENCE");
        row.put("data_residency", "eu-west");
        row.put("security_tier", "CONFIDENTIAL");
        row.put("provenance_digest_hex", provenance.hex());
        row.put("provenance_size_bytes", provenance.sizeBytes());
        row.put("labels_json", "{\"repository\":\"repo-\\u4e00\",\"format\":\"tar+zstd\"}");
        row.put("legal_hold", true);
        row.put("created_at", new Timestamp(1_800_000_000_000L));
        return row;
    }

    private static ResultSet resultSet(Map<String, Object> row) {
        return (ResultSet) Proxy.newProxyInstance(ResultSet.class.getClassLoader(),
                new Class<?>[]{ResultSet.class}, (ignored, method, args) -> {
                    if (args != null && args.length == 1 && args[0] instanceof String column) {
                        Object value = row.get(column);
                        return switch (method.getName()) {
                            case "getString" -> value == null ? null : value.toString();
                            case "getLong" -> value == null ? 0L : ((Number) value).longValue();
                            case "getObject" -> value;
                            case "getBoolean" -> value != null && (Boolean) value;
                            case "getTimestamp" -> value;
                            default -> defaultValue(method.getReturnType());
                        };
                    }
                    return switch (method.getName()) {
                        case "close" -> null;
                        case "isClosed" -> false;
                        default -> defaultValue(method.getReturnType());
                    };
                });
    }

    private static Object defaultValue(Class<?> type) {
        if (!type.isPrimitive() || type == void.class) return null;
        if (type == boolean.class) return false;
        if (type == byte.class) return (byte) 0;
        if (type == short.class) return (short) 0;
        if (type == int.class) return 0;
        if (type == long.class) return 0L;
        if (type == float.class) return 0F;
        if (type == double.class) return 0D;
        if (type == char.class) return '\0';
        throw new IllegalArgumentException("unsupported primitive " + type);
    }
}
