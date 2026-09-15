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
 * OpenRewrite recipe to modernize deprecated WebMvcConfigurerAdapter to WebMvcConfigurer interface.
 *
 * <p>Spring 5.0 introduced Java 8 default methods on {@code WebMvcConfigurer} and deprecated
 * {@code WebMvcConfigurerAdapter}. In Spring Boot 3 / Spring 6, {@code WebMvcConfigurerAdapter}
 * was completely removed.
 *
 * <p>This recipe:
 * <ul>
 *   <li>Replaces {@code extends WebMvcConfigurerAdapter} with {@code implements WebMvcConfigurer}.</li>
 *   <li>Removes import of {@code WebMvcConfigurerAdapter}.</li>
 *   <li>Ensures import of {@code WebMvcConfigurer}.</li>
 * </ul>
 */
public final class SpringWebMvcConfigurerAdapterRecipe extends Recipe {

    private static final String ADAPTER_NAME = "WebMvcConfigurerAdapter";
    private static final String INTERFACE_NAME = "WebMvcConfigurer";
    private static final String ADAPTER_FQN = "org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter";
    private static final String INTERFACE_FQN = "org.springframework.web.servlet.config.annotation.WebMvcConfigurer";

    @Override
    public String getDisplayName() {
        return "Modernize WebMvcConfigurerAdapter to WebMvcConfigurer";
    }

    @Override
    public String getDescription() {
        return "Migrates deprecated WebMvcConfigurerAdapter inheritance to direct WebMvcConfigurer interface implementation.";
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
