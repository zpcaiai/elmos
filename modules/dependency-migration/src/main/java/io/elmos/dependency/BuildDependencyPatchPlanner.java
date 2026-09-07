package io.elmos.dependency;

import io.elmos.intake.IntakeModels;
import io.elmos.skeleton.SkeletonModels;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static io.elmos.dependency.DependencyMigrationModels.*;

final class BuildDependencyPatchPlanner {
    List<BuildPatch> plan(List<Decision> decisions, Request request) {
        Map<String,List<Decision>> byModule = new LinkedHashMap<>();
        decisions.stream().filter(Decision::automatic).filter(decision -> decision.targetModuleId()!=null)
                .forEach(decision -> byModule.computeIfAbsent(decision.targetModuleId(), ignored -> new ArrayList<>()).add(decision));
        return byModule.entrySet().stream().sorted(Map.Entry.comparingByKey()).map(entry -> {
            String module = entry.getKey();
            List<PatchOperation> operations = entry.getValue().stream().sorted(Comparator.comparing(Decision::dependencyId)).map(decision -> {
                if (decision.strategy()==Strategy.REMOVE) return new PatchOperation("remove", decision.sourceCoordinate(), decision.sourceVersion(), "resolved", "complete API-use analysis proved dependency unused");
                if (decision.strategy()==Strategy.TARGET_STANDARD_LIBRARY) return new PatchOperation("no-package", decision.selectedCandidate().coordinate(), decision.selectedCandidate().version(), "runtime", "target standard library mapping");
                Candidate candidate = decision.selectedCandidate();
                return new PatchOperation("add", candidate.coordinate(), candidate.version(), "runtime", "semantic dependency decision "+decision.decisionId());
            }).toList();
            String buildTool = targetBuildTool(module, request);
            List<String> obligations = new ArrayList<>();
            if (buildTool == null) obligations.add("target module has no declared build tool");
            return new BuildPatch(DependencyMigrationIds.id("build-patch", module, operations), module, buildTool,
                    operations, "regenerate with the target package manager; never edit lockfiles by hand",
                    false, expectedFiles(buildTool), obligations);
        }).toList();
    }

    private String targetBuildTool(String module, Request request) {
        if (request.targetProfile()!=null && request.targetProfile().preferredBuildTool()!=null && !request.targetProfile().preferredBuildTool().isBlank()) return request.targetProfile().preferredBuildTool();
        return request.buildModel().projects().stream().filter(project -> module.equals(request.projectToTargetModule().get(project.projectId())))
                .map(IntakeModels.BuildProject::buildTool).filter(value -> value!=null && !value.isBlank()).findFirst().orElse(null);
    }
    private List<String> expectedFiles(String buildTool) {
        if (buildTool == null) return List.of();
        return switch (buildTool.toLowerCase()) {
            case "maven" -> List.of("pom.xml");
            case "gradle" -> List.of("build.gradle", "gradle.lockfile");
            case "npm", "pnpm", "yarn" -> List.of("package.json", "package-manager lockfile");
            case "pip", "poetry", "uv" -> List.of("pyproject.toml", "resolved lockfile");
            case "dotnet", "nuget" -> List.of("project file", "packages.lock.json");
            default -> List.of("target build manifest", "target lockfile");
        };
    }
}
