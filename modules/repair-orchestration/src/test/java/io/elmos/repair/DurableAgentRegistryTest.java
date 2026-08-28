package io.elmos.repair;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import io.elmos.repair.AgentRegistryModels.AgentDefinition;
import io.elmos.repair.AgentRegistryModels.AgentLimits;
import io.elmos.repair.AgentRegistryModels.AgentRegistryException;
import io.elmos.repair.AgentRegistryModels.LayerUpdate;
import io.elmos.repair.AgentRegistryModels.SelectionRequest;
import io.elmos.repair.AgentRegistryModels.Source;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.HexFormat;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DurableAgentRegistryTest {
    private static final Set<String> ADMIN = Set.of(
            "agent-registry:read",
            "agent-registry:write",
            "agent-registry:managed",
            "agent-registry:audit",
            "agent-registry:select",
            "tool:read");
    private static final Instant NOW = Instant.parse("2026-08-28T00:00:00Z");

    @TempDir
    Path temporary;

    @Test
    void mergesGlobalProjectAndManagedWithExactPrecedenceAndDurableEpoch() {
        Path root = temporary.resolve("registry").toAbsolutePath();
        DurableAgentRegistry registry = registry(root);

        var global = registry.replaceLayer(update(
                Source.GLOBAL, 0, "global-1", List.of(
                        agent("reviewer", "global-model", 1, true),
                        agent("global-only", "global-model", 1, true))));
        assertEquals(1, global.contextEpoch());

        var project = registry.replaceLayer(update(
                Source.PROJECT, 1, "project-1", List.of(
                        agent("reviewer", "project-model", 2, true),
                        agent("project-only", "project-model", 1, true))));
        assertEquals(2, project.contextEpoch());

        var managed = registry.replaceLayer(update(
                Source.MANAGED, 2, "managed-1", List.of(
                        agent("reviewer", "managed-model", 3, false))));
        assertEquals(3, managed.contextEpoch());

        var view = registry.view("tenant-a", "project-a", ADMIN);
        assertEquals(3, view.contextEpoch());
        assertEquals(List.of("global-only", "project-only", "reviewer"),
                view.agents().stream().map(value -> value.definition().id()).toList());
        var reviewer = view.agents().stream()
                .filter(value -> value.definition().id().equals("reviewer"))
                .findFirst().orElseThrow();
        assertEquals(Source.MANAGED, reviewer.source());
        assertEquals("managed-model", reviewer.definition().model());
        assertFalse(reviewer.definition().enabled());

        var afterRestart = registry(root).view("tenant-a", "project-a", ADMIN);
        assertEquals(view.contextEpoch(), afterRestart.contextEpoch());
        assertEquals(view.registryDigest(), afterRestart.registryDigest());
        assertEquals(view.agents(), afterRestart.agents());
    }

    @Test
    void configurationIsIdempotentAcrossRestartAndConflictsFailClosed() {
        Path root = temporary.resolve("registry").toAbsolutePath();
        LayerUpdate request = update(
                Source.GLOBAL, 0, "configuration-1", List.of(agent("reviewer", "model-a", 1, true)));
        var first = registry(root).replaceLayer(request);
        var replay = registry(root).replaceLayer(request);

        assertEquals(1, first.contextEpoch());
        assertTrue(replay.idempotentReplay());
        assertEquals(first.registryDigest(), replay.registryDigest());

        LayerUpdate conflict = update(
                Source.GLOBAL, 0, "configuration-1", List.of(agent("reviewer", "model-b", 2, true)));
        AgentRegistryException conflictError = assertThrows(
                AgentRegistryException.class, () -> registry(root).replaceLayer(conflict));
        assertEquals("IDEMPOTENCY_KEY_CONFLICT", conflictError.code());

        LayerUpdate noChange = update(
                Source.GLOBAL, 1, "configuration-2", List.of(agent("reviewer", "model-a", 1, true)));
        var unchanged = registry(root).replaceLayer(noChange);
        assertEquals("unchanged", unchanged.status());
        assertEquals(1, unchanged.contextEpoch());
        assertEquals(1, registry(root).view("tenant-a", "project-a", ADMIN)
                .metrics().configurationReplays());
    }

    @Test
    void permissionAndCapabilityDenialsOccurBeforeHandlerInvocation() {
        DurableAgentRegistry registry = registry(temporary.resolve("registry").toAbsolutePath());
        registry.replaceLayer(update(
                Source.GLOBAL, 0, "configuration-1", List.of(agent("reviewer", "model-a", 1, true))));
        AtomicBoolean invoked = new AtomicBoolean(false);

        var missingSelectorPermission = registry.select(selection(
                1, "selection-1", Set.of("tool:read"), Set.of("tool:read"), Set.of("code:review")));
        assertFalse(missingSelectorPermission.allowed());
        assertEquals("AGENT_REGISTRY_SELECT_REQUIRED", missingSelectorPermission.reasonCode());
        assertThrows(AgentRegistryException.class, () -> registry.invokeSelected(
                missingSelectorPermission, ignored -> invoked.getAndSet(true)));
        assertFalse(invoked.get());

        var undeclaredCapability = registry.select(selection(
                1, "selection-2", ADMIN, Set.of("tool:read"), Set.of("code:write")));
        assertFalse(undeclaredCapability.allowed());
        assertEquals("AGENT_CAPABILITY_UNAVAILABLE", undeclaredCapability.reasonCode());
        assertThrows(AgentRegistryException.class, () -> registry.invokeSelected(
                undeclaredCapability, ignored -> invoked.getAndSet(true)));
        assertFalse(invoked.get());

        var allowed = registry.select(selection(
                1, "selection-3", ADMIN, Set.of("tool:read"), Set.of("code:review")));
        assertTrue(allowed.allowed());
        var invokedResult = registry.invokeSelected(allowed, ignored -> {
            invoked.set(true);
            return "handler-result";
        });
        assertTrue(invoked.get());
        assertEquals("handler-result", invokedResult.value());
        assertEquals(1, registry.view("tenant-a", "project-a", ADMIN).metrics().allowedSelections());
        assertEquals(2, registry.view("tenant-a", "project-a", ADMIN).metrics().deniedSelections());
    }

    @Test
    void contextChangeAndExpiryFenceOldSelectionPermits() {
        Path root = temporary.resolve("registry").toAbsolutePath();
        MutableClock clock = new MutableClock(NOW);
        DurableAgentRegistry registry = new DurableAgentRegistry(root, clock);
        registry.replaceLayer(update(
                Source.GLOBAL, 0, "configuration-1", List.of(agent("reviewer", "model-a", 1, true))));
        SelectionRequest selection = selection(
                1, "selection-1", ADMIN, Set.of("tool:read"), Set.of("code:review"));
        var initial = registry.select(selection);
        assertTrue(initial.allowed());

        registry.replaceLayer(update(
                Source.MANAGED, 1, "configuration-2", List.of(agent("reviewer", "model-b", 2, false))));
        AtomicBoolean staleInvoked = new AtomicBoolean(false);
        AgentRegistryException stalePermit = assertThrows(
                AgentRegistryException.class,
                () -> registry.invokeSelected(initial, ignored -> staleInvoked.getAndSet(true)));
        assertEquals("CONTEXT_EPOCH_STALE", stalePermit.code());
        assertFalse(staleInvoked.get());
        var staleReplay = registry.select(selection);
        assertFalse(staleReplay.allowed());
        assertTrue(staleReplay.idempotentReplay());
        assertEquals("CONTEXT_EPOCH_STALE", staleReplay.reasonCode());

        var disabled = registry.select(selection(
                2, "selection-2", ADMIN, Set.of("tool:read"), Set.of("code:review")));
        assertFalse(disabled.allowed());
        assertEquals("AGENT_DISABLED", disabled.reasonCode());

        DurableAgentRegistry expiringRegistry = new DurableAgentRegistry(
                temporary.resolve("expiring").toAbsolutePath(), clock);
        expiringRegistry.replaceLayer(update(
                Source.GLOBAL, 0, "configuration-3", List.of(agent("reviewer", "model-a", 1, true))));
        SelectionRequest expiringSelection = selection(
                1, "selection-3", ADMIN, Set.of("tool:read"), Set.of("code:review"));
        var permit = expiringRegistry.select(expiringSelection);
        clock.advanceMillis(60_001);
        var expiredReplay = expiringRegistry.select(expiringSelection);
        assertFalse(expiredReplay.allowed());
        assertEquals("AGENT_SELECTION_PERMIT_EXPIRED", expiredReplay.reasonCode());
        assertThrows(AgentRegistryException.class, () -> expiringRegistry.invokeSelected(
                permit, ignored -> "must-not-run"));
    }

    @Test
    void tenantAndProjectScopesNeverLeakDefinitions() {
        DurableAgentRegistry registry = registry(temporary.resolve("registry").toAbsolutePath());
        registry.replaceLayer(update(
                Source.GLOBAL, 0, "configuration-1", List.of(agent("reviewer", "model-a", 1, true))));

        var otherProject = registry.view("tenant-a", "project-b", ADMIN);
        var otherTenant = registry.view("tenant-b", "project-a", ADMIN);
        assertTrue(otherProject.agents().isEmpty());
        assertTrue(otherTenant.agents().isEmpty());
        assertNotEquals(
                registry.view("tenant-a", "project-a", ADMIN).registryDigest(),
                otherProject.registryDigest());
    }

    @Test
    void concurrentCompareAndSetProducesOneWinnerWithoutLostUpdate() throws Exception {
        Path root = temporary.resolve("registry").toAbsolutePath();
        DurableAgentRegistry first = registry(root);
        DurableAgentRegistry second = registry(root);
        CountDownLatch start = new CountDownLatch(1);

        try (var executor = Executors.newFixedThreadPool(2)) {
            var left = executor.submit(() -> runConcurrent(
                    start, first, update(Source.GLOBAL, 0, "left", List.of(agent("left", "model-a", 1, true)))));
            var right = executor.submit(() -> runConcurrent(
                    start, second, update(Source.GLOBAL, 0, "right", List.of(agent("right", "model-b", 1, true)))));
            start.countDown();
            List<String> outcomes = List.of(left.get(10, TimeUnit.SECONDS), right.get(10, TimeUnit.SECONDS));
            assertEquals(1, outcomes.stream().filter("updated"::equals).count());
            assertEquals(1, outcomes.stream().filter("CONTEXT_EPOCH_STALE"::equals).count());
        }

        var view = registry(root).view("tenant-a", "project-a", ADMIN);
        assertEquals(1, view.contextEpoch());
        assertEquals(1, view.agents().size());
    }

    @Test
    void digestTamperAndSymlinkRootFailClosed() throws IOException {
        Path root = temporary.resolve("registry").toAbsolutePath();
        DurableAgentRegistry registry = registry(root);
        registry.replaceLayer(update(
                Source.GLOBAL, 0, "configuration-1", List.of(agent("reviewer", "model-a", 1, true))));
        Path state;
        try (var paths = Files.walk(root)) {
            state = paths.filter(path -> path.getFileName().toString().equals("registry.json"))
                    .findFirst().orElseThrow();
        }
        String original = Files.readString(state);
        assertTrue(original.contains("Global reviewer"));
        Files.writeString(
                state,
                original.replace("Global reviewer", "Forged reviewer"),
                StandardOpenOption.TRUNCATE_EXISTING);
        AgentRegistryException tampered = assertThrows(
                AgentRegistryException.class,
                () -> registry(root).view("tenant-a", "project-a", ADMIN));
        assertEquals("REGISTRY_STATE_TAMPERED", tampered.code());

        Path real = temporary.resolve("real-root");
        Files.createDirectory(real);
        Path link = temporary.resolve("linked-root");
        try {
            Files.createSymbolicLink(link, real);
        } catch (UnsupportedOperationException error) {
            return;
        }
        AgentRegistryException symlink = assertThrows(
                AgentRegistryException.class,
                () -> new DurableAgentRegistry(link.toAbsolutePath()));
        assertEquals("REGISTRY_ROOT_INVALID", symlink.code());
    }

    @Test
    void publishesBoundedLocalCapabilityWithoutClaimingExternalCertification() {
        var capability = registry(temporary.resolve("registry").toAbsolutePath()).capability();
        assertEquals("agent-registry", capability.skillName());
        assertEquals("LOCAL_RUNTIME_IMPLEMENTED", capability.implementationState());
        assertTrue(capability.supportedOperations().containsAll(Set.of(
                "replace-layer", "select", "invoke-selected", "view", "audit", "capability")));
        assertFalse(capability.sideEffectsAuthorized());
        assertEquals("NOT_RUN", capability.externalEvidenceStatus());
        assertEquals("NOT_CERTIFIED", capability.certification());

        try (var binding = DurableAgentRegistry.class.getResourceAsStream(
                "/META-INF/elmos/agent-registry-runtime.json")) {
            assertTrue(binding != null, "Agent Registry runtime binding must be packaged on the classpath");
            Map<String, Object> document = new ObjectMapper().readValue(
                    binding, new TypeReference<>() {});
            assertEquals("io.elmos.repair.DurableAgentRegistry", document.get("runtime_class"));
            assertEquals("LOCAL_RUNTIME_IMPLEMENTED", document.get("binding_state"));
            assertEquals(
                    "sha256:237ef61c498f6d4c5a2dc9737121ebc66789dd0127f464bf661c8ae77314316e",
                    document.get("source_skill_sha256"));
            assertEquals(false, document.get("side_effects_authorized"));
            assertEquals("NOT_RUN", document.get("external_evidence_status"));
            assertEquals("NOT_CERTIFIED", document.get("certification"));
        } catch (IOException error) {
            throw new AssertionError("Agent Registry runtime binding must be valid JSON", error);
        }
    }

    @Test
    void enforcesAdministrativePermissionsAndEverySelectionDenialPath() {
        Path root = temporary.resolve("registry").toAbsolutePath();
        DurableAgentRegistry registry = new DurableAgentRegistry(root);
        LayerUpdate configuration = update(
                Source.GLOBAL, 0, "configuration-1", List.of(agent("reviewer", "model-a", 1, true)));

        assertCode("AGENT_REGISTRY_WRITE_REQUIRED", () -> registry.replaceLayer(new LayerUpdate(
                "tenant-a", "project-a", Source.GLOBAL, 0, "actor", Set.of(), "denied-write", List.of())));
        assertCode("AGENT_REGISTRY_MANAGED_REQUIRED", () -> registry.replaceLayer(new LayerUpdate(
                "tenant-a", "project-a", Source.MANAGED, 0, "actor",
                Set.of("agent-registry:write"), "denied-managed", List.of())));
        registry.replaceLayer(configuration);
        assertCode("AGENT_REGISTRY_READ_REQUIRED", () -> registry.view(
                "tenant-a", "project-a", Set.of()));
        assertCode("AGENT_REGISTRY_AUDIT_REQUIRED", () -> registry.audit(
                "tenant-a", "project-a", Set.of()));

        SelectionRequest staleRequest = selection(0, "stale", ADMIN, Set.of(), Set.of());
        assertEquals("CONTEXT_EPOCH_STALE", registry.select(staleRequest).reasonCode());
        var staleReplay = registry.select(staleRequest);
        assertEquals("CONTEXT_EPOCH_STALE", staleReplay.reasonCode());
        assertTrue(staleReplay.idempotentReplay());
        assertEquals("AGENT_NOT_FOUND", registry.select(new SelectionRequest(
                "tenant-a", "project-a", "missing", 1, "developer-a", ADMIN,
                Set.of(), Set.of(), "missing-agent")).reasonCode());
        assertEquals("AGENT_PERMISSION_NOT_DECLARED", registry.select(selection(
                1, "undeclared-permission", ADMIN, Set.of("tool:write"), Set.of())).reasonCode());
        assertEquals("ACTOR_PERMISSION_DENIED", registry.select(selection(
                1, "actor-denied", Set.of("agent-registry:select"), Set.of("tool:read"), Set.of())).reasonCode());

        SelectionRequest allowedRequest = selection(
                1, "allowed-replay", ADMIN, Set.of("tool:read"), Set.of("code:review"));
        var allowed = registry.select(allowedRequest);
        var replay = registry.select(allowedRequest);
        assertTrue(allowed.allowed());
        assertTrue(replay.allowed());
        assertTrue(replay.idempotentReplay());
        assertCode("IDEMPOTENCY_KEY_CONFLICT", () -> registry.select(selection(
                1, "allowed-replay", ADMIN, Set.of(), Set.of())));

        List<AgentRegistryModels.AuditEvent> audit = registry.audit("tenant-a", "project-a", ADMIN);
        assertEquals(6, audit.size());
        for (int index = 0; index < audit.size(); index++) assertEquals(index + 1L, audit.get(index).sequence());
    }

    @Test
    void rejectsInconsistentAndForgedPermitsBeforeAdmissionCallback() {
        DurableAgentRegistry registry = registry(temporary.resolve("registry").toAbsolutePath());
        registry.replaceLayer(update(
                Source.GLOBAL, 0, "configuration-1", List.of(agent("reviewer", "model-a", 1, true))));
        var allowed = registry.select(selection(
                1, "selection-1", ADMIN, Set.of("tool:read"), Set.of("code:review")));
        var permit = allowed.permit();
        AtomicBoolean invoked = new AtomicBoolean(false);

        var inconsistent = new AgentRegistryModels.SelectionDecision(
                "allowed", "AGENT_SELECTION_ALLOWED", allowed.contextEpoch(), "f".repeat(64), permit, false);
        assertCode("AGENT_SELECTION_PERMIT_INVALID", () -> registry.invokeSelected(
                inconsistent, ignored -> invoked.getAndSet(true)));
        assertFalse(invoked.get());

        var forgedPermit = new AgentRegistryModels.SelectionPermit(
                permit.tenantId(), permit.projectId(), permit.actorId(), permit.agentId(), permit.source(),
                permit.agentVersion(), permit.contextEpoch(), permit.permissions(), permit.capabilities(),
                permit.limits(), permit.issuedAt(), permit.expiresAt(), permit.registryDigest(), "0".repeat(64));
        var forged = new AgentRegistryModels.SelectionDecision(
                "allowed", "AGENT_SELECTION_ALLOWED", allowed.contextEpoch(),
                allowed.registryDigest(), forgedPermit, false);
        assertCode("AGENT_SELECTION_PERMIT_INVALID", () -> registry.invokeSelected(
                forged, ignored -> invoked.getAndSet(true)));
        assertFalse(invoked.get());
        assertThrows(NullPointerException.class, () -> registry.invokeSelected(allowed, ignored -> null));
    }

    @Test
    void revalidatesEverySignedPermitFieldAgainstCurrentRegistry() {
        DurableAgentRegistry registry = registry(temporary.resolve("registry").toAbsolutePath());
        AgentDefinition reviewer = agent("reviewer", "model-a", 1, true);
        AgentDefinition disabled = agent("disabled", "model-a", 1, false);
        registry.replaceLayer(update(
                Source.GLOBAL, 0, "configuration-1", List.of(reviewer, disabled)));
        var selected = registry.select(selection(
                1, "selection-1", ADMIN, Set.of("tool:read"), Set.of("code:review")));
        var permit = selected.permit();
        AtomicBoolean invoked = new AtomicBoolean(false);

        var wrongDecisionEpoch = new AgentRegistryModels.SelectionDecision(
                "allowed", "AGENT_SELECTION_ALLOWED", permit.contextEpoch() + 1,
                permit.registryDigest(), permit, false);
        assertCode("AGENT_SELECTION_PERMIT_INVALID", () -> registry.invokeSelected(
                wrongDecisionEpoch, ignored -> invoked.getAndSet(true)));

        assertStale(registry, selected, signedPermit(
                permit, permit.agentId(), permit.source(), permit.agentVersion(), permit.permissions(),
                permit.capabilities(), permit.limits(), "f".repeat(64)), "CONTEXT_EPOCH_STALE", invoked);
        assertStale(registry, selected, signedPermit(
                permit, "missing", permit.source(), permit.agentVersion(), permit.permissions(),
                permit.capabilities(), permit.limits(), permit.registryDigest()),
                "AGENT_SELECTION_PERMIT_UNRECOGNIZED", invoked);
        assertStale(registry, selected, signedPermit(
                permit, "disabled", permit.source(), permit.agentVersion(), permit.permissions(),
                permit.capabilities(), permit.limits(), permit.registryDigest()),
                "AGENT_SELECTION_PERMIT_UNRECOGNIZED", invoked);
        assertStale(registry, selected, signedPermit(
                permit, permit.agentId(), Source.PROJECT, permit.agentVersion(), permit.permissions(),
                permit.capabilities(), permit.limits(), permit.registryDigest()),
                "AGENT_SELECTION_PERMIT_UNRECOGNIZED", invoked);
        assertStale(registry, selected, signedPermit(
                permit, permit.agentId(), permit.source(), permit.agentVersion() + 1, permit.permissions(),
                permit.capabilities(), permit.limits(), permit.registryDigest()),
                "AGENT_SELECTION_PERMIT_UNRECOGNIZED", invoked);
        assertStale(registry, selected, signedPermit(
                permit, permit.agentId(), permit.source(), permit.agentVersion(), Set.of("tool:write"),
                permit.capabilities(), permit.limits(), permit.registryDigest()),
                "AGENT_SELECTION_PERMIT_UNRECOGNIZED", invoked);
        assertStale(registry, selected, signedPermit(
                permit, permit.agentId(), permit.source(), permit.agentVersion(), permit.permissions(),
                Set.of("code:write"), permit.limits(), permit.registryDigest()),
                "AGENT_SELECTION_PERMIT_UNRECOGNIZED", invoked);
        assertStale(registry, selected, signedPermit(
                permit, permit.agentId(), permit.source(), permit.agentVersion(), permit.permissions(),
                permit.capabilities(), new AgentLimits(2, 2, 0, 2), permit.registryDigest()),
                "AGENT_SELECTION_PERMIT_UNRECOGNIZED", invoked);
        assertFalse(invoked.get());
    }

    @Test
    void rejectsSemanticallyForgedPermitsEvenWhenLocalReceiptEnvelopeIsRecomputed() throws IOException {
        assertPersistedSemanticForgeryRejected(
                "receipt-missing-agent", "missing", Source.GLOBAL, 1,
                Set.of("tool:read"), Set.of("code:review"), new AgentLimits(20, 100_000, 5_000_000, 60_000));
        assertPersistedSemanticForgeryRejected(
                "receipt-disabled-agent", "disabled", Source.GLOBAL, 1,
                Set.of("tool:read"), Set.of("code:review"), new AgentLimits(20, 100_000, 5_000_000, 60_000));
        assertPersistedSemanticForgeryRejected(
                "receipt-source", "reviewer", Source.PROJECT, 1,
                Set.of("tool:read"), Set.of("code:review"), new AgentLimits(20, 100_000, 5_000_000, 60_000));
        assertPersistedSemanticForgeryRejected(
                "receipt-version", "reviewer", Source.GLOBAL, 2,
                Set.of("tool:read"), Set.of("code:review"), new AgentLimits(20, 100_000, 5_000_000, 60_000));
        assertPersistedSemanticForgeryRejected(
                "receipt-permission", "reviewer", Source.GLOBAL, 1,
                Set.of("tool:write"), Set.of("code:review"), new AgentLimits(20, 100_000, 5_000_000, 60_000));
        assertPersistedSemanticForgeryRejected(
                "receipt-capability", "reviewer", Source.GLOBAL, 1,
                Set.of("tool:read"), Set.of("code:write"), new AgentLimits(20, 100_000, 5_000_000, 60_000));
        assertPersistedSemanticForgeryRejected(
                "receipt-limits", "reviewer", Source.GLOBAL, 1,
                Set.of("tool:read"), Set.of("code:review"), new AgentLimits(2, 2, 0, 2));
    }

    @Test
    void rejectsInvalidRootsScopesLocksAndStateFileShapes() throws IOException {
        assertCode("REGISTRY_ROOT_NOT_ABSOLUTE", () -> new DurableAgentRegistry(Path.of("relative")));
        Path fileRoot = temporary.resolve("root-file");
        Files.writeString(fileRoot, "not-a-directory");
        assertCode("REGISTRY_ROOT_UNAVAILABLE", () -> new DurableAgentRegistry(fileRoot.toAbsolutePath()));

        Path scopedRoot = temporary.resolve("scoped-root").toAbsolutePath();
        DurableAgentRegistry scopedRegistry = registry(scopedRoot);
        Path tenantScope = scopedRoot.resolve("tenant-" + sha256("tenant-a").substring(0, 32));
        Files.createSymbolicLink(tenantScope, temporary.resolve("outside"));
        assertCode("REGISTRY_SCOPE_INVALID", () -> scopedRegistry.view("tenant-a", "project-a", ADMIN));

        Path lockRoot = temporary.resolve("lock-root").toAbsolutePath();
        DurableAgentRegistry lockRegistry = registry(lockRoot);
        lockRegistry.view("tenant-a", "project-a", ADMIN);
        Path lock = findNamed(lockRoot, "registry.lock");
        Files.delete(lock);
        Files.createDirectory(lock);
        assertCode("REGISTRY_LOCK_INVALID", () -> lockRegistry.view("tenant-a", "project-a", ADMIN));

        Path directoryStateRoot = initializedRoot("directory-state");
        Path directoryState = findNamed(directoryStateRoot, "registry.json");
        Files.delete(directoryState);
        Files.createDirectory(directoryState);
        assertCode("REGISTRY_STATE_INVALID", () -> registry(directoryStateRoot).view("tenant-a", "project-a", ADMIN));

        Path hardLinkRoot = initializedRoot("hard-link-state");
        Path hardLinkedState = findNamed(hardLinkRoot, "registry.json");
        try {
            Files.createLink(hardLinkedState.resolveSibling("registry-copy.json"), hardLinkedState);
            assertCode("REGISTRY_STATE_INVALID", () -> registry(hardLinkRoot).view("tenant-a", "project-a", ADMIN));
        } catch (UnsupportedOperationException ignored) {
            // The exact filesystem has no hard-link support; no weakened assertion is inferred.
        }
    }

    @Test
    void rejectsTruncatedOversizedMalformedAndWrongSchemaState() throws IOException {
        Path emptyRoot = initializedRoot("empty-state");
        Files.writeString(findNamed(emptyRoot, "registry.json"), "", StandardOpenOption.TRUNCATE_EXISTING);
        assertCode("REGISTRY_STATE_SIZE_INVALID", () -> registry(emptyRoot).view("tenant-a", "project-a", ADMIN));

        Path oversizedRoot = initializedRoot("oversized-state");
        Files.write(
                findNamed(oversizedRoot, "registry.json"),
                new byte[4 * 1024 * 1024 + 1],
                StandardOpenOption.TRUNCATE_EXISTING);
        assertCode("REGISTRY_STATE_SIZE_INVALID", () -> registry(oversizedRoot).view("tenant-a", "project-a", ADMIN));

        Path malformedRoot = initializedRoot("malformed-state");
        Files.writeString(
                findNamed(malformedRoot, "registry.json"), "not-json", StandardOpenOption.TRUNCATE_EXISTING);
        assertCode("REGISTRY_STATE_JSON_INVALID", () -> registry(malformedRoot).view("tenant-a", "project-a", ADMIN));

        Path schemaRoot = initializedRoot("schema-state");
        ObjectNode envelope = (ObjectNode) stateMapper().readTree(findNamed(schemaRoot, "registry.json").toFile());
        envelope.put("schemaVersion", "wrong-schema");
        stateMapper().writeValue(findNamed(schemaRoot, "registry.json").toFile(), envelope);
        assertCode("REGISTRY_STATE_SCHEMA_INVALID", () -> registry(schemaRoot).view("tenant-a", "project-a", ADMIN));

        Path payloadRoot = initializedRoot("missing-payload-state");
        Path payloadState = findNamed(payloadRoot, "registry.json");
        ObjectNode missingPayload = (ObjectNode) stateMapper().readTree(payloadState.toFile());
        missingPayload.set("payload", null);
        stateMapper().writeValue(payloadState.toFile(), missingPayload);
        assertCode("REGISTRY_STATE_SCHEMA_INVALID", () -> registry(payloadRoot)
                .view("tenant-a", "project-a", ADMIN));
    }

    @Test
    void failsClosedOnReadLockAndScopeIoErrorsAndOversizedSerializedState() throws IOException {
        Path readRoot = initializedRoot("read-error");
        Path readState = findNamed(readRoot, "registry.json");
        Set<java.nio.file.attribute.PosixFilePermission> originalStatePermissions =
                Files.getPosixFilePermissions(readState);
        try {
            Files.setPosixFilePermissions(readState, Set.of());
            assertCode("REGISTRY_STATE_UNAVAILABLE", () -> registry(readRoot).view("tenant-a", "project-a", ADMIN));
        } finally {
            Files.setPosixFilePermissions(readState, originalStatePermissions);
        }

        Path lockRoot = initializedRoot("lock-error");
        Path lock = findNamed(lockRoot, "registry.lock");
        Set<java.nio.file.attribute.PosixFilePermission> originalLockPermissions =
                Files.getPosixFilePermissions(lock);
        try {
            Files.setPosixFilePermissions(lock, Set.of(
                    java.nio.file.attribute.PosixFilePermission.OWNER_READ));
            assertCode("REGISTRY_STORE_UNAVAILABLE", () -> registry(lockRoot).view("tenant-a", "project-a", ADMIN));
        } finally {
            Files.setPosixFilePermissions(lock, originalLockPermissions);
        }

        Path scopeRoot = temporary.resolve("scope-io-error").toAbsolutePath();
        DurableAgentRegistry scopeRegistry = registry(scopeRoot);
        Set<java.nio.file.attribute.PosixFilePermission> originalRootPermissions =
                Files.getPosixFilePermissions(scopeRoot);
        try {
            Files.setPosixFilePermissions(scopeRoot, Set.of(
                    java.nio.file.attribute.PosixFilePermission.OWNER_READ,
                    java.nio.file.attribute.PosixFilePermission.OWNER_EXECUTE));
            assertCode("REGISTRY_SCOPE_UNAVAILABLE", () -> scopeRegistry.view("tenant-a", "project-a", ADMIN));
        } finally {
            Files.setPosixFilePermissions(scopeRoot, originalRootPermissions);
        }

        Path largeRoot = temporary.resolve("large-state").toAbsolutePath();
        String maximumPrompt = "x".repeat(32_768);
        List<AgentDefinition> agents = new java.util.ArrayList<>();
        for (int index = 0; index < 256; index++) {
            agents.add(new AgentDefinition(
                    "agent-" + index, "description", "mode", "model", maximumPrompt,
                    Set.of(), Set.of(), Map.of(), new AgentLimits(1, 1, 0, 1), 1, true));
        }
        assertCode("REGISTRY_STATE_SIZE_INVALID", () -> registry(largeRoot).replaceLayer(update(
                Source.GLOBAL, 0, "large-state", agents)));
    }

    @Test
    void rejectsDigestBoundStructuralStateForgery() throws IOException {
        Path layersRoot = initializedRoot("bad-layers");
        forgePayload(layersRoot, payload -> ((ObjectNode) payload.get("layers")).remove("MANAGED"));
        assertCode("REGISTRY_STATE_LAYERS_INVALID", () -> registry(layersRoot).view("tenant-a", "project-a", ADMIN));

        Path mutationRoot = initializedRoot("bad-mutation-receipt");
        forgePayload(mutationRoot, payload -> ((ObjectNode) payload
                .path("mutationReceipts").path("configuration-1").path("result")).put("status", "forged"));
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(mutationRoot).view("tenant-a", "project-a", ADMIN));

        Path selectionRoot = initializedRootWithSelection("bad-selection-receipt");
        forgePayload(selectionRoot, payload -> ((ObjectNode) payload
                .path("selectionReceipts").path("selection-1").path("decision").path("permit"))
                .put("projectId", "forged-project"));
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(selectionRoot).view("tenant-a", "project-a", ADMIN));

        Path auditRoot = initializedRoot("bad-audit");
        forgePayload(auditRoot, payload -> ((ObjectNode) payload.path("audit").get(0)).put("sequence", 2));
        assertCode("REGISTRY_AUDIT_SEQUENCE_INVALID", () -> registry(auditRoot).view("tenant-a", "project-a", ADMIN));

        Path scopeRoot = initializedRoot("bad-scope");
        forgePayload(scopeRoot, payload -> payload.put("tenantId", "forged-tenant"));
        assertCode("REGISTRY_STATE_SCOPE_INVALID", () -> registry(scopeRoot).view("tenant-a", "project-a", ADMIN));
    }

    @Test
    void rejectsEveryDigestBoundStateInvariantAndCapacityLimit() throws IOException {
        Path storeSchemaRoot = initializedRoot("bad-store-schema");
        forgePayload(storeSchemaRoot, payload -> payload.put("schemaVersion", "wrong-store-schema"));
        assertCode("REGISTRY_STATE_SCOPE_INVALID", () -> registry(storeSchemaRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path projectScopeRoot = initializedRoot("bad-project-scope");
        forgePayload(projectScopeRoot, payload -> payload.put("projectId", "forged-project"));
        assertCode("REGISTRY_STATE_SCOPE_INVALID", () -> registry(projectScopeRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path negativeEpochRoot = initializedRoot("negative-epoch");
        forgePayload(negativeEpochRoot, payload -> payload.put("contextEpoch", -1));
        assertCode("REGISTRY_STATE_SCOPE_INVALID", () -> registry(negativeEpochRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path tooManyAgentsRoot = initializedRoot("too-many-agents");
        forgePayload(tooManyAgentsRoot, payload -> {
            ArrayNode agents = (ArrayNode) payload.path("layers").path("GLOBAL");
            ObjectNode template = (ObjectNode) agents.get(0);
            for (int index = 1; index < 257; index++) agents.add(template.deepCopy());
        });
        assertCode("REGISTRY_STATE_LAYERS_INVALID", () -> registry(tooManyAgentsRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path duplicateAgentsRoot = initializedRoot("duplicate-agents");
        forgePayload(duplicateAgentsRoot, payload -> {
            ArrayNode agents = (ArrayNode) payload.path("layers").path("GLOBAL");
            agents.add(agents.get(0).deepCopy());
        });
        assertCode("REGISTRY_STATE_LAYERS_INVALID", () -> registry(duplicateAgentsRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path nullAgentRoot = initializedRoot("null-agent");
        forgePayload(nullAgentRoot, payload -> ((ArrayNode) payload.path("layers").path("GLOBAL"))
                .set(0, com.fasterxml.jackson.databind.node.NullNode.getInstance()));
        assertCode("REGISTRY_STATE_LAYERS_INVALID", () -> registry(nullAgentRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path missingMutationResultRoot = initializedRoot("missing-mutation-result");
        forgePayload(missingMutationResultRoot, payload -> ((ObjectNode) payload
                .path("mutationReceipts").path("configuration-1")).set("result", null));
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(missingMutationResultRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path futureMutationRoot = initializedRoot("future-mutation");
        forgePayload(futureMutationRoot, payload -> ((ObjectNode) payload
                .path("mutationReceipts").path("configuration-1").path("result")).put("contextEpoch", 2));
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(futureMutationRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path futureSelectionRoot = initializedRootWithSelection("future-selection");
        forgePayload(futureSelectionRoot, payload -> ((ObjectNode) payload
                .path("selectionReceipts").path("selection-1").path("decision")).put("contextEpoch", 2));
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(futureSelectionRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path missingSelectionDecisionRoot = initializedRootWithSelection("missing-selection-decision");
        forgePayload(missingSelectionDecisionRoot, payload -> ((ObjectNode) payload
                .path("selectionReceipts").path("selection-1")).set("decision", null));
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(missingSelectionDecisionRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path invalidSelectionStatusRoot = initializedRootWithSelection("invalid-selection-status");
        forgePayload(invalidSelectionStatusRoot, payload -> {
            ObjectNode decision = (ObjectNode) payload
                    .path("selectionReceipts").path("selection-1").path("decision");
            decision.put("status", "forged");
            decision.set("permit", null);
        });
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(invalidSelectionStatusRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path permitDigestRoot = initializedRootWithSelection("bad-permit-digest");
        forgePayload(permitDigestRoot, payload -> ((ObjectNode) payload
                .path("selectionReceipts").path("selection-1").path("decision").path("permit"))
                .put("permitDigest", "f".repeat(64)));
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(permitDigestRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path permitTenantRoot = initializedRootWithSelection("bad-permit-tenant");
        forgePayload(permitTenantRoot, payload -> ((ObjectNode) payload
                .path("selectionReceipts").path("selection-1").path("decision").path("permit"))
                .put("tenantId", "forged-tenant"));
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(permitTenantRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path decisionDigestRoot = initializedRootWithSelection("bad-decision-digest");
        forgePayload(decisionDigestRoot, payload -> ((ObjectNode) payload
                .path("selectionReceipts").path("selection-1").path("decision"))
                .put("registryDigest", "f".repeat(64)));
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(decisionDigestRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path decisionEpochRoot = initializedRootWithSelectionAtEpochTwo("bad-decision-epoch");
        forgePayload(decisionEpochRoot, payload -> ((ObjectNode) payload
                .path("selectionReceipts").path("selection-1").path("decision"))
                .put("contextEpoch", 1));
        assertCode("REGISTRY_RECEIPT_INVALID", () -> registry(decisionEpochRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path stateCapacityRoot = initializedRoot("state-capacity");
        forgePayload(stateCapacityRoot, payload -> expandAudit(payload, 4_097));
        assertCode("REGISTRY_STATE_CAPACITY_INVALID", () -> registry(stateCapacityRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path mutationCapacityRoot = initializedRoot("mutation-state-capacity");
        forgePayload(mutationCapacityRoot, payload -> expandMutationReceipts(payload, 2_049));
        assertCode("REGISTRY_STATE_CAPACITY_INVALID", () -> registry(mutationCapacityRoot)
                .view("tenant-a", "project-a", ADMIN));

        Path selectionCapacityRoot = initializedRootWithSelection("selection-state-capacity");
        forgePayload(selectionCapacityRoot, payload -> expandSelectionReceipts(payload, 2_049));
        assertCode("REGISTRY_STATE_CAPACITY_INVALID", () -> registry(selectionCapacityRoot)
                .view("tenant-a", "project-a", ADMIN));
    }

    @Test
    void exhaustsDurableAuditAndReceiptCapacityWithoutDroppingEvidence() throws IOException {
        Path auditRoot = initializedRoot("audit-capacity");
        forgePayload(auditRoot, payload -> expandAudit(payload, 4_096));
        assertCode("REGISTRY_AUDIT_CAPACITY_EXHAUSTED", () -> registry(auditRoot).replaceLayer(update(
                Source.PROJECT, 1, "after-audit-capacity", List.of(agent("second", "model-b", 1, true)))));

        Path receiptRoot = initializedRoot("receipt-capacity");
        forgePayload(receiptRoot, payload -> {
            ObjectNode receipts = (ObjectNode) payload.path("mutationReceipts");
            ObjectNode template = (ObjectNode) receipts.path("configuration-1");
            for (int index = 1; index < 2_048; index++) {
                receipts.set("receipt-" + index, template.deepCopy());
            }
        });
        assertCode("REGISTRY_RECEIPT_CAPACITY_EXHAUSTED", () -> registry(receiptRoot).replaceLayer(update(
                Source.PROJECT, 1, "after-receipt-capacity", List.of(agent("second", "model-b", 1, true)))));
    }

    @Test
    void candidateCleanupNeverDeletesDirectoriesAndToleratesCleanupFailure() throws IOException {
        DurableAgentRegistry.deleteCandidate(null);

        Path candidate = temporary.resolve("candidate.tmp");
        Files.writeString(candidate, "candidate");
        DurableAgentRegistry.deleteCandidate(candidate);
        assertFalse(Files.exists(candidate));

        Path directory = temporary.resolve("candidate-directory");
        Files.createDirectory(directory);
        DurableAgentRegistry.deleteCandidate(directory);
        assertTrue(Files.isDirectory(directory));

        Path protectedParent = temporary.resolve("protected-parent");
        Files.createDirectory(protectedParent);
        Path protectedCandidate = protectedParent.resolve("candidate.tmp");
        Files.writeString(protectedCandidate, "candidate");
        Set<java.nio.file.attribute.PosixFilePermission> original = Files.getPosixFilePermissions(protectedParent);
        try {
            Files.setPosixFilePermissions(protectedParent, Set.of(
                    java.nio.file.attribute.PosixFilePermission.OWNER_READ,
                    java.nio.file.attribute.PosixFilePermission.OWNER_EXECUTE));
            DurableAgentRegistry.deleteCandidate(protectedCandidate);
            assertTrue(Files.exists(protectedCandidate));
        } finally {
            Files.setPosixFilePermissions(protectedParent, original);
            Files.deleteIfExists(protectedCandidate);
        }
    }

    @Test
    void validatesInternalFilesystemAndScopeSafetyBoundaries() throws IOException {
        Path root = temporary.resolve("safety-root").toAbsolutePath();
        var operation = new DurableAgentRegistry.OperationScope(root, "tenant-a", "project-a");
        DurableAgentRegistry.requireOperationScope(operation, "tenant-a", "project-a");
        assertCode("REGISTRY_OPERATION_SCOPE_INVALID", () -> DurableAgentRegistry.requireOperationScope(
                null, "tenant-a", "project-a"));
        assertCode("REGISTRY_OPERATION_SCOPE_INVALID", () -> DurableAgentRegistry.requireOperationScope(
                operation, "tenant-b", "project-a"));
        assertCode("REGISTRY_OPERATION_SCOPE_INVALID", () -> DurableAgentRegistry.requireOperationScope(
                operation, "tenant-a", "project-b"));

        DurableAgentRegistry.requireContainedScope(root, root.resolve("tenant/project"));
        assertCode("REGISTRY_SCOPE_ESCAPED", () -> DurableAgentRegistry.requireContainedScope(
                root, temporary.resolve("outside").toAbsolutePath()));

        DurableAgentRegistry.requireSingleLinkCount(1, "REGISTRY_LINK_INVALID");
        assertCode("REGISTRY_LINK_INVALID", () -> DurableAgentRegistry.requireSingleLinkCount(
                2L, "REGISTRY_LINK_INVALID"));
        assertCode("REGISTRY_LINK_INVALID", () -> DurableAgentRegistry.requireSingleLinkCount(
                "not-a-number", "REGISTRY_LINK_INVALID"));

        assertTrue(DurableAgentRegistry.constantTimeEquals("a", "a"));
        assertFalse(DurableAgentRegistry.constantTimeEquals("a", "b"));
        assertFalse(DurableAgentRegistry.constantTimeEquals(null, "a"));
        assertFalse(DurableAgentRegistry.constantTimeEquals("a", null));

        Path directory = temporary.resolve("safety-directory");
        Files.createDirectory(directory);
        DurableAgentRegistry.requireDirectory(directory, "REGISTRY_DIRECTORY_INVALID");
        Path regularFile = temporary.resolve("safety-file");
        Files.writeString(regularFile, "safe");
        assertEquals("REGISTRY_DIRECTORY_INVALID", assertThrows(
                AgentRegistryException.class,
                () -> DurableAgentRegistry.requireDirectory(regularFile, "REGISTRY_DIRECTORY_INVALID")).code());
        DurableAgentRegistry.requireRegularSingleLink(regularFile, "REGISTRY_FILE_INVALID");
        assertCode("REGISTRY_FILE_INVALID", () -> DurableAgentRegistry.requireRegularSingleLink(
                directory, "REGISTRY_FILE_INVALID"));
        assertCode("REGISTRY_FILE_UNAVAILABLE", () -> DurableAgentRegistry.requireRegularSingleLink(
                temporary.resolve("missing-file"), "REGISTRY_FILE_UNAVAILABLE"));

        Path fileLink = temporary.resolve("safety-file-link");
        try {
            Files.createSymbolicLink(fileLink, regularFile);
            assertCode("REGISTRY_FILE_INVALID", () -> DurableAgentRegistry.requireRegularSingleLink(
                    fileLink, "REGISTRY_FILE_INVALID"));
        } catch (UnsupportedOperationException ignored) {
            // The exact filesystem cannot exercise symlink metadata; no result is inferred for that branch.
        }

        Path archive = temporary.resolve("unsupported-posix.zip");
        try (var zip = java.nio.file.FileSystems.newFileSystem(
                java.net.URI.create("jar:" + archive.toUri()), Map.of("create", "true"))) {
            Path zipFile = zip.getPath("/entry.txt");
            Files.writeString(zipFile, "entry");
            DurableAgentRegistry.requireRegularSingleLink(zipFile, "REGISTRY_FILE_INVALID");
            DurableAgentRegistry.setOwnerOnly(zipFile, Set.of());
        }
    }

    @Test
    void translatesDeterministicStorageAndSerializationFailures() throws IOException {
        Path existingLock = temporary.resolve("existing.lock");
        Files.writeString(existingLock, "lock");
        DurableAgentRegistry.createLockFile(existingLock);
        assertEquals("lock", Files.readString(existingLock));

        Path state = temporary.resolve("stable-state.json");
        Files.writeString(state, "{}");
        assertEquals(2, DurableAgentRegistry.readStableBytes(state, 2).length);
        assertEquals("REGISTRY_STATE_CHANGED", assertThrows(
                AgentRegistryException.class,
                () -> DurableAgentRegistry.readStableBytes(state, 3)).code());

        assertCode("REGISTRY_TEST_SERIALIZATION_FAILED", () -> DurableAgentRegistry.serialize(
                stateMapper(), new BrokenSerializationValue(), "REGISTRY_TEST_SERIALIZATION_FAILED"));

        Path missingCandidate = temporary.resolve("missing-parent").resolve("candidate.tmp");
        assertCode("REGISTRY_STATE_WRITE_FAILED", () -> DurableAgentRegistry.writeCandidate(
                missingCandidate, "state".getBytes(StandardCharsets.UTF_8)));

        Path atomicCandidate = temporary.resolve("atomic-candidate.tmp");
        Files.writeString(atomicCandidate, "candidate");
        assertCode("REGISTRY_ATOMIC_MOVE_REQUIRED", () -> DurableAgentRegistry.commitCandidate(
                atomicCandidate,
                temporary.resolve("atomic-target.json"),
                temporary,
                (source, target) -> {
                    throw new java.nio.file.AtomicMoveNotSupportedException(
                            source.toString(), target.toString(), "forced atomic-move boundary");
                }));
        assertFalse(Files.exists(atomicCandidate));

        Path commitCandidate = temporary.resolve("commit-candidate.tmp");
        Files.writeString(commitCandidate, "candidate");
        assertCode("REGISTRY_STATE_COMMIT_FAILED", () -> DurableAgentRegistry.commitCandidate(
                commitCandidate,
                temporary.resolve("commit-target.json"),
                temporary,
                (source, target) -> {
                    throw new IOException("forced commit boundary");
                }));
        assertFalse(Files.exists(commitCandidate));

        assertThrows(IllegalStateException.class, () -> DurableAgentRegistry.sha256(
                "value".getBytes(StandardCharsets.UTF_8), "ELMOS-NO-SUCH-DIGEST"));
    }

    private static String runConcurrent(
            CountDownLatch start,
            DurableAgentRegistry registry,
            LayerUpdate update
    ) throws InterruptedException {
        start.await();
        try {
            return registry.replaceLayer(update).status();
        } catch (AgentRegistryException error) {
            return error.code();
        }
    }

    private static void assertStale(
            DurableAgentRegistry registry,
            AgentRegistryModels.SelectionDecision original,
            AgentRegistryModels.SelectionPermit permit,
            String expectedCode,
            AtomicBoolean invoked
    ) {
        var decision = new AgentRegistryModels.SelectionDecision(
                "allowed", "AGENT_SELECTION_ALLOWED", permit.contextEpoch(),
                permit.registryDigest(), permit, original.idempotentReplay());
        assertCode(expectedCode, () -> registry.invokeSelected(
                decision, ignored -> invoked.getAndSet(true)));
    }

    private void assertPersistedSemanticForgeryRejected(
            String name,
            String agentId,
            Source source,
            long agentVersion,
            Set<String> permissions,
            Set<String> capabilities,
            AgentLimits limits
    ) throws IOException {
        Path root = temporary.resolve(name).toAbsolutePath();
        DurableAgentRegistry registry = registry(root);
        registry.replaceLayer(update(
                Source.GLOBAL, 0, "configuration-1", List.of(
                        agent("reviewer", "model-a", 1, true),
                        agent("disabled", "model-a", 1, false))));
        var selected = registry.select(selection(
                1, "selection-1", ADMIN, Set.of("tool:read"), Set.of("code:review")));
        var forgedPermit = signedPermit(
                selected.permit(), agentId, source, agentVersion,
                permissions, capabilities, limits, selected.registryDigest());
        forgePayload(root, payload -> ((ObjectNode) payload
                .path("selectionReceipts").path("selection-1").path("decision"))
                .set("permit", stateMapper().valueToTree(forgedPermit)));
        var forgedDecision = new AgentRegistryModels.SelectionDecision(
                "allowed", "AGENT_SELECTION_ALLOWED", selected.contextEpoch(),
                selected.registryDigest(), forgedPermit, false);
        AtomicBoolean invoked = new AtomicBoolean(false);
        assertCode("AGENT_SELECTION_STALE", () -> registry(root).invokeSelected(
                forgedDecision, ignored -> invoked.getAndSet(true)));
        assertFalse(invoked.get());
    }

    private static AgentRegistryModels.SelectionPermit signedPermit(
            AgentRegistryModels.SelectionPermit base,
            String agentId,
            Source source,
            long agentVersion,
            Set<String> permissions,
            Set<String> capabilities,
            AgentLimits limits,
            String registryDigest
    ) {
        var unsigned = new AgentRegistryModels.SelectionPermit(
                base.tenantId(), base.projectId(), base.actorId(), agentId, source, agentVersion,
                base.contextEpoch(), permissions, capabilities, limits, base.issuedAt(), base.expiresAt(),
                registryDigest, "0".repeat(64));
        return new AgentRegistryModels.SelectionPermit(
                unsigned.tenantId(), unsigned.projectId(), unsigned.actorId(), unsigned.agentId(),
                unsigned.source(), unsigned.agentVersion(), unsigned.contextEpoch(), unsigned.permissions(),
                unsigned.capabilities(), unsigned.limits(), unsigned.issuedAt(), unsigned.expiresAt(),
                unsigned.registryDigest(), permitDigest(unsigned));
    }

    private static String permitDigest(AgentRegistryModels.SelectionPermit permit) {
        Map<String, Object> document = new java.util.TreeMap<>();
        document.put("actorId", permit.actorId());
        document.put("agentId", permit.agentId());
        document.put("agentVersion", permit.agentVersion());
        document.put("capabilities", permit.capabilities());
        document.put("contextEpoch", permit.contextEpoch());
        document.put("expiresAt", permit.expiresAt().toString());
        document.put("issuedAt", permit.issuedAt().toString());
        document.put("permissions", permit.permissions());
        document.put("projectId", permit.projectId());
        document.put("registryDigest", permit.registryDigest());
        document.put("source", permit.source().name());
        document.put("tenantId", permit.tenantId());
        try {
            return sha256(stateMapper().writeValueAsBytes(document));
        } catch (IOException error) {
            throw new AssertionError(error);
        }
    }

    private Path initializedRoot(String name) throws IOException {
        Path root = temporary.resolve(name).toAbsolutePath();
        registry(root).replaceLayer(update(
                Source.GLOBAL, 0, "configuration-1", List.of(agent("reviewer", "model-a", 1, true))));
        return root;
    }

    private Path initializedRootWithSelection(String name) throws IOException {
        Path root = initializedRoot(name);
        registry(root).select(selection(
                1, "selection-1", ADMIN, Set.of("tool:read"), Set.of("code:review")));
        return root;
    }

    private Path initializedRootWithSelectionAtEpochTwo(String name) throws IOException {
        Path root = initializedRoot(name);
        registry(root).replaceLayer(update(
                Source.PROJECT, 1, "configuration-2", List.of(agent("project-agent", "model-b", 1, true))));
        registry(root).select(selection(
                2, "selection-1", ADMIN, Set.of("tool:read"), Set.of("code:review")));
        return root;
    }

    private static Path findNamed(Path root, String fileName) throws IOException {
        try (var paths = Files.walk(root)) {
            return paths.filter(path -> path.getFileName().toString().equals(fileName))
                    .findFirst().orElseThrow();
        }
    }

    private static void forgePayload(Path root, Consumer<ObjectNode> mutation) throws IOException {
        Path state = findNamed(root, "registry.json");
        ObjectMapper mapper = stateMapper();
        ObjectNode envelope = (ObjectNode) mapper.readTree(state.toFile());
        ObjectNode payload = (ObjectNode) envelope.get("payload");
        mutation.accept(payload);
        envelope.put("payloadDigest", sha256(mapper.writeValueAsBytes(canonicalize(payload, mapper))));
        mapper.writeValue(state.toFile(), envelope);
    }

    private static JsonNode canonicalize(JsonNode node, ObjectMapper mapper) {
        if (node.isObject()) {
            ObjectNode sorted = mapper.createObjectNode();
            java.util.TreeSet<String> fields = new java.util.TreeSet<>();
            node.fieldNames().forEachRemaining(fields::add);
            fields.forEach(field -> sorted.set(field, canonicalize(node.get(field), mapper)));
            return sorted;
        }
        if (node.isArray()) {
            ArrayNode values = mapper.createArrayNode();
            node.forEach(value -> values.add(canonicalize(value, mapper)));
            return values;
        }
        return node.deepCopy();
    }

    private static void expandAudit(ObjectNode payload, int size) {
        ArrayNode audit = (ArrayNode) payload.path("audit");
        ObjectNode template = (ObjectNode) audit.get(0);
        for (int index = 1; index < size; index++) {
            ObjectNode event = template.deepCopy();
            event.put("sequence", index + 1L);
            audit.add(event);
        }
    }

    private static void expandMutationReceipts(ObjectNode payload, int size) {
        ObjectNode receipts = (ObjectNode) payload.path("mutationReceipts");
        ObjectNode template = (ObjectNode) receipts.path("configuration-1");
        for (int index = 1; index < size; index++) {
            receipts.set("mutation-" + index, template.deepCopy());
        }
    }

    private static void expandSelectionReceipts(ObjectNode payload, int size) {
        ObjectNode receipts = (ObjectNode) payload.path("selectionReceipts");
        ObjectNode template = (ObjectNode) receipts.path("selection-1");
        for (int index = 2; index <= size; index++) {
            receipts.set("selection-" + index, template.deepCopy());
        }
    }

    private static ObjectMapper stateMapper() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
                .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
                .build();
    }

    private static String sha256(String value) {
        return sha256(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String sha256(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException error) {
            throw new AssertionError(error);
        }
    }

    private static void assertCode(String expected, Runnable operation) {
        assertEquals(expected, assertThrows(AgentRegistryException.class, operation::run).code());
    }

    private static DurableAgentRegistry registry(Path root) {
        return new DurableAgentRegistry(root, Clock.fixed(NOW, ZoneOffset.UTC));
    }

    private static LayerUpdate update(
            Source source,
            long expectedEpoch,
            String idempotencyKey,
            List<AgentDefinition> agents
    ) {
        return new LayerUpdate(
                "tenant-a", "project-a", source, expectedEpoch, "registry-admin",
                ADMIN, idempotencyKey, agents);
    }

    private static SelectionRequest selection(
            long expectedEpoch,
            String idempotencyKey,
            Set<String> actorPermissions,
            Set<String> requiredPermissions,
            Set<String> requiredCapabilities
    ) {
        return new SelectionRequest(
                "tenant-a", "project-a", "reviewer", expectedEpoch, "developer-a",
                actorPermissions, requiredPermissions, requiredCapabilities, idempotencyKey);
    }

    private static AgentDefinition agent(
            String id,
            String model,
            long version,
            boolean enabled
    ) {
        return new AgentDefinition(
                id,
                "Global reviewer",
                "reviewer",
                model,
                "Review the exact task and return structured findings.",
                Set.of("tool:read"),
                Set.of("code:review"),
                Map.of("structured-output", true),
                new AgentLimits(20, 100_000, 5_000_000, 60_000),
                version,
                enabled);
    }

    private static final class MutableClock extends Clock {
        private Instant now;

        private MutableClock(Instant now) {
            this.now = now;
        }

        private void advanceMillis(long millis) {
            now = now.plusMillis(millis);
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            if (!ZoneOffset.UTC.equals(zone)) throw new IllegalArgumentException("test clock is UTC-only");
            return this;
        }

        @Override
        public Instant instant() {
            return now;
        }
    }

    private static final class BrokenSerializationValue {
        public String getValue() {
            throw new IllegalStateException("forced serialization boundary");
        }
    }
}
