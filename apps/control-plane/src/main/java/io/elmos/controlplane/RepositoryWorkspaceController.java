package io.elmos.controlplane;

import io.elmos.integrations.GitRepositoryWorkspaceService;
import io.elmos.integrations.GitRepositoryWorkspaceService.ChangeRequest;
import io.elmos.integrations.GitRepositoryWorkspaceService.FileChange;
import io.elmos.persistence.JdbcUserActivityStore;
import io.elmos.persistence.JdbcUserActivityStore.ActivityEvent;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.function.Supplier;

@RestController
@RequestMapping("/api/v1/repository-workspaces")
@ConditionalOnProperty(name = "elmos.repository-workspace.enabled", havingValue = "true")
public final class RepositoryWorkspaceController {
    record CreateBody(
            GitRepositoryWorkspaceService.Provider provider,
            String providerInstanceId,
            String nativeRepositoryId,
            String cloneUrl,
            String requestedRef,
            String credentialRef
    ) {}

    record ChangeBody(
            String baseCommit,
            String intent,
            boolean codeOwnerApproval,
            List<String> approvedPaths,
            List<FileChange> changes
    ) {}

    record DeleteResult(String workspaceId, String status, boolean externalOperationExecuted) {}
    record CommitBody(
            String expectedHeadCommit,
            String message,
            boolean codeOwnerApproval,
            List<String> approvedPaths
    ) {}
    record PushBody(String expectedCommit, String credentialRef) {}
    record PullRequestBody(
            String expectedCommit,
            String baseBranch,
            String title,
            String body,
            String idempotencyKey,
            String credentialRef
    ) {}
    record MaterializeBody(String expectedHeadCommit) {}
    record ErrorResponse(String errorCode, String message, boolean retryable) {}

    private final GitRepositoryWorkspaceService workspaces;
    private final RepositoryWorkspaceCredentialStore credentials;
    private final JdbcUserActivityStore activity;
    private final Clock clock;
    private final String apiKey;
    private final Path materializedRoot;

    public RepositoryWorkspaceController(
            GitRepositoryWorkspaceService workspaces,
            RepositoryWorkspaceCredentialStore credentials,
            JdbcUserActivityStore activity,
            Clock clock,
            @Value("${elmos.repository-workspace.api-key:}") String apiKey,
            @Value("${elmos.snapshot.materialized-root:}") String materializedRoot
    ) {
        this.workspaces = Objects.requireNonNull(workspaces, "workspaces");
        this.credentials = Objects.requireNonNull(credentials, "credentials");
        this.activity = Objects.requireNonNull(activity, "activity");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.apiKey = apiKey == null ? "" : apiKey.trim();
        this.materializedRoot = materializedRoot == null || materializedRoot.isBlank()
                ? null : Path.of(materializedRoot).toAbsolutePath().normalize();
    }

