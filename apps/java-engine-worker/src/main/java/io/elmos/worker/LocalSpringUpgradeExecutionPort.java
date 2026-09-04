package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.elmos.snapshot.DeterministicSnapshotArchiver;
import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.lib.Constants;
import org.eclipse.jgit.revwalk.RevWalk;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

import static io.elmos.worker.SpringUpgradeModels.*;

/**
 * Executes only inside a pre-approved private Runner. It never invokes a shell and never accepts
 * embedded credentials. Production deployment must place this worker in the rootless Workspace
 * security domain; the default configuration keeps this adapter disabled.
 */
final class LocalSpringUpgradeExecutionPort implements SpringUpgradeExecutionPort {
    /**
     * One client for every loopback probe this class makes.
     *
     * <p>Each {@link HttpClient} owns a selector thread and an executor, and the
     * class is never closed here, so a client built per probe kept those threads
     * alive until it was collected. Every run made several, and concurrent runs
     * multiplied them. The probes all target 127.0.0.1 with the same two-second
     * connect timeout, so a single shared client is equivalent.</p>
     */
    private static final HttpClient LOOPBACK_PROBE_CLIENT =
            HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();

    private static final long MAX_SOURCE_BYTES = 512L * 1024 * 1024;
    private static final int MAX_SOURCE_FILES = 100_000;
    private static final long MAX_CAPABILITY_MANIFEST_BYTES = 512L * 1024;
    private static final int MAX_HEALTH_RESPONSE_BYTES = 64 * 1024;
    static final String ELMOS_RECIPE_COORDINATE =
            "io.elmos:elmos-java-recipes:0.1.0-SNAPSHOT";
    private static final Path ELMOS_RECIPE_REPOSITORY_PATH =
            Path.of("io", "elmos", "elmos-java-recipes", "0.1.0-SNAPSHOT");
    private static final Path ELMOS_PARENT_REPOSITORY_PATH =
            Path.of("io", "elmos", "elmos-parent", "0.1.0-SNAPSHOT");
    private static final Path CAPABILITY_TEST_MANIFEST =
            Path.of("elmos", "spring-capability-tests.json");
    private static final Set<String> COMPLEX_CAPABILITY_STATES = Set.of(
            "observed", "conditional", "declared-only", "generated", "unknown");
    private static final Map<String, List<String>> REQUIRED_COMPLEX_CAPABILITY_INVARIANTS = Map.of(
            "security", List.of(
                    "authentication-success-and-failure",
                    "authorization-allow-and-deny",
                    "filter-chain-order",
                    "csrf-cors-session-and-error-contract"),
            "persistence_database", List.of(
                    "schema-mapping-and-generated-identifiers",
                    "query-result-null-and-precision-equivalence",
                    "constraint-locking-and-exception-semantics",
                    "provider-dialect-and-transaction-resource-binding"),
            "transactions", List.of(
                    "commit-rollback-and-exception-timing",
                    "propagation-isolation-read-only-and-timeout",
                    "transaction-manager-selection",
                    "nested-and-self-invocation-boundaries"),
            "messaging", List.of(
                    "payload-header-and-serialization-equivalence",
                    "ack-retry-redelivery-and-dead-letter",
                    "ordering-concurrency-and-duplicate-handling",
                    "broker-transaction-boundaries"));
    private static final Set<String> EXCLUDED = Set.of(
            ".git", "target", ".gradle", ".idea", ".vscode", ".elmos",
            ".env", "id_rsa", "id_ed25519"
    );
    private final Path workspaceRoot;
    /**
     * Source JDKs keyed by Java release. A multi-version catalog needs more than
     * one source JDK: a Spring Boot 1.5 baseline has to build on Java 8 while a
     * Boot 3.4 baseline needs 17 or 21. Only the releases an operator actually
     * provisioned are present, and a route that needs a missing one is blocked
     * with the release named instead of silently compiling on the wrong JDK.
     */
    private final Map<String, Path> javaHomes;
    private final String mavenExecutable;
    private final String gradleExecutable;
    private final Set<String> allowedGitHosts;
    private final boolean allowFileRepositories;
    private final boolean mavenOffline;
    private final Path dependencySeedRepository;
    private final boolean experimentalRoutesEnabled;
    private final ObjectMapper json;
    private final SpringMvcWarRuntime.Configuration springMvcWarRuntime;
    /**
     * Defaults to {@link DisabledSpringUpgradeCodingAgentPort} in every constructor
     * that does not accept one explicitly, so every existing call site keeps its
     * exact current behavior: {@link #recordCodingAgentCandidates} is a no-op
     * whenever this field stays disabled, and the post-repair failure path throws
     * the identical {@code MAVEN_COMMAND_FAILED} it always has. See ADR-0059.
     */
    private final SpringUpgradeCodingAgentPort codingAgentPort;

    LocalSpringUpgradeExecutionPort(Path workspaceRoot, Path sourceJavaHome, Path targetJavaHome,
                                    String mavenExecutable, Set<String> allowedGitHosts,
                                    boolean allowFileRepositories, ObjectMapper json) {
        this(workspaceRoot, sourceJavaHome, targetJavaHome, mavenExecutable, allowedGitHosts,
                allowFileRepositories, false, null, json);
    }

    LocalSpringUpgradeExecutionPort(Path workspaceRoot, Path sourceJavaHome, Path targetJavaHome,
                                    String mavenExecutable, Set<String> allowedGitHosts,
                                    boolean allowFileRepositories, boolean mavenOffline,
                                    ObjectMapper json) {
        this(workspaceRoot, sourceJavaHome, targetJavaHome, mavenExecutable, allowedGitHosts,
                allowFileRepositories, mavenOffline, null, json);
    }

    LocalSpringUpgradeExecutionPort(Path workspaceRoot, Path sourceJavaHome, Path targetJavaHome,
                                    String mavenExecutable, Set<String> allowedGitHosts,
                                    boolean allowFileRepositories, boolean mavenOffline,
                                    Path dependencySeedRepository, ObjectMapper json) {
        this(workspaceRoot, Map.of("17", sourceJavaHome, SpringRouteCatalog.TARGET_JAVA, targetJavaHome),
                mavenExecutable, allowedGitHosts, allowFileRepositories, mavenOffline,
                dependencySeedRepository, false, json);
    }

    LocalSpringUpgradeExecutionPort(Path workspaceRoot, Map<String, Path> configuredJavaHomes,
                                    String mavenExecutable, Set<String> allowedGitHosts,
                                    boolean allowFileRepositories, boolean mavenOffline,
                                    Path dependencySeedRepository, boolean experimentalRoutesEnabled,
                                    ObjectMapper json) {
        this(workspaceRoot, configuredJavaHomes, mavenExecutable, allowedGitHosts, allowFileRepositories,
                mavenOffline, dependencySeedRepository, experimentalRoutesEnabled, json,
                new DisabledSpringUpgradeCodingAgentPort(
                        "Spring upgrade long-tail Coding Agent model selection was not wired into this "
                                + "execution port instance; see docs/adr/ADR-0059-coding-agent-model-catalog.md."));
    }

    LocalSpringUpgradeExecutionPort(Path workspaceRoot, Map<String, Path> configuredJavaHomes,
                                    String mavenExecutable, String gradleExecutable,
                                    Set<String> allowedGitHosts, boolean allowFileRepositories,
                                    boolean mavenOffline, Path dependencySeedRepository,
                                    boolean experimentalRoutesEnabled, ObjectMapper json) {
        this(workspaceRoot, configuredJavaHomes, mavenExecutable, gradleExecutable,
                allowedGitHosts, allowFileRepositories, mavenOffline, dependencySeedRepository,
                experimentalRoutesEnabled, json,
                new DisabledSpringUpgradeCodingAgentPort(
                        "Spring upgrade long-tail Coding Agent model selection was not wired into this "
                                + "execution port instance; see docs/adr/ADR-0059-coding-agent-model-catalog.md."));
    }

    LocalSpringUpgradeExecutionPort(Path workspaceRoot, Map<String, Path> configuredJavaHomes,
                                    String mavenExecutable, Set<String> allowedGitHosts,
                                    boolean allowFileRepositories, boolean mavenOffline,
                                    Path dependencySeedRepository, boolean experimentalRoutesEnabled,
                                    ObjectMapper json, SpringUpgradeCodingAgentPort codingAgentPort) {
        this(workspaceRoot, configuredJavaHomes, mavenExecutable, "gradle", allowedGitHosts,
                allowFileRepositories, mavenOffline, dependencySeedRepository,
                experimentalRoutesEnabled, json, codingAgentPort);
    }

    LocalSpringUpgradeExecutionPort(Path workspaceRoot, Map<String, Path> configuredJavaHomes,
                                    String mavenExecutable, String gradleExecutable,
                                    Set<String> allowedGitHosts, boolean allowFileRepositories,
                                    boolean mavenOffline, Path dependencySeedRepository,
                                    boolean experimentalRoutesEnabled, ObjectMapper json,
                                    SpringUpgradeCodingAgentPort codingAgentPort) {
        this(workspaceRoot, configuredJavaHomes, mavenExecutable, gradleExecutable,
                allowedGitHosts, allowFileRepositories, mavenOffline, dependencySeedRepository,
                experimentalRoutesEnabled, json, codingAgentPort,
                SpringMvcWarRuntime.Configuration.unconfigured());
    }

    LocalSpringUpgradeExecutionPort(Path workspaceRoot, Map<String, Path> configuredJavaHomes,
                                    String mavenExecutable, String gradleExecutable,
                                    Set<String> allowedGitHosts, boolean allowFileRepositories,
                                    boolean mavenOffline, Path dependencySeedRepository,
                                    boolean experimentalRoutesEnabled, ObjectMapper json,
                                    SpringUpgradeCodingAgentPort codingAgentPort,
                                    SpringMvcWarRuntime.Configuration springMvcWarRuntime) {
        this.workspaceRoot = normalizeRoot(workspaceRoot);
        this.javaHomes = verifiedJavaHomes(configuredJavaHomes);
        Path mavenProbeJavaHome = this.javaHomes.entrySet().stream()
                .max(Comparator.comparingInt(entry -> Integer.parseInt(entry.getKey())))
                .orElseThrow()
                .getValue();
        this.mavenExecutable = requireMaven(mavenExecutable, mavenProbeJavaHome);
        this.gradleExecutable = requireExecutable(gradleExecutable, "Gradle");
        this.allowedGitHosts = Set.copyOf(allowedGitHosts);
        this.allowFileRepositories = allowFileRepositories;
        this.mavenOffline = mavenOffline;
        this.dependencySeedRepository = normalizeDependencySeed(
                dependencySeedRepository, this.workspaceRoot, mavenOffline);
        this.experimentalRoutesEnabled = experimentalRoutesEnabled;
        this.json = Objects.requireNonNull(json);
        this.codingAgentPort = Objects.requireNonNull(codingAgentPort, "codingAgentPort");
        this.springMvcWarRuntime = Objects.requireNonNull(springMvcWarRuntime, "springMvcWarRuntime");
    }

    /** Java releases this Runner can build a source baseline with. */
    Set<String> provisionedJavaReleases() {
        return javaHomes.keySet();
    }

    private static Map<String, Path> verifiedJavaHomes(Map<String, Path> configured) {
        Objects.requireNonNull(configured, "java homes");
        if (configured.isEmpty()) throw new IllegalStateException("at least one JAVA_HOME is required");
        Map<String, Path> verified = new TreeMap<>();
        for (Map.Entry<String, Path> entry : configured.entrySet()) {
            String release = SpringRouteCatalog.normalizeJava(entry.getKey());
            int major;
            try {
                major = Integer.parseInt(release);
            } catch (NumberFormatException error) {
                throw new IllegalArgumentException("JAVA_HOME key must be a Java release: " + entry.getKey());
            }
            verified.put(release, requireJavaHome(entry.getValue(), major, "java-" + release));
        }
        return Map.copyOf(verified);
    }

    private Path sourceJavaHome(String release) {
        Path home = javaHomes.get(SpringRouteCatalog.normalizeJava(release));
        if (home == null) {
            throw blocked("SOURCE_JDK_NOT_PROVISIONED",
                    "The repository declares Java " + release + " but this Runner only provides "
                            + String.join(", ", javaHomes.keySet())
                            + ". Provision the matching JDK before running this route.");
        }
        return home;
    }

    private Path targetJavaHome(String release) {
        String normalized = SpringRouteCatalog.normalizeJava(release);
        Path home = javaHomes.get(normalized);
        if (home == null) {
            throw blocked("TARGET_JDK_NOT_PROVISIONED",
                    "The selected route targets Java " + normalized + " but this Runner only provides "
                            + String.join(", ", javaHomes.keySet())
                            + ". Provision the exact target JDK before running this route.");
        }
        return home;
    }

