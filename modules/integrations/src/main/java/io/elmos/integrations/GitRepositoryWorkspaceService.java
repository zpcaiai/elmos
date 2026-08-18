package io.elmos.integrations;

import io.elmos.scm.EphemeralCredential;
import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.api.FetchCommand;
import org.eclipse.jgit.api.LsRemoteCommand;
import org.eclipse.jgit.lib.ObjectId;
import org.eclipse.jgit.lib.Ref;
import org.eclipse.jgit.transport.RefSpec;
import org.eclipse.jgit.transport.RemoteRefUpdate;
import org.eclipse.jgit.transport.UsernamePasswordCredentialsProvider;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.security.DigestInputStream;
import java.time.Instant;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collection;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Properties;
import java.util.Set;
import java.util.UUID;

/**
 * Provider-neutral, exact-commit Git workspaces for governed local modification.
 *
 * <p>Push and pull-request publication are explicit, separately authorized
 * operations. The service never merges or deploys. Credentials are used only
 * by JGit/provider adapters and are never written into Git configuration or
 * workspace metadata.</p>
 */
public final class GitRepositoryWorkspaceService {
    public enum Provider { GITHUB, GITEE, GENERIC_GIT }
    public enum Completeness { COMPLETE, INCOMPLETE_SUBMODULES, INCOMPLETE_LFS }
    public enum ChangeOperation { UPSERT, DELETE }
    public enum FileCategory {
        SOURCE, DOCUMENTATION, CONFIGURATION, LOCAL_DEPLOYMENT, CLOUD_DEPLOYMENT, TEST, OTHER
    }

    public record CreateRequest(
            String organizationId,
            String actorId,
            Provider provider,
            String providerInstanceId,
            String nativeRepositoryId,
            String cloneUrl,
            String requestedRef
    ) {}

    public record FileEntry(
            String path,
            long bytes,
            String sha256,
            FileCategory category,
            boolean readable,
            boolean writable
    ) {}

    public record Workspace(
            String workspaceId,
            String organizationId,
            String actorId,
            Provider provider,
            String providerInstanceId,
            String nativeRepositoryId,
            String cloneUrl,
            String requestedRef,
            String sourceCommit,
            String currentHeadCommit,
            String branch,
            Completeness completeness,
            boolean codeOwnersPresent,
            List<String> blockers,
            List<FileEntry> files,
            List<String> pendingPaths,
            String pushedCommit,
            String pullRequestId,
            String pullRequestUrl,
            Instant createdAt,
            String status,
            boolean externalOperationExecuted
    ) {}

    public record FileContent(
            String workspaceId,
            String path,
            String sha256,
            FileCategory category,
            String encoding,
            String content
    ) {}

    public record FileChange(
            ChangeOperation operation,
            String path,
            String expectedSha256,
            String contentBase64
    ) {}

    public record ChangeRequest(
            String organizationId,
            String actorId,
            String baseCommit,
            String intent,
            boolean codeOwnerApproval,
            List<String> approvedPaths,
            List<FileChange> changes
    ) {}

    public record ChangeResult(
            String workspaceId,
            String sourceCommit,
            String branch,
            List<String> changedPaths,
            List<String> deletedPaths,
            List<String> untrackedPaths,
            String status,
            boolean pushed,
            boolean pullRequestCreated,
            boolean deployed
    ) {}

    public record CommitRequest(
            String organizationId,
            String actorId,
            String expectedHeadCommit,
            String message,
            boolean codeOwnerApproval,
            List<String> approvedPaths
    ) {}

    public record CommitResult(
            String workspaceId,
            String sourceCommit,
            String commitSha,
            String branch,
            List<String> committedPaths,
            boolean signed,
            String status
    ) {}

    public record PushRequest(
            String organizationId,
            String actorId,
            String expectedCommit
    ) {}

    public record PushResult(
            String workspaceId,
            String commitSha,
            String remoteRef,
            String status,
            boolean externalOperationExecuted
    ) {}

    public record PullRequestRequest(
            String organizationId,
            String actorId,
            String expectedCommit,
            String baseBranch,
            String title,
            String body,
            String idempotencyKey
    ) {}

    public record PullRequestResult(
            String workspaceId,
            String providerPullRequestId,
            String url,
            String sourceCommit,
            String sourceBranch,
            String baseBranch,
            String status,
            boolean externalOperationExecuted
    ) {}

    public record WorkspaceMaterialization(
            String workspaceId,
            String sourceCommit,
            String resolvedCommitSha,
            String relativePath,
            String manifestSha256,
            List<String> excludedProtectedPaths,
            String status
    ) {}

    public record PullRequestContext(
            Provider provider,
            String providerInstanceId,
            String nativeRepositoryId,
            String sourceBranch,
            String sourceCommit,
            String baseBranch,
            String title,
            String body,
            String idempotencyKey
    ) {}

    @FunctionalInterface
    public interface PullRequestPublisher {
        PullRequestResult publish(
                String workspaceId,
                PullRequestContext context,
                EphemeralCredential credential
        );
    }

    public record Capability(
            List<Provider> providers,
            List<FileCategory> fileCategories,
            List<String> supportedProtocols,
            List<String> restrictions,
            String persistence,
            String externalDelivery
    ) {}

    private static final String MANIFEST = "workspace.properties";
    private static final String DELIVERY = "delivery.properties";
    private static final String REPOSITORY = "repository";
    private static final int MAX_CHANGE_COUNT = 100;
    private static final long MAX_CHANGE_BYTES = 2L * 1024 * 1024;
    private static final Set<String> PROTECTED_NAMES = Set.of(
            ".env", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_ed25519",
            "credentials", "credentials.json", "service-account.json"
    );

    private final Path root;
    private final int maximumFiles;
    private final long maximumRepositoryBytes;
    private final boolean allowControlledFileRepositories;
    private final Set<String> allowedGenericHosts;
    private final int maximumWorkspaces;
    private final Duration workspaceTtl;
    private final PullRequestPublisher pullRequests;

    public GitRepositoryWorkspaceService(
            Path root,
            int maximumFiles,
            long maximumRepositoryBytes,
            boolean allowControlledFileRepositories
    ) {
        this(root, maximumFiles, maximumRepositoryBytes, allowControlledFileRepositories,
                Set.of(), 1_000, Duration.ofDays(7), unsupportedPullRequests());
    }

    public GitRepositoryWorkspaceService(
            Path root,
            int maximumFiles,
            long maximumRepositoryBytes,
            boolean allowControlledFileRepositories,
            Set<String> allowedGenericHosts
    ) {
        this(root, maximumFiles, maximumRepositoryBytes, allowControlledFileRepositories,
                allowedGenericHosts, 1_000, Duration.ofDays(7), unsupportedPullRequests());
    }

    public GitRepositoryWorkspaceService(
            Path root,
            int maximumFiles,
            long maximumRepositoryBytes,
            boolean allowControlledFileRepositories,
            Set<String> allowedGenericHosts,
            int maximumWorkspaces,
            Duration workspaceTtl
    ) {
        this(root, maximumFiles, maximumRepositoryBytes,
                allowControlledFileRepositories, allowedGenericHosts,
                maximumWorkspaces, workspaceTtl, unsupportedPullRequests());
    }

