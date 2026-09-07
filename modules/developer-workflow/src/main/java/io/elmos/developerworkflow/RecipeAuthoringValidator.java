package io.elmos.developerworkflow;

import java.util.List;
import java.util.Set;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class RecipeAuthoringValidator {
    public record Recipe(String recipeId, String inputSchema, String outputSchema, List<String> typedSteps,
                         Set<String> allowedTools, boolean arbitraryScript, boolean negativePassed,
                         boolean holdoutPassed, boolean signed) {
        public Recipe { typedSteps=List.copyOf(typedSteps); allowedTools=Set.copyOf(allowedTools); }
    }
    public PolicyDecision validate(Recipe recipe, Set<String> toolAllowlist) {
        if (recipe.recipeId().isBlank() || recipe.inputSchema().isBlank() || recipe.outputSchema().isBlank() || recipe.typedSteps().isEmpty()) return PolicyDecision.deny("RECIPE_CONTRACT_INCOMPLETE");
        if (recipe.arbitraryScript()) return PolicyDecision.deny("ARBITRARY_RECIPE_SCRIPT_DENIED");
        if (!toolAllowlist.containsAll(recipe.allowedTools())) return PolicyDecision.deny("RECIPE_TOOL_NOT_ALLOWLISTED");
        if (!recipe.negativePassed() || !recipe.holdoutPassed()) return PolicyDecision.escalate("RECIPE_CORPUS_INCOMPLETE",recipe.recipeId());
        if (!recipe.signed()) return PolicyDecision.escalate("RECIPE_SIGNATURE_REQUIRED",recipe.recipeId());
        return PolicyDecision.allow("RECIPE_READY",recipe.recipeId());
    }
}
