package io.elmos.semantic;

import io.elmos.intake.IntakeModels.BuildProject;
import io.elmos.intake.IntakeModels.FileEntry;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static io.elmos.semantic.PspModels.*;

public interface SemanticAdapter {
    AdapterDescriptor descriptor();
    AdapterResult analyze(AdapterRequest request);

    record AdapterRequest(Path repositoryRoot, String snapshotId, String semanticRunId,
                          BuildProject project, List<FileEntry> files, AnalysisProfile profile,
                          ResourceBudget budget, Map<String, String> configuration) {
        public AdapterRequest { files = List.copyOf(files); configuration = Map.copyOf(configuration); }
    }
    record AdapterResult(AdapterDescriptor descriptor, List<EntityEnvelope> entities,
                         List<String> invalidationKeys, boolean partial) {
        public AdapterResult { entities = List.copyOf(entities); invalidationKeys = List.copyOf(invalidationKeys); }
    }

    /** Implemented by the isolated engine/workspace boundary, never by the control plane. */
    @FunctionalInterface
    interface NativeAnalyzerPort { AdapterResult analyze(AdapterDescriptor descriptor, AdapterRequest request); }
}
