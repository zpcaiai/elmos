package io.elmos.dependency;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

import static io.elmos.dependency.DependencyMigrationModels.*;

/** Orchestrates Batch 6 without network discovery, package installation, or direct lockfile mutation. */
public final class DependencyMigrationService {
    private final ResolvedGraphProvider graphProvider;
    private final RiskAssessor riskAssessor;
    private final BuildPatchBackend buildBackend;
    private final ContractValidator contractValidator;

    public DependencyMigrationService(ResolvedGraphProvider graphProvider, RiskAssessor riskAssessor,
                                      BuildPatchBackend buildBackend, ContractValidator contractValidator) {
        this.graphProvider=Objects.requireNonNull(graphProvider); this.riskAssessor=Objects.requireNonNull(riskAssessor);
        this.buildBackend=Objects.requireNonNull(buildBackend); this.contractValidator=Objects.requireNonNull(contractValidator);
    }

    public RunResult migrate(Request request) {
        validate(request);
        List<ResolvedGraph> graphs = new DependencyInventoryNormalizer().normalize(request.buildModel(), graphProvider);
        ApiSemanticProfiler profiler = new ApiSemanticProfiler();
        List<ApiUsage> usages = profiler.usages(graphs, request.usageEvidence());
        List<SemanticProfile> profiles = profiler.profiles(usages, request.usageEvidence());
        List<Decision> decisions = new DependencyStrategyPlanner().plan(graphs, usages, profiles, request, riskAssessor);
        List<BuildPatch> patches = new BuildDependencyPatchPlanner().plan(decisions, request);
        List<BuildValidation> buildValidations = patches.stream().map(patch ->
                patch.obligations().isEmpty() ? buildBackend.validate(request.workspace().resolve("target-repository"), patch)
                        : new BuildValidation(patch.patchId(), Status.BLOCKED, "not-run", false, false, false, List.of(), patch.obligations())).toList();
        Map<String,ApiUsage> usageById = usages.stream().collect(Collectors.toMap(ApiUsage::dependencyId, Function.identity()));
        Map<String,SemanticProfile> profileById = profiles.stream().collect(Collectors.toMap(SemanticProfile::dependencyId, Function.identity()));
        List<ContractValidation> contractValidations = decisions.stream().filter(Decision::automatic)
                .map(decision -> contractValidator.validate(decision, profileById.get(decision.dependencyId()), usageById.get(decision.dependencyId()))).toList();
        String runId = DependencyMigrationIds.id("dependency-run", request.buildModel().snapshotId(),
                request.loweringConformance().loweringRunId(), request.targetProfile().targetProfileId(), graphs, decisions);
        ConformanceReport conformance = conformance(runId, request, graphs, usages, profiles, decisions, patches, buildValidations, contractValidations);
        RunManifest manifest = new RunManifest(runId, request.buildModel().snapshotId(), request.loweringConformance().loweringRunId(),
                request.targetProfile().targetProfileId(), DependencyMigrationIds.id("configuration", request.projectToTargetModule(), request.knowledgeMappings()),
                graphs.stream().flatMap(graph -> graph.nodes().stream()).map(NormalizedDependency::dependencyId).sorted().toList(),
                decisions.stream().map(Decision::decisionId).sorted().toList(), request.observedAt());
        return new RunResult(manifest, graphs, usages, profiles, decisions, patches, buildValidations, contractValidations, conformance);
    }

