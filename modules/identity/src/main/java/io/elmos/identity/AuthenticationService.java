package io.elmos.identity;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.UUID;

/**
 * The authentication endpoints, minus HTTP.
 *
 * <p>All policy lives here so it can be read and tested in one place; the Spring
 * controller above is a thin translation to and from HTTP. That split exists
 * because the security-relevant decisions - what to reveal, when to lock, when to
 * revoke - must not be spread across annotations.</p>
 *
 * <p>The design commitment running through every method: <b>a caller learns
 * nothing about whether an account exists.</b> Requesting a code, verifying a
 * code, and failing to verify all look identical from outside regardless of
 * whether the destination is registered. Sign-up and sign-in are the same
 * endpoint and the server decides which one happened.</p>
 */
public final class AuthenticationService {

    /** Long enough to type from an SMS, short enough that a guessed code expires. */
    private static final int CODE_TTL_SECONDS = 300;
    private static final int CODE_DIGITS = 6;
    private static final int MAX_SIGN_IN_FAILURES = 5;
    private static final int LOCK_SECONDS = 900;
    private static final int SESSION_ABSOLUTE_SECONDS = 30 * 24 * 3600;
    private static final int SESSION_IDLE_SECONDS = 14 * 24 * 3600;

    public enum Purpose { SIGN_UP, SIGN_IN, ADD_CHANNEL, PASSWORD_RESET, DELETE_ACCOUNT }

    public interface MessageSender {
        /**
         * Delivers a code. Implementations must never log or persist it.
         *
         * @return false when the provider refused; the service still answers the
         *         caller uniformly so a delivery failure is not an oracle either
         */
        boolean send(Destinations.Channel channel, String normalizedDestination,
                     Purpose purpose, String code);
    }

    /** Refuses everything. The default, so an unconfigured deployment cannot pretend to send. */
    public static final MessageSender UNCONFIGURED_SENDER = (channel, destination, purpose, code) -> false;

    private final IdentityStore store;
    private final MessageSender sender;
    private final String pepper;

    public AuthenticationService(IdentityStore store, MessageSender sender, String pepper) {
        this.store = store;
        this.sender = sender;
        this.pepper = pepper;
    }

    // ---- request a code ----------------------------------------------------

    public enum ChallengeStatus { ISSUED, INVALID_DESTINATION, RATE_LIMITED }

    public record ChallengeOutcome(ChallengeStatus status, String maskedDestination, int retryAfterSeconds) {
    }

    /**
     * Issues a verification code.
     *
     * <p>Returns ISSUED whether or not an account exists. A response that differed
     * would turn this endpoint into a registration checker for any phone number.
     * Rate limiting is reported honestly because the caller already knows it asked
     * twice - that leaks nothing about anyone else.</p>
     */
    public ChallengeOutcome requestChallenge(String rawDestination, Destinations.Channel channel,
                                             Purpose purpose, String remoteAddress) {
        Optional<Destinations.Destination> parsed = parse(rawDestination, channel);
        if (parsed.isEmpty()) {
            return new ChallengeOutcome(ChallengeStatus.INVALID_DESTINATION, null, 0);
        }
        Destinations.Destination destination = parsed.get();
        String destinationHmac = Secrets.lookupHmac(pepper, destination.normalized());
        String code = Secrets.newNumericCode(CODE_DIGITS);
        String challengeId = "chal-" + UUID.randomUUID();

        boolean issued;
        try {
            issued = store.issueChallenge(challengeId, channel, destinationHmac, purpose.name(),
                    Secrets.sha256Hex(code), CODE_TTL_SECONDS,
                    Destinations.clientPrefix(remoteAddress));
        } catch (IdentityStore.StoreException ex) {
            // Rate limit or missing provider. Both are reported the same way, and
            // neither reveals anything about the destination's registration state.
            return new ChallengeOutcome(ChallengeStatus.RATE_LIMITED, destination.masked(), 60);
        }
        if (!issued) {
            return new ChallengeOutcome(ChallengeStatus.RATE_LIMITED, destination.masked(), 60);
        }

        // Delivery failure is deliberately not surfaced as a distinct status: the
        // outbox row records it for operators, and the user is told to check their
        // messages either way. A "provider down" response would be one more signal
        // to probe with.
        sender.send(channel, destination.normalized(), purpose, code);

        return new ChallengeOutcome(ChallengeStatus.ISSUED, destination.masked(), CODE_TTL_SECONDS);
    }

    // ---- verify a code and open a session ----------------------------------

    public enum VerifyStatus { SIGNED_IN, SIGNED_UP, INVALID, LOCKED, INVALID_DESTINATION }

    public record Session(
            String sessionId,
            String accountId,
            String organizationId,
            /** Returned exactly once; only its SHA-256 is stored. */
            String refreshToken,
            Duration absoluteLifetime,
            Duration idleLifetime,
            List<IdentityStore.Membership> memberships) {
    }

    public record VerifyOutcome(VerifyStatus status, Session session) {
        public static VerifyOutcome of(VerifyStatus status) {
            return new VerifyOutcome(status, null);
        }
    }

