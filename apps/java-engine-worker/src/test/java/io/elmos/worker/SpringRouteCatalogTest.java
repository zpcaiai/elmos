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
        var gradle = SpringRouteCatalog.select("2.7.18", "17", "gradle");
        assertEquals("boot-2.x-gradle-to-boot-3.5.3-java-21", gradle.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, gradle.evidence());
        assertTrue(gradle.requiresExperimentalOptIn());
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

    /**
     * Recorded evidence must be internally consistent.
     *
     * <p>This replaced an assertion that exactly one route carried evidence.
     * That version was a count, and a count is the wrong invariant: it fails the
     * moment a second route is legitimately recorded, so the only way past it is
     * to raise the number -- which is exactly the edit someone makes without
     * thinking. What actually needs protecting is that a route claiming
     * PASSED_LOCAL names the tuple it was proven on, and that the tuple is one
     * the route would even accept. Those properties stay true no matter how many
     * routes are recorded, and they fail loudly if a status is flipped without a
     * corresponding run.
     */
    @Test void everyRecordedRouteNamesATupleItWouldAccept() {
        List<SpringRoute> verified = SpringRouteCatalog.verifiedRoutes();
        assertFalse(verified.isEmpty(), "the catalog must carry at least one recorded route");

        for (SpringRoute route : verified) {
            String boot = route.verifiedSourceBoot();
            String java = route.verifiedSourceJava();
            assertFalse(boot.isBlank(),
                    route.routeId() + " claims PASSED_LOCAL without naming a source Boot version");
            assertFalse(java.isBlank(),
                    route.routeId() + " claims PASSED_LOCAL without naming a source Java release");

            assertTrue(SpringRouteCatalog.withinRange(
                            boot, route.sourceBootMinInclusive(), route.sourceBootMaxExclusive()),
                    route.routeId() + " recorded Boot " + boot + " which is outside its own declared "
                            + "range [" + route.sourceBootMinInclusive() + ", "
                            + route.sourceBootMaxExclusive() + ")");
            assertTrue(route.sourceJavaVersions().contains(java),
                    route.routeId() + " recorded Java " + java + " which the route does not accept");

            // The recorded tuple must be the one point that reports PASSED_LOCAL.
            assertEquals(EvidenceStatus.PASSED_LOCAL, route.evidenceFor(boot, java),
                    route.routeId() + " does not report its own recorded tuple as executed");
        }
    }

    /**
     * The converse: a route without recorded execution must not carry a tuple.
     * A leftover tuple on a NOT_RUN route is how a future edit accidentally
     * promotes something -- flip the status and the claim is already sitting
     * there, looking like it was verified.
     */
    @Test void unrecordedRoutesCarryNoTuple() {
        for (SpringRoute route : SpringRouteCatalog.routes()) {
            if (route.routeEvidence() == EvidenceStatus.PASSED_LOCAL) continue;
            assertTrue(route.verifiedSourceBoot().isBlank(),
                    route.routeId() + " is " + route.routeEvidence()
                            + " but names a verified Boot version");
            assertTrue(route.verifiedSourceJava().isBlank(),
                    route.routeId() + " is " + route.routeEvidence()
                            + " but names a verified Java release");
        }
    }

    /**
     * Version matching is exact string equality, so {@code 1.5.22} and
     * {@code 1.5.22.RELEASE} are different tuples even though they are the same
     * release. That is deliberate: the conservative direction is to report
     * NOT_RUN for a string nobody executed. Loosening it would mean claiming
     * execution evidence for a version spelling that was never built.
     */
    @Test void aDifferentSpellingOfTheSameReleaseIsNotTheRecordedTuple() {
        var recorded = SpringRouteCatalog.select("1.5.22.RELEASE", "8", "maven");
        assertEquals(EvidenceStatus.PASSED_LOCAL, recorded.evidence());

        var respelled = SpringRouteCatalog.select("1.5.22", "8", "maven");
        assertEquals(recorded.route(), respelled.route());
        assertEquals(EvidenceStatus.NOT_RUN, respelled.evidence());
    }

    /** The pack the run service reports is bound to the 2.7 route specifically. */
    @Test void theTwoSevenRouteOwnsTheDeclaredPackKey() {
        SpringRoute route = SpringRouteCatalog
                .byId("boot-2.7-maven-to-boot-3.5.3-java-21").orElseThrow();
        assertEquals(SpringUpgradeModels.PACK_KEY, route.packKey());
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

    @Test void gradleRouteUsesTheGradleToolchainInItsExactTuple() {
        SpringRoute route = SpringRouteCatalog.byId("boot-2.x-gradle-to-boot-3.5.3-java-21").orElseThrow();
        var tuple = route.tuple("2.7.18", "17");
        assertEquals("gradle-8.14.3", tuple.sourceBuildTool());
        assertEquals("gradle-8.14.3", tuple.targetBuildTool());
    }
}
