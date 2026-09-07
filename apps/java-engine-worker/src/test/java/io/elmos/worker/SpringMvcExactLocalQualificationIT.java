package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.lib.Constants;
import org.eclipse.jgit.lib.FileMode;
import org.eclipse.jgit.lib.ObjectId;
import org.eclipse.jgit.lib.Repository;
import org.eclipse.jgit.revwalk.RevCommit;
import org.eclipse.jgit.revwalk.RevWalk;
import org.eclipse.jgit.treewalk.TreeWalk;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.jar.Attributes;
import java.util.jar.JarFile;

import static io.elmos.worker.SpringUpgradeModels.SourceMode;
import static io.elmos.worker.SpringUpgradeModels.Stage;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Explicit, environment-provisioned local qualification for the single exact
 * Spring Framework 5.3.39 MVC WAR to Spring Boot 3.5.3 executable-WAR route.
 *
 * <p>The class name deliberately ends in {@code IT}; it is not part of the
 * default Surefire scan. An operator must name it explicitly and provision the
 * exact JDK, Maven and digest-bound Tomcat inputs. Its maximum claim is local
 * engineering evidence. It never produces certification or external evidence.</p>
 */
class SpringMvcExactLocalQualificationIT {
    private static final long GIB = 1024L * 1024L * 1024L;
    private static final long START_FLOOR = 10L * GIB;
    private static final long HARD_STOP_FLOOR = 8L * GIB;
    private static final int MAX_SOURCE_TREE_FILES = 10_000;
    private static final long MAX_SOURCE_TREE_BYTES = 256L * 1024L * 1024L;
    private static final String SOURCE_GIT_TREE_SHA =
            "4e1a0354cb51cfb2479ea049063226d3a9df2b67";
    private static final String MAVEN_ARCHIVE_SHA256 =
            "0d7125e8c91097b36edb990ea5934e6c68b4440eef4ea96510a0f6815e7eeadb";
    private static final String MAVEN_ARCHIVE_SHA512 =
            "03e2d65d4483a3396980629f260e25cac0d8b6f7f2791e4dc20bc83f9514db8d"
                    + "0f05b0479e699a5f34679250c49c8e52e961262ded468a20de0be254d8207076";
    private static final String TOMCAT_ARCHIVE_SHA256 =
            "93306f86baafe13186cc3e705c201040d68b0192a50be667a1f576ee4711db0d";
    private static final String TOMCAT_ARCHIVE_SHA512 =
            "fca7cfbe8255b61fac0e474a9a7ac6fbaf2792c72061fda2666b26eb5ba60718a"
                    + "dc4fc0cbd013f14a41f101bcd7f5b70b2d3eedc37554ff0db4bdb6e2e2898f6";
    private static final String SOURCE_JAVA_RELEASE_SHA256 =
            "09d5fffa5ad3de15dcfd603e747df1e6c9ecdb58f25d333e89661910064e884a";
    private static final String TARGET_JAVA_RELEASE_SHA256 =
            "7befd86565133fbebfa54138e55ec5b03bb59649ea5dda35d9f9b95265226756";
    private static final String RECIPE_BUILD_OUTPUT_TIMESTAMP =
            "2026-08-28T00:00:00Z";
    private static final Map<String, RecipeSeedFile> REQUIRED_RECIPE_SEED_FILES = Map.of(
            "io/elmos/elmos-parent/0.1.0-SNAPSHOT/elmos-parent-0.1.0-SNAPSHOT.pom",
            new RecipeSeedFile(10_461L,
                    "ada08c7433515cf79992c725f180ef12398803b4eb1372444821cc951e10efa8"),
            "io/elmos/elmos-java-recipes/0.1.0-SNAPSHOT/"
                    + "elmos-java-recipes-0.1.0-SNAPSHOT.pom",
            new RecipeSeedFile(751L,
                    "22775dc1c4ceebb891eccd4f6c10f8e4e4f63c1ccdf7a909935b81df7b9f311a"),
            "io/elmos/elmos-java-recipes/0.1.0-SNAPSHOT/"
                    + "elmos-java-recipes-0.1.0-SNAPSHOT.jar",
            new RecipeSeedFile(7_464L,
                    "a2291b649d9d84a36f455e3ef8eb477efdfda9a05c6b9026b76391d8e6a0d45c"));
    private static final String TARGET_TOMCAT_ENTRY =
            "WEB-INF/lib-provided/tomcat-embed-core-10.1.42.jar";
    private static final List<String> REQUIRED_EXTERNAL_EVIDENCE_TYPES = List.of(
            "source_build",
            "target_build",
            "source_startup",
            "target_startup",
            "behavioral_equivalence",
            "security",
            "performance",
            "operability",
            "sbom",
            "rollback",
            "independent_review",
            "customer_acceptance",
            "external_certification");

