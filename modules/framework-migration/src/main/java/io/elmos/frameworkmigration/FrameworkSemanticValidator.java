package io.elmos.frameworkmigration;

import io.elmos.uir.UirModels;

import java.time.Instant;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;

import static io.elmos.frameworkmigration.FrameworkMigrationModels.*;

/** Cross-concern AFSM and emitted-semantics validator. */
final class FrameworkSemanticValidator {
    record Analysis(List<String> blockingIssues, List<SemanticDifference> differences,
                    List<SemanticObligation> obligations, Map<String,List<String>> issuesByEntity) {}

    private static final Map<String,List<String>> SEMANTIC_KEYS = Map.ofEntries(
            Map.entry("endpoint", List.of("route", "methods", "access", "status", "contentType")),
            Map.entry("parameter-binding", List.of("source", "required", "default", "collectionMode", "coercion")),
            Map.entry("response-contract", List.of("status", "contentType", "schema", "nullPolicy")),
            Map.entry("middleware", List.of("order", "shortCircuit", "async")),
            Map.entry("filter", List.of("order", "shortCircuit", "async")),
            Map.entry("interceptor", List.of("order", "shortCircuit", "async")),
            Map.entry("guard", List.of("order", "shortCircuit", "async")),
            Map.entry("provider", List.of("scope", "lazy", "optional", "factoryCalls", "cleanup")),
            Map.entry("validation-contract", List.of("coercion", "errorShape", "collectAll", "groups")),
            Map.entry("exception-mapping", List.of("status", "errorCode", "schema", "priority")),
            Map.entry("entity-model", List.of("precision", "scale", "keyGeneration", "lazyLoading", "tracking")),
            Map.entry("query-model", List.of("ordering", "pagination", "tracking", "locking", "streaming")),
            Map.entry("transaction-policy", List.of("propagation", "isolation", "rollback", "timeout", "readOnly")),
            Map.entry("authentication-scheme", List.of("issuer", "audience", "algorithm", "unauthenticatedStatus", "challenge")),
            Map.entry("authorization-policy", List.of("expression", "defaultDecision", "failureStatus")),
            Map.entry("configuration-source", List.of("priority", "profile", "reload")),
            Map.entry("configuration-binding", List.of("required", "default", "reload", "secretReference")),
            Map.entry("message-producer", List.of("delivery", "ordering", "transaction", "schema")),
            Map.entry("message-consumer", List.of("ack", "delivery", "ordering", "retry", "deadLetter", "schema")),
            Map.entry("cache-region", List.of("backend", "ttl", "cacheNull", "tenantKey", "transactionOrder")),
            Map.entry("cache-operation", List.of("operation", "key", "condition", "transactionOrder")),
            Map.entry("scheduled-job", List.of("durability", "cronDialect", "timezone", "fixedMode", "misfire", "concurrency")),
            Map.entry("background-task", List.of("durability", "retry", "shutdown")),
            Map.entry("startup-hook", List.of("order", "blocking", "timeout")),
            Map.entry("shutdown-hook", List.of("order", "graceful", "timeout")),
            Map.entry("health-check", List.of("healthType", "sensitive", "destructive")));

