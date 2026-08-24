package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.application.DatabaseDataCutoverGovernance;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.application.DatabaseDataCutoverGovernance.Decision.*;
import static io.elmos.application.DatabaseDataCutoverGovernance.Stage.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DatabaseDataControllerTest {
    private final ChinaDbSqlPreflightGateway sqlPreflight =
            mock(ChinaDbSqlPreflightGateway.class);
    private final DatabaseDataController controller =
            new DatabaseDataController(sqlPreflight);

    @AfterEach void resetRequestContext() {
        RequestContextHolder.resetRequestAttributes();
    }

    @Test void keepsDatabaseExecutionAndWriterSwitchOutOfControlPlane() {
        var capabilities = controller.capabilities();
        assertEquals("ELMOS_DATABASE_DATA", capabilities.engine());
        assertEquals(List.of("OLTP_DATABASE", "ANALYTICS_PLATFORM", "BI_SEMANTIC"), capabilities.tracks());
        assertTrue(capabilities.prohibitedActions().contains("CONNECT_TO_CUSTOMER_DATABASE"));
        assertTrue(capabilities.prohibitedActions().contains("SWITCH_AUTHORITATIVE_WRITER"));
        assertTrue(capabilities.status().contains("NOT_CONFIGURED"));
    }

    @Test void writeCutoverRequiresEveryDataGateAndNamedApproval() {
        var evidence = evidence(READ_CUTOVER, WRITE_CUTOVER, true, null);
        assertEquals(HUMAN_REVIEW, controller.evaluateCutover(evidence).decision());
        assertEquals(ADVANCE, controller.evaluateCutover(
                evidence(READ_CUTOVER, WRITE_CUTOVER, true, "database-owner")).decision());
        var blocked = controller.evaluateCutover(evidence(READ_CUTOVER, WRITE_CUTOVER, false, "database-owner"));
        assertEquals(HOLD, blocked.decision());
        assertTrue(blocked.blockers().contains("QUERY_PERFORMANCE_FAILED"));
    }

    @Test void sqlPreflightRejectsRequestsWithoutAnAuthenticatedTenantPrincipal() {
        assertThrows(AccessDeniedException.class, controller::sqlPreflightCapabilities);
        assertThrows(AccessDeniedException.class, () -> controller.assessSql("{}".getBytes()));
        verifyNoInteractions(sqlPreflight);
    }

    @Test void workspaceViewCanReadCapabilitiesButCannotExecutePreflight() {
        bindPrincipal("org-a", "actor-a", Set.of("workspace:view"));
        var capabilities = new ObjectMapper().createObjectNode().put("status", "BLOCKED");
        when(sqlPreflight.capabilities()).thenReturn(capabilities);

        var response = controller.sqlPreflightCapabilities();

        assertSame(capabilities, response.getBody());
        assertEquals("private, no-store", response.getHeaders().getFirst("Cache-Control"));
        assertThrows(AccessDeniedException.class, () -> controller.assessSql("{}".getBytes()));
        verify(sqlPreflight, never()).assess(any(), eq("org-a"), eq("actor-a"));
    }

    @Test void translationExecuteForwardsOnlyTheTrustedTenantAndActor() {
        bindPrincipal("org-a", "actor-a", Set.of("workspace:view", "translation:execute"));
        byte[] request = "{\"schemaVersion\":\"1.0\"}".getBytes();
        var blocked = new ObjectMapper().createObjectNode()
                .put("state", "BLOCKED")
                .putNull("targetSql")
                .put("certification", "NOT_CERTIFIED");
        when(sqlPreflight.assess(request, "org-a", "actor-a")).thenReturn(blocked);

        var response = controller.assessSql(request);

        assertSame(blocked, response.getBody());
        assertEquals("private, no-store", response.getHeaders().getFirst("Cache-Control"));
        verify(sqlPreflight).assess(request, "org-a", "actor-a");
    }

    @Test void workerResponseLengthMismatchFailsClosed() {
        HttpChinaDbSqlPreflightGateway.requireMatchingContentLength(-1, 12);
        HttpChinaDbSqlPreflightGateway.requireMatchingContentLength(12, 12);
        ChinaDbSqlPreflightFailure failure = assertThrows(
                ChinaDbSqlPreflightFailure.class,
                () -> HttpChinaDbSqlPreflightGateway.requireMatchingContentLength(13, 12));
        assertEquals("CHINADB_SQL_PREFLIGHT_PROTOCOL_ERROR", failure.errorCode());
        assertEquals("BLOCKED", failure.body().get("status"));
        assertEquals("NOT_CERTIFIED", failure.body().get("certification"));
    }

    private DatabaseDataCutoverGovernance.Evidence evidence(
            DatabaseDataCutoverGovernance.Stage current,
            DatabaseDataCutoverGovernance.Stage requested,
            boolean performance,
            String approval) {
        return new DatabaseDataCutoverGovernance.Evidence("org-1", current, requested,
                true, true, true, performance, true, true, true, true, true, true,
                true, true, true, List.of("evidence://database-cutover"), approval);
    }

    private static void bindPrincipal(
            String organizationId,
            String actorId,
            Set<String> permissions
    ) {
        var grant = new ControlPlanePrincipal.TenantGrant(Set.of("VIEWER"), permissions);
        var principal = new ControlPlanePrincipal(
                organizationId, actorId, Set.of("VIEWER"), permissions,
                Map.of(organizationId, grant));
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setAttribute(OidcTenantMembershipFilter.PRINCIPAL_ATTRIBUTE, principal);
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
    }
}
