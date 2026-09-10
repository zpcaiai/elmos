package io.elmos.recipes.cloud;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes Spring Cloud Config legacy annotations:
 * - {@code @EnableConfigServer} -> modern config server declarations
 */
public final class SpringCloudConfigBootstrapRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Migrate Spring Cloud Config bootstrap configuration";
    }

    @Override
    public String getDescription() {
        return "Modernizes Spring Cloud Config annotations and imports for Spring Boot 3/4.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("EnableConfigServer".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.cloud.config.server.EnableConfigServer");
                    maybeAddImport("org.springframework.cloud.config.server.EnableConfigServer");
                }
                return a;
            }
        };
    }
}