    Analysis analyze(LiftResult lift, UirModels.Dataset uir, List<RecipePlan> plans,
                     List<Emission> emissions, Set<String> targetModules, Instant observedAt) {
        LinkedHashSet<String> blockers = new LinkedHashSet<>();
        Map<String,List<String>> byEntity = new LinkedHashMap<>();
        List<SemanticDifference> differences = new ArrayList<>();
        List<SemanticObligation> obligations = new ArrayList<>();
        Set<String> uirSourceMaps = uir.entities().stream()
                .filter(entity -> "source-map".equals(entity.entityKind()) || entity.payload() instanceof UirModels.SourceMap)
                .map(UirModels.Entity::entityId).collect(Collectors.toSet());
        Map<String,AfsmEntity> entities = new LinkedHashMap<>();
        for (AfsmEntity entity : lift.entities()) {
            if (entity == null || entity.entityId() == null || entity.entityId().isBlank()) {
                add(blockers, byEntity, "unknown", "afsm-entity-id-missing");
                continue;
            }
            if (entities.putIfAbsent(entity.entityId(), entity) != null)
                add(blockers, byEntity, entity.entityId(), "duplicate-afsm-entity-id");
            validateEnvelope(entity, targetModules, uirSourceMaps, blockers, byEntity);
        }
        for (AfsmEntity entity : entities.values()) {
            for (String relation : entity.relatedEntityIds()) {
                if (!entities.containsKey(relation)) add(blockers, byEntity, entity.entityId(), "dangling-afsm-relation:" + relation);
            }
        }
        validateRoutes(entities.values(), blockers, byEntity);
        validateProtectedEndpoints(entities, blockers, byEntity);
        validateCaptiveDependencies(entities, blockers, byEntity);
        Map<String,RecipePlan> planByEntity = unique(plans, RecipePlan::entityId, blockers, "duplicate-recipe-plan");
        Map<String,Emission> emissionByEntity = unique(emissions, Emission::entityId, blockers, "duplicate-framework-emission");
        for (AfsmEntity entity : entities.values()) {
            RecipePlan plan = planByEntity.get(entity.entityId());
            if (plan == null || !plan.automatic()) add(blockers, byEntity, entity.entityId(), "automatic-recipe-plan-missing");
            Emission emission = emissionByEntity.get(entity.entityId());
            if (emission == null) {
                add(blockers, byEntity, entity.entityId(), "verified-framework-emission-missing");
                continue;
            }
            if (emission.containsSecretMaterial())
                add(blockers, byEntity, entity.entityId(), "secret-material-in-framework-emission");
            if (isHighRisk(entity) && emission.agentGenerated()
                    && (!emission.humanReviewApproved() || blank(emission.reviewEvidenceRef())))
                add(blockers, byEntity, entity.entityId(), "unreviewed-agent-high-risk-framework-patch");
            if (!emission.passed()) {
                add(blockers, byEntity, entity.entityId(), "verified-framework-emission-missing");
                continue;
            }
            if (!emission.sourceMapIds().containsAll(entity.sourceMapIds()))
                add(blockers, byEntity, entity.entityId(), "framework-emission-source-map-gap");
            compareSemantics(entity, emission, observedAt, blockers, byEntity, differences, obligations);
        }
        validatePipelineOrder(entities.values(), emissionByEntity, blockers, byEntity);
        return new Analysis(List.copyOf(blockers), List.copyOf(differences), List.copyOf(obligations),
                byEntity.entrySet().stream().collect(Collectors.toUnmodifiableMap(Map.Entry::getKey,
                        entry -> List.copyOf(entry.getValue()))));
    }

    private void validateEnvelope(AfsmEntity entity, Set<String> targetModules, Set<String> uirSourceMaps,
                                  Set<String> blockers, Map<String,List<String>> byEntity) {
        if (!"1.0".equals(entity.afsmVersion())) add(blockers, byEntity, entity.entityId(), "unsupported-afsm-version");
        if (!ENTITY_KINDS.contains(entity.entityKind())) add(blockers, byEntity, entity.entityId(), "unknown-afsm-entity-kind");
        if (blank(entity.targetModuleId()) || !targetModules.contains(entity.targetModuleId()))
            add(blockers, byEntity, entity.entityId(), "unknown-target-module");
        if (blank(entity.sourceFramework()) || blank(entity.sourceVersion()) || blank(entity.targetFramework()))
            add(blockers, byEntity, entity.entityId(), "framework-identity-incomplete");
        if (entity.sourceMapIds().isEmpty() || !uirSourceMaps.containsAll(entity.sourceMapIds()))
            add(blockers, byEntity, entity.entityId(), "afsm-source-map-invalid");
        if (entity.provenance() == null || blank(entity.provenance().extractor())
                || blank(entity.provenance().extractorVersion()) || entity.provenance().confidence() <= 0
                || entity.provenance().observedAt() == null || entity.provenance().evidenceRefs().isEmpty())
            add(blockers, byEntity, entity.entityId(), "afsm-provenance-incomplete");
        if (hasSecretMaterial(entity.attributes())) add(blockers, byEntity, entity.entityId(), "secret-material-in-afsm");
        if ("endpoint".equals(entity.entityKind())) {
            for (String key : List.of("route", "methods", "access"))
                if (blank(entity.attributes().get(key))) add(blockers, byEntity, entity.entityId(), "endpoint-" + key + "-missing");
        }
        if ("scheduled-job".equals(entity.entityKind()) && blank(entity.attributes().get("timezone")))
            add(blockers, byEntity, entity.entityId(), "scheduler-timezone-missing");
        if (("configuration-binding".equals(entity.entityKind()) || "configuration-source".equals(entity.entityKind()))
                && "true".equalsIgnoreCase(entity.attributes().get("secret"))
                && blank(entity.attributes().get("secretReference")))
            add(blockers, byEntity, entity.entityId(), "secret-reference-missing");
    }

