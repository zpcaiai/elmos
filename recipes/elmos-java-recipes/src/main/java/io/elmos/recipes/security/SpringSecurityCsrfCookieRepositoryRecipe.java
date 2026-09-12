package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.JavaTemplate;
import org.openrewrite.java.tree.J;

/**
 * Updates CookieCsrfTokenRepository constructor invocation to CookieCsrfTokenRepository.withHttpOnlyFalse().
 */
public final class SpringSecurityCsrfCookieRepositoryRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize CSRF Cookie Token Repository";
    }

    @Override
    public String getDescription() {
        return "Converts new CookieCsrfTokenRepository() to CookieCsrfTokenRepository.withHttpOnlyFalse().";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.VariableDeclarations visitVariableDeclarations(J.VariableDeclarations multiVariable, ExecutionContext ctx) {
                J.VariableDeclarations mv = super.visitVariableDeclarations(multiVariable, ctx);
                return (J.VariableDeclarations) JavaTemplate.builder("CookieCsrfTokenRepository #{} = CookieCsrfTokenRepository.withHttpOnlyFalse()")
                        .contextSensitive()
                        .build()
                        .apply(getCursor(), mv.getCoordinates().replace(), mv.getVariables().get(0).getSimpleName());
            }
        };
    }
}