    @Override public ExecutionResult execute(StartRequest request, Path rawRunRoot, Control control) {
        Path runRoot = confined(rawRunRoot);
        createDirectory(runRoot);
        Path source = runRoot.resolve("source");
        SourceIdentity identity = prepare(request, source, control);
        checkCancelled(control);

        control.stage(Stage.LOCK_SNAPSHOT, "Creating deterministic immutable source snapshot");
        DeterministicSnapshotArchiver.SnapshotArchive archive;
        DeterministicSnapshotArchiver.SnapshotContext snapshotContext =
                new DeterministicSnapshotArchiver.SnapshotContext(
                        request.sourceMode() == SourceMode.PUBLIC_GIT ? "PUBLIC_GIT" : "MATERIALIZED",
                        safeRepositoryId(request.repositoryUrl()), safeFullName(request.repositoryUrl()),
                        request.requestedRef(), identity.commitSha(), identity.treeSha());
        try {
            archive = new DeterministicSnapshotArchiver().archive(source, snapshotContext);
        } catch (RuntimeException error) {
            throw blocked("SOURCE_SNAPSHOT_REJECTED",
                    "Source content violated deterministic snapshot limits or safety policy.");
        }
        if (Files.exists(source.resolve(".gitmodules"), LinkOption.NOFOLLOW_LINKS))
            throw blocked("SUBMODULE_AUTHORIZATION_REQUIRED", "Submodules require separate repository authorization and hydration.");
        if (containsGitLfsPointer(source))
            throw blocked("GIT_LFS_HYDRATION_REQUIRED", "Git LFS pointers must be hydrated and verified before migration.");
        String snapshotId = request.snapshotId() == null || request.snapshotId().isBlank()
                ? "snapshot-" + archive.archiveSha256().substring(0, 24) : request.snapshotId();
        write(runRoot.resolve("evidence/source-snapshot-manifest.json"), archive.manifest());
        control.log("snapshot locked sha256:" + archive.archiveSha256());

        control.stage(Stage.FINGERPRINT, "Detecting exact Java, Spring Boot, build and active capability tuple");
        Fingerprint fingerprint = fingerprint(source);
        SpringRouteCatalog.Selection selection = selectRoute(fingerprint, request);
        SpringRouteCatalog.SpringRoute route = selection.route();
        String buildTool = fingerprint.buildTool();
        String sourceJava = SpringRouteCatalog.normalizeJava(fingerprint.javaVersion());
        Path sourceJavaHome = sourceJavaHome(sourceJava);
        Path targetJavaHome = targetJavaHome(route.targetJava());
        control.log("fingerprint spring-boot=" + fingerprint.springBootVersion()
                + " source-framework=" + fingerprint.sourceFrameworkFamily()
                + ":" + fingerprint.sourceFrameworkVersion()
                + " java=" + sourceJava + " build=" + fingerprint.buildTool()
                + " route=" + route.routeId() + " evidence=" + selection.evidence());
        Map<String, Object> routeSelection = new LinkedHashMap<>();
        routeSelection.put("schema_version", "1.0");
        routeSelection.put("route_id", route.routeId());
        routeSelection.put("pack_key", route.packKey());
        routeSelection.put("detected_spring_boot", fingerprint.springBootVersion());
        routeSelection.put("detected_source_framework_family", fingerprint.sourceFrameworkFamily());
        routeSelection.put("detected_source_framework_version", fingerprint.sourceFrameworkVersion());
        routeSelection.put("detected_java", sourceJava);
        routeSelection.put("detected_build_tool", fingerprint.buildTool());
        routeSelection.put("accepted_source_constraint", route.sourceConstraint());
        routeSelection.put("route_evidence", selection.evidence().name());
        routeSelection.put("experimental_opt_in_required", selection.requiresExperimentalOptIn());
        routeSelection.put("recipe_id", route.recipeId());
        routeSelection.put("target_spring_boot", route.targetBoot());
        routeSelection.put("target_java", route.targetJava());
        writeJson(runRoot.resolve("evidence/route-selection.json"), routeSelection);

        control.stage(Stage.SOURCE_BASELINE,
                "Running the source repository's complete " + buildTool + " baseline with Java " + sourceJava);
        Path sourceBaseline = runRoot.resolve("source-baseline");
        Path toolHome = runRoot.resolve(buildTool + "-home");
        createDirectory(toolHome);
        if (SpringRouteCatalog.GRADLE_BUILD_TOOL.equals(buildTool)) {
            requireGradleVersion(sourceJavaHome, toolHome);
        }
        if (dependencySeedRepository != null) {
            copyDependencySeed(dependencySeedRepository, toolHome.resolve(".m2/repository"));
            control.log("dependency seed copied into the isolated per-run repository");
        }
        copyTree(source, sourceBaseline);
        TestSummary sourceTests;
        SpringMvcWarRuntime.OracleRun sourceMvcOracle = null;
        try {
            /*
             * Run verify, not only test. Customer repositories frequently bind
             * coverage, static-analysis, integration-test and packaging gates
             * after the test phase. A route must establish those source gates
             * before transformation so that the independent verifier is not
             * the first component to discover an already-failing baseline.
             *
             * The command runs only in the disposable baseline copy. The
             * locked Snapshot remains read-only by construction even when a
             * repository commits target/ or a build plugin mutates its tree.
             */
            runBuild(sourceBaseline, sourceJavaHome, toolHome, control,
                    List.of(SpringRouteCatalog.MAVEN_BUILD_TOOL.equals(buildTool) ? "verify" : "build"),
                    Duration.ofMinutes(25), buildTool);
            sourceTests = testSummary(sourceBaseline);
            requireSourceTests(sourceTests);
            writeJson(runRoot.resolve("evidence/source-test-summary.json"), sourceTests);
            sourceMvcOracle = validateSourceStartup(sourceBaseline, runRoot, control, sourceJavaHome,
                    buildTool, fingerprint, route);
            if (sourceMvcOracle != null) {
                preserveVerifiedArtifact(
                        SpringMvcWarRuntime.sourceWar(sourceBaseline, buildTool),
                        runRoot.resolve("artifacts/executed-source-spring-mvc-5.3.39.war"));
                control.log("preserved the exact source WAR used by the Tomcat 9 runtime oracle");
            }
        } finally {
            deleteTree(sourceBaseline);
        }
        DeterministicSnapshotArchiver.SnapshotArchive postBaseline;
        try {
            postBaseline = new DeterministicSnapshotArchiver().archive(source, snapshotContext);
        } catch (RuntimeException error) {
            throw blocked("SOURCE_BASELINE_MUTATED_SNAPSHOT",
                    "Source baseline execution changed or invalidated the locked Snapshot.");
        }
        if (!archive.archiveSha256().equals(postBaseline.archiveSha256())) {
            throw blocked("SOURCE_BASELINE_MUTATED_SNAPSHOT",
                    "Source baseline execution changed content outside disposable build outputs.");
        }
        control.log("source snapshot remained immutable after baseline execution");

        control.stage(Stage.EXTRACT_FCM, "Extracting versioned Framework Contract Model before transformation");
        Path fcm = runRoot.resolve("evidence/framework-contract-model.json");
        writeJson(fcm, fcm(identity, archive.archiveSha256(), fingerprint, route, selection));

        Path migrated = runRoot.resolve("migrated");
        copyTree(source, migrated);
        control.stage(Stage.OPENREWRITE,
                "Applying pinned OpenRewrite recipe " + route.recipeId() + " for route " + route.routeId());
        runRewrite(migrated, toolHome, control, route, targetJavaHome);
        checkCancelled(control);

        if (SpringMvcExactTargetMaterializer.supports(route)) {
            /*
             * The exact non-Boot MVC route cannot be completed by source-level
             * OpenRewrite alone: web.xml and the two XML application contexts
             * have to become a governed Boot bootstrap/configuration graph.
             * Materialize from the still-immutable source snapshot, never by
             * executing the repository's Python scaffold. The Java emitter
             * accepts only the complete content-addressed 5.3.39 fixture and
             * publishes a fresh target tree atomically.
             */
            Path exactMvcTarget = runRoot.resolve("mvc-exact-materialized-target");
            SpringMvcExactTargetMaterializer.Materialization materialization =
                    SpringMvcExactTargetMaterializer.materialize(
                            source, exactMvcTarget, route, json);
            deleteTree(migrated);
            try {
                Files.move(exactMvcTarget, migrated, StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException unsupported) {
                try {
                    Files.move(exactMvcTarget, migrated);
                } catch (IOException error) {
                    throw blocked("MVC_TARGET_PUBLISH_FAILED",
                            "The validated exact MVC target could not replace the disposable rewrite tree.");
                }
            } catch (IOException error) {
                throw blocked("MVC_TARGET_PUBLISH_FAILED",
                        "The validated exact MVC target could not replace the disposable rewrite tree.");
            }
            control.log("exact MVC target materialized status=" + materialization.status()
                    + " manifest-sha256:" + materialization.manifestSha256()
                    + " source-files=" + materialization.sourceFileCount());
        }

        control.stage(Stage.BUILD_AND_TEST,
                "Running the target repository's complete " + buildTool + " build with Java " + route.targetJava());
        CommandOutcome firstBuild = runBuildOutcome(migrated, targetJavaHome, toolHome, control,
                List.of(SpringRouteCatalog.MAVEN_BUILD_TOOL.equals(buildTool) ? "verify" : "build"),
                Duration.ofMinutes(30), buildTool);
        if (firstBuild.exitCode() != 0) {
            if (SpringMvcExactTargetMaterializer.supports(route)) {
                throw blocked("MVC_EXACT_TARGET_BUILD_FAILED",
                        "The content-addressed exact MVC target failed its real build; generic repair "
                                + "is forbidden because it would invalidate the emitter receipt.");
            }
            control.stage(Stage.DETERMINISTIC_REPAIR,
                    "Target build failed; applying one bounded deterministic OpenRewrite repair cycle");
            runRewrite(migrated, toolHome, control, route, targetJavaHome);
            CommandOutcome secondBuild = runBuildOutcome(migrated, targetJavaHome, toolHome, control,
                    List.of(SpringRouteCatalog.MAVEN_BUILD_TOOL.equals(buildTool) ? "verify" : "build"),
                    Duration.ofMinutes(30), buildTool);
            if (secondBuild.exitCode() != 0) {
                recordCodingAgentCandidates(runRoot, request.organizationId(), identity.commitSha());
                throw blocked(SpringRouteCatalog.MAVEN_BUILD_TOOL.equals(buildTool)
                                ? "MAVEN_COMMAND_FAILED" : "GRADLE_COMMAND_FAILED",
                        "A required build/OpenRewrite command failed; inspect the redacted run log.");
            }
        }
        TestSummary targetTests = testSummary(migrated);
        requireTestParity(sourceTests, targetTests);
        writeJson(runRoot.resolve("evidence/target-test-summary.json"), targetTests);
        writeJson(runRoot.resolve("evidence/test-parity.json"), Map.of(
                "schema_version", "1.0",
                "status", "PASS",
                "source_executed", sourceTests.executed(),
                "target_executed", targetTests.executed(),
                "source_skipped", sourceTests.skipped(),
                "target_skipped", targetTests.skipped(),
                "preserved_test_identities", sourceTests.testIdentities(),
                "new_target_test_identities", targetTests.testIdentities().stream()
                        .filter(value -> !sourceTests.testIdentities().contains(value))
                        .toList()
        ));
        ComplexCapabilityDecision complexCapabilityDecision = evaluateComplexCapabilities(
                source,
                migrated,
                fingerprint,
                new CapabilityTestRun(sourceTests.testIdentities(), sourceTests.skipped()),
                new CapabilityTestRun(targetTests.testIdentities(), targetTests.skipped()),
                json);
        writeJson(runRoot.resolve("evidence/complex-capability-verification.json"),
                complexCapabilityDecision.report());
        control.log("complex capability verification status="
                + complexCapabilityDecision.report().get("status"));
        if (!complexCapabilityDecision.blockers().isEmpty()) {
            throw blocked("COMPLEX_CAPABILITY_VERIFICATION_BLOCKED",
                    "Complex Spring capability verification failed closed: "
                            + String.join(", ", complexCapabilityDecision.blockers().stream()
                            .limit(8).toList()));
        }
        if (sourceMvcOracle != null) {
            control.stage(Stage.HEALTH_CHECK,
                    "Starting the target executable WAR and comparing the exact source HTTP oracle");
            SpringMvcWarRuntime runtime = new SpringMvcWarRuntime();
            SpringMvcWarRuntime.OracleRun targetMvcOracle = runtime.runTarget(
                    migrated, runRoot, targetJavaHome, buildTool, springMvcWarRuntime, control);
            writeJson(runRoot.resolve("evidence/spring-mvc-http-oracle.json"),
                    SpringMvcWarRuntime.compare(sourceMvcOracle, targetMvcOracle));
            control.log("Spring MVC source/target HTTP oracle matched for every configured path");
        }
        SpringDeploymentGuidance.writeTo(migrated, buildTool, route);

        control.stage(Stage.PACKAGE_ARTIFACT, "Packaging migrated repository as a content-addressed ZIP");
        Path artifact = runRoot.resolve("artifacts/" + route.artifactFileName());
        createDirectory(artifact.getParent());
        zip(migrated, artifact);
        String artifactSha = sha256(artifact);
        control.log("artifact sha256:" + artifactSha + " bytes=" + size(artifact));
        return new ExecutionResult(identity.commitSha(), snapshotId, archive.archiveSha256(), fingerprint,
                runRoot.relativize(fcm).toString(), migrated, artifact, artifactSha, size(artifact),
                List.of("/actuator/health", "/health"));
    }

    @Override public RuntimeHandle start(
            ExecutionResult result,
            StartRequest request,
            Path rawRunRoot,
            Control control
    ) {
        Path runRoot = confined(rawRunRoot);
        String targetJava = SpringRouteCatalog.normalizeJava(request.targetJava());
        Path targetJavaHome = targetJavaHome(targetJava);
        control.stage(Stage.START_APPLICATION, "Starting verified artifact with Java " + targetJava);
        Path jar = bootArtifact(result.migratedRepository(), result.fingerprint());
        int port = reservePort();
        Path log = runRoot.resolve("runtime/application.log");
        createDirectory(log.getParent());
        ProcessBuilder builder = new ProcessBuilder(targetJavaHome.resolve("bin/java").toString(), "-jar", jar.toString());
        builder.directory(result.migratedRepository().toFile());
        builder.environment().put("JAVA_HOME", targetJavaHome.toString());
        bindLoopbackEnvironment(builder, port);
        builder.redirectErrorStream(true);
        builder.redirectOutput(ProcessBuilder.Redirect.appendTo(log.toFile()));
        Process process = null;
        try {
            process = builder.start();
            control.process(process);
            control.stage(Stage.HEALTH_CHECK, "Waiting for application health endpoint");
            String health = waitForHealth(process, port, result.healthCandidates(), control);
            control.log("application healthy on loopback port " + port + " path " + health);
            return new RuntimeHandle(process, null, request.organizationId(), port, health);
        } catch (IOException error) {
            throw blocked("APPLICATION_START_FAILED", "Verified artifact could not be started in the private Runner.");
        } catch (RuntimeException error) {
            if (process != null && process.isAlive()) process.destroyForcibly();
            throw error;
        }
    }

    @Override public void stop(RuntimeHandle handle, Control control) {
        if (handle == null || handle.process() == null) return;
        control.stage(Stage.STOP_APPLICATION, "Stopping application and waiting for graceful shutdown");
        Process process = handle.process();
        process.destroy();
        try {
            if (!process.waitFor(15, TimeUnit.SECONDS)) process.destroyForcibly().waitFor(5, TimeUnit.SECONDS);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
        }
        control.log("application stopped");
    }

    private SpringMvcWarRuntime.OracleRun validateSourceStartup(
            Path source,
            Path runRoot,
            Control control,
            Path sourceJavaHome,
            String buildTool,
            Fingerprint fingerprint,
            SpringRouteCatalog.SpringRoute route
    ) {
        if ("spring-mvc".equals(fingerprint.sourceFrameworkFamily())) {
            SpringMvcWarRuntime.requireExactTuple(fingerprint, route);
            control.stage(Stage.HEALTH_CHECK,
                    "Starting source WAR in the digest-bound external Tomcat 9 runtime");
            return new SpringMvcWarRuntime().runSource(
                    source, runRoot, sourceJavaHome, buildTool, springMvcWarRuntime, control);
        }
        if ("spring-framework".equals(fingerprint.sourceFrameworkFamily())) {
            throw blocked("SPRING_FRAMEWORK_SOURCE_RUNTIME_REQUIRED",
                    "A non-web Spring Framework source requires an exact source runtime adapter; "
                            + "the generic Boot jar launcher cannot infer the source application entry point.");
        }
        Path jar = bootJar(source, buildTool);
        int port = reservePort();
        Path log = runRoot.resolve("evidence/source-startup.log");
        createDirectory(log.getParent());
        ProcessBuilder builder = new ProcessBuilder(
                sourceJavaHome.resolve("bin/java").toString(),
                "-jar",
                jar.toString()
        );
        builder.directory(source.toFile());
        builder.environment().put("JAVA_HOME", sourceJavaHome.toString());
        bindLoopbackEnvironment(builder, port);
        builder.redirectErrorStream(true);
        builder.redirectOutput(ProcessBuilder.Redirect.appendTo(log.toFile()));
        Process process = null;
        try {
            process = builder.start();
            control.process(process);
            HttpProbe probe = waitForStartup(
                    process,
                    port,
                    List.of("/actuator/health", "/health", "/"),
                    control
            );
            control.log("source baseline reached the loopback HTTP boundary on path "
                    + probe.path() + " with status " + probe.statusCode());
        } catch (IOException error) {
            throw blocked("SOURCE_STARTUP_FAILED",
                    "Source baseline could not be started with the exact selected source Java toolchain.");
        } finally {
            if (process != null && process.isAlive()) {
                process.destroy();
                try {
                    if (!process.waitFor(10, TimeUnit.SECONDS)) process.destroyForcibly();
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    process.destroyForcibly();
                }
            }
        }
        return null;
    }

    @Override public boolean configured() { return true; }
    @Override public String configurationReason() {
        return "Local execution adapter is enabled; deployment authority must still prove rootless Workspace isolation.";
    }

    @Override public String runtimeConfigurationReason() {
        return "In-process application startup is disabled for product use; configure the rootless per-run Runtime service.";
    }

    private SourceIdentity prepare(StartRequest request, Path source, Control control) {
        control.stage(Stage.IMPORT_GIT, request.sourceMode() == SourceMode.PUBLIC_GIT
                ? "Importing public Git repository without credentials" : "Reading pre-materialized immutable snapshot");
        if (request.sourceMode() == SourceMode.PUBLIC_GIT) return clonePublic(request, source);
        if (request.materializedRelativePath() == null || request.materializedRelativePath().isBlank())
            throw blocked("MATERIALIZED_SNAPSHOT_PATH_REQUIRED", "A snapshot-bound relative path is required.");
        Path materialized = confined(workspaceRoot.resolve(request.materializedRelativePath()));
        if (!Files.isDirectory(materialized, LinkOption.NOFOLLOW_LINKS))
            throw blocked("MATERIALIZED_SNAPSHOT_UNAVAILABLE", "The immutable snapshot workspace is unavailable.");
        copyTree(materialized, source);
        String commit = requireCommit(request.expectedCommitSha());
        return new SourceIdentity(commit, "0".repeat(40));
    }

    private SourceIdentity clonePublic(StartRequest request, Path source) {
        URI uri = validateRepositoryUri(request.repositoryUrl());
        String branch = normalizeRef(request.requestedRef());
        try (Git git = Git.cloneRepository().setURI(uri.toString()).setBranch(branch)
                .setDepth(1).setCloneSubmodules(false).setDirectory(source.toFile()).call()) {
            var head = git.getRepository().resolve(Constants.HEAD + "^{commit}");
            if (head == null) throw blocked("GIT_COMMIT_UNRESOLVED", "Git did not resolve an immutable commit.");
            String commit = head.name();
            if (request.expectedCommitSha() != null && !request.expectedCommitSha().isBlank()
                    && !commit.equals(requireCommit(request.expectedCommitSha())))
                throw blocked("GIT_COMMIT_MISMATCH", "Resolved commit differs from the requested immutable commit.");
            try (RevWalk walk = new RevWalk(git.getRepository())) {
                return new SourceIdentity(commit, walk.parseCommit(head).getTree().getId().name());
            }
        } catch (BlockedException error) {
            throw error;
        } catch (Exception error) {
            deleteTree(source);
            throw blocked("PUBLIC_GIT_IMPORT_FAILED", "The public repository could not be imported at the requested ref.");
        }
    }

    static Fingerprint fingerprint(Path root) {
        Path pom = root.resolve("pom.xml");
        if (!Files.isRegularFile(pom, LinkOption.NOFOLLOW_LINKS)) {
            if (hasGradleBuild(root)) {
                return fingerprintGradle(root);
            }
            throw blocked("BUILD_MODEL_UNRECOGNIZED",
                    "No root pom.xml and no Gradle build script were found; the source build model "
                            + "could not be identified.");
        }
        return fingerprintMaven(root);
    }

    /**
     * Inspect the complete declared Maven reactor. An aggregator POM often owns
     * neither the Spring nor Java version, so reading only {@code /pom.xml}
     * silently misclassifies real multi-module applications. Conversely, a
     * reactor with conflicting exact authorities cannot be represented by the
     * single source tuple used by a migration route and must fail closed.
     */
    static Fingerprint fingerprintMaven(Path root) {
        List<MavenPomModel> reactor = mavenReactor(root);
        Set<String> bootVersions = exactAuthorities(reactor, model -> springBootVersion(model.document()));
        Set<String> javaVersions = exactAuthorities(reactor, model -> javaVersion(model.document()));
        if (bootVersions.size() > 1) {
            throw blocked("MAVEN_REACTOR_SPRING_BOOT_VERSION_CONFLICT",
                    "Maven modules declare multiple exact Spring Boot versions: "
                            + String.join(", ", bootVersions) + ". Split or normalize the reactor before migration.");
        }
        if (javaVersions.size() > 1) {
            throw blocked("MAVEN_REACTOR_JAVA_VERSION_CONFLICT",
                    "Maven modules declare multiple exact Java releases: "
                            + String.join(", ", javaVersions) + ". This route requires one exact source JDK tuple.");
        }
        String boot = bootVersions.stream().findFirst().orElse("");
        String java = javaVersions.stream().findFirst().orElse("");
        List<String> modules = reactor.stream()
                .map(MavenPomModel::path)
                .map(root.toAbsolutePath().normalize()::relativize)
                .map(Path::getParent)
                .filter(Objects::nonNull)
                .map(Path::toString)
                .filter(value -> !value.isBlank())
                .distinct()
                .sorted()
                .toList();
        String pomText = reactor.stream()
                .map(model -> "\n<!-- elmos-reactor-model:"
                        + root.toAbsolutePath().normalize().relativize(model.path()) + " -->\n"
                        + model.text())
                .reduce("", String::concat);
        String modelName = reactor.size() == 1 ? "pom.xml" : "maven-reactor-poms";
        Map<String,List<String>> traces = new TreeMap<>();
        List<String> capabilities = new ArrayList<>();
        capability(pomText, root, modelName, traces, capabilities,
                "spring-boot-parent", "spring-boot-starter-parent");
        List<String> unknowns = new ArrayList<>();
        if (Files.exists(root.resolve(".gitmodules"))) unknowns.add("submodules-present");
        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(root, pomText, modelName);
        Set<String> frameworkVersions = exactAuthorities(
                reactor, model -> springFrameworkVersion(model.document()));
        String sourceFamily = sourceFrameworkFamily(boot, analysis, !frameworkVersions.isEmpty());
        if (isNonBootSpringFamily(sourceFamily) && frameworkVersions.size() > 1) {
            throw blocked("MAVEN_REACTOR_SPRING_FRAMEWORK_VERSION_CONFLICT",
                    "Maven modules declare multiple exact Spring Framework versions: "
                            + String.join(", ", frameworkVersions)
                            + ". This MVC route requires one exact source framework tuple.");
        }
        String sourceFrameworkVersion = "spring-boot".equals(sourceFamily)
                ? boot : frameworkVersions.stream().findFirst().orElse("");
        if (isNonBootSpringFamily(sourceFamily) && blank(sourceFrameworkVersion)) {
            unknowns.add("spring-framework-version-unresolved");
            sourceFrameworkVersion = "UNKNOWN";
        }
        Fingerprint base = new Fingerprint(blank(boot) ? "UNKNOWN" : boot,
                blank(java) ? "UNKNOWN" : java.trim(), "maven", modules,
                capabilities.stream().distinct().sorted().toList(), unknowns, traces,
                sourceFamily, blank(sourceFrameworkVersion) ? "UNKNOWN" : sourceFrameworkVersion);
        return SpringCapabilityFingerprint.enrich(base, analysis);
    }

    private static List<MavenPomModel> mavenReactor(Path rawRoot) {
        Path root = rawRoot.toAbsolutePath().normalize();
        Path rootPom = root.resolve("pom.xml");
        if (!Files.isRegularFile(rootPom, LinkOption.NOFOLLOW_LINKS)) {
            throw blocked("BUILD_MODEL_UNRECOGNIZED", "The Maven reactor root pom.xml is unavailable.");
        }
        final int maxModels = 256;
        Map<Path, MavenPomModel> models = new LinkedHashMap<>();
        Deque<Path> pending = new ArrayDeque<>();
        pending.add(rootPom);
        while (!pending.isEmpty()) {
            Path requested = pending.removeFirst().toAbsolutePath().normalize();
            if (models.containsKey(requested)) continue;
            if (!requested.startsWith(root) || Files.isSymbolicLink(requested)
                    || !Files.isRegularFile(requested, LinkOption.NOFOLLOW_LINKS)) {
                throw blocked("MAVEN_REACTOR_INCOMPLETE",
                        "Every declared Maven module must resolve to a regular in-snapshot pom.xml.");
            }
            try {
                if (!requested.toRealPath().startsWith(root.toRealPath()) || Files.size(requested) > 1024L * 1024L) {
                    throw blocked("MAVEN_REACTOR_MODEL_REJECTED",
                            "A Maven module model escaped the snapshot or exceeded the 1 MiB model limit.");
                }
            } catch (IOException error) {
                throw blocked("MAVEN_REACTOR_MODEL_REJECTED",
                        "A Maven module model could not be resolved safely.");
            }
            if (models.size() >= maxModels) {
                throw blocked("MAVEN_REACTOR_MODEL_LIMIT_EXCEEDED",
                        "The Maven reactor exceeds the 256-module fingerprint limit.");
            }
            Document document = parsePom(requested);
            models.put(requested, new MavenPomModel(requested, document, read(requested)));
            for (String module : children(document, "modules", "module")) {
                if (module.isBlank() || module.contains("${")) {
                    throw blocked("MAVEN_REACTOR_MODULE_UNRESOLVED",
                            "Maven module paths must be exact project-owned relative paths.");
                }
                Path declared = Path.of(module);
                if (declared.isAbsolute()) {
                    throw blocked("MAVEN_REACTOR_MODULE_ESCAPES_SNAPSHOT",
                            "Maven module paths may not be absolute.");
                }
                Path modulePom = requested.getParent().resolve(declared).resolve("pom.xml").normalize();
                if (!modulePom.startsWith(root)) {
                    throw blocked("MAVEN_REACTOR_MODULE_ESCAPES_SNAPSHOT",
                            "A Maven module path escapes the locked source snapshot.");
                }
                pending.addLast(modulePom);
            }
        }
        return List.copyOf(models.values());
    }

    private static Set<String> exactAuthorities(
            List<MavenPomModel> models,
            java.util.function.Function<MavenPomModel, String> extractor
    ) {
        Set<String> values = new TreeSet<>();
        for (MavenPomModel model : models) {
            String value = extractor.apply(model);
            if (!blank(value)) values.add(value.trim());
        }
        return Collections.unmodifiableSet(new LinkedHashSet<>(values));
    }

    private static String javaVersion(Document document) {
        String java = resolveProperty(document, property(document, "java.version"));
        if (blank(java)) java = resolveProperty(document, property(document, "maven.compiler.release"));
        if (blank(java)) java = resolveProperty(document, property(document, "maven.compiler.source"));
        return blank(java) ? "" : SpringRouteCatalog.normalizeJava(java);
    }

    private record MavenPomModel(Path path, Document document, String text) {}

    static Fingerprint fingerprintGradle(Path root) {
        List<Path> modelFiles = List.of("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")
                .stream()
                .map(root::resolve)
                .filter(path -> Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
                .toList();
        String model = modelFiles.stream().map(LocalSpringUpgradeExecutionPort::read)
                .reduce("", (left, right) -> left + "\n" + right);
        String boot = firstMatch(model,
                "org\\.springframework\\.boot['\"]?\\s*\\)?\\s*version\\s*\\(?['\"]([0-9][^'\"]*)",
                "springBootVersion\\s*=\\s*['\"]([0-9][^'\"]*)");
        String java = firstMatch(model,
                "JavaLanguageVersion\\.of\\(\\s*(\\d+)\\s*\\)",
                "JavaVersion\\.VERSION_(\\d+)",
                "(?:sourceCompatibility|targetCompatibility)\\s*=\\s*['\"]?(?:JavaVersion\\.VERSION_)?(\\d+(?:\\.\\d+)?)");
        java = normalizeJavaScriptRelease(java);
        Map<String,List<String>> traces = new TreeMap<>();
        List<String> capabilities = new ArrayList<>();
        String modelName = modelFiles.stream().map(path -> root.relativize(path).toString())
                .findFirst().orElse("build.gradle");
        if (hasSpringBootGradlePlugin(model)) {
            capabilities.add("spring-boot-plugin");
            traces.put("spring-boot-plugin", List.of(modelName + ":org.springframework.boot plugin"));
        }
        capability(model, root, modelName, traces, capabilities, "rewrite-gradle-plugin", "org.openrewrite.rewrite", "org.openrewrite.gradle.RewritePlugin");
        List<String> unknowns = new ArrayList<>();
        if (Files.exists(root.resolve(".gitmodules"))) unknowns.add("submodules-present");
        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(root, model, modelName);
        String sourceFrameworkVersion = springFrameworkVersion(model);
        String sourceFamily = sourceFrameworkFamily(boot, analysis, !blank(sourceFrameworkVersion));
        if ("spring-boot".equals(sourceFamily)) sourceFrameworkVersion = boot;
        if (isNonBootSpringFamily(sourceFamily) && blank(sourceFrameworkVersion)) {
            unknowns.add("spring-framework-version-unresolved");
            sourceFrameworkVersion = "UNKNOWN";
        }
        Fingerprint base = new Fingerprint(blank(boot) ? "UNKNOWN" : boot.trim(),
                blank(java) ? "UNKNOWN" : java.trim(), SpringRouteCatalog.GRADLE_BUILD_TOOL,
                List.of(), capabilities.stream().distinct().sorted().toList(), unknowns, traces,
                sourceFamily, blank(sourceFrameworkVersion) ? "UNKNOWN" : sourceFrameworkVersion.trim());
        return SpringCapabilityFingerprint.enrich(base, analysis);
    }

    private static String firstMatch(String value, String... expressions) {
        for (String expression : expressions) {
            Matcher matcher = Pattern.compile(expression, Pattern.MULTILINE).matcher(value);
            if (matcher.find()) return matcher.group(1).trim();
        }
        return "";
    }

    private static boolean hasSpringBootGradlePlugin(String model) {
        return Pattern.compile(
                        "(?:id\\s*\\(\\s*['\"]org\\.springframework\\.boot['\"]"
                                + "|id\\s+['\"]org\\.springframework\\.boot['\"]"
                                + "|apply\\s+plugin:\\s*['\"]org\\.springframework\\.boot['\"])")
                .matcher(model).find();
    }

    private static String normalizeJavaScriptRelease(String value) {
        if (blank(value)) return value;
        String normalized = value.trim();
        if (normalized.startsWith("1.")) normalized = normalized.substring(2);
        int dot = normalized.indexOf('.');
        return dot >= 0 ? normalized.substring(0, dot) : normalized;
    }

    private static boolean hasGradleBuild(Path root) {
        for (String candidate : List.of("build.gradle", "build.gradle.kts",
                "settings.gradle", "settings.gradle.kts")) {
            if (Files.isRegularFile(root.resolve(candidate), LinkOption.NOFOLLOW_LINKS)) return true;
        }
        return false;
    }

    /**
     * Pick the catalog route for the detected fingerprint and refuse to run a
     * tuple that has no recorded execution evidence unless the operator has
     * explicitly opted in. Widening the catalog must not widen what the engine
     * is willing to claim by default.
     */
    SpringRouteCatalog.Selection selectRoute(Fingerprint fingerprint) {
        return selectRoute(fingerprint, SpringRouteCatalog.TARGET_BOOT,
                SpringRouteCatalog.TARGET_JAVA, experimentalRoutesEnabled);
    }

    SpringRouteCatalog.Selection selectRoute(Fingerprint fingerprint, StartRequest request) {
        return selectRoute(fingerprint, request.targetSpringBoot(), request.targetJava(),
                experimentalRoutesEnabled || request.allowExperimentalRoutes());
    }

    static SpringRouteCatalog.Selection selectRoute(
            Fingerprint fingerprint,
            String targetSpringBoot,
            String targetJava,
            boolean experimentalRoutesEnabled
    ) {
        String sourceFamily = fingerprint.sourceFrameworkFamily();
        SpringRouteCatalog.Selection selection;
        String sourceDescription;
        if (SpringRouteCatalog.SourceFamily.SPRING_MVC.contractValue().equals(sourceFamily)) {
            selection = SpringRouteCatalog.selectSpringMvc(
                    fingerprint.sourceFrameworkVersion(), fingerprint.javaVersion(),
                    fingerprint.buildTool(), targetSpringBoot, targetJava);
            boolean activeMvc = fingerprint.activeCapabilities().contains("spring-mvc")
                    || fingerprint.activeCapabilities().contains("spring-mvc-xml")
                    || fingerprint.activeCapabilities().contains("servlet-initializer");
            if (!activeMvc) {
                throw blocked("SPRING_MVC_RUNTIME_EVIDENCE_REQUIRED",
                        "Route " + selection.route().routeId()
                                + " requires a production Spring MVC controller, XML MVC contract, "
                                + "WebApplicationInitializer or DispatcherServlet source trace; a "
                                + "declared spring-webmvc dependency alone is not active behavior evidence.");
            }
            sourceDescription = "Spring Framework " + fingerprint.sourceFrameworkVersion();
        } else if (SpringRouteCatalog.SourceFamily.SPRING_FRAMEWORK.contractValue().equals(sourceFamily)) {
            selection = SpringRouteCatalog.selectSpringFramework(
                    fingerprint.sourceFrameworkVersion(), fingerprint.javaVersion(),
                    fingerprint.buildTool(), targetSpringBoot, targetJava);
            if (!fingerprint.activeCapabilities().contains("spring-framework")) {
                throw blocked("SPRING_FRAMEWORK_RUNTIME_EVIDENCE_REQUIRED",
                        "The source exposes a Spring Framework version but no observed Spring bean/context "
                                + "behavior; a declared dependency alone is not active source evidence.");
            }
            sourceDescription = "Spring Framework " + fingerprint.sourceFrameworkVersion();
        } else if (SpringRouteCatalog.SourceFamily.SPRING_BOOT.contractValue().equals(sourceFamily)) {
            selection = SpringRouteCatalog.select(
                    fingerprint.springBootVersion(), fingerprint.javaVersion(), fingerprint.buildTool(),
                    targetSpringBoot, targetJava);
            String versionAuthority = SpringRouteCatalog.MAVEN_BUILD_TOOL.equals(fingerprint.buildTool())
                    ? "spring-boot-parent" : "spring-boot-plugin";
            if (!fingerprint.activeCapabilities().contains(versionAuthority)) {
                throw blocked("UNSUPPORTED_BOOT_VERSION_AUTHORITY",
                        "Route " + selection.route().routeId() + " requires " + versionAuthority
                                + " as the source version authority.");
            }
            sourceDescription = "Spring Boot " + fingerprint.springBootVersion();
        } else {
            throw blocked("SPRING_SOURCE_FAMILY_UNRESOLVED",
                    "The source repository did not expose an exact Spring Boot, Spring MVC, or Spring Framework family.");
        }
        if (selection.requiresExperimentalOptIn() && !experimentalRoutesEnabled) {
            throw blocked("SPRING_ROUTE_EVIDENCE_NOT_RUN",
                    "Route " + selection.route().routeId() + " accepts " + sourceDescription + " on Java "
                            + SpringRouteCatalog.normalizeJava(fingerprint.javaVersion())
                            + " to Spring Boot " + selection.route().targetBoot() + " on Java "
                            + selection.route().targetJava()
                            + ", but this tuple has no recorded local execution evidence ("
                            + selection.evidence() + "). Enable "
                            + "elmos.worker.spring-upgrade.experimental-routes-enabled to run it as an "
                            + "explicitly experimental migration.");
        }
        return selection;
    }

    private void runRewrite(Path root, Path toolHome, Control control,
                            SpringRouteCatalog.SpringRoute route, Path targetJavaHome) {
        Path recipeConfig = installExactRecipe(root, route);
        Path recipeRepository = toolHome.resolve(".m2/repository");
        requireElmosRecipeArtifact(recipeRepository);
        if (SpringRouteCatalog.GRADLE_BUILD_TOOL.equals(route.buildTool())) {
            Path initScript = installGradleRewriteInitScript(root, recipeConfig, route);
            runGradle(root, targetJavaHome, toolHome, control, List.of(
                    "rewriteRun",
                    "--init-script", root.relativize(initScript).toString(),
                    "-Drewrite.activeRecipe=" + route.recipeId()
            ), Duration.ofMinutes(30));
            return;
        }
        runMaven(root, targetJavaHome, toolHome, control, List.of(
                "org.openrewrite.maven:rewrite-maven-plugin:" + route.rewriteMavenPlugin() + ":run",
                "-Drewrite.configLocation=" + root.relativize(recipeConfig),
                "-Drewrite.activeRecipes=" + route.recipeId(),
                "-Drewrite.recipeArtifactCoordinates="
                        + String.join(",", rewriteRecipeArtifactCoordinates(route.rewriteSpring())),
                "-Drewrite.exportDatatables=true"
        ), Duration.ofMinutes(30));
    }

    static List<String> rewriteRecipeArtifactCoordinates(String rewriteSpringVersion) {
        if (rewriteSpringVersion == null || rewriteSpringVersion.isBlank()) {
            throw new IllegalArgumentException("rewrite-spring version is required");
        }
        return List.of(
                "org.openrewrite.recipe:rewrite-spring:" + rewriteSpringVersion,
                ELMOS_RECIPE_COORDINATE);
    }

    static boolean hasElmosRecipeArtifact(Path repository) {
        Objects.requireNonNull(repository, "repository");
        Path artifactDirectory = repository.resolve(ELMOS_RECIPE_REPOSITORY_PATH);
        Path parentDirectory = repository.resolve(ELMOS_PARENT_REPOSITORY_PATH);
        return regularFile(artifactDirectory.resolve("elmos-java-recipes-0.1.0-SNAPSHOT.jar"))
                && regularFile(artifactDirectory.resolve("elmos-java-recipes-0.1.0-SNAPSHOT.pom"))
                && regularFile(parentDirectory.resolve("elmos-parent-0.1.0-SNAPSHOT.pom"));
    }

    private static boolean regularFile(Path path) {
        return Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                && !Files.isSymbolicLink(path);
    }

    private static void requireElmosRecipeArtifact(Path repository) {
        if (!hasElmosRecipeArtifact(repository)) {
            throw blocked("ELMOS_RECIPE_ARTIFACT_NOT_SEEDED",
                    "The immutable Maven seed must contain " + ELMOS_RECIPE_COORDINATE
                            + " and its io.elmos:elmos-parent:0.1.0-SNAPSHOT POM before a Spring recipe can run.");
        }
    }

    static boolean hasGradleRewritePlugin(Path root) {
        return findFiles(root, ".gradle", ".gradle.kts").stream()
                .map(LocalSpringUpgradeExecutionPort::read)
                .anyMatch(text -> text.contains("org.openrewrite.rewrite")
                        || text.contains("org.openrewrite.gradle.RewritePlugin"));
    }

    static boolean hasGradleRewriteRecipe(Path root) {
        return findFiles(root, ".gradle", ".gradle.kts", ".toml") .stream()
                .map(LocalSpringUpgradeExecutionPort::read)
                .anyMatch(text -> text.contains("rewrite-spring"));
    }

    static Path installGradleRewriteInitScript(Path root, Path recipeConfig, SpringRouteCatalog.SpringRoute route) {
        Path initScript = root.resolve(".elmos/openrewrite.init.gradle");
        String pluginCoordinate = "org.openrewrite:plugin:" + route.rewriteMavenPlugin();
        String recipeCoordinate = "org.openrewrite.recipe:rewrite-spring:" + route.rewriteSpring();
        String script = """
                initscript {
                    repositories {
                        mavenLocal()
                        mavenCentral()
                        gradlePluginPortal()
                    }
                    dependencies {
                        classpath "%s"
                    }
                }
                allprojects {
                    repositories {
                        mavenLocal()
                        mavenCentral()
                    }
                    afterEvaluate { p ->
                        if (p == rootProject || p.plugins.hasPlugin("java") || p.plugins.hasPlugin("java-base")) {
                            if (!p.plugins.hasPlugin("org.openrewrite.rewrite") && !p.plugins.hasPlugin(org.openrewrite.gradle.RewritePlugin)) {
                                p.apply plugin: org.openrewrite.gradle.RewritePlugin
                            }
                            p.dependencies {
                                add("rewrite", "%s")
                                add("rewrite", "%s")
                            }
                            p.rewrite {
                                configFile = rootProject.file("%s")
                                activeRecipe(System.getProperty("rewrite.activeRecipe"))
                                setExportDatatables(true)
                            }
                        }
                    }
                }
                """.formatted(
                        pluginCoordinate,
                        recipeCoordinate,
                        ELMOS_RECIPE_COORDINATE,
                        root.relativize(recipeConfig).toString().replace('\\', '/'));
        try {
            Files.deleteIfExists(initScript);
        } catch (IOException ignored) {}
        write(initScript, script.getBytes(StandardCharsets.UTF_8));
        return initScript;
    }

    static Path installGradleRewriteInitScript(Path root, Path recipeConfig) {
        Path initScript = root.resolve(".elmos/openrewrite.init.gradle");
        String pluginCoordinate = "org.openrewrite:plugin:6.44.0";
        String recipeCoordinate = "org.openrewrite.recipe:rewrite-spring:6.8.0";
        String script = """
                initscript {
                    repositories {
                        mavenLocal()
                        mavenCentral()
                        gradlePluginPortal()
                    }
                    dependencies {
                        classpath "%s"
                    }
                }
                allprojects {
                    repositories {
                        mavenLocal()
                        mavenCentral()
                    }
                    afterEvaluate { p ->
                        if (p == rootProject || p.plugins.hasPlugin("java") || p.plugins.hasPlugin("java-base")) {
                            if (!p.plugins.hasPlugin("org.openrewrite.rewrite") && !p.plugins.hasPlugin(org.openrewrite.gradle.RewritePlugin)) {
                                p.apply plugin: org.openrewrite.gradle.RewritePlugin
                            }
                            p.dependencies {
                                add("rewrite", "%s")
                                add("rewrite", "%s")
                            }
                            p.rewrite {
                                configFile = rootProject.file("%s")
                                activeRecipe(System.getProperty("rewrite.activeRecipe"))
                                setExportDatatables(true)
                            }
                        }
                    }
                }
                """.formatted(
                        pluginCoordinate,
                        recipeCoordinate,
                        ELMOS_RECIPE_COORDINATE,
                        root.relativize(recipeConfig).toString().replace('\\', '/'));
        try {
            Files.deleteIfExists(initScript);
        } catch (IOException ignored) {}
        write(initScript, script.getBytes(StandardCharsets.UTF_8));
        return initScript;
    }

    private CommandOutcome runBuildOutcome(Path root, Path javaHome, Path toolHome, Control control,
                                           List<String> goals, Duration timeout, String buildTool) {
        if (SpringRouteCatalog.GRADLE_BUILD_TOOL.equals(buildTool))
            return runGradleOutcome(root, javaHome, toolHome, control, goals, timeout);
        return runMavenOutcome(root, javaHome, toolHome, control, goals, timeout);
    }

    private void requireGradleVersion(Path javaHome, Path gradleHome) {
        Process process = null;
        try {
            ProcessBuilder builder = new ProcessBuilder(gradleExecutable, "--version")
                    .redirectErrorStream(true);
            builder.environment().put("JAVA_HOME", javaHome.toString());
            builder.environment().put("GRADLE_USER_HOME", confined(gradleHome).toString());
            process = builder.start();
            String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            if (!process.waitFor(15, TimeUnit.SECONDS) || process.exitValue() != 0
                    || !output.lines().anyMatch(line -> line.trim().equals("Gradle 8.14.3"))) {
                throw blocked("GRADLE_VERSION_UNSUPPORTED",
                        "The approved Gradle executable must report exactly 8.14.3.");
            }
        } catch (BlockedException error) {
            throw error;
        } catch (IOException error) {
            throw blocked("GRADLE_TOOLCHAIN_UNAVAILABLE",
                    "The approved Gradle executable could not be started.");
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw blocked("RUN_CANCELLED", "The Gradle toolchain check was interrupted.");
        } finally {
            if (process != null && process.isAlive()) process.destroyForcibly();
        }
    }

    private void runBuild(Path root, Path javaHome, Path toolHome, Control control,
                          List<String> goals, Duration timeout, String buildTool) {
        CommandOutcome outcome = runBuildOutcome(root, javaHome, toolHome, control, goals, timeout, buildTool);
        if (outcome.exitCode() != 0) {
            throw blocked(SpringRouteCatalog.GRADLE_BUILD_TOOL.equals(buildTool)
                            ? "GRADLE_COMMAND_FAILED" : "MAVEN_COMMAND_FAILED",
                    "A required build command failed; inspect the redacted run log.");
        }
    }

    private static Path installExactRecipe(Path root, SpringRouteCatalog.SpringRoute route) {
        String resource = route.recipeResource();
        byte[] expected;
        try (var input = LocalSpringUpgradeExecutionPort.class.getResourceAsStream(resource)) {
            if (input == null) throw new IOException("exact recipe resource is missing");
            expected = input.readAllBytes();
        } catch (IOException error) {
            throw blocked("EXACT_RECIPE_UNAVAILABLE",
                    "The immutable exact-version OpenRewrite recipe is unavailable.");
        }
        Path target = root.resolve(".elmos/openrewrite.yml");
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
            try {
                if (!MessageDigest.isEqual(expected, Files.readAllBytes(target))) {
                    throw blocked("EXACT_RECIPE_DIGEST_MISMATCH",
                            "The installed exact-version OpenRewrite recipe changed during execution.");
                }
            } catch (IOException error) {
                throw blocked("EXACT_RECIPE_UNAVAILABLE",
                        "The immutable exact-version OpenRewrite recipe could not be verified.");
            }
        } else {
            write(target, expected);
        }
        return target;
    }

    private CommandOutcome runMavenOutcome(Path root, Path javaHome, Path mavenHome, Control control,
                                           List<String> goals, Duration timeout) {
        checkCancelled(control);
        Path confinedHome = confined(mavenHome);
        createDirectory(confinedHome);
        Path repository = confinedHome.resolve(".m2/repository");
        createDirectory(repository);
        List<String> argv = new ArrayList<>();
        argv.add(mavenExecutable);
        argv.add("-B");
        argv.add("--no-transfer-progress");
        if (mavenOffline) argv.add("--offline");
        argv.addAll(goals);
        ProcessBuilder builder = new ProcessBuilder(argv).directory(root.toFile()).redirectErrorStream(true);
        Map<String, String> inherited = Map.copyOf(builder.environment());
        builder.environment().clear();
        builder.environment().put("JAVA_HOME", javaHome.toString());
        builder.environment().put("HOME", confinedHome.toString());
        builder.environment().put("LANG", "C.UTF-8");
        builder.environment().put("LC_ALL", "C.UTF-8");
        builder.environment().put("MAVEN_OPTS",
                mavenOptions(inherited, confinedHome, repository));
        Process process = null;
        Thread output = null;
        try {
            process = builder.start();
            control.process(process);
            Process observedProcess = process;
            output = Thread.ofVirtual().start(() -> {
                try (var reader = observedProcess.inputReader(StandardCharsets.UTF_8)) {
                    reader.lines().forEach(control::log);
                } catch (IOException error) {
                    control.log("command output collection failed");
                }
            });
            boolean completed = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!completed) {
                process.destroyForcibly();
                output.join(Duration.ofSeconds(5));
                throw blocked("RUNNER_COMMAND_TIMEOUT", "The bounded Maven command exceeded its execution budget.");
            }
            output.join(Duration.ofSeconds(5));
            return new CommandOutcome(process.exitValue());
        } catch (BlockedException error) {
            throw error;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw blocked("RUN_CANCELLED", "The migration command was interrupted.");
        } catch (IOException error) {
            throw blocked("RUNNER_COMMAND_UNAVAILABLE", "The approved Maven toolchain could not be started.");
        } finally {
            if (process != null && process.isAlive()) process.destroyForcibly();
            if (output != null && output.isAlive()) {
                try {
                    output.join(Duration.ofSeconds(5));
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                }
            }
        }
    }

