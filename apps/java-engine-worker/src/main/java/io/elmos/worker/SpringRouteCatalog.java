package io.elmos.worker;

import io.elmos.worker.SpringUpgradeModels.BlockedException;

import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;

/**
 * The authority for every legacy Spring source line this engine can modernize.
 *
 * <p>Before this catalog existed the engine accepted exactly one tuple, so any
 * repository that was not Spring Boot 2.7.18 on Java 17 with Maven was blocked
 * at FINGERPRINT with a message that named a single version. Real legacy
 * estates are spread across Boot 1.5 through 3.4 on Java 8, 11, 17 and 21, and
 * some still use Spring MVC without Spring Boot. Routes are selected from a
 * directed source/target matrix instead of asserted or inferred from a single
 * target.
 *
 * <p>Widening the catalog does not widen the evidence. Each route records the
 * exact tuple that has actually been executed locally; every other tuple inside
 * the same route stays {@code NOT_RUN} and is refused unless the operator has
 * explicitly enabled experimental routes. A route is therefore a statement
 * about what the pipeline can attempt, never a statement about what has passed.
 */
final class SpringRouteCatalog {
    private SpringRouteCatalog() {}

    static final String TARGET_BOOT = "3.5.3";
    static final String TARGET_JAVA = "21";
    static final String TARGET_BOOT_2_7 = "2.7.18";
    static final String TARGET_BOOT_3_2 = "3.2.12";
    static final String TARGET_BOOT_3_5_16 = "3.5.16";
    static final String TARGET_BOOT_4_1 = "4.1.0";
    static final String TARGET_JAVA_17 = "17";
    static final String REWRITE_SPRING = "6.35.0";
    static final String REWRITE_MAVEN_PLUGIN = "6.44.0";
    static final String MAVEN_BUILD_TOOL = "maven";
    static final String GRADLE_BUILD_TOOL = "gradle";
    static final String MAVEN_TOOLCHAIN = "maven-3.9.11";
    static final String GRADLE_TOOLCHAIN = "gradle-8.14.3";

    /** The source framework family is part of the directed route identity. */
    enum SourceFamily {
        SPRING_BOOT("spring-boot"),
        SPRING_MVC("spring-mvc");

        private final String contractValue;

        SourceFamily(String contractValue) {
            this.contractValue = contractValue;
        }

        String contractValue() {
            return contractValue;
        }
    }

    /** Evidence a route carries for a specific detected tuple. */
    enum EvidenceStatus {
        /** The exact tuple has been executed end to end on a real repository. */
        PASSED_LOCAL,
        /** The route can drive this tuple, but no run has been recorded for it. */
        NOT_RUN,
        /** The route is declared for inventory purposes and has no driver yet. */
        NOT_IMPLEMENTED
    }

