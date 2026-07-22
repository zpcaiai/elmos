package io.elmos.persistence;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.scm.GitHubInstallationLifecycleService;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.time.Instant;
import java.util.Map;
import java.util.Set;

@Repository
public final class JdbcGitHubInstallationStore implements GitHubInstallationLifecycleService.Store {
    private final JdbcClient jdbc; private final ObjectMapper mapper;
    public JdbcGitHubInstallationStore(JdbcClient jdbc, ObjectMapper mapper) { this.jdbc = jdbc; this.mapper = mapper; }

    @Override @Transactional public boolean bindIfUnclaimed(GitHubInstallationLifecycleService.Installation installation) {
        int rows = jdbc.sql("""
                insert into github_app_installations(installation_id, connection_id, github_installation_id, account_external_id,
                    account_login, target_type, installed_at, permissions, repository_selection, status, last_synced_at)
                select :id, connection_id, :external, :accountId, :login, :targetType, :installed, cast(:permissions as jsonb),
                    :selection, 'ACTIVE', :synced from scm_connections
                where connection_id = :connection and organization_id = :organization
                on conflict (github_installation_id) do nothing
                """).param("id", installation.installationId()).param("external", installation.githubInstallationId())
                .param("accountId", installation.accountExternalId()).param("login", installation.accountLogin())
                .param("targetType", installation.targetType()).param("installed", installation.installedAt())
                .param("permissions", json(installation.permissions())).param("selection", installation.repositorySelection())
                .param("synced", installation.synchronizedAt()).param("connection", installation.connectionId())
                .param("organization", installation.organizationId()).update();
        return rows == 1;
    }

    @Override public GitHubInstallationLifecycleService.Installation findByExternalId(long githubInstallationId) {
        return jdbc.sql("""
                select gi.*, sc.organization_id from github_app_installations gi
                join scm_connections sc on sc.connection_id = gi.connection_id
                where gi.github_installation_id = :id
                """).param("id", githubInstallationId).query((result, row) -> new GitHubInstallationLifecycleService.Installation(
                        result.getString("installation_id"), result.getString("connection_id"), result.getString("organization_id"),
                        result.getLong("github_installation_id"), result.getLong("account_external_id"), result.getString("account_login"),
                        result.getString("target_type"), result.getString("repository_selection"), permissions(result.getString("permissions")),
                        GitHubInstallationLifecycleService.Status.valueOf(result.getString("status")),
                        result.getObject("installed_at", OffsetDateTime.class).toInstant(),
                        result.getObject("last_synced_at", OffsetDateTime.class).toInstant())).optional().orElse(null);
    }

    @Override public void updateStatus(long githubInstallationId, GitHubInstallationLifecycleService.Status status, Instant changedAt) {
        int rows = jdbc.sql("""
                update github_app_installations set status = :status,
                    suspended_at = case when :status = 'SUSPENDED' then :changed else null end,
                    deleted_at = case when :status = 'DELETED' then :changed else deleted_at end,
                    last_synced_at = :changed where github_installation_id = :id
                """).param("status", status.name()).param("changed", changedAt).param("id", githubInstallationId).update();
        if (rows != 1) throw new SecurityException("unknown GitHub App installation");
    }

    @Override @Transactional public void replaceAuthorizedRepositories(long githubInstallationId,
            Set<GitHubInstallationLifecycleService.Repository> repositories, Instant synchronizedAt) {
        GitHubInstallationLifecycleService.Installation installation = findByExternalId(githubInstallationId);
        if (installation == null || installation.status() != GitHubInstallationLifecycleService.Status.ACTIVE)
            throw new SecurityException("cannot synchronize an inactive installation");
        jdbc.sql("update scm_repositories set authorization_status = 'REVOKED', synced_at = :at where installation_id = :installation")
                .param("at", synchronizedAt).param("installation", installation.installationId()).update();
        for (var repository : repositories) {
            jdbc.sql("""
                    insert into repositories(repository_id, organization_id, scm_provider, external_id, default_branch)
                    values (:id, :organization, 'GITHUB', :external, :defaultBranch)
                    on conflict (repository_id) do nothing
                    """).param("id", repository.repositoryId()).param("organization", installation.organizationId())
                    .param("external", Long.toString(repository.githubRepositoryId())).param("defaultBranch", repository.defaultBranch()).update();
            int mapped = jdbc.sql("select count(*) from repositories where repository_id = :id and organization_id = :organization")
                    .param("id", repository.repositoryId()).param("organization", installation.organizationId()).query(Integer.class).single();
            if (mapped != 1) throw new SecurityException("repository id belongs to another organization");
            jdbc.sql("""
                    insert into scm_repositories(scm_repository_id, repository_id, installation_id, github_repository_id,
                        owner_login, repository_name, full_name, clone_url, html_url, default_branch, visibility,
                        archived, disabled, fork, parent_repository_external_id, authorization_status, synced_at)
                    values (:scmId, :repositoryId, :installation, :external, :owner, :name, :fullName, :cloneUrl, :htmlUrl,
                        :defaultBranch, :visibility, :archived, :disabled, :fork, :parent, 'AUTHORIZED', :synced)
                    on conflict (repository_id) do update set installation_id = excluded.installation_id,
                        owner_login = excluded.owner_login, repository_name = excluded.repository_name, full_name = excluded.full_name,
                        clone_url = excluded.clone_url, html_url = excluded.html_url, default_branch = excluded.default_branch,
                        visibility = excluded.visibility, archived = excluded.archived, disabled = excluded.disabled,
                        fork = excluded.fork, parent_repository_external_id = excluded.parent_repository_external_id,
                        authorization_status = 'AUTHORIZED', synced_at = excluded.synced_at
                    """).param("scmId", "scm-" + repository.repositoryId()).param("repositoryId", repository.repositoryId())
                    .param("installation", installation.installationId()).param("external", repository.githubRepositoryId())
                    .param("owner", repository.owner()).param("name", repository.name()).param("fullName", repository.fullName())
                    .param("cloneUrl", repository.cloneUrl()).param("htmlUrl", repository.htmlUrl()).param("defaultBranch", repository.defaultBranch())
                    .param("visibility", repository.visibility()).param("archived", repository.archived()).param("disabled", repository.disabled())
                    .param("fork", repository.fork()).param("parent", repository.parentRepositoryId()).param("synced", synchronizedAt).update();
        }
        jdbc.sql("update github_app_installations set last_synced_at = :at where installation_id = :id")
                .param("at", synchronizedAt).param("id", installation.installationId()).update();
    }

    private String json(Map<String,String> value) { try { return mapper.writeValueAsString(value); } catch (JsonProcessingException e) { throw new IllegalArgumentException(e); } }
    private Map<String,String> permissions(String value) { try { return mapper.readValue(value, new TypeReference<>() {}); } catch (JsonProcessingException e) { throw new IllegalStateException(e); } }
}
