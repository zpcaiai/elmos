package io.elmos.productionworker;

import io.elmos.productionruntime.ProductionRuntimeException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProductionWorkerDurableJournalTest {
    @TempDir
    Path temporary;

    @Test
    void recordIsAtomicallyReplacedLoadedAndEvicted() {
        Path directory = temporary.resolve("state");
        var journal = new ProductionWorkerDurableJournal(directory);
        UUID attempt = UUID.randomUUID();
        byte[] first = "{\"schemaVersion\":1}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        byte[] second = "{\"schemaVersion\":2}".getBytes(java.nio.charset.StandardCharsets.UTF_8);

        journal.write(attempt, first);
        assertArrayEquals(first, journal.load(10).get(attempt));
        journal.write(attempt, second);
        assertArrayEquals(second, journal.load(10).get(attempt));
        assertTrue(Files.exists(directory.resolve(attempt + ".json")));

        journal.delete(attempt);
        assertEquals(0, journal.load(10).size());
    }

    @Test
    void malformedAndOversizedInventoriesFailClosed() throws Exception {
        Path directory = temporary.resolve("bad-state");
        var journal = new ProductionWorkerDurableJournal(directory);
        Files.writeString(directory.resolve("not-a-uuid.json"), "{}");
        ProductionRuntimeException malformed = assertThrows(
                ProductionRuntimeException.class, () -> journal.load(10));
        assertEquals("WORKER_DURABLE_JOURNAL_FAILURE", malformed.code());

        Files.delete(directory.resolve("not-a-uuid.json"));
        journal.write(UUID.randomUUID(), "{}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        assertThrows(ProductionRuntimeException.class, () -> journal.load(0));
    }
}