    private void validateRoutes(Collection<AfsmEntity> entities, Set<String> blockers,
                                Map<String,List<String>> byEntity) {
        Map<String,List<AfsmEntity>> routes = entities.stream().filter(entity -> "endpoint".equals(entity.entityKind()))
                .collect(Collectors.groupingBy(entity -> entity.targetModuleId() + "\u001f"
                        + entity.attributes().get("methods") + "\u001f" + entity.attributes().get("route")));
        routes.values().stream().filter(values -> values.size() > 1).forEach(values -> values.forEach(entity ->
                add(blockers, byEntity, entity.entityId(), "route-conflict")));
    }

    private void validateProtectedEndpoints(Map<String,AfsmEntity> entities, Set<String> blockers,
                                            Map<String,List<String>> byEntity) {
        for (AfsmEntity endpoint : entities.values()) {
            if (!"endpoint".equals(endpoint.entityKind()) || !"protected".equals(endpoint.attributes().get("access"))) continue;
            boolean authn = endpoint.relatedEntityIds().stream().map(entities::get).filter(Objects::nonNull)
                    .anyMatch(entity -> "authentication-scheme".equals(entity.entityKind()));
            boolean authz = endpoint.relatedEntityIds().stream().map(entities::get).filter(Objects::nonNull)
                    .anyMatch(entity -> "authorization-policy".equals(entity.entityKind()));
            if (!authn) add(blockers, byEntity, endpoint.entityId(), "protected-endpoint-authentication-missing");
            if (!authz) add(blockers, byEntity, endpoint.entityId(), "protected-endpoint-authorization-missing");
        }
    }

    private void validateCaptiveDependencies(Map<String,AfsmEntity> entities, Set<String> blockers,
                                             Map<String,List<String>> byEntity) {
        for (AfsmEntity provider : entities.values()) {
            if (!"provider".equals(provider.entityKind())) continue;
            int ownerRank = scopeRank(provider.attributes().get("scope"));
            for (String relation : provider.relatedEntityIds()) {
                AfsmEntity captured = entities.get(relation);
                if (captured != null && "provider".equals(captured.entityKind())
                        && ownerRank > scopeRank(captured.attributes().get("scope")))
                    add(blockers, byEntity, provider.entityId(), "captive-dependency:" + captured.entityId());
            }
        }
    }

    private void compareSemantics(AfsmEntity entity, Emission emission, Instant observedAt,
                                  Set<String> blockers, Map<String,List<String>> byEntity,
                                  List<SemanticDifference> differences,
                                  List<SemanticObligation> obligations) {
        for (String key : SEMANTIC_KEYS.getOrDefault(entity.entityKind(), List.of())) {
            String source = entity.attributes().get(key);
            if (blank(source)) continue;
            String target = emission.targetSemantics().get(key);
            if (Objects.equals(source, target)) continue;
            boolean verifiedEquivalent = "verified".equals(emission.targetSemantics().get("equivalence." + key))
                    && !blank(emission.targetSemantics().get("equivalenceEvidence." + key));
            String differenceId = FrameworkIds.id("afsm-diff", entity.entityId(), key, source, target);
            String obligationId = verifiedEquivalent ? null : FrameworkIds.id("obligation", differenceId);
            differences.add(new SemanticDifference(differenceId, entity.entityId(), key, source, target,
                    verifiedEquivalent ? "verified-equivalent" : "not-equivalent", verifiedEquivalent ? "medium" : "high", obligationId));
            if (!verifiedEquivalent) {
                add(blockers, byEntity, entity.entityId(), "semantic-drift:" + key);
                obligations.add(new SemanticObligation(obligationId, entity.entityId(), key, "blocking", "open",
                        "Prove or remove framework semantic drift for " + key,
                        verificationFor(key), List.of(), null, null));
            }
        }
        if ("scheduled-job".equals(entity.entityKind()) && "durable".equals(entity.attributes().get("durability"))
                && "memory".equals(emission.targetSemantics().get("durability")))
            add(blockers, byEntity, entity.entityId(), "durable-job-downgraded-to-memory");
        if (("cache-region".equals(entity.entityKind()) || "cache-operation".equals(entity.entityKind()))
                && "true".equals(entity.attributes().get("tenantScoped"))
                && !"true".equals(emission.targetSemantics().get("tenantKeyIncluded")))
            add(blockers, byEntity, entity.entityId(), "tenant-cache-key-missing");
    }