    record SpringRoute(
            String routeId,
            String packKey,
            String label,
            String sourceBootMinInclusive,
            String sourceBootMaxExclusive,
            Set<String> sourceJavaVersions,
            String buildTool,
            String targetBoot,
            String targetJava,
            String recipeResource,
            String recipeId,
            String rewriteSpring,
            String rewriteMavenPlugin,
            EvidenceStatus routeEvidence,
            String verifiedSourceBoot,
            String verifiedSourceJava,
            String notes,
            SourceFamily sourceFamily,
            String exactSourceVersion
    ) {
        SpringRoute {
            sourceJavaVersions = Set.copyOf(sourceJavaVersions);
            exactSourceVersion = normalize(exactSourceVersion);
            if (!exactSourceVersion.isEmpty()
                    && !withinRange(exactSourceVersion, sourceBootMinInclusive, sourceBootMaxExclusive)) {
                throw new IllegalArgumentException(
                        "exact source version must be inside the route's declared range");
            }
        }

        SpringRoute(
                String routeId,
                String packKey,
                String label,
                String sourceBootMinInclusive,
                String sourceBootMaxExclusive,
                Set<String> sourceJavaVersions,
                String buildTool,
                String targetBoot,
                String targetJava,
                String recipeResource,
                String recipeId,
                String rewriteSpring,
                String rewriteMavenPlugin,
                EvidenceStatus routeEvidence,
                String verifiedSourceBoot,
                String verifiedSourceJava,
                String notes,
                SourceFamily sourceFamily
        ) {
            this(routeId, packKey, label, sourceBootMinInclusive, sourceBootMaxExclusive,
                    sourceJavaVersions, buildTool, targetBoot, targetJava, recipeResource,
                    recipeId, rewriteSpring, rewriteMavenPlugin, routeEvidence,
                    verifiedSourceBoot, verifiedSourceJava, notes, sourceFamily, "");
        }

        boolean implemented() {
            return routeEvidence != EvidenceStatus.NOT_IMPLEMENTED;
        }

        /**
         * The detected tuple has recorded execution evidence only when it is
         * the exact point the route was proven on. Everything else inside the
         * accepted range remains NOT_RUN.
         */
        EvidenceStatus evidenceFor(String bootVersion, String javaVersion) {
            if (routeEvidence != EvidenceStatus.PASSED_LOCAL) return routeEvidence;
            return verifiedSourceBoot.equals(bootVersion) && verifiedSourceJava.equals(javaVersion)
                    ? EvidenceStatus.PASSED_LOCAL
                    : EvidenceStatus.NOT_RUN;
        }

        boolean acceptsSourceVersion(String sourceVersion) {
            return exactSourceVersion.isEmpty()
                    ? withinRange(sourceVersion, sourceBootMinInclusive, sourceBootMaxExclusive)
                    : exactSourceVersion.equals(normalize(sourceVersion));
        }

        String sourceConstraint() {
            return exactSourceVersion.isEmpty()
                    ? "[" + sourceBootMinInclusive + ", " + sourceBootMaxExclusive + ")"
                    : "exact:" + exactSourceVersion;
        }

        String artifactFileName() {
            return "migrated-spring-boot-" + targetBoot + ".zip";
        }

        SpringUpgradeModels.ExactTuple tuple(String detectedBoot, String detectedJava) {
            String toolchain = GRADLE_BUILD_TOOL.equals(buildTool) ? GRADLE_TOOLCHAIN : MAVEN_TOOLCHAIN;
            return new SpringUpgradeModels.ExactTuple(
                    sourceFamily == SourceFamily.SPRING_BOOT ? detectedBoot : null,
                    detectedJava, toolchain,
                    targetBoot, targetJava, toolchain,
                    rewriteSpring, rewriteMavenPlugin,
                    sourceFamily.contractValue(), detectedBoot);
        }
    }

    /**
     * Exact directed selection request. The target tuple is never inferred by
     * this type: callers that expose target choice must provide both Boot and
     * Java, while the legacy three-argument selector below deliberately binds
     * to the current 3.5.3 / Java 21 execution path.
     */
    record RouteRequest(
            SourceFamily sourceFamily,
            String sourceVersion,
            String sourceJava,
            String buildTool,
            String targetBoot,
            String targetJava
    ) {
        static RouteRequest boot(String sourceBoot, String sourceJava, String buildTool,
                                 String targetBoot, String targetJava) {
            return new RouteRequest(SourceFamily.SPRING_BOOT, sourceBoot, sourceJava,
                    buildTool, targetBoot, targetJava);
        }

        static RouteRequest springMvc(String sourceSpringFramework, String sourceJava,
                                      String buildTool, String targetBoot, String targetJava) {
            return new RouteRequest(SourceFamily.SPRING_MVC, sourceSpringFramework, sourceJava,
                    buildTool, targetBoot, targetJava);
        }
    }