    @Test
    void executesExactSourceRewriteMaterializerTargetAndRuntimeOracle() throws Exception {
        Path qualificationRoot = absoluteDirectory("ELMOS_MVC_QUALIFICATION_ROOT");
        Path sourceJavaHome = absoluteDirectory("ELMOS_MVC_SOURCE_JAVA_HOME");
        Path targetJavaHome = absoluteDirectory("ELMOS_MVC_TARGET_JAVA_HOME");
        Path maven = absoluteRegularFile("ELMOS_MVC_MAVEN_EXECUTABLE");
        Path mavenArchive = absoluteRegularFile("ELMOS_MVC_MAVEN_ARCHIVE");
        Path tomcatArchive = absoluteRegularFile("ELMOS_MVC_TOMCAT_ARCHIVE");
        Path tomcatHome = absoluteDirectory("ELMOS_MVC_TOMCAT_HOME");
        Path recipeSeedRepository = absoluteDirectory(
                "ELMOS_MVC_RECIPE_SEED_REPOSITORY");
        Path harnessRoot = absoluteDirectory("ELMOS_MVC_HARNESS_ROOT");
        String sourceRelative = required("ELMOS_MVC_SOURCE_RELATIVE_PATH");
        String sourceCommit = required("ELMOS_MVC_SOURCE_COMMIT");
        String harnessCommit = required("ELMOS_MVC_HARNESS_COMMIT");
        String tomcatVersion = required("ELMOS_MVC_TOMCAT_VERSION");
        assertTrue(sourceCommit.matches("[0-9a-f]{40}"));
        assertTrue(harnessCommit.matches("[0-9a-f]{40}"));
        assertEquals(harnessCommit, exactGitHead(harnessRoot),
                "declared harness commit must equal the repository HEAD commit");
        assertEquals("9.0.120", tomcatVersion);
        requireCapacity(qualificationRoot, START_FLOOR, "qualification start");

        Path sourceJavaRelease = absoluteRegularFile(sourceJavaHome.resolve("release"));
        Path targetJavaRelease = absoluteRegularFile(targetJavaHome.resolve("release"));
        assertEquals(1_295L, Files.size(sourceJavaRelease));
        assertEquals(1_228L, Files.size(targetJavaRelease));
        assertEquals(SOURCE_JAVA_RELEASE_SHA256, digest(sourceJavaRelease, "SHA-256"));
        assertEquals(TARGET_JAVA_RELEASE_SHA256, digest(targetJavaRelease, "SHA-256"));
        assertEquals(9_278_421L, Files.size(mavenArchive));
        assertEquals(MAVEN_ARCHIVE_SHA256, digest(mavenArchive, "SHA-256"));
        assertEquals(MAVEN_ARCHIVE_SHA512, digest(mavenArchive, "SHA-512"));
        assertEquals(13_697_062L, Files.size(tomcatArchive));
        assertEquals(TOMCAT_ARCHIVE_SHA256, digest(tomcatArchive, "SHA-256"));
        assertEquals(TOMCAT_ARCHIVE_SHA512, digest(tomcatArchive, "SHA-512"));
        assertEquals("9.0.120", jarManifestValue(
                tomcatHome.resolve("lib/catalina.jar"), "Implementation-Version"));
        Map<String, Object> provisionedRecipeSeed = exactRecipeSeedEvidence(
                recipeSeedRepository);
        String sourceJavaOutput = toolOutput(sourceJavaHome.resolve("bin/java"), "-version");
        String sourceMavenOutput = toolOutput(maven, sourceJavaHome, "-version");
        String targetJavaOutput = toolOutput(targetJavaHome.resolve("bin/java"), "-version");
        String targetMavenOutput = toolOutput(maven, targetJavaHome, "-version");
        assertTrue(sourceJavaOutput.contains("version \"11.0.26\""));
        assertTrue(sourceMavenOutput.contains("Apache Maven 3.9.11")
                && sourceMavenOutput.contains("Java version: 11.0.26"));
        assertTrue(targetJavaOutput.contains("version \"21.0.11\""));
        assertTrue(targetMavenOutput.contains("Apache Maven 3.9.11")
                && targetMavenOutput.contains("Java version: 21.0.11"));

        ObjectMapper json = new ObjectMapper()
                .enable(SerializationFeature.INDENT_OUTPUT)
                .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
        String catalinaSha256 = digest(tomcatHome.resolve("lib/catalina.jar"), "SHA-256");
        String consumedTomcatManifestSha256 =
                SpringMvcWarRuntime.consumedTomcatManifestSha256(tomcatHome);
        SpringMvcWarRuntime.Configuration runtime = SpringMvcWarRuntime.Configuration.of(
                tomcatHome.toString(),
                tomcatVersion,
                catalinaSha256,
                consumedTomcatManifestSha256,
                "",
                oracleCases(),
                json);

        LocalSpringUpgradeExecutionPort port = new LocalSpringUpgradeExecutionPort(
                qualificationRoot,
                Map.of("11", sourceJavaHome, "21", targetJavaHome),
                maven.toString(),
                "gradle",
                Set.of(),
                false,
                false,
                recipeSeedRepository,
                true,
                json,
                new DisabledSpringUpgradeCodingAgentPort("local qualification keeps coding agents disabled"),
                runtime);
        Path runRoot = qualificationRoot.resolve("runs/spring-mvc-5.3.39-to-boot-3.5.3");
        if (Files.exists(runRoot, LinkOption.NOFOLLOW_LINKS)) {
            assertTrue(Files.isDirectory(runRoot, LinkOption.NOFOLLOW_LINKS)
                    && !Files.isSymbolicLink(runRoot));
            try (var children = Files.list(runRoot)) {
                assertTrue(children.allMatch(path -> path.getFileName().toString().equals("maven-home")
                                && Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                                && !Files.isSymbolicLink(path)),
                        "a retried qualification may retain only its isolated Maven dependency cache");
            }
        }

        SpringUpgradeModels.ExecutionResult result;
        String sourceGitTreeSha;
        Path materializedSource = Files.createTempDirectory(
                qualificationRoot, ".exact-source-commit-");
        try {
            sourceGitTreeSha = materializeExactGitSubtree(
                    harnessRoot, sourceCommit, sourceRelative, materializedSource);
            assertEquals(SOURCE_GIT_TREE_SHA, sourceGitTreeSha,
                    "the pinned commit must resolve to the reviewed source corpus tree");
            String materializedRelative = qualificationRoot.relativize(materializedSource)
                    .toString().replace('\\', '/');
            SpringUpgradeModels.StartRequest request = new SpringUpgradeModels.StartRequest(
                    "elmos-local-engineering",
                    SourceMode.MATERIALIZED_SNAPSHOT,
                    "",
                    "",
                    sourceCommit,
                    null,
                    materializedRelative,
                    false,
                    "spring-mvc-exact-local-qualification",
                    "3.5.3",
                    "21");
            QualificationControl control = new QualificationControl(qualificationRoot);
            try (control) {
                result = port.execute(request, runRoot, control);
            }
            writeTextAtomically(
                    runRoot.resolve("evidence/control.log"),
                    String.join("\n", control.lines()) + "\n");
            writeTextAtomically(
                    runRoot.resolve("evidence/source-build.log"),
                    String.join("\n", control.stageLines(Stage.SOURCE_BASELINE)) + "\n");
            writeTextAtomically(
                    runRoot.resolve("evidence/target-build.log"),
                    String.join("\n", control.stageLines(Stage.BUILD_AND_TEST)) + "\n");
        } finally {
            deleteExactMaterialization(qualificationRoot, materializedSource);
        }

        assertEquals("spring-mvc", result.fingerprint().sourceFrameworkFamily());
        assertEquals("5.3.39", result.fingerprint().sourceFrameworkVersion());
        assertEquals("11", SpringRouteCatalog.normalizeJava(result.fingerprint().javaVersion()));
        assertTrue(Files.isRegularFile(result.downloadArtifact(), LinkOption.NOFOLLOW_LINKS));
        assertEquals(result.artifactSha256(), digest(result.downloadArtifact(), "SHA-256"));
        Path executedWar = SpringMvcWarRuntime.executableBootWar(
                result.migratedRepository(), SpringRouteCatalog.MAVEN_BUILD_TOOL);
        Map<String, String> executedWarManifest = executableWarManifest(executedWar);
        assertEquals(SpringMvcWarRuntime.WAR_LAUNCHER, executedWarManifest.get("Main-Class"));
        assertEquals("io.elmos.legacy.LegacyMvcApplication", executedWarManifest.get("Start-Class"));
        assertEquals("3.5.3", executedWarManifest.get("Spring-Boot-Version"));
        JsonNode oracle = json.readTree(runRoot.resolve("evidence/spring-mvc-http-oracle.json").toFile());
        assertEquals("PASS_LOCAL_ENGINEERING", oracle.path("status").asText());
        assertEquals(2, oracle.path("comparisons").size());
        assertTrue(Files.size(runRoot.resolve("evidence/source-startup.log")) > 0);
        assertTrue(Files.size(runRoot.resolve("evidence/target-startup.log")) > 0);

        Path preservedSourceWar = runRoot.resolve(
                "artifacts/executed-source-spring-mvc-5.3.39.war");
        assertTrue(Files.isRegularFile(preservedSourceWar, LinkOption.NOFOLLOW_LINKS)
                && !Files.isSymbolicLink(preservedSourceWar));

        Path expectedDownloadArtifact = runRoot.resolve(
                "artifacts/migrated-spring-boot-3.5.3.zip").toAbsolutePath().normalize();
        assertEquals(expectedDownloadArtifact,
                result.downloadArtifact().toAbsolutePath().normalize());
        Path preservedExecutedWar = runRoot.resolve(
                "artifacts/executed-spring-boot-3.5.3.war");
        preserveExact(executedWar, preservedExecutedWar);
        assertEquals(Files.size(executedWar), Files.size(preservedExecutedWar));
        assertEquals(digest(executedWar, "SHA-256"),
                digest(preservedExecutedWar, "SHA-256"));
        Map<String, Object> targetTomcatCore = jarEntryEvidence(
                preservedExecutedWar, TARGET_TOMCAT_ENTRY);
        assertEquals(3_631_718L, targetTomcatCore.get("bytes"));
        assertEquals("c0ca6acafe5ad63cd5de16ec8894318a7b53ea11e3db1bc217fd5f2a9746a790",
                targetTomcatCore.get("sha256"));
        Map<String, Object> recipeSeed = preserveRecipeSeed(
                recipeSeedRepository,
                runRoot.resolve("artifacts/rewrite-recipe-seed"));
        assertEquals(provisionedRecipeSeed, recipeSeed,
                "preserved rewrite recipe seed must match the provisioned immutable bytes");

        Path materializerReceipt = result.migratedRepository()
                .resolve(".elmos/migration-receipt.json");
        Path materializerSourceMap = result.migratedRepository().resolve(".elmos/source-map.json");
        Path preservedMaterializerReceipt = runRoot.resolve(
                "evidence/target-materialization-receipt.json");
        Path preservedMaterializerSourceMap = runRoot.resolve(
                "evidence/target-materialization-source-map.json");
        preserveExact(materializerReceipt, preservedMaterializerReceipt);
        preserveExact(materializerSourceMap, preservedMaterializerSourceMap);
        JsonNode materializerReceiptDocument = json.readTree(
                preservedMaterializerReceipt.toFile());
        assertControlledTargetProfileBindings(materializerReceiptDocument);

        List<Map<String, Object>> evidenceFiles = evidenceInventory(runRoot);
        Instant observedAt = Instant.now();
        Map<String, Object> receipt = new LinkedHashMap<>();
        receipt.put("schema_version", "1.1");
        receipt.put("status", "PASSED_LOCAL");
        receipt.put("claim_scope", "LOCAL_ENGINEERING_EXACT_FIXTURE_ONLY");
        receipt.put("certified", false);
        receipt.put("external_execution_status", "NOT_RUN");
        receipt.put("observed_at", observedAt.toString());
        receipt.put("source_commit", sourceCommit);
        receipt.put("source_git_tree_sha", sourceGitTreeSha);
        receipt.put("source_snapshot_sha256", result.snapshotDigest());
        receipt.put("route_id", SpringMvcWarRuntime.ROUTE_ID);
        receipt.put("pack_key", SpringMvcExactTargetMaterializer.PACK_KEY);
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("spring_framework", "5.3.39");
        source.put("java", sourceJavaOutput);
        source.put("java_release", fileEvidence(sourceJavaHome, sourceJavaRelease));
        source.put("maven", sourceMavenOutput);
        source.put("maven_archive", archiveEvidence(mavenArchive));
        source.put("tomcat", tomcatVersion);
        source.put("tomcat_archive", archiveEvidence(tomcatArchive));
        source.put("catalina_jar", fileEvidence(tomcatHome, tomcatHome.resolve("lib/catalina.jar")));
        source.put("tomcat_consumed_manifest_sha256", consumedTomcatManifestSha256);
        source.put("executed_war", Map.of(
                "path", runRoot.relativize(preservedSourceWar).toString().replace('\\', '/'),
                "format", "spring-framework-mvc-war",
                "sha256", digest(preservedSourceWar, "SHA-256"),
                "bytes", Files.size(preservedSourceWar)));
        receipt.put("source", source);
        Map<String, Object> target = new LinkedHashMap<>();
        target.put("spring_boot", "3.5.3");
        target.put("spring_framework", "6.2.8");
        target.put("embedded_tomcat", "10.1.42");
        target.put("java", targetJavaOutput);
        target.put("java_release", fileEvidence(targetJavaHome, targetJavaRelease));
        target.put("maven", targetMavenOutput);
        target.put("embedded_tomcat_core", targetTomcatCore);
        target.put("download_artifact", Map.of(
                "path", runRoot.relativize(result.downloadArtifact()).toString().replace('\\', '/'),
                "format", "migrated-repository-zip",
                "sha256", result.artifactSha256(),
                "bytes", result.artifactSize()));
        target.put("executed_war", Map.of(
                "path", runRoot.relativize(preservedExecutedWar).toString().replace('\\', '/'),
                "format", "spring-boot-executable-war",
                "sha256", digest(preservedExecutedWar, "SHA-256"),
                "bytes", Files.size(preservedExecutedWar),
                "manifest", executedWarManifest));
        receipt.put("target", target);
        receipt.put("harness", Map.of(
                "repository_head", harnessCommit,
                "worktree_binding", "repository-head-plus-content-addressed-files",
                "files", harnessInventory(harnessRoot),
                "rewrite_recipe_seed", recipeSeed));
        receipt.put("execution", Map.of(
                "source_clean_verify", "PASSED",
                "source_tomcat_startup", "PASSED",
                "openrewrite_actual_execution", true,
                "trusted_java_materializer", "PASSED",
                "target_clean_verify", "PASSED",
                "target_warlauncher_startup", "PASSED",
                "target_actuator_health", "PASSED",
                "get_and_jsp_oracle_comparisons", 2,
                "validation_and_error_contract_tests", "PASSED",
                "bounded_shutdown", "PASSED"));
        receipt.put("evidence_files", evidenceFiles);

        Path policyPath = runRoot.resolve("qualification-policy.json");
        Map<String, Object> policy = qualificationPolicy(
                sourceCommit,
                digest(preservedExecutedWar, "SHA-256"),
                executedWarManifest,
                sourceJavaRelease,
                targetJavaRelease,
                mavenArchive,
                tomcatArchive,
                targetTomcatCore,
                recipeSeed,
                observedAt);
        writeJsonAtomically(json, policyPath, policy);

        Path bindingPath = runRoot.resolve("exact-tuple-binding.json");
        Map<String, Object> exactBinding = exactTupleBinding(
                sourceCommit,
                sourceGitTreeSha,
                result.snapshotDigest(),
                preservedSourceWar,
                preservedExecutedWar,
                executedWarManifest,
                sourceJavaRelease,
                targetJavaRelease,
                mavenArchive,
                tomcatArchive,
                targetTomcatCore,
                materializerReceiptDocument,
                recipeSeed,
                policyPath,
                observedAt);
        writeJsonAtomically(json, bindingPath, exactBinding);

        receipt.put("exact_tuple_binding", Map.of(
                "path", "exact-tuple-binding.json",
                "sha256", "sha256:" + digest(bindingPath, "SHA-256")));
        receipt.put("policy_snapshot", Map.of(
                "path", "qualification-policy.json",
                "sha256", "sha256:" + digest(policyPath, "SHA-256")));
        Path receiptPath = runRoot.resolve("local-qualification.json");
        writeJsonAtomically(json, receiptPath, receipt);
        writeEvidenceIndex(json, runRoot, evidenceFiles, observedAt);
        System.out.println("ELMOS_MVC_QUALIFICATION_RECEIPT="
                + receiptPath);
        System.out.println("ELMOS_MVC_QUALIFICATION_INDEX="
                + runRoot.resolve("evidence-index.json"));
    }

