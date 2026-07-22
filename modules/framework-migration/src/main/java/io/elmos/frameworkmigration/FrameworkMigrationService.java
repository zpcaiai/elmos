package io.elmos.frameworkmigration;

import java.nio.file.Path;
import java.util.*;
import java.util.function.Predicate;
import java.util.stream.Collectors;

import static io.elmos.frameworkmigration.FrameworkMigrationModels.*;

/** Offline Batch 7 control plane. Native framework analyzers, emitters and startup runners are injected. */
public final class FrameworkMigrationService {
    private final FingerprintDetector fingerprintDetector;
    private final AfsmLifter lifter;
    private final FrameworkBackend backend;
    private final StartupValidator startupValidator;

    public FrameworkMigrationService(AfsmLifter lifter, FrameworkBackend backend,
                                     StartupValidator startupValidator) {
        this(new EvidenceFrameworkFingerprintDetector(), lifter, backend, startupValidator);
    }

    public FrameworkMigrationService(FingerprintDetector fingerprintDetector, AfsmLifter lifter,
                                     FrameworkBackend backend, StartupValidator startupValidator) {
        this.fingerprintDetector = Objects.requireNonNull(fingerprintDetector);
        this.lifter = Objects.requireNonNull(lifter);
        this.backend = Objects.requireNonNull(backend);
        this.startupValidator = Objects.requireNonNull(startupValidator);
    }

    public RunResult migrate(Request request) {
        validate(request);
        FrameworkFingerprint fingerprint = Objects.requireNonNull(
                fingerprintDetector.detect(request.frameworkSignals(), request.targetProfile()), "fingerprint");
        LiftResult lift = Objects.requireNonNull(lifter.lift(new LiftRequest(fingerprint, request.uir(),
                request.targetProfile(), request.sourceProjectToTargetModule())), "AFSM lift");
        List<RecipePlan> plans = new FrameworkRecipeRegistry().plan(lift.entities(), request.recipes(),
                request.targetProfile(), request.targetFrameworkVersion());
        Map<String,AfsmEntity> entities = lift.entities().stream().filter(Objects::nonNull)
                .filter(entity -> entity.entityId() != null)
                .collect(Collectors.toMap(AfsmEntity::entityId, entity -> entity, (left, right) -> left, LinkedHashMap::new));
        Path targetRepository = request.workspace().toAbsolutePath().normalize().resolve("target-repository");
        List<Emission> emissions = plans.stream().filter(RecipePlan::automatic).map(plan -> {
            AfsmEntity entity = entities.get(plan.entityId());
            if (entity == null) return failedEmission(plan, "recipe-plan-entity-missing");
            try {
                Emission emission = backend.emit(new EmissionRequest(entity, plan, request.targetProfile(), targetRepository));
                return emission == null ? failedEmission(plan, "framework-backend-returned-null") : emission;
            } catch (RuntimeException error) {
                return failedEmission(plan, "framework-backend-failed:" + error.getClass().getSimpleName());
            }
        }).sorted(Comparator.comparing(Emission::entityId)).toList();

        Set<String> targetModules = new TreeSet<>(request.sourceProjectToTargetModule().values());
        targetModules.addAll(lift.entities().stream().map(AfsmEntity::targetModuleId).filter(Objects::nonNull).toList());
        FrameworkSemanticValidator.Analysis analysis = new FrameworkSemanticValidator().analyze(
                lift, request.uir(), plans, emissions, targetModules, request.observedAt());
        List<SemanticObligation> obligations = mergeObligations(request, lift, plans, emissions, analysis);
        LinkedHashSet<String> prevalidationBlockers = new LinkedHashSet<>();
        if (!fingerprint.complete()) prevalidationBlockers.addAll(fingerprint.diagnostics());
        if (!lift.complete() || blank(lift.analyzerRef())) {
            prevalidationBlockers.add("authoritative-afsm-lift-incomplete");
            prevalidationBlockers.addAll(lift.diagnostics());
        }
        if (lift.entities().isEmpty()) prevalidationBlockers.add("authoritative-afsm-lift-produced-no-entities");
        lift.entities().stream().filter(entity -> !Objects.equals(request.targetProfile().preferredFramework(), entity.targetFramework()))
                .map(entity -> entity.entityId() + ":target-framework-mismatch")
                .forEach(prevalidationBlockers::add);
        plans.stream().filter(plan -> !plan.automatic()).flatMap(plan -> plan.diagnostics().stream())
                .forEach(prevalidationBlockers::add);
        prevalidationBlockers.addAll(analysis.blockingIssues());
        obligations.stream().filter(SemanticObligation::openAndBlocking)
                .map(obligation -> obligation.entityId() + ":open-blocking-obligation:" + obligation.obligationId())
                .forEach(prevalidationBlockers::add);

        FrameworkValidation validation;
        if (prevalidationBlockers.isEmpty() && emissions.size() == lift.entities().size()
                && emissions.stream().allMatch(Emission::passed)) {
            try {
                validation = Objects.requireNonNull(startupValidator.validate(
                        new ValidationRequest(targetRepository, fingerprint, lift.entities(), emissions)));
            } catch (RuntimeException error) {
                validation = FrameworkValidation.blocked("framework-startup-validator-failed:" + error.getClass().getSimpleName());
            }
        } else {
            validation = FrameworkValidation.blocked("framework-validation-preconditions-blocked");
        }

        String runId = FrameworkIds.id("framework-run", request.uir().manifest().snapshotId(),
                request.uir().manifest().uirRunId(), request.dependencyConformance().dependencyRunId(),
                request.targetProfile().targetProfileId(), fingerprint, lift, plans, emissions, request.observedAt());
        RunManifest manifest = new RunManifest(runId, request.uir().manifest().snapshotId(),
                request.uir().manifest().uirRunId(), request.dependencyConformance().dependencyRunId(),
                request.targetProfile().targetProfileId(), request.targetFrameworkVersion(), fingerprint.frameworkId(),
                FrameworkIds.hash(List.of(request.targetProfile(), request.targetFrameworkVersion(),
                        request.sourceProjectToTargetModule(), request.recipes())),
                lift.entities().stream().map(AfsmEntity::entityId).filter(Objects::nonNull).sorted().toList(),
                plans.stream().map(RecipePlan::planId).sorted().toList(),
                emissions.stream().map(Emission::emissionId).filter(Objects::nonNull).sorted().toList(),
                request.observedAt());
        ConformanceReport conformance = conformance(runId, request, lift, plans, emissions,
                analysis, obligations, validation, targetModules, prevalidationBlockers);
        return new RunResult(manifest, fingerprint, lift, plans, emissions, analysis.differences(),
                obligations, validation, conformance);
    }

