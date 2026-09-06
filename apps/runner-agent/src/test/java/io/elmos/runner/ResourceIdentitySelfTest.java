package io.elmos.runner;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/** Real filesystem ownership/locking plus a stateful container-engine boundary. */
public final class ResourceIdentitySelfTest {
    private ResourceIdentitySelfTest() { }

    public static void main(String[] args) throws Exception {
        if (args.length == 2 && args[0].equals("--sweep")) {
            System.out.println(JobWorkspace.sweepOrphans(Path.of(args[1])));
            return;
        }
        if (args.length == 2 && args[0].equals("--leave-orphan")) {
            // Deliberately omit close: JVM exit releases the OS lock, retaining
            // an exact marker so a later trusted startup can reclaim it.
            workspace(Path.of(args[1]), lease("lease-orphan", 1, "translate-pipeline-v1"));
            return;
        }
        if (args.length == 2 && args[0].equals("--leave-pending")) {
            var lease = lease("lease-pending", 1, "translate-pipeline-v1");
            var workspace = workspace(Path.of(args[1]), lease);
            workspace.recordContainerIntent("elmos-" + "c".repeat(48), JobWorkspace.leaseIdentity(lease));
            // Model a daemon whose lifetime outlasts this JVM. No claim that a
            // real provider container was launched is made by this fixture.
            return;
        }
        Path root = Files.createTempDirectory("elmos-resource-identity-");
        try {
            workspaceAttemptsAreDisjoint(root.resolve("workspaces"));
            closeRefusesReplacement(root.resolve("replacement"));
            containerAttemptsAndPhasesAreDisjoint(root.resolve("containers"));
            pendingIntentSurvivesJvm(root.resolve("pending"));
            unknownCleanupFencesAdmission(root.resolve("unknown"));
            unknownCleanupCannotPublish(root.resolve("unknown-publication"), false);
            unknownCleanupCannotPublish(root.resolve("unknown-spawn"), true);
        } finally {
            JobWorkspace.deleteRecursively(root);
        }
        System.out.println("RUNNER RESOURCE IDENTITY SELF TEST PASSED");
    }

    private static ControlPlaneClient.Lease lease(String leaseId, int attempt, String phase) {
        return new ControlPlaneClient.Lease("job-shared", leaseId, "never-persist-this-token", "TRANSLATION", phase,
                "registry.example.test/translation@sha256:" + "a".repeat(64), 600, 2000, 2048, attempt,
                Map.of(), Map.of());
    }

    private static JobWorkspace workspace(Path root, ControlPlaneClient.Lease lease) throws IOException {
        return JobWorkspace.create(root, lease, WorkspaceAccessProbe.currentUid(), WorkspaceAccessProbe.currentGid());
    }

