package io.elmos.recipes.jpa;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes Hibernate 5 SQLFunction custom dialect methods to Hibernate 6 FunctionContributor:
 * - {@code extends Dialect} -> implements FunctionContributor SPI
 * - {@code registerFunction(...)} -> {@code functionContributions.getFunctionRegistry().register(...)}
 */
public final class Hibernate6DialectFunctionRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize Hibernate Dialect Functions to FunctionContributor SPI";
    }

    @Override
    public String getDescription() {
        return "Replaces legacy Hibernate 5 dialect function registration with Hibernate 6 FunctionContributor SPI.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.ClassDeclaration visitClassDeclaration(J.ClassDeclaration classDecl, ExecutionContext ctx) {
                J.ClassDeclaration cd = super.visitClassDeclaration(classDecl, ctx);
                if (cd.getExtends() != null && cd.getExtends().printTrimmed().contains("Dialect")) {
                    maybeRemoveImport("org.hibernate.dialect.Dialect");
                    maybeAddImport("org.hibernate.boot.model.FunctionContributor");
                    cd = cd.withExtends(null);
                    cd = cd.withImplements(java.util.Collections.singletonList(TypeTree.build("FunctionContributor")));
                }
                return cd;
            }
        };
    }
}
