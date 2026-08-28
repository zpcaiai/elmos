package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TaskFinopsAdmissionPolicyTest {
    private static final TaskFinopsPort.AuthenticatedContext CONTEXT =
            new TaskFinopsPort.AuthenticatedContext(
                    "org-a", "account-a", "actor-a", "request-a");
    private static final TaskFinopsPort.AuthenticatedContext OTHER_CONTEXT =
            new TaskFinopsPort.AuthenticatedContext(
                    "org-a", "account-b", "actor-b", "request-b");

    @Test
    void admitsKnownDemandWhenTenantAccountAndPlatformLimitsHaveCapacity() {
        var result = TaskFinopsAdmissionPolicy.evaluate(
                request(TaskFinopsAdmissionPolicy.RequestedState.ACTIVE_ROOT, 2),
                snapshot(limits(4, 4, 12, 2, 3, 8, 3),
                        usage(1, 1, 4, 1, 0, 2)));

        assertTrue(result.admitted());
        assertEquals(TaskFinopsAdmissionPolicy.Decision.ADMIT, result.decision());
        assertEquals(TaskFinopsAdmissionPolicy.Reason.ADMITTED, result.reason());
        assertEquals(CONTEXT, result.context());
    }

    @Test
    void delaysActiveDemandAtAccountThenPlatformQuota() {
        var accountLimited = TaskFinopsAdmissionPolicy.evaluate(
                request(TaskFinopsAdmissionPolicy.RequestedState.ACTIVE_ROOT, 1),
                snapshot(limits(8, 8, 32, 2, 8, 32, 3),
                        usage(2, 0, 2, 2, 0, 2)));
        assertEquals(TaskFinopsAdmissionPolicy.Reason.ACCOUNT_ACTIVE_ROOT_QUOTA_EXCEEDED,
                accountLimited.reason());

        var platformLimited = TaskFinopsAdmissionPolicy.evaluate(
                request(TaskFinopsAdmissionPolicy.RequestedState.ACTIVE_ROOT, 1),
                snapshot(limits(8, 8, 32, 3, 8, 32, 3),
                        usage(3, 0, 3, 3, 0, 3)));
        assertEquals(TaskFinopsAdmissionPolicy.Reason.PLATFORM_ACTIVE_ROOT_QUOTA_EXCEEDED,
                platformLimited.reason());
        assertTrue(platformLimited.delayed());
    }

    @Test
    void delaysQueuedDemandForQueuedRootAndResourceUnitLimits() {
        var queuedLimited = TaskFinopsAdmissionPolicy.evaluate(
                request(TaskFinopsAdmissionPolicy.RequestedState.QUEUED_ROOT, 1),
                snapshot(limits(8, 1, 32, 3, 2, 32, 3),
                        usage(1, 1, 4, 1, 1, 4)));
        assertEquals(TaskFinopsAdmissionPolicy.Reason.TENANT_QUEUED_ROOT_QUOTA_EXCEEDED,
                queuedLimited.reason());

        var resourceLimited = TaskFinopsAdmissionPolicy.evaluate(
                request(TaskFinopsAdmissionPolicy.RequestedState.QUEUED_ROOT, 3),
                snapshot(limits(8, 8, 6, 3, 8, 6, 3),
                        usage(1, 1, 5, 1, 0, 5)));
        assertEquals(TaskFinopsAdmissionPolicy.Reason.TENANT_RESOURCE_UNIT_QUOTA_EXCEEDED,
                resourceLimited.reason());
    }

    @Test
    void unknownOrMismatchedSnapshotsFailClosed() {
        var unknown = TaskFinopsAdmissionPolicy.evaluate(
                request(TaskFinopsAdmissionPolicy.RequestedState.ACTIVE_ROOT, 1),
                TaskFinopsAdmissionPolicy.QuotaSnapshot.unknown(CONTEXT));
        assertEquals(TaskFinopsAdmissionPolicy.Decision.DELAY, unknown.decision());
        assertEquals(TaskFinopsAdmissionPolicy.Reason.QUOTA_SNAPSHOT_UNKNOWN,
                unknown.reason());

        var mismatched = TaskFinopsAdmissionPolicy.evaluate(
                request(TaskFinopsAdmissionPolicy.RequestedState.ACTIVE_ROOT, 1),
                TaskFinopsAdmissionPolicy.QuotaSnapshot.known(
                        OTHER_CONTEXT, limits(4, 4, 12, 2, 3, 8, 3),
                        usage(1, 1, 4, 1, 0, 2)));
        assertEquals(TaskFinopsAdmissionPolicy.Reason.CONTEXT_MISMATCH,
                mismatched.reason());
    }

    @Test
    void requestIdsDoNotChangeTheTenantAccountActorScope() {
        var snapshotContext = new TaskFinopsPort.AuthenticatedContext(
                "org-a", "account-a", "actor-a", "different-request");
        var result = TaskFinopsAdmissionPolicy.evaluate(
                request(TaskFinopsAdmissionPolicy.RequestedState.ACTIVE_ROOT, 1),
                TaskFinopsAdmissionPolicy.QuotaSnapshot.known(
                        snapshotContext, limits(4, 4, 12, 2, 3, 8, 3),
                        usage(1, 1, 4, 1, 0, 2)));

        assertEquals(TaskFinopsAdmissionPolicy.Reason.ADMITTED, result.reason());
    }

    @Test
    void rejectsInvalidQuotaAndUsageShapes() {
        assertThrows(IllegalArgumentException.class,
                () -> limits(4, 4, 12, 4, 3, 8, 3));
        assertThrows(IllegalArgumentException.class,
                () -> limits(4, 4, 12, 2, 3, 8, 4));
        assertThrows(IllegalArgumentException.class,
                () -> usage(1, 0, 1, 2, 0, 1));
        assertThrows(IllegalArgumentException.class,
                () -> request(TaskFinopsAdmissionPolicy.RequestedState.ACTIVE_ROOT, 65));
    }

    private static TaskFinopsAdmissionPolicy.AdmissionRequest request(
            TaskFinopsAdmissionPolicy.RequestedState state,
            int resourceUnits
    ) {
        return new TaskFinopsAdmissionPolicy.AdmissionRequest(
                CONTEXT, state, resourceUnits);
    }

    private static TaskFinopsAdmissionPolicy.QuotaSnapshot snapshot(
            TaskFinopsAdmissionPolicy.QuotaLimits limits,
            TaskFinopsAdmissionPolicy.UsageSnapshot usage
    ) {
        return TaskFinopsAdmissionPolicy.QuotaSnapshot.known(CONTEXT, limits, usage);
    }

    private static TaskFinopsAdmissionPolicy.QuotaLimits limits(
            int tenantActive,
            int tenantQueued,
            int tenantResources,
            int accountActive,
            int accountQueued,
            int accountResources,
            int platformActive
    ) {
        return new TaskFinopsAdmissionPolicy.QuotaLimits(
                tenantActive, tenantQueued, tenantResources,
                accountActive, accountQueued, accountResources, platformActive);
    }

    private static TaskFinopsAdmissionPolicy.UsageSnapshot usage(
            int tenantActive,
            int tenantQueued,
            int tenantResources,
            int accountActive,
            int accountQueued,
            int accountResources
    ) {
        return new TaskFinopsAdmissionPolicy.UsageSnapshot(
                tenantActive, tenantQueued, tenantResources,
                accountActive, accountQueued, accountResources);
    }
}