    private static Map<String, Object> qualificationPolicy(
            String sourceCommit,
            String targetArtifactSha256,
            Map<String, String> targetManifest,
            Path sourceJavaRelease,
            Path targetJavaRelease,
            Path mavenArchive,
            Path tomcatArchive,
            Map<String, Object> targetTomcatCore,
            Map<String, Object> recipeSeed,
            Instant observedAt) throws IOException {
        Map<String, Object> policy = new LinkedHashMap<>();
        policy.put("schema_version", 1);
        policy.put("policy_id",
                "spring-framework-5-3-mvc-to-spring-boot-3-5-3-local-qualification");
        policy.put("policy_version", observedAt.toString().substring(0, 10) + ".1");
        policy.put("scope", "LOCAL_ENGINEERING_EXACT_FIXTURE_ONLY");
        policy.put("source_mode", "MATERIALIZED_SNAPSHOT");
        policy.put("controls", Map.of(
                "application_egress", "DENY",
                "customer_data", false,
                "credential_access", false,
                "dependency_resolution", "DECLARED_MAVEN_REPOSITORIES_ONLY",
                "external_certification_promotion", false,
                "production_deployment", false,
                "source_tree_mutation", "DENY",
                "target_artifact_overwrite", false,
                "workspace", "EPHEMERAL_ISOLATED"));
        policy.put("evidence_policy", Map.of(
                "digest_algorithm", "SHA-256",
                "external_evidence_status", "NOT_RUN",
                "independent_verifier_required", true,
                "required_evidence_types", REQUIRED_EXTERNAL_EVIDENCE_TYPES,
                "signature_algorithm", "Ed25519",
                "certification_status", "NOT_CERTIFIED"));
        policy.put("exact_tuple", Map.of(
                "source", Map.of(
                        "framework", "spring-framework-mvc",
                        "framework_version", "5.3.39",
                        "java", "11.0.26",
                        "maven", "3.9.11",
                        "servlet_namespace", "javax.servlet",
                        "servlet_api", "4.0.1",
                        "packaging", "war"),
                "target", Map.of(
                        "framework", "spring-boot",
                        "framework_version", "3.5.3",
                        "spring_framework", "6.2.8",
                        "java", "21.0.11",
                        "maven", "3.9.11",
                        "servlet_namespace", "jakarta.servlet",
                        "servlet_api", "6.1",
                        "embedded_tomcat", "10.1.42",
                        "packaging", "executable-war")));
        policy.put("source_commit", sourceCommit);
        policy.put("target_artifact", Map.of(
                "format", "spring-boot-executable-war",
                "sha256", "sha256:" + targetArtifactSha256,
                "manifest", targetManifest));
        policy.put("rewrite_recipe_artifact", recipeSeed);
        policy.put("toolchain_bindings", Map.of(
                "source-java", "sha256:" + digest(sourceJavaRelease, "SHA-256"),
                "source-maven", "sha256:" + digest(mavenArchive, "SHA-256"),
                "source-container", "sha256:" + digest(tomcatArchive, "SHA-256"),
                "target-java", "sha256:" + digest(targetJavaRelease, "SHA-256"),
                "target-maven", "sha256:" + digest(mavenArchive, "SHA-256"),
                "target-container", "sha256:" + targetTomcatCore.get("sha256")));
        policy.put("promotion_boundary", Map.of(
                "maximum_local_decision", "READY_FOR_EXTERNAL_GATE_REVIEW",
                "certification_authority", "EXTERNAL_ONLY",
                "status_mutation_by_local_runner", false));
        return policy;
    }

