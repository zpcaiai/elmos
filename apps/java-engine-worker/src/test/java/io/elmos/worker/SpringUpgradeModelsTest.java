package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringUpgradeModelsTest {
    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules();

    @Test void oldBootOnlyTupleJsonRemainsReadableWithHonestInferredIdentity() throws Exception {
        SpringUpgradeModels.ExactTuple tuple = json.readValue("""
                {
                  "sourceSpringBoot": "2.7.18",
                  "sourceJava": "17",
                  "sourceBuildTool": "maven-3.9.11",
                  "targetSpringBoot": "3.5.3",
                  "targetJava": "21",
                  "targetBuildTool": "maven-3.9.11",
                  "rewriteSpring": "6.35.0",
                  "rewriteMavenPlugin": "6.44.0"
                }
                """, SpringUpgradeModels.ExactTuple.class);

        assertEquals("spring-boot", tuple.sourceFrameworkFamily());
        assertEquals("2.7.18", tuple.sourceFrameworkVersion());
        assertEquals("2.7.18", tuple.sourceSpringBoot());
    }

    @Test void mvcTupleRoundTripKeepsFrameworkIdentityAndNullBootIdentity() throws Exception {
        SpringUpgradeModels.ExactTuple tuple = SpringRouteCatalog.selectSpringMvc(
                "5.3.39", "11", "maven", "3.5.3", "21").route().tuple("5.3.39", "11");

        JsonNode wire = json.readTree(json.writeValueAsBytes(tuple));
        assertEquals("spring-mvc", wire.path("sourceFrameworkFamily").asText());
        assertEquals("5.3.39", wire.path("sourceFrameworkVersion").asText());
        assertNull(wire.get("sourceSpringBoot").textValue());
        SpringUpgradeModels.ExactTuple restored = json.treeToValue(
                wire, SpringUpgradeModels.ExactTuple.class);
        assertNull(restored.sourceSpringBoot());
        assertEquals("spring-mvc", restored.sourceFrameworkFamily());
        assertEquals("5.3.39", restored.sourceFrameworkVersion());
    }

    @Test void mvcTupleCannotSmuggleFrameworkVersionThroughBootField() {
        assertThrows(IllegalArgumentException.class, () -> new SpringUpgradeModels.ExactTuple(
                "5.3.39", "11", "maven-3.9.11", "3.5.3", "21", "maven-3.9.11",
                "6.35.0", "6.44.0", "spring-mvc", "5.3.39"));
    }

    @Test void startRequestNormalizesLegacyJavaAndTargetDefaults() {
        SpringUpgradeModels.StartRequest request = new SpringUpgradeModels.StartRequest(
                "org", SpringUpgradeModels.SourceMode.PUBLIC_GIT, "https://github.com/example/app",
                "main", "a".repeat(40), null, null, false, "idem", "", "1.8");

        assertEquals(SpringUpgradeModels.TARGET_BOOT, request.targetSpringBoot());
        assertEquals("8", request.targetJava());
        assertEquals("idem", request.idempotencyKey());
    }

    @Test void fingerprintInfersUnknownOnlyWhenNoSourceBootIdentityExists() {
        SpringUpgradeModels.Fingerprint unknown = new SpringUpgradeModels.Fingerprint(
                "UNKNOWN", "11", "maven", java.util.List.of(), java.util.List.of(),
                java.util.List.of(), java.util.Map.of());
        SpringUpgradeModels.Fingerprint boot = new SpringUpgradeModels.Fingerprint(
                "2.7.18", "17", "maven", java.util.List.of(), java.util.List.of(),
                java.util.List.of(), java.util.Map.of());

        assertEquals("unknown", unknown.sourceFrameworkFamily());
        assertEquals("UNKNOWN", unknown.sourceFrameworkVersion());
        assertEquals("spring-boot", boot.sourceFrameworkFamily());
        assertEquals("2.7.18", boot.sourceFrameworkVersion());
    }

    @Test void exactTupleBackfillsFrameworkIdentityButRejectsBootVersionDrift() {
        SpringUpgradeModels.ExactTuple boot = new SpringUpgradeModels.ExactTuple(
                null, "17", "maven-3.9.11", "3.5.3", "21", "maven-3.9.11",
                "6.35.0", "6.44.0", "spring-boot", "2.7.18");
        SpringUpgradeModels.ExactTuple framework = new SpringUpgradeModels.ExactTuple(
                null, "11", "maven-3.9.11", "3.5.3", "21", "maven-3.9.11",
                "6.35.0", "6.44.0", "spring-framework", "5.3.39");

        assertEquals("2.7.18", boot.sourceSpringBoot());
        assertEquals("spring-framework", framework.sourceFrameworkFamily());
        assertNull(framework.sourceSpringBoot());
        assertTrue(framework.sourceFrameworkVersion().startsWith("5."));
        assertFalse(framework.sourceFrameworkVersion().isBlank());
        assertThrows(IllegalArgumentException.class, () -> new SpringUpgradeModels.ExactTuple(
                "2.7.18", "17", "maven-3.9.11", "3.5.3", "21", "maven-3.9.11",
                "6.35.0", "6.44.0", "spring-boot", "3.2.12"));
    }
}
