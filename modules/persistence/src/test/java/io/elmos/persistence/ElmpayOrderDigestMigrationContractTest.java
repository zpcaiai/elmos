package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ElmpayOrderDigestMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V84__elmpay_order_digest_lookup.sql");

    @Test void triggerFunctionsResolveEncodeFromPgCatalog() throws Exception {
        String sql = Files.readString(MIGRATION);
        assertEquals(3, count(sql, "pg_catalog.encode(public.digest("));
        assertFalse(sql.contains("public.encode("));
    }

    private static int count(String value, String needle) {
        return (value.length() - value.replace(needle, "").length()) / needle.length();
    }
}
