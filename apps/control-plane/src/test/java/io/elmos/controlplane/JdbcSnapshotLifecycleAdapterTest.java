package io.elmos.controlplane;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class JdbcSnapshotLifecycleAdapterTest {
    @Test void databaseTimestampUsesAnExplicitUtcOffset() {
        Instant value = Instant.parse("2026-08-24T12:34:56.123456Z");

        OffsetDateTime bound = JdbcSnapshotLifecycleAdapter.databaseTimestamp(value);

        assertEquals(value, bound.toInstant());
        assertEquals(ZoneOffset.UTC, bound.getOffset());
        assertNull(JdbcSnapshotLifecycleAdapter.databaseTimestamp(null));
    }
}
