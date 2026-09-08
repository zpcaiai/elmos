package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ElmPayMigrationContractTest {
    private static final Path REPAIR = Path.of(
            "src/main/resources/db/migration/V95__elmpay_digest_function_schema_repair.sql");

    @Test void forwardRepairQualifiesDigestFunctionsAndPreservesProviderBinding() throws Exception {
        String sql = Files.readString(REPAIR);
        assertEquals(3, occurrences(sql, "pg_catalog.encode(public.digest(pg_catalog.convert_to("));
        assertEquals(3, occurrences(sql, "amount_minor, provider, status)"));
        assertEquals(3, occurrences(sql, "NEW.provider, NEW.status)"));
        assertFalse(sql.contains("public.encode("));
        assertEquals(3, occurrences(sql, "SECURITY DEFINER"));
        assertEquals(3, occurrences(sql, "SET search_path = pg_catalog, public, pg_temp"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION elmos_sync_payment_order_directory() FROM PUBLIC"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION elmos_sync_wallet_topup_directory() FROM PUBLIC"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION elmos_sync_commercial_order_directory() FROM PUBLIC"));
    }

    private static int occurrences(String value, String needle) {
        return value.split(java.util.regex.Pattern.quote(needle), -1).length - 1;
    }
}
