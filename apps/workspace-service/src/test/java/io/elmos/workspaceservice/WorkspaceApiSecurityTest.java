package io.elmos.workspaceservice;

import io.elmos.secret.SecretInjectionService;
import io.elmos.secret.SecretLease;
import io.elmos.workspace.WorkspaceModels;
import io.elmos.workspace.WorkspaceProvisioningPort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.flyway.FlywayAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = WorkspaceApiSecurityTest.TestApplication.class,
        properties = {
                "elmos.workspace.service-auth.api-key=workspace-test-key-32-characters",
                "elmos.workspace.service-auth.api-key-expires-at=2026-08-09T01:00:00Z",
                "elmos.workspace.service-auth.organization-id=tenant-a",
                "elmos.workspace.service-auth.actor-id=workspace-service",
                "management.endpoints.web.exposure.include=health"
        })
@AutoConfigureMockMvc
class WorkspaceApiSecurityTest {
    private static final String KEY = "workspace-test-key-32-characters";
    private static final String WORKSPACE_REQUEST = """
            {
              "workspaceId": "ws-1",
              "organizationId": "%s",
              "migrationRunId": "run-1",
              "snapshotId": "snapshot-1",
              "sandboxProfile": "java-21",
              "imageDigest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
              "resources": {
                "cpu": 1.0,
                "memoryMb": 1024,
                "pids": 128,
                "diskMb": 2048,
                "workspaceTimeout": "PT5M"
              },
              "networkPolicyId": "network-1",
              "correlationId": "correlation-1"
            }
            """;
    private static final String COMMAND_REQUEST = """
            {
              "commandId": "command-1",
              "argv": ["/bin/true"],
              "workingDirectory": "/workspace",
              "safeEnvironment": {},
              "timeout": "PT30S"
            }
            """;

    @Autowired MockMvc mvc;
    @Autowired WorkspaceProvisioningPort workspaces;
    @Autowired WorkspaceOwnership ownership;
    @Autowired SecretInjectionService secrets;

    @BeforeEach
    void resetCollaborators() {
        reset(workspaces, ownership, secrets);
    }

    @Test
    void anonymousWorkspaceCallsAreRejectedBeforeTheController() throws Exception {
        mvc.perform(post("/api/v1/workspaces")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(WORKSPACE_REQUEST.formatted("tenant-a")))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("WORKSPACE_SERVICE_AUTH_REQUIRED"));

