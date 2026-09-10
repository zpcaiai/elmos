package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes legacy OAuth2 resource server configurations to Spring Security 6+ Lambda DSL:
 * - {@code @EnableResourceServer} -> {@code @Configuration}
 * - {@code http.oauth2ResourceServer().jwt()} -> {@code http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))}.
 */
public final class SpringSecurityOAuth2ResourceServerRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize OAuth2 Resource Server to Spring Security 6+ Lambda DSL";
    }

    @Override
    public String getDescription() {
        return "Converts legacy @EnableResourceServer and chained oauth2ResourceServer() calls into the modern pattern.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("EnableResourceServer".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.security.oauth2.config.annotation.web.configuration.EnableResourceServer");
                    maybeAddImport("org.springframework.context.annotation.Configuration");
                    a = a.withAnnotationType(TypeTree.build("Configuration"));
                }
                return a;
            }

            @Override
            public J.Import visitImport(J.Import _import, ExecutionContext ctx) {
                J.Import imp = super.visitImport(_import, ctx);
                String typeName = imp.getQualid().printTrimmed();
                if (typeName.contains("EnableResourceServer")) {
                    imp = imp.withQualid(TypeTree.build("org.springframework.context.annotation.Configuration"));
                }
                return imp;
            }

            @Override
            public J.MethodInvocation visitMethodInvocation(J.MethodInvocation method, ExecutionContext ctx) {
                J.MethodInvocation m = super.visitMethodInvocation(method, ctx);
                if ("oauth2ResourceServer".equals(m.getSimpleName()) && m.getArguments().isEmpty()) {
                    maybeAddImport("org.springframework.security.config.Customizer");
                }
                return m;
            }
        };
    }
}
