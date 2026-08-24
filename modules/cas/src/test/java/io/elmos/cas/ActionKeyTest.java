package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.*;

class ActionKeyTest {

    private static final String PINNED_IMAGE =
            "registry.internal/elmos/java21@sha256:" + "a".repeat(64);

    private static CasDigest digest(String text) {
        return CasDigest.of(text.getBytes(StandardCharsets.UTF_8));
    }

    private static ActionKeyBuilder baseline() {
        return new ActionKeyBuilder()
                .tenant("tenant-a", "project-a")
                .sourceTree(digest("source"))
                .dependencyGraph(digest("deps"))
                .adapter("java-adapter", digest("adapter"))
                .irSchemaVersion("ir-3")
                .rulePacks(List.of(new ActionKeyBuilder.RulePackRef("spring-boot-3", digest("rules"))))
                .toolchainImage(PINNED_IMAGE)
                .targetPlatform("linux/arm64")
                .buildOptions(Map.of("profile", "release"))
                .command(List.of("./mvnw", "-q", "verify"))
                .workingDirectory("/workspace/source")
                .declaredOutputs(List.of("target", "reports"))
                .prompt(Optional.of(digest("prompt")))
                .model(Optional.of(new ActionKeyBuilder.ModelIdentity("anthropic", "claude", "v1",
                        Map.of("temperature", "0"))))
                .policy(digest("policy"))
                .permissionScope(Set.of("repo:read", "artifact:write"))
                .sandbox("S2", digest("sandbox-policy"))
                .dataResidency("eu-west")
                .environmentContract(ActionKeyBuilder.EnvironmentContract.of("SOURCE_DATE_EPOCH"))
                .environment(Map.of("SOURCE_DATE_EPOCH", "1787121000"));
    }

    private static ActionKey mutated(Consumer<ActionKeyBuilder> mutation) {
        ActionKeyBuilder builder = baseline();
        mutation.accept(builder);
        return builder.build();
    }

    @Test void identicalInputsProduceAnIdenticalKey() {
        assertEquals(baseline().build().digest(), baseline().build().digest());
    }

    @Test void everyDeclaredInputChangesTheKey() {
        ActionKey base = baseline().build();
        Map<String, ActionKey> variants = Map.ofEntries(
                Map.entry("source_tree", mutated(builder -> builder.sourceTree(digest("source-2")))),
                Map.entry("dependency_graph", mutated(builder -> builder.dependencyGraph(digest("deps-2")))),
                Map.entry("adapter", mutated(builder -> builder.adapter("java-adapter", digest("adapter-2")))),
                Map.entry("ir_schema_version", mutated(builder -> builder.irSchemaVersion("ir-4"))),
                Map.entry("rule_packs", mutated(builder -> builder.rulePacks(
                        List.of(new ActionKeyBuilder.RulePackRef("spring-boot-3", digest("rules-2")))))),
                Map.entry("toolchain_image", mutated(builder -> builder.toolchainImage(
                        "registry.internal/elmos/java21@sha256:" + "b".repeat(64)))),
                Map.entry("target_platform", mutated(builder -> builder.targetPlatform("linux/amd64"))),
                Map.entry("build_options", mutated(builder -> builder.buildOptions(Map.of("profile", "debug")))),
                Map.entry("command", mutated(builder -> builder.command(List.of("./mvnw", "-q", "test")))),
                Map.entry("working_directory", mutated(builder -> builder.workingDirectory("/workspace/other"))),
                Map.entry("declared_outputs", mutated(builder -> builder.declaredOutputs(List.of("target")))),
                Map.entry("prompt", mutated(builder -> builder.prompt(Optional.of(digest("prompt-2"))))),
                Map.entry("model", mutated(builder -> builder.model(Optional.of(
                        new ActionKeyBuilder.ModelIdentity("anthropic", "claude", "v2", Map.of("temperature", "0")))))),
                Map.entry("policy", mutated(builder -> builder.policy(digest("policy-2")))),
                Map.entry("permission_scope", mutated(builder -> builder.permissionScope(Set.of("repo:read")))),
                Map.entry("sandbox", mutated(builder -> builder.sandbox("S3", digest("sandbox-policy")))),
                Map.entry("data_residency", mutated(builder -> builder.dataResidency("us-east"))),
                Map.entry("environment", mutated(builder -> builder.environment(
                        Map.of("SOURCE_DATE_EPOCH", "1787121001")))));

        variants.forEach((component, variant) -> {
            assertNotEquals(base.digest(), variant.digest(), component + " did not change the action key");
            assertEquals(List.of(component), base.explainDifference(variant),
                    component + " changed more or fewer components than expected");
        });
    }

