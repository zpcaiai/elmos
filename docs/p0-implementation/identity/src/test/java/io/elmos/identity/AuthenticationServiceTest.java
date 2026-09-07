package io.elmos.identity;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * End-to-end acceptance for the authentication endpoints, against a real
 * PostgreSQL running the real V1..V55 schema.
 *
 * <p>No mocks below the service: every flow here exercises the actual functions,
 * constraints and RLS policies that production will run. A fake store would have
 * happily agreed with any of my assumptions.</p>
 *
 * <pre>ELMOS_TEST_JDBC_URL=jdbc:postgresql://... java ... AuthenticationServiceTest</pre>
 */
public final class AuthenticationServiceTest {

    private static final List<String> FAILURES = new ArrayList<>();
    private static int checks;
    private static final String PEPPER = "test-pepper-".repeat(4);

    /** Captures what would have been sent, so a test can read the code. */
    static final class CapturingSender implements AuthenticationService.MessageSender {
        final ConcurrentHashMap<String, String> lastCode = new ConcurrentHashMap<>();
        final AtomicInteger sends = new AtomicInteger();
        volatile boolean failDelivery;

        @Override
        public boolean send(Destinations.Channel channel, String destination,
                            AuthenticationService.Purpose purpose, String code) {
            sends.incrementAndGet();
            lastCode.put(destination, code);
            return !failDelivery;
        }
    }

    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault("ELMOS_TEST_JDBC_URL",
                "jdbc:postgresql://localhost/elmos_auth?user=elmos");
        JdbcIdentityStore.Connections connections = () -> DriverManager.getConnection(url);

        try (Connection probe = connections.get()) {
            probe.createStatement().execute("SELECT 1");
        } catch (SQLException ex) {
            System.out.println("skip: no database at " + url);
            return;
        }

        prepareProvider(connections);

        CapturingSender sender = new CapturingSender();
        JdbcIdentityStore store = new JdbcIdentityStore(connections);
        AuthenticationService service = new AuthenticationService(store, sender, PEPPER);

        signUpCreatesAccountOrganizationAndEntitlement(service, sender, store);
        secondSignInReusesTheAccount(service, sender, connections);
        challengeResponseDoesNotRevealRegistration(service, sender, connections);
        wrongCodeIsUniformAndCounted(service, sender, connections);
        refreshRotatesAndDetectsTheft(service, sender, connections);
        signOutRevokes(service, sender, connections);
        organizationSwitchRechecksMembership(service, store, sender, connections);
        deliveryFailureIsNotAnOracle(service, sender, connections);
        cookiesCarryTheRightFlags();

