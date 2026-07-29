package io.elmos.persistence;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

/**
 * The single conversion every store must use when binding a moment in time to a
 * statement parameter.
 *
 * <p>The PostgreSQL driver refuses {@link Instant} outright -- "Can't infer the
 * SQL type to use for an instance of java.time.Instant" -- because an instant
 * carries no offset and the driver will not guess one. {@link OffsetDateTime} at
 * UTC states the offset explicitly, and {@code timestamptz} stores the instant it
 * denotes, so the round trip is lossless whatever the server's timezone.
 *
 * <p>This lives in one place because the mistake it prevents is invisible until a
 * statement actually reaches PostgreSQL. Binding an {@code Instant} compiles, and
 * passes every test backed by a mock or an unreachable datasource; it fails only
 * against a real database. When the container tests in this module were silently
 * skipping, four separate stores had the defect and one of them already carried a
 * private copy of this exact helper -- the correct spelling was sitting in the
 * same package, unused, because using it was never what made a test go green.
 */
final class SqlTimestamps {

    private SqlTimestamps() {
    }

    /** Null-tolerant, because optional windows and nullable columns are ordinary. */
    static OffsetDateTime offset(Instant value) {
        return value == null ? null : value.atOffset(ZoneOffset.UTC);
    }
}
