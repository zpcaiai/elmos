package io.elmos.cas;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;

/**
 * ELMOS-CAS-041. The exact-rerun hit-rate benchmark, as runnable code rather than a target.
 *
 * <p>The goal in the skill is "at least 95 percent exact rerun Action Cache hit for unchanged
 * inputs". Stating that number is easy; the reason it needs a harness is that the interesting
 * failures are on either side of it:
 *
 * <ul>
 *   <li><b>Under-hitting</b> means some input that did not change is in the key anyway — a
 *       timestamp, an absolute path, a map iteration order. The cache looks correct and delivers
 *       nothing.</li>
 *   <li><b>Over-hitting</b> is worse and a naive benchmark rewards it. A cache that ignores the
 *       toolchain digest scores 100 percent and serves stale binaries. So the harness measures
 *       three separate things and all three have to hold: unchanged reruns hit, a single changed
 *       file invalidates <em>only</em> what depends on it, and a changed toolchain invalidates
 *       everything.</li>
 * </ul>
 *
 * <p>The workload is synthetic and the "execution" is simulated: this measures the cache's
 * key and invalidation behaviour at scale, not a real build. A production number needs real
 * repositories, and this harness is what that run should be compared against.
 */
public final class ActionCacheBenchmark {

    public record Scenario(String name, double hitRate, int hits, int misses, List<String> missedModules) {
    }

    public record Report(int modules,
                         int filesPerModule,
                         int actions,
                         List<Scenario> scenarios,
                         long bytesAvoided,
                         long computeMillisAvoided,
                         long wallMillisAvoided,
                         long benchmarkWallMillis,
                         Map<String, Long> outcomeReasons) {

        public double exactRerunHitRate() {
            return scenarios.stream().filter(scenario -> scenario.name().equals("unchanged-rerun"))
                    .mapToDouble(Scenario::hitRate).findFirst().orElse(0);
        }

        public String toMarkdown() {
            StringBuilder markdown = new StringBuilder("# ELMOS-CAS-041 action cache benchmark\n\n");
            markdown.append("Synthetic workload: ").append(modules).append(" modules x ")
                    .append(filesPerModule).append(" files, ").append(actions).append(" actions per round.\n\n");
            markdown.append("| scenario | hit rate | hits | misses | expectation |\n");
            markdown.append("|---|---:|---:|---:|---|\n");
            for (Scenario scenario : scenarios) {
                markdown.append("| `").append(scenario.name()).append("` | ")
                        .append(String.format("%.4f", scenario.hitRate())).append(" | ")
                        .append(scenario.hits()).append(" | ").append(scenario.misses()).append(" | ")
                        .append(expectationOf(scenario.name())).append(" |\n");
            }
            markdown.append("\n- bytes avoided: ").append(bytesAvoided());
            markdown.append("\n- compute avoided (ms): ").append(computeMillisAvoided());
            markdown.append("\n- wall-clock avoided (ms): ").append(wallMillisAvoided());
            markdown.append("\n- benchmark wall-clock (ms): ").append(benchmarkWallMillis());
            markdown.append("\n\n## Outcome reasons\n\n");
            outcomeReasons.forEach((reason, count) ->
                    markdown.append("- `").append(reason).append("`: ").append(count).append('\n'));
            markdown.append("\n> Simulated execution on a synthetic tree. This measures action-key and\n");
            markdown.append("> invalidation behaviour, not build times on a real repository.\n");
            return markdown.toString();
        }

        private static String expectationOf(String scenario) {
            return switch (scenario) {
                case "unchanged-rerun" -> "= 1.0000 (goal >= 0.95)";
                case "one-file-changed" -> "exactly one module misses";
                case "toolchain-changed" -> "= 0.0000, every entry invalidated";
                case "permission-downgraded" -> "= 0.0000, every read denied";
                default -> "";
            };
        }
    }

    private static final String IMAGE_A = "registry.internal/elmos/java21@sha256:" + "a".repeat(64);
    private static final String IMAGE_B = "registry.internal/elmos/java21@sha256:" + "b".repeat(64);

    private final int modules;
    private final int filesPerModule;
    private final AtomicLong clock = new AtomicLong(1_800_000_000_000L);
    private final InMemoryCasStore store = new InMemoryCasStore("bench");
    private final CasMetrics metrics = new CasMetrics();
    private final ActionCache cache;

    public ActionCacheBenchmark(int modules, int filesPerModule) {
        CasText.requirePositive(modules, "modules");
        CasText.requirePositive(filesPerModule, "filesPerModule");
        this.modules = modules;
        this.filesPerModule = filesPerModule;
        this.cache = new ActionCache(store, new CasAccessPolicy(), ActionCache.FailureCachePolicy.none(),
                ActionCache.SampleRecomputePolicy.disabled(), clock::get, metrics);
    }

    public Report run() {
        long started = System.nanoTime();
        Map<String, MerkleTree.CanonicalTree> trees = buildTrees(-1);
        List<Scenario> scenarios = new ArrayList<>();

        populate(trees, IMAGE_A);
        scenarios.add(measure("unchanged-rerun", trees, IMAGE_A, reader(Set.of("repo:read"))));

        Map<String, MerkleTree.CanonicalTree> edited = buildTrees(modules / 2);
        scenarios.add(measure("one-file-changed", edited, IMAGE_A, reader(Set.of("repo:read"))));

        scenarios.add(measure("toolchain-changed", trees, IMAGE_B, reader(Set.of("repo:read"))));

        scenarios.add(measure("permission-downgraded", trees, IMAGE_A, reader(Set.of())));

        long wallMillis = (System.nanoTime() - started) / 1_000_000;
        return new Report(modules, filesPerModule, modules, scenarios, metrics.bytesAvoided(),
                metrics.computeMillisAvoided(), metrics.wallMillisAvoided(), wallMillis, metrics.explain());
    }