    private void validatePipelineOrder(Collection<AfsmEntity> entities, Map<String,Emission> emissions,
                                       Set<String> blockers, Map<String,List<String>> byEntity) {
        List<AfsmEntity> components = entities.stream().filter(entity -> Set.of("middleware", "filter", "interceptor", "guard")
                .contains(entity.entityKind())).toList();
        checkOrder(components, emissions, "authentication", "authorization", blockers, byEntity);
    }

    private void checkOrder(List<AfsmEntity> components, Map<String,Emission> emissions,
                            String before, String after, Set<String> blockers,
                            Map<String,List<String>> byEntity) {
        Optional<AfsmEntity> sourceBefore = firstConcern(components, before, false, emissions);
        Optional<AfsmEntity> sourceAfter = firstConcern(components, after, false, emissions);
        if (sourceBefore.isPresent() && sourceAfter.isPresent()
                && order(sourceBefore.get().attributes().get("order")) >= order(sourceAfter.get().attributes().get("order")))
            add(blockers, byEntity, sourceAfter.get().entityId(), "source-authentication-authorization-order-invalid");
        Optional<AfsmEntity> targetBefore = firstConcern(components, before, true, emissions);
        Optional<AfsmEntity> targetAfter = firstConcern(components, after, true, emissions);
        if (targetBefore.isPresent() && targetAfter.isPresent()) {
            int b = order(emissions.get(targetBefore.get().entityId()).targetSemantics().get("order"));
            int a = order(emissions.get(targetAfter.get().entityId()).targetSemantics().get("order"));
            if (b >= a) add(blockers, byEntity, targetAfter.get().entityId(), "target-authentication-authorization-order-invalid");
        }
    }

    private Optional<AfsmEntity> firstConcern(List<AfsmEntity> components, String concern, boolean target,
                                              Map<String,Emission> emissions) {
        return components.stream().filter(entity -> {
                    if (!target) return concern.equals(entity.attributes().get("concern"));
                    Emission emission = emissions.get(entity.entityId());
                    return emission != null && concern.equals(emission.targetSemantics().get("concern"));
                }).min(Comparator.comparingInt(entity -> order(target
                        ? emissions.get(entity.entityId()).targetSemantics().get("order") : entity.attributes().get("order"))));
    }

    private <T> Map<String,T> unique(List<T> values, Function<T,String> id, Set<String> blockers, String diagnostic) {
        Map<String,T> result = new LinkedHashMap<>();
        for (T value : values) if (result.putIfAbsent(id.apply(value), value) != null) blockers.add(diagnostic + ":" + id.apply(value));
        return result;
    }

    private boolean isHighRisk(AfsmEntity entity) {
        return Set.of("authentication-scheme", "authorization-policy", "transaction-policy").contains(entity.entityKind())
                || ("endpoint".equals(entity.entityKind()) && "protected".equals(entity.attributes().get("access")));
    }

    private boolean hasSecretMaterial(Map<String,String> attributes) {
        return "true".equalsIgnoreCase(attributes.get("secretMaterialPresent"))
                || attributes.keySet().stream().map(key -> key.toLowerCase(Locale.ROOT))
                .anyMatch(key -> key.equals("secretvalue") || key.equals("passwordvalue")
                        || key.equals("tokenvalue") || key.equals("privatekey"));
    }

    private List<String> verificationFor(String key) {
        return switch (key) {
            case "route", "methods", "status", "contentType" -> List.of("route-table-diff", "openapi-diff", "differential-http-test");
            case "propagation", "isolation", "rollback" -> List.of("integration-test", "database-state-check", "manual-review");
            case "expression", "defaultDecision", "failureStatus" -> List.of("security-review", "permission-matrix-test");
            case "ack", "delivery", "ordering" -> List.of("message-contract-test", "failure-injection");
            case "timezone", "cronDialect", "fixedMode", "misfire" -> List.of("clock-simulation");
            default -> List.of("integration-test", "manual-review");
        };
    }

    private int scopeRank(String scope) {
        if (scope == null) return 0;
        return switch (scope) {
            case "application", "singleton-container" -> 6;
            case "module", "session" -> 5;
            case "request", "connection", "task", "thread" -> 3;
            case "transient", "prototype" -> 1;
            default -> 2;
        };
    }

    private int order(String value) {
        try { return Integer.parseInt(value); } catch (RuntimeException ignored) { return Integer.MAX_VALUE; }
    }

    private static boolean blank(String value) { return value == null || value.isBlank(); }

    private void add(Set<String> blockers, Map<String,List<String>> byEntity, String entity, String issue) {
        String value = entity + ":" + issue;
        blockers.add(value); byEntity.computeIfAbsent(entity, ignored -> new ArrayList<>()).add(issue);
    }
}
