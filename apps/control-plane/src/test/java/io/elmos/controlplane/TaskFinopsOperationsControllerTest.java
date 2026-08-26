package io.elmos.controlplane;

import io.elmos.workflow.TaskFinopsAnalytics;
import io.elmos.workflow.TaskFinopsAnalyticsService;
import io.elmos.workflow.TaskFinopsFeatureRollout;
import io.elmos.workflow.TaskFinopsOperationsPort;
import io.elmos.workflow.TaskFinopsPolicy;
import io.elmos.workflow.TaskFinopsPort;
import io.elmos.workflow.TenantLifecyclePolicy;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class TaskFinopsOperationsControllerTest {
    private static final String DIGEST = "a".repeat(64);
    private static final Instant NOW = Instant.parse("2026-08-26T08:00:00Z");
    private final TaskFinopsOperationsPort operations = mock(TaskFinopsOperationsPort.class);

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void rolloutScopeComesOnlyFromAuthenticatedPrincipal() {
        authenticate("TENANT_ADMIN");
        ControlPlanePrincipal expected = ControlPlanePrincipal.current().orElseThrow();
        when(operations.setFeatureRollout(any())).thenReturn(3L);

        var response = controller().rollout(
                "development", "authenticated_account_binding", "rollout-key-1",
                new TaskFinopsOperationsController.RolloutRequest("canary", 10, 2));

        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        var captured = ArgumentCaptor.forClass(
                TaskFinopsOperationsPort.FeatureRolloutCommand.class);
        verify(operations).setFeatureRollout(captured.capture());
        assertEquals(expected.organizationId(), captured.getValue().context().organizationId());
        assertEquals(expected.accountId(), captured.getValue().context().accountId());
        assertEquals(expected.actorId(), captured.getValue().context().actorId());
        assertEquals(TaskFinopsFeatureRollout.Stage.CANARY, captured.getValue().stage());
        assertEquals(10, captured.getValue().exposurePercent());
        assertEquals(64, captured.getValue().requestDigest().length());
    }

    @Test
    void lifecycleRequestReturnsDurableFailClosedState() {
        authenticate("TENANT_ADMIN");
        Instant cutoff = NOW.minusSeconds(86_400);
        when(operations.requestLifecycle(any())).thenReturn("lifecycle-1");
        when(operations.lifecycleStatus(any(), any())).thenAnswer(invocation -> {
            var context = invocation.getArgument(0,
                    io.elmos.workflow.TaskFinopsPort.AuthenticatedContext.class);
            return Optional.of(new TaskFinopsOperationsPort.LifecycleStatus(
                    "lifecycle-1", context.organizationId(), context.accountId(),
                    TenantLifecyclePolicy.Operation.DELETE,
                    TenantLifecyclePolicy.ExportFormat.JSON,
                    "BLOCKED", cutoff, null, null, 0, 0,
                    TenantLifecyclePolicy.ProviderResult.NOT_RUN,
                    "ELMOS_MTF_LEGAL_HOLD_ACTIVE", 1, NOW, null));
        });

        var response = controller().requestLifecycle(
                "delete", "lifecycle-idem-1",
                new TaskFinopsOperationsController.LifecycleRequest(
                        "lifecycle-1", "json", cutoff));

        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        assertTrue(response.getBody() instanceof TaskFinopsOperationsPort.LifecycleStatus);
    }

    @Test
    void viewerCannotRequestTenantDeletion() {
        authenticate("VIEWER");
        assertThrows(AccessDeniedException.class, () -> controller().requestLifecycle(
                "delete", "lifecycle-idem-1",
                new TaskFinopsOperationsController.LifecycleRequest(
                        "lifecycle-1", "json", NOW.minusSeconds(60))));
    }

    @Test
    void malformedCanaryExposureFailsBeforeMutation() {
        authenticate("TENANT_ADMIN");
        assertThrows(IllegalArgumentException.class, () -> controller().rollout(
                "development", "authenticated_account_binding", "rollout-key-1",
                new TaskFinopsOperationsController.RolloutRequest("canary", 100, 2)));
    }

    @Test
    void csvAnalyticsExportReturnsRawBodyAndExactMetadata() {
        authenticate("VIEWER");
        ControlPlanePrincipal principal = ControlPlanePrincipal.current().orElseThrow();
        Instant bucketStart = NOW.minusSeconds(3_600);
        var bucket = new TaskFinopsAnalytics.AggregateBucket(
                principal.organizationId(), principal.accountId(), "=SUM(A1:A2)", 1,
                TaskFinopsPolicy.WorkloadClass.GENERATION,
                TaskFinopsAnalytics.Grain.HOUR, bucketStart, NOW, "CNY",
                TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                new BigDecimal("1.000000"), new BigDecimal("3.000000"),
                new BigDecimal("2.000000"), 1,
                TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                TaskFinopsPort.ReconciliationStatus.RECONCILED);
        when(operations.currentProjection(any(), any(), any(), any(), anyInt()))
                .thenReturn(Optional.of(new TaskFinopsOperationsPort.ProjectionSnapshot(
                        "rebuild-a", 2, NOW,
                        TaskFinopsAnalytics.InputContinuity.COMPLETE,
                        TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN,
                        TaskFinopsAnalytics.ProviderOutcome.UNKNOWN,
                        TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED,
                        DIGEST, DIGEST, List.of(bucket))));

        var response = controller().exportAnalytics(
                "hour", "csv", bucketStart, NOW, 50);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(MediaType.parseMediaType("text/csv;charset=UTF-8"),
                response.getHeaders().getContentType());
        assertTrue(response.getBody().startsWith("schema_version,organization_id,"));
        assertTrue(response.getBody().contains("\"'=SUM(A1:A2)\""));
        assertEquals("1", response.getHeaders().getFirst("X-ELMOS-Row-Count"));
        assertEquals(sha256(response.getBody()),
                response.getHeaders().getFirst("X-ELMOS-Content-SHA256"));
        assertEquals("NOT_RUN",
                response.getHeaders().getFirst("X-ELMOS-External-Evidence"));
        assertEquals("UNKNOWN",
                response.getHeaders().getFirst("X-ELMOS-Provider-Outcome"));
        assertEquals("NOT_CERTIFIED",
                response.getHeaders().getFirst("X-ELMOS-Production-Certification"));
    }

    @Test
    void analyticsExceptionsMapToStableClientErrors() {
        var conflict = controller().analyticsError(new TaskFinopsAnalytics.AnalyticsException(
                "ELMOS_MTF_ANALYTICS_SEQUENCE_GAP"));

        assertTrue(conflict.getStatusCode().is4xxClientError());
        assertEquals(HttpStatus.CONFLICT, conflict.getStatusCode());
        assertTrue(conflict.getBody() instanceof Map<?, ?>);
        assertEquals("ELMOS_MTF_ANALYTICS_SEQUENCE_GAP",
                ((Map<?, ?>) conflict.getBody()).get("code"));

        var badRequest = controller().analyticsError(new TaskFinopsAnalytics.AnalyticsException(
                "ELMOS_MTF_ANALYTICS_SCOPE_MISMATCH"));
        assertTrue(badRequest.getStatusCode().is4xxClientError());
        assertEquals(HttpStatus.BAD_REQUEST, badRequest.getStatusCode());
        assertEquals("ELMOS_MTF_ANALYTICS_SCOPE_MISMATCH",
                ((Map<?, ?>) badRequest.getBody()).get("code"));
    }

    private TaskFinopsOperationsController controller() {
        return new TaskFinopsOperationsController(
                operations, new TaskFinopsAnalyticsService(operations),
                Clock.fixed(NOW, ZoneOffset.UTC));
    }

    private static void authenticate(String role) {
        Jwt token = Jwt.withTokenValue("verified-test-token")
                .header("alg", "RS256")
                .issuer("https://issuer.example.test")
                .subject("actor-finops-operations")
                .issuedAt(NOW.minusSeconds(30))
                .expiresAt(NOW.plusSeconds(300))
                .claim("organization_id", "tenant-finops-operations")
                .claim("roles", List.of(role))
                .build();
        SecurityContextHolder.getContext().setAuthentication(
                new JwtAuthenticationToken(token,
                        List.of(new SimpleGrantedAuthority("ROLE_TEST"))));
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new AssertionError("SHA-256 unavailable", exception);
        }
    }
}
