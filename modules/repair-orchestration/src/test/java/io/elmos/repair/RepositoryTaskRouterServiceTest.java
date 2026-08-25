package io.elmos.repair;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.elmos.repair.RepositoryTaskRouterModels.OperatorRuntimeProfile;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RepositoryTaskRouterServiceTest {
    private static final ObjectMapper JSON = new ObjectMapper();

    private final RepositoryTaskRouterService service = new RepositoryTaskRouterService();

    @Test
    void catalogIsTheExactTenModelSourceOfTruthAndFailsClosed() {
        var catalog = service.catalog();

        assertEquals(List.of(
                "gpt-5.6-sol-max",
                "claude-opus-5-max",
                "claude-fable-5",
                "grok-4.6",
                "kimi-k3-max",
                "glm-5.3-max",
                "qwen3.8-max",
                "deepseek-v4-pro-0813",
                "gemini-3.7-flash-high",
                "claude-sonnet-5"),
                catalog.models().stream().map(RepositoryTaskRouterModels.ModelDescriptor::alias).toList());
        assertEquals("smart", catalog.defaultMode());
        assertEquals("NOT_CONFIGURED", catalog.status());
        assertFalse(catalog.runtimeProfilesAcceptedFromClient());
        assertTrue(catalog.models().stream().noneMatch(RepositoryTaskRouterModels.ModelDescriptor::selectable));
        assertTrue(catalog.models().stream().allMatch(model -> "NOT_CONFIGURED".equals(model.status())));
        assertTrue(catalog.models().stream().allMatch(model -> model.providerModelId() == null));
        assertTrue(catalog.models().stream().allMatch(model -> model.pricing().inputPerMillion() == null));
        assertEquals("NOT_RUN", catalog.evidence().providerInvocation());
        assertEquals("NOT_CERTIFIED", catalog.evidence().certification());
    }

    @Test
    void smartSelectionRequiresNullModelAndReturnsBlockedWithoutTrustedProfiles() throws Exception {
        var result = service.preflight(request("smart", null, null, lowRisk()), "api");

        assertEquals("VALID", result.validationStatus());
        assertEquals("BLOCKED", result.status());
        assertEquals("NOT_CONFIGURED", result.configurationStatus());
        assertNull(result.resolvedModel());
        assertEquals("L0", result.minimumRoutingTier());
        assertEquals("NOT_RUN", result.dag().status());
        assertEquals("NOT_CONFIGURED", result.cost().status());
        assertTrue(result.selection().immutable());
        assertEquals("router_policy", result.selection().fallbackPolicy());
        assertTrue(result.selection().digest().matches("[0-9a-f]{64}"));
        assertTrue(result.reasons().contains("NO_CONFIGURED_MODEL_MEETS_RISK_FLOOR:L0"));
        assertEquals("NOT_RUN", result.evidence().runCreation());
        assertEquals("NOT_RUN", result.evidence().scmEffects());
    }

    @Test
    void manualSelectionIsExactLockedAndRiskFloored() throws Exception {
        var result = service.preflight(request(
                "manual", "glm-5.3-max", "smart_within_allowlist", highSecurityRisk()), "api");

        assertEquals("VALID", result.validationStatus());
        assertEquals("BLOCKED", result.status());
        assertEquals("L3", result.minimumRoutingTier());
        assertTrue(result.reasons().contains("MANUAL_MODEL_BELOW_RISK_FLOOR:glm-5.3-max:L3"));
        assertTrue(result.reasons().contains("SELECTED_MODEL_NOT_CONFIGURED:glm-5.3-max"));
        assertEquals("smart_within_allowlist", result.selection().fallbackPolicy());
    }

    @Test
    void rejectsUnknownAliasSmartModelAndClientRuntimeProfile() throws Exception {
        JsonNode unknownAlias = request("manual", "eleventh-model", "strict", lowRisk());
        assertTrue(service.preflight(unknownAlias, "api").reasons().contains("MODEL_ALIAS_NOT_ALLOWLISTED:eleventh-model"));

        JsonNode smartWithModel = request("smart", "gpt-5.6-sol-max", null, lowRisk());
        assertTrue(service.preflight(smartWithModel, "api").reasons().contains("SMART_SELECTED_MODEL_MUST_BE_NULL"));

        var injected = (ObjectNode) request("smart", null, null, lowRisk()).deepCopy();
        injected.set("runtimeProfiles", JSON.createObjectNode());
        injected.put("selectionSource", "ui");
        injected.put("lockedByUser", true);
        injected.put("resolvedModel", "gpt-5.6-sol-max");
        var injectionResult = service.preflight(injected, "api");
        assertEquals("INVALID", injectionResult.validationStatus());
        assertTrue(injectionResult.reasons().contains("UNSUPPORTED_FIELD:runtimeProfiles"));
        assertTrue(injectionResult.reasons().contains("UNSUPPORTED_FIELD:selectionSource"));
        assertTrue(injectionResult.reasons().contains("UNSUPPORTED_FIELD:lockedByUser"));
        assertTrue(injectionResult.reasons().contains("UNSUPPORTED_FIELD:resolvedModel"));
        assertFalse(injectionResult.runtimeProfilesAcceptedFromClient());
    }

    @Test
    void trustedServerProfileCanPrepareButNeverExecute() throws Exception {
        Instant now = Instant.parse("2026-08-24T02:00:00Z");
        var configured = new RepositoryTaskRouterService(Map.of(
                "gpt-5.6-sol-max",
                new OperatorRuntimeProfile(
                        "operator/gpt-5.6-sol-max",
                        "deployment/openai-primary",
                        "gpt-5.6-sol-2026-08-20",
                        "provider-gateway/openai-v3",
                        now.minusSeconds(30),
                        now.minusSeconds(30),
                        300,
                        true,
                        true,
                        new BigDecimal("1.25"),
                        new BigDecimal("0.25"),
                        new BigDecimal("5.00"),
                        200_000,
                        16_000,
                        2,
                        1_000_000L,
                        0,
                        Set.of("us"),
                        "privacy/private-repository-v1",
                        true,
                        Set.of("repository_task_execution", "architect_verifier"))),
                Clock.fixed(now, ZoneOffset.UTC));

        var result = configured.preflight(request(
                "manual", "gpt-5.6-sol-max", "strict", highSecurityRisk()), "api");

        assertEquals("READY_FOR_TASK_DECOMPOSITION", result.status());
        assertEquals("CONFIGURED", result.configurationStatus());
        assertEquals("gpt-5.6-sol-max", result.resolvedModel());
        assertEquals("api", result.selection().selectionSource());
        assertTrue(result.selection().lockedByUser());
        assertEquals("DEFERRED_NOT_RUN", result.cost().status());
        assertEquals("1.25", configured.catalog().models().getFirst().pricing().inputPerMillion());
        assertEquals("2026-08-24T01:59:30Z", configured.catalog().models().getFirst().pricing().effectiveAt());
        assertEquals("NOT_RUN", result.dag().status());
        assertEquals("NOT_RUN", result.evidence().providerInvocation());
        assertEquals("NOT_RUN", result.evidence().workspaceMutation());
        assertEquals("NOT_CERTIFIED", result.evidence().certification());
    }

    @Test
    void partialAndStaleProfilesRemainNotConfigured() {
        Instant now = Instant.parse("2026-08-24T02:00:00Z");
        var stale = new OperatorRuntimeProfile(
                "operator/gpt-5.6-sol-max",
                "deployment/openai-primary",
                "gpt-5.6-sol-2026-08-20",
                "provider-gateway/openai-v3",
                now.minusSeconds(600),
                now.minusSeconds(600),
                60,
                true,
                true,
                new BigDecimal("1.250000000000000001"),
                BigDecimal.ZERO,
                new BigDecimal("5.00"),
                200_000,
                16_000,
                2,
                1_000_000L,
                0,
                Set.of("us"),
                "privacy/private-repository-v1",
                true,
                Set.of("repository_task_execution", "architect_verifier"));
        var serviceWithStaleProfile = new RepositoryTaskRouterService(
                Map.of("gpt-5.6-sol-max", stale),
                Clock.fixed(now, ZoneOffset.UTC));

        var descriptor = serviceWithStaleProfile.catalog().models().getFirst();
        assertEquals("NOT_CONFIGURED", descriptor.status());
        assertFalse(descriptor.selectable());
        assertEquals("1.250000000000000001", descriptor.pricing().inputPerMillion());
        assertTrue(descriptor.reasons().contains("LIVE_OBSERVATION_STALE_OR_UNSET"));
        assertTrue(descriptor.reasons().contains("PRICING_EFFECTIVE_AT_STALE_OR_UNSET"));

        var partial = new OperatorRuntimeProfile(
                "operator/gpt-5.6-sol-max",
                null,
                null,
                null,
                null,
                null,
                null,
                true,
                true,
                BigDecimal.ONE,
                BigDecimal.ZERO,
                BigDecimal.ONE,
                100,
                10,
                1,
                null,
                null,
                Set.of(),
                null,
                null,
                Set.of());
        var partialDescriptor = new RepositoryTaskRouterService(Map.of("gpt-5.6-sol-max", partial))
                .catalog().models().getFirst();
        assertEquals("NOT_CONFIGURED", partialDescriptor.status());
        assertTrue(partialDescriptor.reasons().contains("DEPLOYMENT_ID_UNSET"));
        assertTrue(partialDescriptor.reasons().contains("CANONICAL_PROVIDER_GATEWAY_ADAPTER_UNSET"));
        assertTrue(partialDescriptor.reasons().contains("REQUIRED_CAPABILITIES_UNSET"));
    }

    private static JsonNode request(String mode, String selectedModel,
                                    String fallback, String riskJson) throws Exception {
        return JSON.readTree(requestJson(mode, selectedModel, fallback, riskJson));
    }

    private static String requestJson(String mode, String selectedModel,
                                      String fallback, String riskJson) {
        String selected = selectedModel == null ? "null" : "\"" + selectedModel + "\"";
        String fallbackValue = fallback == null ? "null" : "\"" + fallback + "\"";
        return """
                {
                  "schemaVersion": "1.0",
                  "catalogVersion": "repository-model-catalog-v1.1.0",
                  "selectionVersion": "repository-model-selection-v1",
                  "mode": "%s",
                  "selectedModel": %s,
                  "optimizationProfile": "cost_performance",
                  "fallbackPolicy": %s,
                  "verificationPolicy": "system_required_verifiers",
                  "risk": %s
                }
                """.formatted(mode, selected, fallbackValue, riskJson);
    }

    private static String lowRisk() {
        return """
                {
                  "security": "low",
                  "dataMigration": "low",
                  "concurrency": "low",
                  "publicContract": "low",
                  "blastRadius": "low",
                  "longHorizon": false
                }
                """;
    }

    private static String highSecurityRisk() {
        return """
                {
                  "security": "high",
                  "dataMigration": "low",
                  "concurrency": "low",
                  "publicContract": "low",
                  "blastRadius": "low",
                  "longHorizon": false
                }
                """;
    }
}
