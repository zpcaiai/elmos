package io.elmos.controlplane;

import io.elmos.commercial.SelfServiceBillingPort;
import io.elmos.commercial.SelfServiceBillingPort.QuotaAdministrationView;
import io.elmos.persistence.JdbcOperationsManagementStore;
import io.elmos.persistence.JdbcOrganizationSelfServiceStore;
import io.elmos.persistence.JdbcRunHistoryStore;
import io.elmos.persistence.JdbcUserActivityStore;
import io.elmos.workflow.ExecutionJobPort;
import io.elmos.workflow.RunnerRegistrationPort;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.ServletException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Verifies the boundary between Spring Security and the controllers' own
 * time-bound operations credential. A 403 from these requests is important:
 * it proves the request reached the controller and was rejected by its key
 * authorization rather than being intercepted as an unauthenticated JWT call.
 */
@WebMvcTest(controllers = {
        OperationsObservabilityController.class,
        TenantQuotaController.class,
        OperationsJobAdministrationController.class,
        OperationsRunnerFleetAdministrationController.class
})
@ContextConfiguration(classes = ControlPlaneOperationsSecurityTest.TestApplication.class)
@Import({
        ControlPlaneSecurityConfiguration.class,
        OperationsAuthorization.class,
        OperationsObservabilityController.class,
        TenantQuotaController.class,
        OperationsJobAdministrationController.class,
        OperationsRunnerFleetAdministrationController.class,
        ServerOperationAuditConfiguration.class
})
class ControlPlaneOperationsSecurityTest {
    private static final String KEY = "operations-security-test-key-32-characters";
    private static final Instant NOW = Instant.parse("2026-08-09T08:00:00Z");
    private static final Instant EXPIRES_AT = NOW.plusSeconds(3600);

    @DynamicPropertySource
    static void operationsCredential(DynamicPropertyRegistry registry) {
        registry.add("elmos.operations.api-key", () -> KEY);
        registry.add("elmos.operations.api-key-expires-at", EXPIRES_AT::toString);
        registry.add("elmos.operations.organization-id", () -> "org-1");
        registry.add("elmos.operations.actor-id", () -> "actor-1");
    }

    @Autowired MockMvc mvc;

    @MockitoBean Clock clock;
    @MockitoBean JdbcUserActivityStore activity;
    @MockitoBean JdbcOperationsManagementStore management;
    @MockitoBean JdbcRunHistoryStore runHistory;
    @MockitoBean SelfServiceBillingPort billing;
    @MockitoBean JdbcOrganizationSelfServiceStore organizations;
    @MockitoBean ExecutionJobPort jobs;
    @MockitoBean RunnerRegistrationPort fleet;

