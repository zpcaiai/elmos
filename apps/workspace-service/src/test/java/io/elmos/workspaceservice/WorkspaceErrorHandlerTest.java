package io.elmos.workspaceservice;

import io.elmos.workspace.WorkspaceProvisioningPort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class WorkspaceErrorHandlerTest {
    private WorkspaceProvisioningPort workspaces;
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        workspaces = mock(WorkspaceProvisioningPort.class);
        mvc = standaloneSetup(new WorkspaceController(workspaces))
                .setControllerAdvice(new WorkspaceErrorHandler())
                .build();
    }

    @Test
    void malformedRequestsHaveAStableNonRetryableContract() throws Exception {
        mvc.perform(post("/api/v1/workspaces")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("WORKSPACE_REQUEST_INVALID"))
                .andExpect(jsonPath("$.retryable").value(false));
    }

    @Test
    void policyFailuresAreForbiddenWithoutLeakingInternalDetails() throws Exception {
        doThrow(new SecurityException("sensitive policy implementation detail"))
                .when(workspaces).terminate(anyString());

        mvc.perform(delete("/api/v1/workspaces/ws-1"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("WORKSPACE_POLICY_DENIED"))
                .andExpect(jsonPath("$.message").value("The workspace request violates an enforced security policy."))
                .andExpect(jsonPath("$.retryable").value(false));
    }

    @Test
    void unavailableProvisionerIsExplicitAndRetryable() throws Exception {
        doThrow(new IllegalStateException("rootless Docker workspace provisioning is disabled"))
                .when(workspaces).terminate(anyString());

        mvc.perform(delete("/api/v1/workspaces/ws-1"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.errorCode").value("WORKSPACE_SERVICE_UNAVAILABLE"))
                .andExpect(jsonPath("$.retryable").value(true));
    }
}