    private static Map<String, Object> exactTupleBinding(
            String sourceCommit,
            String sourceGitTreeSha,
            String sourceSnapshotSha256,
            Path sourceArtifact,
            Path targetArtifact,
            Map<String, String> targetManifest,
            Path sourceJavaRelease,
            Path targetJavaRelease,
            Path mavenArchive,
            Path tomcatArchive,
            Map<String, Object> targetTomcatCore,
            JsonNode materializerReceipt,
            Map<String, Object> recipeSeed,
            Path policyPath,
            Instant observedAt) throws IOException {
        JsonNode generator = materializerReceipt.path("generator_binding");
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("commit", sourceCommit);
        source.put("git_tree_sha", sourceGitTreeSha);
        source.put("snapshot_sha256", "sha256:" + sourceSnapshotSha256);
        source.put("framework", "spring-framework-mvc");
        source.put("framework_version", "5.3.39");
        source.put("java", "11.0.26");
        source.put("maven", "3.9.11");
        source.put("servlet_namespace", "javax.servlet");
        source.put("servlet_api", "4.0.1");
        source.put("packaging", "war");
        source.put("artifact_path", "artifacts/executed-source-spring-mvc-5.3.39.war");
        source.put("artifact_sha256", "sha256:" + digest(sourceArtifact, "SHA-256"));
        source.put("artifact_bytes", Files.size(sourceArtifact));
        source.put("artifact_format", "spring-framework-mvc-war");

        Map<String, Object> target = new LinkedHashMap<>();
        target.put("artifact_path", "artifacts/executed-spring-boot-3.5.3.war");
        target.put("artifact_sha256", "sha256:" + digest(targetArtifact, "SHA-256"));
        target.put("artifact_bytes", Files.size(targetArtifact));
        target.put("artifact_format", "spring-boot-executable-war");
        target.put("framework", "spring-boot");
        target.put("framework_version", "3.5.3");
        target.put("spring_framework_version", "6.2.8");
        target.put("java", "21.0.11");
        target.put("maven", "3.9.11");
        target.put("servlet_namespace", "jakarta.servlet");
        target.put("servlet_api", "6.1");
        target.put("embedded_tomcat", "10.1.42");
        target.put("packaging", "executable-war");
        target.put("manifest", targetManifest);

        Map<String, Object> binding = new LinkedHashMap<>();
        binding.put("schema_version", 1);
        binding.put("binding_id",
                "spring-mvc-5.3.39-java-11-to-boot-3.5.3-java-21-"
                        + observedAt.toString().substring(0, 10));
        binding.put("pack_key", SpringMvcExactTargetMaterializer.PACK_KEY);
        binding.put("source", source);
        binding.put("target", target);
        binding.put("toolchain", Map.of(
                "maven_archive_sha256", "sha256:" + digest(mavenArchive, "SHA-256"),
                "maven_archive_sha512", "sha512:" + digest(mavenArchive, "SHA-512"),
                "source_java_release_sha256", "sha256:" + digest(sourceJavaRelease, "SHA-256"),
                "source_tomcat_archive_sha256", "sha256:" + digest(tomcatArchive, "SHA-256"),
                "source_tomcat_archive_sha512", "sha512:" + digest(tomcatArchive, "SHA-512"),
                "source_tomcat_version", "9.0.120",
                "target_java_release_sha256", "sha256:" + digest(targetJavaRelease, "SHA-256"),
                "target_tomcat_core_entry", targetTomcatCore.get("entry"),
                "target_tomcat_core_sha256", "sha256:" + targetTomcatCore.get("sha256")));
        Map<String, Object> transformation = new LinkedHashMap<>();
        transformation.put("recipe_sha256",
                "sha256:" + generator.path("recipe_sha256").asText());
        transformation.put("custom_recipe_coordinate", recipeSeed.get("coordinate"));
        transformation.put("custom_recipe_build_output_timestamp",
                recipeSeed.get("build_output_timestamp"));
        transformation.put("custom_recipe_artifact_sha256", recipeSeed.get("jar_sha256"));
        transformation.put("custom_recipe_pom_sha256", recipeSeed.get("recipe_pom_sha256"));
        transformation.put("custom_recipe_parent_pom_sha256",
                recipeSeed.get("parent_pom_sha256"));
        transformation.put("materializer_contract_sha256",
                "sha256:" + generator.path("materializer_contract_sha256").asText());
        transformation.put("source_fixture_manifest_sha256",
                "sha256:" + generator.path("input_manifest_sha256").asText());
        transformation.put("target_profile_sha256",
                "sha256:" + generator.path("controlled_target_profile_resources")
                        .get(0).path("sha256").asText());
        binding.put("transformation", transformation);
        binding.put("policy", Map.of(
                "path", "qualification-policy.json",
                "sha256", "sha256:" + digest(policyPath, "SHA-256")));
        binding.put("status_boundary", Map.of(
                "local_execution", "PASSED_LOCAL",
                "external_evidence", "NOT_RUN",
                "production_certification", "NOT_CERTIFIED",
                "maximum_local_decision", "READY_FOR_EXTERNAL_GATE_REVIEW",
                "local_runner_may_certify", false));
        return binding;
    }

