package io.elmos.persistence;

import org.junit.jupiter.api.Test;
import org.springframework.core.NestedRuntimeException;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.net.ConnectException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * Argument guards on {@link JdbcSelfServiceBillingStore#adjustQuota}.
 *
 * <p>Adjusting a tenant's allowance is the most destructive operation an
 * operator can perform through the console, so every check that does not need
 * the database runs before a transaction is opened. The data source below
 * points at a closed port on purpose: a rejection that reaches PostgreSQL fails
 * with a connection error instead of {@code IllegalArgumentException}, which is
 * exactly the signal that validation has drifted behind the write it was meant
 * to precede.
 *
 * <p>The checks that do need the database -- version conflict, the
 * consumed-plus-reserved floor, the no-op refusal -- cannot be covered here and
 * are covered by the container-backed test instead.
 */
class JdbcQuotaAdministrationGuardTest {

    private static final String ORGANIZATION = "org-quota-guard-test";
    private static final String ALLOCATION = "quota-guard-allocation";
    private static final BigDecimal LIMIT = new BigDecimal("1000000");

    private final JdbcSelfServiceBillingStore store = unreachableStore();

    private static JdbcSelfServiceBillingStore unreachableStore() {
        var dataSource = new DriverManagerDataSource(
                "jdbc:postgresql://127.0.0.1:1/elmos-quota-guard-must-not-connect", "none", "none");
        return new JdbcSelfServiceBillingStore(
                JdbcClient.create(dataSource),
                new TransactionTemplate(new DataSourceTransactionManager(dataSource)));
    }

    private void adjust(
            String organizationId,
            String actorId,
            String allocationId,
            BigDecimal tokenLimit,
            BigDecimal creditLimit,
            long expectedVersion,
            String reasonCode
    ) {
        store.adjustQuota(organizationId, actorId, allocationId,
                tokenLimit, creditLimit, expectedVersion, reasonCode);
    }

    @Test
    void refusesBlankIdentifiers() {
        assertThrows(IllegalArgumentException.class,
                () -> adjust("  ", "user:ops", ALLOCATION, LIMIT, LIMIT, 3, "CAPACITY_INCREASE"));
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, " ", ALLOCATION, LIMIT, LIMIT, 3, "CAPACITY_INCREASE"));
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", "", LIMIT, LIMIT, 3, "CAPACITY_INCREASE"));
    }

    @Test
    void refusesAMissingOrNegativeLimit() {
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION, null, LIMIT, 3, "CAPACITY_INCREASE"));
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION, LIMIT, null, 3, "CAPACITY_INCREASE"));
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION,
                        new BigDecimal("-1"), LIMIT, 3, "CAPACITY_INCREASE"));
    }

    /**
     * {@code numeric(30,0)} would round a fractional limit away without saying
     * so, leaving the operator's stated intent and the stored allowance
     * different by an amount nobody sees.
     */
    @Test
    void refusesAFractionalLimit() {
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION,
                        new BigDecimal("100.5"), LIMIT, 3, "CAPACITY_INCREASE"));
    }

    /** A trailing zero after the point is still a whole number. */
    @Test
    void acceptsAWholeNumberWrittenWithADecimalPoint() {
        assertThrows(NestedRuntimeException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION,
                        new BigDecimal("100.00"), LIMIT, 3, "CAPACITY_INCREASE"));
    }

    @Test
    void refusesALimitBeyondTheColumnsRange() {
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION,
                        new BigDecimal("1000000000000000000000000000001"), LIMIT, 3, "CAPACITY_INCREASE"));
    }

    @Test
    void refusesANegativeExpectedVersion() {
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION, LIMIT, LIMIT, -1, "CAPACITY_INCREASE"));
    }

    /**
     * The reason code is written to the append-only event log and flows out
     * through the audit CSV export, so free-form operator text must not be
     * accepted: it would put author-controlled strings into a file other
     * systems parse.
     */
    @Test
    void refusesAReasonThatIsNotACode() {
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION, LIMIT, LIMIT, 3, null));
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION, LIMIT, LIMIT, 3, ""));
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION, LIMIT, LIMIT, 3,
                        "customer asked for more, see ticket #42"));
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION, LIMIT, LIMIT, 3,
                        "capacity_increase"));
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION, LIMIT, LIMIT, 3, "AB"));
        assertThrows(IllegalArgumentException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION, LIMIT, LIMIT, 3,
                        "A".repeat(65)));
    }

    /**
     * A well-formed request must get all the way to the database. Asserting on
     * {@link NestedRuntimeException} rather than a data-access exception because
     * opening the transaction is the first thing that touches the socket, so the
     * failure arrives as a transaction exception. What matters is only that
     * validation let it through -- {@code IllegalArgumentException} is not a
     * {@code NestedRuntimeException}, so an over-strict guard still fails here.
     */
    @Test
    void letsAWellFormedRequestReachTheDatabase() {
        NestedRuntimeException thrown = assertThrows(NestedRuntimeException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION, LIMIT, LIMIT, 3, "CAPACITY_INCREASE"));
        assertInstanceOf(ConnectException.class, rootCause(thrown));
    }

    /** Zero is a legal allowance: it suspends a tenant without deleting it. */
    @Test
    void acceptsZeroAsALimit() {
        assertThrows(NestedRuntimeException.class,
                () -> adjust(ORGANIZATION, "user:ops", ALLOCATION,
                        BigDecimal.ZERO, BigDecimal.ZERO, 0, "TENANT_SUSPENDED"));
    }

    @Test
    void readingAlsoRefusesABlankOrganization() {
        assertThrows(IllegalArgumentException.class,
                () -> store.quotaForAdministration("   "));
    }

    private static Throwable rootCause(Throwable thrown) {
        Throwable cause = thrown;
        while (cause.getCause() != null && cause.getCause() != cause) {
            cause = cause.getCause();
        }
        return cause;
    }
}