    @GetMapping("/capabilities")
    GitRepositoryWorkspaceService.Capability capabilities(
            @RequestHeader("X-ELMOS-Repository-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId
    ) {
        authorize(presentedKey, organizationId, actorId, "repository:read");
        return audited(organizationId, actorId, requestId, "REPOSITORY_CAPABILITIES", "capability",
                workspaces::capability);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    GitRepositoryWorkspaceService.Workspace create(
            @RequestHeader("X-ELMOS-Repository-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @RequestBody CreateBody body
    ) {
        authorize(presentedKey, organizationId, actorId, "repository:write");
        Objects.requireNonNull(body, "body");
        return audited(organizationId, actorId, requestId, "REPOSITORY_WORKSPACE_CREATE",
                body.provider() == null ? "unknown-provider" : body.provider().name(), () -> {
                    try (RepositoryWorkspaceCredentialStore.Lease lease =
                                 credentials.lease(body.credentialRef())) {
                        return workspaces.create(
                                new GitRepositoryWorkspaceService.CreateRequest(
                                        organizationId,
                                        actorId,
                                        body.provider(),
                                        body.providerInstanceId(),
                                        body.nativeRepositoryId(),
                                        body.cloneUrl(),
                                        body.requestedRef()
                                ),
                                lease.username(),
                                lease.credential()
                        );
                    }
                });
    }

    @GetMapping("/{workspaceId}")
    GitRepositoryWorkspaceService.Workspace inspect(
            @RequestHeader("X-ELMOS-Repository-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String workspaceId
    ) {
        authorize(presentedKey, organizationId, actorId, "repository:read");
        return audited(organizationId, actorId, requestId, "REPOSITORY_WORKSPACE_INSPECT",
                safeTarget(workspaceId), () -> {
                    return workspaces.inspect(organizationId, actorId, workspaceId);
                });
    }

    @GetMapping("/{workspaceId}/files")
    GitRepositoryWorkspaceService.FileContent read(
            @RequestHeader("X-ELMOS-Repository-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String workspaceId,
            @RequestParam("path") String path
    ) {
        authorize(presentedKey, organizationId, actorId, "repository:read");
        return audited(organizationId, actorId, requestId, "REPOSITORY_FILE_READ",
                safeTarget(workspaceId), () -> {
                    return workspaces.readFile(organizationId, actorId, workspaceId, path);
                });
    }

    @PostMapping("/{workspaceId}/changes")
    GitRepositoryWorkspaceService.ChangeResult apply(
            @RequestHeader("X-ELMOS-Repository-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String workspaceId,
            @RequestBody ChangeBody body
    ) {
        authorize(presentedKey, organizationId, actorId, "repository:write");
        Objects.requireNonNull(body, "body");
        return audited(organizationId, actorId, requestId, "REPOSITORY_LOCAL_CHANGE",
                safeTarget(workspaceId), () -> workspaces.apply(
                        workspaceId,
                        new ChangeRequest(
                                organizationId,
                                actorId,
                                body.baseCommit(),
                                body.intent(),
                                body.codeOwnerApproval(),
                                body.approvedPaths(),
                                body.changes()
                        )
                ));
    }

    @DeleteMapping("/{workspaceId}")
    DeleteResult delete(
            @RequestHeader("X-ELMOS-Repository-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String workspaceId
    ) {
        authorize(presentedKey, organizationId, actorId, "repository:write");
        return audited(organizationId, actorId, requestId, "REPOSITORY_WORKSPACE_DELETE",
                safeTarget(workspaceId), () -> {
                    workspaces.delete(organizationId, actorId, workspaceId);
                    return new DeleteResult(workspaceId, "DELETED", false);
                });
    }

    @PostMapping("/{workspaceId}/commit")
    GitRepositoryWorkspaceService.CommitResult commit(
            @RequestHeader("X-ELMOS-Repository-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String workspaceId,
            @RequestBody CommitBody body
    ) {
        authorize(presentedKey, organizationId, actorId, "repository:commit");
        return audited(organizationId, actorId, requestId, "REPOSITORY_COMMIT",
                safeTarget(workspaceId), () -> workspaces.commit(
                        workspaceId,
                        new GitRepositoryWorkspaceService.CommitRequest(
                                organizationId, actorId, body.expectedHeadCommit(),
                                body.message(), body.codeOwnerApproval(),
                                body.approvedPaths())));
    }

    @PostMapping("/{workspaceId}/push")
    GitRepositoryWorkspaceService.PushResult push(
            @RequestHeader("X-ELMOS-Repository-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String workspaceId,
            @RequestBody PushBody body
    ) {
        authorize(presentedKey, organizationId, actorId, "repository:push");
        return auditedExternal(organizationId, actorId, requestId, "REPOSITORY_PUSH",
                safeTarget(workspaceId), () -> {
                    try (RepositoryWorkspaceCredentialStore.Lease lease =
                                 credentials.lease(body.credentialRef())) {
                        return workspaces.push(
                                workspaceId,
                                new GitRepositoryWorkspaceService.PushRequest(
                                        organizationId, actorId, body.expectedCommit()),
                                lease.username(), lease.credential());
                    }
                });
    }

    @PostMapping("/{workspaceId}/pull-request")
    GitRepositoryWorkspaceService.PullRequestResult pullRequest(
            @RequestHeader("X-ELMOS-Repository-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String workspaceId,
            @RequestBody PullRequestBody body
    ) {
        authorize(presentedKey, organizationId, actorId, "repository:pr");
        return auditedExternal(organizationId, actorId, requestId, "REPOSITORY_PULL_REQUEST",
                safeTarget(workspaceId), () -> {
                    try (RepositoryWorkspaceCredentialStore.Lease lease =
                                 credentials.lease(body.credentialRef())) {
                        return workspaces.createPullRequest(
                                workspaceId,
                                new GitRepositoryWorkspaceService.PullRequestRequest(
                                        organizationId, actorId, body.expectedCommit(),
                                        body.baseBranch(), body.title(), body.body(),
                                        body.idempotencyKey()),
                                lease.username(), lease.credential());
                    }
                });
    }

    @PostMapping("/{workspaceId}/materializations/spring")
    GitRepositoryWorkspaceService.WorkspaceMaterialization materializeForSpring(
            @RequestHeader("X-ELMOS-Repository-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String workspaceId,
            @RequestBody MaterializeBody body
    ) {
        authorize(presentedKey, organizationId, actorId, "repository:read");
        if (materializedRoot == null) throw new WorkspaceUnavailableException();
        return audited(organizationId, actorId, requestId, "REPOSITORY_SPRING_MATERIALIZE",
                safeTarget(workspaceId), () -> workspaces.materialize(
                        organizationId, actorId, workspaceId,
                        body.expectedHeadCommit(), materializedRoot));
    }

    private <T> T audited(
            String organizationId,
            String actorId,
            String requestId,
            String action,
            String target,
            Supplier<T> operation
    ) {
        return audited(organizationId, actorId, requestId, action, target, false, operation);
    }

    private <T> T auditedExternal(
            String organizationId,
            String actorId,
            String requestId,
            String action,
            String target,
            Supplier<T> operation
    ) {
        return audited(organizationId, actorId, requestId, action, target, true, operation);
    }

    private <T> T audited(
            String organizationId,
            String actorId,
            String requestId,
            String action,
            String target,
            boolean externalSideEffect,
            Supplier<T> operation
    ) {
        String correlation = safeCorrelation(requestId);
        append(organizationId, actorId, correlation, action + "_ATTEMPT", target,
                "SUCCESS", null, false);
        try {
            T result = operation.get();
            appendBestEffort(organizationId, actorId, correlation, action, target,
                    "SUCCESS", null, externalSideEffect);
            return result;
        } catch (RuntimeException error) {
            appendBestEffort(organizationId, actorId, correlation, action, target,
                    "FAILURE", errorCode(error), false);
            throw error;
        }
    }

    private void append(
            String organizationId,
            String actorId,
            String requestId,
            String action,
            String target,
            String result,
            String errorCode,
            boolean externalSideEffect
    ) {
        activity.append(organizationId, actorId, requestId, List.of(new ActivityEvent(
                UUID.randomUUID().toString(),
                requestId,
                "USER_ACTION",
                action,
                "REPOSITORY_WORKSPACE",
                "/repositories",
                target,
                clock.instant(),
                null,
                result,
                errorCode,
                null,
                null,
                Map.of("externalSideEffect", String.valueOf(externalSideEffect))
        )));
    }

    private void appendBestEffort(
            String organizationId,
            String actorId,
            String requestId,
            String action,
            String target,
            String result,
            String errorCode,
            boolean externalSideEffect
    ) {
        try {
            append(organizationId, actorId, requestId, action, target, result,
                    errorCode, externalSideEffect);
        } catch (RuntimeException ignored) {
            // The durable attempt event remains the minimum audit record. Do not
            // repeat a completed filesystem mutation because completion logging failed.
        }
    }

    private void authorize(
            String presentedKey,
            String organizationId,
            String actorId,
            String permission
    ) {
        var principal = ControlPlanePrincipal.current();
        if (principal.isPresent()) {
            try {
                principal.get().require(organizationId, actorId, permission);
                return;
            } catch (RuntimeException error) {
                throw new SecurityException("OIDC repository authorization failed", error);
            }
        }
        if (apiKey.length() < 24) throw new WorkspaceUnavailableException();
        byte[] expected = apiKey.getBytes(StandardCharsets.UTF_8);
        byte[] presented = (presentedKey == null ? "" : presentedKey).getBytes(StandardCharsets.UTF_8);
        if (expected.length != presented.length || !MessageDigest.isEqual(expected, presented)) {
            throw new SecurityException("GIT_WORKSPACE_AUTHORIZATION_FAILED");
        }
    }

    private static String safeCorrelation(String value) {
        if (value != null && value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) return value;
        return UUID.randomUUID().toString();
    }

    private static String safeTarget(String workspaceId) {
        try {
            return UUID.fromString(workspaceId).toString();
        } catch (RuntimeException error) {
            return "invalid-workspace";
        }
    }

    private static String errorCode(RuntimeException error) {
        return error instanceof SecurityException
                ? "REPOSITORY_POLICY_REJECTED"
                : error instanceof IllegalArgumentException
                ? "REPOSITORY_REQUEST_INVALID"
                : "REPOSITORY_OPERATION_UNAVAILABLE";
    }

    @ExceptionHandler(SecurityException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    ErrorResponse forbidden() {
        return new ErrorResponse(
                "REPOSITORY_WORKSPACE_FORBIDDEN",
                "The repository operation was rejected by policy.",
                false);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    ErrorResponse invalid() {
        return new ErrorResponse(
                "REPOSITORY_WORKSPACE_REQUEST_INVALID",
                "The repository operation did not satisfy the workspace contract.",
                false);
    }

    @ExceptionHandler(WorkspaceUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    ErrorResponse notConfigured() {
        return new ErrorResponse(
                "REPOSITORY_WORKSPACE_NOT_CONFIGURED",
                "Repository workspaces are not configured.",
                false);
    }

    @ExceptionHandler(IllegalStateException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    ErrorResponse unavailable() {
        return new ErrorResponse(
                "REPOSITORY_WORKSPACE_UNAVAILABLE",
                "The repository operation is temporarily unavailable.",
                true);
    }

    private static final class WorkspaceUnavailableException extends RuntimeException {}
}
