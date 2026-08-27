package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.PosixFilePermission;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LocalSpringUpgradeExecutionPortTest {
    @TempDir Path temporaryDirectory;

    @Test void readOnlySeedBecomesWritableOnlyInsideThePerRunRepository() throws Exception {
        Path seed = temporaryDirectory.resolve("seed");
        Path seedArtifact = seed.resolve("org/example/library/1.0/library-1.0.jar");
        Path seedTracking = seedArtifact.getParent().resolve("_remote.repositories");
        Files.createDirectories(seedArtifact.getParent());
        Files.writeString(seedArtifact, "artifact");
        Files.writeString(seedTracking, "tracking");
        makeReadOnly(seed);

        Path perRunRepository = temporaryDirectory.resolve("run/.m2/repository");
        LocalSpringUpgradeExecutionPort.copyDependencySeed(seed, perRunRepository);

        assertEquals("artifact", Files.readString(
                perRunRepository.resolve("org/example/library/1.0/library-1.0.jar")));
        assertTrue(Files.isWritable(
                perRunRepository.resolve("org/example/library/1.0/_remote.repositories")));
        assertTrue(Files.isWritable(
                perRunRepository.resolve("org/example/library/1.0")));
        assertTrue(!Files.isWritable(seedTracking) || !ownerCanWrite(seedTracking));
    }

    @Test void rewriteUsesPinnedUpstreamAndRepositoryOwnedRecipeCoordinates() {
        assertEquals(
                List.of(
                        "org.openrewrite.recipe:rewrite-spring:6.35.0",
                        LocalSpringUpgradeExecutionPort.ELMOS_RECIPE_COORDINATE),
                LocalSpringUpgradeExecutionPort.rewriteRecipeArtifactCoordinates("6.35.0"));
        assertThrows(IllegalArgumentException.class,
                () -> LocalSpringUpgradeExecutionPort.rewriteRecipeArtifactCoordinates(" "));
    }

    @Test void customRecipeRequiresItsArtifactAndParentPomInTheImmutableSeed() throws Exception {
        Path repository = temporaryDirectory.resolve("recipe-seed");
        assertFalse(LocalSpringUpgradeExecutionPort.hasElmosRecipeArtifact(repository));

        Path artifactDirectory = repository.resolve(
                "io/elmos/elmos-java-recipes/0.1.0-SNAPSHOT");
        Path parentDirectory = repository.resolve(
                "io/elmos/elmos-parent/0.1.0-SNAPSHOT");
        Files.createDirectories(artifactDirectory);
        Files.createDirectories(parentDirectory);
        Files.writeString(artifactDirectory.resolve("elmos-java-recipes-0.1.0-SNAPSHOT.jar"), "jar");
        Files.writeString(artifactDirectory.resolve("elmos-java-recipes-0.1.0-SNAPSHOT.pom"), "pom");
        Files.writeString(parentDirectory.resolve("elmos-parent-0.1.0-SNAPSHOT.pom"), "parent");

        assertTrue(LocalSpringUpgradeExecutionPort.hasElmosRecipeArtifact(repository));
    }

    @Test void securedAndMissingRoutesProveStartupButServerErrorsDoNot() {
        assertTrue(LocalSpringUpgradeExecutionPort.isStartupStatus(200));
        assertTrue(LocalSpringUpgradeExecutionPort.isStartupStatus(401));
        assertTrue(LocalSpringUpgradeExecutionPort.isStartupStatus(403));
        assertTrue(LocalSpringUpgradeExecutionPort.isStartupStatus(404));
        assertFalse(LocalSpringUpgradeExecutionPort.isStartupStatus(199));
        assertFalse(LocalSpringUpgradeExecutionPort.isStartupStatus(500));
    }

    @Test void runtimeHealthRequiresBoundedTwoXxJsonWithExactUpStatus() {
        ObjectMapper json = new ObjectMapper();
        assertTrue(LocalSpringUpgradeExecutionPort.strictHealthUp(
                200, "{\"status\":\"UP\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8), json));
        assertFalse(LocalSpringUpgradeExecutionPort.strictHealthUp(
                200, "{\"status\":\"DOWN\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8), json));
        assertFalse(LocalSpringUpgradeExecutionPort.strictHealthUp(
                200, "UP".getBytes(java.nio.charset.StandardCharsets.UTF_8), json));
        assertFalse(LocalSpringUpgradeExecutionPort.strictHealthUp(
                503, "{\"status\":\"UP\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8), json));
        assertFalse(LocalSpringUpgradeExecutionPort.strictHealthUp(
                200, new byte[(64 * 1024) + 1], json));
    }

    @Test void runtimeAndManagementEndpointsAreBothPinnedToLoopback() {
        ProcessBuilder builder = new ProcessBuilder("java", "-version");
        LocalSpringUpgradeExecutionPort.bindLoopbackEnvironment(builder, 18081);
        assertEquals("127.0.0.1", builder.environment().get("SERVER_ADDRESS"));
        assertEquals("18081", builder.environment().get("SERVER_PORT"));
        assertEquals("127.0.0.1", builder.environment().get("MANAGEMENT_SERVER_ADDRESS"));
        assertEquals("18081", builder.environment().get("MANAGEMENT_SERVER_PORT"));
        assertThrows(IllegalArgumentException.class,
                () -> LocalSpringUpgradeExecutionPort.bindLoopbackEnvironment(builder, 0));
    }

    @Test void routeSelectionUsesTheRequestedTargetTuple() {
        SpringUpgradeModels.Fingerprint fingerprint = new SpringUpgradeModels.Fingerprint(
                "2.7.18", "17", "maven", List.of(), List.of("spring-boot-parent"),
                List.of(), Map.of("spring-boot-parent", List.of("pom.xml:parent")),
                "spring-boot", "2.7.18");

        SpringRouteCatalog.Selection selection = LocalSpringUpgradeExecutionPort.selectRoute(
                fingerprint, "3.2.12", "17", true);

        assertEquals("boot-2.7-maven-to-boot-3.2.12-java-17", selection.route().routeId());
        assertEquals("17", selection.route().targetJava());
        assertEquals(SpringRouteCatalog.EvidenceStatus.NOT_RUN, selection.evidence());
    }

    @Test void springMvcNeedsProductionTracesAndUsesRecordedExactLocalEvidence() {
        SpringUpgradeModels.Fingerprint activeMvc = new SpringUpgradeModels.Fingerprint(
                "UNKNOWN", "11", "maven", List.of(), List.of("spring-mvc", "spring-mvc-xml"),
                List.of(), Map.of("spring-mvc", List.of(
                        "observed|source|src/main/java/example/Controller.java:2|Spring MVC controller")),
                "spring-mvc", "5.3.39");

        assertEquals("spring-framework-5.3-mvc-maven-to-boot-3.5.3-java-21",
                LocalSpringUpgradeExecutionPort.selectRoute(
                        activeMvc, "3.5.3", "21", false).route().routeId());
        assertEquals(SpringRouteCatalog.EvidenceStatus.PASSED_LOCAL,
                LocalSpringUpgradeExecutionPort.selectRoute(
                        activeMvc, "3.5.3", "21", false).evidence());

        SpringUpgradeModels.Fingerprint dependencyOnly = new SpringUpgradeModels.Fingerprint(
                "UNKNOWN", "11", "maven", List.of(), List.of(), List.of(),
                Map.of("spring-mvc", List.of("declared-only|build-model|pom.xml:8|spring-webmvc")),
                "spring-mvc", "5.3.39");
        SpringUpgradeModels.BlockedException activationBlocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> LocalSpringUpgradeExecutionPort.selectRoute(
                        dependencyOnly, "3.5.3", "21", false));
        assertEquals("SPRING_MVC_RUNTIME_EVIDENCE_REQUIRED", activationBlocked.code());
    }

    @Test void mavenFingerprintUsesExactChildAuthorityForAggregatorRoots() throws Exception {
        writePom(temporaryDirectory.resolve("pom.xml"), """
                <project><modelVersion>4.0.0</modelVersion><groupId>example</groupId>
                  <artifactId>reactor</artifactId><version>1</version>
                  <packaging>pom</packaging><modules><module>app</module><module>library</module></modules>
                </project>
                """);
        writePom(temporaryDirectory.resolve("app/pom.xml"), bootPom("2.7.18", "17"));
        writePom(temporaryDirectory.resolve("library/pom.xml"), """
                <project><modelVersion>4.0.0</modelVersion><groupId>example</groupId>
                  <artifactId>library</artifactId><version>1</version>
                </project>
                """);

        SpringUpgradeModels.Fingerprint fingerprint =
                LocalSpringUpgradeExecutionPort.fingerprintMaven(temporaryDirectory);

        assertEquals("2.7.18", fingerprint.springBootVersion());
        assertEquals("17", fingerprint.javaVersion());
        assertEquals(List.of("app", "library"), fingerprint.modules());
        assertTrue(fingerprint.activeCapabilities().contains("spring-boot-parent"));
    }

    @Test void mavenFingerprintRejectsConflictingModuleBootVersions() throws Exception {
        writePom(temporaryDirectory.resolve("pom.xml"), """
                <project><modelVersion>4.0.0</modelVersion><groupId>example</groupId>
                  <artifactId>reactor</artifactId><version>1</version><packaging>pom</packaging>
                  <modules><module>first</module><module>second</module></modules>
                </project>
                """);
        writePom(temporaryDirectory.resolve("first/pom.xml"), bootPom("2.7.18", "17"));
        writePom(temporaryDirectory.resolve("second/pom.xml"), bootPom("2.6.15", "17"));

        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> LocalSpringUpgradeExecutionPort.fingerprintMaven(temporaryDirectory));
        assertEquals("MAVEN_REACTOR_SPRING_BOOT_VERSION_CONFLICT", blocked.code());
    }

    @Test void mavenFingerprintRejectsMissingDeclaredModuleModel() throws Exception {
        writePom(temporaryDirectory.resolve("pom.xml"), """
                <project><modelVersion>4.0.0</modelVersion><groupId>example</groupId>
                  <artifactId>reactor</artifactId><version>1</version><packaging>pom</packaging>
                  <modules><module>missing</module></modules>
                </project>
                """);

        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> LocalSpringUpgradeExecutionPort.fingerprintMaven(temporaryDirectory));
        assertEquals("MAVEN_REACTOR_INCOMPLETE", blocked.code());
    }

    @Test void complexCapabilityGateIsNotApplicableWithoutCriticalCapabilities() {
        var decision = LocalSpringUpgradeExecutionPort.evaluateComplexCapabilities(
                temporaryDirectory.resolve("source"),
                temporaryDirectory.resolve("target"),
                fingerprint(List.of("web"), List.of(), Map.of(
                        "web", List.of("observed|source|src/main/java/example/Web.java:2|controller"))),
                testRun("example.WebTest#responds"),
                testRun("example.WebTest#responds"),
                new ObjectMapper());

        assertEquals("NOT_APPLICABLE", decision.report().get("status"));
        assertEquals(false, decision.report().get("certification_eligible"));
        assertTrue(decision.blockers().isEmpty());
    }

    @Test void complexCapabilityGateRequiresProjectOwnedManifestEvenForDeclaredOnlyFacts() {
        var decision = LocalSpringUpgradeExecutionPort.evaluateComplexCapabilities(
                temporaryDirectory.resolve("source"),
                temporaryDirectory.resolve("target"),
                fingerprint(List.of("security"), List.of(), Map.of(
                        "security", List.of("observed|source|src/main/java/example/Security.java:2|chain"),
                        "persistence-jpa", List.of("declared-only|build-model|pom.xml:20|data-jpa"))),
                testRun("example.SecurityTest#denies"),
                testRun("example.SecurityTest#denies"),
                new ObjectMapper());

        assertEquals("BLOCKED", decision.report().get("status"));
        assertTrue(decision.blockers().contains("CAPABILITY_TEST_MANIFEST_MISSING"));
        assertTrue(list(decision.report().get("required_domains")).contains("security"));
        assertTrue(list(decision.report().get("required_domains")).contains("persistence_database"));
    }

    @Test void complexCapabilityGatePassesOnlyAsLocalEngineeringWithExactTestsAndInvariants()
            throws Exception {
        Path source = temporaryDirectory.resolve("source");
        Path target = temporaryDirectory.resolve("target");
        Map<String, String> domainTests = Map.of(
                "security", "example.SecurityTest#contracts",
                "persistence_database", "example.DatabaseTest#contracts",
                "transactions", "example.TransactionTest#contracts",
                "messaging", "example.MessagingTest#contracts");
        writeCapabilityManifest(source, target, domainTests, Map.of(), false);
        List<String> identities = domainTests.values().stream().sorted().toList();

        var decision = LocalSpringUpgradeExecutionPort.evaluateComplexCapabilities(
                source,
                target,
                fingerprint(
                        List.of("security", "persistence-jpa", "transactions", "messaging-kafka"),
                        List.of(),
                        Map.of(
                                "security", List.of("observed|source|Security.java:2|chain"),
                                "persistence-jpa", List.of("observed|source|Entity.java:2|entity"),
                                "transactions", List.of("observed|source|Service.java:2|transaction"),
                                "messaging-kafka", List.of("observed|source|Listener.java:2|listener"))),
                new LocalSpringUpgradeExecutionPort.CapabilityTestRun(identities, 0),
                new LocalSpringUpgradeExecutionPort.CapabilityTestRun(identities, 0),
                new ObjectMapper());

        assertEquals("PASS_LOCAL_ENGINEERING", decision.report().get("status"));
        assertEquals(false, decision.report().get("certification_eligible"));
        assertEquals("NOT_CERTIFIED", decision.report().get("certification_status"));
        assertEquals("NOT_RUN", decision.report().get("independent_verification"));
        assertTrue(decision.blockers().isEmpty());
    }

    @Test void unresolvedConditionsAndChangedTestIdentityFailClosed() throws Exception {
        Path source = temporaryDirectory.resolve("source");
        Path target = temporaryDirectory.resolve("target");
        writeCapabilityManifest(source, target,
                Map.of("security", "example.SecurityTest#prodProfile"), Map.of(), false);
        var decision = LocalSpringUpgradeExecutionPort.evaluateComplexCapabilities(
                source,
                target,
                fingerprint(List.of(),
                        List.of("conditional-capability-activation-unresolved:security"),
                        Map.of("security", List.of(
                                "conditional|source|Security.java:2|chain|conditions=profile:prod"))),
                testRun("example.SecurityTest#prodProfile"),
                testRun("example.SecurityTest#renamed"),
                new ObjectMapper());

        assertEquals("BLOCKED", decision.report().get("status"));
        assertTrue(decision.blockers().contains("CONDITIONAL_ACTIVATION_UNRESOLVED:security"));
        assertTrue(decision.blockers().contains("SOURCE_TARGET_TEST_IDENTITY_MISMATCH"));
    }

    @Test void unresolvedCriticalConditionWithoutTraceStillFailsClosed() {
        var decision = LocalSpringUpgradeExecutionPort.evaluateComplexCapabilities(
                temporaryDirectory.resolve("source"),
                temporaryDirectory.resolve("target"),
                fingerprint(List.of(),
                        List.of("conditional-capability-activation-unresolved:messaging-jms"),
                        Map.of()),
                testRun("example.MessagingTest#conditionalListener"),
                testRun("example.MessagingTest#conditionalListener"),
                new ObjectMapper());

        assertEquals("BLOCKED", decision.report().get("status"));
        assertTrue(list(decision.report().get("required_domains")).contains("messaging"));
        assertTrue(decision.blockers().contains(
                "CONDITIONAL_ACTIVATION_UNRESOLVED:messaging-jms"));
    }

    @Test void declaredOnlyCriticalUnknownWithoutTraceStillRequiresManifest() {
        var decision = LocalSpringUpgradeExecutionPort.evaluateComplexCapabilities(
                temporaryDirectory.resolve("source"),
                temporaryDirectory.resolve("target"),
                fingerprint(List.of(),
                        List.of("declared-only-capability-runtime-activation-unobserved:persistence-jdbc"),
                        Map.of()),
                testRun("example.DatabaseTest#contracts"),
                testRun("example.DatabaseTest#contracts"),
                new ObjectMapper());

        assertEquals("BLOCKED", decision.report().get("status"));
        assertTrue(list(decision.report().get("required_domains"))
                .contains("persistence_database"));
        assertTrue(decision.blockers().contains("CAPABILITY_TEST_MANIFEST_MISSING"));
    }

    @Test void manifestReachedThroughSymlinkIsNotProjectOwned() throws Exception {
        Path outside = temporaryDirectory.resolve("outside");
        Path source = temporaryDirectory.resolve("source");
        Path target = temporaryDirectory.resolve("target");
        Map<String, String> domainTests = Map.of(
                "security", "example.SecurityTest#contracts");
        writeCapabilityManifest(outside, target, domainTests, Map.of(), false);
        Files.createDirectories(source);
        Files.createSymbolicLink(source.resolve("elmos"), outside.resolve("elmos"));

        var decision = LocalSpringUpgradeExecutionPort.evaluateComplexCapabilities(
                source,
                target,
                fingerprint(List.of("security"), List.of(), Map.of(
                        "security", List.of("observed|source|Security.java:2|chain"))),
                testRun("example.SecurityTest#contracts"),
                testRun("example.SecurityTest#contracts"),
                new ObjectMapper());

        assertTrue(decision.blockers().contains("CAPABILITY_TEST_MANIFEST_MISSING"));
        @SuppressWarnings("unchecked")
        Map<String, Object> manifest = (Map<String, Object>) decision.report().get("manifest");
        assertEquals(false, manifest.get("project_owned_source_path"));
    }

    @Test void customProviderNeedsItsAdditionalInvariantAndManifestCannotChange() throws Exception {
        Path source = temporaryDirectory.resolve("source");
        Path target = temporaryDirectory.resolve("target");
        Map<String, String> domainTests = Map.of(
                "security", "example.SecurityTest#customProvider");
        SpringUpgradeModels.Fingerprint fingerprint = fingerprint(
                List.of("security", "authentication"),
                List.of("custom-authentication-provider-behavior-requires-runtime-contract"),
                Map.of("security", List.of("observed|source|Security.java:2|chain")));
        writeCapabilityManifest(source, target, domainTests, Map.of(), false);

        var missingInvariant = LocalSpringUpgradeExecutionPort.evaluateComplexCapabilities(
                source, target, fingerprint,
                testRun("example.SecurityTest#customProvider"),
                testRun("example.SecurityTest#customProvider"), new ObjectMapper());
        assertTrue(missingInvariant.blockers().stream().anyMatch(
                blocker -> blocker.contains("custom-authentication-provider-contract")));

        writeCapabilityManifest(source, target, domainTests,
                Map.of("security", List.of("custom-authentication-provider-contract")), true);
        var changedManifest = LocalSpringUpgradeExecutionPort.evaluateComplexCapabilities(
                source, target, fingerprint,
                testRun("example.SecurityTest#customProvider"),
                testRun("example.SecurityTest#customProvider"), new ObjectMapper());
        assertTrue(changedManifest.blockers().contains(
                "CAPABILITY_TEST_MANIFEST_CHANGED_BY_TRANSFORMATION"));

        writeCapabilityManifest(source, target, domainTests,
                Map.of("security", List.of("custom-authentication-provider-contract")), false);
        var passed = LocalSpringUpgradeExecutionPort.evaluateComplexCapabilities(
                source, target, fingerprint,
                testRun("example.SecurityTest#customProvider"),
                testRun("example.SecurityTest#customProvider"), new ObjectMapper());
        assertEquals("PASS_LOCAL_ENGINEERING", passed.report().get("status"));
    }

    private static String bootPom(String version, String java) {
        return """
                <project><modelVersion>4.0.0</modelVersion>
                  <parent><groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-parent</artifactId><version>%s</version></parent>
                  <groupId>example</groupId><artifactId>app</artifactId><version>1</version>
                  <properties><java.version>%s</java.version></properties>
                </project>
                """.formatted(version, java);
    }

    private static SpringUpgradeModels.Fingerprint fingerprint(
            List<String> active,
            List<String> unknowns,
            Map<String, List<String>> traces
    ) {
        return new SpringUpgradeModels.Fingerprint(
                "2.7.18", "17", "maven", List.of(), active, unknowns, traces,
                "spring-boot", "2.7.18");
    }

    private static LocalSpringUpgradeExecutionPort.CapabilityTestRun testRun(String... identities) {
        return new LocalSpringUpgradeExecutionPort.CapabilityTestRun(List.of(identities), 0);
    }

    private static void writeCapabilityManifest(
            Path source,
            Path target,
            Map<String, String> domainTests,
            Map<String, List<String>> extraInvariants,
            boolean changeTarget
    ) throws Exception {
        Map<String, Object> domains = new LinkedHashMap<>();
        Set<String> identities = new TreeSet<>();
        for (Map.Entry<String, String> domain : domainTests.entrySet()) {
            identities.add(domain.getValue());
            List<String> invariants = new ArrayList<>(
                    LocalSpringUpgradeExecutionPort.requiredComplexCapabilityInvariants()
                            .get(domain.getKey()));
            invariants.addAll(extraInvariants.getOrDefault(domain.getKey(), List.of()));
            domains.put(domain.getKey(), Map.of(
                    "invariants", invariants.stream().distinct().sorted().toList(),
                    "test_identities", List.of(domain.getValue())));
        }
        Map<String, Object> manifest = new LinkedHashMap<>();
        manifest.put("schema_version", "1.0");
        manifest.put("kind", "elmos.spring-capability-tests");
        manifest.put("test_identities", identities.stream().toList());
        manifest.put("domains", domains);
        ObjectMapper json = new ObjectMapper();
        byte[] bytes = json.writerWithDefaultPrettyPrinter().writeValueAsBytes(manifest);
        Path sourceManifest = source.resolve("elmos/spring-capability-tests.json");
        Path targetManifest = target.resolve("elmos/spring-capability-tests.json");
        Files.createDirectories(sourceManifest.getParent());
        Files.createDirectories(targetManifest.getParent());
        Files.write(sourceManifest, bytes);
        Files.write(targetManifest, changeTarget
                ? (new String(bytes, java.nio.charset.StandardCharsets.UTF_8) + "\n").getBytes(
                java.nio.charset.StandardCharsets.UTF_8)
                : bytes);
    }

    @SuppressWarnings("unchecked")
    private static List<String> list(Object value) {
        return (List<String>) value;
    }

    private static void writePom(Path path, String content) throws Exception {
        Files.createDirectories(path.getParent());
        Files.writeString(path, content);
    }

    @Test void immutableSeedArtifactsAreSharedByLinkAndCannotBeWrittenBackInto() throws Exception {
        Path seed = temporaryDirectory.resolve("linkable-seed");
        Path group = seed.resolve("org/example/library/1.0");
        Files.createDirectories(group);
        Path seedArtifact = group.resolve("library-1.0.jar");
        Path seedTracking = group.resolve("_remote.repositories");
        Files.writeString(seedArtifact, "artifact");
        Files.writeString(seedTracking, "tracking");
        makeReadOnly(seed);

        Path perRunRepository = temporaryDirectory.resolve("linked-run/.m2/repository");
        LocalSpringUpgradeExecutionPort.copyDependencySeed(seed, perRunRepository);
        Path artifact = perRunRepository.resolve("org/example/library/1.0/library-1.0.jar");
        Path tracking = perRunRepository.resolve("org/example/library/1.0/_remote.repositories");

        // The immutable artifact is shared with the seed rather than duplicated.
        assertEquals(Files.getAttribute(seedArtifact, "unix:ino"), Files.getAttribute(artifact, "unix:ino"));
        assertEquals("artifact", Files.readString(artifact));
        // A shared inode also shares permissions, so the link stays unwritable.
        assertFalse(ownerCanWrite(artifact));

        // The resolver rewrites its tracking file in place, so that one is the run's own.
        assertNotEquals(Files.getAttribute(seedTracking, "unix:ino"), Files.getAttribute(tracking, "unix:ino"));
        assertTrue(ownerCanWrite(tracking));
        assertFalse(ownerCanWrite(seedTracking));

        // Maven replaces an artifact by renaming a new file over it, which leaves the seed alone.
        Path replacement = perRunRepository.resolve("org/example/library/1.0/library-1.0.jar.tmp");
        Files.writeString(replacement, "redownloaded");
        Files.move(replacement, artifact, StandardCopyOption.REPLACE_EXISTING);
        assertEquals("redownloaded", Files.readString(artifact));
        assertEquals("artifact", Files.readString(seedArtifact));
    }

    @Test void writableSeedEntriesAreCopiedBecauseALinkWouldReachBackIntoTheSeed() throws Exception {
        Path seed = temporaryDirectory.resolve("mixed-seed");
        Path group = seed.resolve("org/example/library/1.0");
        Files.createDirectories(group);
        Path locked = group.resolve("library-1.0.jar");
        Path loose = group.resolve("library-1.0.pom");
        Files.writeString(locked, "locked");
        Files.writeString(loose, "loose");
        makeReadOnly(seed);
        Files.setPosixFilePermissions(group, EnumSet.of(
                PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE,
                PosixFilePermission.OWNER_EXECUTE));
        Files.setPosixFilePermissions(loose, EnumSet.of(
                PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE));

        Path perRunRepository = temporaryDirectory.resolve("mixed-run/.m2/repository");
        LocalSpringUpgradeExecutionPort.copyDependencySeed(seed, perRunRepository);

        assertEquals(Files.getAttribute(locked, "unix:ino"),
                Files.getAttribute(perRunRepository.resolve("org/example/library/1.0/library-1.0.jar"),
                        "unix:ino"));
        assertNotEquals(Files.getAttribute(loose, "unix:ino"),
                Files.getAttribute(perRunRepository.resolve("org/example/library/1.0/library-1.0.pom"),
                        "unix:ino"));
    }

    private static void makeReadOnly(Path root) throws Exception {
        try (var paths = Files.walk(root)) {
            for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) {
                Set<PosixFilePermission> permissions =
                        EnumSet.copyOf(Files.getPosixFilePermissions(path));
                permissions.remove(PosixFilePermission.OWNER_WRITE);
                permissions.remove(PosixFilePermission.GROUP_WRITE);
                permissions.remove(PosixFilePermission.OTHERS_WRITE);
                Files.setPosixFilePermissions(path, permissions);
            }
        }
    }

    private static boolean ownerCanWrite(Path path) throws Exception {
        return Files.getPosixFilePermissions(path).contains(PosixFilePermission.OWNER_WRITE);
    }
}