    private CommandOutcome runGradleOutcome(Path root, Path javaHome, Path gradleHome, Control control,
                                            List<String> goals, Duration timeout) {
        checkCancelled(control);
        Path confinedHome = confined(gradleHome);
        createDirectory(confinedHome);
        List<String> argv = new ArrayList<>();
        argv.add(gradleExecutable);
        argv.add("--no-daemon");
        argv.add("--console=plain");
        argv.add("--gradle-user-home");
        argv.add(confinedHome.toString());
        if (mavenOffline) argv.add("--offline");
        argv.addAll(goals);
        ProcessBuilder builder = new ProcessBuilder(argv).directory(root.toFile()).redirectErrorStream(true);
        Map<String, String> inherited = Map.copyOf(builder.environment());
        builder.environment().clear();
        builder.environment().put("JAVA_HOME", javaHome.toString());
        builder.environment().put("GRADLE_USER_HOME", confinedHome.toString());
        builder.environment().put("HOME", confinedHome.toString());
        builder.environment().put("LANG", "C.UTF-8");
        builder.environment().put("LC_ALL", "C.UTF-8");
        builder.environment().put("GRADLE_OPTS", gradleOptions(inherited, confinedHome));
        Process process = null;
        Thread output = null;
        try {
            process = builder.start();
            control.process(process);
            Process observedProcess = process;
            output = Thread.ofVirtual().start(() -> {
                try (var reader = observedProcess.inputReader(StandardCharsets.UTF_8)) {
                    reader.lines().forEach(control::log);
                } catch (IOException error) {
                    control.log("command output collection failed");
                }
            });
            boolean completed = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!completed) {
                process.destroyForcibly();
                output.join(Duration.ofSeconds(5));
                throw blocked("GRADLE_COMMAND_TIMEOUT", "The bounded Gradle command exceeded its execution budget.");
            }
            output.join(Duration.ofSeconds(5));
            return new CommandOutcome(process.exitValue());
        } catch (BlockedException error) {
            throw error;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw blocked("RUN_CANCELLED", "The migration command was interrupted.");
        } catch (IOException error) {
            throw blocked("GRADLE_TOOLCHAIN_UNAVAILABLE", "The approved Gradle toolchain could not be started.");
        } finally {
            if (process != null && process.isAlive()) process.destroyForcibly();
            if (output != null && output.isAlive()) {
                try {
                    output.join(Duration.ofSeconds(5));
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                }
            }
        }
    }

    private void runGradle(Path root, Path javaHome, Path gradleHome, Control control,
                           List<String> goals, Duration timeout) {
        CommandOutcome outcome = runGradleOutcome(root, javaHome, gradleHome, control, goals, timeout);
        if (outcome.exitCode() != 0)
            throw blocked("GRADLE_COMMAND_FAILED", "A required Gradle/OpenRewrite command failed; inspect the redacted run log.");
    }

    private static String gradleOptions(Map<String, String> environment, Path home) {
        String base = "-Djava.awt.headless=true -Duser.timezone=UTC -Duser.home=" + home;
        String proxyValue = firstNonBlank(environment.get("HTTPS_PROXY"), environment.get("https_proxy"));
        if (proxyValue == null) return base;
        try {
            URI proxy = URI.create(proxyValue);
            String host = proxy.getHost();
            int port = proxy.getPort() < 0 ? 80 : proxy.getPort();
            if (!"http".equalsIgnoreCase(proxy.getScheme())
                    || host == null || !host.matches("[A-Za-z0-9.-]{1,253}")
                    || port < 1 || port > 65535 || proxy.getUserInfo() != null
                    || proxy.getQuery() != null || proxy.getFragment() != null
                    || !(proxy.getPath() == null || proxy.getPath().isEmpty() || "/".equals(proxy.getPath()))) {
                throw new IllegalArgumentException("invalid proxy");
            }
            return base + " -Dhttps.proxyHost=" + host + " -Dhttps.proxyPort=" + port
                    + " -Dhttp.proxyHost=" + host + " -Dhttp.proxyPort=" + port
                    + " -Dhttp.nonProxyHosts=localhost|127.*|[::1]"
                    + " -Dhttps.nonProxyHosts=localhost|127.*|[::1]";
        } catch (IllegalArgumentException error) {
            throw blocked("EGRESS_PROXY_CONFIGURATION_INVALID", "Approved Gradle egress proxy configuration is invalid.");
        }
    }

    private static String mavenOptions(
            Map<String, String> environment,
            Path home,
            Path repository
    ) {
        String base = "-Djava.awt.headless=true -Duser.timezone=UTC"
                + " -Duser.home=" + home
                + " -Dmaven.repo.local=" + repository;
        String proxyValue = firstNonBlank(
                environment.get("HTTPS_PROXY"),
                environment.get("https_proxy")
        );
        if (proxyValue == null) return base;
        try {
            URI proxy = URI.create(proxyValue);
            String host = proxy.getHost();
            int port = proxy.getPort() < 0 ? 80 : proxy.getPort();
            if (!"http".equalsIgnoreCase(proxy.getScheme())
                    || host == null
                    || !host.matches("[A-Za-z0-9.-]{1,253}")
                    || port < 1
                    || port > 65535
                    || proxy.getUserInfo() != null
                    || proxy.getQuery() != null
                    || proxy.getFragment() != null
                    || !(proxy.getPath() == null || proxy.getPath().isEmpty()
                    || "/".equals(proxy.getPath()))) {
                throw new IllegalArgumentException("invalid proxy");
            }
            return base
                    + " -Dhttps.proxyHost=" + host
                    + " -Dhttps.proxyPort=" + port
                    + " -Dhttp.proxyHost=" + host
                    + " -Dhttp.proxyPort=" + port
                    + " -Dhttp.nonProxyHosts=localhost|127.*|[::1]"
                    + " -Dhttps.nonProxyHosts=localhost|127.*|[::1]";
        } catch (IllegalArgumentException error) {
            throw blocked("EGRESS_PROXY_CONFIGURATION_INVALID",
                    "Approved Maven egress proxy configuration is invalid.");
        }
    }

    private static String firstNonBlank(String first, String second) {
        if (first != null && !first.isBlank()) return first;
        if (second != null && !second.isBlank()) return second;
        return null;
    }

    private static Path normalizeDependencySeed(
            Path raw,
            Path workspaceRoot,
            boolean required
    ) {
        if (raw == null) {
            if (required) {
                throw new IllegalStateException(
                        "offline Maven execution requires a pre-approved dependency seed repository");
            }
            return null;
        }
        Path value = raw.toAbsolutePath().normalize();
        if (value.startsWith(workspaceRoot)
                || !Files.isDirectory(value, LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(value)) {
            throw new IllegalStateException(
                    "Maven dependency seed must be a real directory outside the writable workspace");
        }
        return value;
    }

    private void runMaven(
            Path root,
            Path javaHome,
            Path mavenHome,
            Control control,
            List<String> goals,
            Duration timeout
    ) {
        CommandOutcome outcome = runMavenOutcome(
                root, javaHome, mavenHome, control, goals, timeout);
        if (outcome.exitCode() != 0)
            throw blocked("MAVEN_COMMAND_FAILED", "A required Maven/OpenRewrite command failed; inspect the redacted run log.");
    }

    /**
     * Best-effort evidence attachment only, called once the bounded
     * {@code Stage.DETERMINISTIC_REPAIR} cycle has already failed a second time.
     * This never changes the failure code or message the caller sees: the caller
     * always throws the identical {@code MAVEN_COMMAND_FAILED} immediately after
     * calling this method, whether or not it writes anything. The actual decision
     * logic lives in the pure, unit-testable {@link #codingAgentEvidencePayload}
     * below; this method only adds the file I/O.
     */
    private void recordCodingAgentCandidates(Path runRoot, String organizationId, String runId) {
        codingAgentEvidencePayload(codingAgentPort, organizationId, runId)
                .ifPresent(payload -> writeJson(runRoot.resolve("evidence/coding-agent-candidates.json"), payload));
    }

    /**
     * Pure decision logic with no file I/O and no dependency on this class's
     * constructor (which requires a real, exact-version JAVA_HOME and Maven
     * executable on disk and therefore cannot be constructed in an ordinary unit
     * test). Kept package-visible specifically so
     * {@code LocalSpringUpgradeExecutionPortCodingAgentEvidenceTest} can exercise
     * every branch without that environment.
     *
     * <p>When {@code port} is the default {@link DisabledSpringUpgradeCodingAgentPort}
     * (today's only wired configuration; see {@code SpringUpgradeConfiguration}'s
     * {@code elmos.worker.spring-upgrade.coding-agent-enabled} flag, default
     * {@code false}), {@link SpringUpgradeCodingAgentPort#configured()} is false
     * and this returns {@link Optional#empty()}, so this change has zero effect on
     * the one pipeline with real {@code PASSED_LOCAL} end-to-end execution evidence.
     *
     * <p>When a real port is enabled, this records which {@code LONG_TAIL_CODE_FIX}
     * candidate models were actually provisionable (real credential present, real
     * health probe passed) at the moment of failure. It is deliberately just
     * evidence, not an applied fix: no capability exists anywhere in this codebase
     * today that has a model generate a patch and apply it, so claiming otherwise
     * here would fabricate a capability instead of describing one. See ADR-0059.
     */
    static Optional<Map<String, Object>> codingAgentEvidencePayload(
            SpringUpgradeCodingAgentPort port, String organizationId, String runId) {
        if (!port.configured()) return Optional.empty();
        List<SpringUpgradeCodingAgentPort.CandidateModel> candidates;
        try {
            candidates = port.provisionCandidates(organizationId, runId);
        } catch (RuntimeException error) {
            return Optional.of(Map.of(
                    "schema_version", "1.0",
                    "status", "PROVISIONING_FAILED",
                    "error", error.getClass().getSimpleName()
            ));
        }
        List<Map<String, Object>> rendered = new ArrayList<>();
        for (SpringUpgradeCodingAgentPort.CandidateModel candidate : candidates) {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("model_id", candidate.modelId());
            entry.put("approved", candidate.approved());
            entry.put("reason_codes", candidate.reasonCodes());
            rendered.add(entry);
        }
        return Optional.of(Map.of(
                "schema_version", "1.0",
                "status", "CANDIDATES_PROVISIONED",
                "note", "These are provisionable LONG_TAIL_CODE_FIX candidate models at failure time, "
                        + "not an applied fix; no automatic patch-generation capability exists yet.",
                "candidates", rendered
        ));
    }

    private Map<String,Object> fcm(SourceIdentity identity, String snapshotDigest, Fingerprint fingerprint,
                                   SpringRouteCatalog.SpringRoute route,
                                   SpringRouteCatalog.Selection selection) {
        Map<String,Object> model = new LinkedHashMap<>();
        model.put("schema_version", "1.0");
        model.put("pack_key", route.packKey());
        model.put("route_id", route.routeId());
        model.put("route_evidence", selection.evidence().name());
        model.put("source_commit", identity.commitSha());
        model.put("source_snapshot_sha256", snapshotDigest);
        model.put("extraction_status", "STATIC_AND_SOURCE_BASELINE");
        model.put("source_framework", Map.of(
                "family", fingerprint.sourceFrameworkFamily(),
                "version", fingerprint.sourceFrameworkVersion()));
        String detectedSourceVersion = SpringRouteCatalog.SourceFamily.SPRING_BOOT.contractValue()
                .equals(fingerprint.sourceFrameworkFamily())
                ? fingerprint.springBootVersion() : fingerprint.sourceFrameworkVersion();
        model.put("exact_tuple", route.tuple(
                detectedSourceVersion, SpringRouteCatalog.normalizeJava(fingerprint.javaVersion())));
        model.put("capabilities", SpringCapabilityFingerprint.fcmCapabilities(fingerprint));
        model.put("language_features", SpringFeatureCatalog.render(
                fingerprint.features(), route.targetBoot(), route.targetJava()));
        model.put("unknowns", fingerprint.unknowns());
        model.put("ordering_and_defaults", Map.of(
                "security_filter_order", "preserve-and-verify",
                "configuration_precedence", "preserve-and-verify",
                "transaction_defaults", "preserve-and-verify"));
        return model;
    }

    private String waitForHealth(Process process, int port, List<String> candidates, Control control) {
        HttpClient client = LOOPBACK_PROBE_CLIENT;
        Instant deadline = Instant.now().plusSeconds(60);
        while (Instant.now().isBefore(deadline)) {
            checkCancelled(control);
            if (!process.isAlive()) throw blocked("APPLICATION_EXITED_BEFORE_HEALTHY", "The application exited before becoming healthy.");
            for (String path : candidates) {
                try {
                    var response = client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
                                    .timeout(Duration.ofSeconds(2))
                                    .header("Accept", "application/json")
                                    .GET().build(),
                            HttpResponse.BodyHandlers.ofInputStream());
                    try (InputStream body = response.body()) {
                        byte[] bytes = body.readNBytes(MAX_HEALTH_RESPONSE_BYTES + 1);
                        if (bytes.length <= MAX_HEALTH_RESPONSE_BYTES
                                && strictHealthUp(response.statusCode(), bytes, json)) {
                            return path;
                        }
                    }
                } catch (IOException ignored) {
                    // Retry until the bounded deadline.
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw blocked("HEALTH_CHECK_INTERRUPTED", "Application health checking was interrupted.");
                }
            }
            try { Thread.sleep(500); }
            catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw blocked("HEALTH_CHECK_INTERRUPTED", "Application health checking was interrupted.");
            }
        }
        process.destroyForcibly();
        throw blocked("APPLICATION_HEALTH_TIMEOUT", "The application did not become healthy within 60 seconds.");
    }

    static boolean strictHealthUp(int statusCode, byte[] body, ObjectMapper json) {
        if (statusCode < 200 || statusCode >= 300 || body == null
                || body.length == 0 || body.length > MAX_HEALTH_RESPONSE_BYTES) {
            return false;
        }
        try {
            JsonNode document = json.readTree(body);
            return document != null && document.isObject()
                    && "UP".equals(document.path("status").asText());
        } catch (IOException | RuntimeException ignored) {
            return false;
        }
    }

    static void bindLoopbackEnvironment(ProcessBuilder builder, int port) {
        Objects.requireNonNull(builder, "builder");
        if (port < 1 || port > 65_535) {
            throw new IllegalArgumentException("runtime port must be between 1 and 65535");
        }
        builder.environment().put("SERVER_ADDRESS", "127.0.0.1");
        builder.environment().put("SERVER_PORT", Integer.toString(port));
        builder.environment().put("MANAGEMENT_SERVER_ADDRESS", "127.0.0.1");
        builder.environment().put("MANAGEMENT_SERVER_PORT", Integer.toString(port));
    }

    private HttpProbe waitForStartup(
            Process process,
            int port,
            List<String> candidates,
            Control control
    ) {
        HttpClient client = LOOPBACK_PROBE_CLIENT;
        Instant deadline = Instant.now().plusSeconds(60);
        while (Instant.now().isBefore(deadline)) {
            checkCancelled(control);
            if (!process.isAlive()) {
                throw blocked("APPLICATION_EXITED_BEFORE_STARTUP",
                        "The source application exited before reaching its HTTP boundary.");
            }
            for (String path : candidates) {
                try {
                    var response = client.send(
                            HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
                                    .timeout(Duration.ofSeconds(2))
                                    .GET()
                                    .build(),
                            HttpResponse.BodyHandlers.discarding()
                    );
                    if (isStartupStatus(response.statusCode())) {
                        return new HttpProbe(path, response.statusCode());
                    }
                } catch (IOException ignored) {
                    // Retry until the bounded deadline.
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw blocked("STARTUP_CHECK_INTERRUPTED",
                            "Source application startup checking was interrupted.");
                }
            }
            try {
                Thread.sleep(500);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw blocked("STARTUP_CHECK_INTERRUPTED",
                        "Source application startup checking was interrupted.");
            }
        }
        process.destroyForcibly();
        throw blocked("APPLICATION_STARTUP_TIMEOUT",
                "The source application did not reach its HTTP boundary within 60 seconds.");
    }

    static boolean isStartupStatus(int statusCode) {
        return statusCode >= 200 && statusCode < 500;
    }

    private record HttpProbe(String path, int statusCode) {}

    private static void capability(String model, Path root, String modelName,
                                   Map<String,List<String>> traces, List<String> capabilities,
                                   String id, String... needles) {
        List<String> found = new ArrayList<>();
        for (String needle : needles) {
            if (model.contains(needle)) found.add(modelName + ":" + needle);
            for (Path file : findFiles(root, ".java", ".yml", ".yaml", ".properties")) {
                if (read(file).contains(needle)) found.add(root.relativize(file).toString() + ":" + needle);
            }
        }
        if (!found.isEmpty()) {
            capabilities.add(id);
            traces.put(id, found.stream().distinct().sorted().limit(100).toList());
        }
    }

    private static Document parsePom(Path pom) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            return factory.newDocumentBuilder().parse(pom.toFile());
        } catch (Exception error) {
            throw blocked("POM_PARSE_FAILED", "The Maven project model could not be parsed safely.");
        }
    }

    private static TestSummary testSummary(Path root) {
        List<Path> reports;
        try (var stream = Files.walk(root)) {
            reports = stream
                    .filter(path -> Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
                    .filter(path -> path.getParent() != null
                            && (path.getParent().getFileName().toString().equals("surefire-reports")
                            || path.getParent().getFileName().toString().equals("test")))
                    .filter(path -> path.getFileName().toString().startsWith("TEST-")
                            && path.getFileName().toString().endsWith(".xml"))
                    .sorted()
                    .toList();
        } catch (IOException error) {
            throw blocked("TEST_EVIDENCE_UNAVAILABLE",
                    "Maven test reports could not be enumerated.");
        }
        long tests = 0;
        long failures = 0;
        long errors = 0;
        long skipped = 0;
        Set<String> identities = new TreeSet<>();
        for (Path report : reports) {
            Document document = parseXml(report, "TEST_REPORT_INVALID",
                    "Build test report is invalid.");
            Element suite = document.getDocumentElement();
            tests = Math.addExact(tests, longAttribute(suite, "tests"));
            failures = Math.addExact(failures, longAttribute(suite, "failures"));
            errors = Math.addExact(errors, longAttribute(suite, "errors"));
            skipped = Math.addExact(skipped, longAttribute(suite, "skipped"));
            NodeList cases = suite.getElementsByTagName("testcase");
            for (int index = 0; index < cases.getLength(); index++) {
                if (cases.item(index) instanceof Element test) {
                    String className = test.getAttribute("classname").trim();
                    String name = test.getAttribute("name").trim();
                    if (!className.isBlank() && !name.isBlank()) {
                        identities.add(className + "#" + name);
                    }
                }
            }
        }
        return new TestSummary(
                reports.stream().map(root::relativize).map(Path::toString).toList(),
                tests,
                failures,
                errors,
                skipped,
                tests - failures - errors - skipped,
                List.copyOf(identities)
        );
    }

    private static void requireSourceTests(TestSummary summary) {
        if (summary.tests() <= 0 || summary.testIdentities().isEmpty()) {
            throw blocked("SOURCE_TEST_CORPUS_EMPTY",
                    "The exact migration route requires at least one executable source test; add characterization tests first.");
        }
        if (summary.failures() != 0 || summary.errors() != 0) {
            throw blocked("SOURCE_TEST_BASELINE_FAILED",
                    "Source test baseline is not green.");
        }
    }

    private static void requireTestParity(TestSummary source, TestSummary target) {
        if (target.failures() != 0 || target.errors() != 0) {
            throw blocked("TARGET_TESTS_FAILED",
                    "Target tests are not green.");
        }
        if (target.tests() < source.tests()
                || target.executed() < source.executed()
                || target.skipped() > source.skipped()
                || !new HashSet<>(target.testIdentities()).containsAll(source.testIdentities())) {
            throw blocked("TEST_CORPUS_WEAKENED",
                    "Target test execution dropped, skipped, or renamed source test identities.");
        }
    }

    static Map<String, List<String>> requiredComplexCapabilityInvariants() {
        return REQUIRED_COMPLEX_CAPABILITY_INVARIANTS;
    }

    /**
     * Fail-closed local engineering gate for security, data, transaction and
     * messaging behavior. The manifest is only a project-owned declaration
     * binding executed test identities to invariants; it is not independent or
     * certification evidence.
     */
    static ComplexCapabilityDecision evaluateComplexCapabilities(
            Path sourceRoot,
            Path targetRoot,
            Fingerprint fingerprint,
            CapabilityTestRun sourceRun,
            CapabilityTestRun targetRun,
            ObjectMapper json
    ) {
        Objects.requireNonNull(sourceRoot, "sourceRoot");
        Objects.requireNonNull(targetRoot, "targetRoot");
        Objects.requireNonNull(fingerprint, "fingerprint");
        Objects.requireNonNull(sourceRun, "sourceRun");
        Objects.requireNonNull(targetRun, "targetRun");
        Objects.requireNonNull(json, "json");

        List<Map<String, Object>> criticalCapabilities = new ArrayList<>();
        Set<String> requiredDomains = new TreeSet<>();
        Set<String> unresolvedConditionalCapabilities = new TreeSet<>();
        Set<String> seen = new HashSet<>();
        for (Map<String, Object> capability : SpringCapabilityFingerprint.fcmCapabilities(fingerprint)) {
            String id = Objects.toString(capability.get("id"), "");
            String state = Objects.toString(capability.get("status"), "unknown");
            String domain = complexCapabilityDomain(id);
            if (domain == null || !COMPLEX_CAPABILITY_STATES.contains(state)) continue;
            if (!seen.add(id + "|" + state)) continue;
            requiredDomains.add(domain);
            Map<String, Object> rendered = new LinkedHashMap<>();
            rendered.put("id", id);
            rendered.put("domain", domain);
            rendered.put("status", state);
            rendered.put("source_trace_count",
                    fingerprint.sourceTraces().getOrDefault(id, List.of()).size());
            criticalCapabilities.add(rendered);
            if ("conditional".equals(state)) unresolvedConditionalCapabilities.add(id);
        }

        Map<String, Set<String>> requiredInvariants = new TreeMap<>();
        for (String domain : requiredDomains) {
            requiredInvariants.put(domain,
                    new TreeSet<>(REQUIRED_COMPLEX_CAPABILITY_INVARIANTS.get(domain)));
        }
        for (String unknown : fingerprint.unknowns()) {
            String unresolvedState = unresolvedCapabilityState(unknown);
            if (unresolvedState != null) {
                String id = unknown.substring(unknown.indexOf(':') + 1);
                String domain = complexCapabilityDomain(id);
                if (domain != null) {
                    requiredDomains.add(domain);
                    requiredInvariants.computeIfAbsent(domain,
                            ignored -> new TreeSet<>(
                                    REQUIRED_COMPLEX_CAPABILITY_INVARIANTS.get(domain)));
                    if ("conditional".equals(unresolvedState)) {
                        unresolvedConditionalCapabilities.add(id);
                    }
                    if (seen.add(id + "|" + unresolvedState)) {
                        criticalCapabilities.add(Map.of(
                                "id", id,
                                "domain", domain,
                                "status", unresolvedState,
                                "source_trace_count", 0));
                    }
                }
                continue;
            }
            String domain = customOrDynamicDomain(unknown);
            if (domain == null) continue;
            requiredDomains.add(domain);
            requiredInvariants.computeIfAbsent(domain,
                    ignored -> new TreeSet<>(REQUIRED_COMPLEX_CAPABILITY_INVARIANTS.get(domain)));
            String extraInvariant = customOrDynamicInvariant(unknown);
            if (extraInvariant != null) requiredInvariants.get(domain).add(extraInvariant);
            if (seen.add("unknown|" + unknown)) {
                criticalCapabilities.add(Map.of(
                        "id", unknown,
                        "domain", domain,
                        "status", "custom-or-dynamic",
                        "source_trace_count", 0));
            }
        }
        criticalCapabilities.sort(Comparator.comparing(entry -> entry.get("id").toString()));

        Set<String> sourceIdentities = normalizedTestIdentities(sourceRun.testIdentities());
        Set<String> targetIdentities = normalizedTestIdentities(targetRun.testIdentities());
        boolean exactIdentityMatch = sourceIdentities.equals(targetIdentities)
                && sourceIdentities.size() == sourceRun.testIdentities().size()
                && targetIdentities.size() == targetRun.testIdentities().size();
        Map<String, Object> testIdentityReport = new LinkedHashMap<>();
        testIdentityReport.put("source_count", sourceIdentities.size());
        testIdentityReport.put("target_count", targetIdentities.size());
        testIdentityReport.put("source_sha256", digestStrings(sourceIdentities));
        testIdentityReport.put("target_sha256", digestStrings(targetIdentities));
        testIdentityReport.put("exact_match", exactIdentityMatch);
        testIdentityReport.put("source_skipped", sourceRun.skipped());
        testIdentityReport.put("target_skipped", targetRun.skipped());

        Map<String, Object> report = baseComplexCapabilityReport();
        report.put("critical_capabilities", List.copyOf(criticalCapabilities));
        report.put("required_domains", requiredDomains.stream().toList());
        report.put("required_invariants", immutableInvariantMap(requiredInvariants));
        report.put("test_identity", testIdentityReport);
        report.put("conditional_activation", Map.of(
                "status", unresolvedConditionalCapabilities.isEmpty()
                        ? "NO_UNRESOLVED_CONDITIONS_OBSERVED" : "UNRESOLVED",
                "unresolved_capabilities", unresolvedConditionalCapabilities.stream().toList()));

        if (requiredDomains.isEmpty()) {
            report.put("status", "NOT_APPLICABLE");
            report.put("manifest", Map.of(
                    "path", CAPABILITY_TEST_MANIFEST.toString(),
                    "status", "NOT_REQUIRED"));
            report.put("blockers", List.of());
            return new ComplexCapabilityDecision(report, List.of());
        }

        List<String> blockers = new ArrayList<>();
        for (String capability : unresolvedConditionalCapabilities) {
            blockers.add("CONDITIONAL_ACTIVATION_UNRESOLVED:" + capability);
        }
        if (sourceIdentities.isEmpty()) blockers.add("SOURCE_COMPLEX_CAPABILITY_TEST_IDENTITIES_EMPTY");
        if (!exactIdentityMatch) blockers.add("SOURCE_TARGET_TEST_IDENTITY_MISMATCH");
        if (sourceRun.skipped() != 0 || targetRun.skipped() != 0) {
            blockers.add("COMPLEX_CAPABILITY_TESTS_SKIPPED");
        }

        ManifestInspection manifest = inspectCapabilityManifest(
                sourceRoot, targetRoot, requiredInvariants, sourceIdentities, json, blockers);
        report.put("manifest", manifest.report());
        List<String> distinctBlockers = blockers.stream().distinct().sorted().toList();
        report.put("status", distinctBlockers.isEmpty() ? "PASS_LOCAL_ENGINEERING" : "BLOCKED");
        report.put("blockers", distinctBlockers);
        return new ComplexCapabilityDecision(report, distinctBlockers);
    }

    private static Map<String, Object> baseComplexCapabilityReport() {
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("schema_version", "1.0");
        report.put("kind", "elmos.spring-complex-capability-verification");
        report.put("scope", "LOCAL_ENGINEERING_ONLY");
        report.put("certification_eligible", false);
        report.put("certification_status", "NOT_CERTIFIED");
        report.put("independent_verification", "NOT_RUN");
        report.put("customer_evidence", "NOT_RUN");
        report.put("production_evidence", "NOT_RUN");
        report.put("evidence_refs", List.of(
                "evidence/source-test-summary.json",
                "evidence/target-test-summary.json",
                "evidence/test-parity.json",
                CAPABILITY_TEST_MANIFEST.toString()));
        return report;
    }

    private static ManifestInspection inspectCapabilityManifest(
            Path sourceRoot,
            Path targetRoot,
            Map<String, Set<String>> requiredInvariants,
            Set<String> sourceTestIdentities,
            ObjectMapper json,
            List<String> blockers
    ) {
        Path sourceManifest = sourceRoot.resolve(CAPABILITY_TEST_MANIFEST).normalize();
        Path targetManifest = targetRoot.resolve(CAPABILITY_TEST_MANIFEST).normalize();
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("path", CAPABILITY_TEST_MANIFEST.toString());
        boolean sourcePresent = confinedRegularManifest(sourceRoot, sourceManifest);
        boolean targetPresent = confinedRegularManifest(targetRoot, targetManifest);
        report.put("source_present", sourcePresent);
        report.put("target_present", targetPresent);
        report.put("project_owned_source_path", sourcePresent);
        report.put("source_sha256", "NOT_AVAILABLE");
        report.put("target_sha256", "NOT_AVAILABLE");
        report.put("target_byte_identical", false);
        report.put("schema_valid", false);

        if (!sourcePresent) {
            blockers.add("CAPABILITY_TEST_MANIFEST_MISSING");
            report.put("status", "MISSING");
            return new ManifestInspection(report);
        }
        byte[] sourceBytes = boundedManifestBytes(sourceManifest, blockers, "SOURCE");
        if (sourceBytes == null) {
            report.put("status", "INVALID");
            return new ManifestInspection(report);
        }
        report.put("source_sha256", digestBytes(sourceBytes));
        if (!targetPresent) {
            blockers.add("TARGET_CAPABILITY_TEST_MANIFEST_MISSING");
        } else {
            byte[] targetBytes = boundedManifestBytes(targetManifest, blockers, "TARGET");
            if (targetBytes != null) {
                report.put("target_sha256", digestBytes(targetBytes));
                boolean identical = MessageDigest.isEqual(sourceBytes, targetBytes);
                report.put("target_byte_identical", identical);
                if (!identical) blockers.add("CAPABILITY_TEST_MANIFEST_CHANGED_BY_TRANSFORMATION");
            }
        }

        int blockersBeforeSchema = blockers.size();
        try {
            JsonNode root = json.readTree(sourceBytes);
            if (root == null || !root.isObject()) {
                blockers.add("CAPABILITY_TEST_MANIFEST_ROOT_INVALID");
            } else {
                if (!"1.0".equals(root.path("schema_version").asText())) {
                    blockers.add("CAPABILITY_TEST_MANIFEST_SCHEMA_VERSION_INVALID");
                }
                if (!"elmos.spring-capability-tests".equals(root.path("kind").asText())) {
                    blockers.add("CAPABILITY_TEST_MANIFEST_KIND_INVALID");
                }
                Set<String> manifestTestIdentities = strictManifestStrings(
                        root.get("test_identities"), "MANIFEST_TEST_IDENTITIES", blockers);
                if (!sourceTestIdentities.containsAll(manifestTestIdentities)) {
                    blockers.add("MANIFEST_TEST_IDENTITIES_NOT_IN_SOURCE_EXECUTION");
                }
                JsonNode domains = root.get("domains");
                if (domains == null || !domains.isObject()) {
                    blockers.add("CAPABILITY_TEST_MANIFEST_DOMAINS_INVALID");
                } else {
                    for (Map.Entry<String, Set<String>> required : requiredInvariants.entrySet()) {
                        JsonNode domain = domains.get(required.getKey());
                        if (domain == null || !domain.isObject()) {
                            blockers.add("CAPABILITY_TEST_DOMAIN_MISSING:" + required.getKey());
                            continue;
                        }
                        Set<String> invariants = strictManifestStrings(
                                domain.get("invariants"),
                                "MANIFEST_INVARIANTS:" + required.getKey(), blockers);
                        Set<String> missing = new TreeSet<>(required.getValue());
                        missing.removeAll(invariants);
                        if (!missing.isEmpty()) {
                            blockers.add("MANIFEST_INVARIANTS_MISSING:" + required.getKey()
                                    + ":" + String.join("+", missing));
                        }
                        Set<String> domainTests = strictManifestStrings(
                                domain.get("test_identities"),
                                "MANIFEST_DOMAIN_TEST_IDENTITIES:" + required.getKey(), blockers);
                        if (!manifestTestIdentities.containsAll(domainTests)) {
                            blockers.add("DOMAIN_TEST_IDENTITIES_NOT_IN_MANIFEST:" + required.getKey());
                        }
                        if (!sourceTestIdentities.containsAll(domainTests)) {
                            blockers.add("DOMAIN_TEST_IDENTITIES_NOT_EXECUTED:" + required.getKey());
                        }
                    }
                }
            }
        } catch (IOException | RuntimeException error) {
            blockers.add("CAPABILITY_TEST_MANIFEST_JSON_INVALID");
        }
        boolean schemaValid = blockers.size() == blockersBeforeSchema;
        report.put("schema_valid", schemaValid);
        report.put("status", schemaValid
                && Boolean.TRUE.equals(report.get("target_byte_identical")) ? "VALID" : "INVALID");
        return new ManifestInspection(report);
    }

    private static boolean confinedRegularManifest(Path root, Path candidate) {
        Path normalizedRoot = root.toAbsolutePath().normalize();
        Path normalizedCandidate = candidate.toAbsolutePath().normalize();
        if (!normalizedCandidate.startsWith(normalizedRoot)
                || normalizedCandidate.equals(normalizedRoot)) return false;
        Path current = normalizedRoot;
        for (Path segment : normalizedRoot.relativize(normalizedCandidate)) {
            current = current.resolve(segment);
            if (Files.isSymbolicLink(current)) return false;
        }
        return Files.isRegularFile(normalizedCandidate, LinkOption.NOFOLLOW_LINKS);
    }

    private static byte[] boundedManifestBytes(Path path, List<String> blockers, String role) {
        try {
            long size = Files.size(path);
            if (size <= 0 || size > MAX_CAPABILITY_MANIFEST_BYTES) {
                blockers.add(role + "_CAPABILITY_TEST_MANIFEST_SIZE_INVALID");
                return null;
            }
            return Files.readAllBytes(path);
        } catch (IOException error) {
            blockers.add(role + "_CAPABILITY_TEST_MANIFEST_READ_FAILED");
            return null;
        }
    }

    private static Set<String> strictManifestStrings(
            JsonNode node,
            String field,
            List<String> blockers
    ) {
        Set<String> values = new TreeSet<>();
        if (node == null || !node.isArray() || node.isEmpty()) {
            blockers.add(field + "_EMPTY_OR_INVALID");
            return values;
        }
        for (JsonNode entry : node) {
            if (!entry.isTextual()) {
                blockers.add(field + "_NON_STRING");
                continue;
            }
            String value = entry.asText().trim();
            if (value.isEmpty() || value.length() > 512 || value.contains("*") || value.contains("?")) {
                blockers.add(field + "_VALUE_INVALID");
                continue;
            }
            if (!values.add(value)) blockers.add(field + "_DUPLICATE");
        }
        return values;
    }

    private static Set<String> normalizedTestIdentities(List<String> identities) {
        Set<String> normalized = new TreeSet<>();
        for (String identity : identities) {
            if (identity != null && !identity.isBlank()) normalized.add(identity.trim());
        }
        return normalized;
    }

    private static Map<String, List<String>> immutableInvariantMap(
            Map<String, Set<String>> invariants
    ) {
        Map<String, List<String>> immutable = new TreeMap<>();
        invariants.forEach((domain, values) -> immutable.put(domain, values.stream().toList()));
        return Map.copyOf(immutable);
    }

    private static String complexCapabilityDomain(String id) {
        if (id.equals("security") || id.equals("authentication") || id.equals("authorization")) {
            return "security";
        }
        if (id.equals("persistence") || id.startsWith("persistence-")
                || id.startsWith("database-provider-")) {
            return "persistence_database";
        }
        if (id.equals("transactions")) return "transactions";
        if (id.equals("messaging") || id.startsWith("messaging-")) return "messaging";
        return null;
    }

    private static String unresolvedCapabilityState(String unknown) {
        if (unknown.startsWith("conditional-capability-activation-unresolved:")) {
            return "conditional";
        }
        if (unknown.startsWith("generated-capability-build-activation-unresolved:")) {
            return "generated";
        }
        if (unknown.startsWith("declared-only-capability-runtime-activation-unobserved:")) {
            return "declared-only";
        }
        if (unknown.startsWith("capability-semantics-unknown:")) return "unknown";
        return null;
    }

    private static String customOrDynamicDomain(String unknown) {
        if (unknown.startsWith("custom-authentication-provider")
                || unknown.startsWith("legacy-security-adapter")) return "security";
        if (unknown.startsWith("dynamic-datasource-routing")) return "persistence_database";
        if (unknown.startsWith("multi-resource-transaction")) return "transactions";
        String lower = unknown.toLowerCase(Locale.ROOT);
        if ((lower.contains("custom") || lower.contains("dynamic"))
                && lower.contains("messag")) return "messaging";
        return null;
    }

    private static String customOrDynamicInvariant(String unknown) {
        if (unknown.startsWith("custom-authentication-provider")) {
            return "custom-authentication-provider-contract";
        }
        if (unknown.startsWith("legacy-security-adapter")) {
            return "legacy-security-adapter-behavior";
        }
        if (unknown.startsWith("dynamic-datasource-routing")) {
            return "dynamic-datasource-routing-contract";
        }
        if (unknown.startsWith("multi-resource-transaction")) {
            return "multi-resource-atomicity-recovery-contract";
        }
        String lower = unknown.toLowerCase(Locale.ROOT);
        if ((lower.contains("custom") || lower.contains("dynamic"))
                && lower.contains("messag")) return "custom-listener-container-contract";
        return null;
    }

    private static String digestStrings(Set<String> values) {
        return digestBytes(String.join("\n", values).getBytes(StandardCharsets.UTF_8));
    }

    private static String digestBytes(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static long longAttribute(Element element, String name) {
        String value = element.getAttribute(name);
        if (value == null || value.isBlank()) return 0;
        try {
            long parsed = Long.parseLong(value);
            if (parsed < 0) throw new NumberFormatException("negative");
            return parsed;
        } catch (NumberFormatException error) {
            throw blocked("TEST_REPORT_INVALID", "Build test report counters are invalid.");
        }
    }

    private static Document parseXml(Path path, String code, String message) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            return factory.newDocumentBuilder().parse(path.toFile());
        } catch (Exception error) {
            throw blocked(code, message);
        }
    }

    private static String springBootVersion(Document document) {
        Element root = document.getDocumentElement();
        Element parent = direct(root, "parent");
        if (parent != null && "spring-boot-starter-parent".equals(text(parent, "artifactId")))
            return resolveProperty(document, text(parent, "version"));
        for (Element dependency : descendants(root, "dependency")) {
            if ("org.springframework.boot".equals(text(dependency, "groupId"))
                    && "spring-boot-dependencies".equals(text(dependency, "artifactId")))
                return resolveProperty(document, text(dependency, "version"));
        }
        return resolveProperty(document, property(document, "spring-boot.version"));
    }

    static String sourceFrameworkFamily(
            String springBootVersion,
            SpringCapabilityFingerprint.Analysis analysis
    ) {
        return sourceFrameworkFamily(springBootVersion, analysis, false);
    }

    static String sourceFrameworkFamily(
            String springBootVersion,
            SpringCapabilityFingerprint.Analysis analysis,
            boolean springFrameworkDeclared
    ) {
        if (!blank(springBootVersion)) return "spring-boot";
        if (analysis.sourceTraces().containsKey("spring-mvc")
                || analysis.sourceTraces().containsKey("spring-mvc-xml")
                || analysis.sourceTraces().containsKey("servlet-initializer")) {
            return "spring-mvc";
        }
        if (springFrameworkDeclared) return "spring-framework";
        return "unknown";
    }

    private static boolean isNonBootSpringFamily(String sourceFamily) {
        return SpringRouteCatalog.SourceFamily.SPRING_MVC.contractValue().equals(sourceFamily)
                || SpringRouteCatalog.SourceFamily.SPRING_FRAMEWORK.contractValue().equals(sourceFamily);
    }

    /**
     * Resolve a traditional Maven Spring Framework version only from an exact
     * project-owned authority: a conventional property, the Spring Framework
     * BOM, or an explicitly versioned Spring dependency. Inherited versions
     * that are not materialized in the inspected POM remain UNKNOWN.
     */
    static String springFrameworkVersion(Document document) {
        for (String propertyName : List.of(
                "spring-framework.version", "spring.version", "org.springframework.version")) {
            String candidate = resolveProperty(document, property(document, propertyName));
            if (!blank(candidate)) return candidate;
        }
        Element root = document.getDocumentElement();
        for (Element dependency : descendants(root, "dependency")) {
            String group = resolveProperty(document, text(dependency, "groupId"));
            String artifact = resolveProperty(document, text(dependency, "artifactId"));
            if (!"org.springframework".equals(group)) continue;
            if (!("spring-framework-bom".equals(artifact)
                    || "spring-webmvc".equals(artifact)
                    || "spring-web".equals(artifact)
                    || "spring-context".equals(artifact)
                    || "spring-core".equals(artifact))) continue;
            String candidate = resolveProperty(document, text(dependency, "version"));
            if (!blank(candidate)) return candidate;
        }
        return "";
    }

    /** Gradle equivalent of the exact, project-owned Spring version authority. */
    static String springFrameworkVersion(String model) {
        return firstMatch(model,
                "org\\.springframework:(?:spring-framework-bom|spring-webmvc|spring-web|spring-context|spring-core):([0-9][A-Za-z0-9._+\\-]*)",
                "(?:springFrameworkVersion|springVersion|spring_version)\\s*=\\s*['\"]([0-9][A-Za-z0-9._+\\-]*)",
                "(?:spring-framework\\.version|spring\\.version)\\s*[=:]\\s*['\"]?([0-9][A-Za-z0-9._+\\-]*)");
    }

    private static String property(Document document, String name) {
        Element properties = direct(document.getDocumentElement(), "properties");
        if (properties == null) return "";
        NodeList children = properties.getChildNodes();
        for (int i = 0; i < children.getLength(); i++) {
            Node child = children.item(i);
            if (child instanceof Element element && local(element).equals(name)) return element.getTextContent().trim();
        }
        return "";
    }

    private static String resolveProperty(Document document, String value) {
        if (value == null) return "";
        String trimmed = value.trim();
        Set<String> visited = new HashSet<>();
        while (trimmed.matches("\\$\\{[^}]+}")) {
            String propertyName = trimmed.substring(2, trimmed.length() - 1);
            if (!visited.add(propertyName)) return "";
            trimmed = property(document, propertyName).trim();
            if (trimmed.isEmpty() || visited.size() >= 8) return trimmed;
        }
        return trimmed;
    }

    private static List<String> children(Document document, String parentName, String childName) {
        Element parent = direct(document.getDocumentElement(), parentName);
        if (parent == null) return List.of();
        List<String> result = new ArrayList<>();
        for (Element child : directChildren(parent, childName)) result.add(child.getTextContent().trim());
        return result;
    }

    private static Element direct(Element parent, String name) {
        return directChildren(parent, name).stream().findFirst().orElse(null);
    }

    private static List<Element> directChildren(Element parent, String name) {
        List<Element> result = new ArrayList<>();
        NodeList nodes = parent.getChildNodes();
        for (int i = 0; i < nodes.getLength(); i++) {
            Node child = nodes.item(i);
            if (child instanceof Element element && local(element).equals(name)) result.add(element);
        }
        return result;
    }

    private static List<Element> descendants(Element root, String name) {
        List<Element> result = new ArrayList<>();
        NodeList nodes = root.getElementsByTagNameNS("*", name);
        for (int i = 0; i < nodes.getLength(); i++) if (nodes.item(i) instanceof Element element) result.add(element);
        return result;
    }

    private static String text(Element parent, String child) {
        Element value = direct(parent, child);
        return value == null ? "" : value.getTextContent().trim();
    }

    private static String local(Element element) {
        return element.getLocalName() == null ? element.getTagName() : element.getLocalName();
    }

    private URI validateRepositoryUri(String value) {
        try {
            URI uri = URI.create(value);
            if (uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null)
                throw blocked("GIT_URL_REJECTED", "Repository URLs cannot contain credentials, queries, or fragments.");
            if ("https".equalsIgnoreCase(uri.getScheme())) {
                if (uri.getHost() == null || !allowedGitHosts.contains(uri.getHost().toLowerCase(Locale.ROOT)))
                    throw blocked("GIT_HOST_NOT_ALLOWED", "Repository host is not in the approved exact host allowlist.");
                return uri;
            }
            if ("file".equalsIgnoreCase(uri.getScheme()) && allowFileRepositories) return uri;
            throw blocked("GIT_SCHEME_NOT_ALLOWED", "Only approved HTTPS or explicitly enabled controlled file repositories are supported.");
        } catch (RuntimeException error) {
            if (error instanceof BlockedException blocked) throw blocked;
            throw blocked("GIT_URL_REJECTED", "Repository URL is invalid.");
        }
    }

    private static String normalizeRef(String value) {
        if (value == null || value.isBlank() || value.length() > 256 || value.contains("..") || value.contains("@{")
                || value.startsWith("-") || !value.matches("(?:refs/(?:heads|tags)/)?[A-Za-z0-9._/-]+"))
            throw blocked("GIT_REF_REJECTED", "Git ref is outside the supported safe grammar.");
        return value.startsWith("refs/") ? value : "refs/heads/" + value;
    }

    private static String requireCommit(String value) {
        if (value == null || !value.matches("[0-9a-f]{40}"))
            throw blocked("IMMUTABLE_COMMIT_REQUIRED", "A full lowercase 40-character commit SHA is required.");
        return value;
    }

    private static Path normalizeRoot(Path root) {
        Path normalized = Objects.requireNonNull(root).toAbsolutePath().normalize();
        createDirectory(normalized);
        return normalized;
    }

    private Path confined(Path raw) {
        Path path = raw.toAbsolutePath().normalize();
        if (!path.startsWith(workspaceRoot) || path.equals(workspaceRoot))
            throw blocked("WORKSPACE_PATH_REJECTED", "Run paths must remain below the configured private workspace root.");
        return path;
    }

    private static Path requireJavaHome(Path home, int expectedMajor, String label) {
        Path normalized = Objects.requireNonNull(home).toAbsolutePath().normalize();
        Path java = normalized.resolve("bin/java");
        if (!Files.isExecutable(java)) throw new IllegalStateException(label + " JAVA_HOME is unavailable");
        try {
            Process process = new ProcessBuilder(java.toString(), "-version").redirectErrorStream(true).start();
            String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            if (!process.waitFor(10, TimeUnit.SECONDS) || process.exitValue() != 0
                    || !reportsJavaRelease(output, expectedMajor))
                throw new IllegalStateException(label + " JAVA_HOME does not provide Java " + expectedMajor);
            return normalized;
        } catch (IOException | InterruptedException error) {
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            throw new IllegalStateException(label + " JAVA_HOME could not be verified", error);
        }
    }

    /**
     * Match the release a JDK reports, across both version schemes.
     *
     * <p>Java 9 introduced the current numbering, so a Java 21 JDK prints
     * {@code version "21.0.11"}. Java 8 and earlier still print the legacy form
     * {@code version "1.8.0_432"}. A legacy estate needs those older JDKs to
     * build its source baseline, so accepting only the modern form would reject
     * a correctly provisioned Java 8 home.
     */
    static boolean reportsJavaRelease(String versionOutput, int expectedMajor) {
        if (versionOutput == null) return false;
        if (versionOutput.contains("version \"" + expectedMajor + ".")
                || versionOutput.contains("version \"" + expectedMajor + "\"")) {
            return true;
        }
        return expectedMajor <= 8
                && (versionOutput.contains("version \"1." + expectedMajor + ".")
                || versionOutput.contains("version \"1." + expectedMajor + "\""));
    }

    private static String requireMaven(String command, Path javaHome) {
        if (command == null || command.isBlank() || command.indexOf('\0') >= 0)
            throw new IllegalArgumentException("Maven executable is required");
        ProcessBuilder builder = new ProcessBuilder(command, "-version").redirectErrorStream(true);
        builder.environment().put("JAVA_HOME", javaHome.toString());
        try {
            Process process = builder.start();
            String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            if (!process.waitFor(15, TimeUnit.SECONDS) || process.exitValue() != 0
                    || !output.contains("Apache Maven 3.9.11")) {
                process.destroyForcibly();
                throw new IllegalStateException("approved Maven executable must be exactly 3.9.11");
            }
            return command;
        } catch (IOException | InterruptedException error) {
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            throw new IllegalStateException("approved Maven executable could not be verified", error);
        }
    }

    private static String requireExecutable(String command, String label) {
        if (command == null || command.isBlank() || command.indexOf('\0') >= 0)
            throw new IllegalArgumentException(label + " executable is required");
        return command;
    }

    private static List<Path> findFiles(Path root, String... suffixes) {
        try (var stream = Files.walk(root)) {
            Set<String> suffix = Set.of(suffixes);
            return stream.filter(path -> Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
                    .filter(path -> !containsExcludedSegment(path))
                    .filter(path -> suffix.stream().anyMatch(value -> path.getFileName().toString().endsWith(value)))
                    .limit(MAX_SOURCE_FILES + 1L).toList();
        } catch (IOException error) {
            throw blocked("SOURCE_SCAN_FAILED", "Source files could not be enumerated safely.");
        }
    }

    private static void copyTree(Path source, Path target) {
        deleteTree(target);
        final long[] bytes = {0};
        final int[] files = {0};
        try {
            Files.walkFileTree(source, EnumSet.noneOf(FileVisitOption.class), Integer.MAX_VALUE, new SimpleFileVisitor<>() {
                @Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) throws IOException {
                    Path relative = source.relativize(dir);
                    if (!relative.toString().isEmpty() && containsExcludedSegment(relative))
                        return FileVisitResult.SKIP_SUBTREE;
                    Files.createDirectories(target.resolve(relative));
                    return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                    Path relative = source.relativize(file);
                    if (containsExcludedSegment(relative)) return FileVisitResult.CONTINUE;
                    if (attrs.isSymbolicLink()) throw new SecurityException("symbolic links require snapshot materializer review");
                    files[0]++;
                    bytes[0] = Math.addExact(bytes[0], attrs.size());
                    if (files[0] > MAX_SOURCE_FILES || bytes[0] > MAX_SOURCE_BYTES)
                        throw new SecurityException("source copy limits exceeded");
                    Files.copy(file, target.resolve(relative), StandardCopyOption.COPY_ATTRIBUTES);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException | SecurityException error) {
            deleteTree(target);
            throw blocked("SOURCE_MATERIALIZATION_FAILED", "Source snapshot could not be materialized safely.");
        }
    }

    /**
     * Files the run must own outright rather than share with the approved seed,
     * because Maven's resolver rewrites them in place instead of replacing them.
     */
    private static final Set<String> RESOLVER_TRACKING_FILES =
            Set.of("_remote.repositories", "resolver-status.properties");

    /**
     * Materialises the approved seed into the writable per-run repository.
     *
     * <p>Seed artifacts are hard-linked rather than copied. A seeded repository
     * for a real Spring application runs to hundreds of megabytes across tens of
     * thousands of files, and copying it byte by byte once per run dominated the
     * cost of starting a run: it is the point at which concurrent runs contend
     * for the disk, so its cost is multiplied by the queue's capacity rather
     * than paid once.</p>
     *
     * <p>Linking cannot expose the shared seed to a run, by construction rather
     * than by convention. A hard link shares the inode and therefore also the
     * permissions, so a link is created only for a seed file that carries no
     * owner write bit: an in-place write through such a link fails outright
     * instead of reaching the seed. Every other file is copied — the resolver's
     * tracking files, which Maven rewrites in place, and any seed file that is
     * itself owner-writable, for which a link would carry a write path back into
     * the seed. Copies keep the previous behaviour of being made owner-writable.</p>
     *
     * <p>That the permission bit is actually enforced is not an assumption: this
     * port is only constructed once the private Runner carries a verified
     * rootless isolation attestation, and a process that is not root cannot
     * write through a file it has no write permission on. Without the
     * attestation the configuration returns a disabled port and this code never
     * runs at all.</p>
     *
     * <p>Hard links cannot cross filesystems, and the seed is required to live
     * outside the workspace root, so the two may well be separate mounts. The
     * first failed link therefore switches the whole tree to copying, which is
     * exactly the previous behaviour.</p>
     */
    static void copyDependencySeed(Path source, Path target) {
        deleteTree(target);
        final long[] bytes = {0};
        final int[] files = {0};
        final boolean[] linking = {true};
        try {
            Files.walkFileTree(source, EnumSet.noneOf(FileVisitOption.class), Integer.MAX_VALUE,
                    new SimpleFileVisitor<>() {
                @Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs)
                        throws IOException {
                    Path relative = source.relativize(dir);
                    if (!relative.toString().isEmpty() && containsExcludedSegment(relative))
                        return FileVisitResult.SKIP_SUBTREE;
                    Path created = target.resolve(relative);
                    Files.createDirectories(created);
                    makeOwnerWritable(created, true);
                    return FileVisitResult.CONTINUE;
                }

                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
                        throws IOException {
                    Path relative = source.relativize(file);
                    if (containsExcludedSegment(relative)) return FileVisitResult.CONTINUE;
                    if (attrs.isSymbolicLink())
                        throw new SecurityException("symbolic links require snapshot materializer review");
                    files[0]++;
                    bytes[0] = Math.addExact(bytes[0], attrs.size());
                    if (files[0] > MAX_SOURCE_FILES || bytes[0] > MAX_SOURCE_BYTES)
                        throw new SecurityException("source copy limits exceeded");
                    Path created = target.resolve(relative);
                    if (linking[0] && !privateToTheRun(file)) {
                        try {
                            Files.createLink(created, file);
                            return FileVisitResult.CONTINUE;
                        } catch (IOException | UnsupportedOperationException error) {
                            linking[0] = false;
                        }
                    }
                    Files.copy(file, created, StandardCopyOption.COPY_ATTRIBUTES);
                    makeOwnerWritable(created, false);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException | SecurityException error) {
            deleteTree(target);
            throw blocked("MAVEN_DEPENDENCY_SEED_MATERIALIZATION_FAILED",
                    "The approved Maven seed could not be materialized into a writable per-run repository.");
        }
    }

    /**
     * Whether a seed entry must be copied instead of linked: either Maven
     * rewrites it in place, or the seed left it owner-writable and a link would
     * carry that write path back into the shared seed. A filesystem without
     * POSIX permissions cannot establish the read-only property at all, so
     * nothing is linked there.
     */
    private static boolean privateToTheRun(Path file) {
        String name = file.getFileName().toString();
        if (RESOLVER_TRACKING_FILES.contains(name) || name.endsWith(".lastUpdated")) return true;
        try {
            return Files.getPosixFilePermissions(file, LinkOption.NOFOLLOW_LINKS)
                    .contains(PosixFilePermission.OWNER_WRITE);
        } catch (UnsupportedOperationException | IOException error) {
            return true;
        }
    }

    private static void makeOwnerWritable(Path path, boolean directory) throws IOException {
        try {
            Set<PosixFilePermission> permissions =
                    EnumSet.copyOf(Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS));
            permissions.add(PosixFilePermission.OWNER_WRITE);
            if (directory) permissions.add(PosixFilePermission.OWNER_EXECUTE);
            Files.setPosixFilePermissions(path, permissions);
        } catch (UnsupportedOperationException error) {
            if (!path.toFile().setWritable(true, true)) {
                throw new IOException("owner-writable permission could not be applied", error);
            }
        }
    }

    private static void zip(Path source, Path target) {
        try (ZipOutputStream output = new ZipOutputStream(Files.newOutputStream(target))) {
            List<Path> paths;
            try (var stream = Files.walk(source)) {
                paths = stream.filter(path -> !path.equals(source))
                        .filter(path -> !containsExcludedSegment(source.relativize(path)))
                        .sorted().toList();
            }
            for (Path path : paths) {
                String name = source.relativize(path).toString().replace(FileSystems.getDefault().getSeparator(), "/");
                ZipEntry entry = new ZipEntry(Files.isDirectory(path) ? name + "/" : name);
                entry.setTime(0);
                output.putNextEntry(entry);
                if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) Files.copy(path, output);
                output.closeEntry();
            }
        } catch (IOException error) {
            throw blocked("ARTIFACT_PACKAGE_FAILED", "Migrated source artifact could not be packaged.");
        }
    }

    private static void preserveVerifiedArtifact(Path source, Path target) {
        try {
            if (!Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS)
                    || Files.isSymbolicLink(source)
                    || Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
                throw blocked("SOURCE_ARTIFACT_PRESERVATION_FAILED",
                        "The verified source artifact is unsafe or its evidence target already exists.");
            }
            createDirectory(target.getParent());
            Files.copy(source, target);
            if (!Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)
                    || Files.isSymbolicLink(target)
                    || Files.size(source) != Files.size(target)
                    || !sha256(source).equals(sha256(target))) {
                throw blocked("SOURCE_ARTIFACT_PRESERVATION_FAILED",
                        "The preserved source artifact does not match the executed bytes.");
            }
        } catch (IOException error) {
            throw blocked("SOURCE_ARTIFACT_PRESERVATION_FAILED",
                    "The verified source artifact could not be preserved as evidence.");
        }
    }

    private static Path bootJar(Path root, String buildTool) {
        Path outputDirectory = SpringRouteCatalog.GRADLE_BUILD_TOOL.equals(buildTool)
                ? root.resolve("build/libs") : root.resolve("target");
        try (var stream = Files.list(outputDirectory)) {
            return stream.filter(path -> path.getFileName().toString().endsWith(".jar"))
                    .filter(path -> !path.getFileName().toString().endsWith(".original"))
                    .filter(path -> !path.getFileName().toString().startsWith("original-"))
                    .filter(LocalSpringUpgradeExecutionPort::isExecutableBootJar)
                    .sorted().findFirst()
                    .orElseThrow(() -> blocked("BOOT_JAR_NOT_FOUND", "Verified Spring Boot artifact was not found."));
        } catch (IOException error) {
            throw blocked("BOOT_JAR_NOT_FOUND", "Verified Spring Boot artifact was not found.");
        }
    }

    private static Path bootArtifact(Path root, Fingerprint sourceFingerprint) {
        if (SpringRouteCatalog.SourceFamily.SPRING_MVC.contractValue()
                .equals(sourceFingerprint.sourceFrameworkFamily())) {
            return SpringMvcWarRuntime.executableBootWar(root, sourceFingerprint.buildTool());
        }
        return bootJar(root, sourceFingerprint.buildTool());
    }

    private static boolean isExecutableBootJar(Path path) {
        try (ZipFile archive = new ZipFile(path.toFile())) {
            return archive.getEntry("BOOT-INF/classes/") != null
                    && archive.getEntry("META-INF/MANIFEST.MF") != null;
        } catch (IOException error) {
            return false;
        }
    }

    private static boolean containsExcludedSegment(Path path) {
        for (Path segment : path) {
            String name = segment.toString();
            if (EXCLUDED.contains(name) || name.startsWith("elmos-secret-")) return true;
        }
        return false;
    }

    private static boolean containsGitLfsPointer(Path root) {
        for (Path path : findFiles(root, "")) {
            try {
                if (Files.size(path) <= 1024
                        && Files.readString(path, StandardCharsets.UTF_8)
                        .startsWith("version https://git-lfs.github.com/spec/v1")) return true;
            } catch (IOException | RuntimeException ignored) {
                // Non-text files and unreadable optional content are not treated as LFS pointers.
            }
        }
        return false;
    }

    private static int reservePort() {
        try (var socket = new java.net.ServerSocket()) {
            socket.bind(new InetSocketAddress("127.0.0.1", 0));
            return socket.getLocalPort();
        } catch (IOException error) {
            throw blocked("RUNTIME_PORT_UNAVAILABLE", "A loopback runtime port could not be reserved.");
        }
    }

    private static void createDirectory(Path path) {
        try { Files.createDirectories(path); }
        catch (IOException error) { throw new IllegalStateException("workspace directory is unavailable", error); }
    }

    private static void deleteTree(Path target) {
        if (target == null || !Files.exists(target, LinkOption.NOFOLLOW_LINKS)) return;
        try {
            Files.walkFileTree(target, new SimpleFileVisitor<>() {
                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                    Files.deleteIfExists(file);
                    return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult postVisitDirectory(Path dir, IOException error) throws IOException {
                    if (error != null) throw error;
                    Files.deleteIfExists(dir);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException error) {
            throw new IllegalStateException("workspace cleanup failed", error);
        }
    }

    private void writeJson(Path path, Object value) {
        try {
            createDirectory(path.getParent());
            json.writerWithDefaultPrettyPrinter()
                    .with(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
                    .writeValue(path.toFile(), value);
        } catch (IOException error) {
            throw blocked("EVIDENCE_WRITE_FAILED", "Framework evidence could not be written.");
        }
    }

    private static void write(Path path, byte[] bytes) {
        try {
            createDirectory(path.getParent());
            Files.write(path, bytes, StandardOpenOption.CREATE_NEW);
        } catch (IOException error) {
            throw blocked("EVIDENCE_WRITE_FAILED", "Snapshot evidence could not be written.");
        }
    }

    private static String read(Path path) {
        try {
            if (Files.size(path) > 4 * 1024 * 1024) return "";
            return Files.readString(path, StandardCharsets.UTF_8);
        } catch (IOException error) {
            return "";
        }
    }

    private static long size(Path path) {
        try { return Files.size(path); }
        catch (IOException error) { throw new IllegalStateException(error); }
    }

    private static String sha256(Path path) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (var input = Files.newInputStream(path)) {
                byte[] buffer = new byte[64 * 1024];
                int count;
                while ((count = input.read(buffer)) >= 0) digest.update(buffer, 0, count);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (Exception error) {
            throw new IllegalStateException("artifact digest failed", error);
        }
    }

    private static String safeRepositoryId(String url) {
        return "public-" + Integer.toUnsignedString(Objects.toString(url, "").hashCode(), 36);
    }

    private static String safeFullName(String url) {
        try {
            URI uri = URI.create(url);
            String path = uri.getPath();
            if (path != null) {
                String clean = path.startsWith("/") ? path.substring(1) : path;
                if (clean.endsWith(".git")) clean = clean.substring(0, clean.length() - 4);
                if (clean.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")) return clean;
            }
        } catch (RuntimeException ignored) { }
        return "public/unknown";
    }

    private static boolean blank(String value) { return value == null || value.isBlank(); }
    private static BlockedException blocked(String code, String message) { return new BlockedException(code, message); }
    private static void checkCancelled(Control control) {
        if (control.cancelled()) throw blocked("RUN_CANCELLED", "The migration run was cancelled.");
    }

    private record SourceIdentity(String commitSha, String treeSha) {}
    private record CommandOutcome(int exitCode) {}
    record CapabilityTestRun(List<String> testIdentities, long skipped) {
        CapabilityTestRun {
            testIdentities = List.copyOf(testIdentities);
            if (skipped < 0) throw new IllegalArgumentException("skipped must not be negative");
        }
    }
    record ComplexCapabilityDecision(Map<String, Object> report, List<String> blockers) {
        ComplexCapabilityDecision {
            report = Map.copyOf(report);
            blockers = List.copyOf(blockers);
        }
    }
    private record ManifestInspection(Map<String, Object> report) {
        private ManifestInspection {
            report = Map.copyOf(report);
        }
    }
    private record TestSummary(
            List<String> reports,
            long tests,
            long failures,
            long errors,
            long skipped,
            long executed,
            List<String> testIdentities
    ) {
        private TestSummary {
            reports = List.copyOf(reports);
            testIdentities = List.copyOf(testIdentities);
        }
    }
}