    public GitRepositoryWorkspaceService(
            Path root,
            int maximumFiles,
            long maximumRepositoryBytes,
            boolean allowControlledFileRepositories,
            Set<String> allowedGenericHosts,
            int maximumWorkspaces,
            Duration workspaceTtl,
            PullRequestPublisher pullRequests
    ) {
        this.root = Objects.requireNonNull(root, "root").toAbsolutePath().normalize();
        if (this.root.getParent() == null) throw new IllegalArgumentException("workspace root must not be a filesystem root");
        if (maximumFiles < 1 || maximumFiles > 1_000_000) throw new IllegalArgumentException("maximumFiles is invalid");
        if (maximumRepositoryBytes < 1 || maximumRepositoryBytes > 100L * 1024 * 1024 * 1024) {
            throw new IllegalArgumentException("maximumRepositoryBytes is invalid");
        }
        if (maximumWorkspaces < 1 || maximumWorkspaces > 100_000) {
            throw new IllegalArgumentException("maximumWorkspaces is invalid");
        }
        if (workspaceTtl == null || workspaceTtl.isNegative() || workspaceTtl.isZero()
                || workspaceTtl.compareTo(Duration.ofDays(90)) > 0) {
            throw new IllegalArgumentException("workspaceTtl is invalid");
        }
        this.maximumFiles = maximumFiles;
        this.maximumRepositoryBytes = maximumRepositoryBytes;
        this.allowControlledFileRepositories = allowControlledFileRepositories;
        this.maximumWorkspaces = maximumWorkspaces;
        this.workspaceTtl = workspaceTtl;
        this.pullRequests = Objects.requireNonNull(pullRequests, "pullRequests");
        this.allowedGenericHosts = Objects.requireNonNull(
                allowedGenericHosts, "allowedGenericHosts").stream()
                .map(String::trim)
                .map(value -> value.toLowerCase(Locale.ROOT))
                .filter(value -> !value.isBlank())
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
        if (this.allowedGenericHosts.stream().anyMatch(host ->
                !host.matches("(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
                        && !host.matches("\\d{1,3}(?:\\.\\d{1,3}){3}"))) {
            throw new IllegalArgumentException("allowedGenericHosts contains an invalid host");
        }
        try {
            Files.createDirectories(this.root);
            if (Files.isSymbolicLink(this.root)
                    || !Files.isDirectory(this.root, LinkOption.NOFOLLOW_LINKS)) {
                throw new SecurityException("workspace root must be a regular directory");
            }
            setOwnerOnlyDirectory(this.root);
        } catch (IOException error) {
            throw new IllegalArgumentException("workspace root is unavailable", error);
        }
    }

    public Capability capability() {
        return new Capability(
                List.of(Provider.values()),
                List.of(FileCategory.values()),
                allowControlledFileRepositories ? List.of("https", "file-development") : List.of("https"),
                List.of(
                        "EXACT_COMMIT_REQUIRED",
                        "GENERIC_GIT_REQUIRES_EXACT_HOST_ALLOWLIST",
                        "SUBMODULES_REQUIRE_SEPARATE_AUTHORIZATION",
                        "LFS_POINTERS_REQUIRE_HYDRATION_AND_DIGEST_VERIFICATION",
                        "CODEOWNERS_REQUIRES_EXPLICIT_APPROVAL",
                        "BINARY_AND_SECRET_FILES_ARE_NOT_EDITABLE",
                        "WORKSPACES_ARE_COUNT_BOUNDED_AND_EXPIRE",
                        "PUSH_PR_MERGE_AND_DEPLOY_ARE_SEPARATE_AUTHORIZED_ACTIONS"
                ),
                "BOUNDED_FILESYSTEM_WORKSPACE",
                "NOT_RUN"
        );
    }

    public synchronized Workspace create(
            CreateRequest request,
            String credentialUsername,
            Optional<EphemeralCredential> credential
    ) {
        validateCreate(request);
        Objects.requireNonNull(credential, "credential");
        if (credential.isPresent()) requireText(credentialUsername, "credentialUsername", 128);
        purgeExpiredWorkspaces();
        if (workspaceCount() >= maximumWorkspaces) {
            throw new IllegalStateException("GIT_WORKSPACE_CAPACITY_EXCEEDED");
        }
        URI cloneUri = validateCloneUri(request.provider(), request.cloneUrl());
        if (!"file".equalsIgnoreCase(cloneUri.getScheme())
                && !request.providerInstanceId().equalsIgnoreCase(cloneUri.getHost())) {
            throw new SecurityException("GIT_PROVIDER_INSTANCE_HOST_MISMATCH");
        }
        String workspaceId = UUID.randomUUID().toString();
        Path directory = workspaceDirectory(workspaceId);
        Path repository = directory.resolve(REPOSITORY);
        try {
            Files.createDirectory(directory);
            setOwnerOnlyDirectory(directory);
            String sourceCommit;
            String resolvedRef;
            try (Git git = Git.init().setDirectory(repository.toFile()).call()) {
                RemoteRef remote = resolveRemote(cloneUri, request.requestedRef(), credentialUsername, credential);
                sourceCommit = remote.commit();
                resolvedRef = remote.fetchRef();
                var fetch = git.fetch()
                        .setRemote(cloneUri.toString())
                        .setDepth(1)
                        .setRefSpecs(new RefSpec("+" + resolvedRef + ":refs/elmos/source"));
                callFetch(fetch, credentialUsername, credential);
                ObjectId fetched = git.getRepository().resolve("refs/elmos/source^{commit}");
                if (fetched == null || !sourceCommit.equals(fetched.name())) {
                    throw new SecurityException("GIT_FETCHED_COMMIT_MISMATCH");
                }
                String branch = "elmos/workspace-" + workspaceId.substring(0, 8);
                git.checkout().setCreateBranch(true).setName(branch).setStartPoint(sourceCommit).call();
                writeManifest(directory, request, workspaceId, sourceCommit, branch, resolvedRef, Instant.now());
            }
            return inspect(request.organizationId(), request.actorId(), workspaceId);
        } catch (RuntimeException failure) {
            safeDelete(directory);
            throw failure;
        } catch (Exception failure) {
            safeDelete(directory);
            throw new IllegalStateException("GIT_WORKSPACE_CREATE_FAILED", failure);
        }
    }

    public synchronized Workspace inspect(String organizationId, String actorId, String workspaceId) {
        Manifest manifest = readManifest(organizationId, workspaceId);
        requireActor(manifest, actorId);
        Path repository = workspaceDirectory(workspaceId).resolve(REPOSITORY);
        Scan scan = scan(repository);
        List<String> blockers = new ArrayList<>();
        Completeness completeness = Completeness.COMPLETE;
        if (scan.submodules()) {
            completeness = Completeness.INCOMPLETE_SUBMODULES;
            blockers.add("SUBMODULES_REQUIRE_SEPARATE_AUTHORIZATION");
        }
        if (scan.lfsPointers()) {
            completeness = Completeness.INCOMPLETE_LFS;
            blockers.add("LFS_OBJECTS_NOT_HYDRATED_OR_VERIFIED");
        }
        boolean writable = completeness == Completeness.COMPLETE;
        List<FileEntry> files = scan.files().stream()
                .map(file -> new FileEntry(
                        file.path(),
                        file.bytes(),
                        file.sha256(),
                        category(file.path()),
                        !protectedPath(file.path()),
                        writable && !protectedPath(file.path())
                ))
                .toList();
        RepositoryState state = repositoryState(repository);
        Delivery delivery = readDelivery(workspaceId);
        String status = !state.pendingPaths().isEmpty()
                ? "LOCAL_CHANGES_PENDING"
                : delivery.pullRequestId() != null
                    ? "PULL_REQUEST_CREATED"
                    : state.headCommit().equals(delivery.pushedCommit())
                        ? "PUSHED_VERIFIED"
                        : !state.headCommit().equals(manifest.sourceCommit())
                            ? "COMMITTED_LOCAL"
                            : blockers.isEmpty() ? "READY_FOR_LOCAL_CHANGE" : "READ_ONLY_INCOMPLETE";
        return new Workspace(
                manifest.workspaceId(),
                manifest.organizationId(),
                manifest.actorId(),
                manifest.provider(),
                manifest.providerInstanceId(),
                manifest.nativeRepositoryId(),
                manifest.cloneUrl(),
                manifest.requestedRef(),
                manifest.sourceCommit(),
                state.headCommit(),
                manifest.branch(),
                completeness,
                scan.codeOwners(),
                List.copyOf(blockers),
                files,
                state.pendingPaths(),
                delivery.pushedCommit(),
                delivery.pullRequestId(),
                delivery.pullRequestUrl(),
                manifest.createdAt(),
                status,
                delivery.pushedCommit() != null || delivery.pullRequestId() != null
        );
    }

    public synchronized FileContent readFile(
            String organizationId,
            String actorId,
            String workspaceId,
            String relativePath
    ) {
        Manifest manifest = readManifest(organizationId, workspaceId);
        requireActor(manifest, actorId);
        String safePath = normalizeRelativePath(relativePath);
        if (protectedPath(safePath)) {
            throw new SecurityException("GIT_WORKSPACE_PROTECTED_FILE_NOT_READABLE");
        }
        Path file = resolveFile(workspaceId, safePath);
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(file)) {
            throw new IllegalArgumentException("GIT_WORKSPACE_FILE_NOT_READABLE");
        }
        try {
            long size = Files.size(file);
            if (size > MAX_CHANGE_BYTES) throw new IllegalArgumentException("GIT_WORKSPACE_FILE_TOO_LARGE");
            byte[] bytes = Files.readAllBytes(file);
            if (binary(bytes)) throw new IllegalArgumentException("GIT_WORKSPACE_BINARY_FILE_NOT_EXPOSED");
            return new FileContent(
                    manifest.workspaceId(),
                    safePath,
                    sha256(bytes),
                    category(safePath),
                    "UTF-8",
                    new String(bytes, StandardCharsets.UTF_8)
            );
        } catch (IOException error) {
            throw new IllegalStateException("GIT_WORKSPACE_FILE_READ_FAILED", error);
        }
    }