    private List<SemanticObligation> mergeObligations(Request request, LiftResult lift,
                                                       List<RecipePlan> plans, List<Emission> emissions,
                                                       FrameworkSemanticValidator.Analysis analysis) {
        LinkedHashMap<String,SemanticObligation> result = new LinkedHashMap<>();
        lift.obligations().forEach(obligation -> result.put(obligation.obligationId(), obligation));
        analysis.obligations().forEach(obligation -> result.put(obligation.obligationId(), obligation));
        Map<String,Recipe> recipeById = request.recipes().stream().collect(Collectors.toMap(Recipe::recipeId,
                recipe -> recipe, (left, right) -> left));
        for (RecipePlan plan : plans) {
            Recipe recipe = recipeById.get(plan.selectedRecipeId());
            for (int index = 0; index < plan.obligationIds().size(); index++) {
                String id = plan.obligationIds().get(index);
                String statement = recipe != null && index < recipe.obligationTemplates().size()
                        ? recipe.obligationTemplates().get(index) : "Resolve framework recipe obligation";
                result.putIfAbsent(id, new SemanticObligation(id, plan.entityId(), "recipe", "blocking", "open",
                        statement, recipe == null ? List.of("manual-review") : recipe.validations(),
                        recipe == null ? List.of() : List.of(recipe.provenanceRef()), null, null));
            }
        }
        Map<String,String> knownEntityByObligation = lift.entities().stream().flatMap(entity -> entity.obligationIds().stream()
                .map(id -> Map.entry(id, entity.entityId()))).collect(Collectors.toMap(Map.Entry::getKey,
                Map.Entry::getValue, (left, right) -> left));
        emissions.forEach(emission -> emission.obligationIds().forEach(id -> knownEntityByObligation.putIfAbsent(id, emission.entityId())));
        knownEntityByObligation.forEach((id, entityId) -> result.putIfAbsent(id,
                new SemanticObligation(id, entityId, "unresolved-reference", "blocking", "open",
                        "Provide the missing framework obligation definition and evidence",
                        List.of("manual-review"), List.of(), null, null)));
        result.values().stream().filter(obligation -> "waived".equalsIgnoreCase(obligation.status())
                && (blank(obligation.owner()) || blank(obligation.waiverReason())))
                .map(obligation -> new SemanticObligation(obligation.obligationId(), obligation.entityId(),
                        obligation.category(), "blocking", "open", "Invalid waiver: owner and reason are required",
                        List.of("manual-review"), obligation.evidenceRefs(), null, null))
                .forEach(obligation -> result.put(obligation.obligationId(), obligation));
        return result.values().stream().sorted(Comparator.comparing(SemanticObligation::obligationId)).toList();
    }

