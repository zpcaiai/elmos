package io.elmos.health;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

record BuildInventory(HealthModels.BuildSystem buildSystem,
                      List<HealthModels.Module> modules,
                      List<HealthModels.Dependency> dependencies,
                      Map<String, String> properties,
                      List<Path> javaFiles,
                      List<Path> testFiles,
                      List<Path> buildFiles,
                      List<HealthModels.Finding> findings) {
    BuildInventory {
        modules = List.copyOf(modules); dependencies = List.copyOf(dependencies);
        properties = Map.copyOf(properties); javaFiles = List.copyOf(javaFiles);
        testFiles = List.copyOf(testFiles); buildFiles = List.copyOf(buildFiles);
        findings = List.copyOf(findings);
    }
}