    public synchronized ChangeResult apply(String workspaceId, ChangeRequest request) {
        if (request == null) throw new IllegalArgumentException("GIT_WORKSPACE_CHANGE_REQUEST_REQUIRED");
        Manifest manifest = readManifest(request.organizationId(), workspaceId);
        requireIdentifier(request.actorId(), "actorId");
        if (!manifest.actorId().equals(request.actorId())) throw new SecurityException("GIT_WORKSPACE_ACTOR_MISMATCH");
        if (!manifest.sourceCommit().equals(request.baseCommit())) throw new SecurityException("GIT_WORKSPACE_BASE_COMMIT_MISMATCH");
        requireNarrative(request.intent(), "intent", 2_000);
        List<FileChange> changes = request.changes() == null ? List.of() : List.copyOf(request.changes());
        if (changes.isEmpty() || changes.size() > MAX_CHANGE_COUNT) {
            throw new IllegalArgumentException("GIT_WORKSPACE_CHANGE_COUNT_INVALID");
        }
        Workspace current = inspect(request.organizationId(), request.actorId(), workspaceId);
        if (current.completeness() != Completeness.COMPLETE) {
            throw new SecurityException("GIT_WORKSPACE_INCOMPLETE_READ_ONLY");
        }
        if (current.codeOwnersPresent() && !request.codeOwnerApproval()) {
            throw new SecurityException("GIT_WORKSPACE_CODEOWNER_APPROVAL_REQUIRED");
        }
        Set<String> approvals = request.approvedPaths() == null
                ? Set.of()
                : new LinkedHashSet<>(request.approvedPaths().stream().map(GitRepositoryWorkspaceService::normalizeRelativePath).toList());
        Set<String> seen = new LinkedHashSet<>();
        for (FileChange change : changes) {
            if (change == null || change.operation() == null) {
                throw new IllegalArgumentException("GIT_WORKSPACE_CHANGE_OPERATION_REQUIRED");
            }
            String path = normalizeRelativePath(change.path());
            if (!seen.add(path)) throw new IllegalArgumentException("GIT_WORKSPACE_DUPLICATE_CHANGE_PATH");
            if (!approvals.contains(path)) throw new SecurityException("GIT_WORKSPACE_PATH_NOT_EXPLICITLY_APPROVED");
            if (protectedPath(path)) throw new SecurityException("GIT_WORKSPACE_PROTECTED_PATH");
            if (change.operation() == ChangeOperation.DELETE
                    && change.contentBase64() != null
                    && !change.contentBase64().isBlank()) {
                throw new IllegalArgumentException("GIT_WORKSPACE_DELETE_CONTENT_FORBIDDEN");
            }
        }

        Path repository = workspaceDirectory(workspaceId).resolve(REPOSITORY);
        Map<Path, byte[]> backups = new LinkedHashMap<>();
        Set<Path> created = new LinkedHashSet<>();
        try {
            for (FileChange change : changes) {
                String path = normalizeRelativePath(change.path());
                Path target = resolveFile(workspaceId, path);
                boolean exists = Files.exists(target, LinkOption.NOFOLLOW_LINKS);
                if (exists && (!Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(target))) {
                    throw new SecurityException("GIT_WORKSPACE_NON_REGULAR_TARGET");
                }
                if (exists) {
                    if (Files.size(target) > MAX_CHANGE_BYTES) {
                        throw new IllegalArgumentException("GIT_WORKSPACE_FILE_TOO_LARGE");
                    }
                    byte[] original = Files.readAllBytes(target);
                    if (change.expectedSha256() == null || !sha256(original).equals(change.expectedSha256())) {
                        throw new SecurityException("GIT_WORKSPACE_CONCURRENT_CHANGE_DETECTED");
                    }
                    backups.put(target, original);
                } else {
                    if (change.expectedSha256() != null && !change.expectedSha256().isBlank()) {
                        throw new SecurityException("GIT_WORKSPACE_NEW_FILE_EXPECTED_HASH_FORBIDDEN");
                    }
                    created.add(target);
                }
                if (change.operation() == ChangeOperation.DELETE) {
                    if (!exists) throw new IllegalArgumentException("GIT_WORKSPACE_DELETE_TARGET_MISSING");
                    Files.delete(target);
                    continue;
                }
                byte[] content = decodeContent(change.contentBase64());
                if (binary(content)) throw new SecurityException("GIT_WORKSPACE_BINARY_WRITE_FORBIDDEN");
                Files.createDirectories(target.getParent());
                Path temporary = Files.createTempFile(target.getParent(), ".elmos-change-", ".tmp");
                try {
                    Files.write(temporary, content);
                    Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
                } finally {
                    Files.deleteIfExists(temporary);
                }
            }
            try (Git git = Git.open(repository.toFile())) {
                var status = git.status().call();
                List<String> changed = new ArrayList<>();
                changed.addAll(status.getModified());
                changed.addAll(status.getChanged());
                changed.addAll(status.getAdded());
                List<String> deleted = new ArrayList<>();
                deleted.addAll(status.getMissing());
                deleted.addAll(status.getRemoved());
                List<String> untracked = new ArrayList<>(status.getUntracked());
                changed = changed.stream().distinct().sorted().toList();
                deleted = deleted.stream().distinct().sorted().toList();
                untracked = untracked.stream().distinct().sorted().toList();
                return new ChangeResult(
                        workspaceId,
                        manifest.sourceCommit(),
                        manifest.branch(),
                        changed,
                        deleted,
                        untracked,
                        "LOCAL_CHANGES_READY_FOR_REVIEW",
                        false,
                        false,
                        false
                );
            }
        } catch (RuntimeException failure) {
            rollback(backups, created);
            throw failure;
        } catch (Exception failure) {
            rollback(backups, created);
            throw new IllegalStateException("GIT_WORKSPACE_CHANGE_FAILED", failure);
        }
    }

    public synchronized void delete(String organizationId, String actorId, String workspaceId) {
        Manifest manifest = readManifest(organizationId, workspaceId);
        requireActor(manifest, actorId);
        safeDelete(workspaceDirectory(workspaceId));
    }

    public synchronized CommitResult commit(String workspaceId, CommitRequest request) {
        Objects.requireNonNull(request, "request");
        Manifest manifest = readManifest(request.organizationId(), workspaceId);
        requireActor(manifest, request.actorId());
        requireCommit(request.expectedHeadCommit(), "expectedHeadCommit");
        requireNarrative(request.message(), "message", 4_000);
        Workspace workspace = inspect(request.organizationId(), request.actorId(), workspaceId);
        if (workspace.completeness() != Completeness.COMPLETE) {
            throw new SecurityException("GIT_WORKSPACE_INCOMPLETE_READ_ONLY");
        }
        if (workspace.codeOwnersPresent() && !request.codeOwnerApproval()) {
            throw new SecurityException("GIT_WORKSPACE_CODEOWNER_APPROVAL_REQUIRED");
        }
        Path repository = workspaceDirectory(workspaceId).resolve(REPOSITORY);
        try (Git git = Git.open(repository.toFile())) {
            ObjectId head = git.getRepository().resolve("HEAD^{commit}");
            if (head == null || !head.name().equals(request.expectedHeadCommit())) {
                throw new SecurityException("GIT_WORKSPACE_HEAD_COMMIT_MISMATCH");
            }
            var status = git.status().call();
            Set<String> actual = new LinkedHashSet<>();
            actual.addAll(status.getModified());
            actual.addAll(status.getChanged());
            actual.addAll(status.getAdded());
            actual.addAll(status.getMissing());
            actual.addAll(status.getRemoved());
            actual.addAll(status.getUntracked());
            if (actual.isEmpty()) throw new IllegalArgumentException("GIT_WORKSPACE_NOTHING_TO_COMMIT");
            Set<String> approved = new LinkedHashSet<>(
                    Objects.requireNonNullElse(request.approvedPaths(), List.<String>of())
                            .stream().map(GitRepositoryWorkspaceService::normalizeRelativePath).toList());
            if (!approved.equals(actual) || approved.stream().anyMatch(GitRepositoryWorkspaceService::protectedPath)) {
                throw new SecurityException("GIT_WORKSPACE_COMMIT_PATH_SCOPE_MISMATCH");
            }
            for (String path : actual) {
                if (status.getMissing().contains(path) || status.getRemoved().contains(path)) {
                    git.rm().addFilepattern(path).call();
                } else {
                    git.add().addFilepattern(path).call();
                }
            }
            var committed = git.commit()
                    .setMessage(request.message())
                    .setAuthor(request.actorId(), "noreply@elmos.invalid")
                    .setCommitter(request.actorId(), "noreply@elmos.invalid")
                    .call();
            return new CommitResult(
                    workspaceId, manifest.sourceCommit(), committed.name(), manifest.branch(),
                    actual.stream().sorted().toList(), false, "COMMITTED_LOCAL");
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("GIT_WORKSPACE_COMMIT_FAILED", error);
        }
    }

