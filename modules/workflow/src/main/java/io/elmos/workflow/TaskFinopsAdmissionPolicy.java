package io.elmos.workflow;

import java.util.Objects;

/**
 * Pure admission policy for tenant/account task demand.
 *
 * <p>The policy evaluates one authenticated account context against a caller
 * supplied, scope-bound quota snapshot. It has no database, provider, clock,
 * queue, or workflow SDK dependency. A snapshot marked {@link SnapshotState#UNKNOWN}
 * always delays admission; unknown capacity is never treated as available.</p>
 *
 * <p>Resource units describe in-flight demand and therefore include both
 * active and queued roots. The platform quota is the hard account-wide active
 * root limit; tenant and account plans may lower it but cannot raise it above
 * {@link #PLATFORM_ACTIVE_ROOT_LIMIT}.</p>
 */
public final class TaskFinopsAdmissionPolicy {
    /** The repository-wide hard maximum for active root tasks per account. */
    public static final int PLATFORM_ACTIVE_ROOT_LIMIT =
            TaskFinopsPolicy.MAX_ACCOUNT_ROOT_TASKS;

    /** Matches the V77 resource-unit column bound. */
    public static final int MAX_REQUEST_RESOURCE_UNITS = 64;

    public enum RequestedState {
        ACTIVE_ROOT,
        QUEUED_ROOT
    }

    public enum Decision {
        ADMIT,
        DELAY
    }

    /** Stable reasons suitable for a caller or audit event; no provider text crosses this boundary. */
    public enum Reason {
        ADMITTED,
        TENANT_ACTIVE_ROOT_QUOTA_EXCEEDED,
        ACCOUNT_ACTIVE_ROOT_QUOTA_EXCEEDED,
        PLATFORM_ACTIVE_ROOT_QUOTA_EXCEEDED,
        TENANT_QUEUED_ROOT_QUOTA_EXCEEDED,
        ACCOUNT_QUEUED_ROOT_QUOTA_EXCEEDED,
        TENANT_RESOURCE_UNIT_QUOTA_EXCEEDED,
        ACCOUNT_RESOURCE_UNIT_QUOTA_EXCEEDED,
        QUOTA_SNAPSHOT_UNKNOWN,
        CONTEXT_MISMATCH
    }

    /**
     * Effective quotas for the tenant and the selected account.
     *
     * <p>A zero limit is valid and means that the corresponding demand is
     * disabled. The platform limit is always positive and cannot exceed the
     * repository hard maximum.</p>
     */
    public record QuotaLimits(
            int tenantActiveRootLimit,
            int tenantQueuedRootLimit,
            int tenantResourceUnitLimit,
            int accountActiveRootLimit,
            int accountQueuedRootLimit,
            int accountResourceUnitLimit,
            int platformActiveRootLimit
    ) {
        public QuotaLimits {
            requireLimit(tenantActiveRootLimit, "TENANT_ACTIVE_ROOT");
            requireLimit(tenantQueuedRootLimit, "TENANT_QUEUED_ROOT");
            requireLimit(tenantResourceUnitLimit, "TENANT_RESOURCE_UNITS");
            requireLimit(accountActiveRootLimit, "ACCOUNT_ACTIVE_ROOT");
            requireLimit(accountQueuedRootLimit, "ACCOUNT_QUEUED_ROOT");
            requireLimit(accountResourceUnitLimit, "ACCOUNT_RESOURCE_UNITS");
            if (platformActiveRootLimit < 1
                    || platformActiveRootLimit > PLATFORM_ACTIVE_ROOT_LIMIT) {
                throw new IllegalArgumentException("ELMOS_MTF_PLATFORM_QUOTA_INVALID");
            }
            if (accountActiveRootLimit > platformActiveRootLimit) {
                throw new IllegalArgumentException("ELMOS_MTF_ACCOUNT_PLATFORM_QUOTA_INVALID");
            }
        }
    }

