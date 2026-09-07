package io.elmos.controlplane;

import io.elmos.cas.ActionCache;
import io.elmos.cas.ActionKey;
import io.elmos.cas.ActionKeyBuilder;
import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasDigest;
import io.elmos.workflow.ExecutionJobPort;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class ActionCacheExecutionControllerTest {

    private final ActionCacheExecutionJobDispatcher dispatcher =
            mock(ActionCacheExecutionJobDispatcher.class);

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void bindsCanonicalActionKeyToAuthenticatedTenantAndDispatches() {
        authenticate("tenant-a", "actor-a", List.of("DEVELOPER"));
        CasDigest requestDigest = CasDigest.ofUtf8("request");
        when(dispatcher.dispatch(any())).thenReturn(new ActionCacheExecutionJobDispatcher.Outcome(
                ActionCacheExecutionJobDispatcher.OutcomeKind.DURABLE_JOB_ACCEPTED,
                "DURABLE_JOB_ENQUEUED", Optional.empty(), Optional.of("job-1"),
                Optional.of(requestDigest), Optional.of(ActionCache.CacheOutcome.MISS), false));
        ActionCacheExecutionController controller =
                new ActionCacheExecutionController(dispatcher, "eu-west", "INTERNAL");

        var response = controller.dispatch(new ActionCacheExecutionController.DispatchRequest(
                keyRequest(key()), "GENERATION", "compile", "idem-1",
                Map.of("sourceRef", "cas:sha256:" + "b".repeat(64) + "/6"),
                (short) 100, 3600, (short) 1, false, "CACHE_OR_ENQUEUE", null));

        assertEquals(202, response.getStatusCode().value());
        Map<?, ?> body = (Map<?, ?>) response.getBody();
        assertEquals("DURABLE_JOB_ACCEPTED", body.get("status"));
        assertEquals("job-1", body.get("jobId"));
        assertEquals(requestDigest.compact(), body.get("requestDigest"));
        var captured = org.mockito.ArgumentCaptor.forClass(
                ActionCacheExecutionJobDispatcher.Request.class);
        verify(dispatcher).dispatch(captured.capture());
        assertEquals("tenant-a", captured.getValue().key().tenantId());
        assertEquals("actor-a", captured.getValue().dispatch().actorId());
        assertEquals("generation:multi", captured.getValue().dispatch().requiredCapability());
        assertEquals("eu-west", captured.getValue().reader().dataResidency());
        assertEquals(CasAccessPolicy.SecurityTier.INTERNAL,
                captured.getValue().reader().clearance());
    }

    @Test
    void rejectsActionKeyForAnotherTenantBeforeCallingDispatcher() {
        authenticate("tenant-a", "actor-a", List.of("DEVELOPER"));
        ActionCacheExecutionController controller =
                new ActionCacheExecutionController(dispatcher, "eu-west", "INTERNAL");

        assertThrows(AccessDeniedException.class, () -> controller.dispatch(
                new ActionCacheExecutionController.DispatchRequest(
                        keyRequest(key("tenant-b")), "GENERATION", "compile", "idem-1",
                        Map.of(), (short) 100, 3600, (short) 1, false,
                        "CACHE_OR_ENQUEUE", null)));
        verifyNoInteractions(dispatcher);
    }

    @Test
    void refusesToExecuteWhenDeploymentResidencyIsMissing() {
        authenticate("tenant-a", "actor-a", List.of("DEVELOPER"));
        ActionCacheExecutionController controller =
                new ActionCacheExecutionController(dispatcher, "", "INTERNAL");

        var response = controller.dispatch(new ActionCacheExecutionController.DispatchRequest(
                keyRequest(key()), "GENERATION", "compile", "idem-1", Map.of(),
                (short) 100, 3600, (short) 1, false, "CACHE_OR_ENQUEUE", null));

        assertEquals(503, response.getStatusCode().value());
        assertEquals("ELMOS_ACTION_CACHE_DATA_RESIDENCY_NOT_CONFIGURED",
                ((Map<?, ?>) response.getBody()).get("code"));
        verifyNoInteractions(dispatcher);
    }

    @Test
    void refusesAnActionKeyOutsideDeploymentResidency() {
        authenticate("tenant-a", "actor-a", List.of("DEVELOPER"));
        ActionCacheExecutionController controller =
                new ActionCacheExecutionController(dispatcher, "us-east", "INTERNAL");

        var error = assertThrows(ExecutionJobPort.ExecutionStateException.class,
                () -> controller.dispatch(new ActionCacheExecutionController.DispatchRequest(
                        keyRequest(key()), "GENERATION", "compile", "idem-1", Map.of(),
                        (short) 100, 3600, (short) 1, false, "CACHE_OR_ENQUEUE", null)));
        assertEquals("ELMOS_ACTION_CACHE_DATA_RESIDENCY_MISMATCH", error.code());
        verifyNoInteractions(dispatcher);
    }

    @Test
    void invalidCompactDigestIsRejectedWithoutDispatch() {
        authenticate("tenant-a", "actor-a", List.of("DEVELOPER"));
        ActionCacheExecutionController controller =
                new ActionCacheExecutionController(dispatcher, "eu-west", "INTERNAL");

        var error = assertThrows(ExecutionJobPort.ExecutionStateException.class,
                () -> controller.dispatch(new ActionCacheExecutionController.DispatchRequest(
                        new ActionCacheExecutionController.ActionKeyRequest(
                                "sha256:not-a-digest/1", "tenant-a", key().components()),
                        "GENERATION", "compile", "idem-1", Map.of(),
                        (short) 100, 3600, (short) 1, false, "CACHE_OR_ENQUEUE", null)));
        assertEquals("ELMOS_ACTION_CACHE_ACTION_KEY_INVALID", error.code());
        verifyNoInteractions(dispatcher);
    }

    private static ActionCacheExecutionController.ActionKeyRequest keyRequest(ActionKey key) {
        return new ActionCacheExecutionController.ActionKeyRequest(
                key.digest().compact(), key.tenantId(), key.components());
    }

    private static ActionKey key() {
        return key("tenant-a");
    }

    private static ActionKey key(String tenant) {
        return new ActionKeyBuilder()
                .tenant(tenant, "project-a")
                .sourceTree(CasDigest.ofUtf8("source"))
                .dependencyGraph(CasDigest.ofUtf8("dependencies"))
                .adapter("java", CasDigest.ofUtf8("adapter"))
                .irSchemaVersion("ir-v3")
                .rulePacks(List.of(new ActionKeyBuilder.RulePackRef(
                        "java-rules", CasDigest.ofUtf8("rules"))))
                .toolchainImage("registry.internal/elmos/java21@sha256:" + "a".repeat(64))
                .targetPlatform("linux/arm64")
                .buildOptions(Map.of("profile", "release"))
                .command(List.of("./mvnw", "verify"))
                .workingDirectory("/workspace/source")
                .declaredOutputs(List.of("target"))
                .prompt(Optional.empty())
                .model(Optional.empty())
                .policy(CasDigest.ofUtf8("policy"))
                .permissionScope(Set.of("generation:execute"))
                .sandbox("S2", CasDigest.ofUtf8("sandbox"))
                .dataResidency("eu-west")
                .environmentContract(ActionKeyBuilder.EnvironmentContract.of())
                .environment(Map.of())
                .build();
    }

    private static void authenticate(String tenant, String actor, List<String> roles) {
        Instant now = Instant.now();
        Jwt token = Jwt.withTokenValue("verified-action-cache-token")
                .header("alg", "RS256")
                .subject(actor)
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300))
                .claim("organization_id", tenant)
                .claim("roles", roles)
                .build();
        SecurityContextHolder.getContext().setAuthentication(
                new JwtAuthenticationToken(token,
                        List.of(new SimpleGrantedAuthority("ROLE_TEST"))));
    }
}
