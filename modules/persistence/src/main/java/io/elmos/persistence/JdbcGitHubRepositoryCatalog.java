package io.elmos.persistence;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * Tenant-scoped catalog of repositories currently authorized through an
 * active GitHub App installation. Callers receive no credential material.
 */
@Repository
public final class JdbcGitHubRepositoryCatalog {
    public record AuthorizedRepository(
            String repositoryId,
            long repositoryExternalId,
            long installationExternalId,
            String fullName,
            String defaultBranch,
            String visibility
    ) {}

    private final JdbcClient jdbc;

    public JdbcGitHubRepositoryCatalog(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public List<AuthorizedRepository> listAuthorized(String organizationId) {
        requireOrganization(organizationId);
        return jdbc.sql("""
                select sr.repository_id, sr.github_repository_id,
                       gi.github_installation_id, sr.full_name,
                       sr.default_branch, sr.visibility
                from scm_repositories sr
                join github_app_installations gi
                  on gi.installation_id = sr.installation_id
                join scm_connections sc
                  on sc.connection_id = gi.connection_id
                join repositories r
                  on r.repository_id = sr.repository_id
                where sc.organization_id = :organization
                  and r.organization_id = :organization
                  and gi.status = 'ACTIVE'
                  and sr.authorization_status = 'AUTHORIZED'
                  and sr.archived = false
                  and sr.disabled = false
                order by lower(sr.full_name), sr.github_repository_id
                """)
                .param("organization", organizationId)
                .query((result, row) -> new AuthorizedRepository(
                        result.getString("repository_id"),
                        result.getLong("github_repository_id"),
                        result.getLong("github_installation_id"),
                        result.getString("full_name"),
                        result.getString("default_branch"),
                        result.getString("visibility")))
                .list();
    }

    public AuthorizedRepository requireAuthorized(
            String organizationId,
            String repositoryId
    ) {
        requireOrganization(organizationId);
        if (repositoryId == null
                || !repositoryId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw new SecurityException("repository identity is invalid");
        }
        return jdbc.sql("""
                select sr.repository_id, sr.github_repository_id,
                       gi.github_installation_id, sr.full_name,
                       sr.default_branch, sr.visibility
                from scm_repositories sr
                join github_app_installations gi
                  on gi.installation_id = sr.installation_id
                join scm_connections sc
                  on sc.connection_id = gi.connection_id
                join repositories r
                  on r.repository_id = sr.repository_id
                where sc.organization_id = :organization
                  and r.organization_id = :organization
                  and sr.repository_id = :repository
                  and gi.status = 'ACTIVE'
                  and sr.authorization_status = 'AUTHORIZED'
                  and sr.archived = false
                  and sr.disabled = false
                """)
                .param("organization", organizationId)
                .param("repository", repositoryId)
                .query((result, row) -> new AuthorizedRepository(
                        result.getString("repository_id"),
                        result.getLong("github_repository_id"),
                        result.getLong("github_installation_id"),
                        result.getString("full_name"),
                        result.getString("default_branch"),
                        result.getString("visibility")))
                .optional()
                .orElseThrow(() ->
                        new SecurityException("repository is not authorized for this organization"));
    }

    private static void requireOrganization(String organizationId) {
        if (organizationId == null
                || !organizationId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw new SecurityException("trusted organization identity is invalid");
        }
    }
}