    public synchronized PushResult push(
            String workspaceId,
            PushRequest request,
            String credentialUsername,
            Optional<EphemeralCredential> credential
    ) {
        Objects.requireNonNull(request, "request");
        Manifest manifest = readManifest(request.organizationId(), workspaceId);
        requireActor(manifest, request.actorId());
        requireCommit(request.expectedCommit(), "expectedCommit");
        URI remote = validateCloneUri(manifest.provider(), manifest.cloneUrl());
        if (!"file".equalsIgnoreCase(remote.getScheme()) && credential.isEmpty()) {
            throw new SecurityException("GIT_PUSH_CREDENTIAL_REQUIRED");
        }
        Path repository = workspaceDirectory(workspaceId).resolve(REPOSITORY);
        try (Git git = Git.open(repository.toFile())) {
            ObjectId head = git.getRepository().resolve("HEAD^{commit}");
            if (head == null || !head.name().equals(request.expectedCommit())) {
                throw new SecurityException("GIT_WORKSPACE_HEAD_COMMIT_MISMATCH");
            }
            if (!git.status().call().isClean()) throw new SecurityException("GIT_WORKSPACE_DIRTY_PUSH_FORBIDDEN");
            String remoteRef = "refs/heads/" + manifest.branch();
            var command = git.push()
                    .setRemote(remote.toString())
                    .setRefSpecs(new RefSpec(manifest.branch() + ":" + remoteRef))
                    .setForce(false);
            Iterable<org.eclipse.jgit.transport.PushResult> results =
                    callPush(command, credentialUsername, credential);
            boolean accepted = false;
            for (var result : results) {
                RemoteRefUpdate update = result.getRemoteUpdate(remoteRef);
                if (update != null && (update.getStatus() == RemoteRefUpdate.Status.OK
                        || update.getStatus() == RemoteRefUpdate.Status.UP_TO_DATE)) {
                    accepted = true;
                }
            }
            if (!accepted) throw new IllegalStateException("GIT_REMOTE_PUSH_REJECTED");
            RemoteRef verified = resolveRemote(remote, remoteRef, credentialUsername, credential);
            if (!request.expectedCommit().equals(verified.commit())) {
                throw new SecurityException("GIT_REMOTE_PUSH_VERIFICATION_FAILED");
            }
            writeDelivery(workspaceId, new Delivery(
                    request.expectedCommit(), null, null, null, null));
            return new PushResult(
                    workspaceId, request.expectedCommit(), remoteRef,
                    "PUSHED_VERIFIED", true);
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("GIT_WORKSPACE_PUSH_FAILED", error);
        }
    }

    public synchronized PullRequestResult createPullRequest(
            String workspaceId,
            PullRequestRequest request,
            String credentialUsername,
            Optional<EphemeralCredential> credential
    ) {
        Objects.requireNonNull(request, "request");
        Manifest manifest = readManifest(request.organizationId(), workspaceId);
        requireActor(manifest, request.actorId());
        requireCommit(request.expectedCommit(), "expectedCommit");
        validateRef(request.baseBranch());
        requireNarrative(request.title(), "title", 240);
        requireNarrative(request.body(), "body", 8_000);
        requireIdentifier(request.idempotencyKey(), "idempotencyKey");
        if (manifest.provider() == Provider.GENERIC_GIT) {
            throw new IllegalArgumentException("GENERIC_GIT_PULL_REQUEST_UNSUPPORTED");
        }
        if (credential.isEmpty()) throw new SecurityException("GIT_PULL_REQUEST_CREDENTIAL_REQUIRED");
        URI remote = validateCloneUri(manifest.provider(), manifest.cloneUrl());
        RemoteRef verified = resolveRemote(
                remote, "refs/heads/" + manifest.branch(), credentialUsername, credential);
        if (!request.expectedCommit().equals(verified.commit())) {
            throw new SecurityException("GIT_PULL_REQUEST_SOURCE_NOT_PUSHED");
        }
        Delivery existing = readDelivery(workspaceId);
        String requestDigest = pullRequestDigest(request, manifest.branch());
        if (existing.pullRequestId() != null) {
            if (!request.idempotencyKey().equals(existing.idempotencyKey())
                    || !requestDigest.equals(existing.pullRequestRequestDigest())
                    || existing.pullRequestUrl() == null) {
                throw new SecurityException("GIT_PULL_REQUEST_ALREADY_CREATED_WITH_DIFFERENT_REQUEST");
            }
            return new PullRequestResult(
                    workspaceId, existing.pullRequestId(), existing.pullRequestUrl(),
                    request.expectedCommit(), manifest.branch(), request.baseBranch(),
                    "PULL_REQUEST_ALREADY_CREATED", true);
        }
        PullRequestResult result = pullRequests.publish(
                workspaceId,
                new PullRequestContext(
                        manifest.provider(), manifest.providerInstanceId(),
                        manifest.nativeRepositoryId(), manifest.branch(),
                        request.expectedCommit(), request.baseBranch(),
                        request.title(), request.body(), request.idempotencyKey()),
                credential.orElseThrow());
        writeDelivery(workspaceId, new Delivery(
                request.expectedCommit(), result.providerPullRequestId(), result.url(),
                request.idempotencyKey(), requestDigest));
        return result;
    }

