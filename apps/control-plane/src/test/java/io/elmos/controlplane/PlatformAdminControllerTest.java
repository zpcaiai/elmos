package io.elmos.controlplane;

import io.elmos.commercial.PlatformAdminPort;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

class PlatformAdminControllerTest {
    private static final String ORGANIZATION = "org-admin";
    private static final String ACTOR = "oidc-admin-subject";

    private final PlatformAdminPort platform = mock(PlatformAdminPort.class);
    private final PlatformAdminController controller = new PlatformAdminController(platform);

    @AfterEach
    void clearRequestContext() {
        RequestContextHolder.resetRequestAttributes();
    }

    @Test
    void otherEmailCannotUseAnExistingPlatformAdministratorRecord() {
        bindDatabasePrincipal(false, ACTOR);
        when(platform.resolveAdminAccount(ORGANIZATION, ACTOR)).thenReturn("acct-live-admin");

        var response = controller.wallets(ORGANIZATION, ACTOR, null, 50);

        assertDenied(response, PlatformAdminPort.Decision.DENIED_NOT_ADMIN);
        verifyNoInteractions(platform);
    }

    @Test
    void exactAdministratorEmailCannotForgeTheActorHeader() {
        bindDatabasePrincipal(true, ACTOR);
        when(platform.resolveAdminAccount(ORGANIZATION, "victim-actor"))
                .thenReturn("acct-victim-admin");

        var response = controller.wallets(ORGANIZATION, "victim-actor", null, 50);

        assertDenied(response, PlatformAdminPort.Decision.DENIED_NOT_ADMIN);
        verifyNoInteractions(platform);
    }

    @Test
    void missingDatabaseBoundPrincipalFailsBeforeAdministratorLookup() {
        when(platform.resolveAdminAccount(ORGANIZATION, ACTOR)).thenReturn("acct-live-admin");

        var response = controller.wallets(ORGANIZATION, ACTOR, null, 50);

        assertDenied(response, PlatformAdminPort.Decision.DENIED_NOT_ADMIN);
        verifyNoInteractions(platform);
    }

    @Test
    void exactAdministratorEmailAndMatchingActorReachTheDatabaseGate() {
        bindDatabasePrincipal(true, ACTOR);
        when(platform.resolveAdminAccount(ORGANIZATION, ACTOR)).thenReturn("acct-admin");
        when(platform.wallets("acct-admin", null, 50)).thenReturn(
                new PlatformAdminPort.Page<>(PlatformAdminPort.Decision.ALLOWED, List.of()));

        var response = controller.wallets(ORGANIZATION, ACTOR, null, 50);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("ALLOWED", ((Map<?, ?>) response.getBody()).get("status"));
        verify(platform).resolveAdminAccount(ORGANIZATION, ACTOR);
        verify(platform).wallets("acct-admin", null, 50);
        verifyNoMoreInteractions(platform);
    }

    private static void bindDatabasePrincipal(boolean platformAdministrator, String actorId) {
        var grant = new ControlPlanePrincipal.TenantGrant(
                Set.of("VIEWER"), Set.of("workspace:view"));
        var principal = new ControlPlanePrincipal(
                ORGANIZATION,
                actorId,
                platformAdministrator,
                grant.roles(),
                grant.permissions(),
                Map.of(ORGANIZATION, grant));
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setAttribute(OidcTenantMembershipFilter.PRINCIPAL_ATTRIBUTE, principal);
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
    }

    private static void assertDenied(
            org.springframework.http.ResponseEntity<?> response,
            PlatformAdminPort.Decision decision
    ) {
        assertEquals(HttpStatus.FORBIDDEN, response.getStatusCode());
        assertEquals("DENIED", ((Map<?, ?>) response.getBody()).get("status"));
        assertEquals(decision.name(), ((Map<?, ?>) response.getBody()).get("code"));
    }
}
