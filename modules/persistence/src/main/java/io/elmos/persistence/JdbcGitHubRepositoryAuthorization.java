package io.elmos.persistence;

import io.elmos.scm.GitHubInstallationTokenBroker;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public final class JdbcGitHubRepositoryAuthorization implements GitHubInstallationTokenBroker.RepositoryAuthorizationPort {
    private final JdbcClient jdbc;
    public JdbcGitHubRepositoryAuthorization(JdbcClient jdbc) { this.jdbc = jdbc; }
    @Override public boolean isAuthorized(String repositoryId, long repositoryExternalId, long installationExternalId) {
        return jdbc.sql("""
                select count(*) from scm_repositories sr
                join github_app_installations gi on gi.installation_id = sr.installation_id
                where sr.repository_id = :repository and sr.github_repository_id = :externalRepository
                  and gi.github_installation_id = :installation and sr.authorization_status = 'AUTHORIZED'
                  and gi.status = 'ACTIVE' and sr.archived = false and sr.disabled = false
                """).param("repository", repositoryId).param("externalRepository", repositoryExternalId)
                .param("installation", installationExternalId).query(Integer.class).single() == 1;
    }
}
