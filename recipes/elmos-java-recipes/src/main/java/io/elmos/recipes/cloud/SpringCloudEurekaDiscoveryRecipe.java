package io.elmos.recipes.cloud;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes legacy Eureka client annotations:
 * - {@code @EnableEurekaClient} -> {@code @EnableDiscoveryClient}
 */
public final class SpringCloudEurekaDiscoveryRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Migrate @EnableEurekaClient to @EnableDiscoveryClient";
    }

    @Override
    public String getDescription() {
        return "Replaces legacy @EnableEurekaClient with standard Spring Cloud @EnableDiscoveryClient.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("EnableEurekaClient".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.cloud.netflix.eureka.EnableEurekaClient");
                    maybeAddImport("org.springframework.cloud.client.discovery.EnableDiscoveryClient");
                    a = a.withAnnotationType(TypeTree.build("EnableDiscoveryClient"));
                }
                return a;
            }
        };
    }
}