    /**
     * Current in-flight demand. Account usage must be a subset of the tenant
     * usage because the authenticated account belongs to that tenant.
     */
    public record UsageSnapshot(
            int tenantActiveRootTasks,
            int tenantQueuedRootTasks,
            int tenantResourceUnits,
            int accountActiveRootTasks,
            int accountQueuedRootTasks,
            int accountResourceUnits
    ) {
        public UsageSnapshot {
            requireUsage(tenantActiveRootTasks, "TENANT_ACTIVE_ROOT");
            requireUsage(tenantQueuedRootTasks, "TENANT_QUEUED_ROOT");
            requireUsage(tenantResourceUnits, "TENANT_RESOURCE_UNITS");
            requireUsage(accountActiveRootTasks, "ACCOUNT_ACTIVE_ROOT");
            requireUsage(accountQueuedRootTasks, "ACCOUNT_QUEUED_ROOT");
            requireUsage(accountResourceUnits, "ACCOUNT_RESOURCE_UNITS");
            if (accountActiveRootTasks > tenantActiveRootTasks
                    || accountQueuedRootTasks > tenantQueuedRootTasks
                    || accountResourceUnits > tenantResourceUnits) {
                throw new IllegalArgumentException("ELMOS_MTF_USAGE_SCOPE_INVALID");
            }
        }
    }

    public enum SnapshotState {
        KNOWN,
        UNKNOWN
    }

    /**
     * A quota snapshot is explicitly bound to the authenticated organization,
     * account, and actor scope that requested the decision. The request ID is
     * deliberately excluded from the scope comparison because it changes per
     * operation and is an audit/idempotency field, not tenant authority.
     * Unknown snapshots intentionally carry no values.
     */
    public record QuotaSnapshot(
            TaskFinopsPort.AuthenticatedContext context,
            SnapshotState state,
            QuotaLimits limits,
            UsageSnapshot usage
    ) {
        public QuotaSnapshot {
            Objects.requireNonNull(context, "context");
            Objects.requireNonNull(state, "state");
            if (state == SnapshotState.KNOWN
                    && (limits == null || usage == null)) {
                throw new IllegalArgumentException("ELMOS_MTF_QUOTA_SNAPSHOT_INVALID");
            }
            if (state == SnapshotState.UNKNOWN
                    && (limits != null || usage != null)) {
                throw new IllegalArgumentException("ELMOS_MTF_UNKNOWN_QUOTA_VALUES");
            }
        }

        public static QuotaSnapshot known(
                TaskFinopsPort.AuthenticatedContext context,
                QuotaLimits limits,
                UsageSnapshot usage
        ) {
            return new QuotaSnapshot(context, SnapshotState.KNOWN,
                    Objects.requireNonNull(limits, "limits"),
                    Objects.requireNonNull(usage, "usage"));
        }

        public static QuotaSnapshot unknown(TaskFinopsPort.AuthenticatedContext context) {
            return new QuotaSnapshot(context, SnapshotState.UNKNOWN, null, null);
        }
    }

    /** Untrusted request data; tenant and actor authority come only from context. */
    public record AdmissionRequest(
            TaskFinopsPort.AuthenticatedContext context,
            RequestedState requestedState,
            int resourceUnits
    ) {
        public AdmissionRequest {
            Objects.requireNonNull(context, "context");
            Objects.requireNonNull(requestedState, "requestedState");
            if (resourceUnits < 1 || resourceUnits > MAX_REQUEST_RESOURCE_UNITS) {
                throw new IllegalArgumentException("ELMOS_MTF_RESOURCE_UNITS_INVALID");
            }
        }
    }

    /** The only result emitted by this policy: explicit decision, reason, and bound context. */
    public record DecisionResult(
            TaskFinopsPort.AuthenticatedContext context,
            Decision decision,
            Reason reason
    ) {
        public DecisionResult {
            Objects.requireNonNull(context, "context");
            Objects.requireNonNull(decision, "decision");
            Objects.requireNonNull(reason, "reason");
            if ((decision == Decision.ADMIT) != (reason == Reason.ADMITTED)) {
                throw new IllegalArgumentException("ELMOS_MTF_DECISION_REASON_INVALID");
            }
        }

        public boolean admitted() {
            return decision == Decision.ADMIT;
        }

        public boolean delayed() {
            return decision == Decision.DELAY;
        }
    }

    private TaskFinopsAdmissionPolicy() {}

