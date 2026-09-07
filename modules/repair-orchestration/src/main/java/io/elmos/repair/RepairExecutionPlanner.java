package io.elmos.repair;

import io.elmos.repair.RepairLoopModels.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Produces a minimum sufficient matrix and pinned, non-interactive command records. */
public final class RepairExecutionPlanner {
    private static final List<Phase> PHASES = List.of(Phase.RESTORE, Phase.BUILD_MODEL, Phase.COMPILE,
            Phase.STATIC_ANALYSIS, Phase.TEST_DISCOVERY, Phase.UNIT_TEST, Phase.CONTRACT_TEST,
            Phase.INTEGRATION_TEST, Phase.STARTUP_TEST, Phase.FULL_REGRESSION);

    public List<MatrixEntry> plan(Request request) {
        List<MatrixEntry> matrix = new ArrayList<>();
        for (ModuleTarget module : request.modules()) {
            for (String platform : module.deploymentPlatforms()) {
                String configuration = module.language() == Language.CSHARP ? "Release" : "default";
                List<CommandRecord> commands = commands(request.targetRepositoryPath(), module);
                String matrixId = RepairLoopIds.id("matrix", request.repairRunId(), module.moduleId(),
                        module.runtimeVersion(), platform, configuration);
                matrix.add(new MatrixEntry(matrixId, module.moduleId(), module.language(),
                        module.runtimeVersion(), platform, configuration, PHASES, commands,
                        "one entry per declared deployment platform; unrelated Cartesian dimensions omitted"));
            }
        }
        return matrix.stream().sorted(java.util.Comparator.comparing(MatrixEntry::matrixId)).toList();
    }

    private List<CommandRecord> commands(Path root, ModuleTarget module) {
        return switch (module.language()) {
            case JAVA -> javaCommands(root, module);
            case PYTHON -> pythonCommands(module);
            case CSHARP -> dotnetCommands(module);
            case TYPESCRIPT, JAVASCRIPT -> nodeCommands(root, module);
        };
    }

    private List<CommandRecord> javaCommands(Path root, ModuleTarget module) {
        String system = module.buildSystem().toLowerCase(Locale.ROOT);
        if (system.contains("gradle")) {
            String executable = Files.isRegularFile(root.resolve("gradlew")) ? "./gradlew" : "gradle";
            return List.of(command(module, Phase.RESTORE, executable, List.of("dependencies"), List.of()),
                    command(module, Phase.BUILD_MODEL, executable, List.of("projects"), List.of()),
                    command(module, Phase.COMPILE, executable, List.of("classes", "testClasses"), List.of()),
                    command(module, Phase.STATIC_ANALYSIS, executable, List.of("check"), List.of("build/reports/**")),
                    command(module, Phase.TEST_DISCOVERY, executable, List.of("test", "--dry-run"), List.of()),
                    command(module, Phase.UNIT_TEST, executable, List.of("test"), List.of("build/test-results/test/*.xml")),
                    command(module, Phase.FULL_REGRESSION, executable, List.of("check"), List.of("build/reports/**")));
        }
        String executable = Files.isRegularFile(root.resolve("mvnw")) ? "./mvnw" : "mvn";
        return List.of(command(module, Phase.RESTORE, executable,
                        List.of("-B", "-DskipTests", "dependency:go-offline"), List.of()),
                command(module, Phase.BUILD_MODEL, executable,
                        List.of("-B", "-DskipTests", "validate"), List.of()),
                command(module, Phase.COMPILE, executable,
                        List.of("-B", "-DskipTests", "test-compile"), List.of()),
                command(module, Phase.STATIC_ANALYSIS, executable,
                        List.of("-B", "-DskipTests", "verify"), List.of("target/site/**")),
                command(module, Phase.TEST_DISCOVERY, "elmos-test-discovery",
                        List.of("--language", "java", "--build-system", "maven", "--output", "reports/test-index.json"),
                        List.of("reports/test-index.json"), "elmos-test-discovery@1"),
                command(module, Phase.UNIT_TEST, executable,
                        List.of("-B", "test"), List.of("target/surefire-reports/TEST-*.xml")),
                command(module, Phase.FULL_REGRESSION, executable,
                        List.of("-B", "verify"), List.of("target/surefire-reports/**", "target/failsafe-reports/**")));
    }

