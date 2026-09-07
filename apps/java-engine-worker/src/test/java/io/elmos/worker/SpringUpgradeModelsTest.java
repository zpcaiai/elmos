package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

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

    @Test void startRequestUsesDefaultsWhenBothTargetFieldsAreAbsent() {
        SpringUpgradeModels.StartRequest request = new SpringUpgradeModels.StartRequest(
                "org", SpringUpgradeModels.SourceMode.PUBLIC_GIT, "https://github.com/example/app",
                "main", "a".repeat(40), null, null, false, "idem", null, null);

        assertEquals(SpringUpgradeModels.TARGET_BOOT, request.targetSpringBoot());
        assertEquals(SpringUpgradeModels.TARGET_JAVA, request.targetJava());
        SpringUpgradeModels.StartRequest blankJava = new SpringUpgradeModels.StartRequest(
                "org", SpringUpgradeModels.SourceMode.PUBLIC_GIT, "https://github.com/example/app",
                "main", "a".repeat(40), null, null, false, "idem", "3.5.3", " ");
        assertEquals(SpringUpgradeModels.TARGET_JAVA, blankJava.targetJava());
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

    @Test void exactTupleAndFeatureObservationKeepUnknownNullsExplicit() {
        SpringUpgradeModels.ExactTuple unknown = new SpringUpgradeModels.ExactTuple(
                null, "11", "maven-3.9.11", "3.5.3", "21", "maven-3.9.11",
                "6.35.0", "6.44.0", null, null);
        assertEquals("unknown", unknown.sourceFrameworkFamily());
        assertEquals("UNKNOWN", unknown.sourceFrameworkVersion());
        assertNull(unknown.sourceSpringBoot());
        SpringUpgradeModels.ExactTuple blank = new SpringUpgradeModels.ExactTuple(
                null, "11", "maven-3.9.11", "3.5.3", "21", "maven-3.9.11",
                "6.35.0", "6.44.0", " ", " ");
        assertEquals("unknown", blank.sourceFrameworkFamily());
        assertEquals("UNKNOWN", blank.sourceFrameworkVersion());

        SpringUpgradeModels.ExactTuple supported =
                SpringUpgradeModels.ExactTuple.supported("maven-3.9.11", "maven-3.9.11");
        assertEquals("spring-boot", supported.sourceFrameworkFamily());
        assertEquals(SpringUpgradeModels.SOURCE_BOOT, supported.sourceFrameworkVersion());

        SpringUpgradeModels.Fingerprint fingerprint = new SpringUpgradeModels.Fingerprint(
                "UNKNOWN", "11", "maven", List.of(), List.of(), List.of(), Map.of(), null, null, null);
        assertEquals("unknown", fingerprint.sourceFrameworkFamily());
        assertEquals("UNKNOWN", fingerprint.sourceFrameworkVersion());
        assertTrue(fingerprint.features().isEmpty());
        SpringUpgradeModels.Fingerprint blankIdentity = new SpringUpgradeModels.Fingerprint(
                " ", "11", "maven", List.of(), List.of(), List.of(), Map.of(), " ", " ", List.of());
        assertEquals("unknown", blankIdentity.sourceFrameworkFamily());
        assertEquals(" ", blankIdentity.sourceFrameworkVersion());

        SpringUpgradeModels.Fingerprint nullIdentity = new SpringUpgradeModels.Fingerprint(
                null, "11", "maven", List.of(), List.of(), List.of(), Map.of(), null, null, List.of());
        assertEquals("unknown", nullIdentity.sourceFrameworkFamily());
        assertNull(nullIdentity.sourceFrameworkVersion());

        SpringUpgradeModels.FeatureObservation feature = new SpringUpgradeModels.FeatureObservation(
                "feature", "component", "domain", null, null, null, null, "", null);
        assertEquals("unknown", feature.evidenceState());
        assertEquals("fcm-required", feature.targetStrategy());
        assertTrue(feature.sourceLanguages().isEmpty());
        assertTrue(feature.sourceTraces().isEmpty());
        assertTrue(feature.targetApis().isEmpty());
        assertTrue(feature.obligations().isEmpty());
        SpringUpgradeModels.FeatureObservation blankFeature = new SpringUpgradeModels.FeatureObservation(
                "feature", "component", "domain", "", List.of(), List.of(), List.of(), "", List.of());
        assertEquals("unknown", blankFeature.evidenceState());
        assertEquals("fcm-required", blankFeature.targetStrategy());
        SpringUpgradeModels.FeatureObservation nullStrategy = new SpringUpgradeModels.FeatureObservation(
                "feature", "component", "domain", "observed", List.of(), List.of(), List.of(), null, List.of());
        assertEquals("fcm-required", nullStrategy.targetStrategy());
    }
}