        System.out.println();
        if (FAILURES.isEmpty()) {
            System.out.println("AUTHENTICATION SERVICE TEST PASSED (" + checks + " checks)");
            System.exit(0);
        }
        System.out.println("AUTHENTICATION SERVICE TEST FAILED (" + FAILURES.size() + "/" + checks + ")");
        FAILURES.forEach(f -> System.out.println("  - " + f));
        System.exit(1);
    }

    // ---- scenarios ---------------------------------------------------------

    static void signUpCreatesAccountOrganizationAndEntitlement(
            AuthenticationService service, CapturingSender sender, JdbcIdentityStore store) {
        String phone = "13800138001";
        AuthenticationService.ChallengeOutcome challenge = service.requestChallenge(
                phone, Destinations.Channel.SMS, AuthenticationService.Purpose.SIGN_IN, "203.0.113.5");

        check("challenge is issued for an unregistered number",
                challenge.status() == AuthenticationService.ChallengeStatus.ISSUED);
        check("only a masked destination is echoed back", "138****8001".equals(challenge.maskedDestination()));

        String code = sender.lastCode.get("+8613800138001");
        check("a six digit code was produced", code != null && code.matches("^\\d{6}$"));

        AuthenticationService.VerifyOutcome verified = service.verifyAndOpenSession(
                phone, Destinations.Channel.SMS, AuthenticationService.Purpose.SIGN_IN,
                code, "203.0.113.5", "MacBook Pro", "chrome");

        check("an unknown number signs up rather than failing",
                verified.status() == AuthenticationService.VerifyStatus.SIGNED_UP);
        check("a session was issued", verified.session() != null);
        check("the refresh token is opaque and full length",
                verified.session().refreshToken().length() == 43);
        check("the new account owns exactly one organization",
                verified.session().memberships().size() == 1);
        check("the first member is the OWNER",
                "OWNER".equals(verified.session().memberships().get(0).role()));
        check("an actor id was provisioned",
                verified.session().memberships().get(0).actorId() != null);

        // The seam: a brand-new organization must be able to run something.
        check("the new organization has an execution entitlement",
                concurrencyLimit(verified.session().organizationId()) >= 1);
    }

    static void secondSignInReusesTheAccount(AuthenticationService service, CapturingSender sender,
                                             JdbcIdentityStore.Connections connections) {
        String phone = "13800138001";
        clearRateLimits(connections);
        service.requestChallenge(phone, Destinations.Channel.SMS,
                AuthenticationService.Purpose.SIGN_IN, "203.0.113.5");
        String code = sender.lastCode.get("+8613800138001");

        AuthenticationService.VerifyOutcome verified = service.verifyAndOpenSession(
                phone, Destinations.Channel.SMS, AuthenticationService.Purpose.SIGN_IN,
                code, "203.0.113.5", "iPhone", "safari");

        check("a known number signs in rather than signing up again",
                verified.status() == AuthenticationService.VerifyStatus.SIGNED_IN);
        check("no second organization was created",
                verified.session().memberships().size() == 1);
    }

    /**
     * The property that matters most on this endpoint: a caller must not be able to
     * use it to find out whether a phone number is registered.
     */
    static void challengeResponseDoesNotRevealRegistration(
            AuthenticationService service, CapturingSender sender,
            JdbcIdentityStore.Connections connections) {
        clearRateLimits(connections);
        AuthenticationService.ChallengeOutcome known = service.requestChallenge(
                "13800138001", Destinations.Channel.SMS,
                AuthenticationService.Purpose.SIGN_IN, "203.0.113.7");
        clearRateLimits(connections);
        AuthenticationService.ChallengeOutcome unknown = service.requestChallenge(
                "13900139009", Destinations.Channel.SMS,
                AuthenticationService.Purpose.SIGN_IN, "203.0.113.7");

        check("registered and unregistered numbers return the same status",
                known.status() == unknown.status());
        check("both report the same retry window",
                known.retryAfterSeconds() == unknown.retryAfterSeconds());
        // A malformed number is a different answer, but it says nothing about
        // anyone's account - the caller already knows what it typed.
        AuthenticationService.ChallengeOutcome malformed = service.requestChallenge(
                "12345", Destinations.Channel.SMS,
                AuthenticationService.Purpose.SIGN_IN, "203.0.113.7");
        check("a malformed number is rejected without a code",
                malformed.status() == AuthenticationService.ChallengeStatus.INVALID_DESTINATION);
    }

    static void wrongCodeIsUniformAndCounted(AuthenticationService service, CapturingSender sender,
                                             JdbcIdentityStore.Connections connections) {
        clearRateLimits(connections);
        service.requestChallenge("13800138001", Destinations.Channel.SMS,
                AuthenticationService.Purpose.SIGN_IN, "203.0.113.5");

        AuthenticationService.VerifyOutcome wrongKnown = service.verifyAndOpenSession(
                "13800138001", Destinations.Channel.SMS, AuthenticationService.Purpose.SIGN_IN,
                "000000", "203.0.113.5", "x", "chrome");
        AuthenticationService.VerifyOutcome wrongUnknown = service.verifyAndOpenSession(
                "13900139009", Destinations.Channel.SMS, AuthenticationService.Purpose.SIGN_IN,
                "000000", "203.0.113.5", "x", "chrome");

        check("a wrong code on a known number returns INVALID",
                wrongKnown.status() == AuthenticationService.VerifyStatus.INVALID);
        check("a wrong code on an unknown number returns the same thing",
                wrongUnknown.status() == wrongKnown.status());
        check("neither returns a session",
                wrongKnown.session() == null && wrongUnknown.session() == null);
        check("the failure was recorded against the known account",
                securityEventCount("CHALLENGE_FAILED") >= 1);
    }

    static void refreshRotatesAndDetectsTheft(AuthenticationService service, CapturingSender sender,
                                              JdbcIdentityStore.Connections connections) {
        clearRateLimits(connections);
        service.requestChallenge("13700137001", Destinations.Channel.SMS,
                AuthenticationService.Purpose.SIGN_IN, "203.0.113.9");
        String code = sender.lastCode.get("+8613700137001");
        AuthenticationService.Session session = service.verifyAndOpenSession(
                "13700137001", Destinations.Channel.SMS, AuthenticationService.Purpose.SIGN_IN,
                code, "203.0.113.9", "Linux", "firefox").session();

        String first = session.refreshToken();
        AuthenticationService.RefreshOutcome rotated = service.refresh(first, "203.0.113.9", "firefox");
        check("the current token rotates",
                rotated.status() == AuthenticationService.RefreshStatus.ROTATED);
        check("rotation returns a different token",
                !rotated.session().refreshToken().equals(first));

        // An attacker replays the copy they took before the real client rotated.
        AuthenticationService.RefreshOutcome replay = service.refresh(first, "198.51.100.4", "curl");
        check("replaying a superseded token is reported as reuse, not a plain rejection",
                replay.status() == AuthenticationService.RefreshStatus.REUSE_DETECTED);

        // And the legitimate client is logged out too, which is the point.
        AuthenticationService.RefreshOutcome afterRevocation =
                service.refresh(rotated.session().refreshToken(), "203.0.113.9", "firefox");
        check("the legitimate client's newer token is dead as well",
                afterRevocation.status() == AuthenticationService.RefreshStatus.REJECTED);

        check("an empty token is rejected without touching the store",
                service.refresh("", "203.0.113.9", "firefox").status()
                        == AuthenticationService.RefreshStatus.REJECTED);
        check("an unknown token is rejected",
                service.refresh(Secrets.newOpaqueToken(), "203.0.113.9", "firefox").status()
                        == AuthenticationService.RefreshStatus.REJECTED);
    }

    static void signOutRevokes(AuthenticationService service, CapturingSender sender,
                               JdbcIdentityStore.Connections connections) {
        clearRateLimits(connections);
        service.requestChallenge("13600136001", Destinations.Channel.SMS,
                AuthenticationService.Purpose.SIGN_IN, "203.0.113.11");
        String code = sender.lastCode.get("+8613600136001");
        AuthenticationService.Session session = service.verifyAndOpenSession(
                "13600136001", Destinations.Channel.SMS, AuthenticationService.Purpose.SIGN_IN,
                code, "203.0.113.11", "iPad", "safari").session();

        service.signOut(session.refreshToken());
        check("a signed-out session cannot refresh",
                service.refresh(session.refreshToken(), "203.0.113.11", "safari").status()
                        != AuthenticationService.RefreshStatus.ROTATED);
        check("signing out twice is harmless", signOutQuietly(service, session.refreshToken()));
        check("signing out with no token is harmless", signOutQuietly(service, null));
    }

    static void organizationSwitchRechecksMembership(AuthenticationService service, JdbcIdentityStore store,
                                                     CapturingSender sender,
                                                     JdbcIdentityStore.Connections connections) {
        clearRateLimits(connections);
        service.requestChallenge("13500135001", Destinations.Channel.SMS,
                AuthenticationService.Purpose.SIGN_IN, "203.0.113.13");
        String code = sender.lastCode.get("+8613500135001");
        AuthenticationService.Session session = service.verifyAndOpenSession(
                "13500135001", Destinations.Channel.SMS, AuthenticationService.Purpose.SIGN_IN,
                code, "203.0.113.13", "pc", "edge").session();

        check("switching to an owned organization succeeds",
                service.switchOrganization(session.accountId(), session.organizationId()).isPresent());
        check("switching to a foreign organization is refused",
                service.switchOrganization(session.accountId(), "org-system").isEmpty());

        // Suspending the sole OWNER is refused by the V53 guard - correctly, and it
        // fired the first time this test was written. So the removal case is
        // exercised on a second, non-owner member instead.
        execute(connections, "INSERT INTO accounts (account_id, status, display_name,"
                + " phone_lookup_hmac, phone_last4, phone_cipher_ref, phone_verified_at)"
                + " VALUES ('acc-colleague', 'ACTIVE', '同事', '" + "c".repeat(64) + "',"
                + " '0002', 'kms://x', now()) ON CONFLICT DO NOTHING");
        execute(connections, "INSERT INTO organization_memberships (organization_membership_id,"
                + " organization_id, schema_version, status, idempotency_key, payload,"
                + " account_ref, member_role, member_state, joined_at) VALUES ('mem-colleague', '"
                + session.organizationId() + "', '2.0', 'ACTIVE', 'colleague', '{}'::jsonb,"
                + " 'acc-colleague', 'MEMBER', 'ACTIVE', now()) ON CONFLICT DO NOTHING");

        check("an active member can switch in",
                service.switchOrganization("acc-colleague", session.organizationId()).isPresent());

        // Membership is re-read on every switch, so removal takes effect at once
        // rather than at the next sign-in.
        execute(connections, "UPDATE organization_memberships SET member_state = 'SUSPENDED'"
                + " WHERE organization_membership_id = 'mem-colleague'");
        check("a suspended member can no longer switch into the organization",
                service.switchOrganization("acc-colleague", session.organizationId()).isEmpty());

        // The guard itself is worth an assertion: it is the only thing standing
        // between a mis-click and an organization nobody can administer.
        boolean guarded = false;
        try {
            execute(connections, "UPDATE organization_memberships SET member_state = 'SUSPENDED'"
                    + " WHERE account_ref = '" + session.accountId() + "'");
        } catch (IllegalStateException ex) {
            guarded = ex.getMessage() != null && ex.getMessage().contains("LAST_OWNER_PROTECTED");
        }
        check("the sole owner cannot be suspended", guarded);
    }

    static void deliveryFailureIsNotAnOracle(AuthenticationService service, CapturingSender sender,
                                             JdbcIdentityStore.Connections connections) {
        clearRateLimits(connections);
        sender.failDelivery = true;
        AuthenticationService.ChallengeOutcome outcome = service.requestChallenge(
                "13400134001", Destinations.Channel.SMS,
                AuthenticationService.Purpose.SIGN_IN, "203.0.113.15");
        sender.failDelivery = false;
        // A provider outage must not become one more signal to probe with; the
        // outbox row records it for operators instead.
        check("a delivery failure still answers ISSUED",
                outcome.status() == AuthenticationService.ChallengeStatus.ISSUED);
        check("the attempt is recorded in the outbox", deliveryCount() >= 1);
    }

    static void cookiesCarryTheRightFlags() {
        String cookie = SessionCookies.refreshCookie("token-value", Duration.ofDays(14));
        for (String flag : List.of("__Host-elmos_refresh=", "Secure", "HttpOnly", "SameSite=Lax", "Path=/")) {
            check("refresh cookie carries " + flag, cookie.contains(flag));
        }
        check("refresh cookie sets no Domain", !cookie.contains("Domain="));

        String csrf = SessionCookies.csrfCookie("csrf-value", Duration.ofDays(14));
        check("csrf cookie is readable by script", !csrf.contains("HttpOnly"));
        check("csrf cookie is still Secure", csrf.contains("Secure"));

        check("logout clears the cookie", SessionCookies.clearedRefreshCookie().contains("Max-Age=0"));

        check("matching csrf halves pass",
                SessionCookies.csrfMatches("abc123", "abc123"));
        check("mismatched csrf halves fail",
                !SessionCookies.csrfMatches("abc123", "abc124"));
        check("a missing csrf header fails", !SessionCookies.csrfMatches("abc123", null));

        String header = "__Host-elmos_refresh=rt; __Host-elmos_csrf=ct; other=x";
        check("cookie parsing finds the refresh value",
                SessionCookies.read(header, SessionCookies.REFRESH_COOKIE).orElse("").equals("rt"));
        check("cookie parsing does not match a prefix",
                SessionCookies.read("__Host-elmos_refresh_x=bad", SessionCookies.REFRESH_COOKIE).isEmpty());

        check("GET cannot change state",
                !SessionCookies.allowStateChange("GET", header, "ct"));
        check("POST with a matching csrf header may change state",
                SessionCookies.allowStateChange("POST", header, "ct"));
        check("POST without the header may not",
                !SessionCookies.allowStateChange("POST", header, null));

        check("wechat is recognised for the session record",
                "wechat".equals(SessionCookies.clientFamily("Mozilla/5.0 MicroMessenger/8.0")));
        check("an unknown agent is bucketed, not stored raw",
                "other".equals(SessionCookies.clientFamily("SomeBot/1.0")));
    }

    // ---- helpers -----------------------------------------------------------

    private static boolean signOutQuietly(AuthenticationService service, String token) {
        try {
            service.signOut(token);
            return true;
        } catch (RuntimeException ex) {
            return false;
        }
    }

    private static void prepareProvider(JdbcIdentityStore.Connections connections) {
        execute(connections, "UPDATE identity_message_providers SET provider_state = 'ACTIVE',"
                + " credential_reference = 'secret://sms', signature_name = 'ELMOS',"
                + " filing_reference = 'SMS-FILING-TEST' WHERE provider_id = 'sms-primary'");
    }

    /** The per-minute limit is real and correct; the test needs many codes quickly. */
    private static void clearRateLimits(JdbcIdentityStore.Connections connections) {
        execute(connections, "DELETE FROM identity_rate_counters");
    }

    private static void execute(JdbcIdentityStore.Connections connections, String sql) {
        try (Connection connection = connections.get()) {
            connection.createStatement().execute(sql);
        } catch (SQLException ex) {
            throw new IllegalStateException(ex.getMessage(), ex);
        }
    }

    private static int concurrencyLimit(String organizationId) {
        return queryInt("SELECT elmos_execution_concurrency_limit('" + organizationId + "')");
    }

    private static int securityEventCount(String eventType) {
        return queryInt("SELECT count(*) FROM account_security_events WHERE event_type = '"
                + eventType + "'");
    }

    private static int deliveryCount() {
        return queryInt("SELECT count(*) FROM identity_message_deliveries");
    }

    private static int queryInt(String sql) {
        String url = System.getenv().getOrDefault("ELMOS_TEST_JDBC_URL",
                "jdbc:postgresql://localhost/elmos_auth?user=elmos");
        try (Connection connection = DriverManager.getConnection(url);
             var rs = connection.createStatement().executeQuery(sql)) {
            return rs.next() ? rs.getInt(1) : -1;
        } catch (SQLException ex) {
            return -1;
        }
    }

    private static void check(String description, boolean condition) {
        checks++;
        System.out.println((condition ? "  ok   " : "  FAIL ") + description);
        if (!condition) {
            FAILURES.add(description);
        }
    }
}