    private List<CommandRecord> pythonCommands(ModuleTarget module) {
        String system = module.buildSystem().toLowerCase(Locale.ROOT);
        boolean uv = system.contains("uv");
        boolean poetry = system.contains("poetry");
        String executable = uv ? "uv" : poetry ? "poetry" : "python";
        List<String> prefix = uv ? List.of() : List.of("-m");
        return List.of(command(module, Phase.RESTORE, executable,
                        uv ? List.of("sync", "--frozen") : poetry ? List.of("install", "--sync", "--no-interaction")
                                : List.of("-m", "pip", "install", "--require-hashes", "-r", "requirements.txt"), List.of()),
                command(module, Phase.BUILD_MODEL, executable,
                        uv ? List.of("run", "pytest", "--collect-only", "-q")
                                : poetry ? List.of("run", "pytest", "--collect-only", "-q")
                                : concat(prefix, "pytest", "--collect-only", "-q"), List.of()),
                command(module, Phase.COMPILE, executable,
                        uv ? List.of("run", "python", "-m", "compileall", "-q", ".")
                                : poetry ? List.of("run", "python", "-m", "compileall", "-q", ".")
                                : concat(prefix, "compileall", "-q", "."), List.of()),
                command(module, Phase.STATIC_ANALYSIS, executable,
                        uv ? List.of("run", "pyright") : poetry ? List.of("run", "mypy", ".")
                                : List.of("-m", "mypy", "."), List.of()),
                command(module, Phase.TEST_DISCOVERY, executable,
                        uv ? List.of("run", "pytest", "--collect-only", "-q")
                                : poetry ? List.of("run", "pytest", "--collect-only", "-q")
                                : concat(prefix, "pytest", "--collect-only", "-q"), List.of()),
                command(module, Phase.UNIT_TEST, executable,
                        uv ? List.of("run", "pytest", "-m", "not integration", "--junitxml=reports/unit.xml")
                                : poetry ? List.of("run", "pytest", "-m", "not integration", "--junitxml=reports/unit.xml")
                                : concat(prefix, "pytest", "-m", "not integration", "--junitxml=reports/unit.xml"),
                        List.of("reports/unit.xml")),
                command(module, Phase.FULL_REGRESSION, executable,
                        uv ? List.of("run", "pytest", "--junitxml=reports/full.xml")
                                : poetry ? List.of("run", "pytest", "--junitxml=reports/full.xml")
                                : concat(prefix, "pytest", "--junitxml=reports/full.xml"), List.of("reports/full.xml")));
    }

    private List<CommandRecord> dotnetCommands(ModuleTarget module) {
        return List.of(command(module, Phase.RESTORE, "dotnet", List.of("restore", "--locked-mode"), List.of()),
                command(module, Phase.BUILD_MODEL, "dotnet", List.of("sln", "list"), List.of()),
                command(module, Phase.COMPILE, "dotnet", List.of("build", "--no-restore", "-c", "Release"), List.of()),
                command(module, Phase.STATIC_ANALYSIS, "dotnet", List.of("build", "--no-restore", "-c", "Release", "-warnaserror"), List.of()),
                command(module, Phase.TEST_DISCOVERY, "dotnet", List.of("test", "--no-build", "--list-tests"), List.of()),
                command(module, Phase.UNIT_TEST, "dotnet", List.of("test", "--no-build", "-c", "Release", "--logger", "trx"), List.of("**/*.trx")),
                command(module, Phase.FULL_REGRESSION, "dotnet", List.of("test", "--no-build", "-c", "Release", "--logger", "trx"), List.of("**/*.trx")));
    }

    private List<CommandRecord> nodeCommands(Path root, ModuleTarget module) {
        String system = module.buildSystem().toLowerCase(Locale.ROOT);
        String packageManager = system.contains("pnpm") || Files.isRegularFile(root.resolve("pnpm-lock.yaml")) ? "pnpm" : "npm";
        List<String> restore = packageManager.equals("pnpm") ? List.of("install", "--frozen-lockfile") : List.of("ci");
        List<String> runBuild = packageManager.equals("pnpm") ? List.of("run", "build") : List.of("run", "build");
        List<String> runTest = packageManager.equals("pnpm") ? List.of("test", "--", "--runInBand") : List.of("test", "--", "--runInBand");
        return List.of(command(module, Phase.RESTORE, packageManager, restore, List.of()),
                command(module, Phase.BUILD_MODEL, packageManager, List.of("run", "--if-present", "build"), List.of()),
                command(module, Phase.COMPILE, packageManager, runBuild, List.of()),
                command(module, Phase.STATIC_ANALYSIS, packageManager, List.of("run", "lint"), List.of()),
                command(module, Phase.TEST_DISCOVERY, packageManager, List.of("test", "--", "--listTests"), List.of()),
                command(module, Phase.UNIT_TEST, packageManager, runTest, List.of("reports/**")),
                command(module, Phase.FULL_REGRESSION, packageManager, runTest, List.of("reports/**")));
    }

    private CommandRecord command(ModuleTarget module, Phase phase, String executable,
                                  List<String> arguments, List<String> reports) {
        return command(module, phase, executable, arguments, reports, module.buildToolVersion());
    }

    private CommandRecord command(ModuleTarget module, Phase phase, String executable,
                                  List<String> arguments, List<String> reports, String toolVersion) {
        String id = RepairLoopIds.id("command", module.moduleId(), module.runtimeVersion(),
                phase, executable, arguments);
        return new CommandRecord(id, phase, ".", executable, arguments, Map.of(),
                timeout(phase), reports, toolVersion);
    }

    private static int timeout(Phase phase) {
        return switch (phase) {
            case RESTORE -> 1200;
            case FULL_REGRESSION, INTEGRATION_TEST -> 3600;
            default -> 1800;
        };
    }

    private static List<String> concat(List<String> prefix, String... values) {
        List<String> result = new ArrayList<>(prefix);
        result.addAll(List.of(values));
        return List.copyOf(result);
    }
}
