package io.elmos.recipes.cloud;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Replaces Netflix Hystrix {@code @HystrixCommand} with Resilience4j {@code @CircuitBreaker}.
 */
public final class SpringCloudHystrixToResilience4jRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Migrate Netflix Hystrix to Resilience4j";
    }

    @Override
    public String getDescription() {
        return "Replaces @HystrixCommand with Resilience4j @CircuitBreaker.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("HystrixCommand".equals(a.getSimpleName())) {
                    maybeRemoveImport("com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand");
                    maybeAddImport("io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker");
                    a = a.withAnnotationType(TypeTree.build("CircuitBreaker"));
                } else if ("EnableCircuitBreaker".equals(a.getSimpleName()) || "EnableHystrix".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.cloud.client.circuitbreaker.EnableCircuitBreaker");
                    maybeRemoveImport("org.springframework.cloud.netflix.hystrix.EnableHystrix");
                }
                return a;
            }
        };
    }
}
