package io.elmos.agentgateway;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

class RepositoryOrchestratorControllerTest {
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = standaloneSetup(new RepositoryOrchestratorController()).build();
    }

    @Test
    void catalogReturnsExactlyTenServerOwnedUnavailableModels() throws Exception {
        mvc.perform(get("/agent/v1/repository-orchestrator/models"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.defaultMode").value("smart"))
                .andExpect(jsonPath("$.status").value("NOT_CONFIGURED"))
                .andExpect(jsonPath("$.models.length()").value(10))
                .andExpect(jsonPath("$.models[0].alias").value("gpt-5.6-sol-max"))
                .andExpect(jsonPath("$.models[9].alias").value("claude-sonnet-5"))
                .andExpect(jsonPath("$.models[0].available").value(false))
                .andExpect(jsonPath("$.models[0].selectable").value(false))
                .andExpect(jsonPath("$.runtimeProfilesAcceptedFromClient").value(false))
                .andExpect(jsonPath("$.evidence.providerInvocation").value("NOT_RUN"))
                .andExpect(jsonPath("$.evidence.certification").value("NOT_CERTIFIED"));
    }

    @Test
    void validSmartPreflightIsSideEffectFreeAndBlockedUntilOperatorConfiguration() throws Exception {
        mvc.perform(post("/agent/v1/repository-orchestrator/preflight")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(validSmartRequest()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("BLOCKED"))
                .andExpect(jsonPath("$.validationStatus").value("VALID"))
                .andExpect(jsonPath("$.configurationStatus").value("NOT_CONFIGURED"))
                .andExpect(jsonPath("$.selection.mode").value("smart"))
                .andExpect(jsonPath("$.selection.selectedModel").doesNotExist())
                .andExpect(jsonPath("$.selection.selectionSource").value("api"))
                .andExpect(jsonPath("$.selection.lockedByUser").value(false))
                .andExpect(jsonPath("$.selection.fallbackPolicy").value("router_policy"))
                .andExpect(jsonPath("$.selection.immutable").value(true))
                .andExpect(jsonPath("$.dag.status").value("NOT_RUN"))
                .andExpect(jsonPath("$.cost.status").value("NOT_CONFIGURED"))
                .andExpect(jsonPath("$.evidence.runCreation").value("NOT_RUN"))
                .andExpect(jsonPath("$.evidence.workspaceMutation").value("NOT_RUN"))
                .andExpect(jsonPath("$.evidence.scmEffects").value("NOT_RUN"));
    }

    @Test
    void clientRuntimeProfilesAndUnknownModelsAreRejected() throws Exception {
        String injected = validSmartRequest().replace(
                "\"risk\": {",
                "\"runtimeProfiles\": {}, \"selectionSource\": \"ui\", \"lockedByUser\": true, "
                        + "\"resolvedModel\": \"gpt-5.6-sol-max\", \"risk\": {");
        mvc.perform(post("/agent/v1/repository-orchestrator/preflight")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(injected))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("BLOCKED"))
                .andExpect(jsonPath("$.validationStatus").value("INVALID"))
                .andExpect(jsonPath("$.reasons").isArray())
                .andExpect(jsonPath("$.reasons.length()").value(4));

        mvc.perform(post("/agent/v1/repository-orchestrator/preflight")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(validSmartRequest()
                                .replace("\"mode\": \"smart\"", "\"mode\": \"manual\"")
                                .replace("\"selectedModel\": null", "\"selectedModel\": \"unknown-model\"")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.reasons[0]").value("MODEL_ALIAS_NOT_ALLOWLISTED:unknown-model"));
    }

    private static String validSmartRequest() {
        return """
                {
                  "schemaVersion": "1.0",
                  "catalogVersion": "repository-model-catalog-v1.1.0",
                  "selectionVersion": "repository-model-selection-v1",
                  "mode": "smart",
                  "selectedModel": null,
                  "optimizationProfile": "cost_performance",
                  "fallbackPolicy": null,
                  "verificationPolicy": "system_required_verifiers",
                  "risk": {
                    "security": "low",
                    "dataMigration": "low",
                    "concurrency": "low",
                    "publicContract": "low",
                    "blastRadius": "low",
                    "longHorizon": false
                  }
                }
                """;
    }
}
