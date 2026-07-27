package io.elmos.controlplane;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.Clock;
import java.util.Objects;
import java.util.UUID;

final class JdbcGithubOnboardingStateStore implements GithubInstallationOnboardingService.StateStore {
    private final JdbcClient jdbc;
    private final Clock clock;

    JdbcGithubOnboardingStateStore(JdbcClient jdbc, Clock clock) {
        this.jdbc = Objects.requireNonNull(jdbc);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    @Transactional
    public String begin(
            String organizationId,
            String requestedConnectionId,
            String nonce,
            Instant expiresAt
    ) {
        String connectionId = requestedConnectionId == null
                ? "ghc-" + UUID.randomUUID()
                : requestedConnectionId;
        Instant now = clock.instant();
        jdbc.sql("""
                insert into scm_connections(
                    connection_id, organization_id, provider, status, created_at, updated_at
                )
                select :connection, organization_id, 'GITHUB', 'PENDING', :now, :now
                from organizations
                where organization_id=:organization
                on conflict (connection_id) do nothing
                """)
                .param("connection", connectionId)
                .param("organization", organizationId)
                .param("now", now)
                .update();
        int inserted = jdbc.sql("""
                insert into github_app_onboarding_states(
                    state_nonce, organization_id, connection_id, stage, expires_at, created_at
                )
                select :nonce, :organization, :connection, 'INSTALL', :expires, :now
                from scm_connections
                where connection_id=:connection and organization_id=:organization
                  and provider='GITHUB' and status <> 'DELETED'
                """)
                .param("nonce", nonce)
                .param("organization", organizationId)
                .param("connection", connectionId)
                .param("expires", expiresAt)
                .param("now", now)
                .update();
        if (inserted != 1) {
            throw new SecurityException("GitHub connection does not belong to the authenticated organization");
        }
        return connectionId;
    }

    @Override
    @Transactional
    public boolean advanceToOauth(
            String organizationId,
            String connectionId,
            String nonce,
            long installationId,
            Instant expiresAt,
            Instant now
    ) {
        return jdbc.sql("""
                update github_app_onboarding_states
                set stage='OAUTH', installation_external_id=:installation,
                    expires_at=:expires, updated_at=:now
                where state_nonce=:nonce and organization_id=:organization
                  and connection_id=:connection and stage='INSTALL'
                  and installation_external_id is null and consumed_at is null
                  and expires_at > :now
                """)
                .param("installation", installationId)
                .param("expires", expiresAt)
                .param("now", now)
                .param("nonce", nonce)
                .param("organization", organizationId)
                .param("connection", connectionId)
                .update() == 1;
    }

    @Override
    @Transactional
    public boolean consumeOauth(
            String organizationId,
            String connectionId,
            String nonce,
            long installationId,
            Instant now
    ) {
        return jdbc.sql("""
                update github_app_onboarding_states
                set consumed_at=:now, updated_at=:now
                where state_nonce=:nonce and organization_id=:organization
                  and connection_id=:connection and stage='OAUTH'
                  and installation_external_id=:installation
                  and consumed_at is null and expires_at > :now
                """)
                .param("now", now)
                .param("nonce", nonce)
                .param("organization", organizationId)
                .param("connection", connectionId)
                .param("installation", installationId)
                .update() == 1;
    }
}