    private static void writeEvidenceIndex(
            ObjectMapper json,
            Path runRoot,
            List<Map<String, Object>> evidenceFiles,
            Instant observedAt) throws IOException {
        List<Map<String, Object>> files = new ArrayList<>();
        files.add(fileEvidence(runRoot,
                runRoot.resolve("artifacts/executed-source-spring-mvc-5.3.39.war")));
        files.add(fileEvidence(runRoot,
                runRoot.resolve("artifacts/executed-spring-boot-3.5.3.war")));
        files.add(fileEvidence(runRoot,
                runRoot.resolve("artifacts/migrated-spring-boot-3.5.3.zip")));
        for (String relative : REQUIRED_RECIPE_SEED_FILES.keySet().stream().sorted().toList()) {
            files.add(fileEvidence(runRoot,
                    runRoot.resolve("artifacts/rewrite-recipe-seed").resolve(relative)));
        }
        files.add(fileEvidence(runRoot, runRoot.resolve("exact-tuple-binding.json")));
        files.add(fileEvidence(runRoot, runRoot.resolve("qualification-policy.json")));
        files.addAll(evidenceFiles);
        files.add(fileEvidence(runRoot, runRoot.resolve("local-qualification.json")));
        files.sort(Comparator.comparing(item -> String.valueOf(item.get("path"))));

        Map<String, Object> index = new LinkedHashMap<>();
        index.put("schema_version", "1.1");
        index.put("pack_key", SpringMvcExactTargetMaterializer.PACK_KEY);
        index.put("run_id", "spring-mvc-5.3.39-to-boot-3.5.3-local-"
                + observedAt.toString().substring(0, 10));
        index.put("status", "PASSED_LOCAL");
        index.put("claim_scope", "LOCAL_ENGINEERING_EXACT_FIXTURE_ONLY");
        index.put("certification_eligible", false);
        index.put("external_execution_status", "NOT_RUN");
        index.put("receipt_binding", "The index deliberately does not self-reference; "
                + "it binds the final receipt, every receipt-owned raw evidence file, "
                + "the exact tuple and policy, the migrated-repository ZIP, and both "
                + "executable WARs by byte count and SHA-256.");
        index.put("files", files);
        writeJsonAtomically(json, runRoot.resolve("evidence-index.json"), index);
    }