    private ConformanceReport conformance(String runId, Request request, LiftResult lift,
                                          List<RecipePlan> plans, List<Emission> emissions,
                                          FrameworkSemanticValidator.Analysis analysis,
                                          List<SemanticObligation> obligations,
                                          FrameworkValidation validation, Set<String> targetModules,
                                          Set<String> prevalidationBlockers) {
        Map<String,Emission> emissionByEntity = emissions.stream().collect(Collectors.toMap(Emission::entityId,
                emission -> emission, (left, right) -> left));
        Coverage coverage = coverage(lift, emissions);
        Fidelity fidelity = fidelity(lift, emissions, analysis.differences());
        LinkedHashSet<String> allBlockers = new LinkedHashSet<>(prevalidationBlockers);
        if (!validation.frameworkReady()) {
            allBlockers.add("framework-startup-and-discovery-not-proven");
            allBlockers.addAll(validation.diagnostics());
        }
        List<ModuleGate> gates = new ArrayList<>();
        for (String module : targetModules) {
            List<AfsmEntity> moduleEntities = lift.entities().stream().filter(entity -> module.equals(entity.targetModuleId())).toList();
            Set<String> moduleIds = moduleEntities.stream().map(AfsmEntity::entityId).collect(Collectors.toSet());
            List<String> moduleIssues = allBlockers.stream().filter(issue -> appliesToModule(issue, moduleIds)).toList();
            boolean entityPlans = moduleEntities.stream().allMatch(entity -> plans.stream().anyMatch(plan ->
                    plan.entityId().equals(entity.entityId()) && plan.automatic()));
            boolean entityEmissions = moduleEntities.stream().allMatch(entity -> {
                Emission emission = emissionByEntity.get(entity.entityId()); return emission != null && emission.passed();
            });
            boolean securityComplete = concernRate(moduleEntities, emissionByEntity,
                    entity -> Set.of("authentication-scheme", "authorization-policy").contains(entity.entityKind())) == 1;
            boolean fa = fingerprintAndLiftReady(request, lift) && entityPlans
                    && rateFor(moduleEntities, emissionByEntity, "endpoint") >= .98
                    && rateFor(moduleEntities, emissionByEntity, "provider") >= .95
                    && rateFor(moduleEntities, emissionByEntity, "configuration-source", "configuration-binding") >= .95
                    && securityComplete && moduleIssues.stream().noneMatch(this::isStructuralOrSecurityIssue);
            boolean fb = fa && entityEmissions && validation.frameworkReady()
                    && moduleIssues.stream().noneMatch(issue -> issue.contains("route-conflict")
                    || issue.contains("captive-dependency") || issue.contains("order-invalid"));
            boolean noOpenBlocking = obligations.stream().filter(SemanticObligation::openAndBlocking)
                    .noneMatch(obligation -> moduleIds.contains(obligation.entityId()));
            boolean fc = fb && rateFor(moduleEntities, emissionByEntity, "endpoint") >= .99
                    && rateFor(moduleEntities, emissionByEntity, "validation-contract") >= .95
                    && rateFor(moduleEntities, emissionByEntity, "transaction-policy") >= .95
                    && rateFor(moduleEntities, emissionByEntity, "authentication-scheme") == 1
                    && rateFor(moduleEntities, emissionByEntity, "authorization-policy") == 1
                    && noOpenBlocking && moduleIssues.isEmpty();
            boolean unreviewedAgent = moduleEntities.stream().map(AfsmEntity::entityId).map(emissionByEntity::get)
                    .filter(Objects::nonNull).anyMatch(emission -> emission.agentGenerated()
                            && (!emission.humanReviewApproved() || blank(emission.reviewEvidenceRef())));
            boolean fd = fc && rateFor(moduleEntities, emissionByEntity, "endpoint") >= .995
                    && rateFor(moduleEntities, emissionByEntity, "provider") >= .99
                    && fidelity.middlewareOrder() == 1 && securityComplete
                    && rateFor(moduleEntities, emissionByEntity, "transaction-policy") >= .98
                    && rateFor(moduleEntities, emissionByEntity, "message-producer", "message-consumer") >= .97
                    && rateFor(moduleEntities, emissionByEntity, "cache-region", "cache-operation") >= .98
                    && rateFor(moduleEntities, emissionByEntity, "scheduled-job", "background-task") >= .98
                    && coverage.sourceTargetTraceCoverage() >= .995 && !unreviewedAgent && validation.smokeReady();
            List<String> evidence = validation.artifacts();
            gates.add(gate(module, "F-A", fa, false, false, moduleIssues, evidence));
            gates.add(gate(module, "F-B", fb, false, false, moduleIssues, evidence));
            gates.add(gate(module, "F-C", fc, true, true, moduleIssues, evidence));
            gates.add(gate(module, "F-D", fd, true, true, moduleIssues, evidence));
        }
        boolean eligible = !targetModules.isEmpty() && gates.stream().filter(gate -> "F-D".equals(gate.gate()))
                .allMatch(gate -> gate.status() == Status.PASSED);
        return new ConformanceReport(7, eligible ? "PASSED" : "BLOCKED", runId, gates,
                coverage, fidelity, List.copyOf(allBlockers), obligations.stream()
                .filter(obligation -> !"verified".equalsIgnoreCase(obligation.status())
                        && !"waived".equalsIgnoreCase(obligation.status()))
                .map(SemanticObligation::obligationId).distinct().sorted().toList(), eligible);
    }

