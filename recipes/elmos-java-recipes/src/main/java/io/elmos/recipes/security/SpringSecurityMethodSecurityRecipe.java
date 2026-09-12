package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes legacy method security annotations:
 * {@code @EnableGlobalMethodSecurity(prePostEnabled = true)} -> {@code @EnableMethodSecurity(prePostEnabled = true)}.
 */
public final class SpringSecurityMethodSecurityRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize @EnableGlobalMethodSecurity to @EnableMethodSecurity";
    }

    @Override
    public String getDescription() {
        return "Migrates Spring Security method-level security configuration to Spring Security 6+ @EnableMethodSecurity.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("EnableGlobalMethodSecurity".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity");
                    maybeAddImport("org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity");
                    a = a.withAnnotationType(TypeTree.build("EnableMethodSecurity"));
                }
                return a;
            }
        };
    }
}