    @BeforeEach
    void fixCredentialClock() {
        when(clock.instant()).thenReturn(NOW);
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "/api/v1/operations-observability/summary",
            "/api/v1/operations-observability/jobs",
            "/api/v1/operations-observability/runners",
            "/api/v1/tenant-quota"
    })
    void anonymousRequestsReachTheKeyProtectedControllersAndFailClosed(String path) throws Exception {
        mvc.perform(get(path)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isForbidden());
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "/api/v1/operations-observability/summary",
            "/api/v1/operations-observability/jobs",
            "/api/v1/operations-observability/runners",
            "/api/v1/tenant-quota"
    })
    void wrongOperationsKeyReachesTheControllerButCannotRead(String path) throws Exception {
        mvc.perform(get(path)
                        .header("X-ELMOS-Operations-Key", "wrong-operations-key-with-safe-length")
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isForbidden());
    }

    @ParameterizedTest
    @MethodSource("selfAuthorizedOperationsRoutes")
    void everyDeclaredSelfAuthorizedRouteBypassesOnlyJwtAndStillFailsClosedWithoutAKey(
            HttpMethod method,
            String path
    ) throws Exception {
        var request = method == HttpMethod.GET ? get(path) : post(path)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}");

        mvc.perform(request
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "APPROVER"))
                .andExpect(status().isForbidden());
    }

    @Test
    void currentShortLivedKeyCanReachOperationsSummaryWithoutBearerJwt() throws Exception {
        when(activity.summary(
                anyString(), any(), any(), anyString(), anyString(), anyInt()))
                .thenReturn(new JdbcUserActivityStore.ActivitySummary(
                        NOW.minusSeconds(3600), NOW, 0, 0, 0, 0, 0,
                        List.of(), List.of(), List.of(),
                        "POSTGRES_DUAL_STORE", "NOT_RUN"));

        mvc.perform(get("/api/v1/operations-observability/summary")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalEvents").value(0));
    }

    @Test
    void currentShortLivedKeyFailureKeepsItsFiveHundredAcrossTheErrorDispatch()
            throws Exception {
        RuntimeException storageFailure = new RuntimeException("simulated operations storage failure");
        when(activity.summary(
                anyString(), any(), any(), anyString(), anyString(), anyInt()))
                .thenThrow(storageFailure);

        ServletException controllerFailure = assertThrows(ServletException.class, () ->
                mvc.perform(get("/api/v1/operations-observability/summary")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER")));
        assertSame(storageFailure, controllerFailure.getCause());
        verify(activity).summary(
                eq("org-1"), any(), eq(NOW), eq("ALL"), eq("ALL"), eq(50));

        mvc.perform(get("/error")
                        .with(request -> {
                            request.setDispatcherType(DispatcherType.ERROR);
                            return request;
                        })
                        .requestAttr(RequestDispatcher.ERROR_STATUS_CODE, 500)
                        .requestAttr(RequestDispatcher.ERROR_REQUEST_URI,
                                "/api/v1/operations-observability/summary")
                        .requestAttr(RequestDispatcher.ERROR_EXCEPTION,
                                controllerFailure.getCause()))
                .andExpect(status().isInternalServerError());
    }

    @Test
    void onlyTheErrorDispatcherBypassesJwtAuthentication() throws Exception {
        mvc.perform(get("/error"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/operations-observability/future-route")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void currentShortLivedKeyCanReachTenantQuotaWithoutBearerJwt() throws Exception {
        when(billing.quotaForAdministration("org-1")).thenReturn(quota());

        mvc.perform(get("/api/v1/tenant-quota")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.organizationId").value("org-1"));
    }

    @Test
    void currentShortLivedKeyCanReadTheRealJobQueueWithoutBearerJwt() throws Exception {
        when(jobs.list("org-1", null, 25, 0)).thenReturn(List.of());

        mvc.perform(get("/api/v1/operations-observability/jobs")
                        .queryParam("limit", "25")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(0))
                .andExpect(jsonPath("$.limit").value(25));
    }

    @Test
    void currentShortLivedKeyCanReadOnlyItsBoundedSecretFreeFleetProjection()
            throws Exception {
        when(fleet.listFleet(
                "org-1", RunnerRegistrationPort.FleetStatus.READY, 3))
                .thenReturn(List.of(runner("runner-1"), runner("runner-2"), runner("runner-3")));

        mvc.perform(get("/api/v1/operations-observability/runners")
                        .queryParam("limit", "2")
                        .queryParam("status", "ready")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.schemaVersion").value("1.0.0"))
                .andExpect(jsonPath("$.items.length()").value(2))
                .andExpect(jsonPath("$.returned").value(2))
                .andExpect(jsonPath("$.truncated").value(true))
                .andExpect(jsonPath("$.status").value("READY"))
                .andExpect(jsonPath("$.items[0].runnerNodeId").value("runner-1"))
                .andExpect(jsonPath("$.items[0].organizationId").doesNotExist())
                .andExpect(jsonPath("$.items[0].enrollmentToken").doesNotExist())
                .andExpect(jsonPath("$.items[0].nodeToken").doesNotExist())
                .andExpect(jsonPath("$.items[0].tokenSha256").doesNotExist())
                .andExpect(jsonPath("$.items[0].verifierActorId").doesNotExist());

        verify(fleet).listFleet(
                "org-1", RunnerRegistrationPort.FleetStatus.READY, 3);
    }

    @Test
    void wrongTenantAndInvalidBoundsFailBeforeFleetStorageAccess() throws Exception {
        mvc.perform(get("/api/v1/operations-observability/runners")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-2")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/v1/operations-observability/runners")
                        .queryParam("limit", "0")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode")
                        .value("OPERATIONS_RUNNER_FLEET_REQUEST_INVALID"));
        mvc.perform(get("/api/v1/operations-observability/runners")
                        .queryParam("limit", "101")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/v1/operations-observability/runners")
                        .queryParam("status", "not-a-fleet-state")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(fleet);
    }

    @Test
    void operatorCancellationIsAuditedAsAttemptAndCompletion() throws Exception {
        when(jobs.find("org-1", "job-1")).thenReturn(Optional.of(job()));
        when(jobs.requestCancel("org-1", "job-1", "actor-1"))
                .thenReturn(ExecutionJobPort.Status.RUNNING);

        mvc.perform(post("/api/v1/operations-observability/jobs/job-1/cancel")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "OPERATOR")
                        .header("X-Request-ID", "cancel-request-1"))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.cancelRequested").value(true))
                .andExpect(jsonPath("$.idempotentReplay").value(false));

        verify(activity, times(2)).append(
                eq("org-1"),
                eq("actor-1"),
                eq("cancel-request-1"),
                anyList());
    }

    @Test
    void anonymousWrongRoleWrongKeyAndCrossTenantCancellationFailBeforeQueueAccess() throws Exception {
        mvc.perform(post("/api/v1/operations-observability/jobs/job-1/cancel")
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "OPERATOR"))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/v1/operations-observability/jobs/job-1/cancel")
                        .header("X-ELMOS-Operations-Key", "wrong-operations-key-with-safe-length")
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "OPERATOR"))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/v1/operations-observability/jobs/job-1/cancel")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "VIEWER"))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/v1/operations-observability/jobs/job-1/cancel")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-2")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "OPERATOR"))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void alreadyRequestedCancellationIsAuditedButDoesNotMutateTheQueueAgain() throws Exception {
        when(jobs.find("org-1", "job-1")).thenReturn(Optional.of(
                job(ExecutionJobPort.Status.RUNNING, true)));

        mvc.perform(post("/api/v1/operations-observability/jobs/job-1/cancel")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "OPERATOR")
                        .header("X-Request-ID", "repeat-cancel-request-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.cancelRequested").value(true))
                .andExpect(jsonPath("$.idempotentReplay").value(true));

        verify(jobs, never()).requestCancel(anyString(), anyString(), anyString());
        verify(activity, times(2)).append(
                eq("org-1"),
                eq("actor-1"),
                eq("repeat-cancel-request-1"),
                anyList());
    }

    @Test
    void terminalCancellationReturnsConflictWithoutMutation() throws Exception {
        when(jobs.find("org-1", "job-1")).thenReturn(Optional.of(
                job(ExecutionJobPort.Status.SUCCEEDED, false)));

        mvc.perform(post("/api/v1/operations-observability/jobs/job-1/cancel")
                        .header("X-ELMOS-Operations-Key", KEY)
                        .header("X-ELMOS-Organization-ID", "org-1")
                        .header("X-ELMOS-Actor-ID", "actor-1")
                        .header("X-ELMOS-Admin-Role", "OPERATOR"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode").value("ELMOS_EXECUTION_JOB_TERMINAL"));

        verify(jobs, never()).requestCancel(anyString(), anyString(), anyString());
    }

    @Test
    void adjacentAndUnrelatedApiPathsStillRequireJwtAuthentication() throws Exception {
        mvc.perform(get("/api/v1/operations-observability-admin/summary"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/operations-observability/future-route"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/v1/operations-observability/summary"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/operations-observability/events"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/operations-observability/runs/run-1/replay/extra"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/v1/operations-observability/jobs"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/operations-observability/jobs/job-1/cancel"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/v1/operations-observability/jobs/job-1/cancel/force"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/operations-observability/runners/runner-1"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/v1/operations-observability/runners"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/tenant-quota-admin"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/tenant-quota/future-route"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/tenant-quota/adjust"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/v1/tenant-quota"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/execution/jobs"))
                .andExpect(status().isUnauthorized());
    }

    private static Stream<Arguments> selfAuthorizedOperationsRoutes() {
        return Stream.of(
                Arguments.of(HttpMethod.GET, "/api/v1/operations-observability/summary"),
                Arguments.of(HttpMethod.GET, "/api/v1/operations-observability/audit-export"),
                Arguments.of(HttpMethod.GET, "/api/v1/operations-observability/runs/run-1/replay"),
                Arguments.of(HttpMethod.GET, "/api/v1/operations-observability/console"),
                Arguments.of(HttpMethod.GET, "/api/v1/operations-observability/jobs"),
                Arguments.of(HttpMethod.GET, "/api/v1/operations-observability/runners"),
                Arguments.of(HttpMethod.GET, "/api/v1/tenant-quota"),
                Arguments.of(HttpMethod.POST, "/api/v1/operations-observability/events"),
                Arguments.of(HttpMethod.POST, "/api/v1/operations-observability/audit-events"),
                Arguments.of(HttpMethod.POST, "/api/v1/operations-observability/evaluate"),
                Arguments.of(HttpMethod.POST, "/api/v1/operations-observability/alerts/alert-1/acknowledge"),
                Arguments.of(HttpMethod.POST, "/api/v1/operations-observability/incidents/incident-1/assign"),
                Arguments.of(HttpMethod.POST, "/api/v1/operations-observability/incidents/incident-1/resolve"),
                Arguments.of(HttpMethod.POST, "/api/v1/operations-observability/remediations/proposal-1/decision"),
                Arguments.of(HttpMethod.POST, "/api/v1/operations-observability/remediations/proposal-1/prepare-scm"),
                Arguments.of(HttpMethod.POST, "/api/v1/operations-observability/retention/enforce"),
                Arguments.of(HttpMethod.POST, "/api/v1/operations-observability/jobs/job-1/cancel"),
                Arguments.of(HttpMethod.POST, "/api/v1/tenant-quota/adjust"));
    }

    private static QuotaAdministrationView quota() {
        return new QuotaAdministrationView(
                "org-1", "quota-1", "subscription-1", "plan-1", "Plan 1",
                NOW.minusSeconds(3600), NOW.plusSeconds(3600),
                new BigDecimal("1000"), new BigDecimal("500"),
                BigDecimal.ZERO, BigDecimal.ZERO,
                BigDecimal.ZERO, BigDecimal.ZERO,
                BigDecimal.ZERO, BigDecimal.ZERO, 1);
    }

    private static ExecutionJobPort.JobView job() {
        return job(ExecutionJobPort.Status.RUNNING, false);
    }

    private static ExecutionJobPort.JobView job(
            ExecutionJobPort.Status status,
            boolean cancelRequested
    ) {
        return new ExecutionJobPort.JobView(
                "job-1",
                "org-1",
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

    private static RunnerRegistrationPort.FleetNodeView runner(String runnerNodeId) {
        return new RunnerRegistrationPort.FleetNodeView(
                runnerNodeId,
                "pool-1",
                "1.2.3",
                RunnerRegistrationPort.FleetStatus.READY,
                List.of("generation:multi"),
                2,
                true,
                NOW.minusSeconds(600),
                "allowlist-v1",
                NOW.minusSeconds(5),
                null,
                NOW.minusSeconds(3600),
                NOW.minusSeconds(5));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }
}
