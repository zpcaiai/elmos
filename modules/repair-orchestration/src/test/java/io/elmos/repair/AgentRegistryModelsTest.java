package io.elmos.repair;

import io.elmos.repair.AgentRegistryModels.AgentDefinition;
import io.elmos.repair.AgentRegistryModels.AgentLimits;
import io.elmos.repair.AgentRegistryModels.AgentRegistryException;
import io.elmos.repair.AgentRegistryModels.AuditEvent;
import io.elmos.repair.AgentRegistryModels.InvocationResult;
import io.elmos.repair.AgentRegistryModels.LayerUpdate;
import io.elmos.repair.AgentRegistryModels.MutationResult;
import io.elmos.repair.AgentRegistryModels.RegistryMetrics;
import io.elmos.repair.AgentRegistryModels.RegistryView;
import io.elmos.repair.AgentRegistryModels.ResolvedAgent;
import io.elmos.repair.AgentRegistryModels.SelectionDecision;
import io.elmos.repair.AgentRegistryModels.SelectionPermit;
import io.elmos.repair.AgentRegistryModels.SelectionRequest;
import io.elmos.repair.AgentRegistryModels.Source;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AgentRegistryModelsTest {
    private static final String DIGEST = "0".repeat(64);
    private static final Instant NOW = Instant.parse("2026-08-28T00:00:00Z");
    private static final AgentLimits LIMITS = new AgentLimits(1, 1, 0, 1);

    @Test
    void rejectsEveryOutOfRangeLimit() {
        assertCode("AGENT_LIMITS_INVALID", () -> new AgentLimits(0, 1, 0, 1));
        assertCode("AGENT_LIMITS_INVALID", () -> new AgentLimits(10_001, 1, 0, 1));
        assertCode("AGENT_LIMITS_INVALID", () -> new AgentLimits(1, 0, 0, 1));
        assertCode("AGENT_LIMITS_INVALID", () -> new AgentLimits(1, 100_000_001, 0, 1));
        assertCode("AGENT_LIMITS_INVALID", () -> new AgentLimits(1, 1, -1, 1));
        assertCode("AGENT_LIMITS_INVALID", () -> new AgentLimits(1, 1, 10_000_000_000_001L, 1));
        assertCode("AGENT_LIMITS_INVALID", () -> new AgentLimits(1, 1, 0, 0));
        assertCode("AGENT_LIMITS_INVALID", () -> new AgentLimits(1, 1, 0, 86_400_001));
    }

    @Test
    void rejectsMalformedAgentFieldsAndBoundedCollections() {
        assertCode("REGISTRY_DECLARATION_INVALID", () -> agent("Uppercase", Set.of(), Map.of(), 1));
        assertCode("REGISTRY_TEXT_INVALID", () -> definition("agent", " ", "mode", "model", "prompt",
                Set.of(), Set.of(), Map.of(), LIMITS, 1));
        assertCode("REGISTRY_TEXT_INVALID", () -> definition("agent", "description", "mode", "model", "x\0",
                Set.of(), Set.of(), Map.of(), LIMITS, 1));
        assertCode("REGISTRY_TEXT_INVALID", () -> definition(
                "agent", "description", "mode", "model", "x\u007f",
                Set.of(), Set.of(), Map.of(), LIMITS, 1));
        assertCode("AGENT_VERSION_INVALID", () -> agent("agent", Set.of(), Map.of(), 0));
        assertThrows(NullPointerException.class, () -> definition(
                "agent", "description", "mode", "model", "prompt",
                null, Set.of(), Map.of(), LIMITS, 1));
        assertThrows(NullPointerException.class, () -> definition(
                "agent", "description", "mode", "model", "prompt",
                Set.of(), null, Map.of(), LIMITS, 1));
        assertThrows(NullPointerException.class, () -> definition(
                "agent", "description", "mode", "model", "prompt",
                Set.of(), Set.of(), null, LIMITS, 1));
        assertThrows(NullPointerException.class, () -> definition(
                "agent", "description", "mode", "model", "prompt",
                Set.of(), Set.of(), Map.of(), null, 1));

        Set<String> oversized = java.util.stream.IntStream.range(0, 129)
                .mapToObj(index -> "permission-" + index).collect(java.util.stream.Collectors.toSet());
        assertCode("REGISTRY_COLLECTION_LIMIT_EXCEEDED", () -> agent("agent", oversized, Map.of(), 1));
        assertCode("REGISTRY_DECLARATION_INVALID", () -> agent("agent", Set.of("BAD"), Map.of(), 1));

        Map<String, Boolean> tooManyFlags = new HashMap<>();
        for (int index = 0; index < 65; index++) tooManyFlags.put("flag-" + index, true);
        assertCode("REGISTRY_COLLECTION_LIMIT_EXCEEDED", () -> agent("agent", Set.of(), tooManyFlags, 1));
        Map<String, Boolean> nullFlag = new HashMap<>();
        nullFlag.put("flag", null);
        assertThrows(NullPointerException.class, () -> agent("agent", Set.of(), nullFlag, 1));
    }

    @Test
    void rejectsMalformedRequestsAndDuplicateAgentDeclarations() {
        AgentDefinition agent = agent("agent", Set.of(), Map.of(), 1);
        assertCode("CONTEXT_EPOCH_INVALID", () -> new LayerUpdate(
                "tenant", "project", Source.GLOBAL, -1, "actor", Set.of(), "key", List.of()));
        assertThrows(NullPointerException.class, () -> new LayerUpdate(
                "tenant", "project", null, 0, "actor", Set.of(), "key", List.of()));
        assertCode("AGENT_ID_DUPLICATE", () -> new LayerUpdate(
                "tenant", "project", Source.GLOBAL, 0, "actor", Set.of(), "key", List.of(agent, agent)));
        List<AgentDefinition> tooMany = new ArrayList<>();
        for (int index = 0; index < 257; index++) {
            tooMany.add(agent("agent-" + index, Set.of(), Map.of(), 1));
        }
        assertCode("REGISTRY_COLLECTION_LIMIT_EXCEEDED", () -> new LayerUpdate(
                "tenant", "project", Source.GLOBAL, 0, "actor", Set.of(), "key", tooMany));
        assertThrows(NullPointerException.class, () -> new LayerUpdate(
                "tenant", "project", Source.GLOBAL, 0, "actor", Set.of(), "key",
                java.util.Arrays.asList((AgentDefinition) null)));

        assertCode("CONTEXT_EPOCH_INVALID", () -> new SelectionRequest(
                "tenant", "project", "agent", -1, "actor", Set.of(), Set.of(), Set.of(), "key"));
    }

    @Test
    void rejectsInvalidMetricsAndResultContracts() {
        assertCode("REGISTRY_METRICS_INVALID", () -> new RegistryMetrics(-1, 0, 0, 0, 0, Map.of()));
        assertCode("REGISTRY_METRICS_INVALID", () -> new RegistryMetrics(0, -1, 0, 0, 0, Map.of()));
        assertCode("REGISTRY_METRICS_INVALID", () -> new RegistryMetrics(0, 0, -1, 0, 0, Map.of()));
        assertCode("REGISTRY_METRICS_INVALID", () -> new RegistryMetrics(0, 0, 0, -1, 0, Map.of()));
        assertCode("REGISTRY_METRICS_INVALID", () -> new RegistryMetrics(0, 0, 0, 0, -1, Map.of()));
        assertCode("REGISTRY_IDENTIFIER_INVALID", () -> new RegistryMetrics(0, 0, 0, 0, 0, Map.of("bad key", 1L)));
        Map<String, Long> nullFailure = new HashMap<>();
        nullFailure.put("FAILURE", null);
        assertCode("REGISTRY_METRICS_INVALID", () -> new RegistryMetrics(0, 0, 0, 0, 0, nullFailure));
        assertCode("REGISTRY_METRICS_INVALID", () -> new RegistryMetrics(0, 0, 0, 0, 0, Map.of("FAILURE", -1L)));

        RegistryMetrics metrics = new RegistryMetrics(0, 0, 0, 0, 0, Map.of());
        assertCode("CONTEXT_EPOCH_INVALID", () -> new RegistryView(
                "schema", "capability", "tenant", "project", -1, DIGEST, List.of(), metrics));
        assertCode("CONTEXT_EPOCH_INVALID", () -> new MutationResult("updated", -1, DIGEST, false));
    }

    @Test
    void rejectsInvalidPermitDecisionInvocationAndAuditContracts() {
        assertCode("AGENT_VERSION_INVALID", () -> permit(0, 0, NOW.plusSeconds(1)));
        assertCode("CONTEXT_EPOCH_INVALID", () -> permit(1, -1, NOW.plusSeconds(1)));
        assertCode("AGENT_PERMIT_EXPIRY_INVALID", () -> permit(1, 0, NOW));
        SelectionPermit permit = permit(1, 0, NOW.plusSeconds(1));
        assertCode("CONTEXT_EPOCH_INVALID", () -> new SelectionDecision(
                "allowed", "OK", -1, DIGEST, permit, false));
        assertCode("SELECTION_DECISION_INVALID", () -> new SelectionDecision(
                "allowed", "OK", 0, DIGEST, null, false));
        assertCode("SELECTION_DECISION_INVALID", () -> new SelectionDecision(
                "denied", "DENIED", 0, DIGEST, permit, false));
        assertThrows(NullPointerException.class, () -> new InvocationResult<>(null, "value"));
        assertThrows(NullPointerException.class, () -> new InvocationResult<>(permit, null));
        assertCode("AUDIT_SEQUENCE_INVALID", () -> new AuditEvent(
                0, NOW, "actor", "operation", "OK", DIGEST, DIGEST, 0));
        assertCode("CONTEXT_EPOCH_INVALID", () -> new AuditEvent(
                1, NOW, "actor", "operation", "OK", DIGEST, DIGEST, -1));
    }

    @Test
    void helperValidationFailsClosedAndResolvedAgentRequiresBothValues() {
        assertCode("REGISTRY_IDENTIFIER_INVALID", () -> AgentRegistryModels.identifier(null, "value"));
        assertCode("REGISTRY_IDENTIFIER_INVALID", () -> AgentRegistryModels.identifier("bad value", "value"));
        assertCode("REGISTRY_DECLARATION_INVALID", () -> AgentRegistryModels.declarationName(null, "value"));
        assertCode("REGISTRY_TEXT_INVALID", () -> AgentRegistryModels.boundedText(null, "value", 2));
        assertCode("REGISTRY_TEXT_INVALID", () -> AgentRegistryModels.boundedText("toolong", "value", 2));
        assertCode("REGISTRY_DIGEST_INVALID", () -> AgentRegistryModels.digest(null, "value"));
        assertCode("REGISTRY_DIGEST_INVALID", () -> AgentRegistryModels.digest("BAD", "value"));
        assertThrows(NullPointerException.class, () -> new ResolvedAgent(null, Source.GLOBAL));
        assertThrows(NullPointerException.class, () -> new ResolvedAgent(
                agent("agent", Set.of(), Map.of(), 1), null));
        assertThrows(AgentRegistryException.class, () -> new AgentRegistryException("bad code", "message"));
        assertTrue(Source.MANAGED.precedence() > Source.PROJECT.precedence());
    }

    private static SelectionPermit permit(long agentVersion, long contextEpoch, Instant expiresAt) {
        return new SelectionPermit(
                "tenant", "project", "actor", "agent", Source.GLOBAL,
                agentVersion, contextEpoch, Set.of(), Set.of(), LIMITS,
                NOW, expiresAt, DIGEST, DIGEST);
    }

    private static AgentDefinition agent(
            String id,
            Set<String> permissions,
            Map<String, Boolean> flags,
            long version
    ) {
        return definition(
                id, "description", "mode", "model", "prompt",
                permissions, Set.of(), flags, LIMITS, version);
    }

    private static AgentDefinition definition(
            String id,
            String description,
            String mode,
            String model,
            String prompt,
            Set<String> permissions,
            Set<String> capabilities,
            Map<String, Boolean> flags,
            AgentLimits limits,
            long version
    ) {
        return new AgentDefinition(
                id, description, mode, model, prompt,
                permissions, capabilities, flags, limits, version, true);
    }

    private static void assertCode(String expected, Runnable operation) {
        assertEquals(expected, assertThrows(AgentRegistryException.class, operation::run).code());
    }
}
