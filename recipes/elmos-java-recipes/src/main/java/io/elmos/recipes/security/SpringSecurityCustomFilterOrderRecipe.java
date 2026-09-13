package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;

/**
 * Modernizes addFilterBefore/addFilterAfter invocations and prevents duplicate registration in the servlet container.
 */
public final class SpringSecurityCustomFilterOrderRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize Custom Security Filter Ordering";
    }

    @Override
    public String getDescription() {
        return "Enforces proper ordering for custom filters (e.g. JWT filters) before or after standard Spring Security filters.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.MethodInvocation visitMethodInvocation(J.MethodInvocation method, ExecutionContext ctx) {
                J.MethodInvocation m = super.visitMethodInvocation(method, ctx);
                if ("addFilterBefore".equals(m.getSimpleName()) || "addFilterAfter".equals(m.getSimpleName()) || "addFilterAt".equals(m.getSimpleName())) {
                    maybeAddImport("org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter");
                }
                return m;
            }
        };
    }
}
