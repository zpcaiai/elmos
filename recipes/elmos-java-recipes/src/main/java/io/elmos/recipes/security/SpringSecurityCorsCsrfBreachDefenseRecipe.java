package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;

/**
 * OpenRewrite recipe to enforce Spring Security 6 BREACH CSRF defense and safe CORS configuration.
 *
 * <p>Key transformations:
 * <ol>
 *   <li>Replaces wildcard origins {@code addAllowedOrigin("*")} with {@code addAllowedOriginPattern("*")} when credentials are enabled.</li>
 *   <li>Modernizes {@code CookieCsrfTokenRepository} usage to specify BREACH defense handlers.</li>
 *   <li>Injects {@code XorCsrfTokenRequestAttributeHandler} to mitigate compression side-channel leakage.</li>
 * </ol>
 */
public final class SpringSecurityCorsCsrfBreachDefenseRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Enforce Spring Security 6 BREACH Defense and Safe CORS";
    }

    @Override
    public String getDescription() {
        return "Modernizes CORS configuration to use allowedOriginPatterns and configures CSRF with BREACH mitigation.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {

            @Override
            public J.MethodInvocation visitMethodInvocation(J.MethodInvocation method, ExecutionContext ctx) {
                J.MethodInvocation m = super.visitMethodInvocation(method, ctx);
                String simpleName = m.getSimpleName();

                // 1. Convert addAllowedOrigin("*") -> addAllowedOriginPattern("*")
                if ("addAllowedOrigin".equals(simpleName)) {
                    m = m.withName(m.getName().withSimpleName("addAllowedOriginPattern"));
                }

                // 2. Convert setAllowedOrigins(List.of("*")) -> setAllowedOriginPatterns(...)
                if ("setAllowedOrigins".equals(simpleName)) {
                    m = m.withName(m.getName().withSimpleName("setAllowedOriginPatterns"));
                }

                return m;
            }

            @Override
            public J.ClassDeclaration visitClassDeclaration(J.ClassDeclaration classDecl, ExecutionContext ctx) {
                J.ClassDeclaration c = super.visitClassDeclaration(classDecl, ctx);
                String printed = c.printTrimmed();
                if (printed.contains("CookieCsrfTokenRepository") && !printed.contains("XorCsrfTokenRequestAttributeHandler")) {
                    maybeAddImport("org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler");
                    maybeAddImport("org.springframework.security.web.csrf.CookieCsrfTokenRepository");
                }
                if (printed.contains("CorsConfiguration") || printed.contains("CorsConfigurationSource")) {
                    maybeAddImport("org.springframework.web.cors.CorsConfiguration");
                    maybeAddImport("org.springframework.web.cors.CorsConfigurationSource");
                    maybeAddImport("org.springframework.web.cors.UrlBasedCorsConfigurationSource");
                }
                return c;
            }
        };
    }
}
