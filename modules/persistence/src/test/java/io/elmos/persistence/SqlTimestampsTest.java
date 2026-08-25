package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class SqlTimestampsTest {
    @Test void offsetUsesAnExplicitUtcOffset() {
        Instant value = Instant.parse("2026-08-24T12:34:56.123456Z");

        OffsetDateTime bound = SqlTimestamps.offset(value);

        assertEquals(value, bound.toInstant());
        assertEquals(ZoneOffset.UTC, bound.getOffset());
        assertNull(SqlTimestamps.offset(null));
    }
}
