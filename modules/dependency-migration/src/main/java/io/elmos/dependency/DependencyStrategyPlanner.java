package io.elmos.dependency;

import io.elmos.skeleton.SkeletonModels;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import static io.elmos.dependency.DependencyMigrationModels.*;

final class DependencyStrategyPlanner {
    List<Decision> plan(List<ResolvedGraph> graphs, List<ApiUsage> usages, List<SemanticProfile> profiles,
                        Request request, RiskAssessor riskAssessor) {
        Map<String,ApiUsage> usageById = usages.stream().collect(java.util.stream.Collectors.toMap(ApiUsage::dependencyId, value -> value));
        Map<String,SemanticProfile> profileById = profiles.stream().collect(java.util.stream.Collectors.toMap(SemanticProfile::dependencyId, value -> value));
        boolean usageComplete = request.usageEvidence() != null && request.usageEvidence().complete() && request.usageEvidence().unresolved().isEmpty();
        return graphs.stream().flatMap(graph -> graph.nodes().stream()).sorted(Comparator.comparing(NormalizedDependency::dependencyId))
                .map(dependency -> decide(dependency, usageById.get(dependency.dependencyId()), profileById.get(dependency.dependencyId()), request, riskAssessor, usageComplete)).toList();
    }

    private Decision decide(NormalizedDependency dependency, ApiUsage usage, SemanticProfile profile,
                            Request request, RiskAssessor riskAssessor, boolean usageComplete) {
        String targetModule = request.projectToTargetModule().get(dependency.projectId());
        List<String> rationale = new ArrayList<>(), obligations = new ArrayList<>();
        if (targetModule == null || targetModule.isBlank()) {
            obligations.add("source project has no target module mapping");
            return decision(dependency, targetModule, Strategy.MANUAL_REVIEW, null, null, null, rationale, obligations, false);
        }
        if (!batch5Eligible(targetModule, request.loweringConformance())) {
            obligations.add("Batch 5 did not admit target module for dependency mapping");
            return decision(dependency, targetModule, Strategy.MANUAL_REVIEW, null, null, null, rationale, obligations, false);
        }
        if (usage != null && !usage.observed()) {
            if (usageComplete) {
                rationale.add("complete usage analysis found no API use");
                return decision(dependency, targetModule, Strategy.REMOVE, null, perfect("remove"), null, rationale, obligations, true);
            }
            obligations.add("usage analysis incomplete; dependency cannot be classified as unused");
            return decision(dependency, targetModule, Strategy.MANUAL_REVIEW, null, null, null, rationale, obligations, false);
        }

        List<Candidate> candidates = discover(dependency, request.targetProfile(), request.knowledgeMappings(), request.observedAt());
        if (candidates.isEmpty()) {
            obligations.add("no approved, provenance-bearing semantic mapping");
            return decision(dependency, targetModule, Strategy.MANUAL_REVIEW, null, null, null, rationale, obligations, false);
        }
        record Evaluated(Candidate candidate, CompatibilityScore score, SupplyChainAssessment risk) {}
        List<Evaluated> evaluated = candidates.stream().map(candidate -> {
            SupplyChainAssessment risk = riskAssessor.assess(candidate, request.targetProfile(), request.observedAt());
            return new Evaluated(candidate, score(candidate, profile, request.targetProfile(), risk), risk);
        }).sorted(Comparator.comparingDouble((Evaluated value) -> value.score().total()).reversed().thenComparing(value -> value.candidate().candidateId())).toList();
        Evaluated selected = evaluated.stream().filter(value -> value.score().selectable() && value.risk().passed()).findFirst().orElse(null);
        if (selected == null) {
            evaluated.forEach(value -> obligations.addAll(value.score().blockingReasons()));
            obligations.add("all semantic candidates failed compatibility or supply-chain gates");
            return decision(dependency, targetModule, Strategy.PROHIBITED, null, null, null, rationale, obligations.stream().distinct().toList(), false);
        }
        rationale.add("selected by API coverage, semantic fit, target policy, and supply-chain gates");
        AdapterPlan adapter = adapter(dependency, targetModule, selected.candidate(), profile);
        BoundaryPlan boundary = boundary(dependency, selected.candidate(), profile);
        obligations.addAll(selected.score().gaps());
        return decision(dependency, targetModule, selected.candidate().strategy(), selected.candidate(), selected.score(), selected.risk(), adapter, boundary, rationale, obligations, true);
    }

