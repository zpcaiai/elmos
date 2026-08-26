package io.elmos.worker;

import io.elmos.worker.SpringRouteCatalog.EvidenceStatus;
import io.elmos.worker.SpringRouteCatalog.SpringRoute;
import io.elmos.worker.SpringUpgradeModels.BlockedException;
import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
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
        assertEquals("UNSUPPORTED_SOURCE_JAVA_VERSION",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.selectSpringMvc(
                                "5.3.39", "17", "maven", "3.5.3", "21")).code());
    }

    @Test void selectsExactIntermediateTargetsWithoutPromotingTheirEvidence() {
        var oneFive = SpringRouteCatalog.select(
                "1.5.22.RELEASE", "8", "maven", "2.7.18", "17");
        assertEquals("boot-1.5-java-8-maven-to-boot-2.7.18-java-17",
                oneFive.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, oneFive.evidence());

        var twoThree = SpringRouteCatalog.select(
                "2.3.12.RELEASE", "11", "maven", "2.7.18", "17");
        assertEquals("boot-2.0-2.6-maven-to-boot-2.7.18-java-17",
                twoThree.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, twoThree.evidence());

        var twoSeven = SpringRouteCatalog.select(
                "2.7.18", "17", "maven", "3.2.12", "17");
        assertEquals("boot-2.7-maven-to-boot-3.2.12-java-17",
                twoSeven.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, twoSeven.evidence());

        var oneFiveToThreeTwo = SpringRouteCatalog.select(
                "1.5.22.RELEASE", "8", "maven", "3.2.12", "17");
        assertEquals("boot-1.5-java-8-maven-to-boot-3.2.12-java-17",
                oneFiveToThreeTwo.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, oneFiveToThreeTwo.evidence());

        var twoThreeToThreeTwo = SpringRouteCatalog.select(
                "2.3.12.RELEASE", "11", "maven", "3.2.12", "17");
        assertEquals("boot-2.0-2.6-maven-to-boot-3.2.12-java-17",
                twoThreeToThreeTwo.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, twoThreeToThreeTwo.evidence());

        var threeOneToThreeTwo = SpringRouteCatalog.select(
                "3.1.12", "17", "maven", "3.2.12", "17");
        assertEquals("boot-3.0-3.1-maven-to-boot-3.2.12-java-17",
                threeOneToThreeTwo.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, threeOneToThreeTwo.evidence());
    }

    @Test void legacySelectorRemainsBoundToTheDefaultTarget() {
        var legacy = SpringRouteCatalog.select("2.7.18", "17", "maven");
        var exact = SpringRouteCatalog.select(
                "2.7.18", "17", "maven",
                SpringRouteCatalog.TARGET_BOOT, SpringRouteCatalog.TARGET_JAVA);
        assertEquals(exact, legacy);
        assertEquals("3.5.3", legacy.route().targetBoot());
        assertEquals("21", legacy.route().targetJava());
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
        assertEquals("SPRING_BOOT_TARGET_DOWNGRADE_REJECTED",
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

    @Test void sourceRangesAreDisjointForEachExactDirectedTarget() {
        List<SpringRoute> routes = SpringRouteCatalog.routes();
        assertTrue(routes.size() >= 15);
        for (int leftIndex = 0; leftIndex < routes.size(); leftIndex += 1) {
            for (int rightIndex = leftIndex + 1; rightIndex < routes.size(); rightIndex += 1) {
                SpringRoute left = routes.get(leftIndex);
                SpringRoute right = routes.get(rightIndex);
                if (left.sourceFamily() != right.sourceFamily()
                        || !left.buildTool().equals(right.buildTool())
                        || !left.targetBoot().equals(right.targetBoot())
                        || !left.targetJava().equals(right.targetJava())) continue;
                boolean disjoint = SpringRouteCatalog.compare(
                                left.sourceBootMaxExclusive(), right.sourceBootMinInclusive()) <= 0
                        || SpringRouteCatalog.compare(
                                right.sourceBootMaxExclusive(), left.sourceBootMinInclusive()) <= 0;
                assertTrue(disjoint,
                        "exact directed target ranges overlap: " + left.routeId() + " / " + right.routeId());
            }
        }
    }

    @Test void everyImplementedRouteShipsItsOwnRecipeResource() {
        Set<String> recipeIds = new HashSet<>();
        for (SpringRoute route : SpringRouteCatalog.routes()) {
            if (!route.implemented()) continue;
            assertTrue(recipeIds.add(route.recipeId()), "recipe ids must be unique: " + route.recipeId());
            assertNotNull(SpringRouteCatalog.class.getResourceAsStream(route.recipeResource()),
                    "missing recipe resource for " + route.routeId());
            assertTrue(Set.of("2.7.18/17", "3.2.12/17", "3.5.3/21", "4.1.0/21", "4.1.1/21")
                            .contains(route.targetBoot() + "/" + route.targetJava()),
                    "unexpected target tuple for " + route.routeId());
        }
    }

    @Test void selectsLatestBootMaintenanceRoutesIncludingBoot410Source() {
        var maven = SpringRouteCatalog.select("4.1.0", "21", "maven", "4.1.1", "21");
        assertEquals("boot-4.0-maven-to-boot-4.1.1-java-21", maven.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, maven.evidence());
        assertTrue(maven.requiresExperimentalOptIn());

        var gradle = SpringRouteCatalog.select("4.1.0", "21", "gradle", "4.1.1", "21");
        assertEquals("boot-4.0-gradle-to-boot-4.1.1-java-21", gradle.route().routeId());
        assertEquals("4.1.1", gradle.route().targetBoot());
    }

    @Test void exactSelectionRejectsMissingUnsupportedAndDowngradeTargets() {
        assertEquals("SOURCE_JAVA_VERSION_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", null, "maven")).code());
        assertEquals("TARGET_SPRING_BOOT_VERSION_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "maven", null, "17")).code());
        assertEquals("TARGET_SPRING_BOOT_VERSION_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "maven", "UNKNOWN", "17")).code());
        assertEquals("TARGET_JAVA_VERSION_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "maven", "3.2.12", null)).code());
        assertEquals("TARGET_JAVA_VERSION_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "maven", "3.2.12", "UNKNOWN")).code());
        assertEquals("TARGET_SPRING_BOOT_VERSION_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "maven", "", "17")).code());
        assertEquals("TARGET_JAVA_VERSION_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "maven", "3.2.12", "")).code());
        assertEquals("UNSUPPORTED_TARGET_SPRING_BOOT_VERSION",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "maven", "3.3.0", "17")).code());
        assertEquals("UNSUPPORTED_TARGET_JAVA_VERSION",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "maven", "3.2.12", "21")).code());
        assertEquals("SPRING_BOOT_TARGET_DOWNGRADE_REJECTED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("3.4.1", "21", "maven", "3.2.12", "17")).code());
        assertEquals("SPRING_BOOT_TARGET_DOWNGRADE_REJECTED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("2.7.18", "17", "maven", "2.7.18", "17")).code());
    }

    @Test void duplicateExactEdgesFailAsAmbiguous() {
        SpringRoute route = SpringRouteCatalog
                .byId("boot-2.7-maven-to-boot-3.2.12-java-17").orElseThrow();
        var request = SpringRouteCatalog.RouteRequest.boot(
                "2.7.18", "17", "maven", "3.2.12", "17");
        assertEquals("SPRING_ROUTE_AMBIGUOUS",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.selectFrom(List.of(route, route), request)).code());
    }

    @Test void selectsOnlyThePackBackedSpringFrameworkFiveThreeMvcEdge() {
        var selection = SpringRouteCatalog.selectSpringMvc(
                "5.3.39", "11", "maven", "3.5.3", "21");
        assertEquals("spring-framework-5.3-mvc-maven-to-boot-3.5.3-java-21",
                selection.route().routeId());
        assertEquals("spring-framework-5-3-mvc-to-spring-boot-3-5-3",
                selection.route().packKey());
        assertEquals("/rewrite/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml",
                selection.route().recipeResource());
        assertEquals("io.elmos.openrewrite.SpringFramework5_3MvcToSpringBoot3_5_3Java21",
                selection.route().recipeId());
        assertEquals(SpringRouteCatalog.SourceFamily.SPRING_MVC,
                selection.route().sourceFamily());
        assertEquals("5.3.39", selection.route().exactSourceVersion());
        assertEquals("exact:5.3.39", selection.route().sourceConstraint());
        var tuple = selection.route().tuple("5.3.39", "11");
        assertNull(tuple.sourceSpringBoot());
        assertEquals("spring-mvc", tuple.sourceFrameworkFamily());
        assertEquals("5.3.39", tuple.sourceFrameworkVersion());
        assertEquals(EvidenceStatus.PASSED_LOCAL, selection.evidence());
        assertEquals("5.3.39", selection.route().verifiedSourceBoot());
        assertEquals("11", selection.route().verifiedSourceJava());
        assertFalse(selection.requiresExperimentalOptIn());
    }

    @Test void exactMvcRouteRejectsAdjacentAndQualifiedVersions() {
        for (String unsupported : List.of("5.3.38", "5.3.40", "5.3.39-SNAPSHOT", "5.3.39.RELEASE")) {
            assertEquals("UNSUPPORTED_TARGET_SPRING_BOOT_VERSION",
                    assertThrows(BlockedException.class,
                            () -> SpringRouteCatalog.selectSpringMvc(
                                unsupported, "11", "maven", "3.5.3", "21"),
                            unsupported).code());
        }
    }

    @Test void olderSpringMvcLinesRemainDeclaredButCannotBeSelected() {
        SpringRoute inventory = SpringRouteCatalog
                .byId("spring-mvc-3.2-5.2-maven-to-boot-3.5.3-java-21").orElseThrow();
        assertEquals(EvidenceStatus.NOT_IMPLEMENTED, inventory.routeEvidence());
        assertFalse(inventory.implemented());
        assertTrue(inventory.recipeResource().isBlank());
        assertTrue(inventory.recipeId().isBlank());

        assertEquals("SPRING_ROUTE_NOT_IMPLEMENTED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.selectSpringMvc(
                                "5.2.22.RELEASE", "8", "maven", "3.5.3", "21")).code());
    }

    @Test void currentMaintenanceInventoryRemainsBlocked() {
        SpringRoute threeFive = SpringRouteCatalog
                .byId("boot-1.5-3.5.15-maven-to-boot-3.5.16-java-21").orElseThrow();

        assertEquals(EvidenceStatus.NOT_IMPLEMENTED, threeFive.routeEvidence());
        assertFalse(threeFive.implemented());
        assertTrue(threeFive.recipeResource().isBlank());
        assertTrue(threeFive.recipeId().isBlank());
        assertTrue(threeFive.verifiedSourceBoot().isBlank());
        assertTrue(threeFive.verifiedSourceJava().isBlank());
        assertEquals("3.5.16", threeFive.targetBoot());
        assertEquals("21", threeFive.targetJava());

        assertEquals("SPRING_ROUTE_NOT_IMPLEMENTED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select(
                                "3.5.3", "21", "maven", "3.5.16", "21")).code());
    }

    @Test void bootVersionsSelectTheDirectBootFourMavenEdges() {
        assertEquals("boot-1.5-maven-to-boot-4.1.0-java-21",
                SpringRouteCatalog.select("1.5.22.RELEASE", "8", "maven", "4.1.0", "21")
                        .route().routeId());
        assertEquals("boot-2.0-2.6-maven-to-boot-4.1.0-java-21",
                SpringRouteCatalog.select("2.3.12.RELEASE", "11", "maven", "4.1.0", "21")
                        .route().routeId());
        assertEquals("boot-2.7-maven-to-boot-4.1.0-java-21",
                SpringRouteCatalog.select("2.7.18", "17", "maven", "4.1.0", "21")
                        .route().routeId());
        assertEquals("boot-3.0-3.4-maven-to-boot-4.1.0-java-21",
                SpringRouteCatalog.select("3.4.1", "17", "maven", "4.1.0", "21")
                        .route().routeId());
        assertEquals("boot-3.5-maven-to-boot-4.1.0-java-21",
                SpringRouteCatalog.select("3.5.16", "21", "maven", "4.1.0", "21")
                        .route().routeId());
        assertEquals("boot-4.0-maven-to-boot-4.1.0-java-21",
                SpringRouteCatalog.select("4.0.6", "21", "maven", "4.1.0", "21")
                        .route().routeId());
    }

    @Test void bootVersionsSelectTheDirectBootFourGradleEdges() {
        assertEquals("boot-1.5-gradle-to-boot-4.1.0-java-21",
                SpringRouteCatalog.select("1.5.22.RELEASE", "8", "gradle", "4.1.0", "21")
                        .route().routeId());
        assertEquals("boot-2.x-gradle-to-boot-4.1.0-java-21",
                SpringRouteCatalog.select("2.7.18", "17", "gradle", "4.1.0", "21")
                        .route().routeId());
        assertEquals("boot-3.x-gradle-to-boot-4.1.0-java-21",
                SpringRouteCatalog.select("3.3.0", "17", "gradle", "4.1.0", "21")
                        .route().routeId());
        assertEquals("boot-4.0-gradle-to-boot-4.1.0-java-21",
                SpringRouteCatalog.select("4.0.6", "21", "gradle", "4.1.0", "21")
                        .route().routeId());
    }

    @Test void directBootFourRoutesRemainExplicitlyUnverified() {
        for (SpringRoute route : SpringRouteCatalog.routes()) {
            if (!route.targetBoot().equals("4.1.0")) continue;
            assertTrue(route.implemented(), route.routeId());
            if (route.routeId().equals("boot-3.5-maven-to-boot-4.1.0-java-21")) {
                assertEquals(EvidenceStatus.PASSED_LOCAL, route.routeEvidence(), route.routeId());
                assertEquals("3.5.3", route.verifiedSourceBoot());
                assertEquals("21", route.verifiedSourceJava());
            } else {
                assertEquals(EvidenceStatus.NOT_RUN, route.routeEvidence(), route.routeId());
            }
            assertEquals("spring-to-boot-4-1-0", route.packKey(), route.routeId());
            assertFalse(route.recipeId().isBlank(), route.routeId());
        }
    }

    @Test void genericSpringMvcCanSelectTheBootFourPreparationEdge() {
        var selection = SpringRouteCatalog.selectSpringMvc(
                "6.2.8", "17", "maven", "4.1.0", "21");
        assertEquals("spring-mvc-3.2-7.0-maven-to-boot-4.1.0-java-21",
                selection.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, selection.evidence());
        assertTrue(selection.requiresExperimentalOptIn());
        assertEquals("spring-to-boot-4-1-0", selection.route().packKey());
    }

    @Test void genericSpringFrameworkCanSelectTheBootFourPreparationEdge() {
        var selection = SpringRouteCatalog.selectSpringFramework(
                "6.2.8", "17", "maven", "4.1.0", "21");
        assertEquals("spring-framework-3.2-7.0-maven-to-boot-4.1.0-java-21",
                selection.route().routeId());
        assertEquals(EvidenceStatus.NOT_RUN, selection.evidence());
        assertTrue(selection.requiresExperimentalOptIn());
        assertEquals("spring-framework", selection.route().sourceFamily().contractValue());
    }

    @Test void bootFourSourceBoundaryAndNoOpAreRejected() {
        assertEquals("SPRING_BOOT_TARGET_DOWNGRADE_REJECTED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("4.1.1", "21", "maven", "4.1.0", "21"))
                        .code());
        assertEquals("SPRING_BOOT_TARGET_DOWNGRADE_REJECTED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.select("4.0.6", "21", "maven", "4.0.6", "21"))
                        .code());
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

    @Test void declaredCatalogDiagnosticsRemainDeterministic() {
        assertEquals("gradle, maven", SpringRouteCatalog.declaredBuildTools());
        assertTrue(SpringRouteCatalog.declaredRanges("maven").contains("["));
        assertTrue(SpringRouteCatalog.declaredRanges("gradle").contains("["));
        assertEquals("none", SpringRouteCatalog.declaredRanges("sbt"));
        assertTrue(SpringRouteCatalog.withinRange("2.7.18-SNAPSHOT", "2.7.0", "3.0.0"));
        assertFalse(SpringRouteCatalog.withinRange("3.0.0", "2.7.0", "3.0.0"));
    }

    @Test void routeSelectionRequiresAnExplicitSourceFamily() {
        assertEquals("SPRING_SOURCE_FAMILY_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.selectFrom(List.of(), null)).code());
        assertEquals("SPRING_SOURCE_FAMILY_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.selectFrom(
                                List.of(),
                                new SpringRouteCatalog.RouteRequest(
                                        null, "2.7.18", "17", "maven", "3.5.3", "21"))).code());
    }

    @Test void frameworkRoutesUseFrameworkSpecificDiagnosticsAndExactEvidenceChecks() {
        assertEquals("SPRING_FRAMEWORK_VERSION_UNRESOLVED",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.selectSpringFramework(
                                "", "17", "maven", "4.1.1", "21")).code());
        assertEquals("UNSUPPORTED_SOURCE_SPRING_FRAMEWORK_VERSION",
                assertThrows(BlockedException.class,
                        () -> SpringRouteCatalog.selectSpringMvc(
                                "3.1.9", "8", "maven", "3.5.3", "21")).code());

        SpringRoute verified = SpringRouteCatalog
                .byId("boot-2.7-maven-to-boot-3.5.3-java-21").orElseThrow();
        assertEquals(EvidenceStatus.NOT_RUN, verified.evidenceFor("2.7.18", "11"));
        assertEquals("migrated-spring-boot-3.5.3.zip", verified.artifactFileName());

        assertThrows(IllegalArgumentException.class, () -> new SpringRoute(
                "invalid-exact-route", "pack", "label", "2.7.0", "3.0.0", Set.of("17"),
                "maven", "3.5.3", "21", "/recipe.yml", "recipe", "6.35.0", "6.44.0",
                EvidenceStatus.NOT_RUN, "", "", "invalid", SpringRouteCatalog.SourceFamily.SPRING_BOOT,
                "3.0.0"));
    }

    @Test void versionUtilitiesRemainTotalForNullMalformedAndTrailingDotInputs() {
        assertEquals(0, SpringRouteCatalog.compare("2.7.", "2.7.0"));
        assertEquals(0, SpringRouteCatalog.compare("2.7.0", "2.7."));
        assertTrue(SpringRouteCatalog.compare("999999999999999999999", "1") < 0);
        assertEquals(0, SpringRouteCatalog.compare("x", "0"));
        assertEquals("", SpringRouteCatalog.normalizeJava(null));
        assertEquals("", SpringRouteCatalog.normalizeJava(""));
        assertEquals("21", SpringRouteCatalog.normalizeJava("1.21"));
        assertEquals("1.8x", SpringRouteCatalog.normalizeJava("1.8x"));
        assertEquals("1.", SpringRouteCatalog.normalizeJava("1."));
    }
}
