package io.elmos.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.core.NestedRuntimeException;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

import java.net.ConnectException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * Argument guards on {@link JdbcUserActivityStore#export}.
 *
 * <p>Deliberately kept out of the container-backed test: every rejection here
 * happens before {@code inTenant} opens a transaction, so these run in any
 * environment, Docker or not. The data source below points nowhere on purpose
 * -- if a future change moves validation after the first query, these tests
 * stop failing with {@code IllegalArgumentException} and start failing with a
 * connection error, which is exactly the signal that the guard has drifted
 * behind the database access it was meant to precede.
 */
class JdbcUserActivityExportGuardTest {

    private static final String ORGANIZATION = "org-guard-test";
    private static final Instant NOW = Instant.parse("2026-07-28T12:00:00Z");

    private final JdbcUserActivityStore store = unreachableStore();

    private static JdbcUserActivityStore unreachableStore() {
        var dataSource = new DriverManagerDataSource(
                "jdbc:postgresql://127.0.0.1:1/elmos-guard-test-must-not-connect", "none", "none");
        return new JdbcUserActivityStore(
                JdbcClient.create(dataSource),
                new TransactionTemplate(new DataSourceTransactionManager(dataSource)),
                new ObjectMapper(),
                Clock.fixed(NOW, ZoneOffset.UTC));
    }

    private void export(Instant from, Instant to, Instant afterAt, String afterId, int limit) {
        store.export(ORGANIZATION, from, to, "ALL", "ALL", afterAt, afterId, limit);
    }

    /**
     * A cursor is a pair. Accepting half of one would silently restart the
     * export from the beginning of the window, duplicating everything already
     * exported.
     */
    @Test
    void refusesAHalfFormedCursor() {
        assertThrows(IllegalArgumentException.class,
                () -> export(NOW.minusSeconds(3_600), NOW, NOW.minusSeconds(600), null, 10));
        assertThrows(IllegalArgumentException.class,
                () -> export(NOW.minusSeconds(3_600), NOW, null, "evt-c", 10));
    }

    @Test
    void refusesAWindowLongerThanAYear() {
        assertThrows(IllegalArgumentException.class,
                () -> export(NOW.minusSeconds(367L * 24 * 60 * 60), NOW, null, null, 10));
    }

    /** An empty or inverted window is a caller mistake, not an empty result. */
    @Test
    void refusesAnInvertedOrEmptyWindow() {
        assertThrows(IllegalArgumentException.class,
                () -> export(NOW, NOW, null, null, 10));
        assertThrows(IllegalArgumentException.class,
                () -> export(NOW, NOW.minusSeconds(3_600), null, null, 10));
    }

    @Test
    void refusesAnOutOfRangeLimit() {
        assertThrows(IllegalArgumentException.class,
                () -> export(NOW.minusSeconds(3_600), NOW, null, null, 0));
        assertThrows(IllegalArgumentException.class,
                () -> export(NOW.minusSeconds(3_600), NOW, null, null, -1));
        assertThrows(IllegalArgumentException.class,
                () -> export(NOW.minusSeconds(3_600), NOW, null, null, 1_001));
    }

    @Test
    void refusesAMissingWindow() {
        assertThrows(NullPointerException.class,
                () -> export(null, NOW, null, null, 10));
        assertThrows(NullPointerException.class,
                () -> export(NOW.minusSeconds(3_600), null, null, null, 10));
    }

    /**
     * A window exactly at the limit is legal, so the guard must reject only
     * what exceeds it. This one reaches the database and therefore fails to
     * connect -- proving the boundary passed validation rather than being
     * rejected off-by-one.
     *
     * <p>The assertion is deliberately on {@link NestedRuntimeException}, the
     * common supertype of Spring's transaction and data-access failures, rather
     * than on {@code DataAccessException}: opening the transaction is the first
     * thing that touches the socket, so the failure surfaces as
     * {@code CannotCreateTransactionException}, which is a transaction
     * exception, not a data-access one. What matters is only that the call got
     * past validation into the data layer -- {@code IllegalArgumentException}
     * and {@code NullPointerException} are not {@code NestedRuntimeException},
     * so an off-by-one guard would still fail this test.
     */
    @Test
    void acceptsAWindowExactlyAtTheLimit() {
        NestedRuntimeException thrown = assertThrows(NestedRuntimeException.class,
                () -> export(NOW.minusSeconds(366L * 24 * 60 * 60), NOW, null, null, 10));
        assertInstanceOf(ConnectException.class, rootCause(thrown),
                "the boundary window should have reached the (unreachable) database");
    }

    private static Throwable rootCause(Throwable thrown) {
        Throwable cause = thrown;
        while (cause.getCause() != null && cause.getCause() != cause) {
            cause = cause.getCause();
        }
        return cause;
    }
}
