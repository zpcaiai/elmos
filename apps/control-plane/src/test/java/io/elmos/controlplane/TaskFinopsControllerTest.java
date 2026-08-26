package io.elmos.controlplane;

import io.elmos.workflow.TaskFinopsPolicy;
import io.elmos.workflow.TaskFinopsPort;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class TaskFinopsControllerTest {
    private static final Instant NOW = Instant.parse("2026-08-24T12:00:00Z");
    private final TaskFinopsPort port = mock(TaskFinopsPort.class);

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void pauseBindsOnlyAuthenticatedOrganizationAccountAndActor() {
        authenticate("DEVELOPER");
        ControlPlanePrincipal expected = ControlPlanePrincipal.current().orElseThrow();
        when(port.pause(any())).thenReturn(TaskFinopsPolicy.TaskState.PAUSE_REQUESTED);

        var response = controller().pause(
                "task-a", "pause-idem-a",
                new TaskFinopsController.ControlRequest("USER_REQUEST"));

        assertEquals(HttpStatus.ACCEPTED, response.getStatusCode());
        ArgumentCaptor<TaskFinopsPort.ControlCommand> captured =
                ArgumentCaptor.forClass(TaskFinopsPort.ControlCommand.class);
        verify(port).pause(captured.capture());
        TaskFinopsPort.AuthenticatedContext context = captured.getValue().context();
        assertEquals(expected.organizationId(), context.organizationId());
        assertEquals(expected.accountId(), context.accountId());
        assertEquals(expected.actorId(), context.actorId());
        assertTrue(context.requestId().startsWith("mtf-api-"));
        assertEquals(64, captured.getValue().requestDigest().length());
    }

    @Test
    void viewerCannotInvokeTaskControlMutation() {
        authenticate("VIEWER");
        assertThrows(AccessDeniedException.class, () -> controller().resume(
                "task-a", "resume-idem-a",
                new TaskFinopsController.ControlRequest("USER_REQUEST")));
    }

    private TaskFinopsController controller() {
        return new TaskFinopsController(
                port, Clock.fixed(NOW, ZoneOffset.UTC));
    }

    private static void authenticate(String role) {
        Jwt token = Jwt.withTokenValue("verified-test-token")
                .header("alg", "RS256")
                .issuer("https://issuer.example.test")
                .subject("actor-finops")
                .issuedAt(NOW.minusSeconds(30))
                .expiresAt(NOW.plusSeconds(300))
                .claim("organization_id", "tenant-finops")
                .claim("roles", List.of(role))
                .build();
        SecurityContextHolder.getContext().setAuthentication(
                new JwtAuthenticationToken(token,
                        List.of(new SimpleGrantedAuthority("ROLE_TEST"))));
    }
}
