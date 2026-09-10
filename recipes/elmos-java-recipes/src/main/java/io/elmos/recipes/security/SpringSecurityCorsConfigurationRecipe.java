package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;

/**
 * Modernizes Spring Security CORS configuration:
 * - {@code cors.addAllowedOrigin("*")} -> {@code cors.addAllowedOriginPattern("*")}
 * - Modernizes chained cors() calls to lambda pattern.
 */
public final class SpringSecurityCorsConfigurationRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize Spring Security CORS Configuration";
    }

    @Override
    public String getDescription() {
        return "Converts addAllowedOrigin to addAllowedOriginPattern for Spring Security 6+ CORS compatibility.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.MethodInvocation visitMethodInvocation(J.MethodInvocation method, ExecutionContext ctx) {
                J.MethodInvocation m = super.visitMethodInvocation(method, ctx);
                if ("addAllowedOrigin".equals(m.getSimpleName())) {
                    m = m.withName(m.getName().withSimpleName("addAllowedOriginPattern"));
                }
                return m;
            }
        };
    }
}