    private boolean fingerprintAndLiftReady(Request request, LiftResult lift) {
        return lift.complete() && !blank(lift.analyzerRef()) && request.dependencyConformance().eligibleForBatch7();
    }

    private ModuleGate gate(String module, String gate, boolean passed, boolean build,
                            boolean integration, List<String> issues, List<String> evidence) {
        return new ModuleGate(module, gate, passed ? Status.PASSED : Status.BLOCKED,
                passed && build, passed && integration, passed && "F-D".equals(gate),
                passed ? List.of() : issues.isEmpty() ? List.of("gate-conditions-not-satisfied") : issues,
                passed ? evidence : List.of());
    }

    private Coverage coverage(LiftResult lift, List<Emission> emissions) {
        Map<String,Emission> byId = emissions.stream().collect(Collectors.toMap(Emission::entityId,
                value -> value, (left, right) -> left));
        List<AfsmEntity> entities = lift.entities();
        return new Coverage(lift.complete() ? 1 : ratio(entities.stream().filter(entity -> entity.provenance() != null).count(), entities.size()),
                rateFor(entities, byId, "endpoint"), rateFor(entities, byId, "provider"),
                rateFor(entities, byId, "validation-contract"),
                rateFor(entities, byId, "entity-model", "repository-model", "query-model", "unit-of-work"),
                rateFor(entities, byId, "transaction-policy"),
                rateFor(entities, byId, "authentication-scheme", "authorization-policy"),
                rateFor(entities, byId, "configuration-source", "configuration-binding"),
                rateFor(entities, byId, "message-producer", "message-consumer", "message-contract"),
                rateFor(entities, byId, "cache-region", "cache-operation"),
                rateFor(entities, byId, "scheduled-job", "background-task"),
                ratio(entities.stream().filter(entity -> !entity.sourceMapIds().isEmpty()).count(), entities.size()));
    }

    private Fidelity fidelity(LiftResult lift, List<Emission> emissions, List<SemanticDifference> differences) {
        Map<String,Emission> byId = emissions.stream().collect(Collectors.toMap(Emission::entityId,
                value -> value, (left, right) -> left));
        return new Fidelity(fidelityFor(lift, byId, differences, Set.of("endpoint")),
                fidelityFor(lift, byId, differences, Set.of("parameter-binding")),
                fidelityFor(lift, byId, differences, Set.of("response-contract", "exception-mapping")),
                fidelityFor(lift, byId, differences, Set.of("middleware", "filter", "interceptor", "guard")),
                fidelityFor(lift, byId, differences, Set.of("provider", "dependency-binding", "lifecycle-scope")),
                fidelityFor(lift, byId, differences, Set.of("validation-contract")),
                fidelityFor(lift, byId, differences, Set.of("transaction-policy")),
                fidelityFor(lift, byId, differences, Set.of("authentication-scheme")),
                fidelityFor(lift, byId, differences, Set.of("authorization-policy")),
                fidelityFor(lift, byId, differences, Set.of("message-producer", "message-consumer", "message-contract")),
                fidelityFor(lift, byId, differences, Set.of("cache-region", "cache-operation")),
                fidelityFor(lift, byId, differences, Set.of("scheduled-job", "background-task")),
                fidelityFor(lift, byId, differences, Set.of("startup-hook", "shutdown-hook", "health-check")));
    }

