package io.elmos.frameworkmigration;

import io.elmos.skeleton.SkeletonModels;

import java.util.*;

import static io.elmos.frameworkmigration.FrameworkMigrationModels.*;

/** Deterministic, production-only AFSM recipe selection. */
final class FrameworkRecipeRegistry {
    List<RecipePlan> plan(List<AfsmEntity> entities, List<Recipe> recipes,
                          SkeletonModels.TargetProfile profile, String targetFrameworkVersion) {
        return entities.stream().sorted(Comparator.comparing(AfsmEntity::entityId))
                .map(entity -> plan(entity, recipes, profile, targetFrameworkVersion)).toList();
    }

    private RecipePlan plan(AfsmEntity entity, List<Recipe> recipes,
                            SkeletonModels.TargetProfile profile, String targetFrameworkVersion) {
        List<Recipe> matches = recipes.stream()
                .filter(recipe -> matches(recipe, entity, targetFrameworkVersion))
                .sorted(Comparator.comparingInt(Recipe::specificity).reversed()
                        .thenComparing(Comparator.comparingInt(Recipe::priority).reversed())
                        .thenComparing(Recipe::recipeId).thenComparing(Recipe::version))
                .toList();
        if (matches.isEmpty()) return blocked(entity, "no-production-recipe");
        Recipe winner = matches.getFirst();
        if (matches.size() > 1 && matches.get(1).specificity() == winner.specificity()
                && matches.get(1).priority() == winner.priority()) {
            return blocked(entity, "ambiguous-recipe:" + winner.recipeId() + "," + matches.get(1).recipeId());
        }
        List<String> unapproved = winner.requiredDependencies().stream()
                .filter(dependency -> !profile.approvedDependencies().contains(dependency)).sorted().toList();
        if (!unapproved.isEmpty()) return blocked(entity, "unapproved-recipe-dependencies:" + String.join(",", unapproved));
        List<String> obligationIds = winner.obligationTemplates().stream()
                .map(template -> FrameworkIds.id("obligation", entity.entityId(), winner.recipeId(), template)).toList();
        String planId = FrameworkIds.id("framework-plan", entity.entityId(), winner.recipeId(), winner.version());
        return new RecipePlan(planId, entity.entityId(), winner.recipeId(),
                matches.stream().skip(1).map(Recipe::recipeId).distinct().toList(),
                winner.transformations(), winner.requiredDependencies(), obligationIds,
                "planned", true, List.of());
    }

    private boolean matches(Recipe recipe, AfsmEntity entity, String targetFrameworkVersion) {
        return recipe.production() && recipe.idempotent()
                && recipe.tests() != null && !recipe.tests().isEmpty()
                && recipe.provenanceRef() != null && !recipe.provenanceRef().isBlank()
                && recipe.entityKind().equals(entity.entityKind())
                && wildcard(recipe.sourceFramework(), entity.sourceFramework())
                && wildcard(recipe.targetFramework(), entity.targetFramework())
                && version(recipe.sourceVersionRange(), entity.sourceVersion())
                && version(recipe.targetVersionRange(), targetFrameworkVersion);
    }

    private boolean wildcard(String expected, String actual) {
        return "*".equals(expected) || Objects.equals(expected, actual);
    }

    private boolean version(String range, String actual) {
        if (range == null || range.isBlank() || "*".equals(range)) return true;
        return actual != null && (range.equals(actual) || (range.endsWith(".*") && actual.startsWith(range.substring(0, range.length()-1))));
    }

    private RecipePlan blocked(AfsmEntity entity, String diagnostic) {
        String id = FrameworkIds.id("framework-plan", entity.entityId(), diagnostic);
        return new RecipePlan(id, entity.entityId(), null, List.of(), List.of(), List.of(),
                List.of(FrameworkIds.id("obligation", entity.entityId(), diagnostic)),
                "blocked", false, List.of(diagnostic));
    }
}
