package io.elmos.recipes.cloud;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Replaces legacy Netflix Ribbon annotations with Spring Cloud LoadBalancer:
 * {@code @RibbonClient(name = "x")} -> {@code @LoadBalancerClient(name = "x")}.
 */
public final class SpringCloudRibbonToLoadBalancerRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Migrate Netflix Ribbon to Spring Cloud LoadBalancer";
    }

    @Override
    public String getDescription() {
        return "Replaces @RibbonClient and @RibbonClients with @LoadBalancerClient and @LoadBalancerClients.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("RibbonClient".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.cloud.netflix.ribbon.RibbonClient");
                    maybeAddImport("org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient");
                    a = a.withAnnotationType(TypeTree.build("LoadBalancerClient"));
                } else if ("RibbonClients".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.cloud.netflix.ribbon.RibbonClients");
                    maybeAddImport("org.springframework.cloud.loadbalancer.annotation.LoadBalancerClients");
                    a = a.withAnnotationType(TypeTree.build("LoadBalancerClients"));
                }
                return a;
            }
        };
    }
}
