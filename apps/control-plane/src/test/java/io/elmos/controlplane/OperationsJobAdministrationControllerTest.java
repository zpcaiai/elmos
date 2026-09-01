package io.elmos.controlplane;

import io.elmos.workflow.ExecutionJobPort;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.stream.IntStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class OperationsJobAdministrationControllerTest {
    private static final String KEY = "operations-jobs-test-key-32-characters";
    private static final String ORGANIZATION = "org-1";
    private static final String ACTOR = "actor-1";
    private static final Instant NOW = Instant.parse("2026-08-09T08:00:00Z");

    private final ExecutionJobPort jobs = mock(ExecutionJobPort.class);
    private final OperationsJobAdministrationController controller =
            new OperationsJobAdministrationController(
                    jobs,
                    new OperationsAuthorization(
                            Clock.fixed(NOW, ZoneOffset.UTC),
                            KEY,
                            NOW.plusSeconds(3600).toString(),
                            ORGANIZATION,
                            ACTOR));

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shortLivedViewerKeyListsAndFiltersRealJobState() {
        when(jobs.list(
                ORGANIZATION,
                ExecutionJobPort.BusinessLine.GENERATION,
                100,
                0)).thenReturn(List.of(
                        job("job-failed", ExecutionJobPort.Status.FAILED, false),
                        job("job-running", ExecutionJobPort.Status.RUNNING, false)));

        OperationsJobAdministrationController.JobListView response = controller.list(
                KEY, ORGANIZATION, ACTOR, "VIEWER", 2, "generation", "running");

        assertEquals(1, response.items().size());
        assertEquals("job-running", response.items().getFirst().jobId());
        assertEquals(ExecutionJobPort.Status.RUNNING, response.items().getFirst().status());
        assertEquals(2, response.scanned());
        assertFalse(response.scanTruncated());
        assertEquals("GENERATION", response.businessLine());
        assertEquals("RUNNING", response.status());
    }

    @Test
    void statusFilteringStopsAtTheExplicitFiveHundredJobScanBudget() {
        List<ExecutionJobPort.JobView> failedPage = IntStream.range(0, 100)
                .mapToObj(index -> job(
                        "job-failed-" + index,
                        ExecutionJobPort.Status.FAILED,
                        false))
                .toList();
        for (int offset = 0; offset < 500; offset += 100) {
            when(jobs.list(ORGANIZATION, null, 100, offset))
                    .thenReturn(failedPage);
        }

        OperationsJobAdministrationController.JobListView response = controller.list(
                KEY, ORGANIZATION, ACTOR, "VIEWER", 1, null, "RUNNING");

        assertEquals(List.of(), response.items());
        assertEquals(500, response.scanned());
        assertTrue(response.scanTruncated());
        for (int offset = 0; offset < 500; offset += 100) {
            verify(jobs).list(ORGANIZATION, null, 100, offset);
        }
    }

    @Test
    void invalidFiltersAndLimitsFailBeforeReadingTheQueue() {
        assertThrows(IllegalArgumentException.class, () -> controller.list(
                KEY, ORGANIZATION, ACTOR, "VIEWER", 0, null, null));
        assertThrows(IllegalArgumentException.class, () -> controller.list(
                KEY, ORGANIZATION, ACTOR, "VIEWER", 101, null, null));
        assertThrows(IllegalArgumentException.class, () -> controller.list(
                KEY, ORGANIZATION, ACTOR, "VIEWER", 10, "unknown", null));
        assertThrows(IllegalArgumentException.class, () -> controller.list(
                KEY, ORGANIZATION, ACTOR, "VIEWER", 10, null, "unknown"));

        verifyNoInteractions(jobs);
    }

    @Test
    void missingWrongAndCrossTenantKeysDoNotReachTheQueue() {
        assertThrows(SecurityException.class, () -> controller.list(
                null, ORGANIZATION, ACTOR, "VIEWER", 10, null, null));
        assertThrows(SecurityException.class, () -> controller.list(
                "wrong-operations-key-with-safe-length",
                ORGANIZATION, ACTOR, "VIEWER", 10, null, null));
        assertThrows(SecurityException.class, () -> controller.list(
                KEY, "org-2", ACTOR, "VIEWER", 10, null, null));

        verifyNoInteractions(jobs);
    }

    @Test
    void missingWrongAndCrossTenantKeysCannotCancelOrProbeAJob() {
        assertThrows(SecurityException.class, () -> controller.cancel(
                null, ORGANIZATION, ACTOR, "OPERATOR", "job-1"));
        assertThrows(SecurityException.class, () -> controller.cancel(
                "wrong-operations-key-with-safe-length",
                ORGANIZATION, ACTOR, "OPERATOR", "job-1"));
        assertThrows(SecurityException.class, () -> controller.cancel(
                KEY, "org-2", ACTOR, "OPERATOR", "job-1"));

        verifyNoInteractions(jobs);
    }

    @Test
    void oidcAdministratorCanReadButCannotSelectAnotherTenant() {
        authenticatePlatformAdministrator();
        when(jobs.list(ORGANIZATION, null, 10, 0)).thenReturn(List.of());

        assertEquals(0, controller.list(
                null, ORGANIZATION, ACTOR, "VIEWER", 10, null, null).items().size());
        assertThrows(SecurityException.class, () -> controller.list(
                null, "org-2", ACTOR, "VIEWER", 10, null, null));

        verify(jobs).list(ORGANIZATION, null, 10, 0);
        verify(jobs, never()).list("org-2", null, 10, 0);
    }

    @Test
    void platformAdministratorCannotCancelOrProbeAnotherTenantsJob() {
        authenticatePlatformAdministrator();

        assertThrows(SecurityException.class, () -> controller.cancel(
                null, "org-2", ACTOR, "OPERATOR", "job-1"));

        verifyNoInteractions(jobs);
    }

    @Test
    void adminReaderCannotCancelEvenWhenTheHeaderClaimsApprover() {
        authenticate(List.of("VIEWER"), List.of("admin:read"));

        assertThrows(SecurityException.class, () -> controller.cancel(
                null, ORGANIZATION, ACTOR, "APPROVER", "job-1"));

        verifyNoInteractions(jobs);
    }

    @Test
    void operatorCanRequestCancellationOfAnActiveJob() {
        authenticatePlatformAdministrator();
        when(jobs.find(ORGANIZATION, "job-1")).thenReturn(Optional.of(
                job("job-1", ExecutionJobPort.Status.RUNNING, false)));
        when(jobs.requestCancel(ORGANIZATION, "job-1", ACTOR))
                .thenReturn(ExecutionJobPort.Status.RUNNING);

        var response = controller.cancel(
                null, ORGANIZATION, ACTOR, "VIEWER", "job-1");

        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        assertTrue(response.getBody().cancelRequested());
        assertFalse(response.getBody().idempotentReplay());
        verify(jobs).requestCancel(ORGANIZATION, "job-1", ACTOR);
    }

    @Test
    void repeatedCancellationReturnsTheExistingIntentWithoutAnotherMutation() {
        authenticatePlatformAdministrator();
        when(jobs.find(ORGANIZATION, "job-1")).thenReturn(Optional.of(
                job("job-1", ExecutionJobPort.Status.RUNNING, true)));

        var response = controller.cancel(
                null, ORGANIZATION, ACTOR, "VIEWER", "job-1");

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertTrue(response.getBody().cancelRequested());
        assertTrue(response.getBody().idempotentReplay());
        verify(jobs, never()).requestCancel(ORGANIZATION, "job-1", ACTOR);
    }

    @ParameterizedTest
    @EnumSource(
            value = ExecutionJobPort.Status.class,
            names = {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED", "LOST"})
    void terminalJobsCannotBeCancelled(ExecutionJobPort.Status terminal) {
        authenticatePlatformAdministrator();
        when(jobs.find(ORGANIZATION, "job-1")).thenReturn(Optional.of(
                job("job-1", terminal, false)));

        ExecutionJobPort.ExecutionStateException rejected = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> controller.cancel(
                        null, ORGANIZATION, ACTOR, "OPERATOR", "job-1"));

        assertEquals("ELMOS_EXECUTION_JOB_TERMINAL", rejected.code());
        verify(jobs, never()).requestCancel(ORGANIZATION, "job-1", ACTOR);
    }

    @Test
    void databaseTerminalRaceIsNotConvertedIntoSuccess() {
        authenticatePlatformAdministrator();
        when(jobs.find(ORGANIZATION, "job-1")).thenReturn(Optional.of(
                job("job-1", ExecutionJobPort.Status.RUNNING, false)));
        when(jobs.requestCancel(ORGANIZATION, "job-1", ACTOR)).thenThrow(
                new ExecutionJobPort.ExecutionStateException(
                        "ELMOS_EXECUTION_JOB_TERMINAL"));

        ExecutionJobPort.ExecutionStateException rejected = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> controller.cancel(
                        null, ORGANIZATION, ACTOR, "OPERATOR", "job-1"));

        assertEquals("ELMOS_EXECUTION_JOB_TERMINAL", rejected.code());
    }

    private static ExecutionJobPort.JobView job(
            String jobId,
            ExecutionJobPort.Status status,
            boolean cancelRequested
    ) {
        return new ExecutionJobPort.JobView(
                jobId,
                ORGANIZATION,
                "job-owner",
                ExecutionJobPort.BusinessLine.GENERATION,
                "project-generation",
                status,
                status.name(),
                (short) 50,
                ExecutionJobPort.ResultStatus.NOT_RUN,
                null,
                (short) 1,
                (short) 3,
                NOW.minusSeconds(60),
                NOW.minusSeconds(30),
                null,
                cancelRequested,
                2);
    }

    private static void authenticate(List<String> roles, List<String> permissions) {
        authenticate(roles, permissions, false);
    }

    private static void authenticatePlatformAdministrator() {
        authenticate(List.of("OPERATOR"), List.of(), true);
    }

    private static void authenticate(
            List<String> roles,
            List<String> permissions,
            boolean platformAdministrator
    ) {
        var tokenBuilder = Jwt.withTokenValue("verified-operations-job-token")
                .header("alg", "RS256")
                .subject(ACTOR)
                .issuedAt(NOW.minusSeconds(60))
                .expiresAt(NOW.plusSeconds(3600))
                .claim("organization_id", ORGANIZATION)
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
