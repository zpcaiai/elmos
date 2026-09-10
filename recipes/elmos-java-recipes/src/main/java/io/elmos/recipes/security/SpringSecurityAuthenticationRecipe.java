package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes AuthenticationManagerBuilder configuration to @Bean AuthenticationManager in Spring Security 6+.
 */
public final class SpringSecurityAuthenticationRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize AuthenticationManagerBuilder to AuthenticationManager @Bean";
    }

    @Override
    public String getDescription() {
        return "Converts configure(AuthenticationManagerBuilder auth) methods into modern @Bean AuthenticationManager declarations.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.MethodDeclaration visitMethodDeclaration(J.MethodDeclaration method, ExecutionContext ctx) {
                J.MethodDeclaration m = super.visitMethodDeclaration(method, ctx);
                if ("configure".equals(m.getSimpleName()) && m.getParameters().size() == 1) {
                    String paramType = m.getParameters().get(0).printTrimmed();
                    if (paramType.contains("AuthenticationManagerBuilder")) {
                        maybeRemoveImport("org.springframework.security.config.annotation.authentication.builders.AuthenticationManagerBuilder");
                        maybeAddImport("org.springframework.context.annotation.Bean");
                        maybeAddImport("org.springframework.security.authentication.AuthenticationManager");
                        maybeAddImport("org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration");
                        m = m.withReturnTypeExpression(TypeTree.build("AuthenticationManager"));
                        m = m.withName(m.getName().withSimpleName("authenticationManager"));
                    }
                }
                return m;
            }
        };
    }
}
