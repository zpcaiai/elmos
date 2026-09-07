package io.elmos.persistence;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Supplier;

/** Exact JDBC boundary for the V59 account and organization self-service API. */
public final class JdbcOrganizationSelfServiceStore {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcOrganizationSelfServiceStore(JdbcClient jdbc, TransactionTemplate transactions) {
        this.jdbc = Objects.requireNonNull(jdbc);
        this.transactions = Objects.requireNonNull(transactions);
    }

    public record OrganizationGrant(
            String organizationId,
            String displayName,
            String role,
            String actorId
    ) {
    }

    public record Member(
            String accountId,
            String actorId,
            String displayName,
            String role,
            String state,
            Instant joinedAt
    ) {
    }

    public String resolveOidcAccount(
            String accountId,
            String issuer,
            String subject,
            String email,
            boolean emailVerified,
            String displayName
    ) {
        return execute(() -> jdbc.sql("""
                SELECT elmos_resolve_oidc_account(
                    :accountId, :issuer, :subject, :email, :emailVerified, :displayName)
                """)
                .param("accountId", accountId)
                .param("issuer", issuer)
                .param("subject", subject)
                .param("email", email)
                .param("emailVerified", emailVerified)
                .param("displayName", displayName)
                .query(String.class).single());
    }

    public List<OrganizationGrant> organizations(String accountId) {
        return execute(() -> jdbc.sql("SELECT * FROM elmos_memberships_of_account(:accountId)")
                .param("accountId", accountId)
                .query((ResultSet rs, int row) -> new OrganizationGrant(
                        rs.getString("organization_id"),
                        rs.getString("display_name"),
                        rs.getString("member_role"),
                        rs.getString("actor_id")))
                .list());
    }

    public String createOrganization(
            String accountId,
            String organizationId,
            String displayName,
            String actorId,
            String dataRegion,
            String verifiedSubjectHash
    ) {
        return execute(() -> jdbc.sql("""
                SELECT elmos_create_self_service_organization(
                    :accountId, :organizationId, :displayName, :actorId,
                    :dataRegion, :verifiedSubjectHash)
                """)
                .param("accountId", accountId)
                .param("organizationId", organizationId)
                .param("displayName", displayName)
                .param("actorId", actorId)
                .param("dataRegion", dataRegion)
                .param("verifiedSubjectHash", verifiedSubjectHash)
                .query(String.class).single());
    }

    public String createInvitation(
            String invitationId,
            String organizationId,
            String inviterAccountId,
            String inviterActorId,
            String destinationHmac,
            String destinationDisplay,
            String role,
            String tokenSha256,
            int ttlSeconds
    ) {
        return execute(() -> jdbc.sql("""
                SELECT elmos_create_organization_invitation(
                    :invitationId, :organizationId, :inviterAccountId, :inviterActorId,
                    :destinationHmac, :destinationDisplay, :role, :tokenSha256, :ttlSeconds)
                """)
                .param("invitationId", invitationId)
                .param("organizationId", organizationId)
                .param("inviterAccountId", inviterAccountId)
                .param("inviterActorId", inviterActorId)
                .param("destinationHmac", destinationHmac)
                .param("destinationDisplay", destinationDisplay)
                .param("role", role)
                .param("tokenSha256", tokenSha256)
                .param("ttlSeconds", ttlSeconds)
                .query(String.class).single());
    }

    public Optional<String> invitationOrganization(String tokenSha256) {
        return execute(() -> jdbc.sql("SELECT elmos_invitation_organization(:token)")
                .param("token", tokenSha256)
                .query(String.class).optional()
                .filter(value -> value != null && !value.isBlank()));
    }

    public String acceptInvitation(
            String tokenSha256,
            String destinationHmac,
            String accountId,
            String actorId
    ) {
        return execute(() -> jdbc.sql("""
                SELECT elmos_accept_organization_invitation(
                    :tokenSha256, :destinationHmac, :accountId, :actorId)
                """)
                .param("tokenSha256", tokenSha256)
                .param("destinationHmac", destinationHmac)
                .param("accountId", accountId)
                .param("actorId", actorId)
                .query(String.class).single());
    }

    public List<Member> members(String organizationId, String requesterAccountId) {
        return execute(() -> jdbc.sql("""
                SELECT * FROM elmos_list_organization_members(:organizationId, :requester)
                """)
                .param("organizationId", organizationId)
                .param("requester", requesterAccountId)
                .query(this::readMember)
                .list());
    }

    public String updateMember(
            String organizationId,
            String requesterAccountId,
            String targetAccountId,
            String role,
            boolean remove
    ) {
        return execute(() -> jdbc.sql("""
                SELECT elmos_update_organization_member(
                    :organizationId, :requester, :target, :role, :remove)
                """)
                .param("organizationId", organizationId)
                .param("requester", requesterAccountId)
                .param("target", targetAccountId)
                .param("role", role)
                .param("remove", remove)
                .query(String.class).single());
    }

    private Member readMember(ResultSet rs, int row) throws SQLException {
        java.time.OffsetDateTime joined = rs.getObject(
                "joined_at", java.time.OffsetDateTime.class);
        return new Member(
                rs.getString("account_id"),
                rs.getString("actor_id"),
                rs.getString("display_name"),
                rs.getString("member_role"),
                rs.getString("member_state"),
                joined == null ? null : joined.toInstant());
    }

    private <T> T execute(Supplier<T> work) {
        try {
            return transactions.execute(status -> work.get());
        } catch (RuntimeException error) {
            String message = rootMessage(error);
            int marker = message == null ? -1 : message.indexOf("ELMOS_");
            if (marker >= 0) {
                String tail = message.substring(marker);
                int end = tail.indexOf(' ');
                throw new OrganizationStoreException(end > 0 ? tail.substring(0, end) : tail);
            }
            throw error;
        }
    }

    private static String rootMessage(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        return current.getMessage();
    }

    public static final class OrganizationStoreException extends RuntimeException {
        private static final long serialVersionUID = 1L;
        private final String code;

        public OrganizationStoreException(String code) {
            super(code);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }
}
