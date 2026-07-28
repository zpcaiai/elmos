package io.elmos.worker;

import io.elmos.worker.SpringRouteCatalog.EvidenceStatus;
import io.elmos.worker.SpringRouteCatalog.SpringRoute;
import io.elmos.worker.SpringUpgradeModels.BlockedException;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringRouteCatalogTest {

    @Test void selectsTheTwoSevenRouteForTheVerifiedTuple() {
        var selection = SpringRouteCatalog.select("2.7.18", "17", "maven");
        assertEquals("boot-2.7-maven-to-boot-3.5.3-java-21", selection.route().routeId());
        assertEquals(EvidenceStatus.PASSED_LOCAL, selection.evidence());
        assertFalse(selection.requiresExperimentalOptIn());
    }

    @Test void otherTuplesInsideTheSameRouteRemainNotRun() {
        var selection = SpringRouteCatalog.select("2.7.5", "11", "maven");
        assertEquals("boot-2.7-maven-to-boot-3.5.3-java-21", selection.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, selection.evidence());
        assertTrue(selection.requiresExperimentalOptIn());
    }

    @Test void coversTheLegacyBootLines() {
        assertEquals("boot-1.5-java-8-maven-to-boot-3.5.3-java-21",
                SpringRouteCatalog.select("1.5.22", "1.8", "maven").route().routeId());
        assertEquals("boot-2.0-2.6-maven-to-boot-3.5.3-java-21",
                SpringRouteCatalog.select("2.3.12", "11", "maven").route().routeId());
        assertEquals("boot-2.0-2.6-maven-to-boot-3.5.3-java-21",
                SpringRouteCatalog.select("2.6.15", "17", "maven").route().routeId());
        assertEquals("boot-3.0-3.4-maven-to-boot-3.5.3-java-21",
                SpringRouteCatalog.select("3.4.1", "17", "maven").route().routeId());
    }

    @Test void toleratesQualifiedReleaseNumbers() {
        assertEquals("boot-2.7-maven-to-boot-3.5.3-java-21",
                SpringRouteCatalog.select("2.7.18-SNAPSHOT", "17", "maven").route().routeId());
        assertEquals("boot-1.5-java-8-maven-to-boot-3.5.3-java-21",
                SpringRouteCatalog.select("1.5.9.RELEASE", "8", "maven").route().routeId());
    }

    @Test void normalizesLegacyJavaReleaseNames() {
        assertEquals("8", SpringRouteCatalog.normalizeJava("1.8"));
        assertEquals("17", SpringRouteCatalog.normalizeJava(" 17 "));
        assertEquals("21", SpringRouteCatalog.normalizeJava("21"));
    }

    @Test void blocksWithASpecificReasonPerFailure() {
        assertEquals("SPRING_BOOT_VERSION_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("UNKNOWN", "17", "maven")).code());
        assertEquals("SOURCE_JAVA_VERSION_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "UNKNOWN", "maven")).code());
        assertEquals("UNSUPPORTED_BUILD_TOOL",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "sbt")).code());
        assertEquals("UNSUPPORTED_SOURCE_BOOT_VERSION",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("1.4.7", "8", "maven")).code());
        assertEquals("UNSUPPORTED_SOURCE_BOOT_VERSION",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("3.5.3", "21", "maven")).code());
        assertEquals("UNSUPPORTED_SOURCE_JAVA_VERSION",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("1.5.22", "17", "maven")).code());
        assertEquals("SPRING_ROUTE_NOT_IMPLEMENTED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "gradle")).code());
    }

    @Test void mavenSourceRangesAreDisjointAndOrdered() {
        List<SpringRoute> maven = SpringRouteCatalog.routes().stream()
                .filter(route -> route.buildTool().equals(SpringRouteCatalog.MAVEN_BUILD_TOOL))
                .toList();
        assertTrue(maven.size() >= 4);
        List<SpringRoute> sorted = new ArrayList<>(maven);
        sorted.sort((left, right) -> SpringRouteCatalog.compare(
                left.sourceBootMinInclusive(), right.sourceBootMinInclusive()));
        for (int index = 0; index + 1 < sorted.size(); index += 1) {
            assertTrue(SpringRouteCatalog.compare(
                            sorted.get(index).sourceBootMaxExclusive(),
                            sorted.get(index + 1).sourceBootMinInclusive()) <= 0,
                    "maven source ranges must not overlap");
        }
    }

    @Test void everyImplementedRouteShipsItsOwnRecipeResource() {
        Set<String> recipeIds = new HashSet<>();
        for (SpringRoute route : SpringRouteCatalog.routes()) {
            if (!route.implemented()) continue;
            assertTrue(recipeIds.add(route.recipeId()), "recipe ids must be unique: " + route.recipeId());
            assertNotNull(SpringRouteCatalog.class.getResourceAsStream(route.recipeResource()),
                    "missing recipe resource for " + route.routeId());
            assertEquals(SpringRouteCatalog.TARGET_BOOT, route.targetBoot());
            assertEquals(SpringRouteCatalog.TARGET_JAVA, route.targetJava());
        }
    }

    @Test void exactlyOneRouteCarriesRecordedEvidence() {
        List<SpringRoute> verified = SpringRouteCatalog.routes().stream()
                .filter(route -> route.routeEvidence() == EvidenceStatus.PASSED_LOCAL)
                .toList();
        assertEquals(1, verified.size());
        SpringRoute route = verified.get(0);
        assertEquals("2.7.18", route.verifiedSourceBoot());
        assertEquals("17", route.verifiedSourceJava());
        assertEquals(SpringUpgradeModels.PACK_KEY, route.packKey());
        assertEquals(route, SpringRouteCatalog.verifiedRoute());
    }

    @Test void javaReleaseDetectionSpansBothVersionSchemes() {
        // Java 9 onwards: openjdk version "21.0.11"
        assertTrue(LocalSpringUpgradeExecutionPort.reportsJavaRelease(
                "openjdk version \"21.0.11\" 2024-04-16", 21));
        assertTrue(LocalSpringUpgradeExecutionPort.reportsJavaRelease(
                "openjdk version \"17.0.11\" 2024-04-16", 17));
        // Java 8 and earlier keep the legacy 1.N form, which a legacy estate
        // needs in order to build its source baseline at all.
        assertTrue(LocalSpringUpgradeExecutionPort.reportsJavaRelease(
                "openjdk version \"1.8.0_432\"\nOpenJDK Runtime Environment Corretto-8.432.06.1", 8));
        assertTrue(LocalSpringUpgradeExecutionPort.reportsJavaRelease("java version \"1.8.0\"", 8));

        assertFalse(LocalSpringUpgradeExecutionPort.reportsJavaRelease(
                "openjdk version \"11.0.26\" 2025-01-21", 8));
        assertFalse(LocalSpringUpgradeExecutionPort.reportsJavaRelease(
                "openjdk version \"1.8.0_432\"", 11));
        // The legacy form is only meaningful up to 8; "1.21" is not a Java 21.
        assertFalse(LocalSpringUpgradeExecutionPort.reportsJavaRelease("openjdk version \"1.21.0\"", 21));
        assertFalse(LocalSpringUpgradeExecutionPort.reportsJavaRelease(null, 21));
    }

    @Test void routeIdsAreUniqueAndResolvable() {
        Set<String> ids = new HashSet<>();
        for (SpringRoute route : SpringRouteCatalog.routes()) {
            assertTrue(ids.add(route.routeId()), "duplicate route id " + route.routeId());
            assertEquals(route, SpringRouteCatalog.byId(route.routeId()).orElseThrow());
        }
        assertTrue(SpringRouteCatalog.byId("does-not-exist").isEmpty());
    }
}
