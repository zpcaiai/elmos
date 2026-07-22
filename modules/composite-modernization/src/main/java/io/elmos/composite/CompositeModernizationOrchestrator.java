package io.elmos.composite;

import java.util.List;

import static io.elmos.composite.CompositeModels.CompositeState;
import static io.elmos.composite.CompositeModels.Language;

/**
 * System-level control layer. It coordinates the Java, .NET, Python and frontend/client engines,
 * but is not itself a source transformation engine and exposes no source-edit operation.
 */
public final class CompositeModernizationOrchestrator {
    public record Capabilities(List<Language> languageEngines, List<String> responsibilities,
                               List<String> prohibitedActions, List<CompositeState> lifecycle,
                               List<String> evidenceLayers) {}

    public Capabilities capabilities() {
        return new Capabilities(
                List.of(Language.JAVA, Language.DOTNET, Language.PYTHON, Language.FRONTEND_CLIENT),
                List.of("SYSTEM_LANDSCAPE", "CROSS_REPOSITORY_DEPENDENCIES", "CONTRACT_CATALOG",
                        "MIGRATION_WAVES", "COMPATIBILITY_WINDOWS", "DATA_OWNERSHIP",
                        "SHADOW_DIFFERENTIAL", "PROGRESSIVE_TRAFFIC", "SYSTEM_CUTOVER",
                        "CLIENT_VERSION_MATRIX", "CLIENT_RELEASE_COHORT"),
                List.of("EDIT_SOURCE", "BYPASS_LANGUAGE_ENGINE", "AUTO_ACCEPT_BUSINESS_RISK",
                        "AUTO_SWITCH_PRODUCTION_WRITES", "DELETE_LEGACY_DATABASE", "AUTO_DECOMMISSION"),
                List.of(CompositeState.DISCOVERY, CompositeState.LANDSCAPE_BUILDING,
                        CompositeState.CONTRACT_BASELINING, CompositeState.MIGRATION_ORDERING,
                        CompositeState.COMPATIBILITY_PREPARING, CompositeState.PARALLEL_RUNTIME,
                        CompositeState.SHADOW_VALIDATING, CompositeState.DATA_SYNCHRONIZING,
                        CompositeState.READ_CUTOVER, CompositeState.WRITE_CUTOVER,
                        CompositeState.FULL_TRAFFIC, CompositeState.STABILITY_HOLD,
                        CompositeState.LEGACY_READ_ONLY, CompositeState.DECOMMISSION_READY,
                        CompositeState.DECOMMISSIONED),
                List.of("LANGUAGE_ENGINE", "FRONTEND_CLIENT_ENGINE", "REPOSITORY", "CONTRACT",
                        "DATA", "RUNTIME", "VISUAL", "ACCESSIBILITY", "CLIENT_RELEASE",
                        "BUSINESS_JOURNEY", "COMPOSITE_SYSTEM"));
    }
}