    private List<Candidate> discover(NormalizedDependency dependency, SkeletonModels.TargetProfile target, List<KnowledgeMapping> mappings, Instant observedAt) {
        if (target == null) return List.of();
        return mappings.stream().filter(mapping -> "approved".equalsIgnoreCase(mapping.approvalStatus()))
                .filter(mapping -> equals(mapping.sourceEcosystem(), dependency.ecosystem()) && equals(mapping.sourceName(), dependency.name()))
                .filter(mapping -> sourceVersionMatches(mapping.sourceVersionRange(), dependency.resolvedVersion()))
                .filter(mapping -> equals(mapping.targetLanguage(), target.language()))
                .filter(mapping -> mapping.provenanceRef()!=null && !mapping.provenanceRef().isBlank())
                .filter(mapping -> mapping.observedAt()!=null && !mapping.observedAt().isAfter(observedAt))
                .filter(mapping -> mapping.strategy()==Strategy.TARGET_STANDARD_LIBRARY || exactVersion(mapping.targetVersion()))
                .map(mapping -> new Candidate(DependencyMigrationIds.id("candidate", mapping.mappingId(), mapping.targetCoordinate(), mapping.targetVersion()), mapping.mappingId(), mapping.targetKind(), mapping.targetCoordinate(), mapping.targetVersion(), mapping.strategy(), mapping.apiMappings(), mapping.semanticClaims(), mapping.confidence(), mapping.provenanceRef()))
                .sorted(Comparator.comparing(Candidate::candidateId)).toList();
    }

    private CompatibilityScore score(Candidate candidate, SemanticProfile profile, SkeletonModels.TargetProfile target, SupplyChainAssessment risk) {
        List<String> required = profile == null ? List.of() : profile.requiredApis();
        long mapped = required.stream().filter(api -> candidate.apiMappings().containsKey(api)).count();
        double api = required.isEmpty() ? 1.0 : (double)mapped / required.size();
        double semantic = profile == null || profile.requirements().isEmpty() ? candidate.knowledgeConfidence()
                : profile.requirements().keySet().stream().filter(candidate.semanticClaims()::containsKey).count() / (double)profile.requirements().size();
        boolean prohibited = containsIgnoreCase(target.prohibitedDependencies(), candidate.coordinate());
        boolean approved = candidate.strategy()==Strategy.TARGET_STANDARD_LIBRARY || target.approvedDependencies().isEmpty() || containsIgnoreCase(target.approvedDependencies(), candidate.coordinate());
        double platform = "supported".equalsIgnoreCase(risk.platformState()) ? 1.0 : 0.0;
        double operational = risk.passed() ? 1.0 : 0.0;
        List<String> gaps = new ArrayList<>();
        required.stream().filter(requiredApi -> !candidate.apiMappings().containsKey(requiredApi)).forEach(requiredApi -> gaps.add("unmapped API: "+requiredApi));
        List<String> blockers = new ArrayList<>(risk.blockers());
        if (prohibited) blockers.add("target profile prohibits "+candidate.coordinate());
        if (!approved) blockers.add("target dependency is outside the approved set: "+candidate.coordinate());
        if (api < 1.0) blockers.add("candidate does not cover the complete used API surface");
        if (semantic < 1.0 && profile != null && !profile.requirements().isEmpty()) blockers.add("candidate lacks required semantic claims");
        if (!risk.passed()) blockers.add("supply-chain assessment did not pass");
        double total = .45*api + .30*semantic + .15*platform + .10*operational;
        return new CompatibilityScore(candidate.candidateId(), api, semantic, platform, operational, total, gaps, blockers.stream().distinct().toList());
    }

