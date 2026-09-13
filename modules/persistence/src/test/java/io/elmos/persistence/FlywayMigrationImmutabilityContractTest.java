package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.zip.CRC32;

import static org.junit.jupiter.api.Assertions.assertEquals;

/** Prevents edits to migrations already recorded by the production Flyway ledger. */
class FlywayMigrationImmutabilityContractTest {
    private static final Path MIGRATION_ROOT = Path.of("src/main/resources/db/migration");

    @Test
    void productionAppliedMigrationsRemainByteSemanticallyImmutable() throws Exception {
        Map<String, Integer> checksums = new LinkedHashMap<>();
        checksums.put("V84__elmpay_order_digest_lookup.sql", -964662769);
        checksums.put("V85__payment_provider_binding_and_credit_expiry.sql", 396458826);
        checksums.put("V86__self_service_catalog_2026_09_08.sql", -1130034245);
        checksums.put("V87__commercial_credit_double_entry_and_outbox.sql", -1897641680);

        for (Map.Entry<String, Integer> migration : checksums.entrySet()) {
            assertEquals(migration.getValue(), flywayChecksum(MIGRATION_ROOT.resolve(migration.getKey())),
                    migration.getKey() + " was already applied and must be changed only by a new migration");
        }
    }

    private static int flywayChecksum(Path migration) throws Exception {
        CRC32 checksum = new CRC32();
        for (String line : Files.readAllLines(migration, StandardCharsets.UTF_8)) {
            checksum.update(line.getBytes(StandardCharsets.UTF_8));
        }
        return (int) checksum.getValue();
    }
}