    private static void workspaceAttemptsAreDisjoint(Path root) throws Exception {
        var oldLease = lease("lease-old", 1, "translate-pipeline-v1");
        var newLease = lease("lease-new", 2, "translate-pipeline-v1");
        JobWorkspace old = workspace(root, oldLease);
        Path legacy = Files.createDirectory(root.resolve("unmarked-legacy"));
        Path invalidMarker = Files.createDirectory(root.resolve("invalid-marker"));
        Files.writeString(invalidMarker.resolve(".elmos-workspace-owner"), "x".repeat(36));
        try (JobWorkspace newer = workspace(root, newLease);
             JobWorkspace changedAttempt = workspace(root, lease("lease-old", 2, "translate-pipeline-v1"))) {
            require(!old.root().equals(newer.root()) && !old.root().equals(changedAttempt.root()), "lease/attempt collision");
            require(!old.root().toString().contains(oldLease.leaseToken()), "token leaked into resource name");
            for (ControlPlaneClient.Lease invalid : List.of(
                    lease("", 1, "translate-pipeline-v1"), lease("lease-invalid", 0, "translate-pipeline-v1"))) {
                try {
                    workspace(root, invalid);
                    throw new AssertionError("invalid lease identity accepted");
                } catch (IllegalArgumentException expected) {
                    require(expected.getMessage().equals("LEASE_RESOURCE_IDENTITY_INVALID"), "wrong identity rejection");
                }
            }
            Path survivor = newer.out().resolve("must-survive");
            Files.writeString(survivor, "new lease output");
            try {
                workspace(root, oldLease);
                throw new AssertionError("duplicate active lease reused workspace");
            } catch (IOException expected) {
                require(expected.getMessage().equals("JOB_WORKSPACE_ALREADY_OWNED"), "wrong duplicate failure");
            }
            require(JobWorkspace.sweepOrphans(root) == 0, "sweeper removed active resources");
            String classPath = Path.of(ResourceIdentitySelfTest.class.getProtectionDomain().getCodeSource().getLocation().toURI())
                    + java.io.File.pathSeparator
                    + Path.of(JobWorkspace.class.getProtectionDomain().getCodeSource().getLocation().toURI());
            Process probe = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                    "-XX:ActiveProcessorCount=2", "-Xmx64m", "-cp", classPath, ResourceIdentitySelfTest.class.getName(),
                    "--sweep", root.toString()).redirectErrorStream(true).start();
            try {
                require(probe.waitFor(60, TimeUnit.SECONDS), "cross-process sweep probe timed out");
                String output = new String(probe.getInputStream().readNBytes(4097), java.nio.charset.StandardCharsets.UTF_8);
                require(probe.exitValue() == 0 && output.strip().equals("0"), "cross-process lock failed: " + output);
            } finally {
                if (probe.isAlive()) probe.destroyForcibly();
            }
            Process orphan = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                    "-XX:ActiveProcessorCount=2", "-Xmx64m", "-cp", classPath,
                    ResourceIdentitySelfTest.class.getName(), "--leave-orphan", root.toString()).start();
            try {
                require(orphan.waitFor(60, TimeUnit.SECONDS) && orphan.exitValue() == 0, "orphan fixture failed");
            } finally {
                if (orphan.isAlive()) orphan.destroyForcibly();
            }
            require(JobWorkspace.sweepOrphans(root) == 1, "orphan reclamation affected active leases");
            require(Files.isDirectory(legacy) && Files.isDirectory(invalidMarker), "unknown ownership was deleted");
            old.close();
            old.close();
            require(Files.readString(survivor).equals("new lease output"), "stale close deleted new lease");
            require(!Files.exists(old.root()), "owned old workspace not removed");
        } finally {
            old.close();
        }
    }

    private static void closeRefusesReplacement(Path root) throws Exception {
        JobWorkspace old = workspace(root, lease("lease-replaced", 1, "translate-pipeline-v1"));
        Path original = old.root();
        Path moved = original.resolveSibling("moved-owned-directory");
        Files.move(original, moved);
        Files.createDirectory(original);
        Files.copy(moved.resolve(".elmos-workspace-owner"), original.resolve(".elmos-workspace-owner"));
        Path survivor = original.resolve("new-owner");
        Files.writeString(survivor, "different inode");
        old.close();
        require(Files.exists(survivor), "stale inode cleanup deleted replacement");
    }

    private static void containerAttemptsAndPhasesAreDisjoint(Path root) throws Exception {
        var config = new AgentConfig("https://control.example.test", "runner-test", "pool-shared", "x".repeat(40),
                List.of("translation:multi"), 3, root, "/fixture/container-engine", 2, 30, 5, 5, 9999, false,
                WorkspaceAccessProbe.currentUid(), WorkspaceAccessProbe.currentGid());
        var engine = new StatefulEngine();
        var runtime = new ContainerRuntime(config, engine);
        var oldLease = lease("lease-old", 1, "translate-pipeline-v1");
        var newLease = lease("lease-new", 2, "translate-pipeline-v1");
        try (JobWorkspace oldWork = workspace(root, oldLease); JobWorkspace newWork = workspace(root, newLease)) {
            var old = runtime.start(oldLease, oldWork, ignored -> { });
            var newer = runtime.start(newLease, newWork, ignored -> { });
            var preflight = runtime.startTranslationPreflight(newLease, newWork);
            int starts = engine.starts.size();
            try {
                runtime.startTranslationPreflight(newLease, newWork);
                throw new AssertionError("unbounded owned container admission");
            } catch (IllegalStateException expected) {
                require(expected.getMessage().equals("RUNNER_CONTAINER_CAPACITY_EXCEEDED"), "wrong capacity failure");
            }
            require(engine.starts.size() == starts, "over-capacity launch reached engine");
            require(!old.containerName().equals(newer.containerName())
                    && !newer.containerName().equals(preflight.containerName()), "container lease/phase collision");
            String oldId = engine.containers.get(old.containerName()).id();
            runtime.stop(old, 1);
            require(engine.containers.containsKey(newer.containerName()) && engine.containers.containsKey(preflight.containerName()),
                    "old stop removed a new lease/phase");
            require(engine.destructiveTargets.equals(List.of(oldId, oldId)), "cleanup targeted a mutable name");
            int commands = engine.commands.size();
            runtime.forceRemove(old.containerName());
            runtime.forceRemove("elmos-unowned");
            require(engine.commands.size() == commands, "unknown/stale cleanup executed an engine command");

            var original = engine.containers.get(newer.containerName());
            engine.containers.put(newer.containerName(), new Container(original.id(), Map.of()));
            int destructive = engine.destructiveTargets.size();
            try {
                runtime.forceRemove(newer.containerName());
                throw new AssertionError("foreign labels accepted");
            } catch (IllegalStateException expected) {
                require(expected.getMessage().equals("RUNNER_CONTAINER_CLEANUP_UNVERIFIED")
                        && expected.getCause().getMessage().equals("CONTAINER_CLEANUP_IDENTITY_MISMATCH"), "wrong ownership failure");
            }
            require(engine.destructiveTargets.size() == destructive, "foreign container was signalled");
            engine.containers.put(newer.containerName(), original);
            // Rebind the mutable name immediately after inspect. Only the old
            // immutable ID may be killed; the replacement must survive.
            engine.rebindAfterInspect = newer.containerName();
            runtime.forceRemove(newer.containerName());
            require(engine.containers.get(newer.containerName()).id().equals("b".repeat(64)), "name race killed replacement");
            runtime.forceRemove(preflight.containerName());
            require(engine.containers.size() == 1, "owned phase cleanup incomplete");
            require(runtime.isFenced(), "unknown cleanup fence was not sticky");
            require(!JobWorkspace.hasPendingContainerIntents(root), "verified cleanup left pending intent");
            for (List<String> command : engine.starts) {
                for (String flag : List.of("--network=none", "--read-only", "--cap-drop=ALL",
                        "--security-opt=no-new-privileges", "--pids-limit=512", "--memory=2048m", "--memory-swap=2048m")) {
                    require(command.contains(flag), "sandbox flag removed: " + flag);
                }
                require(command.stream().noneMatch(value -> value.contains("never-persist-this-token")), "lease token exposed");
                require(!command.contains("--rm"), "auto-remove erased container cleanup identity");
            }
        }
    }

    private static AgentConfig config(Path root, String url) {
        return new AgentConfig(url, "runner-test", "pool-shared", "x".repeat(40), List.of("translation:multi"),
                2, root, "/fixture/container-engine", 2, 30, 5, 5, 9999, false,
                WorkspaceAccessProbe.currentUid(), WorkspaceAccessProbe.currentGid());
    }

    private static void pendingIntentSurvivesJvm(Path root) throws Exception {
        String classPath = Path.of(ResourceIdentitySelfTest.class.getProtectionDomain().getCodeSource().getLocation().toURI())
                + java.io.File.pathSeparator + Path.of(JobWorkspace.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        Process child = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-XX:ActiveProcessorCount=2", "-Xmx64m", "-cp", classPath, ResourceIdentitySelfTest.class.getName(),
                "--leave-pending", root.toString()).inheritIO().start();
        try {
            require(child.waitFor(60, TimeUnit.SECONDS) && child.exitValue() == 0, "pending fixture failed");
        } finally {
            if (child.isAlive()) child.destroyForcibly();
        }
        Path survivor = root.resolve("lease-" + JobWorkspace.leaseIdentity(lease("lease-pending", 1, "translate-pipeline-v1")));
        require(JobWorkspace.hasPendingContainerIntents(root), "JVM exit erased daemon intent");
        require(JobWorkspace.sweepOrphans(root) == 0 && Files.isDirectory(survivor), "sweep inferred container death from JVM exit");
        try (var plane = new FakeControlPlane()) {
            var engine = new StatefulEngine();
            var cfg = config(root, plane.baseUrl());
            var runtime = new ContainerRuntime(cfg, engine);
            require(runtime.isFenced(), "restart ignored pending daemon intent");
            assertFencedAdmission(cfg, runtime, plane, engine);
        }
    }

    private static void unknownCleanupFencesAdmission(Path root) throws Exception {
        try (var plane = new FakeControlPlane()) {
            var cfg = config(root, plane.baseUrl());
            var engine = new StatefulEngine();
            var runtime = new ContainerRuntime(cfg, engine);
            var lease = lease("lease-unknown", 1, "translate-pipeline-v1");
            JobWorkspace workspace = workspace(root, lease);
            var execution = runtime.start(lease, workspace, ignored -> { });
            engine.containers.clear(); // inspect unavailable: not proof a pending daemon create is gone
            try {
                runtime.forceRemove(execution.containerName());
                throw new AssertionError("missing ID accepted as termination proof");
            } catch (IllegalStateException expected) {
                require(expected.getMessage().equals("RUNNER_CONTAINER_CLEANUP_UNVERIFIED"), "wrong unknown failure");
            }
            require(engine.destructiveTargets.isEmpty(), "unknown container target was signalled");
            workspace.close();
            require(Files.isDirectory(workspace.root()) && JobWorkspace.hasPendingContainerIntents(root), "close erased pending workspace");
            require(JobWorkspace.sweepOrphans(root) == 0, "sweep erased pending workspace");
            assertFencedAdmission(cfg, runtime, plane, engine);
        }
    }

    private static void assertFencedAdmission(AgentConfig cfg, ContainerRuntime runtime,
                                             FakeControlPlane plane, StatefulEngine engine) throws Exception {
        var next = lease("lease-next", 2, "translate-pipeline-v1");
        try (JobWorkspace workspace = workspace(cfg.workRoot(), next)) {
            int starts = engine.starts.size();
            try {
                runtime.start(next, workspace, ignored -> { });
                throw new AssertionError("fenced runtime launched a workload");
            } catch (IllegalStateException expected) {
                require(expected.getMessage().equals("RUNNER_CONTAINER_RECONCILIATION_REQUIRED"), "wrong fenced failure");
            }
            require(engine.starts.size() == starts, "fenced launch reached engine");
        }
        var metrics = new AgentMetrics();
        var client = new ControlPlaneClient(cfg);
        var executor = new JobExecutor(cfg, client, runtime, new ArtifactPublisher(client, metrics), metrics);
        require(executor.execute(next) == JobExecutor.Outcome.ABANDONED && plane.completions.isEmpty(), "fence became business failure");
        try (var poller = new LeasePoller(cfg, client, executor, metrics)) {
            poller.pollOnce();
            require(poller.draining() && plane.claimCount.get() == 0 && poller.runningJobs() == 0, "fenced node claimed new jobs");
        }
    }

    private static void unknownCleanupCannotPublish(Path root, boolean failStart) throws Exception {
        try (var plane = new FakeControlPlane()) {
            var cfg = config(root, plane.baseUrl());
            var engine = new StatefulEngine();
            engine.exitImmediately = true;
            engine.inspectUnavailable = true;
            engine.failStart = failStart;
            var runtime = new ContainerRuntime(cfg, engine);
            var client = new ControlPlaneClient(cfg);
            var metrics = new AgentMetrics();
            var lease = plane.lease("job-unknown-output", "lease-unknown-output",
                    "registry.example.test/job@sha256:" + "a".repeat(64), 600);
            var outcome = new JobExecutor(cfg, client, runtime, new ArtifactPublisher(client, metrics), metrics).execute(lease);
            require(outcome == JobExecutor.Outcome.ABANDONED, "unknown cleanup became terminal business result");
            require(plane.uploads.isEmpty() && plane.published.isEmpty() && plane.completions.isEmpty(),
                    "unreconciled daemon output was published/reported");
            require(runtime.isFenced() && JobWorkspace.hasPendingContainerIntents(root), "unknown daemon intent lost");
            Path retained = root.resolve("lease-" + JobWorkspace.leaseIdentity(lease));
            require(Files.isDirectory(retained) && JobWorkspace.sweepOrphans(root) == 0, "unknown workspace was erased");
            // finally must release the host lock even when cleanup is unknown.
            try (var marker = java.nio.channels.FileChannel.open(retained.resolve(".elmos-workspace-owner"),
                    java.nio.file.StandardOpenOption.READ, java.nio.file.StandardOpenOption.WRITE);
                 var lock = marker.tryLock()) {
                require(lock != null, "unknown cleanup leaked workspace ownership lock");
            }
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private record Container(String id, Map<String, String> labels) { }

    private static final class StatefulEngine implements ProcessRunner {
        final Map<String, Container> containers = new LinkedHashMap<>();
        final List<List<String>> commands = new ArrayList<>();
        final List<List<String>> starts = new ArrayList<>();
        final List<String> destructiveTargets = new ArrayList<>();
        String rebindAfterInspect;
        boolean exitImmediately;
        boolean inspectUnavailable;
        boolean failStart;

        @Override
        public Result run(List<String> command, Path cwd, Map<String, String> environment, long timeout) {
            commands.add(List.copyOf(command));
            String operation = command.get(1);
            String target = command.get(command.size() - 1);
            if (operation.equals("inspect")) {
                if (inspectUnavailable) return new Result(1, "", "daemon unavailable", false);
                Container value = containers.get(target);
                if (value == null) return new Result(1, "", "no such container", false);
                String payload = Json.write(List.of(Map.of("Id", value.id(), "Name", "/" + target,
                        "Config", Map.of("Labels", value.labels()))));
                if (target.equals(rebindAfterInspect)) {
                    containers.put(target, new Container("b".repeat(64), Map.of()));
                    rebindAfterInspect = null;
                }
                return new Result(0, payload, "", false);
            }
            if (operation.equals("kill") || operation.equals("rm")) {
                require(target.matches("[0-9a-f]{64}"), "mutable destructive target");
                destructiveTargets.add(target);
                if (operation.equals("rm")) containers.entrySet().removeIf(entry -> entry.getValue().id().equals(target));
                return new Result(0, "", "", false);
            }
            if (operation.equals("ps")) {
                String filter = command.get(command.indexOf("--filter") + 1);
                var matches = containers.entrySet().stream().filter(entry -> filter.startsWith("id=")
                        ? entry.getValue().id().equals(filter.substring(3)) : entry.getKey().matches(filter.substring(5)))
                        .map(entry -> entry.getValue().id()).toList();
                return new Result(0, String.join("\n", matches), "", false);
            }
            throw new AssertionError("unexpected command: " + command);
        }

        @Override
        public Handle start(List<String> command, Path cwd, Map<String, String> environment, Consumer<String> onLine) {
            starts.add(List.copyOf(command));
            if (failStart) throw new IllegalStateException("engine client spawn outcome unknown");
            String name = command.get(command.indexOf("--name") + 1);
            Map<String, String> labels = new LinkedHashMap<>();
            for (String item : command) if (item.startsWith("--label=")) {
                String[] pair = item.substring("--label=".length()).split("=", 2);
                labels.put(pair[0], pair[1]);
            }
            containers.put(name, new Container(JobWorkspace.identityHash(name), labels));
            if (exitImmediately) {
                try { Files.writeString(cwd.resolve("out/project.zip"), "untrusted-until-daemon-confirmed-gone"); }
                catch (IOException error) { throw new IllegalStateException(error); }
            }
            return new Handle() {
                private boolean alive = !exitImmediately;
                public boolean isAlive() { return alive; }
                public void terminate() { alive = false; }
                public void kill() { alive = false; }
                public Integer waitFor(long timeout, TimeUnit unit) { return alive ? null : 0; }
            };
        }
    }
}