        verifyNoInteractions(workspaces, ownership);
    }

    @Test
    void wrongServiceCredentialIsForbiddenWithoutSideEffects() throws Exception {
        mvc.perform(post("/api/v1/workspaces")
                        .with(credential("x".repeat(KEY.length()), "tenant-a", "workspace-service"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(WORKSPACE_REQUEST.formatted("tenant-a")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("WORKSPACE_SERVICE_AUTH_FORBIDDEN"));
        mvc.perform(post("/api/v1/workspaces")
                        .with(credential("short-wrong-key", "tenant-a", "workspace-service"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(WORKSPACE_REQUEST.formatted("tenant-a")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("WORKSPACE_SERVICE_AUTH_FORBIDDEN"));

        verifyNoInteractions(workspaces, ownership);
    }

    @Test
    void credentialTenantAndActorAreBothBound() throws Exception {
        mvc.perform(post("/api/v1/workspaces")
                        .with(credential(KEY, "tenant-b", "workspace-service"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(WORKSPACE_REQUEST.formatted("tenant-b")))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/v1/workspaces")
                        .with(credential(KEY, "tenant-a", "other-actor"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(WORKSPACE_REQUEST.formatted("tenant-a")))
                .andExpect(status().isForbidden());

        verifyNoInteractions(workspaces, ownership);
    }

    @Test
    void authenticatedTenantReplacesRatherThanTrustsTheBodyOrganization() throws Exception {
        when(workspaces.provision(any())).thenReturn(
                new WorkspaceProvisioningPort.WorkspaceHandle("ws-1", "container-1", "network-1"));

        mvc.perform(post("/api/v1/workspaces")
                        .with(validCredential())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(WORKSPACE_REQUEST.formatted("tenant-a")))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.workspaceId").value("ws-1"));

        verify(ownership).requireProvisionable("ws-1", "tenant-a");
        ArgumentCaptor<WorkspaceModels.WorkspaceRequest> request =
                ArgumentCaptor.forClass(WorkspaceModels.WorkspaceRequest.class);
        verify(workspaces).provision(request.capture());
        assertEquals("tenant-a", request.getValue().organizationId());

        reset(workspaces, ownership);
        mvc.perform(post("/api/v1/workspaces")
                        .with(validCredential())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(WORKSPACE_REQUEST.formatted("tenant-b")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("WORKSPACE_POLICY_DENIED"));
        verifyNoInteractions(workspaces, ownership);
    }

    @Test
    void crossTenantOwnershipBlocksEveryWorkspaceMutation() throws Exception {
        doThrow(new SecurityException("not this tenant"))
                .when(ownership).requireOwned("ws-other", "tenant-a");

        mvc.perform(post("/api/v1/workspaces/ws-other/commands")
                        .with(validCredential())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(COMMAND_REQUEST))
                .andExpect(status().isForbidden());
        mvc.perform(delete("/api/v1/workspaces/ws-other")
                        .with(validCredential()))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/v1/workspaces/ws-other/secrets")
                        .with(validCredential())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"leaseId":"lease-1","type":"NEXUS_READ_TOKEN","ttlSeconds":60}
                                """))
                .andExpect(status().isForbidden());
        mvc.perform(delete("/api/v1/workspaces/ws-other/secrets/lease-1")
                        .with(validCredential()))
                .andExpect(status().isForbidden());

        verify(workspaces, never()).execute(any(), any());
        verify(workspaces, never()).terminate(any());
        verifyNoInteractions(secrets);
    }

    @Test
    void missingAndCrossTenantWorkspacesHaveTheSameExternalError() throws Exception {
        doThrow(new SecurityException("missing"))
                .when(ownership).requireOwned("ws-missing", "tenant-a");
        doThrow(new SecurityException("other tenant"))
                .when(ownership).requireOwned("ws-other", "tenant-a");

        MvcResult missing = mvc.perform(delete("/api/v1/workspaces/ws-missing")
                        .with(validCredential()))
                .andExpect(status().isForbidden())
                .andReturn();
        MvcResult otherTenant = mvc.perform(delete("/api/v1/workspaces/ws-other")
                        .with(validCredential()))
                .andExpect(status().isForbidden())
                .andReturn();

        assertEquals(
                missing.getResponse().getContentAsString(),
                otherTenant.getResponse().getContentAsString());
        verify(workspaces, never()).terminate(any());
    }

    @Test
    void ownedWorkspaceAllowsCommandTerminationAndSecretLifecycle() throws Exception {
        Instant now = Instant.parse("2026-08-09T00:00:00Z");
        when(workspaces.execute(any(), any())).thenReturn(new WorkspaceModels.CommandResult(
                "command-1", "a".repeat(64), "/workspace", now, now.plusSeconds(1),
                0, "COMPLETED", "stdout-1", "stderr-1", false, "b".repeat(64), java.util.List.of()));
        when(secrets.inject(any(), any())).thenReturn(new SecretLease(
                "lease-1", "provider-1", SecretLease.SecretType.NEXUS_READ_TOKEN, "ws-1",
                now, now.plusSeconds(60), SecretLease.Status.INJECTED));

        mvc.perform(post("/api/v1/workspaces/ws-1/commands")
                        .with(validCredential())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(COMMAND_REQUEST))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.commandId").value("command-1"));
        mvc.perform(delete("/api/v1/workspaces/ws-1")
                        .with(validCredential()))
                .andExpect(status().isNoContent());
        mvc.perform(post("/api/v1/workspaces/ws-1/secrets")
                        .with(validCredential())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"leaseId":"lease-1","type":"NEXUS_READ_TOKEN","ttlSeconds":60}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.workspaceId").value("ws-1"));
        mvc.perform(delete("/api/v1/workspaces/ws-1/secrets/lease-1")
                        .with(validCredential()))
                .andExpect(status().isNoContent());

        verify(workspaces).execute(any(), any());
        verify(workspaces).terminate("ws-1");
        verify(secrets).inject(any(), any());
        verify(secrets).revoke("lease-1", "ws-1");
    }

    @Test
    void healthAndExactHmacPathStayOpenButEverythingElseDefaultsClosed() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
        for (String path : java.util.List.of(
                "/internal/v1/spring-runtimes",
                "/internal/v1/spring-verifications",
                "/internal/v1/spring-transformations")) {
            mvc.perform(post(path)
                            .header("X-Test-HMAC", "verified-by-existing-controller"))
                    .andExpect(status().isNoContent());
        }
        mvc.perform(post("/internal/v1/unlisted"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/actuator/info"))
                .andExpect(status().isUnauthorized());
    }

    private static RequestPostProcessor validCredential() {
        return credential(KEY, "tenant-a", "workspace-service");
    }

    private static RequestPostProcessor credential(String key, String organizationId, String actorId) {
        return request -> {
            request.addHeader(WorkspaceServiceCredentialFilter.KEY_HEADER, key);
            request.addHeader(WorkspaceServiceCredentialFilter.ORGANIZATION_HEADER, organizationId);
            request.addHeader(WorkspaceServiceCredentialFilter.ACTOR_HEADER, actorId);
            return request;
        };
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration(exclude = {
            DataSourceAutoConfiguration.class,
            FlywayAutoConfiguration.class
    })
    @Import(WorkspaceSecurityConfiguration.class)
    static class TestApplication {
        @Bean
        Clock workspaceClock() {
            return Clock.fixed(Instant.parse("2026-08-09T00:00:00Z"), ZoneOffset.UTC);
        }

        @Bean
        WorkspaceProvisioningPort workspaces() {
            return mock(WorkspaceProvisioningPort.class);
        }

        @Bean
        WorkspaceOwnership ownership() {
            return mock(WorkspaceOwnership.class);
        }

        @Bean
        SecretInjectionService secrets() {
            return mock(SecretInjectionService.class);
        }

        @Bean
        WorkspaceController workspaceController(
                WorkspaceProvisioningPort workspaces,
                WorkspaceOwnership ownership
        ) {
            return new WorkspaceController(workspaces, ownership);
        }

        @Bean
        SecretInjectionController secretInjectionController(
                SecretInjectionService secrets,
                WorkspaceOwnership ownership
        ) {
            return new SecretInjectionController(secrets, ownership);
        }

        @Bean
        WorkspaceErrorHandler workspaceErrorHandler() {
            return new WorkspaceErrorHandler();
        }

        @Bean
        InternalHmacProbe internalHmacProbe() {
            return new InternalHmacProbe();
        }
    }

    @RestController
    static final class InternalHmacProbe {
        @PostMapping({
                "/internal/v1/spring-runtimes",
                "/internal/v1/spring-verifications",
                "/internal/v1/spring-transformations"
        })
        ResponseEntity<Void> runtime(@RequestHeader("X-Test-HMAC") String verifiedHmac) {
            return ResponseEntity.noContent().build();
        }
    }
}
