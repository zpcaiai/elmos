package io.elmos.recipes.cloud;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes legacy Spring Cloud Netflix Feign annotations to Spring Cloud OpenFeign:
 * - {@code org.springframework.cloud.netflix.feign.FeignClient} -> {@code org.springframework.cloud.openfeign.FeignClient}
 * - {@code org.springframework.cloud.netflix.feign.EnableFeignClients} -> {@code org.springframework.cloud.openfeign.EnableFeignClients}
 */
public final class SpringCloudOpenFeignModernizationRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Migrate Netflix Feign to Spring Cloud OpenFeign";
    }

    @Override
    public String getDescription() {
        return "Updates package imports and annotations from legacy Netflix Feign to Spring Cloud OpenFeign.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Import visitImport(J.Import _import, ExecutionContext ctx) {
                J.Import imp = super.visitImport(_import, ctx);
                String typeName = imp.getQualid().printTrimmed();
                if (typeName.startsWith("org.springframework.cloud.netflix.feign")) {
                    String newName = typeName.replace("org.springframework.cloud.netflix.feign", "org.springframework.cloud.openfeign");
                    imp = imp.withQualid(TypeTree.build(newName));
                }
                return imp;
            }
        };
    }
}
