package io.elmos.controlplane;

import io.elmos.integrations.GitRepositoryWorkspaceService;
import io.elmos.persistence.JdbcUserActivityStore;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RepositoryWorkspaceControllerTest {
    private static final String KEY = "repository-workspace-test-key-32";
    private static final Instant NOW = Instant.parse("2026-07-28T10:00:00Z");
    private final GitRepositoryWorkspaceService service = mock(GitRepositoryWorkspaceService.class);
    private final RepositoryWorkspaceCredentialStore credentials =
            mock(RepositoryWorkspaceCredentialStore.class);
    private final JdbcUserActivityStore activity = mock(JdbcUserActivityStore.class);
    private final RepositoryWorkspaceController controller = new RepositoryWorkspaceController(
            service, credentials, activity, Clock.fixed(NOW, ZoneOffset.UTC), KEY,
            "/tmp/elmos-test-materialized");

    @Test
    void createsWorkspaceWithTrustedHeaderIdentityAndServerSideCredentialReference() {
        var body = new RepositoryWorkspaceController.CreateBody(
                GitRepositoryWorkspaceService.Provider.GITEE,
                "gitee.com",
                "owner/repository",
                "https://gitee.com/owner/repository.git",
                "main",
                "tenant-gitee"
        );
        var expected = workspace("tenant-a", "actor-a");
        when(credentials.lease("tenant-gitee"))
                .thenReturn(new RepositoryWorkspaceCredentialStore.Lease(
                        "git-user", Optional.empty(), NOW.plusSeconds(900)));
        when(service.create(any(), eq("git-user"), eq(Optional.empty()))).thenReturn(expected);

        var result = controller.create(KEY, "tenant-a", "actor-a", "request-1", body);

        assertEquals(expected, result);
        verify(service).create(
                new GitRepositoryWorkspaceService.CreateRequest(
                        "tenant-a",
                        "actor-a",
                        GitRepositoryWorkspaceService.Provider.GITEE,
                        "gitee.com",
                        "owner/repository",
                        "https://gitee.com/owner/repository.git",
                        "main"
                ),
                "git-user",
                Optional.empty()
        );
        verify(activity, atLeastOnce()).append(eq("tenant-a"), eq("actor-a"), eq("request-1"), any());
    }

    @Test
    void rejectsWrongApiKeyAndCrossActorWorkspaceRead() {
        assertThrows(SecurityException.class, () -> controller.capabilities(
                "wrong-key", "tenant-a", "actor-a", "request-1"));

        String workspaceId = "d12ac53a-30b8-4d87-8202-9c9a4b181cf8";
        when(service.inspect("tenant-a", "actor-other", workspaceId))
                .thenThrow(new SecurityException("GIT_WORKSPACE_ACTOR_MISMATCH"));
        assertThrows(SecurityException.class, () -> controller.inspect(
                KEY, "tenant-a", "actor-other", "request-2", workspaceId));
        verify(activity, atLeastOnce()).append(eq("tenant-a"), eq("actor-other"), eq("request-2"), any());
    }

    @Test
    void deleteReportsNoExternalOperation() {
        String workspaceId = "d12ac53a-30b8-4d87-8202-9c9a4b181cf8";
        var result = controller.delete(KEY, "tenant-a", "actor-a", "request-3", workspaceId);
        assertEquals("DELETED", result.status());
        assertTrue(!result.externalOperationExecuted());
        verify(service).delete("tenant-a", "actor-a", workspaceId);
    }

    private static GitRepositoryWorkspaceService.Workspace workspace(String tenant, String actor) {
        return new GitRepositoryWorkspaceService.Workspace(
                "d12ac53a-30b8-4d87-8202-9c9a4b181cf8",
                tenant,
                actor,
                GitRepositoryWorkspaceService.Provider.GITEE,
                "gitee.com",
                "owner/repository",
                "https://gitee.com/owner/repository.git",
                "main",
                "1".repeat(40),
                "1".repeat(40),
                "elmos/workspace-d12ac53a",
                GitRepositoryWorkspaceService.Completeness.COMPLETE,
                false,
                List.of(),
                List.of(),
                List.of(),
                null,
                null,
                null,
                NOW,
                "READY_FOR_LOCAL_CHANGE",
                false
        );
    }
}
