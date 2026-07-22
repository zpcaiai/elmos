package io.elmos.persistence;

import io.elmos.secret.SecretInjectionService;
import io.elmos.secret.SecretLease;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import java.time.OffsetDateTime;

@Repository
public final class JdbcSecretLeaseStore implements SecretInjectionService.SecretLeaseStore {
    private final JdbcClient jdbc;
    public JdbcSecretLeaseStore(JdbcClient jdbc) { this.jdbc = jdbc; }
    @Override public void save(SecretLease lease) {
        jdbc.sql("""
                insert into secret_leases(lease_id, provider_lease_id, secret_type, workspace_id, issued_at, expires_at, status)
                values (:id, :provider, :type, :workspace, :issued, :expires, :status)
                on conflict (lease_id) do update set status = excluded.status
                """).param("id", lease.leaseId()).param("provider", lease.providerLeaseId()).param("type", lease.secretType().name())
                .param("workspace", lease.workspaceId()).param("issued", lease.issuedAt()).param("expires", lease.expiresAt())
                .param("status", lease.status().name()).update();
    }
    @Override public SecretLease find(String leaseId) {
        return jdbc.sql("select lease_id, provider_lease_id, secret_type, workspace_id, issued_at, expires_at, status from secret_leases where lease_id = :id")
                .param("id", leaseId).query((result, row) -> new SecretLease(result.getString("lease_id"), result.getString("provider_lease_id"),
                        SecretLease.SecretType.valueOf(result.getString("secret_type")), result.getString("workspace_id"),
                        result.getObject("issued_at", OffsetDateTime.class).toInstant(), result.getObject("expires_at", OffsetDateTime.class).toInstant(),
                        SecretLease.Status.valueOf(result.getString("status")))).single();
    }
}
