package io.elmos.persistence;

import org.junit.jupiter.api.Test;
import org.springframework.core.NestedRuntimeException;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.net.ConnectException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * Argument guards on {@link JdbcRunHistoryStore#replay}.
 *
 * <p>Same shape and same reason as {@link JdbcUserActivityExportGuardTest}:
 * every rejection here happens before a transaction opens, so these run without
 * Docker, and the data source points nowhere on purpose. If validation ever
 * drifts behind the first query, these stop failing with
 * {@code IllegalArgumentException} and start failing with a connection error --
 * which is the signal that the guard moved.
 *
 * <p>What these guards cannot show is that the replay is read-only. That
 * property lives in the read-only transaction and is only observable against a
 * real database, so it is asserted in the container-backed test instead. Two
 * different claims, two different places to prove them.
 */
class JdbcRunHistoryGuardTest {

    private final JdbcRunHistoryStore store = unreachableStore();

    private static JdbcRunHistoryStore unreachableStore() {
        var dataSource = new DriverManagerDataSource(
                "jdbc:postgresql://127.0.0.1:1/elmos-guard-test-must-not-connect", "none", "none");
        return new JdbcRunHistoryStore(
                JdbcClient.create(dataSource),
                new DataSourceTransactionManager(dataSource));
    }

    @Test
    void refusesAMissingOrBlankOrganization() {
        assertThrows(IllegalArgumentException.class, () -> store.replay(null, "run-1"));
        assertThrows(IllegalArgumentException.class, () -> store.replay("", "run-1"));
        assertThrows(IllegalArgumentException.class, () -> store.replay("   ", "run-1"));
    }

    @Test
    void refusesAMissingOrBlankRunId() {
        assertThrows(IllegalArgumentException.class, () -> store.replay("org-1", null));
        assertThrows(IllegalArgumentException.class, () -> store.replay("org-1", ""));
        assertThrows(IllegalArgumentException.class, () -> store.replay("org-1", "   "));
    }

    /**
     * Both identifiers are bound as parameters, so an over-long one is a bad
     * request rather than an injection risk -- but it is still a bad request,
     * and refusing it here keeps a malformed id from becoming a query that
     * scans and returns nothing for a reason nobody can see.
     */
    @Test
    void refusesAnOverLongIdentifier() {
        String tooLong = "x".repeat(129);
        assertThrows(IllegalArgumentException.class, () -> store.replay(tooLong, "run-1"));
        assertThrows(IllegalArgumentException.class, () -> store.replay("org-1", tooLong));
    }

    /**
     * A well-formed pair must get past validation into the data layer. Without
     * this, every guard above would still pass if {@code replay} rejected
     * everything.
     */
    @Test
    void acceptsAWellFormedPair() {
        NestedRuntimeException thrown = assertThrows(NestedRuntimeException.class,
                () -> store.replay("org-1", "run-1"));
        assertInstanceOf(ConnectException.class, rootCause(thrown),
                "a valid request should have reached the (unreachable) database");
    }

    private static Throwable rootCause(Throwable thrown) {
        Throwable cause = thrown;
        while (cause.getCause() != null && cause.getCause() != cause) {
            cause = cause.getCause();
        }
        return cause;
    }
}
