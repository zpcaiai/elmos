package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
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

    private static ActionKeyBuilder minimalRequired() {
        return new ActionKeyBuilder()
                .tenant("tenant-a", "project-a")
                .sourceTree(digest(""))
                .toolchainImage(PINNED_IMAGE)
                .command(List.of("true"))
                .declaredOutputs(List.of())
                .policy(digest(""))
                .permissionScope(Set.of())
                .dataResidency("eu-west")
                .environmentContract(ActionKeyBuilder.EnvironmentContract.of())
                .environment(Map.of());
    }

    private static ActionKey mutated(Consumer<ActionKeyBuilder> mutation) {
        ActionKeyBuilder builder = baseline();
        mutation.accept(builder);
        return builder.build();
    }

    @Test void identicalInputsProduceAnIdenticalKey() {
        assertEquals(baseline().build().digest(), baseline().build().digest());
    }

    @Test void fluentInvocationOrderCannotChangeTheV2DigestOrComponentOrder() {
        ActionKey canonical = baseline().build();
        ActionKey reordered = new ActionKeyBuilder()
                .environmentContract(ActionKeyBuilder.EnvironmentContract.of("SOURCE_DATE_EPOCH"))
                .environment(Map.of("SOURCE_DATE_EPOCH", "1787121000"))
                .dataResidency("eu-west")
                .sandbox("S2", digest("sandbox-policy"))
                .permissionScope(Set.of("artifact:write", "repo:read"))
                .policy(digest("policy"))
                .model(Optional.of(new ActionKeyBuilder.ModelIdentity(
                        "anthropic", "claude", "v1", Map.of("temperature", "0"))))
                .prompt(Optional.of(digest("prompt")))
                .declaredOutputs(List.of("reports", "target"))
                .workingDirectory("/workspace/source")
                .command(List.of("./mvnw", "-q", "verify"))
                .buildOptions(Map.of("profile", "release"))
                .targetPlatform("linux/arm64")
                .toolchainImage(PINNED_IMAGE)
                .rulePacks(List.of(
                        new ActionKeyBuilder.RulePackRef("spring-boot-3", digest("rules"))))
                .irSchemaVersion("ir-3")
                .adapter("java-adapter", digest("adapter"))
                .dependencyGraph(digest("deps"))
                .sourceTree(digest("source"))
                .tenant("tenant-a", "project-a")
                .build();

        assertEquals(ActionKeyBuilder.CANONICAL_COMPONENT_ORDER,
                List.copyOf(canonical.components().keySet()));
        assertEquals(ActionKeyBuilder.CANONICAL_COMPONENT_ORDER,
                List.copyOf(reordered.components().keySet()));
        assertEquals(canonical.components(), reordered.components());
        assertEquals(canonical.digest(), reordered.digest());
    }

    @Test void sharedV2VerifierRejectsOrderDigestAndLegacySchemaDrift() {
        ActionKey canonical = baseline().build();
        assertDoesNotThrow(() -> ActionKeyBuilder.verifyCanonical(canonical));

        List<String> reversedNames = new ArrayList<>(canonical.components().keySet());
        Collections.reverse(reversedNames);
        Map<String, String> reversedComponents = new LinkedHashMap<>();
        reversedNames.forEach(name ->
                reversedComponents.put(name, canonical.components().get(name)));
        ActionKey wrongOrder = new ActionKey(
                canonical.digest(), canonical.tenantId(), reversedComponents);
        assertThrows(IllegalArgumentException.class,
                () -> ActionKeyBuilder.verifyCanonical(wrongOrder));

        CasManifest.CanonicalEncoder legacy =
                new CasManifest.CanonicalEncoder("elmos-action-key/1");
        canonical.components().forEach(legacy::field);
        ActionKey legacyV1 = new ActionKey(
                CasDigest.of(legacy.bytes()), canonical.tenantId(), canonical.components());
        assertThrows(IllegalArgumentException.class,
                () -> ActionKeyBuilder.verifyCanonical(legacyV1));

        ActionKey digestDrift = new ActionKey(
                digest("forged-v2-digest"), canonical.tenantId(), canonical.components());
        assertThrows(IllegalArgumentException.class,
                () -> ActionKeyBuilder.verifyCanonical(digestDrift));
    }

    @Test void sharedV2VerifierRejectsSemanticallyForgedComponentsEvenWithAMatchingDigest() {
        ActionKey canonical = baseline().build();
        Map<String, String> mutableImageComponents = new LinkedHashMap<>(canonical.components());
        mutableImageComponents.put("toolchain_image", "registry.internal/elmos/java21:latest");
        ActionKey mutableImage = withCanonicalV2Digest(
                canonical.tenantId(), mutableImageComponents);

        Map<String, String> malformedTreeComponents = new LinkedHashMap<>(canonical.components());
        malformedTreeComponents.put("source_tree", "not-a-compact-digest");
        ActionKey malformedTree = withCanonicalV2Digest(
                canonical.tenantId(), malformedTreeComponents);

        Map<String, String> zeroLengthStructuredComponents =
                new LinkedHashMap<>(canonical.components());
        zeroLengthStructuredComponents.put("command", digest("").compact());
        ActionKey zeroLengthStructured = withCanonicalV2Digest(
                canonical.tenantId(), zeroLengthStructuredComponents);

        Map<String, String> emptyCommandComponents =
                new LinkedHashMap<>(canonical.components());
        emptyCommandComponents.put("command", canonicalListDigest(List.of()));
        ActionKey emptyCommand = withCanonicalV2Digest(
                canonical.tenantId(), emptyCommandComponents);

        Map<String, String> zeroLengthModelComponents =
                new LinkedHashMap<>(canonical.components());
        zeroLengthModelComponents.put("model", digest("").compact());
        ActionKey zeroLengthModel = withCanonicalV2Digest(
                canonical.tenantId(), zeroLengthModelComponents);

        assertThrows(IllegalArgumentException.class,
                () -> ActionKeyBuilder.verifyCanonical(mutableImage));
        assertThrows(IllegalArgumentException.class,
                () -> ActionKeyBuilder.verifyCanonical(malformedTree));
        assertThrows(IllegalArgumentException.class,
                () -> ActionKeyBuilder.verifyCanonical(zeroLengthStructured));
        assertThrows(IllegalArgumentException.class,
                () -> ActionKeyBuilder.verifyCanonical(emptyCommand));
        assertThrows(IllegalArgumentException.class,
                () -> ActionKeyBuilder.verifyCanonical(zeroLengthModel));
    }

    private static ActionKey withCanonicalV2Digest(
            String tenantId, Map<String, String> components
    ) {
        CasManifest.CanonicalEncoder encoder =
                new CasManifest.CanonicalEncoder(ActionKeyBuilder.CANONICAL_SCHEMA);
        components.forEach(encoder::field);
        return new ActionKey(CasDigest.of(encoder.bytes()), tenantId, components);
    }

    private static String canonicalListDigest(List<String> values) {
        CasManifest.CanonicalEncoder encoder = new CasManifest.CanonicalEncoder("list/1");
        encoder.list("items", values);
        return CasDigest.of(encoder.bytes()).compact();
    }

    @Test void minimalRequiredComponentsAcceptDirectEmptyDigestsAndStructuredEmptyValues() {
        ActionKey minimal = minimalRequired().build();

        assertEquals(0, CasDigest.parseCompact(minimal.components().get("source_tree")).sizeBytes());
        assertEquals(0, CasDigest.parseCompact(minimal.components().get("policy")).sizeBytes());
        assertEquals(ActionKeyBuilder.REQUIRED_COMPONENTS.size(), minimal.components().size());
        assertTrue(minimal.components().keySet().containsAll(ActionKeyBuilder.REQUIRED_COMPONENTS));
        assertDoesNotThrow(() -> ActionKeyBuilder.verifyCanonical(minimal));
    }

    @Test void optionalDigestsMayBeOmittedOrExplicitlyEmpty() {
        ActionKey omitted = minimalRequired().build();
        ActionKey explicitEmpty = minimalRequired()
                .prompt(Optional.empty())
                .model(Optional.empty())
                .build();
        ActionKey directEmptyPromptDigest = minimalRequired()
                .prompt(Optional.of(digest("")))
                .build();

        assertFalse(omitted.components().containsKey("prompt"));
        assertFalse(omitted.components().containsKey("model"));
        assertEquals("", explicitEmpty.components().get("prompt"));
        assertEquals("", explicitEmpty.components().get("model"));
        assertEquals(0, CasDigest.parseCompact(
                directEmptyPromptDigest.components().get("prompt")).sizeBytes());
        assertDoesNotThrow(() -> ActionKeyBuilder.verifyCanonical(omitted));
        assertDoesNotThrow(() -> ActionKeyBuilder.verifyCanonical(explicitEmpty));
        assertDoesNotThrow(() -> ActionKeyBuilder.verifyCanonical(directEmptyPromptDigest));
    }

    @Test void legalUnicodeInputsRemainCanonical() {
        ActionKey unicode = new ActionKeyBuilder()
                .tenant("租户-甲", "项目-火箭")
                .sourceTree(digest("源码-树"))
                .adapter("适配器-λ", digest("适配器"))
                .toolchainImage(PINNED_IMAGE)
                .command(List.of("构建", "--标签=你好🌍"))
                .declaredOutputs(List.of("报告/结果-✓"))
                .policy(digest("策略"))
                .permissionScope(Set.of("仓库:读取", "制品:写入"))
                .dataResidency("亚洲-东部")
                .environmentContract(ActionKeyBuilder.EnvironmentContract.of("区域"))
                .environment(Map.of("区域", "上海"))
                .build();

        assertEquals("租户-甲", unicode.tenantId());
        assertDoesNotThrow(() -> ActionKeyBuilder.verifyCanonical(unicode));
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

    @Test void modelAndRulePackCompositeBoundariesCannotCollide() {
        ActionKey modelLeft = mutated(builder -> builder.model(Optional.of(
                new ActionKeyBuilder.ModelIdentity("a", "b/c", "v1", Map.of()))));
        ActionKey modelRight = mutated(builder -> builder.model(Optional.of(
                new ActionKeyBuilder.ModelIdentity("a/b", "c", "v1", Map.of()))));
        assertNotEquals(modelLeft.digest(), modelRight.digest());

        CasDigest firstDigest = digest("first-rules");
        CasDigest secondDigest = digest("second-rules");
        ActionKey oneStructuredPack = mutated(builder -> builder.rulePacks(List.of(
                new ActionKeyBuilder.RulePackRef(
                        "a=" + firstDigest.compact() + ",b", secondDigest))));
        ActionKey twoStructuredPacks = mutated(builder -> builder.rulePacks(List.of(
                new ActionKeyBuilder.RulePackRef("a", firstDigest),
                new ActionKeyBuilder.RulePackRef("b", secondDigest))));
        assertNotEquals(oneStructuredPack.digest(), twoStructuredPacks.digest());
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