    private double fidelityFor(LiftResult lift, Map<String,Emission> emissions,
                               List<SemanticDifference> differences, Set<String> kinds) {
        List<AfsmEntity> relevant = lift.entities().stream().filter(entity -> kinds.contains(entity.entityKind())).toList();
        if (relevant.isEmpty()) return 1;
        Set<String> failed = differences.stream().filter(difference -> !"verified-equivalent".equals(difference.assessment()))
                .map(SemanticDifference::entityId).collect(Collectors.toSet());
        return ratio(relevant.stream().filter(entity -> {
            Emission emission = emissions.get(entity.entityId()); return emission != null && emission.passed() && !failed.contains(entity.entityId());
        }).count(), relevant.size());
    }

    private double rateFor(List<AfsmEntity> entities, Map<String,Emission> emissions, String... kinds) {
        Set<String> accepted = Set.of(kinds);
        return concernRate(entities, emissions, entity -> accepted.contains(entity.entityKind()));
    }

    private double concernRate(List<AfsmEntity> entities, Map<String,Emission> emissions,
                               Predicate<AfsmEntity> filter) {
        List<AfsmEntity> relevant = entities.stream().filter(filter).toList();
        return relevant.isEmpty() ? 1 : ratio(relevant.stream().filter(entity -> {
            Emission emission = emissions.get(entity.entityId()); return emission != null && emission.passed();
        }).count(), relevant.size());
    }

    private double ratio(long value, long total) { return total == 0 ? 1 : (double) value / total; }

    private boolean appliesToModule(String issue, Set<String> moduleEntityIds) {
        if (moduleEntityIds.stream().anyMatch(id -> issue.startsWith(id + ":"))) return true;
        return !issue.startsWith("afsm:") || issue.startsWith("framework-")
                || issue.startsWith("authoritative-") || issue.startsWith("no-") || issue.startsWith("ambiguous-");
    }

    private boolean isStructuralOrSecurityIssue(String issue) {
        return issue.contains("source-map") || issue.contains("provenance") || issue.contains("endpoint")
                || issue.contains("security") || issue.contains("authentication") || issue.contains("authorization")
                || issue.contains("secret") || issue.contains("route-conflict");
    }

    private Emission failedEmission(RecipePlan plan, String diagnostic) {
        return new Emission(FrameworkIds.id("framework-emission", plan.planId(), diagnostic), plan.entityId(),
                plan.selectedRecipeId(), Status.BLOCKED, List.of(), Map.of(), List.of(), plan.obligationIds(),
                null, false, false, false, true, false, false, null, false, List.of(diagnostic));
    }

    private void validate(Request request) {
        Objects.requireNonNull(request, "request"); Objects.requireNonNull(request.workspace(), "workspace");
        Objects.requireNonNull(request.uir(), "UIR"); Objects.requireNonNull(request.uir().manifest(), "UIR manifest");
        Objects.requireNonNull(request.targetProfile(), "target profile");
        Objects.requireNonNull(request.dependencyConformance(), "Batch 6 conformance");
        Objects.requireNonNull(request.observedAt(), "observation timestamp");
        if (request.dependencyConformance().batch() != 6 || !request.dependencyConformance().eligibleForBatch7())
            throw new IllegalArgumentException("Batch 6 did not admit this run to Batch 7");
        if (blank(request.targetProfile().preferredFramework()))
            throw new IllegalArgumentException("Target framework is unresolved");
        if (blank(request.targetFrameworkVersion()))
            throw new IllegalArgumentException("Target framework version is unresolved");
        if (request.sourceProjectToTargetModule().isEmpty())
            throw new IllegalArgumentException("Source-to-target module mapping is required");
        if (request.sourceProjectToTargetModule().entrySet().stream()
                .anyMatch(entry -> blank(entry.getKey()) || blank(entry.getValue())))
            throw new IllegalArgumentException("Source-to-target module mapping contains blank entries");
    }

    private static boolean blank(String value) { return value == null || value.isBlank(); }
}
