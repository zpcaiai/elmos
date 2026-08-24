package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.persistence.JdbcObjectStorageStore;
import io.elmos.workflow.ExecutionJobPort;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ExecutionJobControllerModernizationProofTest {
    private static final String IMAGE =
            "registry.example.test/elmos/modernization-proof-worker@sha256:" + "a".repeat(64);
    private final ExecutionJobPort jobs = mock(ExecutionJobPort.class);
    private final JdbcObjectStorageStore artifacts = mock(JdbcObjectStorageStore.class);

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void configuredDigestPinnedImageDispatchesTheExactWorkerCapability() {
        authenticateDeveloper();
        when(jobs.enqueue(any())).thenAnswer(invocation ->
                invocation.<ExecutionJobPort.EnqueueCommand>getArgument(0).jobId());
        var controller = controller(IMAGE);

        var response = controller.enqueue(request(), "request-proof-1");

        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        ArgumentCaptor<ExecutionJobPort.EnqueueCommand> command =
                ArgumentCaptor.forClass(ExecutionJobPort.EnqueueCommand.class);
        verify(jobs).enqueue(command.capture());
        assertEquals(ExecutionJobPort.BusinessLine.MODERNIZATION_PROOF,
                command.getValue().businessLine());
        assertEquals("batch105-108-proof-loop", command.getValue().jobKind());
        assertEquals("modernization:proof-loop", command.getValue().requiredCapability());
        assertEquals(IMAGE, command.getValue().runnerImage());
        assertEquals("tenant-proof", command.getValue().organizationId());
        assertEquals(
                ControlPlanePrincipal.stableAccountId(
                        "https://identity.example.test", "actor-proof"),
                command.getValue().accountId());
        assertEquals("actor-proof", command.getValue().actorId());
        assertEquals("request-proof-1", command.getValue().requestId());
        assertEquals("VALIDATION", command.getValue().workloadClass());
        assertEquals(2, command.getValue().resourceUnits());
        assertFalse(command.getValue().requestPayload().containsKey("productionApproved"));
        assertFalse(command.getValue().requestPayload().containsKey("certified"));
    }

    @Test
    void absentImageConfigurationFailsBeforeQueueMutation() {
        authenticateDeveloper();
        var response = controller("").enqueue(request(), "request-proof-2");

        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, response.getStatusCode());
        assertTrue(String.valueOf(response.getBody()).contains("ELMOS_RUNNER_IMAGE_NOT_CONFIGURED"));
        verify(jobs, never()).enqueue(any());
    }

    @Test
    void mutableImageTagFailsBeforeQueueMutation() {
        authenticateDeveloper();
        var response = controller(
                "registry.example.test/elmos/modernization-proof-worker:latest")
                .enqueue(request(), "request-proof-3");

        assertEquals(HttpStatus.SERVICE_UNAVAILABLE, response.getStatusCode());
        verify(jobs, never()).enqueue(any());
    }

    @Test
    void readsAndCancelPassCanonicalAccountAndActorContext() {
        authenticateDeveloper();
        String accountId = ControlPlanePrincipal.stableAccountId(
                "https://identity.example.test", "actor-proof");
        var job = new ExecutionJobPort.JobView(
                "job-proof-1",
                "tenant-proof",
                accountId,
                "actor-proof",
                ExecutionJobPort.BusinessLine.MODERNIZATION_PROOF,
                "batch105-108-proof-loop",
                ExecutionJobPort.Status.RUNNING,
                "ADMITTED",
                null,
                "verifying",
                (short) 50,
                ExecutionJobPort.ResultStatus.NOT_RUN,
                null,
                (short) 1,
                (short) 1,
                Instant.parse("2026-08-24T00:00:00Z"),
                Instant.parse("2026-08-24T00:01:00Z"),
                null,
                false,
                2L);
        when(jobs.find(
                any(ExecutionJobPort.AuthenticatedContext.class),
                eq(job.jobId())))
                .thenReturn(Optional.of(job));
        when(jobs.list(
                any(ExecutionJobPort.AuthenticatedContext.class),
                eq(ExecutionJobPort.BusinessLine.MODERNIZATION_PROOF),
                eq(20),
                eq(0)))
                .thenReturn(List.of(job));
        when(jobs.requestCancel(
                any(ExecutionJobPort.AuthenticatedContext.class),
                eq(job.jobId())))
                .thenReturn(ExecutionJobPort.Status.RUNNING);
        var controller = controller(IMAGE);

        assertEquals(HttpStatus.OK, controller.find(job.jobId()).getStatusCode());
        assertEquals(
                List.of(job),
                controller.list("MODERNIZATION_PROOF", 20, 0));
        assertEquals(HttpStatus.ACCEPTED, controller.cancel(job.jobId()).getStatusCode());

        ArgumentCaptor<ExecutionJobPort.AuthenticatedContext> findContexts =
                ArgumentCaptor.forClass(ExecutionJobPort.AuthenticatedContext.class);
        verify(jobs, times(2)).find(findContexts.capture(), eq(job.jobId()));
        ArgumentCaptor<ExecutionJobPort.AuthenticatedContext> listContext =
                ArgumentCaptor.forClass(ExecutionJobPort.AuthenticatedContext.class);
        verify(jobs).list(
                listContext.capture(),
                eq(ExecutionJobPort.BusinessLine.MODERNIZATION_PROOF),
                eq(20),
                eq(0));
        ArgumentCaptor<ExecutionJobPort.AuthenticatedContext> cancelContext =
                ArgumentCaptor.forClass(ExecutionJobPort.AuthenticatedContext.class);
        verify(jobs).requestCancel(cancelContext.capture(), eq(job.jobId()));

        findContexts.getAllValues().forEach(context ->
                assertCanonicalContext(context, accountId));
        assertCanonicalContext(listContext.getValue(), accountId);
        assertCanonicalContext(cancelContext.getValue(), accountId);
        assertEquals(findContexts.getAllValues().get(1), cancelContext.getValue(),
                "cancel authorization and mutation must use the same bound identity");
    }

    private ExecutionJobController controller(String proofImage) {
        return new ExecutionJobController(
                jobs, artifacts, new ObjectMapper().findAndRegisterModules(),
                "", "", "", "", proofImage);
    }

    private static ExecutionJobController.EnqueueRequest request() {
        return new ExecutionJobController.EnqueueRequest(
                "MODERNIZATION_PROOF", "caller-value-is-ignored", "proof-idempotency-1",
                Map.of(
                        "targetSkillId", "B105-S01",
                        "projectId", "project-proof",
                        "repositoryId", "repository-proof",
                        "policyDigest", "sha256:" + "b".repeat(64),
                        "inputs", Map.of(),
                        "evidence", Map.of()),
                (short) 100, 3600, (short) 1);
    }

    private static void authenticateDeveloper() {
        Instant now = Instant.now();
        Jwt token = Jwt.withTokenValue("verified-test-token")
                .header("alg", "RS256")
                .subject("actor-proof")
                .issuer("https://identity.example.test")
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300))
                .claim("organization_id", "tenant-proof")
                .claim("roles", List.of("DEVELOPER"))
                .build();
        SecurityContextHolder.getContext().setAuthentication(
                new JwtAuthenticationToken(token,
                        List.of(new SimpleGrantedAuthority("ROLE_TEST"))));
    }

    private static void assertCanonicalContext(
            ExecutionJobPort.AuthenticatedContext context,
            String accountId
    ) {
        assertEquals("tenant-proof", context.organizationId());
        assertEquals(accountId, context.accountId());
        assertEquals("actor-proof", context.actorId());
        assertTrue(context.requestId().startsWith("execution-api-"));
    }
}