    private ConformanceReport conformance(String runId, Request request, List<ResolvedGraph> graphs,
                                          List<ApiUsage> usages, List<SemanticProfile> profiles,
                                          List<Decision> decisions, List<BuildPatch> patches,
                                          List<BuildValidation> builds, List<ContractValidation> contracts) {
        Map<String,BuildValidation> buildByPatch = builds.stream().collect(Collectors.toMap(BuildValidation::patchId, Function.identity()));
        Map<String,BuildPatch> patchByModule = patches.stream().collect(Collectors.toMap(BuildPatch::targetModuleId, Function.identity()));
        Map<String,ContractValidation> contractByDependency = contracts.stream().collect(Collectors.toMap(ContractValidation::dependencyId, Function.identity()));
        List<ModuleGate> gates = new ArrayList<>();
        request.projectToTargetModule().values().stream().distinct().sorted().forEach(module -> {
            List<String> projects = request.projectToTargetModule().entrySet().stream().filter(entry -> module.equals(entry.getValue())).map(Map.Entry::getKey).toList();
            List<ResolvedGraph> moduleGraphs = graphs.stream().filter(graph -> projects.contains(graph.projectId())).toList();
            List<String> dependencyIds = moduleGraphs.stream().flatMap(graph -> graph.nodes().stream()).map(NormalizedDependency::dependencyId).toList();
            List<Decision> moduleDecisions = decisions.stream().filter(decision -> module.equals(decision.targetModuleId())).toList();
            boolean da = !moduleGraphs.isEmpty() && moduleGraphs.stream().allMatch(ResolvedGraph::complete);
            boolean db = da && request.usageEvidence()!=null && request.usageEvidence().complete() && request.usageEvidence().analyzerRef()!=null && !request.usageEvidence().analyzerRef().isBlank() && request.usageEvidence().unresolved().isEmpty()
                    && usageEvidenceMatchesGraphs(request.usageEvidence(), graphs)
                    && profiles.stream().filter(profile -> dependencyIds.contains(profile.dependencyId())).allMatch(profile -> profile.unresolved().isEmpty());
            BuildPatch patch = patchByModule.get(module);
            BuildValidation build = patch == null ? null : buildByPatch.get(patch.patchId());
            boolean dc = db && moduleDecisions.size()==dependencyIds.size() && moduleDecisions.stream().allMatch(Decision::automatic)
                    && (patch == null || (build != null && build.passed()));
            boolean dd = dc && moduleDecisions.stream().allMatch(decision -> {
                ContractValidation validation = contractByDependency.get(decision.dependencyId());
                return validation != null && validation.passed();
            });
            gates.add(gate(module,"D-A",da,List.of("complete normalized inventory and resolved graph"),moduleGraphs.stream().map(ResolvedGraph::resolverRef).toList()));
            gates.add(gate(module,"D-B",db,List.of("complete used API surface and semantic profiles"),List.of(request.usageEvidence()==null?"missing":request.usageEvidence().analyzerRef())));
            gates.add(gate(module,"D-C",dc,List.of("approved strategy, supply-chain pass, and reproducible build resolution"),build==null?List.of():build.artifacts()));
            gates.add(gate(module,"D-D",dd,List.of("API contracts and differential behavior pass"),moduleDecisions.stream().map(Decision::dependencyId).toList()));
        });
        int deps = graphs.stream().mapToInt(graph -> graph.nodes().size()).sum();
        long completeGraphs = graphs.stream().filter(ResolvedGraph::complete).count();
        long observedOrProvenUnused = usages.stream().filter(usage -> usage.observed() || (request.usageEvidence()!=null && request.usageEvidence().complete())).count();
        long completeProfiles = profiles.stream().filter(profile -> profile.unresolved().isEmpty()).count();
        long automatic = decisions.stream().filter(Decision::automatic).count();
        long buildPass = builds.stream().filter(BuildValidation::passed).count();
        long contractPass = contracts.stream().filter(ContractValidation::passed).count();
        LinkedHashSet<String> blockers = new LinkedHashSet<>();
        decisions.stream().filter(decision -> !decision.automatic()).flatMap(decision -> decision.obligations().stream()).forEach(blockers::add);
        builds.stream().filter(validation -> !validation.passed()).flatMap(validation -> validation.diagnostics().stream()).forEach(blockers::add);
        contracts.stream().filter(validation -> !validation.passed()).flatMap(validation -> validation.diagnostics().stream()).forEach(blockers::add);
        List<String> obligations = decisions.stream().flatMap(decision -> decision.obligations().stream()).distinct().sorted().toList();
        boolean eligible = !gates.isEmpty() && gates.stream().filter(gate -> "D-D".equals(gate.gate())).allMatch(gate -> gate.status()==Status.PASSED);
        Coverage coverage = new Coverage(deps==0?1:1, ratio(completeGraphs, graphs.size()), ratio(observedOrProvenUnused,deps), ratio(completeProfiles,deps), ratio(automatic,deps), ratio(buildPass,patches.size()), ratio(contractPass,contracts.size()), blockers.size());
        return new ConformanceReport(6, eligible?"PASSED":"BLOCKED", runId, gates, coverage, List.copyOf(blockers), obligations, eligible);
    }

    private ModuleGate gate(String module, String gate, boolean passed, List<String> condition, List<String> evidence) {
        return new ModuleGate(module, gate, passed?Status.PASSED:Status.BLOCKED, passed && "D-D".equals(gate), passed?List.of():condition, evidence.stream().filter(Objects::nonNull).toList());
    }
    private double ratio(long value, long total) { return total==0 ? 1.0 : (double)value/total; }
    private boolean usageEvidenceMatchesGraphs(UsageEvidenceBundle evidence, List<ResolvedGraph> graphs) {
        java.util.Set<String> known = graphs.stream().flatMap(graph -> graph.nodes().stream())
                .map(dependency -> usageKey(dependency.projectId(), dependency.ecosystem(), dependency.name()))
                .collect(java.util.stream.Collectors.toSet());
        return evidence.usages().stream().allMatch(item -> known.contains(usageKey(item.projectId(), item.ecosystem(), item.dependencyName())));
    }
    private String usageKey(String project, String ecosystem, String name) {
        return (String.valueOf(project)+"\u001f"+String.valueOf(ecosystem)+"\u001f"+String.valueOf(name)).toLowerCase(java.util.Locale.ROOT);
    }
    private void validate(Request request) {
        Objects.requireNonNull(request, "request"); Objects.requireNonNull(request.workspace(), "workspace");
        Objects.requireNonNull(request.buildModel(), "build model"); Objects.requireNonNull(request.targetProfile(), "target profile");
        Objects.requireNonNull(request.loweringConformance(), "Batch 5 conformance");
        Objects.requireNonNull(request.observedAt(), "observation timestamp");
        if (!request.loweringConformance().eligibleForBatch6()) throw new IllegalArgumentException("Batch 5 did not admit this run to Batch 6");
    }
}