    @Test void decodingParametersAreCoveredByTheModelComponent() {
        ActionKey greedy = mutated(builder -> builder.model(Optional.of(
                new ActionKeyBuilder.ModelIdentity("anthropic", "claude", "v1", Map.of("temperature", "0")))));
        ActionKey sampled = mutated(builder -> builder.model(Optional.of(
                new ActionKeyBuilder.ModelIdentity("anthropic", "claude", "v1", Map.of("temperature", "1")))));
        assertNotEquals(greedy.digest(), sampled.digest());
    }

    @Test void mutableImageTagsAreRefused() {
        assertThrows(IllegalArgumentException.class,
                () -> baseline().toolchainImage("registry.internal/elmos/java21:latest"));
        assertThrows(IllegalArgumentException.class,
                () -> baseline().toolchainImage("registry.internal/elmos/java21:21.0.10"));
    }

    @Test void anUndeclaredEnvironmentVariableStopsTheKeyFromBeingBuilt() {
        var error = assertThrows(ActionKeyBuilder.UndeclaredEnvironmentException.class,
                () -> baseline().environment(Map.of("SOURCE_DATE_EPOCH", "1", "LD_PRELOAD", "/tmp/evil.so")));
        assertEquals(List.of("LD_PRELOAD"), error.variables());
    }

    @Test void variablesThatCannotAffectOutputCanBeDeclaredIgnored() {
        ActionKey withTrace = baseline()
                .environmentContract(new ActionKeyBuilder.EnvironmentContract(
                        Set.of("SOURCE_DATE_EPOCH"), Set.of("TRACE_ID")))
                .environment(Map.of("SOURCE_DATE_EPOCH", "1787121000", "TRACE_ID", "abc"))
                .build();
        assertEquals(baseline().build().digest(), withTrace.digest());
    }

    @Test void aVariableCannotBeBothSignificantAndIgnored() {
        assertThrows(IllegalArgumentException.class,
                () -> new ActionKeyBuilder.EnvironmentContract(Set.of("A"), Set.of("A")));
    }

    @Test void setOrderedInputsDoNotDependOnIterationOrder() {
        ActionKey first = mutated(builder -> builder.declaredOutputs(List.of("reports", "target"))
                .permissionScope(new java.util.LinkedHashSet<>(List.of("artifact:write", "repo:read"))));
        ActionKey second = mutated(builder -> builder.declaredOutputs(List.of("target", "reports"))
                .permissionScope(new java.util.LinkedHashSet<>(List.of("repo:read", "artifact:write"))));
        assertEquals(first.digest(), second.digest());
    }

    @Test void separatorInjectionCannotCollapseTwoDifferentActionsOntoOneKey() {
        ActionKey injected = mutated(builder -> builder.command(List.of("build", "a\nb")));
        ActionKey split = mutated(builder -> builder.command(List.of("build", "a", "b")));
        assertNotEquals(injected.digest(), split.digest());

        ActionKey optionsInjected = mutated(builder -> builder.buildOptions(Map.of("a", "1\n2:b", "profile", "release")));
        ActionKey optionsSplit = mutated(builder -> builder.buildOptions(Map.of("a", "1", "2:b", "", "profile", "release")));
        assertNotEquals(optionsInjected.digest(), optionsSplit.digest());
    }

    @Test void anIncompleteKeyIsRefusedRatherThanSilentlyNarrowed() {
        var error = assertThrows(IllegalStateException.class, () -> new ActionKeyBuilder()
                .tenant("tenant-a", "project-a")
                .sourceTree(digest("source"))
                .build());
        assertTrue(error.getMessage().contains("toolchain_image"));
        assertTrue(error.getMessage().contains("permission_scope"));
    }
}
