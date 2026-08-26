package io.elmos.runner;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Self-contained acceptance suite for the Runner Agent.
 *
 * <p>No third-party test framework, matching the agent's zero-dependency rule.
 * Run with {@code java -cp target/classes:target/test-classes io.elmos.runner.AgentSelfTest};
 * a non-zero exit code fails the build.</p>
 */
public final class AgentSelfTest {

    private static final List<String> FAILURES = new ArrayList<>();
    private static int checks;

    enum RealContainerStatus { PASSED, NOT_RUN, FAILED }

    public static void main(String[] args) throws Exception {
        Path scratch = Files.createTempDirectory("elmos-agent-test");
        try {
            jsonRoundTrips();
            jsonRejectsHostileInput();
            configFailsClosed();
            imagePinningIsEnforced();
            localImageInventoryFailsClosed(scratch);
            claimAdvertisesOnlyVerifiedImages(scratch);
            containerFlagsAreComplete();
            workspaceIsolatesAndCleansUp();
            digestMatchesKnownVector(scratch);
            artifactRolesAreDerivedFromLayout();
            progressProtocolIsParsed();
            backoffStaysInBounds();
            nodeCredentialSurvivesRestart(scratch);
            realContainerConfigurationFailsClosed(scratch);

            endToEndSuccess(scratch);
            cancellationKillsTheContainer(scratch);
            stolenLeaseIsAbandonedWithoutReporting(scratch);
            drainStopsClaiming(scratch);
            workspaceAccessIsProvenAtStartup(scratch);
            networkPartitionFencesTheJob(scratch);
            boolean realContainerRequired = false;
            boolean strictProfileValid = true;
            try {
                realContainerRequired = realContainerRequired(
                        System.getProperty("elmos.test.requireRealContainer", "false"));
            } catch (IllegalArgumentException ex) {
                strictProfileValid = false;
                check("real-container strict profile is a boolean", false);
            }

            int failuresBeforeRealContainer = FAILURES.size();
            RealContainerStatus realContainerStatus;
            try {
                realContainerStatus = realContainerRoundTrip(scratch);
            } catch (Exception ex) {
                if (ex instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
                realContainerStatus = RealContainerStatus.FAILED;
                check("real container round trip completed: " + ex.getMessage(), false);
            }
            if (FAILURES.size() > failuresBeforeRealContainer) {
                realContainerStatus = RealContainerStatus.FAILED;
            }
            if (!strictProfileValid) {
                realContainerStatus = RealContainerStatus.FAILED;
            }
            System.out.println("ELMOS_RUNNER_REAL_CONTAINER_RESULT=" + Json.write(Map.of(
                    "schemaVersion", "elmos.runner-real-container.v1",
                    "status", realContainerStatus.name(),
                    "required", realContainerRequired)));
            if (realContainerRequired) {
                check("strict profile requires a passed real container round trip",
                        realContainerStatus == RealContainerStatus.PASSED);
            }
        } finally {
            JobWorkspace.deleteRecursively(scratch);
        }

        System.out.println();
        if (FAILURES.isEmpty()) {
            System.out.println("RUNNER AGENT SELF TEST PASSED (" + checks + " checks)");
            return;
        }
        System.out.println("RUNNER AGENT SELF TEST FAILED (" + FAILURES.size() + "/" + checks + ")");
        FAILURES.forEach(failure -> System.out.println("  - " + failure));
        throw new AssertionError("RUNNER AGENT SELF TEST FAILED");
    }

    // ---- unit level --------------------------------------------------------

    static void jsonRoundTrips() {
        Map<String, Object> source = new HashMap<>();
        source.put("text", "quote\" backslash\\ newline\n tab\t");
        source.put("number", 42);
        source.put("flag", true);
        source.put("nothing", null);
        source.put("nested", Map.of("list", List.of(1, 2, 3)));

        Map<String, Object> parsed = Json.parseObject(Json.write(source));
        check("json preserves escaped text", source.get("text").equals(parsed.get("text")));
        check("json preserves integers", Json.integer(parsed, "number", -1) == 42);
        check("json preserves booleans", Json.bool(parsed, "flag", false));
        check("json preserves explicit null", parsed.containsKey("nothing") && parsed.get("nothing") == null);
        check("json preserves nesting", Json.object(parsed, "nested").containsKey("list"));

        // Chinese text and emoji must survive, since job kinds and filenames carry them.
        String unicode = Json.string(Json.parseObject(Json.write(Map.of("k", "生成任务 ✅"))), "k", "");
        check("json preserves non-ascii", "生成任务 ✅".equals(unicode));
    }

    static void jsonRejectsHostileInput() {
        check("json rejects trailing content", throwsJson("{} {}"));
        check("json rejects unterminated string", throwsJson("{\"a\":\"b"));
        check("json rejects bad escape", throwsJson("{\"a\":\"\\x\"}"));
        check("json rejects deep nesting", throwsJson("[".repeat(200) + "]".repeat(200)));
    }

    static void configFailsClosed() {
        Map<String, String> base = new HashMap<>();
        base.put("ELMOS_CONTROL_PLANE_BASE_URL", "https://control.example.com");
        base.put("ELMOS_RUNNER_NODE_ID", "runner-1");
        base.put("ELMOS_RUNNER_POOL_ID", "pool-shared");
        base.put("ELMOS_RUNNER_ENROLMENT_TOKEN", "x".repeat(40));
        base.put("ELMOS_RUNNER_CAPABILITIES", "generation:multi");
        base.put("ELMOS_RUNNER_IMAGES", pinned());
        base.put("ELMOS_RUNNER_WORK_ROOT", "/tmp/elmos-runner-work");
        base.put("ELMOS_RUNNER_ALLOW_HOST_EXECUTION", "true");

        check("config accepts a valid host-execution setup", !throwsConfig(base));

        check("config rejects http outside loopback",
                throwsConfig(with(base, "ELMOS_CONTROL_PLANE_BASE_URL", "http://control.example.com")));
        check("config rejects a short enrolment token",
                throwsConfig(with(base, "ELMOS_RUNNER_ENROLMENT_TOKEN", "short")));
        check("config rejects the filesystem root as work root",
                throwsConfig(with(base, "ELMOS_RUNNER_WORK_ROOT", "/")));
        check("config rejects host execution in production",
                throwsConfig(with(base, "ELMOS_ENVIRONMENT", "production")));
        check("config requires a container engine when host execution is off",
                throwsConfig(with(base, "ELMOS_RUNNER_ALLOW_HOST_EXECUTION", "false")));
        check("config rejects a mutable runner image",
                throwsConfig(with(base, "ELMOS_RUNNER_IMAGES",
                        "registry.example.com/elmos/generation:latest")));
        check("config rejects duplicate runner images",
                throwsConfig(with(base, "ELMOS_RUNNER_IMAGES", pinned() + "," + pinned())));
        check("config rejects empty runner image entries",
                throwsConfig(with(base, "ELMOS_RUNNER_IMAGES", pinned() + ",")));
        check("strict real-container profile accepts true",
                realContainerRequired("true"));
        check("strict real-container profile accepts false",
                !realContainerRequired("false"));
        check("strict real-container profile rejects unknown values",
                throwsEngineConfiguration(() -> realContainerRequired("yes")));

        Map<String, String> relativeEngine = with(base, "ELMOS_RUNNER_ALLOW_HOST_EXECUTION", "false");
        relativeEngine.put("ELMOS_RUNNER_CONTAINER_ENGINE", "podman");
        check("config rejects a PATH-resolved container engine", throwsConfig(relativeEngine));

        // A lease that covers fewer than three heartbeats loses the job on one
        // dropped request.
        Map<String, String> tightTiming = with(base, "ELMOS_RUNNER_LEASE_SECONDS", "30");
        tightTiming.put("ELMOS_RUNNER_HEARTBEAT_SECONDS", "20");
        boolean threw = false;
        try {
            AgentConfig.fromEnvironment(tightTiming).validateTimings();
        } catch (AgentConfig.ConfigException ex) {
            threw = true;
        }
        check("config rejects a heartbeat interval too close to the lease", threw);
    }

    static void imagePinningIsEnforced() {
        String digest = "registry.example.com/elmos/generation@sha256:" + "b".repeat(64);
        boolean pinnedOk = true;
        try {
            ContainerRuntime.validateImage(digest);
        } catch (RuntimeException ex) {
            pinnedOk = false;
        }
        check("digest-pinned image is accepted", pinnedOk);
        check("mutable tag is rejected", throwsImage("registry.example.com/elmos/generation:latest"));
        check("short digest is rejected", throwsImage("registry.example.com/x@sha256:abc"));
        check("null image is rejected", throwsImage(null));
    }

    static void localImageInventoryFailsClosed(Path scratch) throws IOException {
        Path work = Files.createTempDirectory(scratch, "image-inventory");
        String absent = "registry.example.com/elmos/other@sha256:" + "d".repeat(64);
        AgentConfig config = new AgentConfig(
                "https://control.example.com", "runner-test", "pool-shared", "x".repeat(40),
                List.of("generation:multi"), List.of(pinned(), absent), 2, work,
                "/usr/bin/podman", 2, 30, 5, 5, 9999, false,
                WorkspaceAccessProbe.currentUid(), WorkspaceAccessProbe.currentGid());
        ProcessRunner inventory = new ProcessRunner() {
            @Override
            public Result run(List<String> command, Path workingDirectory,
                              Map<String, String> environment, long timeoutSeconds) {
                boolean present = command.size() == 4
                        && command.get(1).equals("image")
                        && command.get(2).equals("exists")
                        && command.get(3).equals(pinned());
                return new Result(present ? 0 : 1, "", "", false);
            }

            @Override
            public Handle start(List<String> command, Path workingDirectory,
                                Map<String, String> environment,
                                java.util.function.Consumer<String> onLine) {
                throw new UnsupportedOperationException("not used by inventory test");
            }
        };
        ContainerRuntime runtime = new ContainerRuntime(config, inventory);
        check("claim inventory reports only images present by exact digest",
                runtime.locallyAvailableImages().equals(List.of(pinned())));
        check("startup rejects any configured image absent from the local store",
                throwsRuntime(runtime::requireConfiguredImagesLocal));
    }

    static void claimAdvertisesOnlyVerifiedImages(Path scratch) throws Exception {
        try (FakeControlPlane plane = new FakeControlPlane()) {
            AgentConfig config = hostConfig(
                    plane.baseUrl(), Files.createTempDirectory(scratch, "claim-images"), 1);
            ControlPlaneClient client = new ControlPlaneClient(config);
            client.claim(1, List.of(pinned()));
            Object advertised = plane.lastClaimRequest.get().get("availableImages");
            check("claim request carries the exact verified image list",
                    advertised instanceof List<?> images && images.equals(List.of(pinned())));
            check("claim rejects an empty verified image list",
                    throwsRuntime(() -> client.claim(1, List.of())));
        }
    }

    static void containerFlagsAreComplete() throws IOException {
        Path work = Files.createTempDirectory("elmos-flags");
        AgentConfig config = hostConfig("http://127.0.0.1:1", work, 1);
        ContainerRuntime runtime = new ContainerRuntime(
                new AgentConfig(config.controlPlaneBaseUrl(), config.runnerNodeId(), config.poolId(),
                        config.enrolmentToken(), config.capabilities(), List.of(pinned()),
                        config.maxConcurrency(), work,
                        "/usr/bin/podman", 1, 120, 30, 30, 9464, false,
                        WorkspaceAccessProbe.currentUid(), WorkspaceAccessProbe.currentGid()),
                new ProcessRunner.Os());

        try (JobWorkspace workspace = JobWorkspace.create(work, "job-flags")) {
            ControlPlaneClient.Lease lease = new ControlPlaneClient.Lease("job-flags", "lease-1", "t",
                    "GENERATION", "kind", "reg.example.com/i@sha256:" + "c".repeat(64),
                    600, 2000, 2048, 1, Map.of(), Map.of());
            String command = String.join(" ", runtime.buildCommand(lease, workspace, "elmos-job-flags"));

            for (String required : List.of("--network=none", "--read-only", "--cap-drop=ALL",
                    "--security-opt=no-new-privileges", "--pids-limit=512",
                    "--memory=2048m", "--memory-swap=2048m", "--cpus=2.00", "--pull=never")) {
                check("container command carries " + required, command.contains(required));
            }
            // The workload uid must be the one that owns the workspace, not a
            // constant that happens to match in one deployment.
            check("workload runs as the agent identity",
                    command.contains("--user=" + WorkspaceAccessProbe.currentUid()
                            + ":" + WorkspaceAccessProbe.currentGid()));
            check("input directory is mounted read-only", command.contains(":/elmos/in:ro"));
            check("output directory is mounted read-write", command.contains(":/elmos/out:rw"));
            // The workload must never see the credentials the agent holds.
            check("no enrolment token reaches the container",
                    !command.contains(config.enrolmentToken()));
            check("no control-plane url reaches the container",
                    !command.contains(config.controlPlaneBaseUrl()));
        } finally {
            JobWorkspace.deleteRecursively(work);
        }
    }

    static void workspaceIsolatesAndCleansUp() throws IOException {
        Path work = Files.createTempDirectory("elmos-ws");
        try {
            Path root;
            try (JobWorkspace workspace = JobWorkspace.create(work, "job-abc")) {
                root = workspace.root();
                check("workspace directories are owner-only",
                        PosixFilePermissions.toString(Files.getPosixFilePermissions(root)).equals("rwx------"));
                workspace.writeInput("request.json", "{}");
                Files.writeString(workspace.out().resolve("project.zip"), "zip-bytes");
                Files.createSymbolicLink(workspace.out().resolve("escape"), Path.of("/etc/passwd"));

                List<Path> outputs = workspace.outputs();
                check("workspace lists real outputs", outputs.size() == 1);
                check("workspace skips symlinked outputs",
                        outputs.stream().noneMatch(p -> p.getFileName().toString().equals("escape")));
            }
            check("workspace is removed on close", !Files.exists(root));

            check("workspace rejects a traversal job id", throwsIo(() -> JobWorkspace.create(work, "../escape")));

            Files.createDirectories(work.resolve("orphan-1"));
            Files.createDirectories(work.resolve("orphan-2"));
            check("orphan sweep removes leftovers", JobWorkspace.sweepOrphans(work) == 2);
        } finally {
            JobWorkspace.deleteRecursively(work);
        }
    }

    static void digestMatchesKnownVector(Path scratch) throws IOException {
        Path file = scratch.resolve("abc.txt");
        Files.writeString(file, "abc");
        // Published SHA-256 test vector for "abc".
        check("streaming digest matches the known vector",
                ArtifactPublisher.sha256(file)
                        .equals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
    }

    static void artifactRolesAreDerivedFromLayout() {
        check("archive role", ArtifactPublisher.roleFor("project.zip").equals("PROJECT_ARCHIVE"));
        check("evidence role", ArtifactPublisher.roleFor("evidence/pack.tar.zst").equals("EVIDENCE_PACK"));
        check("log role", ArtifactPublisher.roleFor("logs/build.log").equals("BUILD_LOG"));
        check("sbom role", ArtifactPublisher.roleFor("sbom.spdx.json").equals("SBOM"));
        check("diff role", ArtifactPublisher.roleFor("changes.patch").equals("DIFF"));
        check("gate role", ArtifactPublisher.roleFor("gate/gate-report.json").equals("GATE_REPORT"));
    }

    static void progressProtocolIsParsed() {
        check("progress line parses stage and percent",
                JobExecutor.parseProgress("::elmos stage=building progress=40").get("progress").equals(40));
        check("progress line parses stage only",
                JobExecutor.parseProgress("::elmos stage=queued").get("stage").equals("queued"));
        check("ordinary output is not progress",
                JobExecutor.parseProgress("Downloading dependency foo").isEmpty());
        check("injected progress line with junk is rejected",
                JobExecutor.parseProgress("::elmos stage=build; rm -rf /").isEmpty());
    }

    static void backoffStaysInBounds() {
        Backoff backoff = new Backoff(100, 1_000);
        long previousCeiling = 0;
        for (int i = 0; i < 20; i++) {
            long delay = backoff.nextDelayMillis();
            check("backoff stays within bounds", delay >= 100 && delay <= 1_000);
            previousCeiling = Math.max(previousCeiling, delay);
        }
        check("backoff reaches its ceiling", previousCeiling > 100);
        backoff.reset();
        check("backoff resets", backoff.attempts() == 0);
    }

    static void nodeCredentialSurvivesRestart(
            Path scratch) throws Exception {
        Path work = Files.createTempDirectory(
                scratch, "node-credential");
        String first = "a".repeat(43);
        NodeCredentialStore created =
                new NodeCredentialStore(work, first);
        check("new node credential is not enrolled",
                !created.state().preexisting());
        created.markEnrolled();

        NodeCredentialStore restarted =
                new NodeCredentialStore(work, "b".repeat(43));
        check("node credential survives restart",
                restarted.state().preexisting()
                        && first.equals(
                                restarted.state().currentToken()));

        String next = "c".repeat(43);
        String request = "rotate-test-0001";
        restarted.stageRotation(next, request);
        NodeCredentialStore interrupted =
                new NodeCredentialStore(work, "d".repeat(43));
        check("pending rotation survives an ambiguous response",
                interrupted.state().hasPendingRotation());
        check("pending rotation keeps the exact request",
                request.equals(
                        interrupted.state().rotationRequestId()));
        interrupted.commitPending();

        NodeCredentialStore committed =
                new NodeCredentialStore(work, "e".repeat(43));
        check("confirmed rotation becomes the durable token",
                next.equals(
                        committed.state().currentToken()));
        check("confirmed rotation clears pending state",
                !committed.state().hasPendingRotation());
    }

    // ---- end to end --------------------------------------------------------

    static void endToEndSuccess(Path scratch) throws Exception {
        try (FakeControlPlane plane = new FakeControlPlane()) {
            Path work = Files.createTempDirectory(scratch, "e2e-ok");
            Path engine = fakeEngine(scratch, "engine-ok.sh", 0, 0);
            AgentConfig config = engineConfig(plane.baseUrl(), work, engine);

            JobExecutor executor = executor(config, plane);
            JobExecutor.Outcome outcome = executor.execute(
                    plane.lease("job-ok", "lease-ok", pinned(), 600));

            String diagnostic = plane.completions.isEmpty()
                    ? "no-completion"
                    : plane.completions.get(0).failureCode();
            check("successful job reports SUCCEEDED (failure=" + diagnostic + ")",
                    outcome == JobExecutor.Outcome.SUCCEEDED);
            check("completion reached the control plane", plane.completions.size() == 1);
            if (!plane.completions.isEmpty()) {
                check("completion status is SUCCEEDED",
                        plane.completions.get(0).status().equals("SUCCEEDED"));
                check("result status is PASSED",
                        plane.completions.get(0).resultStatus().equals("PASSED"));
            }
            check("artifact was uploaded", plane.uploads.size() == 1);
            check("artifact was published", plane.published.size() == 1);
            if (!plane.published.isEmpty()) {
                check("artifact role was derived",
                        plane.published.get(0).role().equals("PROJECT_ARCHIVE"));
            }
            check("workspace was cleaned up", !Files.exists(work.resolve("job-ok")));
        }
    }

    static void cancellationKillsTheContainer(Path scratch) throws Exception {
        try (FakeControlPlane plane = new FakeControlPlane()) {
            plane.cancelRequested.set(true);
            Path work = Files.createTempDirectory(scratch, "e2e-cancel");
            Path engine = fakeEngine(scratch, "engine-slow.sh", 60, 0);
            AgentConfig config = engineConfig(plane.baseUrl(), work, engine);

            long started = System.currentTimeMillis();
            JobExecutor.Outcome outcome = executor(config, plane)
                    .execute(plane.lease("job-cancel", "lease-cancel", pinned(), 600));
            long elapsed = System.currentTimeMillis() - started;

            check("cancelled job reports CANCELLED", outcome == JobExecutor.Outcome.CANCELLED);
            check("cancellation is observed within one heartbeat interval", elapsed < 20_000);
            check("cancellation reported once", plane.completions.size() == 1);
            check("cancellation status is CANCELLED",
                    plane.completions.get(0).status().equals("CANCELLED"));
            check("cancelled job publishes nothing", plane.published.isEmpty());
        }
    }

    static void stolenLeaseIsAbandonedWithoutReporting(Path scratch) throws Exception {
        try (FakeControlPlane plane = new FakeControlPlane()) {
            plane.leaseStolen.set(true);
            Path work = Files.createTempDirectory(scratch, "e2e-stolen");
            Path engine = fakeEngine(scratch, "engine-slow2.sh", 60, 0);
            AgentConfig config = engineConfig(plane.baseUrl(), work, engine);

            JobExecutor.Outcome outcome = executor(config, plane)
                    .execute(plane.lease("job-stolen", "lease-stolen", pinned(), 600));

            check("stolen lease yields ABANDONED", outcome == JobExecutor.Outcome.ABANDONED);
            // The decisive assertion: a runner that lost its lease must not write
            // anything, or it would overwrite the newer runner's result.
            check("abandoned job reports nothing", plane.completions.isEmpty());
            check("abandoned job publishes nothing", plane.published.isEmpty());
            check("abandoned job cleans its workspace", !Files.exists(work.resolve("job-stolen")));
        }
    }

    static void drainStopsClaiming(Path scratch) throws Exception {
        try (FakeControlPlane plane = new FakeControlPlane()) {
            Path work = Files.createTempDirectory(scratch, "e2e-drain");
            Path engine = fakeEngine(scratch, "engine-drain.sh", 0, 0);
            AgentConfig config = engineConfig(plane.baseUrl(), work, engine);

            AgentMetrics metrics = new AgentMetrics();
            ControlPlaneClient client = new ControlPlaneClient(config);
            ContainerRuntime containers = new ContainerRuntime(config, new ProcessRunner.Os());
            JobExecutor executorUnderDrain = new JobExecutor(config, client, containers,
                    new ArtifactPublisher(client, metrics), metrics);

            LeasePoller poller = new LeasePoller(
                    config, client, containers, executorUnderDrain, metrics);

            plane.drainRequested.set(true);
            plane.enqueueLease("job-drain", "lease-drain", pinned(), 600);
            poller.pollOnce();

            check("drain flag is observed", poller.draining());
            check("draining agent does not claim", plane.claimCount.get() == 0);
            check("no job ran while draining", poller.runningJobs() == 0);
            poller.shutdown(1);
        }
    }

    static void workspaceAccessIsProvenAtStartup(Path scratch) throws IOException {
        Path work = Files.createTempDirectory(scratch, "probe-ok");
        AgentConfig matching = engineConfigAt(work, Path.of("/usr/bin/podman"),
                WorkspaceAccessProbe.currentUid(), WorkspaceAccessProbe.currentGid());
        check("matching uid passes the workspace probe",
                WorkspaceAccessProbe.verify(matching).usable());

        // A uid the agent cannot chown to must be refused at startup rather than
        // producing a job that succeeds and writes nothing.
        Path work2 = Files.createTempDirectory(scratch, "probe-bad");
        AgentConfig mismatched = engineConfigAt(work2, Path.of("/usr/bin/podman"),
                WorkspaceAccessProbe.currentUid() + 4242, WorkspaceAccessProbe.currentGid() + 4242);
        WorkspaceAccessProbe.Result result = WorkspaceAccessProbe.verify(mismatched);
        boolean canChown = WorkspaceAccessProbe.currentUid() == 0;
        check("mismatched uid is decided explicitly, not by luck",
                canChown ? result.usable() : !result.usable());
        if (!canChown) {
            check("the refusal explains the consequence",
                    result.detail().contains("Permission denied"));
        }
    }

    /**
     * The self-fencing path that a plain 409 does not cover: the control plane
     * stops answering entirely. The agent must stop the container on its own and
     * report nothing, because another runner may already hold the job.
     */
    static void networkPartitionFencesTheJob(Path scratch) throws Exception {
        try (FakeControlPlane plane = new FakeControlPlane()) {
            Path work = Files.createTempDirectory(scratch, "e2e-partition");
            Path engine = fakeEngine(scratch, "engine-partition.sh", 60, 0);
            AgentConfig config = engineConfig(plane.baseUrl(), work, engine);

            // Kill the control plane the moment the job starts running.
            Thread partition = Thread.ofVirtual().start(() -> {
                try {
                    Thread.sleep(1_500);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                plane.partition();
            });

            long started = System.currentTimeMillis();
            JobExecutor.Outcome outcome = executor(config, plane)
                    .execute(plane.lease("job-partition", "lease-partition", pinned(), 600));
            long elapsed = System.currentTimeMillis() - started;
            partition.join();

            check("a partitioned agent abandons its job", outcome == JobExecutor.Outcome.ABANDONED);
            // lease=30s, safety margin=10s, so fencing must happen by ~20s.
            check("fencing happens before the lease expires", elapsed < 30_000);
            check("a partitioned agent reports nothing", plane.completions.isEmpty());
            check("a partitioned agent cleans its workspace",
                    !Files.exists(work.resolve("job-partition")));
        }
    }

    /**
     * The real thing: the agent's own container command, run by real rootless
     * podman, against an already-present digest-pinned image. Skipped only when
     * the caller has not configured the acceptance image or engine.
     */
    static RealContainerStatus realContainerRoundTrip(Path scratch) throws Exception {
        String image = System.getenv("ELMOS_TEST_IMAGE");
        String configuredEngine = System.getenv("ELMOS_TEST_CONTAINER_ENGINE");
        Path podman = resolveTestPodman(
                configuredEngine,
                List.of(Path.of("/usr/bin/podman"), Path.of("/opt/homebrew/bin/podman"),
                        Path.of("/usr/local/bin/podman")));
        boolean imageConfigured = image != null && !image.isBlank();
        boolean engineConfigured = configuredEngine != null && !configuredEngine.isBlank();
        if (!imageConfigured && !engineConfigured) {
            System.out.println("  NOT_RUN real container round trip (set ELMOS_TEST_IMAGE and"
                    + " optionally ELMOS_TEST_CONTAINER_ENGINE)");
            return RealContainerStatus.NOT_RUN;
        }
        if (!imageConfigured || podman == null) {
            throw new IllegalArgumentException(
                    "ELMOS_TEST_IMAGE and a real podman executable are both required");
        }

        requireRootlessPodman(podman);
        check("real podman image exists by exact digest",
                requireLocalPinnedImage(podman, image));

        try (FakeControlPlane plane = new FakeControlPlane()) {
            Path work = Files.createTempDirectory(scratch, "e2e-podman");
            // A rootless runner and its workload intentionally share the same host
            // identity. Forcing uid 65532 here made the test require chown even when
            // the real runner was an ordinary non-root user (for example uid 501 on
            // macOS), so the test failed before podman was ever invoked. Root-run
            // development environments still use the conventional non-root uid.
            int workloadUid = WorkspaceAccessProbe.currentUid();
            int workloadGid = WorkspaceAccessProbe.currentGid();
            if (workloadUid == 0) {
                workloadUid = 65532;
            }
            if (workloadGid == 0) {
                workloadGid = 65532;
            }
            AgentConfig config = new AgentConfig(plane.baseUrl(), "runner-test", "pool-shared",
                    "x".repeat(40), List.of("generation:multi"), List.of(image),
                    2, work, podman.toString(),
                    2, 30, 5, 5, 9999, false, workloadUid, workloadGid);
            check("real container runs as a non-root uid", config.workloadUid() != 0);

            JobExecutor.Outcome outcome = executor(config, plane)
                    .execute(plane.lease("job-podman", "lease-podman", image, 300));

            check("real podman job succeeded", outcome == JobExecutor.Outcome.SUCCEEDED);
            check("real container produced an artifact", plane.published.size() == 1);
            check("real artifact was uploaded", plane.uploads.size() == 1);
            check("real artifact bytes are derived from the exact lease inputs",
                    plane.uploads.size() == 1
                            && new String(plane.uploads.get(0), java.nio.charset.StandardCharsets.UTF_8)
                                    .equals("request={\"targets\":[\"java\"]}\ncheckpoint={}\n"));
            check("real workspace was torn down", !Files.exists(work.resolve("job-podman")));
        }
        return RealContainerStatus.PASSED;
    }

    static boolean realContainerRequired(String value) {
        if (value == null || value.isBlank() || value.equalsIgnoreCase("false")) {
            return false;
        }
        if (value.equalsIgnoreCase("true")) {
            return true;
        }
        throw new IllegalArgumentException(
                "elmos.test.requireRealContainer must be true or false");
    }

    static void realContainerConfigurationFailsClosed(Path scratch) throws IOException {
        Path directory = Files.createTempDirectory(scratch, "podman-resolution");
        Path podman = directory.resolve("podman");
        Files.writeString(podman, "#!/bin/sh\nexit 0\n");
        Files.setPosixFilePermissions(podman, PosixFilePermissions.fromString("rwx------"));
        Path docker = directory.resolve("docker");
        Files.writeString(docker, "#!/bin/sh\nexit 0\n");
        Files.setPosixFilePermissions(docker, PosixFilePermissions.fromString("rwx------"));

        check("explicit real-container engine must resolve to podman",
                resolveTestPodman(podman.toString(), List.of()).equals(podman));
        check("an executable podman candidate is auto-detected",
                resolveTestPodman("", List.of(podman)).equals(podman));
        check("missing podman candidates stay unavailable",
                resolveTestPodman("", List.of(directory.resolve("missing"))) == null);
        check("a relative real-container engine is rejected",
                throwsEngineConfiguration(() -> resolveTestPodman("podman", List.of())));
        check("docker cannot masquerade as the podman acceptance engine",
                throwsEngineConfiguration(() -> resolveTestPodman(docker.toString(), List.of())));

        String rootlessInfo = """
                {"host":{"security":{"rootless":true}},"version":{"Version":"6.1.0"}}
                """;
        String rootfulInfo = """
                {"host":{"security":{"rootless":false}},"version":{"Version":"6.1.0"}}
                """;
        check("podman preflight accepts rootless podman info", isRootlessPodmanInfo(rootlessInfo));
        check("podman preflight rejects rootful podman info", !isRootlessPodmanInfo(rootfulInfo));
        check("podman preflight rejects docker-shaped info",
                !isRootlessPodmanInfo("{\"ServerVersion\":\"29.4.0\"}"));
    }

    static Path resolveTestPodman(String configured, List<Path> candidates) {
        if (configured != null && !configured.isBlank()) {
            Path path = Path.of(configured).normalize();
            if (!path.isAbsolute() || path.getFileName() == null
                    || !path.getFileName().toString().equals("podman")
                    || !Files.isExecutable(path)) {
                throw new IllegalArgumentException(
                        "ELMOS_TEST_CONTAINER_ENGINE must be an absolute executable named podman");
            }
            return path;
        }
        for (Path candidate : candidates) {
            if (candidate.isAbsolute() && candidate.getFileName() != null
                    && candidate.getFileName().toString().equals("podman")
                    && Files.isExecutable(candidate)) {
                return candidate.normalize();
            }
        }
        return null;
    }

    static boolean isRootlessPodmanInfo(String text) {
        try {
            Map<String, Object> info = Json.parseObject(text);
            Map<String, Object> version = Json.object(info, "version");
            Map<String, Object> security = Json.object(Json.object(info, "host"), "security");
            return !Json.string(version, "Version", "").isBlank()
                    && Json.bool(security, "rootless", false);
        } catch (RuntimeException ex) {
            return false;
        }
    }

    private static void requireRootlessPodman(Path podman) {
        ProcessRunner.Result info = new ProcessRunner.Os().run(
                List.of(podman.toString(), "info", "--format", "json"), null, Map.of(), 30);
        if (!info.ok()) {
            throw new IllegalStateException("REAL_PODMAN_PREFLIGHT_FAILED");
        }
        if (!isRootlessPodmanInfo(info.stdout())) {
            throw new IllegalStateException("REAL_ROOTLESS_PODMAN_REQUIRED");
        }
    }

    private static boolean requireLocalPinnedImage(Path podman, String image) {
        ContainerRuntime.validateImage(image);
        ProcessRunner.Result exists = new ProcessRunner.Os().run(
                List.of(podman.toString(), "image", "exists", image), null, Map.of(), 30);
        if (!exists.ok()) {
            throw new IllegalStateException("REAL_PINNED_IMAGE_MUST_EXIST_LOCALLY");
        }
        return true;
    }

    // ---- helpers -----------------------------------------------------------

    private static JobExecutor executor(AgentConfig config, FakeControlPlane plane) {
        AgentMetrics metrics = new AgentMetrics();
        ControlPlaneClient client = new ControlPlaneClient(config);
        return new JobExecutor(config, client,
                new ContainerRuntime(config, new ProcessRunner.Os()),
                new ArtifactPublisher(client, metrics), metrics);
    }

    private static String pinned() {
        return "registry.example.com/elmos/generation@sha256:" + "a".repeat(64);
    }

    private static AgentConfig hostConfig(String baseUrl, Path work, int concurrency) {
        return new AgentConfig(baseUrl, "runner-test", "pool-shared", "x".repeat(40),
                List.of("generation:multi"), List.of(pinned()), concurrency, work, "",
                1, 30, 5, 5, 9999, true,
                WorkspaceAccessProbe.currentUid(), WorkspaceAccessProbe.currentGid());
    }

    private static AgentConfig engineConfigAt(Path work, Path engine, int uid, int gid) {
        return new AgentConfig("https://control.example.com", "runner-test", "pool-shared",
                "x".repeat(40), List.of("generation:multi"), List.of(pinned()),
                2, work, engine.toString(),
                2, 30, 5, 5, 9999, false, uid, gid);
    }

    private static AgentConfig engineConfig(String baseUrl, Path work, Path engine) {
        return new AgentConfig(baseUrl, "runner-test", "pool-shared", "x".repeat(40),
                List.of("generation:multi"), List.of(pinned()), 2, work, engine.toString(),
                2, 30, 5, 5, 9999, false,
                WorkspaceAccessProbe.currentUid(), WorkspaceAccessProbe.currentGid());
    }

    /**
     * A stand-in for podman. It parses the {@code --volume} flags exactly as a real
     * engine would, writes an artifact into the output mount, then sleeps and exits
     * with the requested code.
     */
    private static Path fakeEngine(Path scratch, String name, int sleepSeconds, int exitCode) throws IOException {
        Path script = scratch.resolve(name);
        Files.writeString(script, """
                #!/usr/bin/env bash
                set -euo pipefail
                if [ "${1:-}" = "info" ]; then echo '{"rootless":true}'; exit 0; fi
                if [ "${1:-}" = "image" ] && [ "${2:-}" = "exists" ]; then exit 0; fi
                if [ "${1:-}" = "kill" ] || [ "${1:-}" = "rm" ]; then exit 0; fi
                OUT=""
                for arg in "$@"; do
                  case "$arg" in
                    --volume=*:/elmos/out:rw) OUT="${arg#--volume=}"; OUT="${OUT%%:/elmos/out:rw}" ;;
                  esac
                done
                echo "::elmos stage=building progress=10"
                if [ -n "$OUT" ]; then printf 'generated-project-bytes' > "$OUT/project.zip"; fi
                echo "::elmos stage=packaging progress=90"
                sleep %d
                exit %d
                """.formatted(sleepSeconds, exitCode));
        Files.setPosixFilePermissions(script, PosixFilePermissions.fromString("rwx------"));
        return script;
    }

    private static Map<String, String> with(Map<String, String> base, String key, String value) {
        Map<String, String> copy = new HashMap<>(base);
        copy.put(key, value);
        return copy;
    }

    private static boolean throwsConfig(Map<String, String> env) {
        try {
            AgentConfig.fromEnvironment(env);
            return false;
        } catch (AgentConfig.ConfigException ex) {
            return true;
        }
    }

    private static boolean throwsJson(String text) {
        try {
            Json.parse(text);
            return false;
        } catch (Json.JsonException ex) {
            return true;
        }
    }

    private static boolean throwsImage(String image) {
        try {
            ContainerRuntime.validateImage(image);
            return false;
        } catch (RuntimeException ex) {
            return true;
        }
    }

    private static boolean throwsEngineConfiguration(Runnable action) {
        try {
            action.run();
            return false;
        } catch (IllegalArgumentException ex) {
            return true;
        }
    }

    private static boolean throwsRuntime(Runnable action) {
        try {
            action.run();
            return false;
        } catch (RuntimeException ex) {
            return true;
        }
    }

    private interface IoAction {
        void run() throws IOException;
    }

    private static boolean throwsIo(IoAction action) {
        try {
            action.run();
            return false;
        } catch (IOException ex) {
            return true;
        }
    }

    private static void check(String description, boolean condition) {
        checks++;
        if (condition) {
            System.out.println("  ok   " + description);
        } else {
            System.out.println("  FAIL " + description);
            FAILURES.add(description);
        }
    }
}
