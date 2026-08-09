package io.elmos.controlplane;

import io.elmos.persistence.JdbcOrganizationSelfServiceStore;
import io.elmos.workflow.RunnerRegistrationPort;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Runtime verification of the authenticated tenant-to-runner write boundary. */
@WebMvcTest(controllers = RunnerFleetAdministrationController.class)
@ContextConfiguration(classes = RunnerFleetAdministrationSecurityTest.TestApplication.class)
@Import({
        ControlPlaneSecurityConfiguration.class,
        RunnerFleetAdministrationController.class
})
class RunnerFleetAdministrationSecurityTest {
    @Autowired MockMvc mvc;

    @MockitoBean RunnerRegistrationPort fleet;
    @MockitoBean JdbcOrganizationSelfServiceStore organizations;

    @Test
    void anonymousAndInsufficientRolesCannotReachFleetWrites() throws Exception {
        mvc.perform(post("/api/v1/runner/nodes/runner-1/drain"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/v1/runner/nodes/runner-1/drain")
                        .with(principal("org-1", "actor-1", "VIEWER")))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/v1/runner/nodes/runner-1/attestation/verify")
                        .with(principal("org-1", "actor-1", "OPERATOR")))
                .andExpect(status().isForbidden());

        verifyNoInteractions(fleet);
    }

    @Test
    void authenticatedTenantAndActorAreExplicitlyPassedToTheStore() throws Exception {
        mvc.perform(post("/api/v1/runner/nodes/runner-1/attestation/verify")
                        .with(principal("org-1", "actor-1", "APPROVER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("READY"));
        mvc.perform(post("/api/v1/runner/nodes/runner-1/drain")
                        .with(principal("org-1", "actor-1", "OPERATOR")))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("DRAINING"));

        verify(fleet).verifyAttestation("org-1", "runner-1", "actor-1");
        verify(fleet).requestDrain("org-1", "runner-1", "actor-1");
        verify(fleet, never()).verifyAttestation(
                "org-2", "runner-1", "actor-1");
        verify(fleet, never()).requestDrain(
                "org-2", "runner-1", "actor-1");
    }

    @Test
    void crossTenantAndNonexistentAttestationTargetsAreIndistinguishable()
            throws Exception {
        rejectAttestation("runner-other-tenant");
        rejectAttestation("runner-missing");

        String crossTenant = mvc.perform(post(
                                "/api/v1/runner/nodes/runner-other-tenant/attestation/verify")
                        .with(principal("org-1", "actor-1", "APPROVER")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ELMOS_RUNNER_UNKNOWN"))
                .andReturn().getResponse().getContentAsString();
        String nonexistent = mvc.perform(post(
                                "/api/v1/runner/nodes/runner-missing/attestation/verify")
                        .with(principal("org-1", "actor-1", "APPROVER")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ELMOS_RUNNER_UNKNOWN"))
                .andReturn().getResponse().getContentAsString();

        org.junit.jupiter.api.Assertions.assertEquals(crossTenant, nonexistent);
    }

    @Test
    void crossTenantAndNonexistentDrainTargetsAreIndistinguishable()
            throws Exception {
        rejectDrain("runner-other-tenant");
        rejectDrain("runner-missing");

        String crossTenant = mvc.perform(post(
                                "/api/v1/runner/nodes/runner-other-tenant/drain")
                        .with(principal("org-1", "actor-1", "OPERATOR")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ELMOS_RUNNER_UNKNOWN"))
                .andReturn().getResponse().getContentAsString();
        String nonexistent = mvc.perform(post(
                                "/api/v1/runner/nodes/runner-missing/drain")
                        .with(principal("org-1", "actor-1", "OPERATOR")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ELMOS_RUNNER_UNKNOWN"))
                .andReturn().getResponse().getContentAsString();

        org.junit.jupiter.api.Assertions.assertEquals(crossTenant, nonexistent);
    }

    private void rejectAttestation(String runnerNodeId) {
        doThrow(new RunnerRegistrationPort.RunnerAuthenticationException(
                "ELMOS_RUNNER_UNKNOWN"))
                .when(fleet).verifyAttestation(
                        "org-1", runnerNodeId, "actor-1");
    }

    private void rejectDrain(String runnerNodeId) {
        doThrow(new RunnerRegistrationPort.RunnerAuthenticationException(
                "ELMOS_RUNNER_UNKNOWN"))
                .when(fleet).requestDrain(
                        "org-1", runnerNodeId, "actor-1");
    }

    private static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.JwtRequestPostProcessor principal(
            String organizationId,
            String actorId,
            String role
    ) {
        return jwt().jwt(token -> token
                .subject(actorId)
                .claim("organization_id", organizationId)
                .claim("roles", List.of(role)));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }
}