    private static void writeJsonAtomically(
            ObjectMapper json,
            Path target,
            Object value) throws IOException {
        assertTrue(!Files.exists(target, LinkOption.NOFOLLOW_LINKS),
                "qualification output must not overwrite an existing file: " + target);
        Path temporary = Files.createTempFile(
                target.getParent(), "." + target.getFileName(), ".tmp");
        try {
            json.writeValue(temporary.toFile(), value);
            try (FileChannel channel = FileChannel.open(temporary, StandardOpenOption.WRITE)) {
                channel.force(true);
            }
            try {
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
            } catch (java.nio.file.AtomicMoveNotSupportedException unsupported) {
                Files.move(temporary, target);
            }
            try (FileChannel directory = FileChannel.open(
                    target.getParent(), StandardOpenOption.READ)) {
                directory.force(true);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static void writeTextAtomically(Path target, String value) throws IOException {
        assertTrue(!Files.exists(target, LinkOption.NOFOLLOW_LINKS),
                "qualification output must not overwrite an existing file: " + target);
        byte[] raw = value.getBytes(StandardCharsets.UTF_8);
        Path temporary = Files.createTempFile(
                target.getParent(), "." + target.getFileName(), ".tmp");
        try {
            Files.write(
                    temporary,
                    raw,
                    StandardOpenOption.TRUNCATE_EXISTING,
                    StandardOpenOption.WRITE);
            try (FileChannel channel = FileChannel.open(temporary, StandardOpenOption.WRITE)) {
                channel.force(true);
            }
            try {
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
            } catch (java.nio.file.AtomicMoveNotSupportedException unsupported) {
                Files.move(temporary, target);
            }
            try (FileChannel directory = FileChannel.open(
                    target.getParent(), StandardOpenOption.READ)) {
                directory.force(true);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static Map<String, String> executableWarManifest(Path war) throws IOException {
        try (JarFile archive = new JarFile(war.toFile())) {
            Attributes attributes = archive.getManifest().getMainAttributes();
            return Map.of(
                    "Main-Class", attributes.getValue(Attributes.Name.MAIN_CLASS),
                    "Start-Class", attributes.getValue("Start-Class"),
                    "Spring-Boot-Version", attributes.getValue("Spring-Boot-Version"));
        }
    }

    private static String jarManifestValue(Path jar, String name) throws IOException {
        try (JarFile archive = new JarFile(jar.toFile())) {
            return archive.getManifest().getMainAttributes().getValue(name);
        }
    }

    private static Map<String, Object> jarEntryEvidence(Path jar, String entryName)
            throws IOException {
        MessageDigest sha256;
        try {
            sha256 = MessageDigest.getInstance("SHA-256");
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
        try (JarFile archive = new JarFile(jar.toFile())) {
            var entry = archive.getJarEntry(entryName);
            assertTrue(entry != null && !entry.isDirectory(),
                    "required target container entry is missing: " + entryName);
            long bytes = 0;
            try (var input = archive.getInputStream(entry)) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = input.read(buffer)) >= 0) {
                    sha256.update(buffer, 0, read);
                    bytes += read;
                }
            }
            assertEquals(entry.getSize(), bytes);
            return Map.of(
                    "entry", entryName,
                    "bytes", bytes,
                    "sha256", HexFormat.of().formatHex(sha256.digest()));
        }
    }

    private static Map<String, Object> exactRecipeSeedEvidence(Path root) throws IOException {
        Path normalizedRoot = root.toAbsolutePath().normalize();
        assertTrue(Files.isDirectory(normalizedRoot, LinkOption.NOFOLLOW_LINKS)
                        && !Files.isSymbolicLink(normalizedRoot),
                "rewrite recipe seed must be a real directory");
        List<String> observed = new ArrayList<>();
        Files.walkFileTree(normalizedRoot, new SimpleFileVisitor<>() {
            @Override public FileVisitResult preVisitDirectory(
                    Path directory, BasicFileAttributes attributes) {
                assertTrue(!Files.isSymbolicLink(directory),
                        "rewrite recipe seed must not contain symbolic links");
                return FileVisitResult.CONTINUE;
            }

            @Override public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attributes) {
                assertTrue(attributes.isRegularFile()
                                && Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)
                                && !Files.isSymbolicLink(file),
                        "rewrite recipe seed must contain only regular files");
                observed.add(normalizedRoot.relativize(file).toString().replace('\\', '/'));
                assertTrue(observed.size() <= REQUIRED_RECIPE_SEED_FILES.size(),
                        "rewrite recipe seed contains undeclared files");
                return FileVisitResult.CONTINUE;
            }
        });
        observed.sort(String::compareTo);
        assertEquals(REQUIRED_RECIPE_SEED_FILES.keySet().stream().sorted().toList(), observed,
                "rewrite recipe seed must contain the exact three approved Maven artifacts");

        List<Map<String, Object>> files = new ArrayList<>();
        for (String relative : observed) {
            Path file = normalizedRoot.resolve(relative);
            RecipeSeedFile expected = REQUIRED_RECIPE_SEED_FILES.get(relative);
            assertEquals(expected.bytes(), Files.size(file),
                    "rewrite recipe seed byte count drifted: " + relative);
            assertEquals(expected.sha256(), digest(file, "SHA-256"),
                    "rewrite recipe seed digest drifted: " + relative);
            files.add(fileEvidence(normalizedRoot, file));
        }
        return Map.of(
                "coordinate", LocalSpringUpgradeExecutionPort.ELMOS_RECIPE_COORDINATE,
                "build_output_timestamp", RECIPE_BUILD_OUTPUT_TIMESTAMP,
                "jar_sha256", "sha256:" + REQUIRED_RECIPE_SEED_FILES.entrySet().stream()
                        .filter(entry -> entry.getKey().endsWith(".jar"))
                        .findFirst().orElseThrow().getValue().sha256(),
                "recipe_pom_sha256", "sha256:"
                        + REQUIRED_RECIPE_SEED_FILES.get(
                                "io/elmos/elmos-java-recipes/0.1.0-SNAPSHOT/"
                                        + "elmos-java-recipes-0.1.0-SNAPSHOT.pom").sha256(),
                "parent_pom_sha256", "sha256:"
                        + REQUIRED_RECIPE_SEED_FILES.get(
                                "io/elmos/elmos-parent/0.1.0-SNAPSHOT/"
                                        + "elmos-parent-0.1.0-SNAPSHOT.pom").sha256(),
                "files", List.copyOf(files));
    }

    private static Map<String, Object> preserveRecipeSeed(Path source, Path target)
            throws IOException {
        assertTrue(!Files.exists(target, LinkOption.NOFOLLOW_LINKS),
                "preserved rewrite recipe seed must be create-only");
        for (String relative : REQUIRED_RECIPE_SEED_FILES.keySet().stream().sorted().toList()) {
            preserveExact(source.resolve(relative), target.resolve(relative));
        }
        return exactRecipeSeedEvidence(target);
    }

    private static List<Map<String, Object>> harnessInventory(Path root) throws IOException {
        List<String> relatives = List.of(
                "pom.xml",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/LocalSpringUpgradeExecutionPort.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringCapabilityFingerprint.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringDeploymentGuidance.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringFeatureCatalog.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringMvcExactTargetMaterializer.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringMvcWarRuntime.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringRouteCatalog.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringUpgradeModels.java",
                "apps/java-engine-worker/src/main/resources/rewrite/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml",
                "apps/java-engine-worker/src/main/resources/spring-mvc/exact-5.3.39-fixture-manifest.json",
                "apps/java-engine-worker/src/main/resources/spring-mvc/target-profile/profile.json",
                "apps/java-engine-worker/src/main/resources/spring-mvc/target-profile/scaffold-manifest.json",
                "apps/java-engine-worker/src/test/java/io/elmos/worker/SpringMvcExactLocalQualificationIT.java",
                "recipes/elmos-java-recipes/pom.xml",
                "recipes/elmos-java-recipes/src/main/java/io/elmos/recipes/RewriteSpringFoundation.java",
                "recipes/elmos-java-recipes/src/main/java/io/elmos/recipes/SpringSecurityLambdaChain.java",
                "recipes/elmos-java-recipes/src/test/java/io/elmos/recipes/RewriteSpringFoundationTest.java",
                "recipes/elmos-java-recipes/src/test/java/io/elmos/recipes/SpringSecurityLambdaChainTest.java");
        List<Map<String, Object>> files = new ArrayList<>();
        for (String relative : relatives) {
            files.add(fileEvidence(root, root.resolve(relative)));
        }
        return List.copyOf(files);
    }

    /**
     * Materialize only the requested subtree from the exact Git commit. Reading
     * the checked-out files would let an uncommitted worktree change masquerade
     * as the pinned source commit, so qualification reads blobs directly from
     * the repository object database and rejects links, submodules and special
     * file modes.
     */
    private static String materializeExactGitSubtree(
            Path repositoryRoot,
            String commitSha,
            String rawSubtree,
            Path destination) throws Exception {
        assertTrue(commitSha.matches("[0-9a-f]{40}"),
                "source commit must be a full lowercase SHA-1");
        assertTrue(rawSubtree != null
                        && rawSubtree.matches("[A-Za-z0-9._/-]+")
                        && !rawSubtree.startsWith("/")
                        && !rawSubtree.endsWith("/")
                        && !rawSubtree.contains("//"),
                "source subtree must use the bounded repository-relative grammar");
        Path relativeSubtree = Path.of(rawSubtree).normalize();
        assertTrue(!relativeSubtree.isAbsolute()
                        && !relativeSubtree.startsWith("..")
                        && !relativeSubtree.toString().equals("."),
                "source subtree must stay below the repository root");
        Path normalizedDestination = destination.toAbsolutePath().normalize();
        assertTrue(Files.isDirectory(normalizedDestination, LinkOption.NOFOLLOW_LINKS)
                        && !Files.isSymbolicLink(normalizedDestination),
                "materialization destination must be a real directory");

        String gitPath = relativeSubtree.toString().replace('\\', '/');
        try (Git git = Git.open(repositoryRoot.toFile())) {
            Repository repository = git.getRepository();
            try (RevWalk revisions = new RevWalk(repository)) {
                ObjectId resolved = repository.resolve(commitSha + "^{commit}");
                assertTrue(resolved != null && commitSha.equals(resolved.name()),
                        "the pinned source commit is unavailable or resolves differently");
                RevCommit commit = revisions.parseCommit(resolved);
                ObjectId subtreeId;
                try (TreeWalk selected = TreeWalk.forPath(repository, gitPath, commit.getTree())) {
                    assertTrue(selected != null && FileMode.TREE.equals(selected.getFileMode(0)),
                            "the pinned source subtree is unavailable at the exact commit");
                    subtreeId = selected.getObjectId(0).copy();
                }

                int files = 0;
                long bytes = 0;
                try (TreeWalk tree = new TreeWalk(repository)) {
                    tree.addTree(subtreeId);
                    tree.setRecursive(true);
                    while (tree.next()) {
                        FileMode mode = tree.getFileMode(0);
                        assertTrue(FileMode.REGULAR_FILE.equals(mode)
                                        || FileMode.EXECUTABLE_FILE.equals(mode),
                                "source subtree contains a link, submodule or special file: "
                                        + tree.getPathString());
                        Path relative = Path.of(tree.getPathString()).normalize();
                        assertTrue(!relative.isAbsolute()
                                        && !relative.startsWith("..")
                                        && !relative.toString().equals("."),
                                "source blob path escapes the materialization root");
                        Path target = normalizedDestination.resolve(relative).normalize();
                        assertTrue(target.startsWith(normalizedDestination)
                                        && !target.equals(normalizedDestination),
                                "source blob target escapes the materialization root");
                        long blobBytes = repository.open(
                                tree.getObjectId(0), Constants.OBJ_BLOB).getSize();
                        files = Math.addExact(files, 1);
                        bytes = Math.addExact(bytes, blobBytes);
                        assertTrue(files <= MAX_SOURCE_TREE_FILES
                                        && bytes <= MAX_SOURCE_TREE_BYTES,
                                "source subtree exceeds qualification materialization limits");
                        assertTrue(!Files.exists(target, LinkOption.NOFOLLOW_LINKS),
                                "source subtree contains a colliding path");
                        Files.createDirectories(target.getParent());
                        try (var input = repository.open(
                                        tree.getObjectId(0), Constants.OBJ_BLOB).openStream();
                             var output = Files.newOutputStream(
                                     target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
                            long copied = input.transferTo(output);
                            assertEquals(blobBytes, copied,
                                    "materialized blob byte count must match Git");
                        }
                    }
                }
                assertTrue(files > 0, "source subtree must contain regular files");
                return subtreeId.name();
            }
        }
    }

    private static String exactGitHead(Path repositoryRoot) throws Exception {
        try (Git git = Git.open(repositoryRoot.toFile())) {
            ObjectId head = git.getRepository().resolve("HEAD^{commit}");
            assertTrue(head != null, "qualification harness HEAD must resolve to a commit");
            return head.name();
        }
    }

    private static void deleteExactMaterialization(Path qualificationRoot, Path materialized)
            throws IOException {
        Path root = qualificationRoot.toAbsolutePath().normalize();
        Path target = materialized.toAbsolutePath().normalize();
        assertTrue(target.getParent() != null
                        && target.getParent().equals(root)
                        && target.getFileName().toString().startsWith(".exact-source-commit-"),
                "temporary source cleanup target is outside the exact qualification scope");
        if (!Files.exists(target, LinkOption.NOFOLLOW_LINKS)) return;
        Files.walkFileTree(target, new SimpleFileVisitor<>() {
            @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attributes)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override public FileVisitResult postVisitDirectory(Path directory, IOException error)
                    throws IOException {
                if (error != null) throw error;
                Files.delete(directory);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    private static void preserveExact(Path source, Path target) throws IOException {
        assertTrue(Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS)
                        && !Files.isSymbolicLink(source),
                "preserved evidence source must be a real regular file: " + source);
        assertTrue(!Files.exists(target, LinkOption.NOFOLLOW_LINKS),
                "preserved evidence target must not already exist: " + target);
        Files.createDirectories(target.getParent());
        Path temporary = Files.createTempFile(
                target.getParent(), "." + target.getFileName(), ".tmp");
        try {
            Files.copy(source, temporary, StandardCopyOption.REPLACE_EXISTING);
            try (FileChannel channel = FileChannel.open(temporary, StandardOpenOption.WRITE)) {
                channel.force(true);
            }
            try {
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
            } catch (java.nio.file.AtomicMoveNotSupportedException unsupported) {
                Files.move(temporary, target);
            }
            try (FileChannel directory = FileChannel.open(
                    target.getParent(), StandardOpenOption.READ)) {
                directory.force(true);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
        assertTrue(Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)
                        && !Files.isSymbolicLink(target),
                "preserved evidence target must be a real regular file: " + target);
        assertEquals(Files.size(source), Files.size(target));
        assertEquals(digest(source, "SHA-256"), digest(target, "SHA-256"));
    }

    private static void assertControlledTargetProfileBindings(JsonNode receipt) {
        assertEquals("spring-framework-5-3-mvc-to-spring-boot-3-5-3",
                receipt.path("pack_key").asText());
        assertEquals("MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED",
                receipt.path("status").asText());
        JsonNode generator = receipt.path("generator_binding");
        assertEquals("c49c796656a34391b892b4a61973161aafce778a4cfc742e5dfb1f0e2eb27f24",
                generator.path("materializer_contract_sha256").asText());
        JsonNode profiles = generator.path("controlled_target_profile_resources");
        assertTrue(profiles.isArray());
        assertEquals(2, profiles.size());
        assertEquals("classpath:/spring-mvc/target-profile/profile.json",
                profiles.get(0).path("resource").asText());
        assertEquals(3731, profiles.get(0).path("bytes").asLong());
        assertEquals("8042f1bed7cde57d13e9794b7a694437d5b12d40f0eb4948c656d942a9297ee1",
                profiles.get(0).path("sha256").asText());
        assertEquals("classpath:/spring-mvc/target-profile/scaffold-manifest.json",
                profiles.get(1).path("resource").asText());
        assertEquals(1773, profiles.get(1).path("bytes").asLong());
        assertEquals("a2e741b1a535c690633b27e0301f6931ad287e2b0ddd3fefb97cb5194d5819d6",
                profiles.get(1).path("sha256").asText());
    }

    private static Map<String, Object> fileEvidence(Path root, Path path) throws IOException {
        Path normalizedRoot = root.toAbsolutePath().normalize();
        Path normalized = path.toAbsolutePath().normalize();
        assertTrue(normalized.startsWith(normalizedRoot)
                        && Files.isRegularFile(normalized, LinkOption.NOFOLLOW_LINKS)
                        && !Files.isSymbolicLink(normalized),
                "evidence file must be a real regular file below its declared root: " + normalized);
        return Map.of(
                "path", normalizedRoot.relativize(normalized).toString().replace('\\', '/'),
                "bytes", Files.size(normalized),
                "sha256", digest(normalized, "SHA-256"));
    }

    private static Map<String, Object> archiveEvidence(Path path) throws IOException {
        return Map.of(
                "path", path.toAbsolutePath().normalize().toString(),
                "bytes", Files.size(path),
                "sha256", digest(path, "SHA-256"),
                "sha512", digest(path, "SHA-512"));
    }

    private static String oracleCases() {
        return """
                [
                  {
                    "id": "source-readiness-order-42",
                    "method": "GET",
                    "path": "/api/orders/42",
                    "headers": {"accept": "application/json"},
                    "expected_statuses": [200],
                    "body_mode": "EXACT_BYTES",
                    "readiness": true
                  },
                  {
                    "id": "odd-order-review",
                    "method": "GET",
                    "path": "/api/orders/7",
                    "headers": {"accept": "application/json"},
                    "expected_statuses": [200],
                    "body_mode": "EXACT_BYTES"
                  },
                  {
                    "id": "jsp-order-list",
                    "method": "GET",
                    "path": "/orders",
                    "headers": {"accept": "text/html"},
                    "expected_statuses": [200],
                    "body_mode": "JSP_UTF8_LINE_ENDINGS"
                  }
                ]
                """;
    }

    private record RecipeSeedFile(long bytes, String sha256) { }

    private static List<Map<String, Object>> evidenceInventory(Path runRoot) throws IOException {
        List<Path> paths;
        try (var stream = Files.walk(runRoot.resolve("evidence"))) {
            paths = stream.filter(path -> Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
                    .sorted(Comparator.comparing(path -> runRoot.relativize(path).toString()))
                    .toList();
        }
        List<Map<String, Object>> files = new ArrayList<>();
        for (Path path : paths) {
            files.add(Map.of(
                    "path", runRoot.relativize(path).toString().replace('\\', '/'),
                    "bytes", Files.size(path),
                    "sha256", digest(path, "SHA-256")));
        }
        return List.copyOf(files);
    }

    private static String toolOutput(Path executable, String argument) throws Exception {
        Process process = new ProcessBuilder(executable.toString(), argument).redirectErrorStream(true).start();
        byte[] output = process.getInputStream().readAllBytes();
        assertTrue(process.waitFor(15, java.util.concurrent.TimeUnit.SECONDS));
        assertEquals(0, process.exitValue());
        return new String(output, StandardCharsets.UTF_8).trim();
    }

    private static String toolOutput(Path executable, Path javaHome, String argument) throws Exception {
        ProcessBuilder builder = new ProcessBuilder(executable.toString(), argument).redirectErrorStream(true);
        builder.environment().put("JAVA_HOME", javaHome.toString());
        Process process = builder.start();
        byte[] output = process.getInputStream().readAllBytes();
        assertTrue(process.waitFor(15, java.util.concurrent.TimeUnit.SECONDS));
        assertEquals(0, process.exitValue());
        return new String(output, StandardCharsets.UTF_8).trim();
    }

    private static String digest(Path path, String algorithm) throws IOException {
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance(algorithm);
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
        try (var input = Files.newInputStream(path)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = input.read(buffer)) >= 0) digest.update(buffer, 0, read);
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static Path absoluteDirectory(String name) {
        Path path = Path.of(required(name));
        assertTrue(path.isAbsolute() && Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                && !Files.isSymbolicLink(path), name + " must be an absolute real directory");
        return path.toAbsolutePath().normalize();
    }

    private static Path absoluteRegularFile(String name) {
        Path path = Path.of(required(name));
        assertTrue(path.isAbsolute() && Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                && !Files.isSymbolicLink(path), name + " must be an absolute regular file");
        return path.toAbsolutePath().normalize();
    }

    private static Path absoluteRegularFile(Path path) {
        assertTrue(path.isAbsolute() && Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                && !Files.isSymbolicLink(path), path + " must be an absolute regular file");
        return path.toAbsolutePath().normalize();
    }

    private static String required(String name) {
        String value = System.getenv(name);
        assertTrue(value != null && !value.isBlank(), name + " is required");
        return value.trim();
    }

    private static void requireCapacity(Path path, long floor, String stage) throws IOException {
        FileStore store = Files.getFileStore(path);
        assertTrue(store.getUsableSpace() >= floor,
                stage + " requires at least " + floor + " usable bytes; found " + store.getUsableSpace());
    }

    private static final class QualificationControl
            implements SpringUpgradeExecutionPort.Control, AutoCloseable {
        private final Path capacityPath;
        private final CopyOnWriteArrayList<String> lines = new CopyOnWriteArrayList<>();
        private final Set<Process> processes = ConcurrentHashMap.newKeySet();
        private final AtomicBoolean closed = new AtomicBoolean();
        private final AtomicBoolean capacityStop = new AtomicBoolean();
        private final Thread monitor;

        QualificationControl(Path capacityPath) {
            this.capacityPath = capacityPath;
            this.monitor = Thread.ofPlatform().daemon().name("mvc-capacity-monitor").start(() -> {
                while (!closed.get()) {
                    try {
                        long usable = Files.getFileStore(capacityPath).getUsableSpace();
                        if (usable <= HARD_STOP_FLOOR) {
                            capacityStop.set(true);
                            log("CAPACITY_HARD_STOP usable_bytes=" + usable);
                            processes.stream().filter(Process::isAlive).forEach(Process::destroyForcibly);
                            return;
                        }
                        Thread.sleep(1_000);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        return;
                    } catch (IOException error) {
                        capacityStop.set(true);
                        log("CAPACITY_MONITOR_FAILED " + error.getClass().getSimpleName());
                        processes.stream().filter(Process::isAlive).forEach(Process::destroyForcibly);
                        return;
                    }
                }
            });
        }

        @Override public void stage(Stage stage, String message) {
            log("STAGE " + stage + " " + message);
        }

        @Override public void log(String line) {
            String bounded = line == null ? "" : line.replace('\r', ' ').replace('\n', ' ');
            if (bounded.length() > 16_384) bounded = bounded.substring(0, 16_384);
            lines.add(bounded);
            System.out.println(bounded);
        }

        @Override public void process(Process process) {
            if (process != null) processes.add(process);
        }

        @Override public boolean cancelled() {
            return capacityStop.get();
        }

        List<String> lines() {
            return List.copyOf(lines);
        }

        List<String> stageLines(Stage requested) {
            String marker = "STAGE " + requested + " ";
            List<String> selected = new ArrayList<>();
            boolean capture = false;
            for (String line : lines) {
                if (line.startsWith("STAGE ")) {
                    if (capture) break;
                    capture = line.startsWith(marker);
                }
                if (capture) selected.add(line);
            }
            assertTrue(!selected.isEmpty(), "missing raw stage log for " + requested);
            return List.copyOf(selected);
        }

        @Override public void close() throws InterruptedException {
            closed.set(true);
            monitor.interrupt();
            monitor.join(5_000);
            processes.stream().filter(Process::isAlive).forEach(Process::destroyForcibly);
        }
    }
}
