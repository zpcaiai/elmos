package io.elmos.workspaceservice;

import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

class WorkspaceServiceCredentialFilterTest {
    private static final Clock NOW = Clock.fixed(
            Instant.parse("2026-08-09T00:00:00Z"), ZoneOffset.UTC);

    @Test
    void missingConfigurationFailsClosedAsUnavailable() throws Exception {
        var filter = new WorkspaceServiceCredentialFilter(NOW, "", "", "", "");
        var request = workspaceRequest();
        var response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        assertEquals(503, response.getStatus());
        assertEquals("no-store", response.getHeader("Cache-Control"));
        verifyNoInteractions(chain);
    }

    @Test
    void anOverlongCredentialLeaseIsNotTreatedAsConfigured() throws Exception {
        var filter = new WorkspaceServiceCredentialFilter(
                NOW,
                "workspace-test-key-32-characters",
                "2026-08-10T00:00:01Z",
                "tenant-a",
                "workspace-service");
        var request = workspaceRequest();
        var response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        assertEquals(503, response.getStatus());
        verifyNoInteractions(chain);
    }

    @Test
    void anExpiredCredentialLeaseIsNotTreatedAsConfigured() throws Exception {
        var filter = new WorkspaceServiceCredentialFilter(
                NOW,
                "workspace-test-key-32-characters",
                "2026-08-08T23:59:59Z",
                "tenant-a",
                "workspace-service");
        var request = workspaceRequest();
        var response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        assertEquals(503, response.getStatus());
        verifyNoInteractions(chain);
    }

    @Test
    void anOversizedPresentedCredentialIsRejectedBeforeTheController() throws Exception {
        var filter = configuredFilter();
        var request = workspaceRequest();
        request.addHeader(WorkspaceServiceCredentialFilter.KEY_HEADER, "x".repeat(4097));
        request.addHeader(WorkspaceServiceCredentialFilter.ORGANIZATION_HEADER, "tenant-a");
        request.addHeader(WorkspaceServiceCredentialFilter.ACTOR_HEADER, "workspace-service");
        var response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        assertEquals(403, response.getStatus());
        verifyNoInteractions(chain);
    }

    private static WorkspaceServiceCredentialFilter configuredFilter() {
        return new WorkspaceServiceCredentialFilter(
                NOW,
                "workspace-test-key-32-characters",
                "2026-08-09T01:00:00Z",
                "tenant-a",
                "workspace-service");
    }

    private static MockHttpServletRequest workspaceRequest() {
        var request = new MockHttpServletRequest("POST", "/api/v1/workspaces");
        request.setServletPath("/api/v1/workspaces");
        return request;
    }
}