    /**
     * Verifies a code and returns a session.
     *
     * <p>Sign-up and sign-in are one endpoint. The client does not say which it
     * wants and cannot: telling the server "I am registering" would let it discover
     * that the number is already taken. The server checks after the code is proven
     * and creates the account only if there is none.</p>
     */
    public VerifyOutcome verifyAndOpenSession(String rawDestination, Destinations.Channel channel,
                                              Purpose purpose, String code, String remoteAddress,
                                              String deviceLabel, String clientFamily) {
        Optional<Destinations.Destination> parsed = parse(rawDestination, channel);
        if (parsed.isEmpty()) {
            return VerifyOutcome.of(VerifyStatus.INVALID_DESTINATION);
        }
        Destinations.Destination destination = parsed.get();
        String destinationHmac = Secrets.lookupHmac(pepper, destination.normalized());

        Optional<IdentityStore.Account> existing = channel == Destinations.Channel.SMS
                ? store.findByPhoneHmac(destinationHmac)
                : store.findByEmail(destination.normalized());

        // A locked account still consumes the code, so an attacker cannot use the
        // response to learn that this destination is locked - which would confirm
        // it is registered.
        Optional<String> challengeId = store.consumeChallenge(
                destinationHmac, purpose.name(), Secrets.sha256Hex(code));

        if (challengeId.isEmpty()) {
            existing.ifPresent(account -> {
                boolean locked = store.recordSignInFailure(account.accountId(),
                        MAX_SIGN_IN_FAILURES, LOCK_SECONDS);
                store.recordSecurityEvent("sec-" + UUID.randomUUID(), account.accountId(),
                        "CHALLENGE_FAILED", "FAILURE",
                        locked ? "ACCOUNT_LOCKED" : "CODE_INVALID",
                        Destinations.clientPrefix(remoteAddress), clientFamily);
            });
            return VerifyOutcome.of(VerifyStatus.INVALID);
        }

        if (existing.isPresent() && existing.get().locked()) {
            // Reported only after a correct code, so it is not an oracle: the
            // caller already proved control of the destination.
            return VerifyOutcome.of(VerifyStatus.LOCKED);
        }

        IdentityStore.Account account;
        VerifyStatus status;
        if (existing.isPresent()) {
            account = existing.get();
            store.clearSignInFailures(account.accountId());
            status = VerifyStatus.SIGNED_IN;
        } else {
            account = createAccountFor(destination, destinationHmac);
            provisionFirstOrganization(account, destination, destinationHmac);
            status = VerifyStatus.SIGNED_UP;
        }

        List<IdentityStore.Membership> memberships = store.membershipsOf(account.accountId());
        if (memberships.isEmpty()) {
            // An account with no organization cannot do anything. This should be
            // impossible after completeSignup, so treat it as a failure rather
            // than handing back a session that leads to an empty product.
            throw new IdentityStore.StoreException("ELMOS_ACCOUNT_HAS_NO_ORGANIZATION");
        }

        Session session = openSession(account, memberships, remoteAddress, deviceLabel, clientFamily,
                channel == Destinations.Channel.SMS ? "SMS_OTP" : "EMAIL_OTP");
        store.recordSecurityEvent("sec-" + UUID.randomUUID(), account.accountId(),
                status == VerifyStatus.SIGNED_UP ? "SIGN_UP" : "SIGN_IN", "SUCCESS", null,
                Destinations.clientPrefix(remoteAddress), clientFamily);
        return new VerifyOutcome(status, session);
    }

    // ---- refresh -----------------------------------------------------------

    public enum RefreshStatus { ROTATED, REUSE_DETECTED, REJECTED }

    public record RefreshOutcome(RefreshStatus status, Session session) {
    }

    /**
     * Rotates the refresh token.
     *
     * <p>REUSE_DETECTED means a superseded token was presented: two parties hold
     * the same secret, the session is already revoked by the store, and the caller
     * must be sent back to sign-in. It is deliberately distinguishable from
     * REJECTED in logs and metrics - it is a security event, not a stale tab.</p>
     */
    public RefreshOutcome refresh(String presentedToken, String remoteAddress, String clientFamily) {
        if (presentedToken == null || presentedToken.isBlank()) {
            return new RefreshOutcome(RefreshStatus.REJECTED, null);
        }
        String nextToken = Secrets.newOpaqueToken();
        IdentityStore.Rotation rotation = store.rotateSession(
                Secrets.sha256Hex(presentedToken), Secrets.sha256Hex(nextToken), SESSION_IDLE_SECONDS);

        switch (rotation.outcome()) {
            case REUSED -> {
                store.recordSecurityEvent("sec-" + UUID.randomUUID(), rotation.accountId(),
                        "SESSION_REVOKED", "BLOCKED", "REFRESH_TOKEN_REUSED",
                        Destinations.clientPrefix(remoteAddress), clientFamily);
                return new RefreshOutcome(RefreshStatus.REUSE_DETECTED, null);
            }
            case REJECTED -> {
                return new RefreshOutcome(RefreshStatus.REJECTED, null);
            }
            default -> {
                List<IdentityStore.Membership> memberships = store.membershipsOf(rotation.accountId());
                return new RefreshOutcome(RefreshStatus.ROTATED, new Session(
                        rotation.sessionId(), rotation.accountId(), rotation.organizationId(),
                        nextToken, Duration.ofSeconds(SESSION_ABSOLUTE_SECONDS),
                        Duration.ofSeconds(SESSION_IDLE_SECONDS), memberships));
            }
        }
    }