    /** @param editedModule index whose last file is perturbed, or -1 for the pristine tree */
    private Map<String, MerkleTree.CanonicalTree> buildTrees(int editedModule) {
        Map<String, MerkleTree.CanonicalTree> trees = new LinkedHashMap<>();
        for (int module = 0; module < modules; module++) {
            List<MerkleTree.FileNode> files = new ArrayList<>();
            for (int file = 0; file < filesPerModule; file++) {
                String content = "module-" + module + "/file-" + file;
                if (module == editedModule && file == filesPerModule - 1) {
                    content = content + "// one changed line";
                }
                CasDigest digest = CasDigest.ofUtf8(content);
                store.put(digest, content.getBytes(StandardCharsets.UTF_8));
                files.add(new MerkleTree.FileNode("src/main/java/M" + file + ".java", digest, false));
            }
            MerkleTree.CanonicalTree tree = MerkleTree.canonicalize(files, List.of());
            tree.treeObjects().forEach(object -> store.put(object.digest(), object.bytes()));
            trees.put("module-" + module, tree);
        }
        return trees;
    }

    private void populate(Map<String, MerkleTree.CanonicalTree> trees, String image) {
        var writer = new ActionCache.WriterIdentity("bench-runner", "elmos.internal", "node-bench", true);
        trees.forEach((module, tree) -> {
            ActionKey key = actionKey(module, tree, image);
            String output = "output-of-" + module;
            CasDigest manifest = CasDigest.ofUtf8(output);
            store.put(manifest, output.getBytes(StandardCharsets.UTF_8));
            ActionResultRecord result = ActionResultRecord.succeeded("act-" + module, "receipt-" + module,
                    manifest, CasDigest.ofUtf8("provenance-" + module),
                    new ActionResultRecord.ResourceUsage(42, 1024, 4_000_000, 1_000_000, 0, 61),
                    "2026-08-19T06:30:00Z", "2026-08-19T06:31:01Z");
            cache.put(key, result, producer(Set.of("repo:read"), image), writer,
                    ActionCache.RiskTier.STANDARD, Optional.empty());
        });
    }

    private Scenario measure(String name, Map<String, MerkleTree.CanonicalTree> trees, String image,
                             CasAccessPolicy.ReaderContext reader) {
        int hits = 0;
        int misses = 0;
        List<String> missed = new ArrayList<>();
        for (Map.Entry<String, MerkleTree.CanonicalTree> module : trees.entrySet()) {
            ActionKey key = actionKey(module.getKey(), module.getValue(), image);
            ActionCache.Lookup lookup = cache.get(key, reader, false);
            if (lookup.outcome() == ActionCache.CacheOutcome.HIT) {
                hits++;
            } else {
                misses++;
                missed.add(module.getKey());
            }
        }
        return new Scenario(name, (double) hits / (hits + misses), hits, misses, List.copyOf(missed));
    }

    private ActionKey actionKey(String module, MerkleTree.CanonicalTree tree, String image) {
        return new ActionKeyBuilder()
                .tenant("tenant-bench", "project-bench")
                .sourceTree(tree.rootDigest())
                .dependencyGraph(CasDigest.ofUtf8("deps"))
                .adapter("java-adapter", CasDigest.ofUtf8("adapter"))
                .irSchemaVersion("ir-3")
                .rulePacks(List.of(new ActionKeyBuilder.RulePackRef("spring-boot-3", CasDigest.ofUtf8("rules"))))
                .toolchainImage(image)
                .targetPlatform("linux/arm64")
                .buildOptions(Map.of("profile", "release", "module", module))
                .command(List.of("./mvnw", "-q", "verify"))
                .workingDirectory("/workspace/source/" + module)
                .declaredOutputs(List.of("target"))
                .prompt(Optional.empty())
                .model(Optional.empty())
                .policy(CasDigest.ofUtf8("policy"))
                .permissionScope(Set.of("repo:read"))
                .sandbox("S2", CasDigest.ofUtf8("sandbox"))
                .dataResidency("eu-west")
                .environmentContract(ActionKeyBuilder.EnvironmentContract.of("SOURCE_DATE_EPOCH"))
                .environment(Map.of("SOURCE_DATE_EPOCH", "1787121000"))
                .build();
    }

    private static CasAccessPolicy.ProducerContext producer(Set<String> scope, String image) {
        return new CasAccessPolicy.ProducerContext("tenant-bench", "project-bench", scope, "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, CasObjectModel.Sensitivity.GENERATED_OUTPUT, image,
                Optional.of(CasDigest.ofUtf8("provenance")));
    }

    private static CasAccessPolicy.ReaderContext reader(Set<String> scope) {
        return new CasAccessPolicy.ReaderContext("tenant-bench", scope, "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, false);
    }

    public static void main(String[] arguments) throws Exception {
        int modules = arguments.length > 0 ? Integer.parseInt(arguments[0]) : 200;
        int filesPerModule = arguments.length > 1 ? Integer.parseInt(arguments[1]) : 25;
        Report report = new ActionCacheBenchmark(modules, filesPerModule).run();
        System.out.println(report.toMarkdown());
        if (arguments.length > 2) {
            Files.writeString(Path.of(arguments[2]), report.toMarkdown());
        }
        if (report.exactRerunHitRate() < 0.95) {
            System.err.println("FAIL: exact rerun hit rate " + report.exactRerunHitRate() + " below 0.95");
            System.exit(1);
        }
    }
}
