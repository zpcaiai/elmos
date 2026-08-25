package io.elmos.commercial;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/**
 * The platform-wide administration surface.
 *
 * <p>Every method takes the administrator's account id as its first argument
 * and returns a status alongside the data. That is not ceremony: the underlying
 * V75 functions refuse by returning no rows and an audit row, never by raising,
 * so that a refused access still leaves a trace. An adapter that translated a
 * refusal into an exception would be discarding the distinction between
 * "refused" and "nothing to show", which are very different answers to
 * "why is this list empty".
 */
public interface PlatformAdminPort {

    /** Outcome of an attempted platform operation, mirroring the V75 codes. */
    enum Decision { ALLOWED, DENIED_NOT_ADMIN, DENIED_ROLE, DENIED_POLICY, DENIED_LAST_APPROVER;

        public static Decision parse(String value) {
            if (value == null) {
                return DENIED_POLICY;
            }
            for (Decision decision : values()) {
                if (decision.name().equals(value)) {
                    return decision;
                }
            }
            return DENIED_POLICY;
        }

        public boolean allowed() {
            return this == ALLOWED;
        }
    }

    record WalletRow(
            String organizationId, String displayName, String currency,
            BigDecimal balanceMinor, BigDecimal reservedMinor, BigDecimal spendableMinor,
            String walletStatus, long heldReservations, Instant updatedAt
    ) {}

    record LedgerRow(
            String entryId, long seq, String direction, BigDecimal amountMinor,
            BigDecimal balanceAfterMinor, String entryType, String sourceType,
            String sourceRef, String actorId, String reason, Instant occurredAt
    ) {}

    record TopupRow(
            String topupOrderId, String organizationId, String actorId,
            BigDecimal amountMinor, String provider, String outTradeNo, String status,
            Instant createdAt, Instant paidAt, Instant creditedAt
    ) {}

    record JobRow(
            String jobId, String organizationId, String businessLine, String jobKind,
            String status, String resultStatus, String failureCode,
            Instant createdAt, Instant startedAt, Instant finishedAt,
            BigDecimal settledAmountMinor, String holdStatus
    ) {}

    /**
     * An empty list is ambiguous on its own, so the decision travels with it.
     * The console shows "no access" and "nothing here" differently.
     */
    record Page<T>(Decision decision, List<T> rows) {
        public static <T> Page<T> denied(Decision decision) {
            return new Page<>(decision, List.of());
        }
    }

    /**
     * Maps a console session back to the account it belongs to.
     *
     * @return null when there is no live membership; callers must treat that as
     *         "not an administrator" rather than falling back to the actor id,
     *         which would put an unresolvable identity into the audit log
     */
    String resolveAdminAccount(String organizationId, String actorId);

    Page<WalletRow> wallets(String adminAccountId, String afterOrganizationId, int limit);

    Page<LedgerRow> ledger(String adminAccountId, String organizationId, int limit, int offset);

    Page<TopupRow> topups(String adminAccountId, String statusFilter, int limit);

    Page<JobRow> jobs(String adminAccountId, String statusFilter,
                      String organizationFilter, int limitPerOrganization);

    /** @return the ledger entry id when allowed, otherwise the refusal */
    record AdjustResult(Decision decision, String entryId) {}

    AdjustResult adjust(String adminAccountId, String organizationId, String direction,
                        BigDecimal amountMinor, String reason, String idempotencyKey);

    Decision grant(String adminAccountId, String targetAccountId,
                   String platformRole, String reason);

    Decision revoke(String adminAccountId, String targetAccountId, String reason);
}
