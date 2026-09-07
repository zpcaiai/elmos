package io.elmos.controlplane;

import io.elmos.commercial.SelfServiceBillingPort;
import io.elmos.commercial.SelfServiceBillingPort.QuotaAdministrationView;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Contract of the quota endpoints.
 *
 * <p>The point of most of these is not that a bad request is refused, but that
 * it is refused <em>before</em> the store is reached. A validation that runs
 * after the write has been issued is not a validation, so every rejection test
 * ends by asserting the store was never called rather than only that an
 * exception came back.
 */
class TenantQuotaControllerTest {

    private static final String KEY = "tenant-quota-test-key-32-characters";
    private static final Instant NOW = Instant.parse("2026-07-29T10:00:00Z");

    private final SelfServiceBillingPort billing = mock(SelfServiceBillingPort.class);
    private final TenantQuotaController controller = new TenantQuotaController(
            billing,
            new OperationsAuthorization(
                    Clock.fixed(NOW, ZoneOffset.UTC), KEY,
                    NOW.plusSeconds(3600).toString(), "org-1", "actor-1"));

    private static QuotaAdministrationView view(long version) {
        return new QuotaAdministrationView(
                "org-1", "quota-1", "sub-1", "plan-pro", "Pro",
                NOW.minusSeconds(86_400), NOW.plusSeconds(86_400),
                new BigDecimal("1000"), new BigDecimal("500"),
                new BigDecimal("100"), new BigDecimal("50"),
                new BigDecimal("10"), new BigDecimal("5"),
                new BigDecimal("110"), new BigDecimal("55"),
                version);
    }

    private static TenantQuotaController.AdjustmentBody body(String reasonCode) {
        return new TenantQuotaController.AdjustmentBody(
                "quota-1", new BigDecimal("2000"), new BigDecimal("900"), 7L, reasonCode);
    }

    @Test void readsTheAllowanceForAViewer() {
        QuotaAdministrationView expected = view(7);
        when(billing.quotaForAdministration("org-1")).thenReturn(expected);

        assertSame(expected, controller.quota(KEY, "org-1", "actor-1", "VIEWER"));
    }

    /**
     * The read floor is VIEWER on purpose. Raising it to APPROVER would push
     * operators to borrow an approver credential just to look at a number, which
     * costs more security than it buys.
     */
    @Test void refusesAReadFromAnUnknownRole() {
        assertThrows(RuntimeException.class,
                () -> controller.quota(KEY, "org-1", "actor-1", "AUDITOR"));
        verify(billing, never()).quotaForAdministration(anyString());
    }

    @Test void adjustsForAnApproverAndReturnsTheStateAfterTheChange() {
        QuotaAdministrationView after = view(8);
        when(billing.adjustQuota(
                "org-1", "actor-1", "quota-1",
                new BigDecimal("2000"), new BigDecimal("900"), 7L, "PLAN_UPGRADE"))
                .thenReturn(after);

        assertEquals(8, controller
                .adjust(KEY, "org-1", "actor-1", "APPROVER", body("PLAN_UPGRADE"))
                .allocationVersion());
    }

    /**
     * An OPERATOR may acknowledge an alert but may not change what a paying
     * tenant is allowed to do. If this ever starts passing, the write floor has
     * silently dropped a level.
     */
    @Test void refusesAnAdjustmentFromAnOperator() {
        assertThrows(RuntimeException.class,
                () -> controller.adjust(KEY, "org-1", "actor-1", "OPERATOR", body("PLAN_UPGRADE")));
        verify(billing, never()).adjustQuota(
                anyString(), anyString(), anyString(), any(), any(), anyLong(), anyString());
    }

    /**
     * The reason lands in an append-only event log and from there in the audit
     * CSV export. Free text there is a delimiter injection and an unanswerable
     * audit trail at the same time, so the token shape is enforced here.
     */
    @Test void refusesAFreeTextReason() {
        for (String reason : new String[] {
                null, "", "upgrade", "PLAN UPGRADE", "PLAN,UPGRADE", "PLAN\nUPGRADE", "AB"}) {
            assertThrows(IllegalArgumentException.class,
                    () -> controller.adjust(KEY, "org-1", "actor-1", "APPROVER", body(reason)),
                    () -> "reason should have been refused: " + reason);
        }
        verify(billing, never()).adjustQuota(
                anyString(), anyString(), anyString(), any(), any(), anyLong(), anyString());
    }

    @Test void refusesANegativeOrUnboundedLimit() {
        var negative = new TenantQuotaController.AdjustmentBody(
                "quota-1", new BigDecimal("-1"), new BigDecimal("900"), 7L, "PLAN_UPGRADE");
        var unbounded = new TenantQuotaController.AdjustmentBody(
                "quota-1", new BigDecimal("1000"), new BigDecimal("1000000001"), 7L, "PLAN_UPGRADE");
        var missing = new TenantQuotaController.AdjustmentBody(
                "quota-1", null, new BigDecimal("900"), 7L, "PLAN_UPGRADE");

        assertThrows(IllegalArgumentException.class,
                () -> controller.adjust(KEY, "org-1", "actor-1", "APPROVER", negative));
        assertThrows(IllegalArgumentException.class,
                () -> controller.adjust(KEY, "org-1", "actor-1", "APPROVER", unbounded));
        assertThrows(IllegalArgumentException.class,
                () -> controller.adjust(KEY, "org-1", "actor-1", "APPROVER", missing));
        verify(billing, never()).adjustQuota(
                anyString(), anyString(), anyString(), any(), any(), anyLong(), anyString());
    }

    @Test void refusesAMalformedAllocationIdentifier() {
        var injected = new TenantQuotaController.AdjustmentBody(
                "quota 1; drop", new BigDecimal("2000"), new BigDecimal("900"), 7L, "PLAN_UPGRADE");

        assertThrows(IllegalArgumentException.class,
                () -> controller.adjust(KEY, "org-1", "actor-1", "APPROVER", injected));
        verify(billing, never()).adjustQuota(
                anyString(), anyString(), anyString(), any(), any(), anyLong(), anyString());
    }

    /**
     * The version travels through untouched. A controller that defaulted or
     * "corrected" it would defeat the only thing stopping two operators from
     * overwriting each other's change.
     */
    @Test void forwardsTheExpectedVersionUnchanged() {
        when(billing.adjustQuota(
                anyString(), anyString(), anyString(), any(), any(), anyLong(), anyString()))
                .thenReturn(view(8));

        controller.adjust(KEY, "org-1", "actor-1", "APPROVER", body("PLAN_UPGRADE"));

        verify(billing).adjustQuota(
                "org-1", "actor-1", "quota-1",
                new BigDecimal("2000"), new BigDecimal("900"), 7L, "PLAN_UPGRADE");
    }

    /** A wrong operations key must not reach billing at all. */
    @Test void refusesAWrongOperationsKey() {
        assertThrows(SecurityException.class,
                () -> controller.quota("wrong-key-but-long-enough-32-chars", "org-1", "actor-1", "VIEWER"));
        assertThrows(SecurityException.class,
                () -> controller.adjust(
                        "wrong-key-but-long-enough-32-chars", "org-1", "actor-1", "APPROVER",
                        body("PLAN_UPGRADE")));
        verify(billing, never()).quotaForAdministration(anyString());
        verify(billing, never()).adjustQuota(
                anyString(), anyString(), anyString(), any(), any(), anyLong(), anyString());
    }
}