    public void signOut(String presentedToken) {
        if (presentedToken == null || presentedToken.isBlank()) {
            return;
        }
        store.findSessionByToken(Secrets.sha256Hex(presentedToken))
                .ifPresent(session -> store.revokeSession(session.sessionId(), "USER_SIGNED_OUT"));
    }

    // ---- organization switching -------------------------------------------

    /**
     * Switches the active organization.
     *
     * <p>The membership is re-checked from the store on every switch rather than
     * trusted from the session, so a removed member loses access at the next
     * switch instead of at the next sign-in.</p>
     */
    public Optional<Session> switchOrganization(Session session, String organizationId) {
        if (session == null || organizationId == null || organizationId.isBlank()) {
            return Optional.empty();
        }
        return store.switchSessionOrganization(
                        session.sessionId(), session.accountId(), organizationId)
                .map(membership -> new Session(
                        session.sessionId(),
                        session.accountId(),
                        membership.organizationId(),
                        session.refreshToken(),
                        session.absoluteLifetime(),
                        session.idleLifetime(),
                        store.membershipsOf(session.accountId())));
    }

    // ---- internals ---------------------------------------------------------

    private Optional<Destinations.Destination> parse(String raw, Destinations.Channel channel) {
        return channel == Destinations.Channel.SMS
                ? Destinations.normalizeChineseMobile(raw)
                : Destinations.normalizeEmail(raw);
    }

    private IdentityStore.Account createAccountFor(Destinations.Destination destination, String hmac) {
        String accountId = "acc-" + UUID.randomUUID();
        if (destination.channel() == Destinations.Channel.SMS) {
            String last4 = destination.normalized().substring(destination.normalized().length() - 4);
            // The cipher reference is what the KMS envelope produces. The plaintext
            // number is never a column.
            store.createPhoneAccount(accountId, destination.masked(), hmac, last4,
                    "kms://identity/" + accountId);
        } else {
            store.createEmailAccount(accountId, destination.masked(), destination.normalized());
        }
        return store.findById(accountId).orElseThrow(
                () -> new IdentityStore.StoreException("ELMOS_ACCOUNT_CREATE_FAILED"));
    }

    private void provisionFirstOrganization(IdentityStore.Account account,
                                            Destinations.Destination destination, String hmac) {
        String organizationId = "org-" + UUID.randomUUID();
        String actorId = actorIdFor(organizationId, account.accountId());
        // The verified subject hash is what enforces one trial per real person;
        // trial_grants holds a global UNIQUE on it.
        store.completeSignup(account.accountId(), organizationId,
                defaultOrganizationName(destination), actorId, hmac, "cn-north");
    }

    /**
     * Deterministic per (organization, account) so the same person always resolves
     * to the same actor id, which the audit, evidence and job records key on.
     */
    static String actorIdFor(String organizationId, String accountId) {
        return "actor-" + Secrets.sha256Hex(organizationId + ":" + accountId).substring(0, 32);
    }

    private static String defaultOrganizationName(Destinations.Destination destination) {
        return destination.masked() + " 的组织";
    }

    private Session openSession(IdentityStore.Account account, List<IdentityStore.Membership> memberships,
                                String remoteAddress, String deviceLabel, String clientFamily, String amr) {
        String sessionId = "sess-" + UUID.randomUUID();
        String refreshToken = Secrets.newOpaqueToken();
        String organizationId = memberships.get(0).organizationId();

        List<String> methods = new ArrayList<>();
        methods.add(amr);

        store.openSession(sessionId, account.accountId(), organizationId,
                Secrets.sha256Hex(refreshToken), SESSION_ABSOLUTE_SECONDS, SESSION_IDLE_SECONDS,
                methods, sanitizeLabel(deviceLabel), sanitizeLabel(clientFamily),
                Destinations.clientPrefix(remoteAddress));

        return new Session(sessionId, account.accountId(), organizationId, refreshToken,
                Duration.ofSeconds(SESSION_ABSOLUTE_SECONDS), Duration.ofSeconds(SESSION_IDLE_SECONDS),
                memberships);
    }

    /** Device labels are user-controlled and end up in an operator console. */
    static String sanitizeLabel(String value) {
        if (value == null) {
            return null;
        }
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < value.length() && out.length() < 64; i++) {
            char c = value.charAt(i);
            if (Character.isLetterOrDigit(c) || c == ' ' || c == '-' || c == '_' || c == '.') {
                out.append(c);
            }
        }
        String cleaned = out.toString().trim();
        return cleaned.isEmpty() ? null : cleaned.toLowerCase(Locale.ROOT);
    }
}
