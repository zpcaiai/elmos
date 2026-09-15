package io.elmos.recipes.web;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

import java.util.ArrayList;
import java.util.List;

/**
 * OpenRewrite recipe to modernize deprecated HandlerInterceptorAdapter to HandlerInterceptor interface.
 *
 * <p>Spring 5.3 deprecated {@code HandlerInterceptorAdapter} in favor of default methods on
 * {@code HandlerInterceptor}. In Spring 6 / Spring Boot 3, {@code HandlerInterceptorAdapter}
 * was removed completely.
 *
 * <p>This recipe:
 * <ul>
 *   <li>Replaces {@code extends HandlerInterceptorAdapter} with {@code implements HandlerInterceptor}.</li>
 *   <li>Removes import of {@code HandlerInterceptorAdapter}.</li>
 *   <li>Ensures import of {@code HandlerInterceptor}.</li>
 * </ul>
 */
public final class SpringHandlerInterceptorAdapterRecipe extends Recipe {

    private static final String ADAPTER_NAME = "HandlerInterceptorAdapter";
    private static final String INTERFACE_NAME = "HandlerInterceptor";
    private static final String ADAPTER_FQN = "org.springframework.web.servlet.handler.HandlerInterceptorAdapter";
    private static final String INTERFACE_FQN = "org.springframework.web.servlet.HandlerInterceptor";

    @Override
    public String getDisplayName() {
        return "Modernize HandlerInterceptorAdapter to HandlerInterceptor";
    }

    @Override
    public String getDescription() {
        return "Migrates deprecated HandlerInterceptorAdapter inheritance to direct HandlerInterceptor interface implementation.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.ClassDeclaration visitClassDeclaration(J.ClassDeclaration classDecl, ExecutionContext ctx) {
                J.ClassDeclaration cd = super.visitClassDeclaration(classDecl, ctx);
                if (cd.getExtends() != null && cd.getExtends().printTrimmed().contains(ADAPTER_NAME)) {
                    maybeRemoveImport(ADAPTER_FQN);
                    maybeAddImport(INTERFACE_FQN);

                    cd = cd.withExtends(null);

                    List<TypeTree> impls = new ArrayList<>();
                    if (cd.getImplements() != null) {
                        impls.addAll(cd.getImplements());
                    }

                    boolean alreadyImplements = impls.stream()
                            .anyMatch(t -> t.printTrimmed().contains(INTERFACE_NAME));

                    if (!alreadyImplements) {
                        impls.add(TypeTree.build(INTERFACE_NAME));
                    }
                    cd = cd.withImplements(impls);
                }
                return cd;
            }
        };
    }
}
