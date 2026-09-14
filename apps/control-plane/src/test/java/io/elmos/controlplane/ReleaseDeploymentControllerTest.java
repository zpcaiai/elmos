package io.elmos.controlplane;

import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import static org.junit.jupiter.api.Assertions.*;

class ReleaseDeploymentControllerTest {
    @AfterEach void cleanup() { RequestContextHolder.resetRequestAttributes(); }

    @Test void requiresDatabaseIdentityAndExactActorGrant() throws Exception {
        var binding = new ReleaseDeploymentController.Binding(Map.of("tenant_id", "tenant",
                "workspace_id", "workspace", "project_id", "project", "environment_id", "env",
                "account_id", "account"), Map.of("actor", Set.of("deployment:read")));
        int[] calls = {0};
        var host = new ReleaseDeploymentController.Host() {
            public ReleaseDeploymentController.Binding binding(String environment) { return binding; }
            public byte[] exchange(String method, String path, byte[] body, String actor,
                                   ReleaseDeploymentController.Binding actual) {
                calls[0]++;
                assertEquals("actor", actor);
                assertEquals("/v1/deployments/one", path);
                assertEquals(binding, actual);
                return "{}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
            }
        };
        var beans = new DefaultListableBeanFactory();
        beans.registerSingleton("host", host);
        var controller = new ReleaseDeploymentController(beans.getBeanProvider(ReleaseDeploymentController.Host.class));
        var request = new MockHttpServletRequest("GET", "/api/v1/release-deployment/env/v1/deployments/one");
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
        request.addHeader("X-ELMOS-Actor-ID", "actor");
        assertThrows(AccessDeniedException.class, () -> controller.call("env", request));
        var grant = new ControlPlanePrincipal.TenantGrant(Set.of("VIEWER"), Set.of("workspace:view"));
        request.setAttribute(OidcTenantMembershipFilter.PRINCIPAL_ATTRIBUTE,
                new ControlPlanePrincipal("tenant", "other", false, grant.roles(), grant.permissions(), Map.of("tenant", grant)));
        assertThrows(AccessDeniedException.class, () -> controller.call("env", request));
        assertEquals(0, calls[0]);
        request.setAttribute(OidcTenantMembershipFilter.PRINCIPAL_ATTRIBUTE,
                new ControlPlanePrincipal("tenant", "actor", false, grant.roles(), grant.permissions(), Map.of("tenant", grant)));
        assertEquals(200, controller.call("env", request).getStatusCode().value());
        assertEquals(1, calls[0]);
    }
}
