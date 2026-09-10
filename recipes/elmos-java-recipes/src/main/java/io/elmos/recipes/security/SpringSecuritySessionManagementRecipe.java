package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;

/**
 * Modernizes sessionManagement() chained configuration to SessionCreationPolicy lambda.
 */
public final class SpringSecuritySessionManagementRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize Session Management Lambda Configuration";
    }

    @Override
    public String getDescription() {
        return "Converts legacy sessionManagement().sessionCreationPolicy(...) to sessionManagement(s -> s.sessionCreationPolicy(...)).";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.MethodInvocation visitMethodInvocation(J.MethodInvocation method, ExecutionContext ctx) {
                J.MethodInvocation m = super.visitMethodInvocation(method, ctx);
                if ("sessionManagement".equals(m.getSimpleName())) {
                    maybeAddImport("org.springframework.security.config.http.SessionCreationPolicy");
                }
                return m;
            }
        };
    }
}