    public synchronized WorkspaceMaterialization materialize(
            String organizationId,
            String actorId,
            String workspaceId,
            String expectedHeadCommit,
            Path materializedRoot
    ) {
        Manifest manifest = readManifest(organizationId, workspaceId);
        requireActor(manifest, actorId);
        requireCommit(expectedHeadCommit, "expectedHeadCommit");
        Path targetRoot = Objects.requireNonNull(materializedRoot, "materializedRoot")
                .toAbsolutePath().normalize();
        if (targetRoot.getParent() == null) {
            throw new IllegalArgumentException("materializedRoot must not be a filesystem root");
        }
        Workspace workspace = inspect(organizationId, actorId, workspaceId);
        if (workspace.completeness() != Completeness.COMPLETE
                || !workspace.pendingPaths().isEmpty()
                || !expectedHeadCommit.equals(workspace.currentHeadCommit())) {
            throw new SecurityException("GIT_WORKSPACE_MATERIALIZATION_SOURCE_NOT_IMMUTABLE");
        }
        Path repository = workspaceDirectory(workspaceId).resolve(REPOSITORY);
        Scan scan = scan(repository);
        List<RawFile> included = scan.files().stream()
                .filter(file -> !protectedPath(file.path()))
                .toList();
        List<String> excluded = scan.files().stream()
                .map(RawFile::path)
                .filter(GitRepositoryWorkspaceService::protectedPath)
                .sorted()
                .toList();
        String manifestDigest = sha256(included.stream()
                .map(file -> file.path() + "\0" + file.bytes() + "\0" + file.sha256() + "\n")
                .collect(java.util.stream.Collectors.joining())
                .getBytes(StandardCharsets.UTF_8));
        String tenantSegment = sha256(organizationId.getBytes(StandardCharsets.UTF_8)).substring(0, 16);
        Path relative = Path.of("repository-workspaces", tenantSegment, workspaceId, expectedHeadCommit);
        Path target = targetRoot.resolve(relative).normalize();
        if (!target.startsWith(targetRoot) || target.equals(targetRoot)) {
            throw new SecurityException("GIT_WORKSPACE_MATERIALIZATION_PATH_ESCAPE");
        }
        Path marker = target.resolve(".elmos-workspace-materialization.properties");
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
            verifyMaterialization(target, marker, workspaceId, expectedHeadCommit, manifestDigest, included);
            return new WorkspaceMaterialization(
                    workspaceId, manifest.sourceCommit(), expectedHeadCommit,
                    relative.toString().replace('\\', '/'), manifestDigest, excluded,
                    "MATERIALIZED_VERIFIED");
        }
        try {
            Files.createDirectories(target.getParent());
            Path temporary = Files.createTempDirectory(target.getParent(), ".elmos-materialize-");
            try {
                for (RawFile file : included) {
                    Path source = repository.resolve(file.path()).normalize();
                    Path output = temporary.resolve(file.path()).normalize();
                    if (!source.startsWith(repository) || !output.startsWith(temporary)) {
                        throw new SecurityException("GIT_WORKSPACE_MATERIALIZATION_FILE_ESCAPE");
                    }
                    Files.createDirectories(output.getParent());
                    Files.copy(source, output);
                    if (!file.sha256().equals(sha256(output))) {
                        throw new SecurityException("GIT_WORKSPACE_MATERIALIZATION_DIGEST_MISMATCH");
                    }
                }
                Properties properties = new Properties();
                properties.setProperty("workspaceId", workspaceId);
                properties.setProperty("organizationDigest",
                        sha256(organizationId.getBytes(StandardCharsets.UTF_8)));
                properties.setProperty("sourceCommit", manifest.sourceCommit());
                properties.setProperty("resolvedCommitSha", expectedHeadCommit);
                properties.setProperty("manifestSha256", manifestDigest);
                properties.setProperty("excludedProtectedPaths", String.join(",", excluded));
                try (var output = Files.newOutputStream(
                        temporary.resolve(".elmos-workspace-materialization.properties"))) {
                    properties.store(output, "ELMOS immutable repository handoff");
                }
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
            } catch (RuntimeException | IOException error) {
                deleteConfined(temporary, targetRoot);
                throw error;
            }
        } catch (RuntimeException error) {
            throw error;
        } catch (IOException error) {
            throw new IllegalStateException("GIT_WORKSPACE_MATERIALIZATION_FAILED", error);
        }
        return new WorkspaceMaterialization(
                workspaceId, manifest.sourceCommit(), expectedHeadCommit,
                relative.toString().replace('\\', '/'), manifestDigest, excluded,
                "MATERIALIZED_VERIFIED");
    }

    private static void verifyMaterialization(
            Path target,
            Path marker,
            String workspaceId,
            String expectedHeadCommit,
            String manifestDigest,
            List<RawFile> included
    ) {
        if (Files.isSymbolicLink(target) || !Files.isDirectory(target, LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(marker)
                || !Files.isRegularFile(marker, LinkOption.NOFOLLOW_LINKS)) {
            throw new SecurityException("GIT_WORKSPACE_MATERIALIZATION_INVALID");
        }
        Properties properties = new Properties();
        try (var input = Files.newInputStream(marker)) {
            properties.load(input);
            if (!workspaceId.equals(properties.getProperty("workspaceId"))
                    || !expectedHeadCommit.equals(properties.getProperty("resolvedCommitSha"))
                    || !manifestDigest.equals(properties.getProperty("manifestSha256"))) {
                throw new SecurityException("GIT_WORKSPACE_MATERIALIZATION_IDENTITY_MISMATCH");
            }
            for (RawFile file : included) {
                Path materialized = target.resolve(file.path()).normalize();
                if (!materialized.startsWith(target)
                        || Files.isSymbolicLink(materialized)
                        || !Files.isRegularFile(materialized, LinkOption.NOFOLLOW_LINKS)
                        || Files.size(materialized) != file.bytes()
                        || !file.sha256().equals(sha256(materialized))) {
                    throw new SecurityException("GIT_WORKSPACE_MATERIALIZATION_TAMPERED");
                }
            }
        } catch (RuntimeException error) {
            throw error;
        } catch (IOException error) {
            throw new IllegalStateException("GIT_WORKSPACE_MATERIALIZATION_VERIFY_FAILED", error);
        }
    }

    private static void deleteConfined(Path target, Path root) {
        if (target == null || !target.normalize().startsWith(root) || target.normalize().equals(root)) return;
        try {
            Files.walkFileTree(target, new SimpleFileVisitor<>() {
                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
                        throws IOException {
                    Files.deleteIfExists(file);
                    return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult postVisitDirectory(Path directory, IOException error)
                        throws IOException {
                    if (error != null) throw error;
                    Files.deleteIfExists(directory);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException ignored) {
            // Preserve the original materialization failure.
        }
    }

    private RepositoryState repositoryState(Path repository) {
        try (Git git = Git.open(repository.toFile())) {
            ObjectId head = git.getRepository().resolve("HEAD^{commit}");
            if (head == null) throw new SecurityException("GIT_WORKSPACE_HEAD_MISSING");
            var status = git.status().call();
            Set<String> pending = new LinkedHashSet<>();
            pending.addAll(status.getModified());
            pending.addAll(status.getChanged());
            pending.addAll(status.getAdded());
            pending.addAll(status.getMissing());
            pending.addAll(status.getRemoved());
            pending.addAll(status.getUntracked());
            return new RepositoryState(head.name(), pending.stream().sorted().toList());
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("GIT_WORKSPACE_STATE_READ_FAILED", error);
        }
    }

    private Delivery readDelivery(String workspaceId) {
        Path path = workspaceDirectory(workspaceId).resolve(DELIVERY);
        if (!Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
            return new Delivery(null, null, null, null, null);
        }
        if (Files.isSymbolicLink(path) || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new SecurityException("GIT_WORKSPACE_DELIVERY_STATE_INVALID");
        }
        Properties properties = new Properties();
        try (var input = Files.newInputStream(path)) {
            properties.load(input);
        } catch (IOException error) {
            throw new IllegalStateException("GIT_WORKSPACE_DELIVERY_STATE_READ_FAILED", error);
        }
        String pushedCommit = optionalProperty(properties, "pushedCommit");
        String pullRequestId = optionalProperty(properties, "pullRequestId");
        String pullRequestUrl = optionalProperty(properties, "pullRequestUrl");
        String idempotencyKey = optionalProperty(properties, "idempotencyKey");
        String requestDigest = optionalProperty(properties, "pullRequestRequestDigest");
        if (pushedCommit != null) requireCommit(pushedCommit, "pushedCommit");
        if ((pullRequestId == null) != (pullRequestUrl == null)
                || (pullRequestId == null) != (idempotencyKey == null)
                || (pullRequestId == null) != (requestDigest == null)
                || (requestDigest != null && !requestDigest.matches("[0-9a-f]{64}"))) {
            throw new SecurityException("GIT_WORKSPACE_DELIVERY_STATE_INCOMPLETE");
        }
        return new Delivery(pushedCommit, pullRequestId, pullRequestUrl, idempotencyKey, requestDigest);
    }

    private void writeDelivery(String workspaceId, Delivery delivery) {
        Path path = workspaceDirectory(workspaceId).resolve(DELIVERY);
        Delivery current = readDelivery(workspaceId);
        Properties properties = new Properties();
        putOptional(properties, "pushedCommit",
                delivery.pushedCommit() != null ? delivery.pushedCommit() : current.pushedCommit());
        putOptional(properties, "pullRequestId",
                delivery.pullRequestId() != null ? delivery.pullRequestId() : current.pullRequestId());
        putOptional(properties, "pullRequestUrl",
                delivery.pullRequestUrl() != null ? delivery.pullRequestUrl() : current.pullRequestUrl());
        putOptional(properties, "idempotencyKey",
                delivery.idempotencyKey() != null ? delivery.idempotencyKey() : current.idempotencyKey());
        putOptional(properties, "pullRequestRequestDigest",
                delivery.pullRequestRequestDigest() != null
                        ? delivery.pullRequestRequestDigest()
                        : current.pullRequestRequestDigest());
        Path temporary = path.resolveSibling(DELIVERY + "." + UUID.randomUUID() + ".tmp");
        try (var output = Files.newOutputStream(temporary)) {
            properties.store(output, "ELMOS repository delivery state; contains no credential");
            Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            setOwnerOnly(path);
        } catch (IOException error) {
            try { Files.deleteIfExists(temporary); } catch (IOException ignored) { }
            throw new IllegalStateException("GIT_WORKSPACE_DELIVERY_STATE_WRITE_FAILED", error);
        }
    }

    private static String pullRequestDigest(PullRequestRequest request, String sourceBranch) {
        return sha256((request.expectedCommit() + "\n" + sourceBranch + "\n"
                + request.baseBranch() + "\n" + request.title() + "\n" + request.body())
                .getBytes(StandardCharsets.UTF_8));
    }

    private static String optionalProperty(Properties properties, String key) {
        String value = properties.getProperty(key);
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static void putOptional(Properties properties, String key, String value) {
        if (value != null) properties.setProperty(key, value);
    }

    private record RepositoryState(String headCommit, List<String> pendingPaths) {}
    private record Delivery(
            String pushedCommit,
            String pullRequestId,
            String pullRequestUrl,
            String idempotencyKey,
            String pullRequestRequestDigest
    ) {}

    private static void requireActor(Manifest manifest, String actorId) {
        requireIdentifier(actorId, "actorId");
        if (!manifest.actorId().equals(actorId)) {
            throw new SecurityException("GIT_WORKSPACE_ACTOR_MISMATCH");
        }
    }

    private static void requireCommit(String value, String field) {
        if (value == null || !value.matches("[0-9a-f]{40}")) {
            throw new IllegalArgumentException(field + " is invalid");
        }
    }

    private static PullRequestPublisher unsupportedPullRequests() {
        return (workspaceId, context, credential) -> {
            throw new IllegalStateException("GIT_PULL_REQUEST_PUBLISHER_NOT_CONFIGURED");
        };
    }

    private RemoteRef resolveRemote(
            URI uri,
            String requestedRef,
            String username,
            Optional<EphemeralCredential> credential
    ) {
        validateRef(requestedRef);
        try {
            var command = Git.lsRemoteRepository()
                    .setRemote(uri.toString())
                    .setHeads(true)
                    .setTags(true);
            Collection<Ref> advertised = callLsRemote(command, username, credential);
            Map<String, Ref> refs = new HashMap<>();
            advertised.forEach(ref -> refs.put(ref.getName(), ref));
            if (requestedRef.matches("[0-9a-f]{40}")) {
                String advertisedRef = refs.values().stream()
                        .filter(ref -> ref.getObjectId() != null
                                && requestedRef.equals(ref.getObjectId().name()))
                        .map(ref -> ref.getName().endsWith("^{}")
                                ? ref.getName().substring(0, ref.getName().length() - 3)
                                : ref.getName())
                        .sorted()
                        .findFirst()
                        .orElseThrow(() -> new SecurityException("GIT_EXACT_COMMIT_NOT_ADVERTISED"));
                return new RemoteRef(requestedRef, advertisedRef);
            }
            String full = requestedRef.startsWith("refs/")
                    ? requestedRef
                    : refs.containsKey("refs/heads/" + requestedRef)
                    ? "refs/heads/" + requestedRef
                    : "refs/tags/" + requestedRef;
            Ref ref = refs.get(full);
            if (ref == null || ref.getObjectId() == null) throw new IllegalArgumentException("GIT_REF_NOT_FOUND");
            Ref peeled = refs.get(full + "^{}");
            String commit = peeled == null ? ref.getObjectId().name() : peeled.getObjectId().name();
            if (!commit.matches("[0-9a-f]{40}")) throw new SecurityException("GIT_REF_NOT_EXACT_COMMIT");
            return new RemoteRef(commit, full);
        } catch (RuntimeException failure) {
            throw failure;
        } catch (Exception failure) {
            throw new IllegalStateException("GIT_REF_RESOLUTION_FAILED", failure);
        }
    }

    private URI validateCloneUri(Provider provider, String raw) {
        requireText(raw, "cloneUrl", 2_048);
        URI uri;
        try {
            uri = URI.create(raw);
        } catch (RuntimeException error) {
            throw new IllegalArgumentException("GIT_CLONE_URL_INVALID", error);
        }
        if (uri.getUserInfo() != null || uri.getFragment() != null || uri.getQuery() != null) {
            throw new SecurityException("GIT_CLONE_URL_MUST_NOT_CONTAIN_CREDENTIALS_QUERY_OR_FRAGMENT");
        }
        if ("file".equalsIgnoreCase(uri.getScheme())) {
            if (!allowControlledFileRepositories || provider != Provider.GENERIC_GIT) {
                throw new SecurityException("GIT_FILE_PROTOCOL_NOT_ALLOWED");
            }
            return uri;
        }
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null) {
            throw new SecurityException("GIT_ONLY_HTTPS_IS_SUPPORTED");
        }
        String host = uri.getHost().toLowerCase(Locale.ROOT);
        if (provider == Provider.GITHUB && !"github.com".equals(host)) {
            throw new SecurityException("GITHUB_PROVIDER_HOST_MISMATCH");
        }
        if (provider == Provider.GITEE && !"gitee.com".equals(host)) {
            throw new SecurityException("GITEE_PROVIDER_HOST_MISMATCH");
        }
        if (provider == Provider.GENERIC_GIT && !allowedGenericHosts.contains(host)) {
            throw new SecurityException("GENERIC_GIT_HOST_NOT_ALLOWED");
        }
        return uri;
    }

    private Scan scan(Path repository) {
        List<RawFile> files = new ArrayList<>();
        long[] totals = new long[]{0, 0};
        boolean[] special = new boolean[]{false, false, false};
        try {
            Files.walkFileTree(repository, EnumSet.noneOf(java.nio.file.FileVisitOption.class), Integer.MAX_VALUE,
                    new SimpleFileVisitor<>() {
                        @Override
                        public FileVisitResult preVisitDirectory(Path directory, BasicFileAttributes attributes) {
                            if (directory.equals(repository.resolve(".git"))) return FileVisitResult.SKIP_SUBTREE;
                            if (Files.isSymbolicLink(directory)) throw new SecurityException("GIT_WORKSPACE_SYMLINK_FORBIDDEN");
                            return FileVisitResult.CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFile(Path file, BasicFileAttributes attributes) throws IOException {
                            if (Files.isSymbolicLink(file) || !attributes.isRegularFile()) {
                                throw new SecurityException("GIT_WORKSPACE_NON_REGULAR_FILE_FORBIDDEN");
                            }
                            totals[0]++;
                            totals[1] += attributes.size();
                            if (totals[0] > maximumFiles || totals[1] > maximumRepositoryBytes) {
                                throw new SecurityException("GIT_WORKSPACE_REPOSITORY_LIMIT_EXCEEDED");
                            }
                            String relative = repository.relativize(file).toString().replace('\\', '/');
                            if (relative.equals(".gitmodules") && attributes.size() > 0) special[0] = true;
                            if (relative.equals(".gitattributes") && attributes.size() <= MAX_CHANGE_BYTES) {
                                String attributesText = Files.readString(file, StandardCharsets.UTF_8);
                                if (attributesText.matches("(?s).*filter\\s*=\\s*lfs.*")) special[1] = true;
                            }
                            if (relative.equals("CODEOWNERS") || relative.endsWith("/CODEOWNERS")) special[2] = true;
                            files.add(new RawFile(relative, attributes.size(), sha256(file)));
                            return FileVisitResult.CONTINUE;
                        }
                    });
        } catch (IOException error) {
            throw new IllegalStateException("GIT_WORKSPACE_SCAN_FAILED", error);
        }
        files.sort(Comparator.comparing(RawFile::path));
        return new Scan(List.copyOf(files), special[0], special[1], special[2]);
    }

    private void writeManifest(
            Path directory,
            CreateRequest request,
            String workspaceId,
            String sourceCommit,
            String branch,
            String resolvedRef,
            Instant createdAt
    ) throws IOException {
        Properties properties = new Properties();
        properties.setProperty("workspaceId", workspaceId);
        properties.setProperty("organizationId", request.organizationId());
        properties.setProperty("actorId", request.actorId());
        properties.setProperty("provider", request.provider().name());
        properties.setProperty("providerInstanceId", request.providerInstanceId());
        properties.setProperty("nativeRepositoryId", request.nativeRepositoryId());
        properties.setProperty("cloneUrl", request.cloneUrl());
        properties.setProperty("requestedRef", request.requestedRef());
        properties.setProperty("resolvedRef", resolvedRef);
        properties.setProperty("sourceCommit", sourceCommit);
        properties.setProperty("branch", branch);
        properties.setProperty("createdAt", createdAt.toString());
        Path temporary = Files.createTempFile(directory, ".workspace-", ".tmp");
        try (var output = Files.newOutputStream(temporary)) {
            properties.store(output, "ELMOS governed Git workspace");
        }
        setOwnerOnly(temporary);
        Files.move(temporary, directory.resolve(MANIFEST), StandardCopyOption.ATOMIC_MOVE);
    }

    private Manifest readManifest(String organizationId, String workspaceId) {
        requireIdentifier(organizationId, "organizationId");
        requireUuid(workspaceId, "workspaceId");
        Path manifestPath = workspaceDirectory(workspaceId).resolve(MANIFEST);
        Properties properties = new Properties();
        try (var input = Files.newInputStream(manifestPath)) {
            properties.load(input);
        } catch (IOException error) {
            throw new IllegalArgumentException("GIT_WORKSPACE_NOT_FOUND", error);
        }
        Manifest manifest = new Manifest(
                properties.getProperty("workspaceId"),
                properties.getProperty("organizationId"),
                properties.getProperty("actorId"),
                Provider.valueOf(properties.getProperty("provider")),
                properties.getProperty("providerInstanceId"),
                properties.getProperty("nativeRepositoryId"),
                properties.getProperty("cloneUrl"),
                properties.getProperty("requestedRef"),
                properties.getProperty("resolvedRef"),
                properties.getProperty("sourceCommit"),
                properties.getProperty("branch"),
                Instant.parse(properties.getProperty("createdAt"))
        );
        if (!manifest.organizationId().equals(organizationId)) throw new SecurityException("GIT_WORKSPACE_TENANT_MISMATCH");
        if (!manifest.createdAt().plus(workspaceTtl).isAfter(Instant.now())) {
            safeDelete(workspaceDirectory(workspaceId));
            throw new IllegalArgumentException("GIT_WORKSPACE_EXPIRED");
        }
        return manifest;
    }

    private void purgeExpiredWorkspaces() {
        Instant cutoff = Instant.now().minus(workspaceTtl);
        try (var directories = Files.list(root)) {
            directories
                    .filter(path -> Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS))
                    .filter(path -> {
                        try {
                            UUID.fromString(path.getFileName().toString());
                            return true;
                        } catch (RuntimeException ignored) {
                            return false;
                        }
                    })
                    .toList()
                    .forEach(directory -> {
                        Path manifest = directory.resolve(MANIFEST);
                        Properties properties = new Properties();
                        try (var input = Files.newInputStream(manifest)) {
                            properties.load(input);
                            Instant createdAt = Instant.parse(properties.getProperty("createdAt"));
                            if (directory.getFileName().toString().equals(properties.getProperty("workspaceId"))
                                    && !createdAt.isAfter(cutoff)) {
                                safeDelete(directory);
                            }
                        } catch (RuntimeException | IOException ignored) {
                            // Unknown or corrupt directories are never auto-deleted.
                        }
                    });
        } catch (IOException error) {
            throw new IllegalStateException("GIT_WORKSPACE_CLEANUP_FAILED", error);
        }
    }

    private long workspaceCount() {
        try (var directories = Files.list(root)) {
            return directories.filter(path ->
                    Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                            && path.getFileName().toString().matches(
                            "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"))
                    .count();
        } catch (IOException error) {
            throw new IllegalStateException("GIT_WORKSPACE_CAPACITY_CHECK_FAILED", error);
        }
    }

    private Path workspaceDirectory(String workspaceId) {
        requireUuid(workspaceId, "workspaceId");
        Path resolved = root.resolve(workspaceId).normalize();
        if (!resolved.startsWith(root) || resolved.equals(root)) throw new SecurityException("GIT_WORKSPACE_PATH_ESCAPE");
        return resolved;
    }

    private Path resolveFile(String workspaceId, String relativePath) {
        Path repository = workspaceDirectory(workspaceId).resolve(REPOSITORY).normalize();
        Path resolved = repository.resolve(relativePath).normalize();
        if (!resolved.startsWith(repository) || resolved.equals(repository)) {
            throw new SecurityException("GIT_WORKSPACE_FILE_PATH_ESCAPE");
        }
        return resolved;
    }

    private void validateCreate(CreateRequest request) {
        if (request == null) throw new IllegalArgumentException("GIT_WORKSPACE_CREATE_REQUEST_REQUIRED");
        requireIdentifier(request.organizationId(), "organizationId");
        requireIdentifier(request.actorId(), "actorId");
        if (request.provider() == null) throw new IllegalArgumentException("provider is required");
        requireIdentifier(request.providerInstanceId(), "providerInstanceId");
        requireText(request.nativeRepositoryId(), "nativeRepositoryId", 256);
        validateRef(request.requestedRef());
    }

    private static String normalizeRelativePath(String value) {
        requireText(value, "path", 512);
        String normalized = value.replace('\\', '/');
        if (normalized.startsWith("/") || normalized.startsWith("-") || normalized.contains("../")
                || normalized.equals("..") || normalized.contains("\0") || normalized.contains("//")) {
            throw new SecurityException("GIT_WORKSPACE_RELATIVE_PATH_INVALID");
        }
        Path parsed = Path.of(normalized).normalize();
        if (parsed.isAbsolute() || parsed.startsWith("..") || parsed.getNameCount() == 0) {
            throw new SecurityException("GIT_WORKSPACE_RELATIVE_PATH_INVALID");
        }
        return parsed.toString().replace('\\', '/');
    }

    private static boolean protectedPath(String relativePath) {
        String normalized = relativePath.toLowerCase();
        String name = Path.of(normalized).getFileName().toString();
        if (normalized.equals(".git") || normalized.startsWith(".git/")) return true;
        if (normalized.equals("ownership/policy.json")) return true;
        if (name.startsWith(".env.")) return true;
        if (PROTECTED_NAMES.contains(name)) return true;
        if (name.endsWith(".pem") || name.endsWith(".key") || name.endsWith(".p12")
                || name.endsWith(".pfx") || name.endsWith(".jks")) return true;
        return normalized.contains("/secrets/") || normalized.startsWith("secrets/");
    }

    private static FileCategory category(String relativePath) {
        String value = relativePath.toLowerCase();
        String name = Path.of(value).getFileName().toString();
        if (name.equals("readme") || name.startsWith("readme.") || name.endsWith(".md")
                || name.endsWith(".adoc") || name.endsWith(".rst") || name.endsWith(".txt")
                || value.startsWith("docs/")) {
            return FileCategory.DOCUMENTATION;
        }
        if (value.startsWith(".github/workflows/") || value.startsWith(".gitlab-ci")
                || value.startsWith(".circleci/") || value.startsWith(".azure-pipelines/")
                || name.startsWith("azure-pipelines.") || name.startsWith("cloudbuild.")
                || value.contains("/kubernetes/") || value.startsWith("kubernetes/")
                || value.startsWith("k8s/") || value.startsWith("helm/")
                || value.startsWith("terraform/") || value.startsWith("pulumi/")
                || value.startsWith("cloudformation/") || value.startsWith(".aws-sam/")
                || name.endsWith(".tf") || name.endsWith(".tfvars")
                || name.equals("serverless.yml") || name.equals("serverless.yaml")
                || name.equals("vercel.json") || name.equals("netlify.toml")
                || name.equals("fly.toml") || name.equals("render.yaml")
                || name.equals("render.yml") || name.equals("railway.json")) {
            return FileCategory.CLOUD_DEPLOYMENT;
        }
        if (name.equals("dockerfile") || name.startsWith("dockerfile.")
                || name.startsWith("docker-compose") || name.startsWith("compose.")
                || name.equals("procfile") || name.equals("nixpacks.toml")
                || value.startsWith(".devcontainer/") || value.startsWith("deploy/")
                || value.startsWith("scripts/deploy")) {
            return FileCategory.LOCAL_DEPLOYMENT;
        }
        if (value.startsWith("test/") || value.startsWith("tests/") || value.contains("/test/")
                || value.contains("/tests/") || name.endsWith("test.java")
                || name.endsWith("test.kt") || name.endsWith("_test.py")
                || name.endsWith(".spec.ts") || name.endsWith(".test.ts")
                || name.endsWith(".spec.js") || name.endsWith(".test.js")) {
            return FileCategory.TEST;
        }
        if (name.endsWith(".yml") || name.endsWith(".yaml") || name.endsWith(".json")
                || name.endsWith(".toml") || name.endsWith(".ini") || name.endsWith(".conf")
                || name.endsWith(".properties") || name.endsWith(".xml")
                || name.equals("makefile") || name.equals("justfile")) {
            return FileCategory.CONFIGURATION;
        }
        if (name.matches(".*\\.(java|kt|kts|groovy|cs|fs|fsx|vb|py|pyi|ts|tsx|js|jsx|mjs|cjs|vue|svelte|go|rs|php|rb|c|cc|cpp|h|hpp|swift|m|mm|dart|scala|sc|ex|exs|erl|hrl|lua|r|sql|sh|bash|zsh|fish|ps1)$")) {
            return FileCategory.SOURCE;
        }
        return FileCategory.OTHER;
    }

    private static byte[] decodeContent(String content) {
        if (content == null) throw new IllegalArgumentException("GIT_WORKSPACE_CONTENT_REQUIRED");
        long maximumEncodedBytes = ((MAX_CHANGE_BYTES + 2) / 3) * 4;
        if (content.length() > maximumEncodedBytes) {
            throw new IllegalArgumentException("GIT_WORKSPACE_CHANGE_TOO_LARGE");
        }
        byte[] decoded;
        try {
            decoded = Base64.getDecoder().decode(content);
        } catch (IllegalArgumentException error) {
            throw new IllegalArgumentException("GIT_WORKSPACE_CONTENT_BASE64_INVALID", error);
        }
        if (decoded.length > MAX_CHANGE_BYTES) {
            throw new IllegalArgumentException("GIT_WORKSPACE_CHANGE_TOO_LARGE");
        }
        return decoded;
    }

    private static boolean binary(byte[] content) {
        int maximum = Math.min(content.length, 8_192);
        for (int index = 0; index < maximum; index++) if (content[index] == 0) return true;
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(java.nio.ByteBuffer.wrap(content));
            return false;
        } catch (CharacterCodingException error) {
            return true;
        }
    }

    private static String sha256(byte[] content) {
        try {
            return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static String sha256(Path file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (DigestInputStream input = new DigestInputStream(Files.newInputStream(file), digest)) {
                input.transferTo(java.io.OutputStream.nullOutputStream());
            }
            return java.util.HexFormat.of().formatHex(digest.digest());
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static void validateRef(String ref) {
        if (ref == null || ref.isBlank() || ref.length() > 512 || ref.startsWith("-")
                || ref.contains("..") || ref.contains("@{") || ref.contains("\\")
                || (!ref.matches("[0-9a-f]{40}") && !ref.matches("(?:refs/(?:heads|tags)/)?[A-Za-z0-9._/-]+"))) {
            throw new SecurityException("GIT_REF_INVALID");
        }
    }

    private static void requireIdentifier(String value, String field) {
        requireText(value, field, 128);
        if (!value.matches("[A-Za-z0-9][A-Za-z0-9._:-]*")) throw new IllegalArgumentException(field + " is invalid");
    }

    private static void requireUuid(String value, String field) {
        try {
            UUID.fromString(value);
        } catch (RuntimeException error) {
            throw new IllegalArgumentException(field + " is invalid", error);
        }
    }

    private static void requireText(String value, String field, int maximum) {
        if (value == null || value.isBlank() || value.length() > maximum
                || value.indexOf('\0') >= 0 || value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(field + " is invalid");
        }
    }

    private static void requireNarrative(String value, String field, int maximum) {
        if (value == null || value.isBlank() || value.length() > maximum || value.indexOf('\0') >= 0) {
            throw new IllegalArgumentException(field + " is invalid");
        }
    }

    private static void setOwnerOnly(Path file) {
        try {
            if (Files.getFileStore(file).supportsFileAttributeView("posix")) {
                Files.setPosixFilePermissions(file, Set.of(
                        PosixFilePermission.OWNER_READ,
                        PosixFilePermission.OWNER_WRITE
                ));
            }
        } catch (IOException error) {
            throw new IllegalStateException("GIT_WORKSPACE_MANIFEST_PERMISSION_FAILED", error);
        }
    }

    private static void setOwnerOnlyDirectory(Path directory) {
        try {
            if (Files.getFileStore(directory).supportsFileAttributeView("posix")) {
                Files.setPosixFilePermissions(directory, Set.of(
                        PosixFilePermission.OWNER_READ,
                        PosixFilePermission.OWNER_WRITE,
                        PosixFilePermission.OWNER_EXECUTE
                ));
            }
        } catch (IOException error) {
            throw new IllegalStateException("GIT_WORKSPACE_DIRECTORY_PERMISSION_FAILED", error);
        }
    }

    private static void rollback(Map<Path, byte[]> backups, Set<Path> created) {
        for (Path path : created) {
            try {
                Files.deleteIfExists(path);
            } catch (IOException ignored) {
                // The original failure remains authoritative.
            }
        }
        backups.forEach((path, content) -> {
            try {
                Files.createDirectories(path.getParent());
                Files.write(path, content);
            } catch (IOException ignored) {
                // The original failure remains authoritative.
            }
        });
    }

    private void safeDelete(Path target) {
        if (target == null || !Files.exists(target, LinkOption.NOFOLLOW_LINKS)) return;
        Path normalized = target.toAbsolutePath().normalize();
        if (!normalized.startsWith(root) || normalized.equals(root)) throw new SecurityException("GIT_WORKSPACE_UNSAFE_DELETE");
        try {
            Files.walkFileTree(normalized, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attributes) throws IOException {
                    Files.deleteIfExists(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(Path directory, IOException error) throws IOException {
                    if (error != null) throw error;
                    Files.deleteIfExists(directory);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException error) {
            throw new IllegalStateException("GIT_WORKSPACE_DELETE_FAILED", error);
        }
    }

    private static Collection<Ref> callLsRemote(
            LsRemoteCommand command,
            String username,
            Optional<EphemeralCredential> credential
    ) throws Exception {
        if (credential.isEmpty()) return command.call();
        return credential.get().use(value -> {
            try {
                return command
                        .setCredentialsProvider(new UsernamePasswordCredentialsProvider(username, value))
                        .call();
            } catch (Exception error) {
                throw new GitTransportFailure(error);
            }
        });
    }

    private static void callFetch(
            FetchCommand command,
            String username,
            Optional<EphemeralCredential> credential
    ) throws Exception {
        if (credential.isEmpty()) {
            command.call();
            return;
        }
        credential.get().use(value -> {
            try {
                command
                        .setCredentialsProvider(new UsernamePasswordCredentialsProvider(username, value))
                        .call();
                return null;
            } catch (Exception error) {
                throw new GitTransportFailure(error);
            }
        });
    }

    private static Iterable<org.eclipse.jgit.transport.PushResult> callPush(
            org.eclipse.jgit.api.PushCommand command,
            String username,
            Optional<EphemeralCredential> credential
    ) throws Exception {
        if (credential.isEmpty()) return command.call();
        return credential.get().use(value -> {
            try {
                return command
                        .setCredentialsProvider(new UsernamePasswordCredentialsProvider(username, value))
                        .call();
            } catch (Exception error) {
                throw new GitTransportFailure(error);
            }
        });
    }

    private static final class GitTransportFailure extends RuntimeException {
        private GitTransportFailure(Exception cause) { super(cause); }
    }
    private record RemoteRef(String commit, String fetchRef) {}
    private record RawFile(String path, long bytes, String sha256) {}
    private record Scan(List<RawFile> files, boolean submodules, boolean lfsPointers, boolean codeOwners) {}
    private record Manifest(
            String workspaceId,
            String organizationId,
            String actorId,
            Provider provider,
            String providerInstanceId,
            String nativeRepositoryId,
            String cloneUrl,
            String requestedRef,
            String resolvedRef,
            String sourceCommit,
            String branch,
            Instant createdAt
    ) {}
}
