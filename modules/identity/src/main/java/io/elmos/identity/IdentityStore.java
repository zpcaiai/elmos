package io.elmos.identity;

import java.util.List;
import java.util.Optional;

/**
 * Persistence boundary for the authentication service.
 *
 * <p>Every method maps onto a V55/V56 function or table. The service above it
 * contains the policy; this interface contains no decisions, so the security
 * behaviour can be read in one file rather than inferred from SQL.</p>
 */
public interface IdentityStore {

    final class StoreException extends RuntimeException {
        private static final long serialVersionUID = 1L;
        private final String code;

        public StoreException(String code) {
            super(code);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    record Account(
            String accountId,
            String status,
            String displayName,
            boolean phoneVerified,
            boolean emailVerified,
            int failedSignInCount,
            boolean locked) {
    }

    record Membership(String organizationId, String displayName, String role, String actorId) {
    }

    record SessionRecord(
            String sessionId,
            String accountId,
            String organizationId,
            java.time.Instant absoluteExpiresAt,
            java.time.Instant idleExpiresAt) {
    }

    enum RotationOutcome { ROTATED, REUSED, REJECTED }

    record Rotation(RotationOutcome outcome, String sessionId, String accountId, String organizationId) {
    }

    // ---- challenges --------------------------------------------------------

    /**
     * @return false when a rate limit or missing provider stopped the issue; the
     *         service turns that into a uniform response
     */
    boolean issueChallenge(String challengeId, Destinations.Channel channel, String destinationHmac,
                           String purpose, String codeSha256, int ttlSeconds, String clientPrefix);

    /** @return the challenge id on success, empty on every kind of failure */
    Optional<String> consumeChallenge(String destinationHmac, String purpose, String codeSha256);

    // ---- accounts ----------------------------------------------------------

    Optional<Account> findByPhoneHmac(String phoneLookupHmac);

    Optional<Account> findByEmail(String normalizedEmail);

    Optional<Account> findById(String accountId);

    String createPhoneAccount(String accountId, String displayName, String phoneLookupHmac,
                              String phoneLast4, String phoneCipherRef);

    String createEmailAccount(String accountId, String displayName, String email);

    /** Atomic: activate, provision the organization, grant the trial. */
    String completeSignup(String accountId, String organizationId, String organizationName,
                          String ownerActorId, String verifiedSubjectHash, String dataRegion);

    void clearSignInFailures(String accountId);

    /** @return true when the account is now locked */
    boolean recordSignInFailure(String accountId, int maxFailures, int lockSeconds);

    List<Membership> membershipsOf(String accountId);

    // ---- sessions ----------------------------------------------------------

    String openSession(String sessionId, String accountId, String organizationId,
                       String refreshTokenSha256, int absoluteSeconds, int idleSeconds,
                       List<String> amr, String deviceLabel, String clientFamily, String ipPrefix);

    Rotation rotateSession(String presentedSha256, String nextSha256, int idleSeconds);

    Optional<Membership> switchSessionOrganization(
            String sessionId, String accountId, String organizationId);

    void revokeSession(String sessionId, String reasonCode);

    Optional<SessionRecord> findSessionByToken(String refreshTokenSha256);

    void recordSecurityEvent(String eventId, String accountId, String eventType,
                             String outcome, String failureCode, String ipPrefix, String clientFamily);
}
