package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.persistence.JdbcObjectStorageStore;
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

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class ExecutionJobControllerAuthorizationTest {
    private static final String TENANT = "tenant-jobs";
    private static final String ACTOR = "actor-jobs";

    private final ExecutionJobPort jobs = mock(ExecutionJobPort.class);
    private final JdbcObjectStorageStore artifacts = mock(JdbcObjectStorageStore.class);
    private final ExecutionJobController controller = new ExecutionJobController(
            jobs,
            artifacts,
            new ObjectMapper().findAndRegisterModules(),
            "", "", "", "", "");

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void viewerCannotReadAJobOrItsArtifactMetadata() {
        authenticate(List.of("VIEWER"), List.of());
        when(jobs.find(TENANT, "job-1")).thenReturn(Optional.of(job()));

        assertThrows(AccessDeniedException.class, () -> controller.find("job-1"));

        verify(artifacts, never()).artifactsFor(anyString(), anyString());
    }

    @Test
    void businessLineExecutorCanReadTheJobAndItsArtifacts() {
        authenticate(List.of("DEVELOPER"), List.of());
        when(jobs.find(TENANT, "job-1")).thenReturn(Optional.of(job()));
        when(artifacts.artifactsFor(TENANT, "job-1")).thenReturn(List.of());

        assertEquals(200, controller.find("job-1").getStatusCode().value());

        verify(artifacts).artifactsFor(TENANT, "job-1");
    }

    @Test
    void businessLineExecutorCannotEnumerateEveryBusinessLine() {
        authenticate(List.of("DEVELOPER"), List.of());

        assertThrows(AccessDeniedException.class, () -> controller.list(null, 50, 0));

        verify(jobs, never()).list(TENANT, null, 50, 0);
    }

    @Test
    void adminReaderCanEnumerateEveryBusinessLine() {
        authenticatePlatformAdministrator();
        when(jobs.list(TENANT, null, 50, 0)).thenReturn(List.of());

        assertEquals(List.of(), controller.list(null, 50, 0));

        verify(jobs).list(TENANT, null, 50, 0);
    }

    @Test
    void filteredListRequiresTheSelectedBusinessLinePermission() {
        authenticate(List.of("VIEWER"), List.of());
        assertThrows(
                AccessDeniedException.class,
                () -> controller.list("GENERATION", 25, 0));
        verify(jobs, never()).list(TENANT, ExecutionJobPort.BusinessLine.GENERATION, 25, 0);

        authenticate(List.of("DEVELOPER"), List.of());
        when(jobs.list(TENANT, ExecutionJobPort.BusinessLine.GENERATION, 25, 0))
                .thenReturn(List.of());
        assertEquals(List.of(), controller.list("GENERATION", 25, 0));
        verify(jobs).list(TENANT, ExecutionJobPort.BusinessLine.GENERATION, 25, 0);
    }

    @Test
    void tenantListRejectsUnboundedOffsetsBeforeQueryingTheStore() {
        authenticatePlatformAdministrator();

        var negative = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> controller.list(null, 50, -1));
        assertEquals("ELMOS_EXECUTION_OFFSET_INVALID", negative.code());

        var excessive = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> controller.list(null, 50, 10_001));
        assertEquals("ELMOS_EXECUTION_OFFSET_INVALID", excessive.code());

        verify(jobs, never()).list(TENANT, null, 50, -1);
        verify(jobs, never()).list(TENANT, null, 50, 10_001);
        verifyNoInteractions(jobs);
    }

    @Test
    void tenantListAcceptsTheMaximumBoundedOffset() {
        authenticatePlatformAdministrator();
        when(jobs.list(TENANT, null, 50, 10_000)).thenReturn(List.of());

        assertEquals(List.of(), controller.list(null, 50, 10_000));

        verify(jobs).list(TENANT, null, 50, 10_000);
    }

    @Test
    void tenantListRejectsInvalidLimitsBeforeQueryingTheStore() {
        authenticatePlatformAdministrator();

        var zero = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> controller.list(null, 0, 0));
        assertEquals("ELMOS_EXECUTION_LIMIT_INVALID", zero.code());

        var excessive = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> controller.list(null, 101, 0));
        assertEquals("ELMOS_EXECUTION_LIMIT_INVALID", excessive.code());

        verify(jobs, never()).list(TENANT, null, 0, 0);
        verify(jobs, never()).list(TENANT, null, 101, 0);
        verifyNoInteractions(jobs);
    }

    private static ExecutionJobPort.JobView job() {
        Instant now = Instant.parse("2026-08-09T08:00:00Z");
        return new ExecutionJobPort.JobView(
                "job-1",
                TENANT,
                "job-owner",
                ExecutionJobPort.BusinessLine.GENERATION,
                "project-generation",
                ExecutionJobPort.Status.QUEUED,
                "QUEUED",
                (short) 0,
                ExecutionJobPort.ResultStatus.NOT_RUN,
                null,
                (short) 0,
                (short) 1,
                now,
                null,
                null,
                false,
                1);
    }

    private static void authenticate(List<String> roles, List<String> permissions) {
        authenticate(roles, permissions, false);
    }

    private static void authenticatePlatformAdministrator() {
        authenticate(List.of("VIEWER"), List.of("admin:read"), true);
    }

    private static void authenticate(
            List<String> roles,
            List<String> permissions,
            boolean platformAdministrator
    ) {
        Instant now = Instant.now();
        var tokenBuilder = Jwt.withTokenValue("verified-job-authorization-token")
                .header("alg", "RS256")
                .subject(ACTOR)
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300))
                .claim("organization_id", TENANT)
                .claim("roles", roles)
                .claim("permissions", permissions);
        if (platformAdministrator) {
            tokenBuilder
                    .claim("email", ControlPlanePrincipal.PLATFORM_ADMINISTRATOR_EMAIL)
                    .claim("email_verified", true);
        }
        Jwt token = tokenBuilder.build();
        SecurityContextHolder.getContext().setAuthentication(
                new JwtAuthenticationToken(
                        token,
                        List.of(new SimpleGrantedAuthority("ROLE_TEST"))));
    }
}
