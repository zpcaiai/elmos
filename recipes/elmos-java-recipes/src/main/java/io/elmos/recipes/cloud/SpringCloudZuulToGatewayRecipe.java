package io.elmos.recipes.cloud;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Migrates Netflix Zuul legacy proxy annotations and filters to Spring Cloud Gateway:
 * - {@code @EnableZuulProxy} / {@code @EnableZuulServer} -> {@code @Configuration}
 * - {@code extends ZuulFilter} -> {@code implements GlobalFilter}
 */
public final class SpringCloudZuulToGatewayRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Migrate Netflix Zuul to Spring Cloud Gateway";
    }

    @Override
    public String getDescription() {
        return "Replaces legacy @EnableZuulProxy with Spring Cloud Gateway configuration and modernizes filter interfaces.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("EnableZuulProxy".equals(a.getSimpleName()) || "EnableZuulServer".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.cloud.netflix.zuul.EnableZuulProxy");
                    maybeRemoveImport("org.springframework.cloud.netflix.zuul.EnableZuulServer");
                    maybeAddImport("org.springframework.context.annotation.Configuration");
                    a = a.withAnnotationType(TypeTree.build("Configuration"));
                }
                return a;
            }

            @Override
            public J.ClassDeclaration visitClassDeclaration(J.ClassDeclaration classDecl, ExecutionContext ctx) {
                J.ClassDeclaration cd = super.visitClassDeclaration(classDecl, ctx);
                if (cd.getExtends() != null && "ZuulFilter".equals(cd.getExtends().printTrimmed())) {
                    maybeRemoveImport("com.netflix.zuul.ZuulFilter");
                    maybeRemoveImport("com.netflix.zuul.context.RequestContext");
                    maybeRemoveImport("com.netflix.zuul.exception.ZuulException");
                    maybeAddImport("org.springframework.cloud.gateway.filter.GlobalFilter");
                    maybeAddImport("org.springframework.core.Ordered");
                    cd = cd.withExtends(null);
                    
                    java.util.List<TypeTree> impls = new java.util.ArrayList<>();
                    if (cd.getImplements() != null) {
                        impls.addAll(cd.getImplements());
                    }
                    impls.add(TypeTree.build("GlobalFilter"));
                    impls.add(TypeTree.build("Ordered"));
                    cd = cd.withImplements(impls);
                }
                return cd;
            }

            @Override
            public J.MethodDeclaration visitMethodDeclaration(J.MethodDeclaration method, ExecutionContext ctx) {
                J.MethodDeclaration md = super.visitMethodDeclaration(method, ctx);
                if ("filterOrder".equals(md.getSimpleName())) {
                    md = md.withName(md.getName().withSimpleName("getOrder"));
                } else if ("run".equals(md.getSimpleName())) {
                    maybeAddImport("org.springframework.cloud.gateway.filter.GatewayFilterChain");
                    maybeAddImport("org.springframework.web.server.ServerWebExchange");
                    maybeAddImport("reactor.core.publisher.Mono");
                    md = md.withName(md.getName().withSimpleName("filter"));
                    md = md.withReturnTypeExpression(TypeTree.build("Mono<Void>"));
                }
                return md;
            }
        };
    }
}