    private static final List<SpringRoute> ROUTES = List.of(
            new SpringRoute(
                    "boot-1.5-java-8-maven-to-boot-2.7.18-java-17",
                    "spring-boot-1-5-to-2-7-18",
                    "Spring Boot 1.5.x / Java 8 / Maven → Boot 2.7.18 / Java 17",
                    "1.5.0", "2.0.0", Set.of("8"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT_2_7, TARGET_JAVA_17,
                    "/rewrite/spring-boot-1.5-to-2.7.18.yml",
                    "io.elmos.openrewrite.SpringBoot1_5ToBoot2_7_18Java17",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_RUN, "", "",
                    "Steps through Boot 2.0 and 2.7 and moves Java 8 to Java 17. "
                            + "Security defaults, legacy Actuator paths, javax validation and custom "
                            + "auto-configuration remain explicit runtime obligations. No exact tuple "
                            + "on this edge has execution evidence.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-1.5-java-8-maven-to-boot-3.5.3-java-21",
                    "spring-boot-1-5-to-3-5-3",
                    "Spring Boot 1.5.x / Java 8 / Maven",
                    "1.5.0", "2.0.0", Set.of("8"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "/rewrite/spring-boot-1.5-to-3.5.3.yml",
                    "io.elmos.openrewrite.SpringBoot1_5ToBoot3_5_3Java21",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.PASSED_LOCAL, "1.5.22.RELEASE", "8",
                    "Chains the 2.0, 2.7 and 3.5 Boot migrations with the Java 8 to 21 migration. "
                            + "javax to jakarta, removed 1.5 auto-configuration and Actuator endpoint "
                            + "renames frequently need manual review after the deterministic pass. "
                            + "Recorded on Boot 1.5.22.RELEASE / Java 8 with health served at /health, "
                            + "which is where the pre-2.0 Actuator publishes it. Nothing here exercises "
                            + "org.hibernate.validator.constraints.* -- those constraints were removed in "
                            + "Hibernate Validator 7 and their migration is unproven.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-1.5-java-8-maven-to-boot-3.2.12-java-17",
                    "spring-boot-1-5-to-3-2-12",
                    "Spring Boot 1.5.x / Java 8 / Maven → Boot 3.2.12 / Java 17",
                    "1.5.0", "2.0.0", Set.of("8"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT_3_2, TARGET_JAVA_17,
                    "/rewrite/spring-boot-1.5-to-3.2.12.yml",
                    "io.elmos.openrewrite.SpringBoot1_5ToBoot3_2_12Java17",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_RUN, "", "",
                    "Steps through Boot 2.0, 2.7 and 3.2 before pinning Java 17. Security, "
                            + "Jakarta, persistence, transaction and messaging behavior has not run "
                            + "for any exact source tuple on this directed edge.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-2.0-2.6-maven-to-boot-2.7.18-java-17",
                    "spring-boot-2-0-2-6-to-2-7-18",
                    "Spring Boot 2.0–2.6 / Java 8, 11, 17 / Maven → Boot 2.7.18 / Java 17",
                    "2.0.0", "2.7.0", Set.of("8", "11", "17"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT_2_7, TARGET_JAVA_17,
                    "/rewrite/spring-boot-2.0-2.6-to-2.7.18.yml",
                    "io.elmos.openrewrite.SpringBoot2_0To2_6ToBoot2_7_18Java17",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_RUN, "", "",
                    "Applies the ordered 2.x migrations and pins Boot 2.7.18 / Java 17. "
                            + "Authentication, persistence, transaction and messaging behavior must be "
                            + "exercised before any exact tuple on this edge can advance beyond NOT_RUN.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-2.0-2.6-maven-to-boot-3.2.12-java-17",
                    "spring-boot-2-0-2-6-to-3-2-12",
                    "Spring Boot 2.0–2.6 / Java 8, 11, 17 / Maven → Boot 3.2.12 / Java 17",
                    "2.0.0", "2.7.0", Set.of("8", "11", "17"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT_3_2, TARGET_JAVA_17,
                    "/rewrite/spring-boot-2.0-2.6-to-3.2.12.yml",
                    "io.elmos.openrewrite.SpringBoot2_0To2_6ToBoot3_2_12Java17",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_RUN, "", "",
                    "Applies the ordered Boot 2.7 and Boot 3.2 migrations and pins Java 17. "
                            + "Security 6, ORM/provider, transaction, serialization and message "
                            + "delivery contracts remain NOT_RUN.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-2.0-2.6-maven-to-boot-3.5.3-java-21",
                    "spring-boot-2-0-2-6-to-3-5-3",
                    "Spring Boot 2.0–2.6 / Java 8, 11, 17 / Maven",
                    "2.0.0", "2.7.0", Set.of("8", "11", "17"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "/rewrite/spring-boot-2.0-2.6-to-3.5.3.yml",
                    "io.elmos.openrewrite.SpringBoot2_0To2_6ToBoot3_5_3Java21",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.PASSED_LOCAL, "2.3.12.RELEASE", "11",
                    "Steps through Boot 2.7 before 3.5 so the intermediate deprecations are applied "
                            + "in order. Sources below Java 17 additionally cross the Boot 3 baseline. "
                            + "Recorded on Boot 2.3.12.RELEASE / Java 11.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-2.7-maven-to-boot-3.2.12-java-17",
                    "spring-boot-2-7-to-3-2-12",
                    "Spring Boot 2.7.x / Java 8, 11, 17 / Maven → Boot 3.2.12 / Java 17",
                    "2.7.0", "2.8.0", Set.of("8", "11", "17"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT_3_2, TARGET_JAVA_17,
                    "/rewrite/spring-boot-2.7-to-3.2.12.yml",
                    "io.elmos.openrewrite.SpringBoot2_7ToBoot3_2_12Java17",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_RUN, "", "",
                    "Crosses the javax-to-jakarta and Spring Security 5-to-6 boundaries while "
                            + "retaining Java 17. Database provider, transaction, serialization and "
                            + "message-delivery contracts are required runtime checks. No exact tuple "
                            + "on this edge has execution evidence.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-2.7-maven-to-boot-3.5.3-java-21",
                    "spring-boot-2-7-18-to-3-5-3",
                    "Spring Boot 2.7.x / Java 8, 11, 17 / Maven",
                    "2.7.0", "2.8.0", Set.of("8", "11", "17"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "/rewrite/spring-boot-2.7.18-to-3.5.3.yml",
                    "io.elmos.openrewrite.SpringBoot2_7_18To3_5_3Java21",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.PASSED_LOCAL, "2.7.18", "17",
                    "Recorded on Boot 2.7.18 / Java 17, the first tuple this engine executed "
                            + "end to end.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-3.0-3.1-maven-to-boot-3.2.12-java-17",
                    "spring-boot-3-0-3-1-to-3-2-12",
                    "Spring Boot 3.0–3.1 / Java 17 / Maven → Boot 3.2.12 / Java 17",
                    "3.0.0", "3.2.0", Set.of("17"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT_3_2, TARGET_JAVA_17,
                    "/rewrite/spring-boot-3.0-3.1-to-3.2.12.yml",
                    "io.elmos.openrewrite.SpringBoot3_0To3_1ToBoot3_2_12Java17",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_RUN, "", "",
                    "Already on the Jakarta and Java 17 baselines; applies the ordered Boot 3.2 "
                            + "migration only. Exact security, data, transaction and messaging "
                            + "behavior evidence remains NOT_RUN.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-3.0-3.4-maven-to-boot-3.5.3-java-21",
                    "spring-boot-3-0-3-4-to-3-5-3",
                    "Spring Boot 3.0–3.4 / Java 17, 21 / Maven",
                    "3.0.0", "3.5.0", Set.of("17", "21"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "/rewrite/spring-boot-3.0-3.4-to-3.5.3.yml",
                    "io.elmos.openrewrite.SpringBoot3_0To3_4ToBoot3_5_3Java21",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.PASSED_LOCAL, "3.4.1", "17",
                    "Already on the jakarta baseline; the pass is limited to the 3.5 migration and "
                            + "the Java 21 language and API migration. Recorded on Boot 3.4.1 / Java 17.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-1.5-3.5.15-maven-to-boot-3.5.16-java-21",
                    "spring-boot-1-5-3-5-15-to-3-5-16-inventory-only",
                    "Spring Boot 1.5–3.5.15 / Java 8, 11, 17, 21 / Maven → Boot 3.5.16 / Java 21",
                    "1.5.0", "3.5.16", Set.of("8", "11", "17", "21"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT_3_5_16, TARGET_JAVA,
                    "", "",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_IMPLEMENTED, "", "",
                    "Inventory-only current maintenance target. No exact pinned OpenRewrite "
                            + "composition, executable Batch 30 pack or source/target runtime evidence "
                            + "exists for Boot 3.5.16 / Java 21, so selection must fail closed. The "
                            + "existing Boot 3.5.3 routes and their recorded evidence remain unchanged.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-1.5-4.0-maven-to-boot-4.1.0-java-21",
                    "spring-boot-1-5-4-0-to-4-1-0-inventory-only",
                    "Spring Boot 1.5–4.0 / Java 8, 11, 17, 21 / Maven → Boot 4.1.0 / Java 21",
                    "1.5.0", "4.1.0", Set.of("8", "11", "17", "21"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT_4_1, TARGET_JAVA,
                    "", "",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_IMPLEMENTED, "", "",
                    "Inventory-only latest target. No exact pinned OpenRewrite composition, "
                            + "executable Batch 30 pack or source/target runtime evidence exists for "
                            + "Boot 4.1.0 / Java 21, so selection must fail closed.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "boot-2.x-gradle-to-boot-3.5.3-java-21",
                    "spring-boot-2-x-gradle-to-3-5-3",
                    "Spring Boot 2.x / Gradle",
                    "2.0.0", "3.0.0", Set.of("8", "11", "17"), GRADLE_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "/rewrite/spring-boot-2.x-gradle-to-3.5.3.yml",
                    "io.elmos.openrewrite.SpringBoot2xGradleToBoot3_5_3Java21",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_RUN, "", "",
                    "Gradle execution is now wired through the approved Gradle 8.14.3 driver. "
                            + "The exact source tuple remains NOT_RUN until a real Gradle project with "
                            + "an OpenRewrite Gradle plugin/recipe dependency passes baseline, rewrite, "
                            + "target build and loopback startup evidence.",
                    SourceFamily.SPRING_BOOT),
            new SpringRoute(
                    "spring-mvc-3.2-5.2-maven-to-boot-3.5.3-java-21",
                    "spring-framework-3-2-5-2-mvc-to-spring-boot-3-5-3",
                    "Spring MVC non-Boot 3.2–5.2 / Maven → Boot 3.5.3 / Java 21",
                    "3.2.0", "5.3.0", Set.of("8", "11", "17"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "", "",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_IMPLEMENTED, "", "",
                    "Inventory-only declaration. No exact Batch 30 pack or execution driver exists "
                            + "for Spring Framework 3.2 through 5.2, so route selection must fail closed.",
                    SourceFamily.SPRING_MVC),
            new SpringRoute(
                    "spring-framework-5.3-mvc-maven-to-boot-3.5.3-java-21",
                    "spring-framework-5-3-mvc-to-spring-boot-3-5-3",
                    "Spring Framework 5.3.39 MVC / Java 11 / Maven → Boot 3.5.3 / Java 21",
                    "5.3.39", "5.3.40", Set.of("11"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "/rewrite/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml",
                    "io.elmos.openrewrite.SpringFramework5_3MvcToSpringBoot3_5_3Java21",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.PASSED_LOCAL, "5.3.39", "11",
                    "Binds the runtime directory to the exact experimental Batch 30 Spring "
                            + "Framework 5.3 MVC pack. The exact checked-in fixture passed local "
                            + "source/target build, Tomcat/WarLauncher startup and bounded HTTP/JSP "
                            + "oracles only; customer, holdout, complex provider and independent "
                            + "evidence remain NOT_RUN and the pack remains NOT_CERTIFIED.",
                    SourceFamily.SPRING_MVC,
                    "5.3.39")
    );

    static List<SpringRoute> routes() {
        return ROUTES;
    }

    static Optional<SpringRoute> byId(String routeId) {
        return ROUTES.stream().filter(route -> route.routeId().equals(routeId)).findFirst();
    }

    /**
     * Every route that carries recorded local execution evidence.
     *
     * <p>This replaced a singular {@code verifiedRoute()} that returned
     * {@code findFirst()}. While exactly one route was recorded that was
     * harmless; with four it would have silently returned whichever route
     * happened to sit earliest in the list, so a caller asking "the verified
     * route" would have got an arbitrary answer that still looked authoritative.
     * Returning the set forces the caller to say which one it means.
     */
    static List<SpringRoute> verifiedRoutes() {
        return ROUTES.stream()
                .filter(route -> route.routeEvidence() == EvidenceStatus.PASSED_LOCAL)
                .toList();
    }

    record Selection(SpringRoute route, EvidenceStatus evidence) {
        boolean requiresExperimentalOptIn() {
            return evidence != EvidenceStatus.PASSED_LOCAL;
        }
    }

    /**
     * Preserve the existing execution contract: fingerprints that do not yet
     * carry a requested target continue to select the 3.5.3 / Java 21 edge.
     * New target-aware callers must use the exact overload or RouteRequest.
     */
    static Selection select(String bootVersion, String javaVersion, String buildTool) {
        return select(RouteRequest.boot(
                bootVersion, javaVersion, buildTool, TARGET_BOOT, TARGET_JAVA));
    }

    /** Select an exact Boot source-to-target edge. */
    static Selection select(String bootVersion, String javaVersion, String buildTool,
                            String targetBoot, String targetJava) {
        return select(RouteRequest.boot(
                bootVersion, javaVersion, buildTool, targetBoot, targetJava));
    }

    /** Select the explicitly declared non-Boot Spring MVC modernization edge. */
    static Selection selectSpringMvc(String springFrameworkVersion, String javaVersion,
                                     String buildTool, String targetBoot, String targetJava) {
        return select(RouteRequest.springMvc(
                springFrameworkVersion, javaVersion, buildTool, targetBoot, targetJava));
    }

    static Selection select(RouteRequest request) {
        return selectFrom(ROUTES, request);
    }

    /**
     * Choose an exact directed route from a supplied catalog. Keeping the
     * catalog parameter package-private lets regression tests prove that an
     * accidental duplicate/overlap fails closed rather than relying only on a
     * static no-overlap assertion.
     */
    static Selection selectFrom(List<SpringRoute> catalog, RouteRequest request) {
        if (request == null || request.sourceFamily() == null) {
            throw new BlockedException("SPRING_SOURCE_FAMILY_UNRESOLVED",
                    "The source Spring framework family must be explicit.");
        }

        SourceFamily family = request.sourceFamily();
        String source = normalize(request.sourceVersion());
        String java = normalizeJava(request.sourceJava());
        String build = normalize(request.buildTool()).toLowerCase(Locale.ROOT);
        String targetBoot = normalize(request.targetBoot());
        String targetJava = normalizeJava(request.targetJava());

        if (source.isEmpty() || "unknown".equals(source.toLowerCase(Locale.ROOT))) {
            String code = family == SourceFamily.SPRING_BOOT
                    ? "SPRING_BOOT_VERSION_UNRESOLVED"
                    : "SPRING_FRAMEWORK_VERSION_UNRESOLVED";
            throw new BlockedException(code,
                    "The " + family.contractValue() + " source version could not be resolved; "
                            + "an exact source version is required for route selection.");
        }
        if (java.isEmpty() || "unknown".equals(java.toLowerCase(Locale.ROOT))) {
            throw new BlockedException("SOURCE_JAVA_VERSION_UNRESOLVED",
                    "The source Java release could not be resolved from the build model; "
                            + "the route cannot be selected without an exact source JDK.");
        }
        if (targetBoot.isEmpty() || "unknown".equals(targetBoot.toLowerCase(Locale.ROOT))) {
            throw new BlockedException("TARGET_SPRING_BOOT_VERSION_UNRESOLVED",
                    "The target Spring Boot version must be requested explicitly.");
        }
        if (targetJava.isEmpty() || "unknown".equals(targetJava.toLowerCase(Locale.ROOT))) {
            throw new BlockedException("TARGET_JAVA_VERSION_UNRESOLVED",
                    "The target Java release must be requested explicitly.");
        }
        if (family == SourceFamily.SPRING_BOOT && compare(targetBoot, source) <= 0) {
            throw new BlockedException("SPRING_BOOT_TARGET_DOWNGRADE_REJECTED",
                    "Target Spring Boot " + targetBoot + " must be newer than source Spring Boot "
                            + source + "; downgrade and no-op routes are not declared by the "
                            + "modernization catalog.");
        }

        List<SpringRoute> buildMatches = catalog.stream()
                .filter(route -> route.sourceFamily() == family)
                .filter(route -> route.buildTool().equals(build))
                .toList();
        if (buildMatches.isEmpty()) {
            throw new BlockedException("UNSUPPORTED_BUILD_TOOL",
                    "No " + family.contractValue() + " route is declared for build tool '" + build
                            + "'. Declared build tools: " + declaredBuildTools(catalog, family) + ".");
        }

        List<SpringRoute> sourceMatches = buildMatches.stream()
                .filter(route -> route.acceptsSourceVersion(source))
                .toList();
        if (sourceMatches.isEmpty()) {
            String code = family == SourceFamily.SPRING_BOOT
                    ? "UNSUPPORTED_SOURCE_BOOT_VERSION"
                    : "UNSUPPORTED_SOURCE_SPRING_FRAMEWORK_VERSION";
            throw new BlockedException(code,
                    family.contractValue() + " " + source
                            + " is outside every declared source range for " + build
                            + ". Declared ranges: " + declaredRanges(catalog, family, build) + ".");
        }

        // Resolve the exact target before checking its source-Java domain.
        // Inventory-only edges for other targets must not change diagnostics or
        // make an existing executable target appear to accept a wider source
        // JDK merely because the broad inventory declaration lists it.
        List<SpringRoute> targetBootMatches = sourceMatches.stream()
                .filter(route -> route.targetBoot().equals(targetBoot))
                .toList();
        if (targetBootMatches.isEmpty()) {
            throw new BlockedException("UNSUPPORTED_TARGET_SPRING_BOOT_VERSION",
                    "No exact target Spring Boot " + targetBoot + " edge is declared for "
                            + family.contractValue() + " " + source + " / Java " + java
                            + ". Declared target tuples: " + declaredTargets(sourceMatches) + ".");
        }

        List<SpringRoute> targetJavaMatches = targetBootMatches.stream()
                .filter(route -> route.targetJava().equals(targetJava))
                .toList();
        if (targetJavaMatches.isEmpty()) {
            throw new BlockedException("UNSUPPORTED_TARGET_JAVA_VERSION",
                    "Target Spring Boot " + targetBoot + " is declared, but not with Java "
                            + targetJava + ". Declared target tuples: "
                            + declaredTargets(targetBootMatches) + ".");
        }

        List<SpringRoute> exactMatches = targetJavaMatches.stream()
                .filter(route -> route.sourceJavaVersions().contains(java))
                .toList();
        if (exactMatches.isEmpty()) {
            throw new BlockedException("UNSUPPORTED_SOURCE_JAVA_VERSION",
                    "The exact " + family.contractValue() + " target route does not accept source Java "
                            + java + ". Accepted releases: "
                            + declaredSourceJava(targetJavaMatches) + ".");
        }
        if (exactMatches.size() > 1) {
            // Overlapping ranges for the same full directed tuple are a catalog defect.
            throw new BlockedException("SPRING_ROUTE_AMBIGUOUS",
                    family.contractValue() + " " + source + " / Java " + java + " / " + build
                            + " → Boot " + targetBoot + " / Java " + targetJava
                            + " matched more than one declared route; exact directed edges must be unique.");
        }

        SpringRoute route = exactMatches.get(0);
        if (!route.implemented()) {
            throw new BlockedException("SPRING_ROUTE_NOT_IMPLEMENTED",
                    "Route " + route.routeId() + " is declared but has no execution driver: "
                            + route.notes());
        }
        return new Selection(route, route.evidenceFor(source, java));
    }

    static String declaredBuildTools() {
        return String.join(", ", sortedStrings(ROUTES.stream().map(SpringRoute::buildTool)
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new))));
    }

    private static String declaredBuildTools(List<SpringRoute> catalog, SourceFamily family) {
        return String.join(", ", sortedStrings(catalog.stream()
                .filter(route -> route.sourceFamily() == family)
                .map(SpringRoute::buildTool)
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new))));
    }

    static String declaredRanges(String buildTool) {
        return declaredRanges(ROUTES, SourceFamily.SPRING_BOOT, buildTool);
    }

    private static String declaredRanges(List<SpringRoute> catalog, SourceFamily family,
                                         String buildTool) {
        return catalog.stream()
                .filter(route -> route.sourceFamily() == family)
                .filter(route -> route.buildTool().equals(buildTool))
                .map(SpringRoute::sourceConstraint)
                .distinct()
                .reduce((left, right) -> left + ", " + right)
                .orElse("none");
    }

    private static String declaredSourceJava(List<SpringRoute> routes) {
        Set<String> versions = routes.stream()
                .flatMap(route -> route.sourceJavaVersions().stream())
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        return String.join(", ", sorted(versions));
    }

    private static String declaredTargets(List<SpringRoute> routes) {
        return routes.stream()
                .map(route -> "Boot " + route.targetBoot() + " / Java " + route.targetJava())
                .distinct()
                .sorted()
                .reduce((left, right) -> left + ", " + right)
                .orElse("none");
    }

    /**
     * Compare dotted release numbers segment by segment. Qualifiers such as
     * {@code -SNAPSHOT} or {@code .RELEASE} are cut before comparison so a
     * repository pinned to {@code 2.7.18-SNAPSHOT} still resolves to the 2.7
     * route instead of silently falling out of every range.
     */
    static boolean withinRange(String version, String minInclusive, String maxExclusive) {
        return compare(version, minInclusive) >= 0 && compare(version, maxExclusive) < 0;
    }

    static int compare(String left, String right) {
        String[] leftParts = numericPrefix(left).split("\\.");
        String[] rightParts = numericPrefix(right).split("\\.");
        int length = Math.max(leftParts.length, rightParts.length);
        for (int index = 0; index < length; index += 1) {
            int leftValue = index < leftParts.length ? parse(leftParts[index]) : 0;
            int rightValue = index < rightParts.length ? parse(rightParts[index]) : 0;
            if (leftValue != rightValue) return Integer.compare(leftValue, rightValue);
        }
        return 0;
    }

    private static String numericPrefix(String value) {
        StringBuilder builder = new StringBuilder();
        for (char character : value.trim().toCharArray()) {
            if (Character.isDigit(character) || character == '.') builder.append(character);
            else break;
        }
        String prefix = builder.toString();
        while (prefix.endsWith(".")) prefix = prefix.substring(0, prefix.length() - 1);
        return prefix.isEmpty() ? "0" : prefix;
    }

    private static int parse(String value) {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException error) {
            return 0;
        }
    }

    private static String normalize(String value) {
        return value == null ? "" : value.trim();
    }

    /** {@code 1.8} and {@code 8} are the same JDK; normalize to the release number. */
    static String normalizeJava(String value) {
        String normalized = normalize(value);
        if (normalized.startsWith("1.") && normalized.length() > 2) {
            String remainder = normalized.substring(2);
            if (remainder.chars().allMatch(Character::isDigit)) return remainder;
        }
        return normalized;
    }

    private static List<String> sorted(Set<String> values) {
        return values.stream().sorted(Comparator.comparingInt(SpringRouteCatalog::parse)).toList();
    }

    private static List<String> sortedStrings(Set<String> values) {
        return values.stream().sorted().toList();
    }
}