    private AdapterPlan adapter(NormalizedDependency dependency, String module, Candidate candidate, SemanticProfile profile) {
        if (candidate.strategy()!=Strategy.GENERATED_ADAPTER && candidate.strategy()!=Strategy.COMPATIBILITY_RUNTIME && candidate.strategy()!=Strategy.APPROVED_NATIVE && candidate.strategy()!=Strategy.ECOSYSTEM_PACKAGE) return null;
        String id = DependencyMigrationIds.id("adapter", dependency.dependencyId(), candidate.candidateId());
        String folder = candidate.strategy()==Strategy.COMPATIBILITY_RUNTIME ? "compatibility-runtime" : "adapters";
        return new AdapterPlan(id, dependency.dependencyId(), candidate.strategy(), module,
                profile == null ? List.of() : profile.requiredApis(), List.of("target-repository/"+folder+"/"+id), List.of("generated code requires target compiler validation"));
    }
    private BoundaryPlan boundary(NormalizedDependency dependency, Candidate candidate, SemanticProfile profile) {
        if (!java.util.Set.of(Strategy.IN_PROCESS_WRAPPER, Strategy.SIDECAR, Strategy.REMOTE_SERVICE, Strategy.RETAIN_SOURCE_RUNTIME).contains(candidate.strategy())) return null;
        String id = DependencyMigrationIds.id("boundary", dependency.dependencyId(), candidate.strategy());
        String protocol = candidate.strategy()==Strategy.IN_PROCESS_WRAPPER ? "in-process ABI" : "versioned RPC";
        return new BoundaryPlan(id, dependency.dependencyId(), candidate.strategy(), protocol, "schema-first", "explicit startup/readiness/shutdown", "bounded concurrency with cancellation", List.of("timeouts", "memory", "connections"), List.of("boundaries/"+candidate.strategy().name().toLowerCase(Locale.ROOT)+"/"+id), List.of("validate serialization compatibility", "validate failure propagation and cleanup"));
    }
    private Decision decision(NormalizedDependency dep, String module, Strategy strategy, Candidate candidate, CompatibilityScore score, SupplyChainAssessment risk, List<String> rationale, List<String> obligations, boolean automatic) {
        return decision(dep,module,strategy,candidate,score,risk,null,null,rationale,obligations,automatic);
    }
    private Decision decision(NormalizedDependency dep, String module, Strategy strategy, Candidate candidate, CompatibilityScore score, SupplyChainAssessment risk, AdapterPlan adapter, BoundaryPlan boundary, List<String> rationale, List<String> obligations, boolean automatic) {
        return new Decision(DependencyMigrationIds.id("decision", dep.dependencyId(), strategy, candidate==null?"":candidate.candidateId()), dep.dependencyId(), dep.coordinate(), dep.resolvedVersion(), module, strategy, candidate, score, risk, adapter, boundary, rationale, obligations, automatic);
    }
    private CompatibilityScore perfect(String id) { return new CompatibilityScore(id,1,1,1,1,1,List.of(),List.of()); }
    private boolean batch5Eligible(String module, io.elmos.lowering.LoweringModels.ConformanceReport report) {
        return report != null && report.eligibleForBatch6() && report.modules().stream().anyMatch(gate -> module.equals(gate.targetModuleId()) && gate.eligibleForDependencyMapping());
    }
    private static boolean equals(String a, String b) { return a != null && b != null && a.equalsIgnoreCase(b); }
    private static boolean containsIgnoreCase(List<String> values, String candidate) { return candidate != null && values.stream().anyMatch(candidate::equalsIgnoreCase); }
    private static boolean exactVersion(String value) {
        return value != null && !value.isBlank() && !value.matches(".*[<>=~^*xX, ].*");
    }
    /** Deliberately small cross-ecosystem subset. Unknown range syntax fails closed and must be resolved by an authority. */
    private static boolean sourceVersionMatches(String range, String version) {
        if (range == null || version == null) return false;
        if (range.equals("*") || range.equals(version)) return true;
        if (!(range.startsWith("[") || range.startsWith("(")) || !(range.endsWith("]") || range.endsWith(")")) || !range.contains(",")) return false;
        String[] bounds = range.substring(1, range.length()-1).split(",", -1);
        if (bounds.length != 2) return false;
        int lower = bounds[0].isBlank() ? 1 : compareVersion(version, bounds[0].trim());
        int upper = bounds[1].isBlank() ? -1 : compareVersion(version, bounds[1].trim());
        boolean lowerOk = bounds[0].isBlank() || (range.startsWith("[") ? lower >= 0 : lower > 0);
        boolean upperOk = bounds[1].isBlank() || (range.endsWith("]") ? upper <= 0 : upper < 0);
        return lowerOk && upperOk;
    }
    private static int compareVersion(String left, String right) {
        String[] a=left.split("[.-]"), b=right.split("[.-]");
        for (int i=0;i<Math.max(a.length,b.length);i++) {
            String av=i<a.length?a[i]:"0", bv=i<b.length?b[i]:"0";
            int compared;
            try { compared=Integer.compare(Integer.parseInt(av),Integer.parseInt(bv)); }
            catch (NumberFormatException ignored) { compared=av.compareToIgnoreCase(bv); }
            if (compared!=0) return compared;
        }
        return 0;
    }
}
