package io.elmos.identity;

import java.sql.Array;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.function.Supplier;

/**
 * {@link IdentityStore} over plain JDBC.
 *
 * <p>No ORM and no Spring: every statement is a call to a V53/V55 function, so
 * this class contains no SQL logic of its own and the application role needs no
 * table grants at all. That is the point - "what can the web tier touch" is the
 * list of functions below, not an audit of privileges.</p>
 *
 * <p>PostgreSQL errors are translated into stable codes here. The driver's message
 * never escapes, so a failure cannot leak schema details into an HTTP response.</p>
 */
public final class JdbcIdentityStore implements IdentityStore {

    /** Supplies a connection per call; wire this to the pool. */
    public interface Connections {
        Connection get() throws SQLException;
    }

    private final Connections connections;

    public JdbcIdentityStore(Connections connections) {
        this.connections = connections;
    }

    // ---- challenges --------------------------------------------------------

    @Override
    public boolean issueChallenge(String challengeId, Destinations.Channel channel, String destinationHmac,
                                  String purpose, String codeSha256, int ttlSeconds, String clientPrefix) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT elmos_issue_verification_challenge(?, ?, ?, ?, ?, ?, ?)")) {
                statement.setString(1, challengeId);
                statement.setString(2, channel.name());
                statement.setString(3, destinationHmac);
                statement.setString(4, purpose);
                statement.setString(5, codeSha256);
                statement.setInt(6, ttlSeconds);
                statement.setString(7, clientPrefix);
                try (ResultSet rs = statement.executeQuery()) {
                    return rs.next() && rs.getBoolean(1);
                }
            }
        });
    }

    @Override
    public Optional<String> consumeChallenge(String destinationHmac, String purpose, String codeSha256) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT elmos_consume_verification_challenge(?, ?, ?)")) {
                statement.setString(1, destinationHmac);
                statement.setString(2, purpose);
                statement.setString(3, codeSha256);
                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        return Optional.<String>empty();
                    }
                    String value = rs.getString(1);
                    return Optional.ofNullable(value);
                }
            }
        });
    }

    // ---- accounts ----------------------------------------------------------

    @Override
    public Optional<Account> findByPhoneHmac(String phoneLookupHmac) {
        return findAccount("SELECT * FROM elmos_find_account_by_phone(?)", phoneLookupHmac);
    }

    @Override
    public Optional<Account> findByEmail(String normalizedEmail) {
        return findAccount("SELECT * FROM elmos_find_account_by_email(?)", normalizedEmail);
    }

    @Override
    public Optional<Account> findById(String accountId) {
        return findAccount("SELECT * FROM elmos_find_account(?)", accountId);
    }

    private Optional<Account> findAccount(String sql, String argument) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(sql)) {
                statement.setString(1, argument);
                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        return Optional.<Account>empty();
                    }
                    return Optional.of(new Account(
                            rs.getString("account_id"),
                            rs.getString("status"),
                            rs.getString("display_name"),
                            rs.getBoolean("phone_verified"),
                            rs.getBoolean("email_verified"),
                            rs.getShort("failed_sign_in_count"),
                            rs.getBoolean("locked")));
                }
            }
        });
    }

    @Override
    public String createPhoneAccount(String accountId, String displayName, String phoneLookupHmac,
                                     String phoneLast4, String phoneCipherRef) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT elmos_create_phone_account(?, ?, ?, ?, ?)")) {
                statement.setString(1, accountId);
                statement.setString(2, displayName);
                statement.setString(3, phoneLookupHmac);
                statement.setString(4, phoneLast4);
                statement.setString(5, phoneCipherRef);
                try (ResultSet rs = statement.executeQuery()) {
                    rs.next();
                    return rs.getString(1);
                }
            }
        });
    }

    @Override
    public String createEmailAccount(String accountId, String displayName, String email) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT elmos_create_email_account(?, ?, ?)")) {
                statement.setString(1, accountId);
                statement.setString(2, displayName);
                statement.setString(3, email);
                try (ResultSet rs = statement.executeQuery()) {
                    rs.next();
                    return rs.getString(1);
                }
            }
        });
    }

    @Override
    public String completeSignup(String accountId, String organizationId, String organizationName,
                                 String ownerActorId, String verifiedSubjectHash, String dataRegion) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT elmos_complete_signup(?, ?, ?, ?, ?, ?)")) {
                statement.setString(1, accountId);
                statement.setString(2, organizationId);
                statement.setString(3, organizationName);
                statement.setString(4, ownerActorId);
                statement.setString(5, verifiedSubjectHash);
                statement.setString(6, dataRegion);
                try (ResultSet rs = statement.executeQuery()) {
                    rs.next();
                    return rs.getString(1);
                }
            }
        });
    }

    @Override
    public void clearSignInFailures(String accountId) {
        withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT elmos_clear_sign_in_failures(?)")) {
                statement.setString(1, accountId);
                statement.execute();
                return null;
            }
        });
    }

    @Override
    public boolean recordSignInFailure(String accountId, int maxFailures, int lockSeconds) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT elmos_record_sign_in_failure(?, ?::smallint, ?)")) {
                statement.setString(1, accountId);
                statement.setInt(2, maxFailures);
                statement.setInt(3, lockSeconds);
                try (ResultSet rs = statement.executeQuery()) {
                    return rs.next() && rs.getBoolean(1);
                }
            }
        });
    }

    @Override
    public List<Membership> membershipsOf(String accountId) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT * FROM elmos_memberships_of_account(?)")) {
                statement.setString(1, accountId);
                try (ResultSet rs = statement.executeQuery()) {
                    List<Membership> memberships = new ArrayList<>();
                    while (rs.next()) {
                        memberships.add(new Membership(
                                rs.getString("organization_id"),
                                rs.getString("display_name"),
                                rs.getString("member_role"),
                                rs.getString("actor_id")));
                    }
                    return memberships;
                }
            }
        });
    }

    // ---- sessions ----------------------------------------------------------

    @Override
    public String openSession(String sessionId, String accountId, String organizationId,
                              String refreshTokenSha256, int absoluteSeconds, int idleSeconds,
                              List<String> amr, String deviceLabel, String clientFamily, String ipPrefix) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT elmos_open_session(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")) {
                Array methods = connection.createArrayOf("text", amr.toArray());
                statement.setString(1, sessionId);
                statement.setString(2, accountId);
                statement.setString(3, organizationId);
                statement.setString(4, refreshTokenSha256);
                statement.setInt(5, absoluteSeconds);
                statement.setInt(6, idleSeconds);
                statement.setArray(7, methods);
                statement.setString(8, deviceLabel);
                statement.setString(9, clientFamily);
                statement.setString(10, ipPrefix);
                try (ResultSet rs = statement.executeQuery()) {
                    rs.next();
                    return rs.getString(1);
                }
            }
        });
    }

    @Override
    public Rotation rotateSession(String presentedSha256, String nextSha256, int idleSeconds) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT * FROM elmos_rotate_session_token(?, ?, ?)")) {
                statement.setString(1, presentedSha256);
                statement.setString(2, nextSha256);
                statement.setInt(3, idleSeconds);
                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        return new Rotation(RotationOutcome.REJECTED, null, null, null);
                    }
                    return new Rotation(
                            RotationOutcome.valueOf(rs.getString("outcome")),
                            rs.getString("session_id"),
                            rs.getString("account_id"),
                            rs.getString("organization_id"));
                }
            }
        });
    }

    @Override
    public void revokeSession(String sessionId, String reasonCode) {
        withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT elmos_revoke_session(?, ?)")) {
                statement.setString(1, sessionId);
                statement.setString(2, reasonCode);
                statement.execute();
                return null;
            }
        });
    }

    @Override
    public Optional<SessionRecord> findSessionByToken(String refreshTokenSha256) {
        return withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT * FROM elmos_find_session_by_token(?)")) {
                statement.setString(1, refreshTokenSha256);
                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        return Optional.<SessionRecord>empty();
                    }
                    return Optional.of(new SessionRecord(
                            rs.getString("session_id"),
                            rs.getString("account_id"),
                            rs.getString("organization_id"),
                            rs.getObject("absolute_expires_at", java.time.OffsetDateTime.class).toInstant(),
                            rs.getObject("idle_expires_at", java.time.OffsetDateTime.class).toInstant()));
                }
            }
        });
    }

    @Override
    public void recordSecurityEvent(String eventId, String accountId, String eventType,
                                    String outcome, String failureCode, String ipPrefix, String clientFamily) {
        withConnection(connection -> {
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT elmos_record_security_event(?, ?, ?, ?, ?, ?, ?)")) {
                statement.setString(1, eventId);
                statement.setString(2, accountId);
                statement.setString(3, eventType);
                statement.setString(4, outcome);
                statement.setString(5, failureCode);
                statement.setString(6, ipPrefix);
                statement.setString(7, clientFamily);
                statement.execute();
                return null;
            }
        });
    }

    // ---- infrastructure ----------------------------------------------------

    private interface Work<T> {
        T run(Connection connection) throws SQLException;
    }

    private <T> T withConnection(Work<T> work) {
        try (Connection connection = connections.get()) {
            return work.run(connection);
        } catch (SQLException ex) {
            throw new StoreException(translate(ex));
        }
    }

    /**
     * Maps a PostgreSQL failure to a stable code.
     *
     * <p>The {@code ELMOS_} exceptions raised by the migration functions carry the
     * code in their message; everything else collapses to a generic code so the
     * driver's text - which names tables and columns - cannot reach a response
     * body or a log line that a user might see.</p>
     */
    private static String translate(SQLException ex) {
        String message = ex.getMessage();
        if (message != null) {
            int marker = message.indexOf("ELMOS_");
            if (marker >= 0) {
                String tail = message.substring(marker);
                int end = tail.indexOf('\n');
                if (end < 0) {
                    end = tail.indexOf(' ');
                }
                return end > 0 ? tail.substring(0, end).trim() : tail.trim();
            }
        }
        if ("23505".equals(ex.getSQLState())) {
            return "ELMOS_IDENTITY_CONFLICT";
        }
        return "ELMOS_IDENTITY_STORE_ERROR";
    }

    /** Unused today; kept so a future callable-statement path has one place to live. */
    static void close(CallableStatement statement) throws SQLException {
        if (statement != null) {
            statement.close();
        }
    }

    /** Test seam for suppliers that need to fail fast. */
    static <T> T require(Supplier<T> supplier, String code) {
        T value = supplier.get();
        if (value == null) {
            throw new StoreException(code);
        }
        return value;
    }
}
