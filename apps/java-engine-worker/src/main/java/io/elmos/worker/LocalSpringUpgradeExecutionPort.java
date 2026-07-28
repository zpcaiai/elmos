package io.elmos.worker;

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
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
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
    private static final long MAX_SOURCE_BYTES = 512L * 1024 * 1024;
    private static final int MAX_SOURCE_FILES = 100_000;
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
    private final Path targetJavaHome;
    private final String mavenExecutable;
    private final Set<String> allowedGitHosts;
    private final boolean allowFileRepositories;
    private final boolean mavenOffline;
    private final Path dependencySeedRepository;
    private final boolean experimentalRoutesEnabled;
    private final ObjectMapper json;
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
                                    String mavenExecutable, Set<String> allowedGitHosts,
                                    boolean allowFileRepositories, boolean mavenOffline,
                                    Path dependencySeedRepository, boolean experimentalRoutesEnabled,
                                    ObjectMapper json, SpringUpgradeCodingAgentPort codingAgentPort) {
        this.workspaceRoot = normalizeRoot(workspaceRoot);
        this.javaHomes = verifiedJavaHomes(configuredJavaHomes);
        Path target = this.javaHomes.get(SpringRouteCatalog.TARGET_JAVA);
        if (target == null) {
            throw new IllegalStateException(
                    "target JAVA_HOME for Java " + SpringRouteCatalog.TARGET_JAVA + " is required");
        }
        this.targetJavaHome = target;
        this.mavenExecutable = requireMaven(mavenExecutable, this.targetJavaHome);
        this.allowedGitHosts = Set.copyOf(allowedGitHosts);
        this.allowFileRepositories = allowFileRepositories;
        this.mavenOffline = mavenOffline;
        this.dependencySeedRepository = normalizeDependencySeed(
                dependencySeedRepository, this.workspaceRoot, mavenOffline);
        this.experimentalRoutesEnabled = experimentalRoutesEnabled;
        this.json = Objects.requireNonNull(json);
        this.codingAgentPort = Objects.requireNonNull(codingAgentPort, "codingAgentPort");
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
        SpringRouteCatalog.Selection selection = selectRoute(fingerprint);
        SpringRouteCatalog.SpringRoute route = selection.route();
        String sourceJava = SpringRouteCatalog.normalizeJava(fingerprint.javaVersion());
        Path sourceJavaHome = sourceJavaHome(sourceJava);
        control.log("fingerprint spring-boot=" + fingerprint.springBootVersion()
                + " java=" + sourceJava + " build=" + fingerprint.buildTool()
                + " route=" + route.routeId() + " evidence=" + selection.evidence());
        Map<String, Object> routeSelection = new LinkedHashMap<>();
        routeSelection.put("schema_version", "1.0");
        routeSelection.put("route_id", route.routeId());
        routeSelection.put("pack_key", route.packKey());
        routeSelection.put("detected_spring_boot", fingerprint.springBootVersion());
        routeSelection.put("detected_java", sourceJava);
        routeSelection.put("detected_build_tool", fingerprint.buildTool());
        routeSelection.put("accepted_source_range",
                "[" + route.sourceBootMinInclusive() + ", " + route.sourceBootMaxExclusive() + ")");
        routeSelection.put("route_evidence", selection.evidence().name());
        routeSelection.put("experimental_opt_in_required", selection.requiresExperimentalOptIn());
        routeSelection.put("recipe_id", route.recipeId());
        routeSelection.put("target_spring_boot", route.targetBoot());
        routeSelection.put("target_java", route.targetJava());
        writeJson(runRoot.resolve("evidence/route-selection.json"), routeSelection);

        control.stage(Stage.SOURCE_BASELINE,
                "Running the source repository's complete Maven verify lifecycle with Java " + sourceJava);
        Path sourceBaseline = runRoot.resolve("source-baseline");
        Path mavenHome = runRoot.resolve("maven-home");
        createDirectory(mavenHome);
        if (dependencySeedRepository != null) {
            copyDependencySeed(dependencySeedRepository, mavenHome.resolve(".m2/repository"));
            control.log("maven dependency seed copied into the isolated per-run repository");
        }
        copyTree(source, sourceBaseline);
        TestSummary sourceTests;
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
            runMaven(sourceBaseline, sourceJavaHome, mavenHome, control,
                    List.of("verify"), Duration.ofMinutes(25));
            sourceTests = testSummary(sourceBaseline);
            requireSourceTests(sourceTests);
            writeJson(runRoot.resolve("evidence/source-test-summary.json"), sourceTests);
            validateSourceStartup(sourceBaseline, runRoot, control, sourceJavaHome);
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
        runRewrite(migrated, mavenHome, control, route);
        checkCancelled(control);

        control.stage(Stage.BUILD_AND_TEST,
                "Running the target repository's complete Maven verify lifecycle with Java " + route.targetJava());
        CommandOutcome firstBuild = runMavenOutcome(migrated, targetJavaHome, mavenHome, control,
                List.of("verify"), Duration.ofMinutes(30));
        if (firstBuild.exitCode() != 0) {
            control.stage(Stage.DETERMINISTIC_REPAIR,
                    "Target build failed; applying one bounded deterministic OpenRewrite repair cycle");
            runRewrite(migrated, mavenHome, control, route);
            CommandOutcome secondBuild = runMavenOutcome(migrated, targetJavaHome, mavenHome, control,
                    List.of("verify"), Duration.ofMinutes(30));
            if (secondBuild.exitCode() != 0) {
                recordCodingAgentCandidates(runRoot, request.organizationId(), identity.commitSha());
                throw blocked("MAVEN_COMMAND_FAILED",
                        "A required Maven/OpenRewrite command failed; inspect the redacted run log.");
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
        SpringDeploymentGuidance.writeTo(migrated);

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
        control.stage(Stage.START_APPLICATION, "Starting verified artifact with Java 21");
        Path jar = bootJar(result.migratedRepository());
        int port = reservePort();
        Path log = runRoot.resolve("runtime/application.log");
        createDirectory(log.getParent());
        ProcessBuilder builder = new ProcessBuilder(targetJavaHome.resolve("bin/java").toString(), "-jar", jar.toString());
        builder.directory(result.migratedRepository().toFile());
        builder.environment().put("JAVA_HOME", targetJavaHome.toString());
        builder.environment().put("SERVER_PORT", Integer.toString(port));
        builder.environment().put("MANAGEMENT_SERVER_PORT", Integer.toString(port));
        builder.redirectErrorStream(true);
        builder.redirectOutput(ProcessBuilder.Redirect.appendTo(log.toFile()));
        try {
            Process process = builder.start();
            control.process(process);
            control.stage(Stage.HEALTH_CHECK, "Waiting for application health endpoint");
            String health = waitForHealth(process, port, result.healthCandidates(), control);
            control.log("application healthy on loopback port " + port + " path " + health);
            return new RuntimeHandle(process, null, request.organizationId(), port, health);
        } catch (IOException error) {
            throw blocked("APPLICATION_START_FAILED", "Verified artifact could not be started in the private Runner.");
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

    private void validateSourceStartup(Path source, Path runRoot, Control control, Path sourceJavaHome) {
        Path jar = bootJar(source);
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
        builder.environment().put("SERVER_PORT", Integer.toString(port));
        builder.environment().put("MANAGEMENT_SERVER_PORT", Integer.toString(port));
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
                    "Source baseline could not be started with the exact Java 17 toolchain.");
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

    Fingerprint fingerprint(Path root) {
        Path pom = root.resolve("pom.xml");
        if (!Files.isRegularFile(pom, LinkOption.NOFOLLOW_LINKS)) {
            // Report the build tool that was actually found so route selection
            // can produce a specific reason instead of "Maven only".
            if (hasGradleBuild(root)) {
                throw blocked("SPRING_ROUTE_NOT_IMPLEMENTED",
                        "A Gradle build was detected. The Gradle route is declared in the catalog but "
                                + "has no execution driver: it needs its own wrapper verification and "
                                + "rewrite plugin invocation.");
            }
            throw blocked("BUILD_MODEL_UNRECOGNIZED",
                    "No root pom.xml and no Gradle build script were found; the source build model "
                            + "could not be identified.");
        }
        Document document = parsePom(pom);
        String boot = springBootVersion(document);
        String java = property(document, "java.version");
        if (blank(java)) java = property(document, "maven.compiler.release");
        if (blank(java)) java = property(document, "maven.compiler.source");
        List<String> modules = children(document, "modules", "module");
        String pomText = read(pom);
        Map<String,List<String>> traces = new TreeMap<>();
        List<String> capabilities = new ArrayList<>();
        capability(pomText, root, traces, capabilities, "web", "spring-boot-starter-web", "@RestController", "@Controller");
        capability(pomText, root, traces, capabilities, "spring-boot-parent", "spring-boot-starter-parent");
        capability(pomText, root, traces, capabilities, "security", "spring-boot-starter-security", "@EnableWebSecurity", "SecurityFilterChain");
        capability(pomText, root, traces, capabilities, "persistence", "spring-boot-starter-data-jpa", "@Entity", "JpaRepository");
        capability(pomText, root, traces, capabilities, "transactions", "spring-tx", "@Transactional");
        capability(pomText, root, traces, capabilities, "validation", "spring-boot-starter-validation", "@Valid", "@Validated");
        capability(pomText, root, traces, capabilities, "actuator", "spring-boot-starter-actuator", "management.endpoints");
        capability(pomText, root, traces, capabilities, "messaging", "spring-kafka", "@KafkaListener", "JmsListener");
        capability(pomText, root, traces, capabilities, "scheduler", "spring-context", "@Scheduled", "@EnableScheduling");
        List<String> unknowns = new ArrayList<>();
        if (findFiles(root, ".java").stream().anyMatch(path -> read(path).contains("WebSecurityConfigurerAdapter")))
            unknowns.add("legacy-security-adapter-requires-rewrite-and-contract-review");
        if (Files.exists(root.resolve(".gitmodules"))) unknowns.add("submodules-present");
        return new Fingerprint(blank(boot) ? "UNKNOWN" : boot, blank(java) ? "UNKNOWN" : java.trim(),
                "maven", modules, capabilities.stream().distinct().sorted().toList(), unknowns, traces);
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
        SpringRouteCatalog.Selection selection = SpringRouteCatalog.select(
                fingerprint.springBootVersion(), fingerprint.javaVersion(), fingerprint.buildTool());
        if (!fingerprint.activeCapabilities().contains("spring-boot-parent")) {
            throw blocked("UNSUPPORTED_BOOT_VERSION_AUTHORITY",
                    "Route " + selection.route().routeId() + " requires spring-boot-starter-parent as "
                            + "the source version authority.");
        }
        if (selection.requiresExperimentalOptIn() && !experimentalRoutesEnabled) {
            throw blocked("SPRING_ROUTE_EVIDENCE_NOT_RUN",
                    "Route " + selection.route().routeId() + " accepts Spring Boot "
                            + fingerprint.springBootVersion() + " on Java "
                            + SpringRouteCatalog.normalizeJava(fingerprint.javaVersion())
                            + ", but this tuple has no recorded local execution evidence ("
                            + selection.evidence() + "). Enable "
                            + "elmos.worker.spring-upgrade.experimental-routes-enabled to run it as an "
                            + "explicitly experimental migration.");
        }
        return selection;
    }

    private void runRewrite(Path root, Path mavenHome, Control control,
                            SpringRouteCatalog.SpringRoute route) {
        Path recipeConfig = installExactRecipe(root, route);
        runMaven(root, targetJavaHome, mavenHome, control, List.of(
                "org.openrewrite.maven:rewrite-maven-plugin:" + route.rewriteMavenPlugin() + ":run",
                "-Drewrite.configLocation=" + root.relativize(recipeConfig),
                "-Drewrite.activeRecipes=" + route.recipeId(),
                "-Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-spring:"
                        + route.rewriteSpring(),
                "-Drewrite.exportDatatables=true"
        ), Duration.ofMinutes(30));
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
        model.put("exact_tuple", route.tuple(
                fingerprint.springBootVersion(), SpringRouteCatalog.normalizeJava(fingerprint.javaVersion())));
        model.put("capabilities", fingerprint.activeCapabilities().stream().map(capability -> Map.of(
                "id", capability,
                "status", "observed",
                "source_traces", fingerprint.sourceTraces().getOrDefault(capability, List.of()),
                "obligations", List.of("target-build", "startup", "behavior-comparison")
        )).toList());
        model.put("unknowns", fingerprint.unknowns());
        model.put("ordering_and_defaults", Map.of(
                "security_filter_order", "preserve-and-verify",
                "configuration_precedence", "preserve-and-verify",
                "transaction_defaults", "preserve-and-verify"));
        return model;
    }

    private String waitForHealth(Process process, int port, List<String> candidates, Control control) {
        HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
        Instant deadline = Instant.now().plusSeconds(60);
        while (Instant.now().isBefore(deadline)) {
            checkCancelled(control);
            if (!process.isAlive()) throw blocked("APPLICATION_EXITED_BEFORE_HEALTHY", "The application exited before becoming healthy.");
            for (String path : candidates) {
                try {
                    var response = client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
                                    .timeout(Duration.ofSeconds(2)).GET().build(),
                            HttpResponse.BodyHandlers.discarding());
                    if (response.statusCode() >= 200 && response.statusCode() < 300) return path;
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

    private HttpProbe waitForStartup(
            Process process,
            int port,
            List<String> candidates,
            Control control
    ) {
        HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
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

    private void capability(String pom, Path root, Map<String,List<String>> traces, List<String> capabilities,
                            String id, String... needles) {
        List<String> found = new ArrayList<>();
        for (String needle : needles) {
            if (pom.contains(needle)) found.add("pom.xml:" + needle);
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
                            && path.getParent().getFileName().toString().equals("surefire-reports"))
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
                    "Maven test report is invalid.");
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

    private static long longAttribute(Element element, String name) {
        String value = element.getAttribute(name);
        if (value == null || value.isBlank()) return 0;
        try {
            long parsed = Long.parseLong(value);
            if (parsed < 0) throw new NumberFormatException("negative");
            return parsed;
        } catch (NumberFormatException error) {
            throw blocked("TEST_REPORT_INVALID", "Maven test report counters are invalid.");
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
        if (trimmed.matches("\\$\\{[^}]+}")) return property(document, trimmed.substring(2, trimmed.length() - 1));
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

    static void copyDependencySeed(Path source, Path target) {
        copyTree(source, target);
        try {
            Files.walkFileTree(target, new SimpleFileVisitor<>() {
                @Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs)
                        throws IOException {
                    makeOwnerWritable(dir, true);
                    return FileVisitResult.CONTINUE;
                }

                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
                        throws IOException {
                    makeOwnerWritable(file, false);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException error) {
            deleteTree(target);
            throw blocked("MAVEN_DEPENDENCY_SEED_MATERIALIZATION_FAILED",
                    "The approved Maven seed could not be copied into a writable per-run repository.");
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

    private static Path bootJar(Path root) {
        try (var stream = Files.list(root.resolve("target"))) {
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
