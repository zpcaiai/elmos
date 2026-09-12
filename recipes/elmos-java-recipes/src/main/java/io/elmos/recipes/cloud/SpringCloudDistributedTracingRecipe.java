package io.elmos.recipes.cloud;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes Spring Cloud Sleuth to Micrometer Tracing:
 * - {@code org.springframework.cloud.sleuth.Tracer} -> {@code io.micrometer.tracing.Tracer}
 * - {@code org.springframework.cloud.sleuth.SpanCustomizer} -> {@code io.micrometer.tracing.SpanCustomizer}
 * - {@code org.springframework.cloud.sleuth.annotation.NewSpan} -> {@code io.micrometer.tracing.annotation.NewSpan}
 */
public final class SpringCloudDistributedTracingRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Migrate Spring Cloud Sleuth to Micrometer Tracing";
    }

    @Override
    public String getDescription() {
        return "Replaces legacy Spring Cloud Sleuth tracing types and annotations with Micrometer Tracing.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Import visitImport(J.Import _import, ExecutionContext ctx) {
                J.Import imp = super.visitImport(_import, ctx);
                String typeName = imp.getQualid().printTrimmed();
                if (typeName.startsWith("org.springframework.cloud.sleuth")) {
                    String newName = typeName.replace("org.springframework.cloud.sleuth", "io.micrometer.tracing");
                    imp = imp.withQualid(TypeTree.build(newName));
                }
                return imp;
            }
        };
    }
}