    /**
     * Evaluates one root-task request against a context-bound snapshot.
     *
     * <p>For an active request, active-root quotas and the platform hard limit
     * are checked. For a queued request, queued-root quotas are checked. Both
     * states consume resource-unit quota because queued work is still admitted
     * demand and must not bypass backpressure.</p>
     */
    public static DecisionResult evaluate(
            AdmissionRequest request,
            QuotaSnapshot snapshot
    ) {
        Objects.requireNonNull(request, "request");
        Objects.requireNonNull(snapshot, "snapshot");
        if (!sameScope(request.context(), snapshot.context())) {
            return delay(request.context(), Reason.CONTEXT_MISMATCH);
        }
        if (snapshot.state() == SnapshotState.UNKNOWN) {
            return delay(request.context(), Reason.QUOTA_SNAPSHOT_UNKNOWN);
        }

        QuotaLimits limits = snapshot.limits();
        UsageSnapshot usage = snapshot.usage();
        long projectedTenantResourceUnits = (long) usage.tenantResourceUnits()
                + request.resourceUnits();
        if (projectedTenantResourceUnits > limits.tenantResourceUnitLimit()) {
            return delay(request.context(), Reason.TENANT_RESOURCE_UNIT_QUOTA_EXCEEDED);
        }
        long projectedAccountResourceUnits = (long) usage.accountResourceUnits()
                + request.resourceUnits();
        if (projectedAccountResourceUnits > limits.accountResourceUnitLimit()) {
            return delay(request.context(), Reason.ACCOUNT_RESOURCE_UNIT_QUOTA_EXCEEDED);
        }

        long projectedAccountActive = usage.accountActiveRootTasks();
        if (usage.accountActiveRootTasks() > limits.platformActiveRootLimit()) {
            return delay(request.context(), Reason.PLATFORM_ACTIVE_ROOT_QUOTA_EXCEEDED);
        }
        if (request.requestedState() == RequestedState.ACTIVE_ROOT) {
            long projectedTenantActive = (long) usage.tenantActiveRootTasks() + 1;
            if (projectedTenantActive > limits.tenantActiveRootLimit()) {
                return delay(request.context(), Reason.TENANT_ACTIVE_ROOT_QUOTA_EXCEEDED);
            }
            projectedAccountActive++;
            if (projectedAccountActive > limits.platformActiveRootLimit()) {
                return delay(request.context(), Reason.PLATFORM_ACTIVE_ROOT_QUOTA_EXCEEDED);
            }
            if (projectedAccountActive > limits.accountActiveRootLimit()) {
                return delay(request.context(), Reason.ACCOUNT_ACTIVE_ROOT_QUOTA_EXCEEDED);
            }
        } else {
            long projectedTenantQueued = (long) usage.tenantQueuedRootTasks() + 1;
            if (projectedTenantQueued > limits.tenantQueuedRootLimit()) {
                return delay(request.context(), Reason.TENANT_QUEUED_ROOT_QUOTA_EXCEEDED);
            }
            long projectedAccountQueued = (long) usage.accountQueuedRootTasks() + 1;
            if (projectedAccountQueued > limits.accountQueuedRootLimit()) {
                return delay(request.context(), Reason.ACCOUNT_QUEUED_ROOT_QUOTA_EXCEEDED);
            }
        }
        return new DecisionResult(request.context(), Decision.ADMIT, Reason.ADMITTED);
    }

    private static DecisionResult delay(
            TaskFinopsPort.AuthenticatedContext context,
            Reason reason
    ) {
        return new DecisionResult(context, Decision.DELAY, reason);
    }

    private static boolean sameScope(
            TaskFinopsPort.AuthenticatedContext left,
            TaskFinopsPort.AuthenticatedContext right
    ) {
        return left.organizationId().equals(right.organizationId())
                && left.accountId().equals(right.accountId())
                && left.actorId().equals(right.actorId());
    }

    private static void requireLimit(int value, String field) {
        if (value < 0) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_LIMIT_INVALID");
        }
    }

    private static void requireUsage(int value, String field) {
        if (value < 0) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_USAGE_INVALID");
        }
    }
}
