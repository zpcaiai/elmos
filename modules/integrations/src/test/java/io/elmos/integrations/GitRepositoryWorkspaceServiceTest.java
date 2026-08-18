package io.elmos.integrations;

import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.lib.Constants;
import org.eclipse.jgit.revwalk.RevCommit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Base64;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GitRepositoryWorkspaceServiceTest {
    @TempDir Path temporary;

    @Test
    void createsExactCommitInventoryAndAppliesOnlyApprovedLocalTextChanges() throws Exception {
        RepositoryFixture source = repository(false, false, false);
        GitRepositoryWorkspaceService service = service();
        GitRepositoryWorkspaceService.Workspace workspace = service.create(
                request(source, source.branch()),
                "unused",
                Optional.empty()
        );

        assertEquals(source.commit(), workspace.sourceCommit());
        assertEquals(GitRepositoryWorkspaceService.Completeness.COMPLETE, workspace.completeness());
        assertTrue(workspace.files().stream().anyMatch(file ->
                file.path().equals("README.md")
                        && file.category() == GitRepositoryWorkspaceService.FileCategory.DOCUMENTATION));
        assertTrue(workspace.files().stream().anyMatch(file ->
                file.path().equals(".github/workflows/deploy.yml")
                        && file.category() == GitRepositoryWorkspaceService.FileCategory.CLOUD_DEPLOYMENT));
        assertTrue(workspace.files().stream().anyMatch(file ->
                file.path().equals("Dockerfile")
                        && file.category() == GitRepositoryWorkspaceService.FileCategory.LOCAL_DEPLOYMENT));
        assertTrue(workspace.files().stream().anyMatch(file ->
                file.path().equals("src/App.java")
                        && file.category() == GitRepositoryWorkspaceService.FileCategory.SOURCE));

        GitRepositoryWorkspaceService.FileContent read =
                service.readFile("tenant-a", "actor-a", workspace.workspaceId(), "README.md");
        assertEquals("# Before\n", read.content());

        GitRepositoryWorkspaceService.ChangeResult result = service.apply(
                workspace.workspaceId(),
                new GitRepositoryWorkspaceService.ChangeRequest(
                        "tenant-a",
                        "actor-a",
                        source.commit(),
                        "Implement the requested documentation and cloud deployment configuration.",
                        false,
                        List.of("README.md", "terraform/main.tf"),
                        List.of(
                                new GitRepositoryWorkspaceService.FileChange(
                                        GitRepositoryWorkspaceService.ChangeOperation.UPSERT,
                                        "README.md",
                                        read.sha256(),
                                        base64("# After\n")
                                ),
                                new GitRepositoryWorkspaceService.FileChange(
                                        GitRepositoryWorkspaceService.ChangeOperation.UPSERT,
                                        "terraform/main.tf",
                                        null,
                                        base64("")
                                )
                        )
                )
        );

        assertTrue(result.changedPaths().contains("README.md"));
        assertTrue(result.untrackedPaths().contains("terraform/main.tf"));
        assertFalse(result.pushed());
        assertFalse(result.pullRequestCreated());
        assertFalse(result.deployed());
        assertEquals("# After\n",
                service.readFile("tenant-a", "actor-a", workspace.workspaceId(), "README.md").content());
        assertEquals("", service.readFile(
                "tenant-a", "actor-a", workspace.workspaceId(), "terraform/main.tf").content());
    }

    @Test
    void rejectsProviderMismatchTraversalSecretsAndConcurrentOverwrite() throws Exception {
        RepositoryFixture source = repository(false, false, false);
        GitRepositoryWorkspaceService service = service();
        assertThrows(SecurityException.class, () -> service.create(
                new GitRepositoryWorkspaceService.CreateRequest(
                        "tenant-a", "actor-a", GitRepositoryWorkspaceService.Provider.GITHUB,
                        "github.com", "owner/repository", source.uri(), source.branch()),
                "unused", Optional.empty()));
        assertThrows(SecurityException.class, () -> service.create(
                new GitRepositoryWorkspaceService.CreateRequest(
                        "tenant-a", "actor-a", GitRepositoryWorkspaceService.Provider.GENERIC_GIT,
                        "git.example.com", "owner/repository",
                        "https://git.example.com/owner/repository.git", source.branch()),
                "unused", Optional.empty()));
        assertThrows(SecurityException.class, () -> service.create(
                new GitRepositoryWorkspaceService.CreateRequest(
                        "tenant-a", "actor-a", GitRepositoryWorkspaceService.Provider.GITHUB,
                        "gitee.com", "owner/repository",
                        "https://github.com/owner/repository.git", source.branch()),
                "unused", Optional.empty()));

        GitRepositoryWorkspaceService.Workspace workspace =
                service.create(request(source, source.branch()), "unused", Optional.empty());
        assertThrows(SecurityException.class,
                () -> service.inspect("tenant-a", "actor-other", workspace.workspaceId()));
        assertThrows(SecurityException.class,
                () -> service.readFile("tenant-a", "actor-a", workspace.workspaceId(), "../outside"));
        assertThrows(SecurityException.class,
                () -> service.readFile("tenant-a", "actor-a", workspace.workspaceId(), ".env"));

        GitRepositoryWorkspaceService.FileContent read =
                service.readFile("tenant-a", "actor-a", workspace.workspaceId(), "README.md");
        assertThrows(SecurityException.class, () -> service.apply(
                workspace.workspaceId(),
                change(source, ".env", null, base64("SECRET=forbidden\n"), false)));
        assertThrows(SecurityException.class, () -> service.apply(
                workspace.workspaceId(),
                change(source, ".env.production", null, base64("SECRET=forbidden\n"), false)));
        assertThrows(SecurityException.class, () -> service.apply(
                workspace.workspaceId(),
                change(source, "README.md", "0".repeat(64), base64("# overwrite\n"), false)));
        assertEquals(read.sha256(),
                service.readFile("tenant-a", "actor-a", workspace.workspaceId(), "README.md").sha256());
    }

    @Test
    void codeOwnersRequiresExplicitApprovalAndIncompleteObjectsRemainReadOnly() throws Exception {
        RepositoryFixture owned = repository(true, false, false);
        GitRepositoryWorkspaceService service = service();
        GitRepositoryWorkspaceService.Workspace workspace =
                service.create(request(owned, owned.commit()), "unused", Optional.empty());
        assertTrue(workspace.codeOwnersPresent());
        GitRepositoryWorkspaceService.FileContent read =
                service.readFile("tenant-a", "actor-a", workspace.workspaceId(), "README.md");
        assertThrows(SecurityException.class, () -> service.apply(
                workspace.workspaceId(),
                change(owned, "README.md", read.sha256(), base64("# denied\n"), false)));
        GitRepositoryWorkspaceService.ChangeResult approved = service.apply(
                workspace.workspaceId(),
                change(owned, "README.md", read.sha256(), base64("# approved\n"), true));
        assertTrue(approved.changedPaths().contains("README.md"));

        RepositoryFixture submodules = repository(false, true, false);
        GitRepositoryWorkspaceService.Workspace submoduleWorkspace =
                service.create(request(submodules, submodules.branch()), "unused", Optional.empty());
        assertEquals(GitRepositoryWorkspaceService.Completeness.INCOMPLETE_SUBMODULES,
                submoduleWorkspace.completeness());
        assertTrue(submoduleWorkspace.files().stream().noneMatch(GitRepositoryWorkspaceService.FileEntry::writable));

        RepositoryFixture lfs = repository(false, false, true);
        GitRepositoryWorkspaceService.Workspace lfsWorkspace =
                service.create(request(lfs, lfs.branch()), "unused", Optional.empty());
        assertEquals(GitRepositoryWorkspaceService.Completeness.INCOMPLETE_LFS, lfsWorkspace.completeness());
    }

    @Test
    void boundsTotalWorkspaceCount() throws Exception {
        RepositoryFixture source = repository(false, false, false);
        GitRepositoryWorkspaceService service = new GitRepositoryWorkspaceService(
                temporary.resolve("bounded-workspaces"),
                1_000,
                64L * 1024 * 1024,
                true,
                Set.of(),
                1,
                Duration.ofDays(7)
        );
        service.create(request(source, source.branch()), "unused", Optional.empty());
        IllegalStateException error = assertThrows(IllegalStateException.class,
                () -> service.create(request(source, source.branch()), "unused", Optional.empty()));
        assertEquals("GIT_WORKSPACE_CAPACITY_EXCEEDED", error.getMessage());
    }

    @Test
    void commitsExactApprovedPathsAndPushesVerifiedNonForceBranch() throws Exception {
        RepositoryFixture source = repository(false, false, false);
        GitRepositoryWorkspaceService service = service();
        var workspace = service.create(request(source, source.branch()), "unused", Optional.empty());
        var read = service.readFile("tenant-a", "actor-a", workspace.workspaceId(), "README.md");
        service.apply(workspace.workspaceId(), change(
                source, "README.md", read.sha256(), base64("# Delivered\n"), false));

        assertThrows(SecurityException.class, () -> service.commit(
                workspace.workspaceId(),
                new GitRepositoryWorkspaceService.CommitRequest(
                        "tenant-a", "actor-a", source.commit(), "wrong scope",
                        false, List.of("src/App.java"))));

        var committed = service.commit(
                workspace.workspaceId(),
                new GitRepositoryWorkspaceService.CommitRequest(
                        "tenant-a", "actor-a", source.commit(), "Deliver requested change",
                        false, List.of("README.md")));
        assertEquals(List.of("README.md"), committed.committedPaths());
        assertFalse(committed.signed());

        var pushed = service.push(
                workspace.workspaceId(),
                new GitRepositoryWorkspaceService.PushRequest(
                        "tenant-a", "actor-a", committed.commitSha()),
                "unused",
                Optional.empty());
        assertEquals("PUSHED_VERIFIED", pushed.status());
        assertTrue(pushed.externalOperationExecuted());

        var recovered = service.inspect("tenant-a", "actor-a", workspace.workspaceId());
        assertEquals(committed.commitSha(), recovered.currentHeadCommit());
        assertEquals(committed.commitSha(), recovered.pushedCommit());
        assertEquals(List.of(), recovered.pendingPaths());
        assertEquals("PUSHED_VERIFIED", recovered.status());
        try (Git remote = Git.open(Path.of(java.net.URI.create(source.uri())).toFile())) {
            assertEquals(
                    committed.commitSha(),
                    remote.getRepository().resolve("refs/heads/" + workspace.branch()).name());
        }
    }

    @Test
    void genericGitCannotAssumePullRequestApi() throws Exception {
        RepositoryFixture source = repository(false, false, false);
        GitRepositoryWorkspaceService service = service();
        var workspace = service.create(request(source, source.branch()), "unused", Optional.empty());
        assertThrows(IllegalArgumentException.class, () -> service.createPullRequest(
                workspace.workspaceId(),
                new GitRepositoryWorkspaceService.PullRequestRequest(
                        "tenant-a", "actor-a", source.commit(), "main",
                        "Review", "Body", "request-1"),
                "unused",
                Optional.empty()));
    }

    @Test
    void materializesImmutableSpringHandoffAndExcludesProtectedFiles() throws Exception {
        RepositoryFixture source = repository(false, false, false);
        GitRepositoryWorkspaceService service = service();
        var workspace = service.create(request(source, source.branch()), "unused", Optional.empty());
        var inspected = service.inspect("tenant-a", "actor-a", workspace.workspaceId());
        assertTrue(inspected.files().stream()
                .filter(file -> file.path().equals("src/App.java"))
                .allMatch(GitRepositoryWorkspaceService.FileEntry::readable));
        assertTrue(inspected.files().stream()
                .filter(file -> file.path().equals(".env"))
                .noneMatch(GitRepositoryWorkspaceService.FileEntry::readable));
        Path handoffRoot = temporary.resolve("materialized");

        var first = service.materialize(
                "tenant-a", "actor-a", workspace.workspaceId(),
                workspace.currentHeadCommit(), handoffRoot);
        var second = service.materialize(
                "tenant-a", "actor-a", workspace.workspaceId(),
                workspace.currentHeadCommit(), handoffRoot);

        assertEquals(first, second);
        Path materialized = handoffRoot.resolve(first.relativePath());
        assertTrue(Files.isRegularFile(materialized.resolve("src/App.java")));
        assertTrue(Files.isRegularFile(materialized.resolve("Dockerfile")));
        assertFalse(Files.exists(materialized.resolve(".env")));
        assertEquals(List.of(".env"), first.excludedProtectedPaths());
        assertEquals("MATERIALIZED_VERIFIED", first.status());
    }

    private GitRepositoryWorkspaceService service() {
        return new GitRepositoryWorkspaceService(
                temporary.resolve("workspaces"), 1_000, 64L * 1024 * 1024, true);
    }

    private GitRepositoryWorkspaceService.CreateRequest request(RepositoryFixture source, String ref) {
        return new GitRepositoryWorkspaceService.CreateRequest(
                "tenant-a",
                "actor-a",
                GitRepositoryWorkspaceService.Provider.GENERIC_GIT,
                "local-test",
                "fixture/repository",
                source.uri(),
                ref
        );
    }

    private GitRepositoryWorkspaceService.ChangeRequest change(
            RepositoryFixture fixture,
            String path,
            String expectedHash,
            String content,
            boolean ownerApproval
    ) {
        return new GitRepositoryWorkspaceService.ChangeRequest(
                "tenant-a",
                "actor-a",
                fixture.commit(),
                "Apply the explicitly requested local workspace update.",
                ownerApproval,
                List.of(path),
                List.of(new GitRepositoryWorkspaceService.FileChange(
                        GitRepositoryWorkspaceService.ChangeOperation.UPSERT,
                        path,
                        expectedHash,
                        content
                ))
        );
    }

    private RepositoryFixture repository(boolean codeOwners, boolean submodules, boolean lfs) throws Exception {
        Path directory = Files.createTempDirectory(temporary, "source-");
        Files.createDirectories(directory.resolve("src"));
        Files.createDirectories(directory.resolve("config"));
        Files.createDirectories(directory.resolve(".github/workflows"));
        Files.writeString(directory.resolve("README.md"), "# Before\n");
        Files.writeString(directory.resolve(".env"), "DATABASE_URL=must-not-be-exposed\n");
        Files.writeString(directory.resolve("src/App.java"), "final class App {}\n");
        Files.writeString(directory.resolve("config/application.yml"), "enabled: true\n");
        Files.writeString(directory.resolve("Dockerfile"), "FROM scratch\n");
        Files.writeString(directory.resolve(".github/workflows/deploy.yml"), "name: deploy\n");
        if (codeOwners) {
            Files.createDirectories(directory.resolve(".github"));
            Files.writeString(directory.resolve(".github/CODEOWNERS"), "* @owner\n");
        }
        if (submodules) {
            Files.writeString(directory.resolve(".gitmodules"),
                    "[submodule \"dependency\"]\n\tpath = dependency\n\turl = https://example.test/dependency.git\n");
        }
        if (lfs) Files.writeString(directory.resolve(".gitattributes"), "*.bin filter = lfs diff=lfs merge=lfs -text\n");
        try (Git git = Git.init().setDirectory(directory.toFile()).call()) {
            git.add().addFilepattern(".").call();
            RevCommit commit = git.commit()
                    .setAuthor("ELMOS Test", "test@elmos.invalid")
                    .setCommitter("ELMOS Test", "test@elmos.invalid")
                    .setMessage("fixture")
                    .call();
            String branch = git.getRepository().getBranch();
            assertEquals(commit.name(), git.getRepository().resolve(Constants.HEAD).name());
            return new RepositoryFixture(directory.toUri().toString(), branch, commit.name());
        }
    }

    private static String base64(String value) {
        return Base64.getEncoder().encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    private record RepositoryFixture(String uri, String branch, String commit) {}
}
