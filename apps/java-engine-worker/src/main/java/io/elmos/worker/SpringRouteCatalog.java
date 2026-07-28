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
 * estates are spread across Boot 1.5 through 3.4 on Java 8, 11, 17 and 21, so
 * the route is now selected from a declared catalog instead of asserted.
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
    static final String REWRITE_SPRING = "6.35.0";
    static final String REWRITE_MAVEN_PLUGIN = "6.44.0";
    static final String MAVEN_BUILD_TOOL = "maven";
    static final String GRADLE_BUILD_TOOL = "gradle";
    static final String MAVEN_TOOLCHAIN = "maven-3.9.11";

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
            String notes
    ) {
        SpringRoute {
            sourceJavaVersions = Set.copyOf(sourceJavaVersions);
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

        String artifactFileName() {
            return "migrated-spring-boot-" + targetBoot + ".zip";
        }

        SpringUpgradeModels.ExactTuple tuple(String detectedBoot, String detectedJava) {
            return new SpringUpgradeModels.ExactTuple(
                    detectedBoot, detectedJava, MAVEN_TOOLCHAIN,
                    targetBoot, targetJava, MAVEN_TOOLCHAIN,
                    rewriteSpring, rewriteMavenPlugin);
        }
    }

    private static final List<SpringRoute> ROUTES = List.of(
            new SpringRoute(
                    "boot-1.5-java-8-maven-to-boot-3.5.3-java-21",
                    "spring-boot-1-5-to-3-5-3",
                    "Spring Boot 1.5.x / Java 8 / Maven",
                    "1.5.0", "2.0.0", Set.of("8"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "/rewrite/spring-boot-1.5-to-3.5.3.yml",
                    "io.elmos.openrewrite.SpringBoot1_5ToBoot3_5_3Java21",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_RUN, "", "",
                    "Chains the 2.0, 2.7 and 3.5 Boot migrations with the Java 8 to 21 migration. "
                            + "javax to jakarta, removed 1.5 auto-configuration and Actuator endpoint "
                            + "renames frequently need manual review after the deterministic pass."),
            new SpringRoute(
                    "boot-2.0-2.6-maven-to-boot-3.5.3-java-21",
                    "spring-boot-2-0-2-6-to-3-5-3",
                    "Spring Boot 2.0–2.6 / Java 8, 11, 17 / Maven",
                    "2.0.0", "2.7.0", Set.of("8", "11", "17"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "/rewrite/spring-boot-2.0-2.6-to-3.5.3.yml",
                    "io.elmos.openrewrite.SpringBoot2_0To2_6ToBoot3_5_3Java21",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_RUN, "", "",
                    "Steps through Boot 2.7 before 3.5 so the intermediate deprecations are applied "
                            + "in order. Sources below Java 17 additionally cross the Boot 3 baseline."),
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
                    "The only tuple with recorded end-to-end local execution is Boot 2.7.18 on Java 17."),
            new SpringRoute(
                    "boot-3.0-3.4-maven-to-boot-3.5.3-java-21",
                    "spring-boot-3-0-3-4-to-3-5-3",
                    "Spring Boot 3.0–3.4 / Java 17, 21 / Maven",
                    "3.0.0", "3.5.0", Set.of("17", "21"), MAVEN_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "/rewrite/spring-boot-3.0-3.4-to-3.5.3.yml",
                    "io.elmos.openrewrite.SpringBoot3_0To3_4ToBoot3_5_3Java21",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_RUN, "", "",
                    "Already on the jakarta baseline; the pass is limited to the 3.5 migration and "
                            + "the Java 21 language and API migration."),
            new SpringRoute(
                    "boot-2.x-gradle-to-boot-3.5.3-java-21",
                    "spring-boot-2-x-gradle-to-3-5-3",
                    "Spring Boot 2.x / Gradle",
                    "1.5.0", "3.5.0", Set.of("8", "11", "17"), GRADLE_BUILD_TOOL,
                    TARGET_BOOT, TARGET_JAVA,
                    "", "",
                    REWRITE_SPRING, REWRITE_MAVEN_PLUGIN,
                    EvidenceStatus.NOT_IMPLEMENTED, "", "",
                    "Declared for inventory only. Gradle needs its own build driver, wrapper "
                            + "verification and rewrite plugin invocation; no driver is bound yet.")
    );

    static List<SpringRoute> routes() {
        return ROUTES;
    }

    static Optional<SpringRoute> byId(String routeId) {
        return ROUTES.stream().filter(route -> route.routeId().equals(routeId)).findFirst();
    }

    /** The tuple that carries recorded local execution evidence. */
    static SpringRoute verifiedRoute() {
        return ROUTES.stream()
                .filter(route -> route.routeEvidence() == EvidenceStatus.PASSED_LOCAL)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("catalog has no verified route"));
    }

    record Selection(SpringRoute route, EvidenceStatus evidence) {
        boolean requiresExperimentalOptIn() {
            return evidence != EvidenceStatus.PASSED_LOCAL;
        }
    }

    /**
     * Choose the route for a detected fingerprint.
     *
     * <p>The blocked reasons are deliberately specific. "Unsupported" without a
     * reason forces an operator to read engine source to find out whether the
     * Boot line, the JDK or the build tool was the problem.
     */
    static Selection select(String bootVersion, String javaVersion, String buildTool) {
        String boot = normalize(bootVersion);
        String java = normalizeJava(javaVersion);
        String build = buildTool == null ? "" : buildTool.trim().toLowerCase(Locale.ROOT);

        if (boot.isEmpty() || "unknown".equals(boot.toLowerCase(Locale.ROOT))) {
            throw new BlockedException("SPRING_BOOT_VERSION_UNRESOLVED",
                    "The Spring Boot version could not be resolved from the build model; "
                            + "the route cannot be selected without an exact source version.");
        }
        if (java.isEmpty() || "unknown".equals(java.toLowerCase(Locale.ROOT))) {
            throw new BlockedException("SOURCE_JAVA_VERSION_UNRESOLVED",
                    "The source Java release could not be resolved from the build model; "
                            + "the route cannot be selected without an exact source JDK.");
        }

        List<SpringRoute> buildMatches = ROUTES.stream()
                .filter(route -> route.buildTool().equals(build))
                .toList();
        if (buildMatches.isEmpty()) {
            throw new BlockedException("UNSUPPORTED_BUILD_TOOL",
                    "No route is declared for build tool '" + build + "'. Declared build tools: "
                            + declaredBuildTools() + ".");
        }

        List<SpringRoute> bootMatches = buildMatches.stream()
                .filter(route -> withinRange(boot, route.sourceBootMinInclusive(), route.sourceBootMaxExclusive()))
                .toList();
        if (bootMatches.isEmpty()) {
            throw new BlockedException("UNSUPPORTED_SOURCE_BOOT_VERSION",
                    "Spring Boot " + boot + " is outside every declared source range for " + build
                            + ". Declared ranges: " + declaredRanges(build) + ".");
        }
        if (bootMatches.size() > 1) {
            // Overlapping ranges are a catalog defect, not a customer input problem.
            throw new BlockedException("SPRING_ROUTE_AMBIGUOUS",
                    "Spring Boot " + boot + " matched more than one declared route; the catalog "
                            + "must declare disjoint source ranges.");
        }

        SpringRoute route = bootMatches.get(0);
        if (!route.sourceJavaVersions().contains(java)) {
            throw new BlockedException("UNSUPPORTED_SOURCE_JAVA_VERSION",
                    "Route " + route.routeId() + " accepts Java "
                            + String.join(", ", sorted(route.sourceJavaVersions()))
                            + " but the repository declares Java " + java + ".");
        }
        if (!route.implemented()) {
            throw new BlockedException("SPRING_ROUTE_NOT_IMPLEMENTED",
                    "Route " + route.routeId() + " is declared but has no execution driver: "
                            + route.notes());
        }
        return new Selection(route, route.evidenceFor(boot, java));
    }

    static String declaredBuildTools() {
        return String.join(", ", sorted(ROUTES.stream().map(SpringRoute::buildTool)
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new))));
    }

    static String declaredRanges(String buildTool) {
        return ROUTES.stream()
                .filter(route -> route.buildTool().equals(buildTool))
                .map(route -> "[" + route.sourceBootMinInclusive() + ", " + route.sourceBootMaxExclusive() + ")")
                .distinct()
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
}
